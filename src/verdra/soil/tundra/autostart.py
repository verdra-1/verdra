# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Start with the system."""

from verdra.soil import humus, tundra


def support() -> humus.Unsupported:
    """Return why this job isn't available: Linux is paused (decision record 0018)."""
    return tundra.UNSUPPORTED
