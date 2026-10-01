# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Entry point for `python -m verdra` and the frozen app; hands over to trunk/sapwood."""

import sys


def main() -> int:
    """Start Verdra and return its exit code."""
    from verdra.canopy.crown.window import Shell  # noqa: PLC0415 - keep `--help`-style paths light
    from verdra.trunk.sapwood import startup  # noqa: PLC0415

    return startup.run(sys.argv, Shell)


if __name__ == "__main__":
    sys.exit(main())
