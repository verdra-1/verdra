# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Find Roblox, start it with the proxy variables, register the roblox-player: handler.

Spec S-12 on Windows, built on the facts confirmed on the maintainer's PC (docs/platforms/
windows.md, 2026-10-04):

- W-01: per-user installs keep version folders in `%LOCALAPPDATA%\\Roblox\\Versions`. Roblox
  Studio keeps its version folders there too, so a **Player** version folder is one holding
  `RobloxPlayerBeta.exe`; a folder holding `RobloxStudioBeta.exe` is never used, never changed.
  Several version folders can exist side by side.
- W-03: `HKCU\\Software\\Classes\\roblox-player\\shell\\open\\command` holds the handler command
  and a `version` value naming the current version folder. The current Player folder is the one
  that value names; failing that, the newest Player folder (by its program's date).
- W-05: each version folder holds `ssl\\cacert.pem`, not read-only.
- W-02: all-users installs (`Program Files` and `Program Files (x86)`, handler under HKLM) are
  found, but their trust files can only be changed with administrator rights, which per-app
  routing never uses (S-12 rule 3), so such a client carries the unconfirmed fact `W-02` and
  routing refuses it with a plain message.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Literal, Protocol

import psutil

from verdra.soil import humus, terrain

#: W-01: the program that marks a Player version folder.
PLAYER_EXECUTABLE: Final = "RobloxPlayerBeta.exe"
#: W-01: the program that marks a Studio version folder; such a folder is never touched.
STUDIO_EXECUTABLE: Final = "RobloxStudioBeta.exe"
#: W-05: the trust file inside each version folder.
TRUST_FILE: Final = ("ssl", "cacert.pem")
#: W-03: the handler command key and the value naming the current version folder.
HANDLER_COMMAND_KEY: Final = terrain.WINDOWS_URL_HANDLER_KEY + r"\shell\open\command"
HANDLER_VERSION_VALUE: Final = "version"
#: W-03: what a URL scheme key needs so Windows offers it as a link handler.
URL_PROTOCOL_VALUE: Final = "URL Protocol"
#: The `(default)` value of a registry key.
DEFAULT: Final = ""

Hive = Literal["HKCU", "HKLM"]


class Registry(Protocol):
    """The few registry operations S-12 needs, on string values only."""

    def get(self, hive: Hive, key: str, name: str) -> str | None:
        """Return a value, or None if the key or the value doesn't exist."""
        ...

    def exists(self, hive: Hive, key: str) -> bool:
        """Return whether a key exists."""
        ...

    def set(self, hive: Hive, key: str, name: str, value: str) -> None:
        """Set a value, creating the key and its parents if needed."""
        ...

    def delete_value(self, hive: Hive, key: str, name: str) -> None:
        """Delete a value; nothing happens if it doesn't exist."""
        ...

    def delete_key(self, hive: Hive, key: str) -> None:
        """Delete an empty key; nothing happens if it doesn't exist."""
        ...


def _winreg() -> Any:
    """Return the winreg module (Windows only; typed loosely so type checks pass elsewhere)."""
    import winreg  # noqa: PLC0415 - Windows only

    return winreg


class WindowsRegistry:
    """`Registry` on the real Windows registry (winreg)."""

    def _hive(self, hive: Hive) -> int:
        winreg = _winreg()
        return winreg.HKEY_CURRENT_USER if hive == "HKCU" else winreg.HKEY_LOCAL_MACHINE

    def get(self, hive: Hive, key: str, name: str) -> str | None:
        winreg = _winreg()
        try:
            with winreg.OpenKey(self._hive(hive), key) as handle:
                value, kind = winreg.QueryValueEx(handle, name)
        except OSError:
            return None
        return value if kind in {winreg.REG_SZ, winreg.REG_EXPAND_SZ} else None

    def exists(self, hive: Hive, key: str) -> bool:
        winreg = _winreg()
        try:
            winreg.OpenKey(self._hive(hive), key).Close()
        except OSError:
            return False
        return True

    def set(self, hive: Hive, key: str, name: str, value: str) -> None:
        winreg = _winreg()
        with winreg.CreateKeyEx(self._hive(hive), key, 0, winreg.KEY_SET_VALUE) as handle:
            winreg.SetValueEx(handle, name, 0, winreg.REG_SZ, value)

    def delete_value(self, hive: Hive, key: str, name: str) -> None:
        winreg = _winreg()
        try:
            with winreg.OpenKey(self._hive(hive), key, 0, winreg.KEY_SET_VALUE) as handle:
                winreg.DeleteValue(handle, name)
        except FileNotFoundError:
            return

    def delete_key(self, hive: Hive, key: str) -> None:
        winreg = _winreg()
        try:
            winreg.DeleteKey(self._hive(hive), key)
        except FileNotFoundError:
            return


def player_folders(versions: Path) -> list[Path]:
    """Return the Player version folders in a Versions folder (W-01), sorted by name.

    A folder holding Studio's program is left out even if it also holds the Player's: Verdra
    never touches a Studio folder.
    """
    try:
        children = [child for child in versions.iterdir() if child.is_dir()]
    except OSError:
        return []
    return sorted(filter(is_player_folder, children), key=lambda child: child.name.lower())


def is_player_folder(folder: Path) -> bool:
    """Return whether `folder` is a Player version folder (W-01), never a Studio one."""
    return (folder / PLAYER_EXECUTABLE).is_file() and not (folder / STUDIO_EXECUTABLE).exists()


def current_player(
    players: Sequence[Path], handler_version: str | None
) -> tuple[Path, humus.FoundBy] | None:
    """Return the current Player folder and how it was found (W-03), or None if there's none.

    The handler's `version` value is a folder name; it counts only if it names one of the
    Player folders exactly (case aside), never a path.
    """
    if not players:
        return None
    if handler_version:
        wanted = handler_version.strip().lower()
        for folder in players:
            if folder.name.lower() == wanted:
                return folder, "handler"

    def age(folder: Path) -> tuple[int, str]:
        try:
            modified = (folder / PLAYER_EXECUTABLE).stat().st_mtime_ns
        except OSError:
            modified = 0
        return modified, folder.name.lower()

    return max(players, key=age), "newest"


def trust_files(players: Iterable[Path]) -> tuple[Path, ...]:
    """Return the trust file of each Player folder that has one (W-05)."""
    return tuple(path for folder in players if (path := folder.joinpath(*TRUST_FILE)).is_file())


def find_clients(
    local_appdata: Path | None, program_folders: Sequence[Path], registry: Registry
) -> list[humus.RobloxClient]:
    """Return the installed Roblox Players: the per-user one first, then all-users ones."""
    found: list[humus.RobloxClient] = []
    places: list[tuple[humus.Scope, Path, Hive]] = []
    if local_appdata is not None:
        places.append(("user", local_appdata / "Roblox" / "Versions", "HKCU"))
    places.extend(
        ("all_users", folder / "Roblox" / "Versions", "HKLM") for folder in program_folders
    )
    seen: set[str] = set()
    for scope, versions, hive in places:
        key = os.path.normcase(str(versions))
        if key in seen:
            continue
        seen.add(key)
        players = player_folders(versions)
        current = current_player(
            players, registry.get(hive, HANDLER_COMMAND_KEY, HANDLER_VERSION_VALUE)
        )
        if current is None:
            continue
        folder, found_by = current
        found.append(
            humus.RobloxClient(
                scope=scope,
                executable=folder / PLAYER_EXECUTABLE,
                found_by=found_by,
                trust_files=trust_files(players),
                install_folders=(versions,),
                unconfirmed=() if scope == "user" else ("W-02",),
            )
        )
    return found


def program_folders(environment: Mapping[str, str]) -> list[Path]:
    """Return the all-users program folders to look in (W-02), each once."""
    folders: list[Path] = []
    for name in ("ProgramFiles", "ProgramFiles(x86)"):
        value = next((v for k, v in environment.items() if k.upper() == name.upper()), "")
        if value and Path(value) not in folders:
            folders.append(Path(value))
    return folders


def local_appdata(environment: Mapping[str, str]) -> Path | None:
    """Return `%LOCALAPPDATA%`, or None if it isn't set."""
    value = next((v for k, v in environment.items() if k.upper() == "LOCALAPPDATA"), "")
    return Path(value) if value else None


def launch(
    client: humus.RobloxClient,
    link: str | None,
    proxy_port: int,
    environment: Mapping[str, str],
    spawn: humus.Spawn = subprocess.Popen,
) -> int:
    """Start the Player directly with the proxy variables; return its process ID (S-12).

    The link, if any, is passed on as the one argument, unchanged (rule 1), as Roblox's own
    handler command does (`"<folder>\\RobloxPlayerBeta.exe" %1`, W-03).
    """
    arguments = [str(client.executable)] + ([link] if link else [])
    process = spawn(
        arguments,
        env=humus.proxy_environment(environment, proxy_port),
        cwd=str(client.executable.parent),
        close_fds=True,
    )
    return int(process.pid)


def hosts_file(environment: Mapping[str, str]) -> Path:
    """Return the hosts file (W-10: readable as a normal user)."""
    root = next((v for k, v in environment.items() if k.upper() == "SYSTEMROOT"), r"C:\Windows")
    return Path(root) / "System32" / "drivers" / "etc" / "hosts"


def _me() -> str | None:
    try:
        return psutil.Process().username()
    except psutil.Error:
        return None


def running_players(
    client: humus.RobloxClient,
    processes: Callable[..., Iterable[Any]] = psutil.process_iter,
    me: Callable[[], str | None] = _me,
) -> list[humus.RunningClient]:
    """Return this user's running Players of `client` and their proxy variables (S-15).

    A Player is a `RobloxPlayerBeta.exe` inside a version folder of the client's install
    folders (W-01). Only the user's own processes are looked at, read-only (S-15 rule 2).
    Whether another process's environment can be read is W-09, confirmed in stage 2; when it
    can't, the process is listed with `proxies` None and the reason.
    """
    folders = {os.path.normcase(str(folder)) for folder in client.install_folders}
    user = me()
    found: list[humus.RunningClient] = []
    for process in processes(["pid", "name", "exe", "username"]):
        info = process.info
        exe = info.get("exe")
        if not exe or info.get("username") != user:
            continue
        path = Path(exe)
        if path.name.lower() != PLAYER_EXECUTABLE.lower():
            continue
        if os.path.normcase(str(path.parent.parent)) not in folders:
            continue
        try:
            environment = process.environ()
        except (psutil.Error, OSError) as error:
            found.append(humus.RunningClient(info["pid"], path.name, None, type(error).__name__))
            continue
        proxies = {
            key.upper(): value
            for key, value in environment.items()
            if key.upper() in humus.PROXY_VARIABLES
        }
        found.append(humus.RunningClient(info["pid"], path.name, proxies))
    return found


def quote(argument: str) -> str:
    """Quote one argument of a Windows command line (the handler command)."""
    return '"' + argument.replace('"', '\\"') + '"'


def command_line(command: Sequence[str]) -> str:
    """Return the handler command line: each argument quoted, then the link as `"%1"`."""
    return " ".join(quote(part) for part in command) + ' "%1"'


class WindowsLinkHandler:
    """The per-user `roblox-player:` handler in HKCU (W-03).

    Verdra changes only the command's `(default)` value; Roblox's `version` value and the other
    values stay. If the user has no per-user handler (an all-users install), the scheme key is
    created with what Windows needs and deleted again on restore.
    """

    def __init__(self, registry: Registry, root: str = terrain.WINDOWS_URL_HANDLER_KEY) -> None:
        self.registry = registry
        self.root = root
        self.command_key = root + r"\shell\open\command"

    def _created_keys(self) -> list[str]:
        """Return the keys `register` would create, innermost first."""
        keys = [self.command_key, self.root + r"\shell\open", self.root + r"\shell", self.root]
        return [key for key in keys if not self.registry.exists("HKCU", key)]

    def snapshot(self) -> dict[str, Any]:
        """Return the current command and which keys don't exist yet."""
        return {
            "command": self.registry.get("HKCU", self.command_key, DEFAULT),
            "url_protocol": self.registry.get("HKCU", self.root, URL_PROTOCOL_VALUE),
            "created_keys": self._created_keys(),
        }

    def register(self, command: Sequence[str]) -> None:
        """Make Verdra's command the handler (the link arrives as `%1`)."""
        if self.registry.get("HKCU", self.root, URL_PROTOCOL_VALUE) is None:
            self.registry.set("HKCU", self.root, URL_PROTOCOL_VALUE, "")
        self.registry.set("HKCU", self.command_key, DEFAULT, command_line(command))

    def registered(self, command: Sequence[str]) -> bool:
        """Return whether Verdra's command is still the handler."""
        return self.registry.get("HKCU", self.command_key, DEFAULT) == command_line(command)

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        """Put the recorded command back, or remove what `register` created."""
        command = snapshot.get("command")
        if command is None:
            self.registry.delete_value("HKCU", self.command_key, DEFAULT)
        else:
            self.registry.set("HKCU", self.command_key, DEFAULT, str(command))
        if snapshot.get("url_protocol") is None:
            self.registry.delete_value("HKCU", self.root, URL_PROTOCOL_VALUE)
        for key in snapshot.get("created_keys", []):
            self.registry.delete_key("HKCU", str(key))
