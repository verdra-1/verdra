# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Linux and Sober.

`PLATFORM` is this package's implementation of the Platform protocol (soil/humus).
"""

from __future__ import annotations

from typing import Final, Literal

from verdra.soil import humus


class Tundra:
    """The Linux platform."""

    @property
    def system(self) -> Literal["linux"]:
        """The system this package is for."""
        return "linux"

    @property
    def name(self) -> str:
        """The system's name as people read it in messages (M-PLAT-01)."""
        return "Linux"

    @property
    def key_file_fallback(self) -> bool:
        """Whether the CA key may live in a user-only file when there is no secret store."""
        return True

    def support(self) -> humus.Unsupported | None:
        """Return None: Linux with Sober is supported."""
        return None

    def prefers_reduced_motion(self) -> bool | None:
        """Return whether GNOME's `enable-animations` is off, or None when it can't be read."""
        output = humus.read_command(
            ["gsettings", "get", "org.gnome.desktop.interface", "enable-animations"]
        )
        return None if output is None else output == "false"


PLATFORM: Final = Tundra()
