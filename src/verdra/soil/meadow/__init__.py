# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Windows.

`PLATFORM` is this package's implementation of the Platform protocol (soil/humus).
"""

from __future__ import annotations

import ctypes
from typing import Final, Literal

from verdra.soil import humus

#: SystemParametersInfo action that reads "Show animations in Windows" (client-area animation).
_SPI_GETCLIENTAREAANIMATION: Final = 0x1042


class Meadow:
    """The Windows platform."""

    @property
    def system(self) -> Literal["windows"]:
        """The system this package is for."""
        return "windows"

    @property
    def name(self) -> str:
        """The system's name as people read it in messages (M-PLAT-01)."""
        return "Windows"

    @property
    def key_file_fallback(self) -> bool:
        """Whether the CA key may live in a user-only file when there is no secret store."""
        return False

    def support(self) -> humus.Unsupported | None:
        """Return None: Windows is Verdra's main platform."""
        return None

    def prefers_reduced_motion(self) -> bool | None:
        """Return the inverse of "Show animations in Windows", or None when it can't be read."""
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return None
        enabled = ctypes.c_int()
        ok = windll.user32.SystemParametersInfoW(
            _SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0
        )
        return None if not ok else not enabled.value


PLATFORM: Final = Meadow()
