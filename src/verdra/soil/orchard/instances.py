# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Multi-instance support (Moderation risk). Windows and macOS per S-51; Linux as Sober allows
(confirm at M5), otherwise unsupported.
"""

from verdra.soil import humus, orchard


def support() -> humus.Unsupported:
    """Return why this job isn't available: macOS is deferred until after 1.0."""
    return orchard.UNSUPPORTED
