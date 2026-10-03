# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""The Platform protocol every OS package implements; picks the right one at startup.

meadow (Windows), orchard (macOS) and tundra (Linux and Sober) each provide one `Platform`.
Nothing outside soil checks the operating system: it asks `current()` (Master plan 16.2). M0
holds the parts the app shell needs: which system Verdra runs on, whether Verdra supports it,
and whether the system asks for reduced motion (6.6). The routing, launching and keeper parts
of the protocol arrive with their specs (M1 onward).

macOS is deferred until after 1.0 (decision record 0014): orchard answers every job with
`Unsupported`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Literal, Protocol

System = Literal["windows", "macos", "linux"]

_TIMEOUT_SECONDS = 1.0


#: Why a job isn't available. "deferred": the whole system waits for a later release (macOS,
#: decision record 0014). More reasons arrive with the specs that need them (S-51 instances).
Reason = Literal["deferred"]


@dataclass(frozen=True, slots=True)
class Unsupported:
    """A job this system can't do, with the reason, so the UI can explain it (Reference R1).

    It carries no text: the UI turns it into M-PLAT-01 ("<Feature> isn't available on
    <system>: <reason>.") from the message catalog.
    """

    system: System
    reason: Reason


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

    @property
    def key_file_fallback(self) -> bool:
        """Whether the CA key may live in a user-only file when there is no secret store.

        Only Linux, where a desktop may lack a Secret Service (plan 16.2, risk R-10).
        """
        ...

    def prefers_reduced_motion(self) -> bool | None:
        """Return whether the OS asks apps to reduce motion, or None when it can't be read."""
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
