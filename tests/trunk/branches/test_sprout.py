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
    sprout.add_certificate(found, vault, ledger, NOW)
    assert len(found.trust_files) == 2
    for path in found.trust_files:
        assert terrain.CA_BEGIN_MARKER.encode() in path.read_bytes()
    assert studio.read_bytes() == PEM
    assert stat.S_IMODE(old.stat().st_mode) == stat.S_IMODE(stat.S_IREAD)
    assert [e.kind for e in ledger.entries()] == ["ca_roblox_bundle"] * 2
    # Reset gives every trust file back byte for byte, read-only flag included.
    summary = fallow.reset(ledger.path, vault=vault, cert_file=tmp_path / "ca.crt")
    assert summary.failed == []
    for path in found.trust_files:
        assert path.read_bytes() == PEM
    assert stat.S_IMODE(old.stat().st_mode) == stat.S_IMODE(stat.S_IREAD)


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
