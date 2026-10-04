# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-12 on Windows: finding the Player, launching it, the roblox-player: handler.

Built on docs/platforms/windows.md (maintainer's PC, 2026-10-04). Discovery and the handler run
on every system against a fake registry and fixture folders; the handler also runs against the
real registry on the Windows runner, under a throwaway key.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from verdra.soil import humus, terrain
from verdra.soil.meadow import launcher
from verdra.soil.meadow.launcher import Hive


class FakeRegistry:
    """`launcher.Registry` in memory: {(hive, key): {name: value}}."""

    def __init__(self, keys: dict[tuple[Hive, str], dict[str, str]] | None = None) -> None:
        # Like a real profile, where Software\Classes always exists.
        self.keys: dict[tuple[Hive, str], dict[str, str]] = {
            ("HKCU", "software"): {},
            ("HKCU", "software\\classes"): {},
        }
        for (hive, key), values in (keys or {}).items():
            self.set(hive, key, "", "")
            self.keys[hive, key.lower()] = dict(values)

    def get(self, hive: Hive, key: str, name: str) -> str | None:
        return self.keys.get((hive, key.lower()), {}).get(name)

    def exists(self, hive: Hive, key: str) -> bool:
        return (hive, key.lower()) in self.keys

    def set(self, hive: Hive, key: str, name: str, value: str) -> None:
        parts = key.split("\\")
        for end in range(1, len(parts) + 1):
            self.keys.setdefault((hive, "\\".join(parts[:end]).lower()), {})
        self.keys[hive, key.lower()][name] = value

    def delete_value(self, hive: Hive, key: str, name: str) -> None:
        self.keys.get((hive, key.lower()), {}).pop(name, None)

    def delete_key(self, hive: Hive, key: str) -> None:
        children = [k for h, k in self.keys if h == hive and k.startswith(key.lower() + "\\")]
        assert not children, f"{key} still has subkeys"
        self.keys.pop((hive, key.lower()), None)


def version(
    versions: Path, name: str, *, program: str = launcher.PLAYER_EXECUTABLE, age: int = 0
) -> Path:
    """Make a version folder with a program and a trust file; `age` seconds old."""
    folder = versions / name
    (folder / "ssl").mkdir(parents=True)
    (folder / "ssl" / "cacert.pem").write_bytes(b"-----BEGIN CERTIFICATE-----\n")
    exe = folder / program
    exe.write_bytes(b"MZ")
    stamp = 1_800_000_000 - age
    os.utime(exe, (stamp, stamp))
    return folder


def handler(version_name: str) -> dict[tuple[Hive, str], dict[str, str]]:
    return {("HKCU", launcher.HANDLER_COMMAND_KEY): {"version": version_name, "": '"x" %1'}}


def test_the_current_player_is_the_one_the_handler_names(tmp_path: Path) -> None:
    versions = tmp_path / "Roblox" / "Versions"
    named = version(versions, "version-aaaa", age=500)
    version(versions, "version-bbbb", age=10)  # newer, but not the one the handler names
    [client] = launcher.find_clients(tmp_path, [], FakeRegistry(handler("version-aaaa")))
    assert client.executable == named / launcher.PLAYER_EXECUTABLE
    assert client.found_by == "handler"
    assert client.scope == "user"
    assert client.unconfirmed == ()


def test_without_a_usable_handler_value_the_newest_player_is_used(tmp_path: Path) -> None:
    versions = tmp_path / "Roblox" / "Versions"
    version(versions, "version-old", age=500)
    newest = version(versions, "version-new", age=10)
    for registry in (
        FakeRegistry(),
        FakeRegistry(handler("version-gone")),
        FakeRegistry(handler(r"..\version-old")),  # a path, not a folder name
    ):
        [client] = launcher.find_clients(tmp_path, [], registry)
        assert client.executable == newest / launcher.PLAYER_EXECUTABLE
        assert client.found_by == "newest"


def test_studio_folders_are_ignored_and_never_get_the_certificate(tmp_path: Path) -> None:
    versions = tmp_path / "Roblox" / "Versions"
    player = version(versions, "version-player", age=500)
    studio = version(versions, "version-studio", program=launcher.STUDIO_EXECUTABLE, age=1)
    both = version(versions, "version-both", age=1)
    (both / launcher.STUDIO_EXECUTABLE).write_bytes(b"MZ")
    # The handler naming Studio's folder doesn't make it a Player folder.
    [client] = launcher.find_clients(tmp_path, [], FakeRegistry(handler("version-studio")))
    assert client.executable == player / launcher.PLAYER_EXECUTABLE
    assert client.trust_files == (player / "ssl" / "cacert.pem",)
    assert launcher.player_folders(versions) == [player]
    assert not launcher.is_player_folder(studio)
    assert not launcher.is_player_folder(both)


def test_a_studio_only_install_is_no_roblox(tmp_path: Path) -> None:
    versions = tmp_path / "Roblox" / "Versions"
    version(versions, "version-studio", program=launcher.STUDIO_EXECUTABLE)
    assert launcher.find_clients(tmp_path, [], FakeRegistry()) == []
    assert launcher.find_clients(None, [], FakeRegistry()) == []


def test_every_player_folder_gets_the_certificate(tmp_path: Path) -> None:
    versions = tmp_path / "Roblox" / "Versions"
    first = version(versions, "version-1", age=50)
    second = version(versions, "version-2", age=5)
    without = version(versions, "version-3", age=1)
    (without / "ssl" / "cacert.pem").unlink()
    [client] = launcher.find_clients(tmp_path, [], FakeRegistry())
    assert client.trust_files == (first / "ssl" / "cacert.pem", second / "ssl" / "cacert.pem")
    assert client.install_folders == (versions,)


def test_all_users_installs_are_found_but_marked_unconfirmed(tmp_path: Path) -> None:
    programs = tmp_path / "Program Files"
    shared = version(programs / "Roblox" / "Versions", "version-shared")
    registry = FakeRegistry({("HKLM", launcher.HANDLER_COMMAND_KEY): {"version": "version-shared"}})
    [client] = launcher.find_clients(tmp_path / "nobody", [programs, programs], registry)
    assert client.scope == "all_users"
    assert client.found_by == "handler"
    assert client.executable == shared / launcher.PLAYER_EXECUTABLE
    assert client.unconfirmed == ("W-02",)


def test_the_per_user_player_comes_first(tmp_path: Path) -> None:
    version(tmp_path / "Roblox" / "Versions", "version-mine")
    version(tmp_path / "Program Files" / "Roblox" / "Versions", "version-shared")
    clients = launcher.find_clients(tmp_path, [tmp_path / "Program Files"], FakeRegistry())
    assert [c.scope for c in clients] == ["user", "all_users"]


def test_folders_come_from_the_environment_in_any_spelling() -> None:
    environment = {
        "PROGRAMFILES": r"C:\Program Files",
        "programfiles(x86)": r"C:\Program Files (x86)",
    }
    assert launcher.program_folders(environment) == [
        Path(r"C:\Program Files"),
        Path(r"C:\Program Files (x86)"),
    ]
    assert launcher.program_folders({"ProgramFiles": "X", "ProgramFiles(x86)": "X"}) == [Path("X")]
    assert launcher.local_appdata({"LocalAppData": "L"}) == Path("L")
    assert launcher.local_appdata({}) is None


class Recorder:
    """A spawn that records its call and returns a fake process."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, arguments: list[str], **options: Any) -> Any:
        self.calls.append((arguments, options))
        return type("Process", (), {"pid": 4321})()


@pytest.mark.spec("S-12", 5)
def test_launching_adds_only_the_proxy_variables(tmp_path: Path) -> None:
    """S-12 test 5 (fake launcher)."""
    client = humus.RobloxClient(
        scope="user", executable=tmp_path / "v" / launcher.PLAYER_EXECUTABLE, found_by="handler"
    )
    environment = {"PATH": r"C:\Windows", "LANG": "en", "https_proxy": "http://elsewhere:1"}
    spawn = Recorder()
    link = "roblox-player:1+launchmode:play+gameinfo:abc+placelauncherurl:https%3A%2F%2Fx%3Fa%3D1"
    assert launcher.launch(client, link, 49443, environment, spawn) == 4321
    [(arguments, options)] = spawn.calls
    assert arguments == [str(client.executable), link]
    assert options["cwd"] == str(client.executable.parent)
    assert options["env"] == {
        "PATH": r"C:\Windows",
        "LANG": "en",
        "HTTPS_PROXY": "http://127.0.0.1:49443",
        "HTTP_PROXY": "http://127.0.0.1:49443",
    }
    launcher.launch(client, None, 50000, {}, spawn)
    assert spawn.calls[1][0] == [str(client.executable)]


@pytest.mark.spec("S-12", 3)
def test_the_handler_is_registered_and_restored_exactly() -> None:
    """S-12 test 3 on a fake registry: Roblox's own values stay, its command comes back."""
    roblox = '"C:\\R\\version-a\\RobloxPlayerBeta.exe" %1'
    registry = FakeRegistry(
        {
            ("HKCU", terrain.WINDOWS_URL_HANDLER_KEY): {
                "": "URL: Roblox Protocol",
                "URL Protocol": "",
            },
            ("HKCU", launcher.HANDLER_COMMAND_KEY): {"": roblox, "version": "version-a"},
        }
    )
    before = {key: dict(values) for key, values in registry.keys.items()}
    handler = launcher.WindowsLinkHandler(registry)
    snapshot = handler.snapshot()
    assert snapshot == {"command": roblox, "url_protocol": "", "created_keys": []}
    handler.register(["C:\\Verdra\\verdra.exe"])
    assert registry.get("HKCU", launcher.HANDLER_COMMAND_KEY, "") == '"C:\\Verdra\\verdra.exe" "%1"'
    assert registry.get("HKCU", launcher.HANDLER_COMMAND_KEY, "version") == "version-a"
    handler.restore(snapshot)
    assert registry.keys == before


def test_without_a_per_user_handler_restore_removes_what_was_created() -> None:
    registry = FakeRegistry()
    handler = launcher.WindowsLinkHandler(registry)
    snapshot = handler.snapshot()
    handler.register(["verdra.exe", "--flag"])
    assert registry.get("HKCU", terrain.WINDOWS_URL_HANDLER_KEY, "URL Protocol") == ""
    assert registry.get("HKCU", launcher.HANDLER_COMMAND_KEY, "") == '"verdra.exe" "--flag" "%1"'
    handler.restore(snapshot)
    assert registry.keys == FakeRegistry().keys


@pytest.fixture
def test_key() -> Iterator[str]:
    """A throwaway scheme key under HKCU\\Software, removed afterwards."""
    root = rf"Software\VerdraTest-{uuid.uuid4().hex}"
    yield root
    real = launcher.WindowsRegistry()
    for base in (root, root + "-new"):
        for key in (base + r"\shell\open\command", base + r"\shell\open", base + r"\shell", base):
            real.delete_key("HKCU", key)


@pytest.mark.spec("S-12", 3)
@pytest.mark.skipif(sys.platform != "win32", reason="the real registry is Windows only")
def test_the_handler_round_trip_on_the_real_registry(test_key: str) -> None:
    """S-12 test 3 on the Windows runner: a test key stands in for roblox-player."""
    real = launcher.WindowsRegistry()
    real.set("HKCU", test_key, "URL Protocol", "")
    real.set("HKCU", test_key + r"\shell\open\command", "", '"C:\\R\\RobloxPlayerBeta.exe" %1')
    real.set("HKCU", test_key + r"\shell\open\command", "version", "version-a")
    handler = launcher.WindowsLinkHandler(real, root=test_key)
    snapshot = handler.snapshot()
    handler.register([r"C:\Verdra\verdra.exe"])
    assert (
        real.get("HKCU", test_key + r"\shell\open\command", "") == '"C:\\Verdra\\verdra.exe" "%1"'
    )
    handler.restore(snapshot)
    assert (
        real.get("HKCU", test_key + r"\shell\open\command", "")
        == '"C:\\R\\RobloxPlayerBeta.exe" %1'
    )
    assert real.get("HKCU", test_key + r"\shell\open\command", "version") == "version-a"
    assert real.get("HKCU", test_key, "URL Protocol") == ""

    fresh = launcher.WindowsLinkHandler(real, root=test_key + "-new")
    created = fresh.snapshot()
    fresh.register([r"C:\Verdra\verdra.exe"])
    assert real.exists("HKCU", test_key + r"-new\shell\open\command")
    fresh.restore(created)
    assert not real.exists("HKCU", test_key + "-new")


def test_the_platform_answers_for_windows(tmp_path: Path) -> None:
    from verdra.soil import meadow  # noqa: PLC0415

    player = version(tmp_path, "version-p")
    studio = version(tmp_path, "version-s", program=launcher.STUDIO_EXECUTABLE)
    assert meadow.PLATFORM.trust_files_in(player) == [player / "ssl" / "cacert.pem"]
    assert meadow.PLATFORM.trust_files_in(studio) == []
    assert meadow.PLATFORM.trust_files_in(tmp_path / "version-new") == []


class FakeProcess:
    def __init__(self, pid: int, exe: str, username: str, environ: dict[str, str] | None) -> None:
        self.info = {"pid": pid, "name": Path(exe).name, "exe": exe, "username": username}
        self._environ = environ

    def environ(self) -> dict[str, str]:
        if self._environ is None:
            import psutil  # noqa: PLC0415

            raise psutil.AccessDenied(self.info["pid"])
        return self._environ


@pytest.mark.spec("S-15", 5)
def test_only_this_users_players_of_the_client_are_listed(tmp_path: Path) -> None:
    versions = tmp_path / "Roblox" / "Versions"
    player = str(versions / "version-a" / launcher.PLAYER_EXECUTABLE)
    client = humus.RobloxClient(
        scope="user", executable=Path(player), found_by="handler", install_folders=(versions,)
    )
    processes = [
        FakeProcess(1, player, "me", {"https_proxy": "http://127.0.0.1:8888", "PATH": "x"}),
        FakeProcess(2, player, "someone else", {"HTTPS_PROXY": "http://elsewhere:1"}),
        FakeProcess(
            3, str(versions / "version-a" / launcher.STUDIO_EXECUTABLE), "me", {"HTTPS_PROXY": "x"}
        ),
        FakeProcess(
            4, str(tmp_path / "Other" / "Versions" / "v" / launcher.PLAYER_EXECUTABLE), "me", {}
        ),
        FakeProcess(5, str(tmp_path / "proxy.exe"), "me", {"HTTPS_PROXY": "http://127.0.0.1:1"}),
        FakeProcess(6, player, "me", None),
    ]
    found = launcher.running_players(client, lambda _attrs: processes, lambda: "me")
    assert found == [
        humus.RunningClient(
            1, launcher.PLAYER_EXECUTABLE, {"HTTPS_PROXY": "http://127.0.0.1:8888"}
        ),
        humus.RunningClient(6, launcher.PLAYER_EXECUTABLE, None, "AccessDenied"),
    ]


def test_the_hosts_file_is_under_system_root() -> None:
    assert (
        launcher.hosts_file({"SystemRoot": r"D:\Win"})
        == Path(r"D:\Win") / "System32" / "drivers" / "etc" / "hosts"
    )


@pytest.mark.spec("S-12", 6)
@given(st.text(min_size=1).map(lambda rest: "roblox-player:" + rest))
def test_a_link_reaches_roblox_byte_for_byte(link: str) -> None:
    """S-12 rule 1: whatever the link holds, the Player receives exactly it."""
    spawn = Recorder()
    client = humus.RobloxClient(scope="user", executable=Path("R.exe"), found_by="handler")
    launcher.launch(client, link, 49443, {}, spawn)
    [(arguments, _options)] = spawn.calls
    assert arguments[1] == link
    assert arguments[1].encode("utf-8", "surrogatepass") == link.encode("utf-8", "surrogatepass")
