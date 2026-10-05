# SPDX-FileCopyrightText: 2026 The Verdra Authors
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

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import psutil
from PySide6.QtCore import QCoreApplication, QObject, Signal

from verdra.bark import husk, resin, scar
from verdra.roots import gardener, hyphae, mycelium, rules, taproot
from verdra.roots.symbionts.grafter import Grafter
from verdra.soil import humus, terrain
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


# --- Launching ------------------------------------------------------------------------------------


@dataclass
class Launches:
    """The Roblox processes Verdra started, so only those are ever closed (S-12 rule 4)."""

    platform: humus.Platform = field(default_factory=humus.current)
    environment: Callable[[], Mapping[str, str]] = lambda: dict(os.environ)
    spawn: humus.Spawn | None = None
    #: PID → the process's creation time, so a reused PID is never mistaken for Roblox.
    started: dict[int, float] = field(default_factory=dict)

    def launch(self, client: humus.RobloxClient, link: str | None, proxy_port: int) -> int:
        """Start `client` with the proxy variables and `link` (unchanged); return its PID."""
        options = {} if self.spawn is None else {"spawn": self.spawn}
        pid = self.platform.launch_roblox(client, link, proxy_port, self.environment(), **options)
        try:
            self.started[pid] = psutil.Process(pid).create_time()
        except psutil.Error:
            self.started[pid] = 0.0
        return pid

    def running(self) -> list[psutil.Process]:
        """Return the processes Verdra started that are still running."""
        alive: list[psutil.Process] = []
        for pid, created in list(self.started.items()):
            try:
                process = psutil.Process(pid)
                if process.is_running() and (not created or process.create_time() == created):
                    alive.append(process)
                    continue
            except psutil.Error:
                pass
            del self.started[pid]
        return alive

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
    """

    refused = Signal(str)
    other_tool = Signal(str)

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
        snapshots: rules.SnapshotHolder | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
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

    def launch(self, link: str | None = None) -> None:
        """Start routing if needed, then Roblox with `link` (unchanged)."""
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
            assert self.client is not None and self.router.port is not None  # noqa: S101 - running
            self.launches.launch(self.client, link, self.router.port)
            self.status.launched()

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

    def quit(self) -> None:
        """Shutdown's routing steps: close Roblox if the setting says so, then stop routing."""
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
        grafter = Grafter(self.snapshots)
        pipeline = hyphae.Pipeline(request=(grafter,), response=(grafter,))
        return hyphae.Interception(
            hyphae.LeafContexts(authority),
            lambda: self.snapshots.current.hosts(),  # noqa: PLW0108 - read the newest snapshot
            self._open_upstream,
            lambda: pipeline,
            on_verification_failure=self.router.report_certificate_failure,
        )

    def _diagnostic(self, authority: resin.Authority) -> mycelium.Interceptor:
        from verdra.roots import litmus  # noqa: PLC0415 - source runs only (decision record 0015)

        return litmus.interception(
            hyphae.LeafContexts(authority),
            self._open_upstream,
            on_verification_failure=self.router.report_certificate_failure,
        )
