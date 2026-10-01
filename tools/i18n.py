# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Update the message catalogue `src/verdra/assets/i18n/verdra_en.ts` from the source.

Master plan 6.7 and Reference R5: every user-facing string goes through Qt's translation
functions, and the catalogue holds them all, each under its context (a message ID such as
"M-SET-01", or the screen it belongs to). Line locations are left out so the file changes only
when a sentence does.

    python tools/i18n.py           update the catalogue
    python tools/i18n.py --check   fail if the catalogue is out of date (CI)
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "verdra"
CATALOGUE = SOURCE / "assets" / "i18n" / "verdra_en.ts"


def update(target: Path) -> None:
    """Write the catalogue for the current source to `target`."""
    lupdate = shutil.which("pyside6-lupdate")
    if lupdate is None:
        raise SystemExit("pyside6-lupdate isn't installed; run `uv sync` first.")
    files = sorted(str(path) for path in SOURCE.rglob("*.py"))
    subprocess.run(  # noqa: S603 - fixed tool, file list from the repository
        [
            lupdate,
            "-silent",
            "-locations",
            "none",
            "-no-obsolete",
            "-source-language",
            "en_US",
            "-target-language",
            "en_US",
            *files,
            "-ts",
            str(target),
        ],
        check=True,
    )


def main() -> int:
    """Update or check the catalogue and return a process exit code."""
    parser = argparse.ArgumentParser(description="Update the message catalogue")
    parser.add_argument("--check", action="store_true", help="fail if the catalogue is stale")
    arguments = parser.parse_args()
    if not arguments.check:
        CATALOGUE.parent.mkdir(parents=True, exist_ok=True)
        update(CATALOGUE)
        return 0
    with tempfile.TemporaryDirectory() as folder:
        fresh = Path(folder) / CATALOGUE.name
        if CATALOGUE.exists():
            shutil.copyfile(CATALOGUE, fresh)
        update(fresh)
        if CATALOGUE.exists() and filecmp.cmp(fresh, CATALOGUE, shallow=False):
            return 0
    print("src/verdra/assets/i18n/verdra_en.ts is out of date; run python tools/i18n.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
