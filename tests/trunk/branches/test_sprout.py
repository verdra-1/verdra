# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-12: choosing the client, the certificate, link handling, launching (sprout)."""

from __future__ import annotations

import ast
import re
import stat
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

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

    def __init__(self, clients: list[humus.RobloxClient]) -> None:
        super().__init__(FakeHandler())
        self.clients = clients
        self.launched: list[tuple[str | None, int]] = []

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
def routed(
    installed: tuple[humus.RobloxClient, Path, Path], tmp_path: Path, qapp: Any
) -> Iterator[tuple[sprout.Sprout, RoutingPlatform, scar.Ledger]]:
    from tests.roots.test_routing_status import FakeClock  # noqa: PLC0415
    from verdra.roots import gardener  # noqa: PLC0415

    found, _old, _studio = installed
    platform = RoutingPlatform([found])
    ledger = scar.Ledger(tmp_path / "changes.json")
    vault = husk.Husk(MemoryKeyring(), file_fallback=False, key_file=tmp_path / "ca.key")
    status = gardener.RoutingStatusSource(FakeClock().schedule)
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
    assert made.launch(link) is None
    assert platform.launched == [(link, made.router.port)]
    assert made.status._launch is not None  # noqa: SLF001 - the S-14 launch window is open


def test_a_refused_client_changes_nothing_and_says_why(tmp_path: Path, qapp: Any) -> None:
    from tests.roots.test_routing_status import FakeClock  # noqa: PLC0415
    from verdra.roots import gardener  # noqa: PLC0415

    platform = RoutingPlatform([client(scope="flatpak", found_by="package", unconfirmed=("L-02",))])
    ledger = scar.Ledger(tmp_path / "changes.json")
    status = gardener.RoutingStatusSource(FakeClock().schedule)
    made = sprout.Sprout(FakeSettings(), status, platform=platform, ledger=lambda: ledger)  # type: ignore[arg-type]
    said: list[str] = []
    made.refused.connect(said.append)
    refused = made.launch("roblox-player:1")
    assert refused == sprout.unconfirmed("L-02")
    assert said == [refused.text]  # type: ignore[union-attr]
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
