# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-12: choosing the client, the certificate, link handling, launching (sprout)."""

from __future__ import annotations

import ast
import os
import re
import socket
import stat
import subprocess
import sys
import threading
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QLocale
from pytestqt.qtbot import QtBot

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from tests.roots.test_routing_status import FakeClock
from tests.support.isolation import MemoryKeyring
from verdra.bark import husk, scar
from verdra.soil import humus, terrain
from verdra.soil.meadow import launcher
from verdra.trunk.branches import fallow, sprout

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
PEM = b"-----BEGIN CERTIFICATE-----\nroblox\n-----END CERTIFICATE-----\n"


def client(**overrides: Any) -> humus.RobloxClient:
    values: dict[str, Any] = {
        "scope": "user",
        "executable": Path("RobloxPlayerBeta.exe"),
        "found_by": "handler",
    }
    return humus.RobloxClient(**(values | overrides))


# --- Choosing the client --------------------------------------------------------------------


@pytest.mark.spec("S-12", 7)
def test_no_roblox_is_m_launch_01() -> None:
    for found in ([], humus.Unsupported(system="macos", reason="deferred")):
        refused = sprout.choose(found)
        assert isinstance(refused, sprout.Refused)
        assert refused.message_id == "M-LAUNCH-01"


def test_a_client_with_an_unconfirmed_fact_is_refused_plainly() -> None:
    shared = client(scope="all_users", unconfirmed=("W-02",))
    assert sprout.choose([shared]) == sprout.unconfirmed("W-02")
    assert sprout.choose([shared]).message_id == "M-LAUNCH-05"  # type: ignore[union-attr]
    mine = client()
    assert sprout.choose([mine, shared]) is mine
    assert sprout.choose([shared, mine]) is mine


def test_every_fact_soil_can_report_has_a_message() -> None:
    """A new unconfirmed fact in soil fails here until it has a plain message."""
    soil = Path(humus.__file__).resolve().parent
    facts = {
        node.value
        for path in soil.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text("utf-8")))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and re.fullmatch(r"[LW]-\d\d", node.value)
    }
    assert facts == {"W-02"}  # Linux (L-) facts left with Linux (decision record 0018)
    for fact in facts:
        assert sprout.unconfirmed(fact).text


# --- The certificate (S-10 in Player folders only) ----------------------------------------------


@pytest.fixture
def installed(tmp_path: Path) -> Iterator[tuple[humus.RobloxClient, Path, Path]]:
    """A per-user install: a current Player folder, an old one (read-only trust file), Studio."""
    versions = tmp_path / "Roblox" / "Versions"
    folders = {}
    for name, program in (
        ("version-current", launcher.PLAYER_EXECUTABLE),
        ("version-old", launcher.PLAYER_EXECUTABLE),
        ("version-studio", launcher.STUDIO_EXECUTABLE),
    ):
        folder = versions / name
        (folder / "ssl").mkdir(parents=True)
        (folder / "ssl" / "cacert.pem").write_bytes(PEM)
        (folder / program).write_bytes(b"MZ")
        folders[name] = folder
    old = folders["version-old"] / "ssl" / "cacert.pem"
    old.chmod(stat.S_IREAD)

    class Registry:
        """The handler names the current folder; nothing else exists."""

        def get(self, hive: str, key: str, name: str) -> str | None:
            return "version-current" if (hive, name) == ("HKCU", "version") else None

    [found] = launcher.find_clients(tmp_path, [], Registry())  # type: ignore[arg-type]
    yield found, old, folders["version-studio"] / "ssl" / "cacert.pem"
    old.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_the_certificate_goes_into_every_player_folder_and_never_studio(
    installed: tuple[humus.RobloxClient, Path, Path], tmp_path: Path
) -> None:
    found, old, studio = installed
    vault = husk.Husk(MemoryKeyring())
    ledger = scar.Ledger(tmp_path / "changes.json")
    # Windows reports a read-only file as 0o444, POSIX as 0o400: compare with what it was.
    read_only = stat.S_IMODE(old.stat().st_mode)
    assert not read_only & stat.S_IWUSR
    sprout.add_certificate(found, vault, ledger, NOW)
    assert len(found.trust_files) == 2
    for path in found.trust_files:
        assert terrain.CA_BEGIN_MARKER.encode() in path.read_bytes()
    assert studio.read_bytes() == PEM
    assert stat.S_IMODE(old.stat().st_mode) == read_only
    assert [e.kind for e in ledger.entries()] == ["ca_roblox_bundle"] * 2
    # Reset gives every trust file back byte for byte, read-only flag included.
    summary = fallow.reset(ledger.path, vault=vault, cert_file=tmp_path / "ca.crt")
    assert summary.failed == []
    for path in found.trust_files:
        assert path.read_bytes() == PEM
    assert stat.S_IMODE(old.stat().st_mode) == read_only


def test_a_client_with_an_unconfirmed_fact_never_gets_the_certificate(tmp_path: Path) -> None:
    vault = husk.Husk(MemoryKeyring())
    ledger = scar.Ledger(tmp_path / "changes.json")
    with pytest.raises(ValueError, match="unconfirmed"):
        sprout.add_certificate(client(unconfirmed=("W-02",)), vault, ledger, NOW)
    assert ledger.entries() == []


# --- Link handling ----------------------------------------------------------------------------


class FakeHandler:
    """A `humus.LinkHandler` holding one command."""

    def __init__(self, command: str | None = "roblox") -> None:
        self.command = command

    def snapshot(self) -> dict[str, Any]:
        return {"command": self.command}

    def register(self, command: Sequence[str]) -> None:
        self.command = " ".join(command)

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        self.command = snapshot["command"]

    def registered(self, command: Sequence[str]) -> bool:
        return self.command == " ".join(command)


class FakePlatform:
    def __init__(self, handler: FakeHandler | humus.Unsupported) -> None:
        self.handler = handler

    def link_handler(self) -> FakeHandler | humus.Unsupported:
        return self.handler


@pytest.mark.spec("S-12", 3)
def test_link_handling_records_the_previous_handler_first_and_restores_it(tmp_path: Path) -> None:
    """S-12 test 3 and rule 2 (the registry round trip is in tests/soil/meadow)."""
    handler = FakeHandler()
    platform: Any = FakePlatform(handler)
    ledger = scar.Ledger(tmp_path / "changes.json")
    sprout.set_link_handling(True, ledger, platform, ["verdra"])
    assert handler.command == "verdra"
    [entry] = ledger.entries()
    assert (entry.kind, entry.target, entry.state) == ("uri_handler", "roblox-player", "done")
    assert entry.details["snapshot"] == {"command": "roblox"}
    sprout.set_link_handling(True, ledger, platform, ["verdra"])  # already on: nothing new
    assert len(ledger.entries()) == 1
    sprout.set_link_handling(False, ledger, platform, ["verdra"])
    assert handler.command == "roblox"
    assert [e.state for e in ledger.entries()] == ["removed"]
    sprout.set_link_handling(True, ledger, platform, ["verdra"])  # on again: a new entry
    assert [e.state for e in ledger.entries()] == ["removed", "done"]


def test_a_handler_roblox_took_back_is_recorded_again(tmp_path: Path) -> None:
    handler = FakeHandler()
    platform: Any = FakePlatform(handler)
    ledger = scar.Ledger(tmp_path / "changes.json")
    sprout.set_link_handling(True, ledger, platform, ["verdra"])
    handler.command = "roblox, updated"  # Roblox's updater rewrote its handler
    sprout.set_link_handling(True, ledger, platform, ["verdra"])
    first, second = ledger.entries()
    assert (first.state, first.details["reclaimed_by_roblox"]) == ("removed", True)
    assert (second.state, second.details["snapshot"]) == ("done", {"command": "roblox, updated"})
    sprout.set_link_handling(False, ledger, platform, ["verdra"])
    assert handler.command == "roblox, updated"


def test_reset_everything_restores_the_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler = FakeHandler(None)
    platform: Any = FakePlatform(handler)
    monkeypatch.setattr(humus, "current", lambda: platform)
    ledger = scar.Ledger(tmp_path / "changes.json")
    sprout.set_link_handling(True, ledger, platform, ["verdra"])
    vault = husk.Husk(MemoryKeyring())
    summary = fallow.reset(ledger.path, vault=vault, cert_file=tmp_path / "ca.crt")
    assert summary.failed == []
    assert handler.command is None


def test_a_failed_registration_is_marked_failed(tmp_path: Path) -> None:
    class Broken(FakeHandler):
        def register(self, command: Sequence[str]) -> None:
            raise PermissionError("access denied")

    ledger = scar.Ledger(tmp_path / "changes.json")
    with pytest.raises(PermissionError):
        sprout.set_link_handling(True, ledger, FakePlatform(Broken()), ["verdra"])  # type: ignore[arg-type]
    [entry] = ledger.entries()
    assert (entry.state, entry.details["error"]) == ("failed", "access denied")


def test_where_links_cant_be_taken_over_nothing_is_recorded(tmp_path: Path) -> None:
    ledger = scar.Ledger(tmp_path / "changes.json")
    platform: Any = FakePlatform(humus.Unsupported(system="linux", reason="unconfirmed"))
    with pytest.raises(sprout.LinkHandlingUnavailableError):
        sprout.set_link_handling(True, ledger, platform, ["verdra"])
    assert ledger.entries() == []


# --- Launching and closing (rule 4) -----------------------------------------------------------


SLEEP = [sys.executable, "-c", "import time; time.sleep(60)"]


class SleepingPlatform:
    """Launches a sleeping Python instead of Roblox, recording what it was given."""

    def __init__(self) -> None:
        self.given: list[tuple[str | None, int, dict[str, str]]] = []
        self.processes: list[subprocess.Popen[bytes]] = []

    def launch_roblox(
        self,
        client: humus.RobloxClient,
        link: str | None,
        proxy_port: int,
        environment: Mapping[str, str],
        spawn: Any = subprocess.Popen,
    ) -> int:
        self.given.append((link, proxy_port, dict(environment)))
        self.processes.append(subprocess.Popen(SLEEP))  # noqa: S603 - the test's own interpreter
        return self.processes[-1].pid


def test_only_the_processes_verdra_started_are_closed() -> None:
    platform = SleepingPlatform()
    launches = sprout.Launches(platform=platform, environment=lambda: {"A": "1"})  # type: ignore[arg-type]
    other = subprocess.Popen(SLEEP)  # noqa: S603 - a Roblox Verdra didn't start
    try:
        pid = launches.launch(client(), "roblox-player:1", 49443)
        assert platform.given == [("roblox-player:1", 49443, {"A": "1"})]
        assert [p.pid for p in launches.running()] == [pid]
        launches.close_all(timeout=10)
        assert launches.running() == []
        assert platform.processes[0].wait(timeout=10) is not None
        assert other.poll() is None
    finally:
        for process in [other, *platform.processes]:
            process.kill()
            process.wait()


# --- Routing and launching together (Sprout) --------------------------------------------------


class FakeSettings:
    def __init__(self, **values: Any) -> None:
        self.values = {
            "routing.proxy_port": 0,
            "routing.handle_roblox_links": True,
            "routing.close_roblox_on_quit": False,
            "routing.upstream.kind": "direct",
            "routing.upstream.host": "",
            "routing.upstream.port": 0,
            "routing.upstream.username": "",
        } | {key.replace("__", "."): value for key, value in values.items()}

    def value(self, key: str) -> Any:
        return self.values[key]


class RoutingPlatform(FakePlatform):
    """Clients, trust files and launches for `Sprout`, without Roblox."""

    def __init__(self, clients: list[humus.RobloxClient], hosts: Path | None = None) -> None:
        super().__init__(FakeHandler())
        self.clients = clients
        self.launched: list[tuple[str | None, int]] = []
        self.hosts = hosts or Path(os.devnull)
        self.running: list[humus.RunningClient] | humus.Unsupported = []
        self.checked_on: list[bool] = []

    def hosts_file(self) -> Path:
        return self.hosts

    def running_clients(
        self, client: humus.RobloxClient
    ) -> list[humus.RunningClient] | humus.Unsupported:
        self.checked_on.append(threading.current_thread() is threading.main_thread())
        return self.running

    def roblox_clients(self) -> list[humus.RobloxClient]:
        return self.clients

    def trust_files_in(self, version_folder: Path) -> list[Path]:
        return []

    def launch_roblox(
        self,
        client: humus.RobloxClient,
        link: str | None,
        proxy_port: int,
        environment: Mapping[str, str],
        spawn: Any = None,
    ) -> int:
        self.launched.append((link, proxy_port))
        return 999_999_999  # no such process


@pytest.fixture
def routing_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def routed(
    installed: tuple[humus.RobloxClient, Path, Path],
    tmp_path: Path,
    qapp: Any,
    routing_clock: FakeClock,
) -> Iterator[tuple[sprout.Sprout, RoutingPlatform, scar.Ledger]]:
    from verdra.roots import gardener  # noqa: PLC0415

    found, _old, _studio = installed
    platform = RoutingPlatform([found])
    ledger = scar.Ledger(tmp_path / "changes.json")
    vault = husk.Husk(MemoryKeyring())
    status = gardener.RoutingStatusSource(routing_clock.schedule)
    made = sprout.Sprout(
        FakeSettings(),
        status,
        platform=platform,  # type: ignore[arg-type]
        ledger=lambda: ledger,
        vault=lambda: vault,
        clock=lambda: NOW,
    )
    yield made, platform, ledger
    made.stop_routing()
    made.deleteLater()
    status.deleteLater()


def test_starting_routing_adds_the_certificate_starts_the_proxy_and_takes_links(
    routed: tuple[sprout.Sprout, RoutingPlatform, scar.Ledger],
) -> None:
    made, platform, ledger = routed
    assert made.start_routing() is None
    assert made.routing and made.router.port
    assert made.status.current.state.value == "routing"
    assert sorted(e.kind for e in ledger.entries()) == ["ca_roblox_bundle"] * 2 + ["uri_handler"]
    assert platform.handler.command is not None and "verdra" in platform.handler.command  # type: ignore[union-attr]
    assert made.watch is not None
    assert made.start_routing() is None  # already routing: nothing new
    assert len(ledger.entries()) == 3


@pytest.mark.spec("S-12", 5)
def test_launching_starts_routing_first_and_opens_the_launch_window(
    routed: tuple[sprout.Sprout, RoutingPlatform, scar.Ledger],
) -> None:
    made, platform, _ledger = routed
    link = "roblox-player:1+launchmode:play+gameinfo:x"
    made.launch(link)
    assert platform.launched == [(link, made.router.port)]
    assert made.status._launch is not None  # noqa: SLF001 - the S-14 launch window is open


def test_a_refused_client_changes_nothing_and_says_why(tmp_path: Path, qapp: Any) -> None:
    from verdra.roots import gardener  # noqa: PLC0415

    platform = RoutingPlatform([client(scope="all_users", unconfirmed=("W-02",))])
    ledger = scar.Ledger(tmp_path / "changes.json")
    status = gardener.RoutingStatusSource(FakeClock().schedule)
    made = sprout.Sprout(FakeSettings(), status, platform=platform, ledger=lambda: ledger)  # type: ignore[arg-type]
    said: list[str] = []
    made.refused.connect(said.append)
    made.launch("roblox-player:1")
    assert said == [sprout.unconfirmed("W-02").text]
    assert not made.routing
    assert platform.launched == []
    assert ledger.entries() == []
    assert platform.handler.command == "roblox"  # type: ignore[union-attr]
    made.deleteLater()
    status.deleteLater()


def test_quitting_closes_roblox_only_when_the_setting_says_so(
    routed: tuple[sprout.Sprout, RoutingPlatform, scar.Ledger],
) -> None:
    made, _platform, _ledger = routed
    closed: list[bool] = []
    made.launches.close_all = lambda timeout=5.0: closed.append(True)  # type: ignore[method-assign]
    made.start_routing()
    made.quit()
    assert closed == [] and not made.routing
    made.settings.values["routing.close_roblox_on_quit"] = True  # type: ignore[attr-defined]
    made.start_routing()
    made.quit()
    assert closed == [True] and not made.routing


def test_diagnostic_routing_intercepts_the_10_2_hosts(
    routed: tuple[sprout.Sprout, RoutingPlatform, scar.Ledger],
) -> None:
    from verdra.roots import litmus  # noqa: PLC0415

    made, _platform, _ledger = routed
    made.diagnose = True
    assert made.start_routing() is None
    interceptor = made.router._proxy.interceptor  # type: ignore[union-attr]  # noqa: SLF001
    assert interceptor is not None
    assert interceptor.wants("assetdelivery.roblox.com", 443)
    assert not interceptor.wants("example.com", 443)
    assert isinstance(interceptor.hosts(), litmus.DiagnosticHosts)  # type: ignore[attr-defined]


@pytest.mark.spec("S-11", 3)
def test_an_upstream_certificate_failure_turns_routing_degraded(
    routed: tuple[sprout.Sprout, RoutingPlatform, scar.Ledger], qtbot: QtBot
) -> None:
    """Plan 12.2: the request fails (hyphae's test) and the status turns Degraded with M-PROXY-02,
    reported from the proxy's own thread."""
    made, _platform, _ledger = routed
    made.diagnose = True
    assert made.start_routing() is None
    interceptor = made.router._proxy.interceptor  # type: ignore[union-attr]  # noqa: SLF001
    report = interceptor.on_verification_failure  # type: ignore[attr-defined]
    thread = threading.Thread(target=report, args=("fts.rbxcdn.com", "self-signed certificate"))
    thread.start()
    thread.join()
    qtbot.waitUntil(lambda: made.status.current.state.value == "degraded")
    assert made.status.current.trigger.value == "upstream_certificate"  # type: ignore[union-attr]
    assert made.status.current.reason == (
        "A Roblox server's certificate couldn't be verified (fts.rbxcdn.com). That request was "
        "blocked."
    )


@pytest.mark.spec("S-14", 1)
def test_each_trigger_reaches_the_status_from_where_it_happens(
    routed: tuple[sprout.Sprout, RoutingPlatform, scar.Ledger],
    routing_clock: FakeClock,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S-14 test 1 through the real proxy, launcher and version watch. Error from another tool:
    the S-15 tests below; from taken ports: tests/roots/test_router.py and test_mycelium.py."""
    from verdra.roots import gardener  # noqa: PLC0415

    made, platform, _ledger = routed

    async def no_network(host: str, port: int) -> Any:
        raise OSError(f"no network in this test ({host}:{port})")

    made.connector = no_network
    made.diagnose = True
    state = lambda: made.status.current.state.value  # noqa: E731
    trigger = lambda: made.status.current.trigger.value  # type: ignore[union-attr]  # noqa: E731
    monkeypatch.setattr(platform, "trust_files_in", lambda v: [v / "ssl" / "cacert.pem"])
    # Start and stop
    assert made.start_routing() is None
    assert state() == "routing"
    made.stop_routing()
    assert state() == "idle"
    # (a) Roblox launched with the proxy variables, but no CONNECT within 20 s ...
    made.launch("roblox-player:1")
    assert platform.launched == [("roblox-player:1", made.router.port)]
    routing_clock.advance(20.5)
    assert (state(), trigger()) == ("degraded", "not_routed")
    # ... cleared by its first CONNECT through the proxy
    with socket.create_connection(("127.0.0.1", made.router.port or 0), timeout=5) as client:
        client.sendall(b"CONNECT assetdelivery.roblox.com:443 HTTP/1.1\r\n\r\n")
        qtbot.waitUntil(lambda: state() == "routing", timeout=2_000)
    # (b) an upstream certificate failure, reported on the proxy's thread
    report = made.router.report_certificate_failure
    thread = threading.Thread(target=report, args=("fts.rbxcdn.com", "self-signed certificate"))
    thread.start()
    thread.join()
    qtbot.waitUntil(lambda: state() == "degraded", timeout=2_000)
    assert trigger() == "upstream_certificate"
    routing_clock.advance(gardener.CERTIFICATE_WINDOW_SECONDS + 1)
    assert state() == "routing"
    # (c) a new Roblox version whose trust file can't take the block, until it's repaired
    assert made.watch is not None
    made.watch.PATIENCE_SECONDS = 0.2
    with monkeypatch.context() as locked:
        locked.setattr(gardener, "add_ca", _locked)
        version = made.client.install_folders[0] / "version-new"  # type: ignore[union-attr]
        (version / "ssl").mkdir(parents=True)
        (version / "ssl" / "cacert.pem").write_bytes(b"")
        qtbot.waitUntil(lambda: state() == "degraded", timeout=5_000)
    assert trigger() == "ca_missing"
    assert made.status.current.reason == (
        "Verdra couldn't add its certificate to the Roblox version version-new, so Roblox "
        "isn't routed."
    )
    made.repair_certificate()
    assert state() == "routing"


@pytest.mark.spec("S-16", 5)
def test_reset_completes_with_the_proxy_port_taken_and_routing_in_error(
    routed: tuple[sprout.Sprout, RoutingPlatform, scar.Ledger],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio  # noqa: PLC0415

    from verdra.trunk.branches import fallow  # noqa: PLC0415

    made, platform, ledger = routed
    files = list(platform.clients[0].trust_files)
    before = [p.read_bytes() for p in files]

    async def taken(*_args: object, **_kwargs: object) -> None:
        raise OSError("in use")

    monkeypatch.setattr(asyncio, "start_server", taken)
    made.start_routing()
    assert (made.status.current.state.value, made.routing) == ("error", False)
    assert made.status.current.trigger.value == "proxy_failed"  # type: ignore[union-attr]
    assert list(ledger.open_entries())  # the certificate went in before the proxy failed
    vault = husk.Husk(MemoryKeyring())
    summary = fallow.reset(ledger.path, vault=vault, cert_file=tmp_path / "ca.crt")
    assert summary.failed == []
    assert summary.removed == len(files)
    assert list(scar.Ledger(ledger.path).open_entries()) == []
    assert [p.read_bytes() for p in files] == before


def _locked(*_args: object) -> None:
    raise PermissionError(13, "Access is denied")


# --- Coexistence before routing (spec S-15) ---------------------------------------------------


@pytest.mark.spec("S-15", 1)
def test_another_tool_blocks_routing_with_m_coex_01_and_try_again_routes(
    routed: tuple[sprout.Sprout, RoutingPlatform, scar.Ledger],
) -> None:
    """S-15 tests 1 and 2: a Roblox using another proxy blocks start; after it exits, it routes."""
    made, platform, ledger = routed
    platform.running = [
        humus.RunningClient(7, "RobloxPlayerBeta.exe", {"HTTPS_PROXY": "http://127.0.0.1:8888"})
    ]
    shown: list[str] = []
    made.other_tool.connect(shown.append)
    made.launch("roblox-player:1")
    assert shown == ["Another tool is already routing Roblox traffic. Close it, then try again."]
    assert made.status.current.state.value == "error"
    assert made.status.current.trigger.value == "other_tool"  # type: ignore[union-attr]
    assert not made.routing and platform.launched == [] and ledger.entries() == []
    platform.running = []  # the other tool's Roblox has exited
    made.retry()
    assert made.routing
    assert made.status.current.state.value == "routing"
    assert platform.launched == [("roblox-player:1", made.router.port)]


@pytest.mark.spec("S-15", 3)
def test_a_foreign_hosts_line_blocks_routing_and_the_file_stays_byte_identical(
    routed: tuple[sprout.Sprout, RoutingPlatform, scar.Ledger], tmp_path: Path
) -> None:
    made, platform, _ledger = routed
    hosts = tmp_path / "hosts"
    hosts.write_bytes(b"127.0.0.1 localhost\r\n10.0.0.9 assetdelivery.roblox.com\r\n")
    before = hosts.read_bytes()
    platform.hosts = hosts
    made.start_routing()
    assert not made.routing
    assert hosts.read_bytes() == before


@pytest.mark.spec("S-15", 6)
def test_an_incomplete_check_still_routes_and_says_so(
    routed: tuple[sprout.Sprout, RoutingPlatform, scar.Ledger],
    caplog: pytest.LogCaptureFixture,
) -> None:
    made, platform, _ledger = routed
    platform.running = [humus.RunningClient(8, "RobloxPlayerBeta.exe", None, "AccessDenied")]
    with caplog.at_level("INFO", logger="verdra"):
        made.start_routing()
    assert made.routing
    assert any("RobloxPlayerBeta.exe (8): AccessDenied" in r.getMessage() for r in caplog.records)


@pytest.mark.spec("S-15", 4)
def test_verdras_own_port_taken_is_no_sign(
    routed: tuple[sprout.Sprout, RoutingPlatform, scar.Ledger],
    caplog: pytest.LogCaptureFixture,
) -> None:
    import socket  # noqa: PLC0415

    made, _platform, _ledger = routed
    with socket.create_server(("127.0.0.1", 0)) as taken:
        port = taken.getsockname()[1]
        made.settings.values["routing.proxy_port"] = port  # type: ignore[attr-defined]
        with caplog.at_level("INFO", logger="verdra"):
            made.start_routing()
        assert made.routing and made.router.port != port
    assert any(f"Port {port} was in use" in r.getMessage() for r in caplog.records)


@pytest.mark.spec("S-15", 7)
def test_the_check_runs_off_the_ui_thread(
    routed: tuple[sprout.Sprout, RoutingPlatform, scar.Ledger], qtbot: Any
) -> None:
    from verdra.trunk import tendrils  # noqa: PLC0415

    made, platform, _ledger = routed
    pool = tendrils.Tendrils(workers=2)
    made.pool = pool
    try:
        made.start_routing()
        qtbot.waitUntil(lambda: made.routing, timeout=5000)
        assert platform.checked_on == [False]
    finally:
        pool.shutdown(grace=1.0)


@pytest.mark.spec("S-21", 9)
def test_routing_decrypts_only_what_the_replacements_need(
    routed: tuple[sprout.Sprout, RoutingPlatform, scar.Ledger],
) -> None:
    from types import MappingProxyType  # noqa: PLC0415

    from verdra.roots import rules  # noqa: PLC0415

    made, _platform, _ledger = routed
    assert made.start_routing() is None
    interceptor = made.router._proxy.interceptor  # type: ignore[union-attr]  # noqa: SLF001
    assert interceptor is not None
    hosts = ("assetdelivery.roblox.com", "fts.rbxcdn.com", "apis.roblox.com", "example.com")
    assert [interceptor.wants(h, 443) for h in hosts] == [False] * 4  # no replacement: tunnels
    graft = rules.Graft(1111111, None, "asset_id", "2222222", "P", "r")
    made.snapshots.publish(rules.GraftSnapshot(MappingProxyType({(1111111, None): graft})))
    # Published while routing: the next connection already sees it.
    assert [interceptor.wants(h, 443) for h in hosts] == [True, False, False, False]
    # A CONNECT may spell the host in capitals or with the root's trailing dot.
    assert interceptor.wants("AssetDelivery.Roblox.com.", 443)
    assert [s.name for s in interceptor.pipeline().request] == ["grafter"]  # type: ignore[attr-defined]
    made.snapshots.publish(rules.GraftSnapshot())
    assert not interceptor.wants("assetdelivery.roblox.com", 443)


#: Roblox's own files beside the version folders: the W-06 names from the maintainer's Stage 1
#: report (cache database and its journal files, cache folders, local storage, logs, settings).
ROBLOX_FILES = (
    "rbx-storage.db",
    "rbx-storage.db-shm",
    "rbx-storage.db-wal",
    "rbx-storage/ab/cd0123",
    "LocalStorage/appStorage.json",
    "logs/0.741_20261004_player.log",
    "GlobalBasicSettings_13.xml",
    "frm.cfg",
    "Downloads/roblox-installer.exe",
)


@pytest.mark.spec("S-24", 6)
def test_apply_now_deletes_and_changes_no_roblox_file(
    routed: tuple[sprout.Sprout, RoutingPlatform, scar.Ledger], tmp_path: Path
) -> None:
    """S-24 rule 4: until the cache files are recorded, Apply now clears nothing. It publishes the
    snapshot and restarts only the Roblox Verdra launched; the only changes on disk are routing's
    own (the CA block in Player trust files, the link handler), each in the ledger."""
    from verdra.trunk.branches import grafts  # noqa: PLC0415

    made, platform, ledger = routed
    roblox = tmp_path / "Roblox"
    for name in ROBLOX_FILES:
        (roblox / name).parent.mkdir(parents=True, exist_ok=True)
        (roblox / name).write_bytes(name.encode())
    studio = roblox / "Versions" / "version-studio" / "ssl" / "cacert.pem"
    assert made.start_routing() is None  # routing's own changes happen here, recorded
    recorded = [(e.kind, e.target) for e in ledger.entries()]
    assert {kind for kind, _ in recorded} == {"ca_roblox_bundle", "uri_handler"}

    def files() -> dict[str, tuple[bytes, int]]:
        return {
            str(p.relative_to(roblox)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(roblox.rglob("*"))
            if p.is_file()
        }

    before = files()

    class Settings:
        def __init__(self) -> None:
            self.values: dict[str, object] = {"replacements.profile_order": []}

        def value(self, key: str) -> object:
            return self.values[key]

        def set(self, key: str, value: object) -> None:
            self.values[key] = value

    service = grafts.Grafts(tmp_path / "profiles", Settings(), holder=made.snapshots)
    profile = service.edit("create", "A")
    service.edit(
        "add_replacement",
        profile.id,
        grafts.Original(asset_id=1111111),
        grafts.Target(kind="asset_id", value="2222222"),
    )
    service.edit(  # real-size IDs: one above Qt's 32-bit int, one above 2^32
        "add_replacement",
        profile.id,
        grafts.Original(asset_id=ABOVE_UINT32),
        grafts.Target(kind="asset_id", value=str(ABOVE_INT32)),
    )
    assert service.publish() == 2  # what Apply now does first
    made.restart_roblox()  # then, after M-LAUNCH-03, this
    assert made.snapshots.current.swaps() == {1111111: 2222222, ABOVE_UINT32: ABOVE_INT32}
    assert files() == before  # nothing in Roblox's folder deleted or changed
    assert studio.read_bytes() == PEM  # Studio's trust file never touched
    assert [(e.kind, e.target) for e in ledger.entries()] == recorded  # no new system change
    assert platform.launched[-1] == (None, made.router.port)  # relaunched through Verdra
    service.deleteLater()


# --- Roblox's download cache, moved aside by Apply now (S-24 step 5) ---------------------------

#: Every name W-06 recorded in the maintainer's `%LOCALAPPDATA%\Roblox` (one file in each folder),
#: so the test proves that only the cache names move.
W06_NAMES = (
    "123456789/x.dat",  # the numeric folder (likely the user ID), with an invented number
    "AnalysticsSettings.xml",
    "AssistantSettings/a.json",
    "ClientSettings/c.json",
    "DefaultInstances/d.rbxm",
    "Downloads/roblox-installer.exe",
    "frm.cfg",
    "GlobalBasicSettings_13.xml",
    "GlobalBasicSettings_13_Studio.xml",
    "GlobalSettings_13.xml",
    "LocalStorage/appStorage.json",
    "logs/0.741_20261004_player.log",
    "mcp.bat",
    "notifications/n.json",
    "OTAPatchBackups/o.bin",
    "OTAPlugins/p.rbxm",
    "placeIDEState/s.json",
    "rbx-storage/ab/cd0123",
    "rbx-storage/ef/gh4567",
    "rbx-storage.db",
    "rbx-storage.db-shm",
    "rbx-storage.db-wal",
    "rbx-storage.id",
    "rbx-storage-sc/k.bin",
    "RobloxPlayerInstaller/i.exe",
    "RobloxStudio/settings.json",
    "RobloxStudioInstaller/i.exe",
    "tmp-capture-storage/t.bin",
    "UniversalApp/u.json",
    "Versions/version-player/RobloxPlayerBeta.exe",
    "Versions/version-studio/RobloxStudioBeta.exe",
)
CACHE = ("rbx-storage.db-shm", "rbx-storage.db-wal", "rbx-storage.db", "rbx-storage")


class CachePlatform:
    """The Windows platform's cache list over a fake `%LOCALAPPDATA%`, with set processes."""

    def __init__(self, local_appdata: Path) -> None:
        self.local_appdata = local_appdata
        self.processes = humus.RobloxProcesses()

    def roblox_cache_files(self) -> list[Path]:
        from verdra.soil.meadow import files  # noqa: PLC0415

        return files.cache_files(self.local_appdata)

    def roblox_processes(self) -> humus.RobloxProcesses:
        return self.processes


@pytest.fixture
def roblox_folder(tmp_path: Path) -> Path:
    roblox = tmp_path / "LocalAppData" / "Roblox"
    for name in W06_NAMES:
        (roblox / name).parent.mkdir(parents=True, exist_ok=True)
        (roblox / name).write_bytes(name.encode())
    return roblox


def snapshot(folder: Path) -> dict[str, tuple[bytes, int]]:
    """Every file under `folder`: its bytes and modification time (nanoseconds)."""
    return {
        p.relative_to(folder).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def is_cache(relative: str) -> bool:
    return relative.split("/", 1)[0] in CACHE


@pytest.mark.spec("S-24", 7)
def test_only_the_recorded_cache_moves_and_nothing_else_changes(
    roblox_folder: Path, tmp_path: Path
) -> None:
    platform = CachePlatform(roblox_folder.parent)
    ledger = scar.Ledger(tmp_path / "changes.json")
    before = snapshot(roblox_folder)
    moved = sprout.move_cache(platform, ledger, NOW, root=tmp_path / "backup")  # type: ignore[arg-type]
    assert moved is not None and moved.names == CACHE
    after = snapshot(roblox_folder)
    # Everything else is byte- and date-identical; the cache is gone from Roblox's folder ...
    assert after == {k: v for k, v in before.items() if not is_cache(k)}
    # ... and is in the backup, byte- and date-identical.
    assert snapshot(moved.backup) == {k: v for k, v in before.items() if is_cache(k)}
    [entry] = ledger.entries()
    assert (entry.kind, entry.state, entry.target) == (
        "roblox_cache_moved",
        "done",
        str(roblox_folder),
    )
    assert entry.details["backup"] == str(moved.backup)
    assert [item["name"] for item in entry.details["items"]] == list(CACHE)
    assert sprout.move_cache(platform, ledger, NOW, root=tmp_path / "backup") is None  # type: ignore[arg-type]


@pytest.mark.spec("S-24", 7)
@pytest.mark.parametrize(
    "running",
    [humus.RobloxProcesses(players=(41,)), humus.RobloxProcesses(studio=(42,))],
    ids=["player", "studio"],
)
def test_nothing_moves_while_a_player_or_studio_runs(
    roblox_folder: Path, tmp_path: Path, running: humus.RobloxProcesses
) -> None:
    platform = CachePlatform(roblox_folder.parent)
    platform.processes = running
    ledger = scar.Ledger(tmp_path / "changes.json")
    before = snapshot(roblox_folder)
    with pytest.raises(sprout.RobloxRunningError):
        sprout.move_cache(platform, ledger, NOW, root=tmp_path / "backup")  # type: ignore[arg-type]
    assert snapshot(roblox_folder) == before
    assert ledger.entries() == []
    assert not (tmp_path / "backup").exists()


@pytest.mark.spec("S-24", 8)
def test_reset_everything_puts_the_cache_back(roblox_folder: Path, tmp_path: Path) -> None:
    platform = CachePlatform(roblox_folder.parent)
    ledger_file = tmp_path / "changes.json"
    before = snapshot(roblox_folder)
    moved = sprout.move_cache(platform, scar.Ledger(ledger_file), NOW, root=tmp_path / "backup")  # type: ignore[arg-type]
    assert moved is not None
    summary = fallow.reset(
        ledger_file, vault=husk.Husk(MemoryKeyring()), cert_file=tmp_path / "ca.crt"
    )
    assert summary.removed == 1 and summary.failed == []
    assert snapshot(roblox_folder) == before  # every byte and date as it was
    assert not (tmp_path / "backup").exists()  # the empty backup folders are gone
    assert [e.state for e in scar.Ledger(ledger_file).entries()] == ["removed"]


@pytest.mark.spec("S-24", 8)
def test_reset_keeps_the_backup_when_roblox_made_new_files(
    roblox_folder: Path, tmp_path: Path
) -> None:
    platform = CachePlatform(roblox_folder.parent)
    ledger_file = tmp_path / "changes.json"
    moved = sprout.move_cache(platform, scar.Ledger(ledger_file), NOW, root=tmp_path / "backup")  # type: ignore[arg-type]
    assert moved is not None
    kept = snapshot(moved.backup)
    (roblox_folder / "rbx-storage.db").write_bytes(b"Roblox's new database")
    summary = fallow.reset(
        ledger_file, vault=husk.Husk(MemoryKeyring()), cert_file=tmp_path / "ca.crt"
    )
    [failed] = summary.failed
    assert failed.reason == (
        "Roblox has made new saved assets since, so Verdra kept the old ones in "
        f"{moved.backup}. You can delete that folder."
    )
    assert snapshot(moved.backup) == kept  # nothing put back, nothing lost
    assert (roblox_folder / "rbx-storage.db").read_bytes() == b"Roblox's new database"
    assert not (roblox_folder / "rbx-storage.db-wal").exists()  # no half-restored database


@pytest.mark.spec("S-24", 9)
def test_a_crash_mid_move_loses_nothing_and_reset_puts_it_back(
    roblox_folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = CachePlatform(roblox_folder.parent)
    ledger_file = tmp_path / "changes.json"
    before = snapshot(roblox_folder)
    real_move = sprout.shutil.move
    done: list[str] = []

    def crash_after_two(source: Path, target: Path) -> object:
        if len(done) == 2:
            raise KeyboardInterrupt  # the process dies here: nothing after this line runs
        done.append(Path(source).name)
        return real_move(source, target)

    monkeypatch.setattr(sprout.shutil, "move", crash_after_two)
    with pytest.raises(KeyboardInterrupt):
        sprout.move_cache(platform, scar.Ledger(ledger_file), NOW, root=tmp_path / "backup")  # type: ignore[arg-type]
    monkeypatch.undo()
    # Every file is either in place or in the backup, and the ledger knows about the move.
    [entry] = scar.Ledger(ledger_file).entries()
    assert entry.state == "pending"
    backup = Path(entry.details["backup"])
    for relative, (data, _mtime) in before.items():
        place = roblox_folder / relative
        saved = backup / relative
        assert (place.exists() and place.read_bytes() == data) or saved.read_bytes() == data
    fallow.reset(ledger_file, vault=husk.Husk(MemoryKeyring()), cert_file=tmp_path / "ca.crt")
    assert snapshot(roblox_folder) == before


@pytest.mark.spec("S-24", 9)
def test_a_failed_move_puts_back_what_moved(
    roblox_folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = CachePlatform(roblox_folder.parent)
    ledger = scar.Ledger(tmp_path / "changes.json")
    before = snapshot(roblox_folder)
    real_move = sprout.shutil.move

    def locked_database(source: Path, target: Path) -> object:
        if Path(source).name == "rbx-storage.db" and Path(target).parent.name != "Roblox":
            raise PermissionError(13, "The file is in use")
        return real_move(source, target)

    monkeypatch.setattr(sprout.shutil, "move", locked_database)
    with pytest.raises(PermissionError):
        sprout.move_cache(platform, ledger, NOW, root=tmp_path / "backup")  # type: ignore[arg-type]
    assert snapshot(roblox_folder) == before
    assert [e.state for e in ledger.entries()] == ["removed"]
    assert not (tmp_path / "backup").exists()


def test_sprout_reports_every_cache_outcome_in_activity(
    roblox_folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: Any
) -> None:
    platform = CachePlatform(roblox_folder.parent)
    ledger = scar.Ledger(tmp_path / "changes.json")
    from verdra.roots import gardener  # noqa: PLC0415

    status = gardener.RoutingStatusSource(FakeClock().schedule)
    made = sprout.Sprout(
        FakeSettings(),  # type: ignore[arg-type]
        status,
        platform=platform,  # type: ignore[arg-type]
        ledger=lambda: ledger,
        clock=lambda: NOW,
    )
    monkeypatch.setattr(sprout, "cache_backup_root", lambda: tmp_path / "backup")
    caplog.set_level("INFO", logger="verdra.trunk.branches.sprout")
    platform.processes = humus.RobloxProcesses(studio=(42,))
    assert made.clear_cache() is None  # Studio runs: nothing moves (the interface says so)
    platform.processes = humus.RobloxProcesses()
    moved = made.clear_cache()
    assert moved is not None
    assert caplog.messages[-1] == (
        "Moved Roblox's saved assets (rbx-storage.db-shm, rbx-storage.db-wal, rbx-storage.db, "
        f"rbx-storage) to {moved.backup}. Reset everything puts them back."
    )
    (roblox_folder / "rbx-storage.db").write_bytes(b"new")
    monkeypatch.setattr(
        sprout.shutil, "move", lambda *_a: (_ for _ in ()).throw(OSError(5, "Access is denied"))
    )
    assert made.clear_cache() is None
    assert caplog.messages[-1] == (
        "Verdra couldn't move Roblox's saved assets aside (Access is denied). Nothing was changed."
    )
    made.deleteLater()
    status.deleteLater()


# --- Only the newest backup is kept (owner, 7 October 2026) ------------------------------------


def refill(roblox: Path, text: bytes) -> None:
    """Roblox makes its cache again, as during a join."""
    (roblox / "rbx-storage").mkdir(exist_ok=True)
    (roblox / "rbx-storage" / "n.bin").write_bytes(text)
    for name in ("rbx-storage.db", "rbx-storage.db-shm", "rbx-storage.db-wal"):
        (roblox / name).write_bytes(text + name.encode())


def cache_sprout(
    platform: CachePlatform, ledger: scar.Ledger, monkeypatch: pytest.MonkeyPatch, root: Path
) -> tuple[sprout.Sprout, Any]:
    from verdra.roots import gardener  # noqa: PLC0415

    status = gardener.RoutingStatusSource(FakeClock().schedule)
    times = iter(NOW + timedelta(minutes=minute) for minute in range(100))
    made = sprout.Sprout(
        FakeSettings(),  # type: ignore[arg-type]
        status,
        platform=platform,  # type: ignore[arg-type]
        ledger=lambda: ledger,
        clock=lambda: next(times),
    )
    monkeypatch.setattr(sprout, "cache_backup_root", lambda: root)
    return made, status


@pytest.mark.spec("S-24", 10)
def test_each_apply_now_keeps_only_the_newest_backup(
    roblox_folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: Any
) -> None:
    platform = CachePlatform(roblox_folder.parent)
    ledger = scar.Ledger(tmp_path / "changes.json")
    root = tmp_path / "backup"
    made, status = cache_sprout(platform, ledger, monkeypatch, root)
    caplog.set_level("INFO", logger="verdra.trunk.branches.sprout")
    first = made.clear_cache()
    assert first is not None
    refill(roblox_folder, b"second")
    second = made.clear_cache()
    assert second is not None
    assert sorted(p.name for p in root.iterdir()) == [second.backup.name]  # the older one is gone
    old, new = ledger.entries()
    assert (old.state, old.details["deleted"]) == ("removed", True)  # recorded in the ledger
    assert new.state == "done"
    assert (
        caplog.messages[-1]
        # The source text; the catalogue's singular form, loaded by the app, reads "1 backup".
        == "Deleted 1 backups of Roblox's saved assets ("
        + (QLocale().formattedDataSize(sum(len(n.encode()) for n in W06_NAMES if is_cache(n))))
        + ")."
    )
    made.deleteLater()
    status.deleteLater()


@pytest.mark.spec("S-24", 10)
def test_reset_everything_restores_the_newest_backup(
    roblox_folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = CachePlatform(roblox_folder.parent)
    ledger_file = tmp_path / "changes.json"
    ledger = scar.Ledger(ledger_file)
    made, status = cache_sprout(platform, ledger, monkeypatch, tmp_path / "backup")
    assert made.clear_cache() is not None
    refill(roblox_folder, b"newest")
    newest = snapshot(roblox_folder)
    assert made.clear_cache() is not None
    summary = fallow.reset(
        ledger_file, vault=husk.Husk(MemoryKeyring()), cert_file=tmp_path / "ca.crt"
    )
    assert summary.removed == 1 and summary.failed == []
    assert snapshot(roblox_folder) == newest  # the newest backup, byte- and date-identical
    assert not (tmp_path / "backup").exists()
    made.deleteLater()
    status.deleteLater()


@pytest.mark.spec("S-24", 10)
def test_a_crash_while_deleting_old_backups_loses_nothing_reset_needs(
    roblox_folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = CachePlatform(roblox_folder.parent)
    ledger_file = tmp_path / "changes.json"
    ledger = scar.Ledger(ledger_file)
    root = tmp_path / "backup"
    made, status = cache_sprout(platform, ledger, monkeypatch, root)
    assert made.clear_cache() is not None
    refill(roblox_folder, b"newest")
    newest = snapshot(roblox_folder)
    real_rmtree = sprout.shutil.rmtree

    def crash_halfway(folder: Path, *_args: object, **_kwargs: object) -> None:
        next(Path(folder).rglob("*.db")).unlink()  # part of the old backup is gone ...
        raise KeyboardInterrupt  # ... and the process dies here

    monkeypatch.setattr(sprout.shutil, "rmtree", crash_halfway)
    with pytest.raises(KeyboardInterrupt):
        made.clear_cache()
    monkeypatch.setattr(sprout.shutil, "rmtree", real_rmtree)
    # The old backup's entry was marked removed before deleting started: Reset never touches the
    # half-deleted folder, and puts the newest backup back.
    assert [e.state for e in scar.Ledger(ledger_file).entries()] == ["removed", "done"]
    assert len(list(root.iterdir())) == 2  # the half-deleted folder is still there
    summary = fallow.reset(
        ledger_file, vault=husk.Husk(MemoryKeyring()), cert_file=tmp_path / "ca.crt"
    )
    assert summary.failed == []
    assert snapshot(roblox_folder) == newest
    # The leftover goes with the next deletion (here "Delete backups").
    made.delete_backups()
    assert not root.exists() or list(root.iterdir()) == []
    made.deleteLater()
    status.deleteLater()


@pytest.mark.spec("S-24", 10)
def test_a_backup_reset_still_needs_is_never_deleted(
    roblox_folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A move a crash interrupted ("pending") keeps its backup: Reset puts those files back."""
    platform = CachePlatform(roblox_folder.parent)
    ledger = scar.Ledger(tmp_path / "changes.json")
    root = tmp_path / "backup"
    made, status = cache_sprout(platform, ledger, monkeypatch, root)
    interrupted = root / "interrupted"
    (interrupted / "rbx-storage").mkdir(parents=True)
    entry = ledger.begin(
        "roblox_cache_moved", str(roblox_folder), {"backup": str(interrupted), "items": []}
    )
    moved = made.clear_cache()
    assert moved is not None
    assert sorted(p.name for p in root.iterdir()) == sorted([moved.backup.name, "interrupted"])
    assert ledger.entries()[0].id == entry.id and ledger.entries()[0].state == "pending"
    made.deleteLater()
    status.deleteLater()


@pytest.mark.spec("S-24", 10)
def test_delete_backups_removes_them_all_and_reset_then_has_none_to_restore(
    roblox_folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = CachePlatform(roblox_folder.parent)
    ledger_file = tmp_path / "changes.json"
    ledger = scar.Ledger(ledger_file)
    root = tmp_path / "backup"
    made, status = cache_sprout(platform, ledger, monkeypatch, root)
    assert made.clear_cache() is not None
    assert sprout.backups_size(root) > 0
    changed: list[bool] = []
    made.backups_changed.connect(lambda: changed.append(True))
    made.delete_backups()
    assert sprout.backups_size(root) == 0
    assert changed == [True]
    assert [e.state for e in scar.Ledger(ledger_file).entries()] == ["removed"]
    summary = fallow.reset(
        ledger_file, vault=husk.Husk(MemoryKeyring()), cert_file=tmp_path / "ca.crt"
    )
    assert summary.removed == 0 and summary.failed == []
    made.deleteLater()
    status.deleteLater()
