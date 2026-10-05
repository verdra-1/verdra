# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The Platform protocol every OS package implements; picks the right one at startup.

meadow (Windows), orchard (macOS) and tundra (Linux) each provide one `Platform`.
Nothing outside soil checks the operating system: it asks `current()` (Master plan 16.2). M0
holds the parts the app shell needs: which system Verdra runs on, whether Verdra supports it,
and whether the system asks for reduced motion (6.6). The routing, launching and keeper parts
of the protocol arrive with their specs (M1 onward): S-12 adds Roblox discovery, launching and
link handling.

Windows is the only platform until further notice. macOS is deferred until after 1.0 (decision
record 0014) and Linux is paused, planned later (decision record 0018): orchard and tundra answer
every job with `Unsupported`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from verdra.soil import terrain

if TYPE_CHECKING:
    import ssl

System = Literal["windows", "macos", "linux"]

_TIMEOUT_SECONDS = 1.0


#: Why a job isn't available. "deferred": the whole system waits for a later release (macOS,
#: decision record 0014). "paused": the system is paused until further notice, planned later
#: (Linux, decision record 0018). "unconfirmed": the job needs a platform fact that isn't
#: confirmed in docs/platforms/ yet (plan 16.4), so Verdra doesn't guess. More reasons arrive
#: with the specs that need them (S-51 instances).
Reason = Literal["deferred", "paused", "unconfirmed"]


@dataclass(frozen=True, slots=True)
class Unsupported:
    """A job this system can't do, with the reason, so the UI can explain it (Reference R1).

    It carries no text: the UI turns it into M-PLAT-01 ("<Feature> isn't available on
    <system>: <reason>.") from the message catalog.
    """

    system: System
    reason: Reason


#: How an installed Roblox client was installed: for this user or for all users (Windows).
Scope = Literal["user", "all_users"]
#: How the version to launch was chosen (spec S-12): the link handler's `version` value or the
#: newest Player version folder.
FoundBy = Literal["handler", "newest"]

#: Starts a process: `subprocess.Popen` in the app, a recorder in tests.
Spawn = Callable[..., Any]

#: The proxy variables a launched client gets (spec S-12, plan 10.1).
PROXY_VARIABLES = ("HTTPS_PROXY", "HTTP_PROXY")


@dataclass(frozen=True, slots=True)
class RobloxClient:
    """An installed Roblox client (spec S-12 discovery; facts in docs/platforms/<os>.md)."""

    scope: Scope
    #: The program `launch_roblox` starts.
    executable: Path
    found_by: FoundBy
    #: Where Verdra's CA block goes (spec S-10): one trust file per Player version folder.
    trust_files: tuple[Path, ...] = ()
    #: Folders where new versions appear; roots/gardener watches them (S-10 test 3).
    install_folders: tuple[Path, ...] = ()
    #: IDs of the platform facts routing this client needs that aren't confirmed yet. Routing
    #: refuses such a client with a plain message instead of guessing (plan 16.4).
    unconfirmed: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RunningClient:
    """A Roblox client of this user that is running (spec S-15, sign 1)."""

    pid: int
    name: str
    #: Its `HTTPS_PROXY` and `HTTP_PROXY` values (names in upper case); None when its
    #: environment couldn't be read (W-09, L-06), with the reason in `error`.
    proxies: dict[str, str] | None
    error: str = ""


def proxy_environment(environment: Mapping[str, str], port: int) -> dict[str, str]:
    """Return a copy of `environment` with Verdra's proxy variables (spec S-12, test 5).

    Any spelling of the two names already present (`https_proxy`, say) is replaced, so the
    client can't pick up another proxy; every other variable is kept as it is.
    """
    names = {name.upper() for name in PROXY_VARIABLES}
    copy = {key: value for key, value in environment.items() if key.upper() not in names}
    for name in PROXY_VARIABLES:
        copy[name] = f"http://{terrain.PROXY_HOST}:{port}"
    return copy


class LinkHandler(Protocol):
    """The system's handler for `roblox-player:` links (spec S-12, "Links from the browser")."""

    def snapshot(self) -> dict[str, Any]:
        """Return what `restore` needs to put the current handler back exactly (JSON values)."""
        ...

    def register(self, command: Sequence[str]) -> None:
        """Make `command` (the link appended) the handler."""
        ...

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        """Put back the handler `snapshot` recorded."""
        ...

    def registered(self, command: Sequence[str]) -> bool:
        """Return whether `command` is the handler now (Roblox's updater may have taken it back)."""
        ...


def verdra_command() -> list[str]:
    """Return the command that starts this Verdra; a link handler appends the link.

    A built Verdra is its own executable; from source it is the Python running it, with
    `pythonw.exe` preferred where it exists so no console window opens.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable]
    python = Path(sys.executable)
    windowless = python.with_name("pythonw.exe")
    return [str(windowless if windowless.is_file() else python), "-m", terrain.DISTRIBUTION]


class Platform(Protocol):
    """What each OS package provides."""

    @property
    def system(self) -> System:
        """The system this package is for."""
        ...

    @property
    def name(self) -> str:
        """The system's name as people read it in messages (M-PLAT-01)."""
        ...

    def support(self) -> Unsupported | None:
        """Return None when Verdra supports this system, else why it doesn't."""
        ...

    def prefers_reduced_motion(self) -> bool | None:
        """Return whether the OS asks apps to reduce motion, or None when it can't be read."""
        ...

    def load_cert_chain(self, context: ssl.SSLContext, certificate: bytes, key: bytes) -> None:
        """Load a PEM certificate and key into `context` without writing them to disk.

        Python's ssl module reads them only from paths, and leaf keys must never touch the disk
        (Master plan 10.3, spec S-10), so each system hands OpenSSL an in-memory file.
        """
        ...

    def roblox_clients(self) -> list[RobloxClient] | Unsupported:
        """Return the installed Roblox clients, the one to launch first (spec S-12)."""
        ...

    def trust_files_in(self, version_folder: Path) -> list[Path]:
        """Return the trust files of a new version folder, none if it isn't a Player's."""
        ...

    def launch_roblox(
        self,
        client: RobloxClient,
        link: str | None,
        proxy_port: int,
        environment: Mapping[str, str],
        spawn: Spawn = subprocess.Popen,
    ) -> int:
        """Start `client` with the proxy variables (and `link`, unchanged); return its PID."""
        ...

    def link_handler(self) -> LinkHandler | Unsupported:
        """Return the `roblox-player:` handler, or why Verdra can't take it on this system."""
        ...

    def hosts_file(self) -> Path:
        """Return the system hosts file, which Verdra only ever reads in per-app mode (S-15)."""
        ...

    def running_clients(self, client: RobloxClient) -> list[RunningClient] | Unsupported:
        """Return this user's running processes of `client`, or why they can't be listed."""
        ...


def system() -> System:
    """Return the system Verdra runs on."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def platform_for(which: System) -> Platform:
    """Return the OS package's Platform for a system."""
    # Imported here, not at the top: the OS packages import this module for the protocol.
    match which:
        case "windows":
            from verdra.soil import meadow  # noqa: PLC0415

            return meadow.PLATFORM
        case "macos":
            from verdra.soil import orchard  # noqa: PLC0415

            return orchard.PLATFORM
        case "linux":
            from verdra.soil import tundra  # noqa: PLC0415

            return tundra.PLATFORM


def current() -> Platform:
    """Return the Platform for the system Verdra runs on."""
    return platform_for(system())


def system_name() -> str:
    """Return the system's name as people read it in messages (M-PLAT-01)."""
    return current().name


def prefers_reduced_motion() -> bool | None:
    """Return whether the OS asks apps to reduce motion, or None when it can't be read."""
    try:
        return current().prefers_reduced_motion()
    except OSError:
        return None


def read_command(command: list[str]) -> str | None:
    """Run a fixed command without a shell; return its trimmed output, or None if it failed."""
    executable = shutil.which(command[0])
    if executable is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - fixed arguments, no shell
            [executable, *command[1:]],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    return result.stdout.strip() if result.returncode == 0 else None
