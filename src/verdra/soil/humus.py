# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""The Platform protocol every OS package implements; picks the right one at startup.

M0 holds the parts the app shell needs: which system Verdra runs on, and whether the system asks
for reduced motion (Master plan 6.6). The routing, launching and keeper parts of the protocol
arrive with their specs (M1 onward).
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
from typing import Literal

System = Literal["windows", "macos", "linux"]

_TIMEOUT_SECONDS = 1.0


def system() -> System:
    """Return the system Verdra runs on."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def system_name() -> str:
    """Return the system's name as people read it in messages (M-PLAT-01)."""
    return {"windows": "Windows", "macos": "macOS", "linux": "Linux"}[system()]


def prefers_reduced_motion() -> bool | None:
    """Return whether the OS asks apps to reduce motion, or None when it can't be read.

    Windows: the "Show animations in Windows" setting (client-area animation). macOS: Accessibility
    › Display › "Reduce motion". Linux: GNOME's `enable-animations`.
    """
    try:
        match system():
            case "windows":
                return _windows_reduced_motion()
            case "macos":
                output = _read(["defaults", "read", "com.apple.universalaccess", "reduceMotion"])
                return None if output is None else output == "1"
            case "linux":
                output = _read(
                    ["gsettings", "get", "org.gnome.desktop.interface", "enable-animations"]
                )
                return None if output is None else output == "false"
    except OSError:
        return None


def _windows_reduced_motion() -> bool | None:
    spi_get_client_area_animation = 0x1042
    enabled = ctypes.c_int()
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return None
    ok = windll.user32.SystemParametersInfoW(
        spi_get_client_area_animation, 0, ctypes.byref(enabled), 0
    )
    return None if not ok else not enabled.value


def _read(command: list[str]) -> str | None:
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
