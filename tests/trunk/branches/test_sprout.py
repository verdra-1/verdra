# SPDX-FileCopyrightText: 2026 The Verdra Authors
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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pytestqt.qtbot import QtBot

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
    sober = client(scope="flatpak", found_by="package", unconfirmed=("L-02",))
    shared = client(scope="all_users", unconfirmed=("W-02",))
    assert sprout.choose([sober]) == sprout.unconfirmed("L-02")
    assert sprout.choose([sober]).message_id == "M-LAUNCH-04"  # type: ignore[union-attr]
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
    assert facts == {"L-02", "W-02"}
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
    vault = husk.Husk(MemoryKeyring(), file_fallback=False, key_file=tmp_path / "ca.key")
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
    vault = husk.Husk(MemoryKeyring(), file_fallback=False, key_file=tmp_path / "ca.key")
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
    vault = husk.Husk(MemoryKeyring(), file_fallback=False, key_file=tmp_path / "ca.key")
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
    vault = husk.Husk(MemoryKeyring(), file_fallback=False, key_file=tmp_path / "ca.key")
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

    platform = RoutingPlatform([client(scope="flatpak", found_by="package", unconfirmed=("L-02",))])
    ledger = scar.Ledger(tmp_path / "changes.json")
    status = gardener.RoutingStatusSource(FakeClock().schedule)
    made = sprout.Sprout(FakeSettings(), status, platform=platform, ledger=lambda: ledger)  # type: ignore[arg-type]
    said: list[str] = []
    made.refused.connect(said.append)
    made.launch("roblox-player:1")
    assert said == [sprout.unconfirmed("L-02").text]
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
    vault = husk.Husk(MemoryKeyring(), file_fallback=False, key_file=tmp_path / "other.key")
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
