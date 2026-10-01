# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Logging: rotating files (5 × 2 MB), Activity model, redaction through bark/veil.

Spec S-03. Every record passes `bark.veil.VeilFilter` on the logging thread's queue handler
before any other handler sees it. A background listener writes the rotating file and fills the
in-memory ring buffer that backs the Activity screen, so logging never waits on the disk in the
UI thread.
"""

from __future__ import annotations

import io
import json
import logging
import logging.handlers
import platform
import queue
import threading
import time
import zipfile
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

from PySide6.QtCore import (
    QAbstractTableModel,
    QCoreApplication,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    QTimer,
    Signal,
)

import verdra
from verdra.bark import veil
from verdra.soil import atomic, terrain

FILE_BYTES = 2 * 1024 * 1024
FILE_COUNT = 5
RING_SIZE = 5_000
BUNDLE_LOG_LINES = 2_000
DETAILED_LOGGING_HOURS = 24
LOGGER_NAME = "verdra"

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

ModelIndex = QModelIndex | QPersistentModelIndex


@dataclass(frozen=True)
class ActivityRecord:
    """One redacted log record as the Activity screen shows it."""

    created: float
    level: int
    logger: str
    message: str

    @property
    def level_name(self) -> str:
        """Return the level's name: DEBUG, INFO, WARNING or ERROR."""
        return logging.getLevelName(self.level)

    def line(self) -> str:
        """Return the record as one line of text, as copied to the clipboard."""
        stamp = datetime.fromtimestamp(self.created).isoformat(sep=" ", timespec="seconds")
        return f"{stamp} {self.level_name:<7} {self.message}"


class RingBuffer:
    """The last records in memory, oldest dropped first; safe to use from any thread."""

    def __init__(self, size: int = RING_SIZE) -> None:
        self._records: deque[ActivityRecord] = deque(maxlen=size)
        self._lock = threading.Lock()

    def append(self, record: ActivityRecord) -> None:
        """Add a record."""
        with self._lock:
            self._records.append(record)

    def snapshot(self) -> list[ActivityRecord]:
        """Return the records, oldest first."""
        with self._lock:
            return list(self._records)

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


def matching(
    records: Iterable[ActivityRecord], text: str = "", levels: Iterable[int] | None = None
) -> list[ActivityRecord]:
    """Return the records whose message contains `text` (any case) and whose level is listed."""
    needle = text.casefold()
    wanted = set(levels) if levels is not None else None
    return [
        record
        for record in records
        if (wanted is None or record.level in wanted)
        and (not needle or needle in record.message.casefold())
    ]


class _RingHandler(logging.Handler):
    """Feeds the ring buffer and tells the Activity model, from the listener thread."""

    def __init__(self, ring: RingBuffer, notify: Callable[[ActivityRecord], None]) -> None:
        super().__init__()
        self._ring = ring
        self._notify = notify

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if record.exc_text:
            message = f"{message}\n{record.exc_text}"
        entry = ActivityRecord(record.created, record.levelno, record.name, message)
        self._ring.append(entry)
        self._notify(entry)


class _Bridge(QObject):
    """Carries new records from the listener thread to the Qt thread."""

    appended = Signal(object)


class ActivityModel(QAbstractTableModel):
    """The Activity screen's table: time, level and message of each record in the ring."""

    COLUMNS: ClassVar[tuple[str, ...]] = ("time", "level", "message")

    def __init__(self, ring: RingBuffer, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._records = ring.snapshot()
        self._limit = RING_SIZE

    def add(self, record: ActivityRecord) -> None:
        """Append a record (on the Qt thread), dropping the oldest beyond the ring's size."""
        if len(self._records) >= self._limit:
            self.beginRemoveRows(QModelIndex(), 0, 0)
            self._records.pop(0)
            self.endRemoveRows()
        row = len(self._records)
        self.beginInsertRows(QModelIndex(), row, row)
        self._records.append(record)
        self.endInsertRows()

    def record(self, row: int) -> ActivityRecord:
        """Return the record shown in a row."""
        return self._records[row]

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        """Return the number of records (Qt API)."""
        return 0 if parent.isValid() else len(self._records)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        """Return the number of columns (Qt API)."""
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Return a cell's text, or the record itself for Qt.UserRole (Qt API)."""
        if not index.isValid():
            return None
        record = self._records[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return record
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        column = self.COLUMNS[index.column()]
        if column == "time":
            return datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        if column == "level":
            return record.level_name.capitalize()
        return record.message


class Rings:
    """The app's logging: install once at startup, stop at shutdown.

    Attributes:
        ring: The in-memory records behind the Activity screen.
        log_file: The current log file.
    """

    def __init__(self, logs_dir: Path | None = None) -> None:
        self.logs_dir = logs_dir or terrain.logs_dir()
        self.log_file = self.logs_dir / terrain.LOG_FILE
        self.ring = RingBuffer()
        self._bridge = _Bridge()
        self._queue: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
        self._queue_handler = logging.handlers.QueueHandler(self._queue)
        self._queue_handler.addFilter(veil.VeilFilter())
        self._listener: logging.handlers.QueueListener | None = None
        self._models: list[ActivityModel] = []
        self._detailed = False

    def hold(self) -> None:
        """Queue `verdra` records from now on, so nothing logged before `start` is lost.

        Startup loads the settings (plan 8.4 step 2) before it starts logging (step 3); what the
        settings store reports then waits in the queue, redacted, and reaches the file and
        Activity when the listener starts.
        """
        root = logging.getLogger(LOGGER_NAME)
        if self._queue_handler not in root.handlers:
            root.addHandler(self._queue_handler)
        root.propagate = False
        if root.level == logging.NOTSET:
            root.setLevel(logging.INFO)

    def start(self, *, detailed: bool = False) -> None:
        """Install the handlers on the `verdra` logger and start the listener thread."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            self.log_file, maxBytes=FILE_BYTES, backupCount=FILE_COUNT - 1, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(_FORMAT))
        ring_handler = _RingHandler(self.ring, self._bridge.appended.emit)
        self._listener = logging.handlers.QueueListener(
            self._queue, file_handler, ring_handler, respect_handler_level=False
        )
        self._listener.start()
        root = logging.getLogger(LOGGER_NAME)
        if self._queue_handler not in root.handlers:
            root.addHandler(self._queue_handler)
        root.propagate = False
        self.set_detailed(detailed)

    def stop(self) -> None:
        """Flush every queued record to disk and remove the handlers."""
        logging.getLogger(LOGGER_NAME).removeHandler(self._queue_handler)
        if self._listener is not None:
            self._listener.stop()
            for handler in self._listener.handlers:
                handler.close()
            self._listener = None

    def set_detailed(self, detailed: bool) -> None:
        """Keep Debug records only while detailed logging is on."""
        self._detailed = detailed
        logging.getLogger(LOGGER_NAME).setLevel(logging.DEBUG if detailed else logging.INFO)

    def model(self, parent: QObject | None = None) -> ActivityModel:
        """Return a table model of the ring that grows as records arrive."""
        model = ActivityModel(self.ring, parent)
        self._bridge.appended.connect(model.add, Qt.ConnectionType.QueuedConnection)
        self._models.append(model)
        return model

    def tail(self, lines: int = BUNDLE_LOG_LINES) -> list[str]:
        """Return the last lines of the log files, oldest first (already redacted)."""
        files = [
            self.log_file.with_name(f"{self.log_file.name}.{n}")
            for n in range(FILE_COUNT - 1, 0, -1)
        ]
        collected: deque[str] = deque(maxlen=lines)
        for path in [*files, self.log_file]:
            try:
                with path.open(encoding="utf-8", errors="replace") as handle:
                    collected.extend(line.rstrip("\n") for line in handle)
            except FileNotFoundError:
                continue
        return list(collected)


def detailed_logging_expired(since: str, now: datetime | None = None) -> bool:
    """Return whether detailed logging, turned on at `since` (ISO 8601), has run for 24 hours."""
    if not since:
        return True
    try:
        started = datetime.fromisoformat(since)
    except ValueError:
        return True
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    return (now or datetime.now(UTC)) - started >= timedelta(hours=DETAILED_LOGGING_HOURS)


class DetailedLogging(QObject):
    """Keeps Settings › Advanced › "Detailed logging" in step with the log level.

    Turning it on records the time; 24 hours later (also across restarts) it turns itself off.
    """

    def __init__(self, rings: Rings, settings: Any, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rings = rings
        self._settings = settings
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._expire)
        settings.changed.connect(self._changed)
        self._apply()

    def _apply(self) -> None:
        on = bool(self._settings.value("advanced.detailed_logging"))
        since = str(self._settings.value("advanced.detailed_logging_since"))
        if on and detailed_logging_expired(since):
            self._expire()
            return
        self._rings.set_detailed(on)
        self._timer.stop()
        if on:
            started = datetime.fromisoformat(since)
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            remaining = started + timedelta(hours=DETAILED_LOGGING_HOURS) - datetime.now(UTC)
            self._timer.start(max(0, int(remaining.total_seconds() * 1000)))

    def _changed(self, key: str, value: object) -> None:
        if key != "advanced.detailed_logging" or self._settings.read_only:
            return
        if value:
            self._settings.set("advanced.detailed_logging_since", datetime.now(UTC).isoformat())
        self._apply()

    def _expire(self) -> None:
        self._timer.stop()
        self._rings.set_detailed(False)
        if not self._settings.read_only:
            self._settings.set("advanced.detailed_logging", False)
            self._settings.set("advanced.detailed_logging_since", "")
        logging.getLogger(__name__).info(
            "%s",
            QCoreApplication.translate(
                "M-LOG-04", "Detailed logging turned itself off after 24 hours."
            ),
        )


@dataclass(frozen=True)
class BundleSources:
    """What goes into a support bundle besides the logs (Master plan 13.9)."""

    routing_mode: str
    routing_status: str
    settings_file: Path
    ledger_file: Path
    profiles_dir: Path


def export_support_bundle(
    target: Path, rings: Rings, sources: BundleSources, *, include_profiles: bool = False
) -> Path:
    """Write the support bundle ZIP to `target` and return its path.

    Everything in it passes through the redaction filter. Nothing is uploaded.
    """
    about = {
        "version": verdra.__version__,
        "build": build_id(),
        "system": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "routing_mode": sources.routing_mode,
        "routing_status": sources.routing_status,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("about.json", json.dumps(about, indent=2) + "\n")
        log_text = "\n".join(veil.redact_text(line) for line in rings.tail()) + "\n"
        bundle.writestr(terrain.LOG_FILE, log_text)
        for name, path in (
            (terrain.SETTINGS_FILE, sources.settings_file),
            (terrain.LEDGER_FILE, sources.ledger_file),
        ):
            if path.is_file():
                bundle.writestr(name, _redacted_json(path))
        if include_profiles and sources.profiles_dir.is_dir():
            for profile in sorted(sources.profiles_dir.glob("*.json")):
                bundle.writestr(f"profiles/{profile.name}", _redacted_json(profile))
    atomic.write_atomic(target, buffer.getvalue())
    return target


def _redacted_json(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        return json.dumps(veil.redact_data(json.loads(text)), indent=2, ensure_ascii=False) + "\n"
    except ValueError:
        return veil.redact_text(text)


def build_id() -> str:
    """Return the build's short Git commit, recorded at build time, or "dev"."""
    stamp = Path(verdra.__file__).with_name("assets") / "build.txt"
    try:
        return stamp.read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"


def default_bundle_path() -> Path:
    """Return where "Export support bundle…" suggests saving (the exports folder)."""
    return terrain.exports_dir() / bundle_file_name()


def bundle_sources(settings: Any, routing_status: str = "Idle") -> BundleSources:
    """Return what goes into a support bundle besides the logs, from the current settings."""
    return BundleSources(
        routing_mode=str(settings.value("routing.mode")),
        routing_status=routing_status,
        settings_file=settings.path,
        ledger_file=terrain.config_dir() / terrain.LEDGER_FILE,
        profiles_dir=terrain.config_dir() / "profiles",
    )


def bundle_file_name(now: float | None = None) -> str:
    """Return the default file name for a support bundle."""
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    return f"Verdra support bundle {stamp}.zip"
