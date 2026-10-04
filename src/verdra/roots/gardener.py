# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Routing lifecycle and status (Idle, Routing, Degraded, Error); CA in Roblox trust files;
coexistence check.

The CA block in Roblox trust files (spec S-10), and the one routing status (spec S-14,
`RoutingStatusSource`). Each change is recorded in the
ledger before it is made (`ca_roblox_bundle`, plan 9.4) with the file's SHA-256, its original
mode (read-only flag included) and the exact bytes inserted, so removing the block gives back
the file byte for byte. Files are written only through soil/atomic. Which files to change comes
from the confirmed platform facts (plan 16.4), not from here.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import stat
import threading
import time
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol
from urllib.parse import urlsplit

import shiboken6
from cryptography import x509
from PySide6.QtCore import QCoreApplication, QFileSystemWatcher, QObject, QTimer, Signal

from verdra.bark import husk, resin, scar, veil
from verdra.roots import mycelium, rules
from verdra.soil import atomic, terrain

log = logging.getLogger(__name__)


def _newline(data: bytes) -> bytes:
    return b"\r\n" if b"\r\n" in data else b"\n"


def _write_keeping_mode(path: Path, data: bytes, mode: int) -> None:
    """Write `path` atomically, then give it back `mode` (its read-only flag included)."""
    with contextlib.suppress(FileNotFoundError):
        os.chmod(path, mode | stat.S_IWUSR)  # a read-only target can't be replaced on Windows
    try:
        atomic.write_atomic(path, data)
    finally:
        os.chmod(path, mode)


def add_ca(path: Path, certificate: x509.Certificate, ledger: scar.Ledger) -> bool:
    """Add the CA block to a trust file; return False if the file already has exactly it.

    A Verdra block the ledger doesn't know about (an older CA) is removed first, so the file
    never holds two.
    """
    data = atomic.read_bytes(path)
    newline = _newline(data)
    block = resin.trust_block(certificate).replace("\n", newline.decode("ascii")).encode("ascii")
    if data.count(terrain.CA_BEGIN_MARKER.encode("ascii")) == 1 and block in data:
        return False
    data = resin.strip_blocks(data)
    inserted = (newline if data and not data.endswith(b"\n") else b"") + block
    mode = stat.S_IMODE(path.stat().st_mode)
    entry = ledger.begin(
        "ca_roblox_bundle",
        str(path),
        {
            "sha256_before": hashlib.sha256(data).hexdigest(),
            "mode": mode,
            "inserted": inserted.decode("ascii"),
        },
    )
    try:
        _write_keeping_mode(path, data + inserted, mode)
    except OSError as error:
        ledger.mark(entry.id, "failed", error=str(error))
        raise
    ledger.mark(entry.id, "done")
    return True


def remove_ca(entry: scar.Entry, ledger: scar.Ledger) -> None:
    """Undo a `ca_roblox_bundle` entry: take the block out and restore the file's mode.

    Works for entries a crash left `pending`: if the block never reached the file, there is
    nothing to take out.
    """
    path = Path(entry.target)
    if not path.exists():
        ledger.mark(entry.id, "removed")
        return
    data = atomic.read_bytes(path)
    inserted = str(entry.details["inserted"]).encode("ascii")
    restored = data.replace(inserted, b"", 1) if inserted in data else resin.strip_blocks(data)
    mode = int(entry.details["mode"])
    if restored != data:
        _write_keeping_mode(path, restored, mode)
    else:
        os.chmod(path, mode)
    ledger.mark(entry.id, "removed")


def certificate_path() -> Path:
    """Return `trust/ca.crt` in the config folder (plan 9.1)."""
    return terrain.config_dir() / terrain.TRUST_FOLDER / terrain.CA_CERTIFICATE_FILE


def _load(vault: husk.Husk, cert_file: Path) -> resin.Authority | None:
    """Return the stored CA, or None if the certificate or its key is missing or doesn't match."""
    text = vault.load_ca_key()
    if text is None or not cert_file.exists():
        return None
    try:
        certificate = x509.load_pem_x509_certificate(atomic.read_bytes(cert_file))
        key = resin.key_from_secret(text)
    except ValueError:
        return None
    return resin.Authority(certificate, key) if resin.matches(certificate, key) else None


def ensure_ca(
    vault: husk.Husk,
    ledger: scar.Ledger,
    trust_files: Iterable[Path],
    now: datetime,
    cert_file: Path | None = None,
) -> resin.Authority:
    """Return a valid CA, in every trust file; create or rotate it first if needed (S-10).

    Rotation (30 days before expiry) follows the spec's order: a new CA is created, the old
    block is removed from every trust file, the new block is added, and only then is the old
    key replaced in the secret store. No file ever holds two blocks.
    """
    cert_file = cert_file if cert_file is not None else certificate_path()
    files = list(trust_files)
    current = _load(vault, cert_file)
    if current is not None and not resin.needs_rotation(current.certificate, now):
        for path in files:
            add_ca(path, current.certificate, ledger)
        return current
    fresh = resin.create_authority(now)
    for entry in list(ledger.open_entries()):
        if entry.kind == "ca_roblox_bundle":
            remove_ca(entry, ledger)
    for path in files:
        add_ca(path, fresh.certificate, ledger)
    vault.save_ca_key(resin.key_to_secret(fresh.key))
    atomic.write_atomic(cert_file, resin.certificate_pem(fresh.certificate))
    return fresh


class VersionWatch(QObject):
    """Watches the Roblox install folders and adds the CA to each new version (S-10, test 3).

    A new version folder appears before the installer has written its files, so a new folder
    is checked every second until each of its trust files has the block, for at most
    `PATIENCE_SECONDS`. Each version updated writes M-CA-02 to Activity.
    """

    #: How long a new version folder is checked for its trust files.
    PATIENCE_SECONDS = 120.0

    updated = Signal(str)

    def __init__(
        self,
        install_folders: Iterable[Path],
        trust_files_in: Callable[[Path], Iterable[Path]],
        certificate: x509.Certificate,
        ledger: scar.Ledger,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.trust_files_in = trust_files_in
        self.certificate = certificate
        self.ledger = ledger
        self.folders = [path for path in install_folders if path.is_dir()]
        self.known = {child for folder in self.folders for child in _subfolders(folder)}
        self.pending: dict[Path, float] = {}
        self.watcher = QFileSystemWatcher([str(folder) for folder in self.folders], self)
        self.watcher.directoryChanged.connect(self._changed)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._check_pending)

    def _changed(self, _folder: str) -> None:
        now = time.monotonic()
        for folder in self.folders:
            for child in _subfolders(folder):
                if child not in self.known:
                    self.known.add(child)
                    self.pending[child] = now
        self._check_pending()

    def _check_pending(self) -> None:
        now = time.monotonic()
        for version, since in list(self.pending.items()):
            files = [path for path in self.trust_files_in(version) if path.is_file()]
            if files and all(self._add(path) for path in files):
                del self.pending[version]
                log.info(
                    "%s",
                    QCoreApplication.translate(
                        "M-CA-02",
                        "Roblox updated. Verdra added its certificate to the new version.",
                    ),
                )
                self.updated.emit(str(version))
            elif now - since > self.PATIENCE_SECONDS:
                del self.pending[version]
        if self.pending and not self.timer.isActive():
            self.timer.start()
        elif not self.pending:
            self.timer.stop()

    def _add(self, path: Path) -> bool:
        try:
            add_ca(path, self.certificate, self.ledger)
        except OSError:
            return False  # the installer may still be writing it; tried again next second
        return True


def _subfolders(folder: Path) -> set[Path]:
    try:
        return {child for child in folder.iterdir() if child.is_dir()}
    except OSError:
        return set()


# --- Routing status (spec S-14) ------------------------------------------------------------------


class State(StrEnum):
    """The routing state everything that shows status renders (plan 7.1, 4.6, 7.10)."""

    IDLE = "idle"
    ROUTING = "routing"
    DEGRADED = "degraded"
    ERROR = "error"

    def label(self) -> str:
        """Return the state's word in the interface language."""
        return {
            State.IDLE: QCoreApplication.translate("Status", "Idle"),
            State.ROUTING: QCoreApplication.translate("Status", "Routing"),
            State.DEGRADED: QCoreApplication.translate("Status", "Degraded"),
            State.ERROR: QCoreApplication.translate("Status", "Error"),
        }[self]


class Trigger(StrEnum):
    """Why routing isn't simply Routing or Idle (spec S-14 table)."""

    #: Degraded (a): a launched Roblox sent nothing through Verdra within the launch window.
    NOT_ROUTED = "not_routed"
    #: Degraded (b): an upstream certificate couldn't be verified (S-11).
    UPSTREAM_CERTIFICATE = "upstream_certificate"
    #: Degraded (c): an installed Roblox version lacks the CA block (S-10).
    CA_MISSING = "ca_missing"
    #: Error: the proxy couldn't start (M-PROXY-01).
    PROXY_FAILED = "proxy_failed"
    #: Error: another routing tool was detected (S-15, M-COEX-01).
    OTHER_TOOL = "other_tool"
    #: Error: the keeper is unavailable (Hosts-file mode, M6).
    KEEPER = "keeper"


ERROR_TRIGGERS: Final = frozenset({Trigger.PROXY_FAILED, Trigger.OTHER_TOOL, Trigger.KEEPER})
#: Degraded (a): how long after a launch Roblox traffic must arrive.
LAUNCH_WINDOW_SECONDS: Final = 20.0
#: Degraded (b) clears after this long without another certificate failure.
CERTIFICATE_WINDOW_SECONDS: Final = 120.0


@dataclass(frozen=True, slots=True)
class RoutingStatus:
    """One published status: the state, the reason shown, and the other active reasons."""

    state: State
    trigger: Trigger | None = None
    reason: str = ""
    #: The other active triggers' reasons, most recent first (the popover lists them).
    others: tuple[str, ...] = ()


class Cancel(Protocol):
    def __call__(self) -> None: ...


#: Runs `callback` once after `seconds`; returns a function that cancels it.
Schedule = Callable[[float, Callable[[], None]], Cancel]


def qt_schedule(parent: QObject) -> Schedule:
    """Return a `Schedule` backed by single-shot Qt timers owned by `parent`."""

    def schedule(seconds: float, callback: Callable[[], None]) -> Cancel:
        timer = QTimer(parent)
        timer.setSingleShot(True)
        timer.timeout.connect(callback)
        timer.timeout.connect(timer.deleteLater)
        timer.start(round(seconds * 1000))

        def cancel() -> None:
            if shiboken6.isValid(timer):
                timer.stop()
                timer.deleteLater()

        return cancel

    return schedule


class RoutingStatusSource(QObject):
    """The one routing status (spec S-14): events in, one published value out.

    Callers report events (routing started or stopped, Roblox traffic seen, a launch, a
    certificate failure, a missing or repaired CA block, an error and its end); `changed` is
    emitted once per change of the published value, and each change of state is written to
    Activity once. Error beats Degraded, Degraded beats Routing; among triggers of one kind the
    most recent is shown. The only timers are the launch window and the certificate window.

    Signals:
        changed(RoutingStatus): The published status changed.
    """

    changed = Signal(object)

    def __init__(self, schedule: Schedule | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._schedule = schedule if schedule is not None else qt_schedule(self)
        self._running = False
        #: Active triggers and their reasons, in the order they were raised.
        self._active: dict[Trigger, str] = {}
        self._launch: Cancel | None = None
        self._certificate: Cancel | None = None
        self.current = RoutingStatus(State.IDLE)

    # Events --------------------------------------------------------------------------------

    def started(self) -> None:
        """The proxy is listening: Routing, unless something else holds."""
        self._running = True
        self._clear(Trigger.PROXY_FAILED, Trigger.UPSTREAM_CERTIFICATE, publish=False)
        self._publish()

    def stopped(self) -> None:
        """Routing is off (paused from the tray, or stopped)."""
        self._running = False
        self._cancel_launch()
        self._cancel_certificate()
        self._clear(Trigger.NOT_ROUTED, Trigger.UPSTREAM_CERTIFICATE, publish=False)
        self._publish()

    def launched(self) -> None:
        """Roblox was launched through Verdra: its traffic must arrive within the window."""
        self._cancel_launch()
        self._launch = self._schedule(LAUNCH_WINDOW_SECONDS, self._launch_window_over)

    def traffic_seen(self) -> None:
        """A Roblox connection reached Verdra: Degraded (a) clears."""
        self._cancel_launch()
        self._clear(Trigger.NOT_ROUTED)

    def certificate_failed(self, reason: str) -> None:
        """An upstream certificate couldn't be verified: Degraded (b) for two minutes."""
        self._cancel_certificate()
        self._certificate = self._schedule(
            CERTIFICATE_WINDOW_SECONDS, lambda: self._clear(Trigger.UPSTREAM_CERTIFICATE)
        )
        self._raise(Trigger.UPSTREAM_CERTIFICATE, reason)

    def ca_missing(self, reason: str) -> None:
        """An installed Roblox version lacks the CA block: Degraded (c)."""
        self._raise(Trigger.CA_MISSING, reason)

    def ca_repaired(self) -> None:
        """The CA block is back in every trust file."""
        self._clear(Trigger.CA_MISSING)

    def error(self, trigger: Trigger, reason: str) -> None:
        """Routing can't work (`trigger` is one of `ERROR_TRIGGERS`)."""
        if trigger not in ERROR_TRIGGERS:
            msg = f"{trigger} is not an error trigger"
            raise ValueError(msg)
        self._raise(trigger, reason)

    def error_cleared(self, trigger: Trigger) -> None:
        """The cause of an error is gone."""
        self._clear(trigger)

    # Internals -----------------------------------------------------------------------------

    def _launch_window_over(self) -> None:
        self._launch = None
        if self._running:
            self._raise(
                Trigger.NOT_ROUTED,
                QCoreApplication.translate(
                    "M-STATUS-01", "Roblox isn't routed through Verdra yet. Restart it from here."
                ),
            )

    def _cancel_launch(self) -> None:
        if self._launch is not None:
            self._launch()
            self._launch = None

    def _cancel_certificate(self) -> None:
        if self._certificate is not None:
            self._certificate()
            self._certificate = None

    def _raise(self, trigger: Trigger, reason: str) -> None:
        self._active.pop(trigger, None)  # most recent last
        self._active[trigger] = reason
        self._publish()

    def _clear(self, *triggers: Trigger, publish: bool = True) -> None:
        for trigger in triggers:
            self._active.pop(trigger, None)
        if publish:
            self._publish()

    def _compute(self) -> RoutingStatus:
        recent = list(reversed(self._active.items()))
        errors = [(t, r) for t, r in recent if t in ERROR_TRIGGERS]
        degraded = [(t, r) for t, r in recent if t not in ERROR_TRIGGERS]
        if errors:
            (trigger, reason), rest = errors[0], errors[1:] + degraded
            return RoutingStatus(State.ERROR, trigger, reason, tuple(r for _, r in rest))
        if not self._running:
            return RoutingStatus(State.IDLE)
        if degraded:
            (trigger, reason), rest = degraded[0], degraded[1:]
            return RoutingStatus(State.DEGRADED, trigger, reason, tuple(r for _, r in rest))
        return RoutingStatus(State.ROUTING)

    def _publish(self) -> None:
        status = self._compute()
        if status == self.current:
            return
        old, self.current = self.current, status
        if status.state is not old.state:
            _log_change(old, status)
        self.changed.emit(status)


def _log_change(old: RoutingStatus, new: RoutingStatus) -> None:
    """Write one Activity line for a change of state (S-14 "Logging", rule 2)."""
    level = {State.DEGRADED: logging.WARNING, State.ERROR: logging.ERROR}.get(
        new.state, logging.INFO
    )
    if new.reason:
        line = QCoreApplication.translate(
            "M-STATUS-07", "Routing status changed from {old} to {new}: {reason}"
        ).format(old=old.state.label(), new=new.state.label(), reason=new.reason)
    else:
        line = QCoreApplication.translate(
            "M-STATUS-06", "Routing status changed from {old} to {new}."
        ).format(old=old.state.label(), new=new.state.label())
    log.log(level, "%s", line)


# --- Routing lifecycle (plan 8.3, 10.1) --------------------------------------------------------


class Router(QObject):
    """Runs the proxy (roots/mycelium) on its own thread and asyncio loop (plan 8.3).

    `start` waits until the proxy listens and reports it to the routing status; each CONNECT the
    proxy sees reaches the status on the Qt thread as Roblox traffic (S-14 Degraded (a)). If no
    port can be used, the status shows Error with M-PROXY-01 and `start` raises.

    Signals:
        connected(str): The proxy saw a CONNECT to this host (on the Qt thread).
        certificate_failed(str): A server's certificate for this host couldn't be verified;
            the status turns Degraded (b) on the Qt thread (S-11 test 3, plan 12.2).
    """

    connected = Signal(str)
    certificate_failed = Signal(str)

    #: How long `start` and `stop` wait for the proxy's thread.
    WAIT_SECONDS = 10.0

    def __init__(self, status: RoutingStatusSource, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.status = status
        self.port: int | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._proxy: mycelium.Mycelium | None = None
        # A bound method of this object, which lives on the Qt thread: the signal, emitted on
        # the proxy's thread, is queued to it.
        self.connected.connect(self._traffic)
        self.certificate_failed.connect(self._certificate)

    @property
    def running(self) -> bool:
        """Whether the proxy is listening."""
        return self.port is not None

    def report_certificate_failure(self, host: str, reason: str) -> None:  # noqa: ARG002
        """Report a failed upstream verification; safe to call on the proxy's thread.

        The reason is technical and already in the debug log; the status shows M-PROXY-02.
        """
        self.certificate_failed.emit(host)

    def _certificate(self, host: str) -> None:
        self.status.certificate_failed(
            QCoreApplication.translate(
                "M-PROXY-02",
                "A Roblox server's certificate couldn't be verified ({host}). That request was "
                "blocked.",
            ).format(host=host)
        )

    def start(
        self,
        port: int,
        connect: mycelium.Connector,
        interceptor: mycelium.Interceptor | None = None,
    ) -> int:
        """Start the proxy and return the port it listens on (routing.proxy_port or another).

        Raises:
            mycelium.ProxyStartError: no loopback port could be used (M-PROXY-01).
        """
        if self.port is not None:
            return self.port
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, name="verdra-proxy", daemon=True)
        thread.start()
        proxy = mycelium.Mycelium(
            port,
            connect,
            interceptor=interceptor,
            on_connect=lambda host, _port: self.connected.emit(host),
        )
        try:
            self.port = asyncio.run_coroutine_threadsafe(proxy.start(), loop).result(
                self.WAIT_SECONDS
            )
        except mycelium.ProxyStartError as error:
            _end_loop(loop, thread)
            self.status.error(
                Trigger.PROXY_FAILED,
                QCoreApplication.translate(
                    "M-PROXY-01",
                    "Verdra couldn't start routing: port {port} is in use and no other port "
                    "was free.",
                ).format(port=error.port),
            )
            raise
        self._loop, self._thread, self._proxy = loop, thread, proxy
        self.status.error_cleared(Trigger.PROXY_FAILED)
        self.status.started()
        return self.port

    def stop(self) -> None:
        """Stop the proxy and its thread; routing is Idle afterwards."""
        loop, thread, proxy = self._loop, self._thread, self._proxy
        self._loop = self._thread = self._proxy = None
        self.port = None
        if loop is not None and thread is not None and proxy is not None:
            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(proxy.stop(), loop).result(self.WAIT_SECONDS)
            _end_loop(loop, thread)
        self.status.stopped()

    def _traffic(self, _host: str) -> None:
        self.status.traffic_seen()


def _end_loop(loop: asyncio.AbstractEventLoop, thread: threading.Thread) -> None:
    loop.call_soon_threadsafe(loop.stop)
    thread.join(Router.WAIT_SECONDS)
    if not thread.is_alive():
        loop.close()


# --- Coexistence check (spec S-15, per-app mode) ------------------------------------------------


@dataclass(frozen=True, slots=True)
class Coexistence:
    """What the coexistence check found: signs of another routing tool, and what it couldn't see."""

    #: One Activity line per sign (S-15 rule 4).
    signs: tuple[str, ...] = ()
    #: Why parts of the check couldn't be done (S-15 test 6); those parts aren't signs.
    incomplete: tuple[str, ...] = ()

    @property
    def clear(self) -> bool:
        """Whether routing may start."""
        return not self.signs


def points_at_verdra(value: str, ports: Collection[int]) -> bool:
    """Return whether a proxy variable's value is Verdra's own listener (any of `ports`)."""
    parts = urlsplit(value if "://" in value else f"http://{value}")
    try:
        port = parts.port
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return host in {terrain.PROXY_HOST, "localhost", "::1"} and port in ports


def shown_proxy(value: str) -> str:
    """Return a proxy value for Activity: its address only, never a user name or password."""
    parts = urlsplit(value if "://" in value else f"http://{value}")
    try:
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        port = ""
    host = parts.hostname or ""
    if not host:
        return veil.redact_text(value)
    return f"{parts.scheme}://{host}{port}"


def hosts_signs(text: str) -> list[tuple[int, str]]:
    """Return (line number, host) for each 10.2 host the hosts file maps without Verdra's marker.

    Comment lines, lines for other hosts and lines carrying `# verdra:route` are not signs; any
    address counts, not only loopback (S-15 test 3).
    """
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if terrain.HOSTS_MARKER in line:
            continue
        fields = line.split("#", 1)[0].split()
        found.extend((number, host) for host in fields[1:] if rules.is_roblox_host(host))
    return found


def check_coexistence(
    running: Iterable[RunningClientView] | None,
    own_ports: Collection[int],
    hosts_text: str | None,
    *,
    unreadable: str = "",
) -> Coexistence:
    """Look for signs of another routing tool before per-app routing starts (spec S-15).

    `running` is this user's running Roblox clients (None when they can't be listed on this
    system, with the reason in `unreadable`); `hosts_text` is the hosts file (None if it
    couldn't be read). Nothing is changed anywhere: this only reads (S-15 rule 1).
    """
    signs: list[str] = []
    incomplete: list[str] = []
    if running is None:
        incomplete.append(unreadable)
    for client in running or ():
        if client.proxies is None:
            incomplete.append(f"{client.name} ({client.pid}): {client.error}")
            continue
        for value in dict.fromkeys(client.proxies.values()):
            if value and not points_at_verdra(value, own_ports):
                signs.append(
                    QCoreApplication.translate(
                        "M-COEX-02",
                        "Another routing tool: {name} (process {pid}) uses the proxy {proxy}.",
                    ).format(name=client.name, pid=client.pid, proxy=shown_proxy(value))
                )
    if hosts_text is None:
        incomplete.append("hosts")
    else:
        signs.extend(
            QCoreApplication.translate(
                "M-COEX-03", "Another routing tool: line {line} of the hosts file maps {host}."
            ).format(line=line, host=host)
            for line, host in hosts_signs(hosts_text)
        )
    return Coexistence(tuple(signs), tuple(incomplete))


class RunningClientView(Protocol):
    """A running Roblox client as soil reports it (soil/humus.RunningClient)."""

    @property
    def pid(self) -> int: ...
    @property
    def name(self) -> str: ...
    @property
    def proxies(self) -> dict[str, str] | None: ...
    @property
    def error(self) -> str: ...
