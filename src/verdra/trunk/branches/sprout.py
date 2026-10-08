# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Launching Roblox: environment, link handling, Apply now restart, multi-instance.

Spec S-12. This part:

- **Choosing the client.** The platform finds the installed clients (soil, from the facts in
  docs/platforms/). The first one whose facts are all confirmed is used. A client that still
  needs an unconfirmed fact is refused with a plain message instead of a guess (plan 16.4):
  a Roblox installed for all users, whose trust files need administrator rights (M-LAUNCH-05).
  No client at all is M-LAUNCH-01.
- **The certificate.** Verdra's CA goes into the trust file of every Player version folder of
  that client (S-10, `roots/gardener.ensure_ca`), each change a `ca_roblox_bundle` ledger entry
  that keeps the file's mode, read-only flag included. Studio's folders are never in the list.
- **Launching.** The client starts with the proxy variables; the PID is kept so that only what
  Verdra started is ever closed (rule 4).
- **Links.** With `routing.handle_roblox_links` on, Verdra's command becomes the `roblox-player:`
  handler; the previous handler is stored in a `uri_handler` ledger entry first (rule 2) and
  put back exactly when handling is turned off or on Reset everything.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import psutil
from PySide6.QtCore import QCoreApplication, QLocale, QObject, Signal

from verdra.bark import husk, resin, scar
from verdra.roots import gardener, hyphae, mycelium, rules, taproot
from verdra.roots.symbionts.grafter import Grafter
from verdra.soil import atomic, humus, terrain
from verdra.trunk import tendrils

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Refused:
    """Why Verdra won't route or launch Roblox here, as the sentence the user sees."""

    message_id: str
    text: str


def no_roblox() -> Refused:
    """M-LAUNCH-01."""
    return Refused(
        "M-LAUNCH-01",
        QCoreApplication.translate(
            "M-LAUNCH-01",
            "Roblox isn't installed, or Verdra couldn't find it. Install Roblox, then try again.",
        ),
    )


def unconfirmed(fact: str) -> Refused:
    """The plain message for a client that needs an unconfirmed platform fact.

    Raises:
        KeyError: no message names this fact yet (a test checks every fact soil can report).
    """
    messages: dict[str, Callable[[], Refused]] = {
        "W-02": lambda: Refused(
            "M-LAUNCH-05",
            QCoreApplication.translate(
                "M-LAUNCH-05",
                "Verdra can't route a Roblox installed for all users: that needs administrator "
                "rights, which routing per app never uses. Install Roblox for your account "
                "only, then try again. Nothing was changed.",
            ),
        ),
    }
    return messages[fact]()


def choose(clients: list[humus.RobloxClient] | humus.Unsupported) -> humus.RobloxClient | Refused:
    """Return the client to route and launch, or why there is none (S-12 discovery)."""
    if isinstance(clients, humus.Unsupported) or not clients:
        return no_roblox()
    for client in clients:
        if not client.unconfirmed:
            return client
    return unconfirmed(clients[0].unconfirmed[0])


def add_certificate(
    client: humus.RobloxClient, vault: husk.Husk, ledger: scar.Ledger, now: datetime
) -> resin.Authority:
    """Put Verdra's CA into every trust file of the client's Player folders (S-10)."""
    if client.unconfirmed:
        msg = f"{client.executable} needs unconfirmed facts {client.unconfirmed}"
        raise ValueError(msg)
    return gardener.ensure_ca(vault, ledger, client.trust_files, now)


# --- Links (S-12 "Links from the browser") -------------------------------------------------------


class LinkHandlingUnavailableError(RuntimeError):
    """This system's `roblox-player:` handler can't be taken over (yet)."""


def _handler(platform: humus.Platform) -> humus.LinkHandler:
    handler = platform.link_handler()
    if isinstance(handler, humus.Unsupported):
        raise LinkHandlingUnavailableError(handler.reason)
    return handler


def _open_handler_entries(ledger: scar.Ledger) -> list[scar.Entry]:
    return [entry for entry in ledger.open_entries() if entry.kind == "uri_handler"]


def set_link_handling(
    on: bool,  # noqa: FBT001 - mirrors the setting
    ledger: scar.Ledger,
    platform: humus.Platform | None = None,
    command: Sequence[str] | None = None,
) -> None:
    """Make Verdra the `roblox-player:` handler, or put the previous one back (S-12).

    Turning it on records the previous handler in a `uri_handler` entry before the change
    (rule 2). If Roblox's updater has taken the handler back since, that entry is closed (the
    handler is Roblox's again) and a new one is recorded. Turning it off restores every open
    entry, newest first.

    Raises:
        LinkHandlingUnavailableError: the system's handler can't be taken over yet.
        OSError: the handler couldn't be changed; the entry is marked failed.
    """
    platform = platform or humus.current()
    command = list(command or humus.verdra_command())
    handler = _handler(platform)
    entries = _open_handler_entries(ledger)
    if not on:
        for entry in entries:
            restore_handler(entry, ledger, platform)
        return
    if entries and handler.registered(command):
        return
    for entry in entries:
        ledger.mark(entry.id, "removed", reclaimed_by_roblox=True)
    entry = ledger.begin("uri_handler", terrain.URL_SCHEME, {"snapshot": handler.snapshot()})
    try:
        handler.register(command)
    except OSError as error:
        ledger.mark(entry.id, "failed", error=str(error))
        raise
    ledger.mark(entry.id, "done")


def restore_handler(
    entry: scar.Entry, ledger: scar.Ledger, platform: humus.Platform | None = None
) -> None:
    """Undo a `uri_handler` entry: put the recorded handler back exactly (S-12, S-16)."""
    _handler(platform or humus.current()).restore(dict(entry.details["snapshot"]))
    ledger.mark(entry.id, "removed")


# --- Roblox's download cache (S-24 step 5) --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RunningRoblox:
    """This user's running Roblox Players and Studios, for Apply now (S-24 rule 4)."""

    players: frozenset[int]
    studio: bool


class RobloxRunningError(RuntimeError):
    """A Roblox Player or Studio is running, so the cache stays where it is."""

    def __init__(self, processes: humus.RobloxProcesses) -> None:
        super().__init__("Roblox is running")
        self.processes = processes


class CacheKeptError(RuntimeError):
    """Roblox made new cache files since the move, so the backup stays where it is."""


@dataclass(frozen=True, slots=True)
class CacheMove:
    """What Apply now moved aside: the names, and the folder they went to."""

    names: tuple[str, ...]
    backup: Path


def cache_backup_root() -> Path:
    """Return the folder that holds the moved caches, one subfolder per move."""
    return terrain.config_dir() / terrain.ROBLOX_CACHE_BACKUP_FOLDER


def move_cache(
    platform: humus.Platform, ledger: scar.Ledger, now: datetime, root: Path | None = None
) -> CacheMove | None:
    """Move Roblox's download cache into a new backup folder (S-24 step 5); None if none.

    Only the names soil records as cache (W-06), only while no Roblox Player or Studio of this
    user runs, and never deleting anything: each file or folder is renamed into the backup, so
    after a crash every one is either still in place or in the backup, and the ledger entry,
    written first, lets Reset everything put back what moved. If a move fails, what already
    moved is put back at once.

    Raises:
        RobloxRunningError: a Player or Studio is running; nothing was moved.
        OSError: a file couldn't be moved; everything is back in place.
    """
    files = platform.roblox_cache_files()
    if isinstance(files, humus.Unsupported) or not files:
        return None
    running = platform.roblox_processes()
    if isinstance(running, humus.Unsupported):
        return None
    if running.any:
        raise RobloxRunningError(running)
    base = root or cache_backup_root()
    backup = base / now.strftime("%Y-%m-%d %H.%M.%S")
    suffix = 1
    while backup.exists():
        suffix += 1
        backup = base / f"{now.strftime('%Y-%m-%d %H.%M.%S')} ({suffix})"
    items = [{"name": path.name, "path": str(path)} for path in files]
    entry = ledger.begin(
        "roblox_cache_moved", str(files[0].parent), {"backup": str(backup), "items": items}
    )
    backup.mkdir(parents=True)
    moved: list[Path] = []
    try:
        for path in files:
            shutil.move(path, backup / path.name)
            moved.append(path)
    except OSError:
        for path in reversed(moved):
            shutil.move(backup / path.name, path)
        _remove_if_empty(backup)
        ledger.mark(entry.id, "removed")
        raise
    ledger.mark(entry.id, "done")
    return CacheMove(tuple(path.name for path in files), backup)


def restore_cache(entry: scar.Entry, ledger: scar.Ledger) -> None:
    """Undo a `roblox_cache_moved` entry: put the moved cache back (S-16).

    Everything goes back, or nothing: if Roblox made any of the same files since, the backup
    stays where it is (a database and its write-ahead files only belong together).

    Raises:
        CacheKeptError: Roblox made new cache files since; the backup is kept, its folder named.
    """
    backup = Path(entry.details["backup"])
    items = [(backup / item["name"], Path(item["path"])) for item in entry.details["items"]]
    waiting = [(saved, original) for saved, original in items if saved.exists()]
    if any(original.exists() for _saved, original in waiting):
        raise CacheKeptError(
            QCoreApplication.translate(
                "M-CACHE-05",
                "Roblox has made new saved assets since, so Verdra kept the old ones in "
                "{folder}. You can delete that folder.",
            ).format(folder=backup)
        )
    for saved, original in reversed(waiting):
        shutil.move(saved, original)
    _remove_if_empty(backup)
    ledger.mark(entry.id, "removed")


def prune_backups(ledger: scar.Ledger, keep: Path | None, root: Path | None = None) -> list[Path]:
    """Forget every cache backup but `keep` (all of them when None); return the folders to delete.

    Write-ahead (S-16): each backup's ledger entry is marked removed first, so Reset everything
    never tries to put back a backup that is being deleted. A backup whose entry isn't done (a
    move a crash interrupted, or one that failed) is kept: Reset everything still needs it.
    Folders no open entry names (left by a crash while deleting) are deleted too. Nothing is
    deleted here: `delete_folders` does that, on a worker.
    """
    base = root or cache_backup_root()
    keep_name = keep.name if keep is not None else None
    needed: set[str] = set()
    for entry in ledger.open_entries():
        if entry.kind != "roblox_cache_moved":
            continue
        folder = Path(entry.details["backup"])
        if folder.parent != base:
            continue
        if entry.state != "done" or folder.name == keep_name:
            needed.add(folder.name)
            continue
        ledger.mark(entry.id, "removed", deleted=True)
    if not base.is_dir():
        return []
    return sorted(
        folder
        for folder in base.iterdir()
        if folder.is_dir() and folder.name not in needed and folder.name != keep_name
    )


def delete_folders(folders: list[Path]) -> int:
    """Delete the given backup folders and return how many bytes that freed.

    Raises:
        OSError: a folder couldn't be deleted completely (what remains goes next time).
    """
    freed = 0
    for folder in folders:
        size = folder_size(folder)
        shutil.rmtree(folder)
        freed += size
    return freed


def folder_size(folder: Path) -> int:
    """Return the total size of the files in `folder`, 0 if it's gone."""
    total = 0
    for current, _folders, files in os.walk(folder):
        for name in files:
            with contextlib.suppress(OSError):
                total += (Path(current) / name).stat().st_size
    return total


def backups_size(root: Path | None = None) -> int:
    """Return how much space the cache backups use."""
    return folder_size(root or cache_backup_root())


def cache_moved_text(moved: CacheMove) -> str:
    """M-CACHE-01: what Apply now moved and where."""
    return QCoreApplication.translate(
        "M-CACHE-01",
        "Moved Roblox's saved assets ({names}) to {folder}. Reset everything puts them back.",
    ).format(names=", ".join(moved.names), folder=moved.backup)


def capture_text(ids: tuple[int, ...]) -> str:
    """M-DIAG-03: a format capture is on (source runs only, roots/litmus)."""
    return QCoreApplication.translate(
        "M-DIAG-03",
        "Format capture is on for {ids}. Their replacements are off while it runs, and what "
        "Roblox's CDN sends for them is written to {folder}. Restart Verdra without "
        "--format-capture to turn it off.",
    ).format(ids=", ".join(str(i) for i in ids), folder=terrain.diagnostics_dir())


def control_text(original: int, donor: int) -> str:
    """M-DIAG-08: the control experiment is on (source runs only, roots/litmus)."""
    return QCoreApplication.translate(
        "M-DIAG-08",
        "Control experiment is on: when Roblox downloads asset {original}, it gets asset "
        "{donor}'s real bytes from the CDN, and replacements of {original} are off. Restart "
        "Verdra without --control-swap to turn it off.",
    ).format(original=original, donor=donor)


def other_player_text() -> str:
    """M-LAUNCH-08: a Player Verdra didn't start is running (banner and routing status)."""
    return QCoreApplication.translate(
        "M-LAUNCH-08",
        "Roblox is already running without Verdra. Close it completely, then click Apply now.",
    )


def _remove_if_empty(folder: Path) -> None:
    with contextlib.suppress(OSError):
        folder.rmdir()
    with contextlib.suppress(OSError):
        folder.parent.rmdir()


# --- Launching ------------------------------------------------------------------------------------


@dataclass
class Launches:
    """The Roblox processes Verdra started, so only those are ever closed (S-12 rule 4).

    With `record`, the list is also kept in that file, so a Verdra started again still knows the
    Players an earlier run started (a Player keeps using Verdra's proxy port after Verdra
    restarts). Each entry is a process ID with its creation time: a reused ID never matches.
    Only normal process information is used (psutil); nothing is read from inside a process.
    """

    platform: humus.Platform = field(default_factory=humus.current)
    environment: Callable[[], Mapping[str, str]] = lambda: dict(os.environ)
    spawn: humus.Spawn | None = None
    #: PID → the process's creation time, so a reused PID is never mistaken for Roblox.
    started: dict[int, float] = field(default_factory=dict)
    #: Where the list is kept between runs of Verdra (None: in memory only).
    record: Path | None = None

    def __post_init__(self) -> None:
        if self.record is None:
            return
        try:
            data = json.loads(atomic.read_bytes(self.record))
        except OSError, ValueError:
            return
        if isinstance(data, dict):
            for pid, created in data.items():
                with contextlib.suppress(TypeError, ValueError):
                    if float(created) > 0:  # a time that couldn't be read never matches later
                        self.started[int(pid)] = float(created)
        self.running()

    def launch(self, client: humus.RobloxClient, link: str | None, proxy_port: int) -> int:
        """Start `client` with the proxy variables and `link` (unchanged); return its PID."""
        options = {} if self.spawn is None else {"spawn": self.spawn}
        pid = self.platform.launch_roblox(client, link, proxy_port, self.environment(), **options)
        self.adopt(pid)
        return pid

    def adopt(self, pid: int) -> None:
        """Count `pid` as a Player Verdra started (one it launched, or one using its proxy)."""
        try:
            self.started[pid] = psutil.Process(pid).create_time()
        except psutil.Error:
            self.started[pid] = 0.0
        self._save()

    def running(self) -> list[psutil.Process]:
        """Return the processes Verdra started that are still running."""
        alive: list[psutil.Process] = []
        before = len(self.started)
        for pid, created in list(self.started.items()):
            try:
                process = psutil.Process(pid)
                if process.is_running() and (not created or process.create_time() == created):
                    alive.append(process)
                    continue
            except psutil.Error:
                pass
            del self.started[pid]
        if len(self.started) != before:
            self._save()
        return alive

    def _save(self) -> None:
        if self.record is None:
            return
        kept = {str(pid): created for pid, created in self.started.items() if created > 0}
        try:
            atomic.write_atomic(self.record, json.dumps(kept).encode("utf-8"))
        except OSError as error:
            log.debug("The list of Players Verdra started wasn't saved: %s", error)

    def close_all(self, timeout: float = 5.0) -> None:
        """Close the processes Verdra started (S-12 "Closing on quit"), never any other."""
        processes = self.running()
        for process in processes:
            try:
                process.terminate()
            except psutil.Error:
                continue
        _gone, left = psutil.wait_procs(processes, timeout=timeout)
        for process in left:
            try:
                process.kill()
            except psutil.Error:
                continue
        self.started.clear()
        self._save()


# --- Routing and launching together ---------------------------------------------------------------


class Settings(Protocol):
    """What `Sprout` reads from the settings store (trunk/almanac)."""

    def value(self, key: str) -> Any:
        """Return a setting's value."""
        ...


class Sprout(QObject):
    """Starts routing and launches Roblox through it (S-12; the order of plan 10.1).

    Starting routing: choose the client (a refusal is reported, nothing changes), put Verdra's
    CA into its Player folders, start the proxy on its own thread, take over `roblox-player:`
    links if `routing.handle_roblox_links` is on, and watch for new Roblox versions. Launching
    starts routing first if needed, then the client with the proxy variables, and opens the
    launch window of the routing status (S-14).

    With `diagnose`, the proxy intercepts the 10.2 hosts read-only and logs their TLS details
    (roots/litmus, source runs only, decision record 0015); otherwise every connection is a
    blind tunnel, as no feature intercepts anything yet.

    Before routing starts and before each launch, the coexistence check of S-15 runs as a
    background job (`pool`; inline without one): if another routing tool shows, routing doesn't
    start, the status is Error and `other_tool` carries M-COEX-01.

    Signals:
        refused(str): Why routing or a launch didn't happen, as the sentence to show.
        other_tool(str): Another routing tool was found (M-COEX-01); `retry` tries again.
        backups_changed(): Cache backups were deleted, or deleting them failed.
        others_changed(bool): Whether a Player Verdra didn't start is running changed (M-LAUNCH-08).
        held_back(str): A launch wasn't started because such a Player runs; the link (or "")
            waits for the user's choice (`launch(link, despite_others=True)` or `close_others`).
        handed_off(str): A Player Verdra started closed at once and the other Player runs: the
            join most likely went there (M-LAUNCH-14).
    """

    refused = Signal(str)
    other_tool = Signal(str)
    backups_changed = Signal()
    others_changed = Signal(bool)
    held_back = Signal(str)
    handed_off = Signal(str)

    #: How often Verdra looks again while a Player it didn't start runs, until it closes.
    OTHERS_WATCH_SECONDS = 3.0
    #: How long after a launch Verdra checks whether the Player it started is still running.
    HANDOFF_SECONDS = 10.0

    def __init__(
        self,
        settings: Settings,
        status: gardener.RoutingStatusSource,
        *,
        platform: humus.Platform | None = None,
        ledger: Callable[[], scar.Ledger] = scar.Ledger,
        vault: Callable[[], husk.Husk] = husk.Husk,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        launches: Launches | None = None,
        connect: mycelium.Connector | None = None,
        pool: tendrils.Tendrils | None = None,
        diagnose: bool = False,
        capture: tuple[int, ...] = (),
        save_bodies: bool = False,
        control: tuple[int, int] | None = None,
        snapshots: rules.SnapshotHolder | None = None,
        schedule: gardener.Schedule | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._schedule = schedule if schedule is not None else gardener.qt_schedule(self)
        #: Players this user runs that Verdra didn't start (M-LAUNCH-08), as last seen.
        self.others: frozenset[int] = frozenset()
        self._watch: gardener.Cancel | None = None
        self._handoff: gardener.Cancel | None = None
        #: Players already looked at that aren't Verdra's (no Verdra proxy, or unreadable),
        #: so the watch every few seconds doesn't read every process again.
        self._not_ours: set[int] = set()
        #: The replacements the proxy applies (S-21), published by trunk/branches/grafts.
        self.snapshots = snapshots or rules.SnapshotHolder()
        self.settings = settings
        self.status = status
        self.platform = platform or humus.current()
        self.ledger = ledger
        self.vault = vault
        self.clock = clock
        self.launches = launches or Launches(platform=self.platform)
        self.connector = connect or self._open_tunnel
        self.diagnose = diagnose
        #: A format capture (roots/litmus, source runs only): these assets' downloads are
        #: reported and their replacements are left alone.
        self.capture = capture
        self.save_bodies = save_bodies
        #: The control experiment (roots/litmus, source runs only): (original, donor).
        self.control = control
        self.router = gardener.Router(status, self)
        self.pool = pool
        self.client: humus.RobloxClient | None = None
        self.watch: gardener.VersionWatch | None = None
        self._checking = False
        self._last: tuple[str | None, bool] = (None, False)

    @property
    def routing(self) -> bool:
        """Whether the proxy is running."""
        return self.router.running

    def start_routing(self) -> None:
        """Start routing (S-12); a refusal goes to `refused`, another tool to `other_tool`."""
        self._request(None, launch=False)

    def launch(self, link: str | None = None, *, despite_others: bool = False) -> None:
        """Start routing if needed, then Roblox with `link` (unchanged).

        While a Player Verdra didn't start runs, a new launch would most likely hand its join to
        that Player, which never uses Verdra: unless `despite_others`, the launch waits and
        `held_back` asks the user (close that Roblox, join anyway, or cancel).
        """
        if not despite_others and self.refresh_others():
            log.warning(
                "%s",
                QCoreApplication.translate(
                    "M-LAUNCH-09",
                    "Verdra didn't start Roblox yet: Roblox is already running without Verdra, "
                    "so the game would open there without your replacements.",
                ),
            )
            self.held_back.emit(link or "")
            return
        self._request(link, launch=True)

    def retry(self) -> None:
        """Run the last request again ("Try again" in M-COEX-01)."""
        link, launch = self._last
        self._request(link, launch=launch)

    # --- The order of a request: choose, check, start, launch ------------------------------

    def _request(self, link: str | None, *, launch: bool) -> None:
        self._last = (link, launch)
        choice = choose(self.platform.roblox_clients())
        if isinstance(choice, Refused):
            self._refuse(choice)
            return
        if self._checking:
            return  # the check under way carries on with this request (`_last`)
        self._checking = True
        if self.pool is None:
            self._checked(choice, self._check(choice))
            return
        job = self.pool.submit(
            QCoreApplication.translate("Routing", "Checking for other routing tools"),
            lambda _handle: self._check(choice),
        )
        job.succeeded.connect(lambda result: self._checked(choice, result))
        job.failed.connect(
            lambda reason: self._checked(choice, gardener.Coexistence(incomplete=(reason,)))
        )

    def _check(self, client: humus.RobloxClient) -> gardener.Coexistence:
        """The coexistence check of S-15, read-only; runs as a background job (rule 3)."""
        running = self.platform.running_clients(client)
        unreadable = ""
        if isinstance(running, humus.Unsupported):
            unreadable = f"processes: {running.reason}"
            running = None
        for found in running or ():
            # Detailed logging only: the evidence for W-09 in stage 2 (whether another
            # process's proxy variables can be read on Windows).
            log.debug(
                "Coexistence check: %s (%d) %s",
                found.name,
                found.pid,
                {k: gardener.shown_proxy(v) for k, v in found.proxies.items()}
                if found.proxies is not None
                else f"environment not readable: {found.error}",
            )
        try:
            hosts = self.platform.hosts_file().read_text(encoding="utf-8", errors="replace")
        except OSError:
            hosts = None
        ports = {int(self.settings.value("routing.proxy_port"))}
        if self.router.port is not None:
            ports.add(self.router.port)
        return gardener.check_coexistence(running, ports, hosts, unreadable=unreadable)

    def _checked(self, client: humus.RobloxClient, result: gardener.Coexistence) -> None:
        self._checking = False
        for line in result.signs:
            log.warning("%s", line)
        if result.incomplete:
            log.info(
                "%s",
                QCoreApplication.translate(
                    "M-COEX-04",
                    "Verdra couldn't check everything for other routing tools ({parts}), so it "
                    "went ahead.",
                ).format(parts="; ".join(result.incomplete)),
            )
        if not result.clear:
            text = QCoreApplication.translate(
                "M-COEX-01",
                "Another tool is already routing Roblox traffic. Close it, then try again.",
            )
            self.status.error(gardener.Trigger.OTHER_TOOL, text)
            self.other_tool.emit(text)
            return
        self.status.error_cleared(gardener.Trigger.OTHER_TOOL)
        if not self.router.running and self._start(client) is not None:
            return
        link, launch = self._last
        if launch:
            self._launch_now(link)

    def _launch_now(self, link: str | None) -> None:
        """Start the Player and say what happened (M-LAUNCH-12, M-LAUNCH-13)."""
        assert self.client is not None and self.router.port is not None  # noqa: S101 - running
        try:
            pid = self.launches.launch(self.client, link, self.router.port)
        except OSError as error:
            self._refuse(
                Refused(
                    "M-LAUNCH-12",
                    QCoreApplication.translate(
                        "M-LAUNCH-12", "Verdra couldn't start Roblox: {reason}."
                    ).format(reason=error.strerror or type(error).__name__),
                )
            )
            return
        log.info(
            "%s",
            QCoreApplication.translate(
                "M-LAUNCH-13", "Started Roblox through Verdra (process {pid})."
            ).format(pid=pid),
        )
        self.status.launched()
        if self._handoff is not None:
            self._handoff()
        self._handoff = self._schedule(self.HANDOFF_SECONDS, lambda: self._check_handoff(pid))

    def _check_handoff(self, pid: int) -> None:
        """Ten seconds after a launch: is the Player still running? If not, say where it went."""
        self._handoff = None
        if pid in {process.pid for process in self.launches.running()}:
            return
        others = self.refresh_others()
        if others:
            text = QCoreApplication.translate(
                "M-LAUNCH-14",
                "Roblox handed this game to the Roblox that was already running without Verdra "
                "(process {pid}), so your replacements don't show there. Close Roblox completely, "
                "then join again.",
            ).format(pid=min(others))
            log.warning("%s", text)
            self.handed_off.emit(text)
            return
        log.info(
            "%s",
            QCoreApplication.translate(
                "M-LAUNCH-15", "The Roblox Verdra started closed right away (process {pid})."
            ).format(pid=pid),
        )

    # --- Players Verdra didn't start (M-LAUNCH-08) ---------------------------------------------

    def other_players(self) -> frozenset[int]:
        """Return this user's running Players that Verdra didn't start, as far as it can tell.

        Verdra's own record decides (`launches`). A Player not in it whose environment Windows
        shows, with Verdra's proxy in it, was started by an earlier run of Verdra and is taken
        into the record; when Windows refuses to show it ("AccessDenied"), the record alone
        decides. Nothing else is ever tried to read a process (S-15 rule 2).
        """
        running = self.roblox_processes()
        if running is None:
            return frozenset()
        others = running.players - self.players_started_here()
        return others - self._routed_here(others) if others else others

    def _routed_here(self, pids: frozenset[int]) -> set[int]:
        if self.client is None or self.router.port is None or pids <= self._not_ours:
            return set()
        found = self.platform.running_clients(self.client)
        if isinstance(found, humus.Unsupported):
            return set()
        ours = humus.proxy_environment({}, self.router.port)
        routed = {
            client.pid
            for client in found
            if client.pid in pids
            and client.proxies is not None
            and all(client.proxies.get(name.upper()) == value for name, value in ours.items())
        }
        for pid in routed:
            self.launches.adopt(pid)
        self._not_ours = set(pids - routed)
        return routed

    def refresh_others(self) -> frozenset[int]:
        """Look again for Players Verdra didn't start; update the status and `others_changed`.

        While one runs, Verdra looks again every few seconds, so the status and the banner go
        away by themselves once it is closed.
        """
        others = self.other_players()
        if bool(others) != bool(self.others):
            if others:
                self.status.other_player(other_player_text())
            else:
                self.status.other_player_closed()
            self.others = others
            self.others_changed.emit(bool(others))
        self.others = others
        if self._watch is not None:
            self._watch()
            self._watch = None
        if others:
            self._watch = self._schedule(self.OTHERS_WATCH_SECONDS, self._watch_tick)
        return others

    def _watch_tick(self) -> None:
        self._watch = None
        self.refresh_others()

    def close_others(self) -> None:
        """Close the Players Verdra didn't start, after the user confirmed it (M-LAUNCH-10).

        Only Players this user runs that Verdra's record doesn't hold, looked up again now;
        never Studio, never anything else. A Player that won't close is left as it is.
        """
        others = self.other_players()
        processes: list[psutil.Process] = []
        for pid in others:
            with contextlib.suppress(psutil.Error):
                processes.append(psutil.Process(pid))
        for process in processes:
            with contextlib.suppress(psutil.Error):
                process.terminate()
        _gone, left = psutil.wait_procs(processes, timeout=5)
        if processes:
            log.info(
                "%s",
                QCoreApplication.translate(
                    "M-LAUNCH-11", "Closed the Roblox that was running without Verdra."
                )
                if not left
                else QCoreApplication.translate(
                    "M-LAUNCH-16",
                    "Verdra couldn't close the Roblox that is running without Verdra. Close it "
                    "from Task Manager, then try again.",
                ),
            )
        self.refresh_others()

    def _start(self, choice: humus.RobloxClient) -> Refused | None:
        """Add the CA, start the proxy, take over links and watch for new versions."""
        ledger = self.ledger()
        try:
            authority = add_certificate(choice, self.vault(), ledger, self.clock())
        except OSError as error:
            path = error.filename or (choice.trust_files[0] if choice.trust_files else "")
            return self._refuse(
                Refused(
                    "M-CA-01",
                    QCoreApplication.translate(
                        "M-CA-01",
                        "Verdra couldn't add its certificate to Roblox at {path}: {reason}.",
                    ).format(path=path, reason=error.strerror or error),
                )
            )
        interceptor = self._diagnostic(authority) if self.diagnose else self._features(authority)
        try:
            self.router.start(
                int(self.settings.value("routing.proxy_port")), self.connector, interceptor
            )
        except mycelium.ProxyStartError:
            return Refused("M-PROXY-01", self.status.current.reason)
        self.client = choice
        self._links(ledger)
        self.watch = gardener.VersionWatch(
            choice.install_folders,
            self.platform.trust_files_in,
            authority.certificate,
            ledger,
            self,
        )
        self.watch.missing.connect(self._certificate_missing)
        return None

    def repair_certificate(self) -> None:
        """S-14 Degraded (c)'s fix: add the certificate again where it is missing."""
        if self.watch is not None and self.watch.repair():
            self.status.ca_repaired()

    def _certificate_missing(self, version: str) -> None:
        self.status.ca_missing(
            QCoreApplication.translate(
                "M-CA-04",
                "Verdra couldn't add its certificate to the Roblox version {version}, so Roblox "
                "isn't routed.",
            ).format(version=Path(version).name)
        )

    def stop_watching(self) -> None:
        """Stop looking for other Players and for the last launch's hand-off (on quit)."""
        for cancel in (self._watch, self._handoff):
            if cancel is not None:
                cancel()
        self._watch = self._handoff = None

    def stop_routing(self) -> None:
        """Stop the proxy; routing is Idle. Changes stay recorded for Reset everything."""
        if self.watch is not None:
            self.watch.deleteLater()
            self.watch = None
        self.router.stop()

    def restart_roblox(self) -> None:
        """Close the Roblox Verdra launched and start it again through Verdra (S-24)."""
        self.launches.close_all()
        self.launch()

    def roblox_running(self) -> bool:
        """Whether a Roblox Verdra launched is still running (M-SHELL-02)."""
        return bool(self.launches.running())

    def roblox_processes(self) -> RunningRoblox | None:
        """Return this user's running Players and Studios, or None where that can't be read."""
        found = self.platform.roblox_processes()
        if isinstance(found, humus.Unsupported):
            return None
        return RunningRoblox(frozenset(found.players), bool(found.studio))

    def players_started_here(self) -> set[int]:
        """Return the process IDs of the Players this Verdra started that still run."""
        return {process.pid for process in self.launches.running()}

    def close_roblox(self) -> None:
        """Close the Roblox Verdra launched, never any other (S-12 rule 4)."""
        self.launches.close_all()

    def clear_cache(self) -> CacheMove | None:
        """Move Roblox's download cache aside (S-24 step 5); None if nothing moved.

        Only while no Player or Studio runs; the move is in the ledger first, and Reset
        everything puts it back. Every outcome goes to Activity.
        """
        try:
            moved = move_cache(self.platform, self.ledger(), self.clock())
        except RobloxRunningError:
            return None
        except OSError as error:
            log.warning(
                "%s",
                QCoreApplication.translate(
                    "M-CACHE-04",
                    "Verdra couldn't move Roblox's saved assets aside ({reason}). Nothing was "
                    "changed.",
                ).format(reason=error.strerror or type(error).__name__),
            )
            return None
        if moved is not None:
            log.info("%s", cache_moved_text(moved))
            self._prune(moved.backup)
        return moved

    def delete_backups(self) -> None:
        """Delete every cache backup (Settings › "Delete backups"); Reset can't restore them."""
        self._prune(None)

    def _prune(self, keep: Path | None) -> None:
        """Keep only the newest backup (or none): the ledger first, the folders on a worker."""
        try:
            folders = prune_backups(self.ledger(), keep)
        except (OSError, scar.LedgerError) as error:
            self._prune_failed(str(error))
            return
        if not folders:
            return
        if self.pool is None:
            self._delete(folders)
            return
        job = self.pool.submit(
            QCoreApplication.translate("M-CACHE-06", "Deleting backups of Roblox's saved assets"),
            lambda _handle: delete_folders(folders),
        )
        job.succeeded.connect(lambda freed: self._deleted(len(folders), freed))
        job.failed.connect(self._prune_failed)

    def _delete(self, folders: list[Path]) -> None:
        try:
            freed = delete_folders(folders)
        except OSError as error:
            self._prune_failed(error.strerror or type(error).__name__)
            return
        self._deleted(len(folders), freed)

    def _deleted(self, count: int, freed: int) -> None:
        log.info(
            "%s",
            self.tr(
                "Deleted %n backups of Roblox's saved assets ({size}).", "M-CACHE-07", count
            ).format(size=QLocale().formattedDataSize(freed)),
        )
        self.backups_changed.emit()

    def _prune_failed(self, reason: str) -> None:
        log.warning(
            "%s",
            QCoreApplication.translate(
                "M-CACHE-08",
                "Verdra couldn't delete every backup of Roblox's saved assets ({reason}). It tries "
                "again after the next Apply now.",
            ).format(reason=reason),
        )
        self.backups_changed.emit()

    def quit(self) -> None:
        """Shutdown's routing steps: close Roblox if the setting says so, then stop routing."""
        self.stop_watching()
        if self.settings.value("routing.close_roblox_on_quit"):
            self.launches.close_all()
        self.stop_routing()

    def _refuse(self, refused: Refused) -> Refused:
        log.warning("%s", refused.text)
        self.refused.emit(refused.text)
        return refused

    def _links(self, ledger: scar.Ledger) -> None:
        """Take over (or give back) `roblox-player:` links as the setting says (S-12)."""
        try:
            set_link_handling(
                bool(self.settings.value("routing.handle_roblox_links")), ledger, self.platform
            )
        except LinkHandlingUnavailableError:
            return
        except OSError as error:
            log.warning(
                "%s",
                QCoreApplication.translate(
                    "M-LAUNCH-06", "Verdra couldn't take over Roblox links: {reason}."
                ).format(reason=error.strerror or error),
            )

    async def _open_tunnel(self, host: str, port: int) -> mycelium.Streams:
        return await taproot.open_tunnel(self._transport(), host, port, self.router.port or 0)

    def _transport(self) -> taproot.Transport:
        """The internet connection from Settings › Routing (`routing.upstream.*`)."""
        return taproot.Transport(
            kind=self.settings.value("routing.upstream.kind"),
            host=str(self.settings.value("routing.upstream.host")),
            port=int(self.settings.value("routing.upstream.port")),
            username=str(self.settings.value("routing.upstream.username")),
        )

    async def _open_upstream(self, host: str, port: int) -> mycelium.Streams:
        return await taproot.open_tls(
            self._transport(), host, port, proxy_port=self.router.port or 0
        )

    def _features(self, authority: resin.Authority) -> mycelium.Interceptor:
        """Decrypt only the hosts the current snapshot needs (plan 10.1, 10.2; S-21)."""
        left = frozenset(self.capture) | frozenset(self.control[:1] if self.control else ())
        grafter = Grafter(
            self.snapshots, on_unreadable=self.router.report_unreadable_assets, leave=left
        )
        pipeline = hyphae.Pipeline(request=(grafter,), response=(grafter,))
        extra: frozenset[str] = frozenset()
        if left:
            pipeline, extra = self._diagnostics(grafter)
        return hyphae.Interception(
            hyphae.LeafContexts(authority),
            lambda: self.snapshots.current.hosts() | extra,
            self._open_upstream,
            lambda: pipeline,
            on_verification_failure=self.router.report_certificate_failure,
        )

    def _diagnostics(self, grafter: Grafter) -> tuple[hyphae.Pipeline, frozenset[str]]:
        """The source-only format capture and control experiment around the grafter."""
        from verdra.roots import litmus  # noqa: PLC0415 - source runs only (decision 0015)

        before: list[hyphae.Symbiont] = []
        after: list[hyphae.Symbiont] = []
        if self.control:
            before.append(litmus.ControlSwap(*self.control))
        if self.capture:
            after.append(
                litmus.FormatCapture(
                    frozenset(self.capture),
                    terrain.diagnostics_dir(),
                    save_bodies=self.save_bodies,
                )
            )
        # The capture runs after the grafter on the way out (it sees the IDs as sent) and before
        # it on the way back (it sees the CDN's own answer).
        pipeline = hyphae.Pipeline(
            request=(*before, grafter, *after), response=(*before, *after, grafter)
        )
        return pipeline, litmus.CAPTURE_HOSTS

    def _diagnostic(self, authority: resin.Authority) -> mycelium.Interceptor:
        from verdra.roots import litmus  # noqa: PLC0415 - source runs only (decision record 0015)

        return litmus.interception(
            hyphae.LeafContexts(authority),
            self._open_upstream,
            on_verification_failure=self.router.report_certificate_failure,
        )
