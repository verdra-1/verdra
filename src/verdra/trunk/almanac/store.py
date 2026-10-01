# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Load, validate, save atomically with .bak; change signals.

`SettingsStore` owns `settings.json` (spec S-02). It validates key by key, so a single bad value
is replaced by its default without losing the rest; keeps unknown keys so a newer Verdra's
settings survive a round trip; saves through `soil/atomic` at most once per 300 ms; and never
writes a file made by a newer Verdra. `StateStore` keeps the free-form UI state in `state.json`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import msgspec
from PySide6.QtCore import QCoreApplication, QObject, QTimer, Signal

from verdra.soil import atomic, terrain
from verdra.trunk.almanac import migrate, schema

log = logging.getLogger(__name__)

SAVE_DELAY_MS = 300

# Struct types that are groups of keys (walked into), as opposed to values (validated whole).
_GROUP_TYPES: tuple[type[msgspec.Struct], ...] = (
    schema.Settings,
    schema.General,
    schema.Routing,
    schema.Upstream,
    schema.Library,
    schema.Appearance,
    schema.Privacy,
    schema.Advanced,
    schema.Tweaks,
    schema.Accounts,
    schema.Traffic,
)


@dataclass(frozen=True)
class Notice:
    """A message the interface shows about the settings file (M-SET-01 to M-SET-03)."""

    message_id: str
    text: str


@dataclass
class Decoded:
    """The result of validating one parsed settings document."""

    settings: schema.Settings
    unknown: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


class DamagedFileError(ValueError):
    """A settings file isn't a readable settings document."""


class ReadOnlyError(RuntimeError):
    """The settings came from a newer Verdra and can't be changed."""


def decode(document: dict[str, Any]) -> Decoded:
    """Validate a settings document key by key against the schema.

    Missing keys take their defaults; an unknown key is kept in `unknown`; a value of the wrong
    type or out of range is replaced by its default and listed in `problems`.
    """
    body = {key: value for key, value in document.items() if key not in {"format", "version"}}
    settings, unknown, problems = _build(schema.Settings, body, "")
    assert isinstance(settings, schema.Settings)  # noqa: S101 - _build returns its struct type
    return Decoded(settings=settings, unknown=unknown, problems=problems)


def _build(
    struct_type: type[msgspec.Struct], raw: dict[str, Any], prefix: str
) -> tuple[msgspec.Struct, dict[str, Any], list[str]]:
    values: dict[str, Any] = {}
    unknown: dict[str, Any] = {}
    problems: list[str] = []
    names = set()
    for info in msgspec.structs.fields(struct_type):
        names.add(info.name)
        if info.name not in raw:
            continue
        dotted = f"{prefix}{info.name}"
        value = raw[info.name]
        if isinstance(info.type, type) and issubclass(info.type, _GROUP_TYPES):
            if isinstance(value, dict):
                values[info.name], nested, more = _build(info.type, value, dotted + ".")
                if nested:
                    unknown[info.name] = nested
                problems += more
            else:
                problems.append(f"{dotted}: expected a group of settings; using the defaults")
            continue
        try:
            values[info.name] = msgspec.convert(value, info.type, strict=True)
        except msgspec.ValidationError as error:
            problems.append(f"{dotted}: {error}; using the default")
    for key, value in raw.items():
        if key not in names:
            unknown[key] = value
            problems.append(f"{prefix}{key}: unknown setting, kept but ignored")
    return struct_type(**values), unknown, problems


def encode(settings: schema.Settings, unknown: dict[str, Any]) -> bytes:
    """Return the settings file's bytes: format and version first, unknown keys merged back."""
    body = msgspec.to_builtins(settings)
    _merge(body, unknown)
    document = {"format": schema.FORMAT, "version": schema.VERSION, **body}
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _merge(target: dict[str, Any], extra: dict[str, Any]) -> None:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target.setdefault(key, value)


def parse(data: bytes) -> dict[str, Any]:
    """Parse settings bytes, or raise DamagedFileError if they aren't a settings document."""
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DamagedFileError(str(error)) from error
    if not isinstance(document, dict) or document.get("format") != schema.FORMAT:
        raise DamagedFileError("not a Verdra settings file")
    version = document.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise DamagedFileError(f"invalid version {version!r}")
    return document


class SettingsStore(QObject):
    """Typed, versioned, crash-safe settings (spec S-02).

    Signals:
        changed(key, value): A setting changed; `key` is dotted ("appearance.theme").
    """

    changed = Signal(str, object)

    def __init__(self, path: Path | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.path = path or terrain.config_dir() / terrain.SETTINGS_FILE
        self.settings = schema.Settings()
        self.notices: list[Notice] = []
        self.read_only = False
        self._unknown: dict[str, Any] = {}
        self._dirty = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(SAVE_DELAY_MS)
        self._timer.timeout.connect(self.flush)

    # --- Loading ---------------------------------------------------------------------------

    def load(self) -> None:
        """Read the settings file, falling back to its .bak and then to defaults (plan 9.7)."""
        self.notices = []
        self.read_only = False
        if self.path.parent.exists():
            atomic.remove_stale_temporaries(self.path)
        document = self._read_with_fallback()
        if document is None:
            self.settings, self._unknown = schema.Settings(), {}
            return
        version = document["version"]
        if migrate.is_newer(version, schema.VERSION):
            self.read_only = True
            self._notify(
                "M-SET-03",
                QCoreApplication.translate(
                    "M-SET-03", "This file was made by a newer Verdra. Update Verdra to edit it."
                ),
            )
            log.warning("Settings file is version %s; opened read-only.", version)
        else:
            document = migrate.migrate(document, migrate.SETTINGS_STEPS, schema.VERSION)
        decoded = decode(document)
        self.settings, self._unknown = decoded.settings, decoded.unknown
        for problem in decoded.problems:
            log.warning("Setting %s", problem)
        if decoded.problems and not self.read_only:
            self._dirty = True  # Write the corrected values once.
            self.flush()

    def _read_with_fallback(self) -> dict[str, Any] | None:
        try:
            return parse(atomic.read_bytes(self.path))
        except FileNotFoundError:
            return None
        except (OSError, DamagedFileError) as error:
            log.error("Settings file %s couldn't be read: %s", self.path, error)
        backup = atomic.backup_path(self.path)
        try:
            data = atomic.read_bytes(backup)
            document = parse(data)
        except (OSError, DamagedFileError) as error:
            log.error("Settings backup %s couldn't be read either: %s", backup, error)
        else:
            atomic.write_atomic(self.path, data)
            self._notify(
                "M-SET-01",
                QCoreApplication.translate(
                    "M-SET-01",
                    "Your settings file was damaged. Verdra restored the last good copy.",
                ),
            )
            return document
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        moved = atomic.move_aside(self.path, f"broken-{stamp}")
        self._notify(
            "M-SET-02",
            QCoreApplication.translate(
                "M-SET-02",
                "Your settings file couldn't be read, so Verdra started with default settings. "
                "The damaged file was kept as {name}.",
            ).format(name=moved.name),
        )
        return None

    def _notify(self, message_id: str, text: str) -> None:
        self.notices.append(Notice(message_id, text))
        log.warning("%s", text)

    # --- Reading and changing --------------------------------------------------------------

    def value(self, key: str) -> Any:
        """Return the current value of a dotted key."""
        target: Any = self.settings
        for part in key.split("."):
            target = getattr(target, part)
        return target

    def set(self, key: str, value: Any) -> None:
        """Validate and change one setting, notify listeners, and schedule a save.

        Raises:
            ReadOnlyError: The settings came from a newer Verdra.
            msgspec.ValidationError: The value doesn't fit the key's type or range.
            KeyError: The key doesn't exist.
        """
        if self.read_only:
            raise ReadOnlyError(key)
        converted = msgspec.convert(value, schema.field_type(key), strict=True)
        *groups, name = key.split(".")
        target: Any = self.settings
        for group in groups:
            target = getattr(target, group)
        if getattr(target, name) == converted:
            return
        setattr(target, name, converted)
        self._dirty = True
        if not self._timer.isActive():
            self._timer.start()
        self.changed.emit(key, converted)

    def reset_group(self, group: str) -> None:
        """Reset every key of one Settings-screen group to its default."""
        for key, default in schema.defaults().items():
            if key.startswith(group + "."):
                self.set(key, default)

    def flush(self) -> None:
        """Write pending changes now (also called on quit)."""
        self._timer.stop()
        if not self._dirty or self.read_only:
            return
        atomic.write_atomic(self.path, encode(self.settings, self._unknown), keep_backup=True)
        self._dirty = False


class StateStore:
    """Free-form UI state in `state.json`: window geometry, splitters, columns, last screen.

    It is safe to delete; a damaged file is simply replaced.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or terrain.config_dir() / terrain.STATE_FILE
        self._data: dict[str, Any] = {}

    def load(self) -> None:
        """Read state.json, ignoring a missing or damaged file."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError, ValueError:
            data = {}
        self._data = data if isinstance(data, dict) else {}

    def get(self, key: str, default: Any = None) -> Any:
        """Return a stored value, or `default`."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Store a JSON-compatible value (saved by `save`)."""
        self._data[key] = value

    def save(self) -> None:
        """Write state.json atomically."""
        text = json.dumps(self._data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        atomic.write_atomic(self.path, text.encode("utf-8"))
