# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Find Roblox, start it with the proxy variables, register the roblox-player: handler."""

from verdra.soil import humus, orchard


def support() -> humus.Unsupported:
    """Return why this job isn't available: macOS is deferred until after 1.0."""
    return orchard.UNSUPPORTED
