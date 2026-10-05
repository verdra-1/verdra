# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Global hotkeys."""

from verdra.soil import humus, tundra


def support() -> humus.Unsupported:
    """Return why this job isn't available: Linux is paused (decision record 0018)."""
    return tundra.UNSUPPORTED
