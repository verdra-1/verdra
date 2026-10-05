# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Multi-instance support (Moderation risk), per S-51."""

from verdra.soil import humus, orchard


def support() -> humus.Unsupported:
    """Return why this job isn't available: macOS is deferred until after 1.0."""
    return orchard.UNSUPPORTED
