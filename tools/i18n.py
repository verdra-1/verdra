# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Update the message catalogue `src/verdra/assets/i18n/verdra_en.ts` and its compiled `.qm`.

Master plan 6.7 and Reference R5: every user-facing string goes through Qt's translation
functions, and the catalogue holds them all, each under its context (a message ID such as
"M-SET-01", or the screen it belongs to). Line locations are left out so the file changes only
when a sentence does.

Messages with a count (`self.tr(text, message_id, n)`) are plural entries: the English
catalogue gives their singular and plural forms ("Routing · %n replacement active" and
"…replacements…"), which lupdate keeps when it updates the file. The compiled catalogue
`verdra_en.qm`, which the app loads at startup, is built with lrelease (Reference R1:
assets/i18n holds the source and the compiled files).

    python tools/i18n.py           update the catalogue and build the .qm
    python tools/i18n.py --check   fail if either is out of date, or a plural entry has no
                                   forms (CI)
"""

from __future__ import annotations

import argparse
import filecmp
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "verdra"
CATALOG = SOURCE / "assets" / "i18n" / "verdra_en.ts"
COMPILED = CATALOG.with_suffix(".qm")


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
    drop_code_comments(target)
    add_header(target)


#: lupdate reads every `#:` comment as a note for translators and attaches it to the next
#: message. Verdra's `#:` comments document code (constants, attributes), so they don't belong
#: in the catalog.
EXTRA_COMMENT = re.compile(r"^[ \t]*<extracomment>.*?</extracomment>\n", re.MULTILINE | re.DOTALL)


def drop_code_comments(path: Path) -> None:
    """Remove the code comments lupdate copied into the catalogue as translator notes."""
    text = path.read_text(encoding="utf-8")
    path.write_text(EXTRA_COMMENT.sub("", text), encoding="utf-8", newline="\n")


SPDX_HEADER = (
    "<!-- SPDX-FileCopyrightText: 2026 q0f7 -->\n<!-- SPDX-License-Identifier: Apache-2.0 -->\n"
)


def add_header(path: Path) -> None:
    """Put the SPDX header after the XML declaration (lupdate rewrites the file without it)."""
    text = path.read_text(encoding="utf-8")
    if SPDX_HEADER in text:
        return
    declaration, _, rest = text.partition("\n")
    path.write_text(f"{declaration}\n{SPDX_HEADER}{rest}", encoding="utf-8", newline="\n")


def compile_catalog(source: Path, target: Path) -> None:
    """Build the compiled catalogue `target` from the .ts file `source` with lrelease."""
    lrelease = shutil.which("pyside6-lrelease")
    if lrelease is None:
        raise SystemExit("pyside6-lrelease isn't installed; run `uv sync` first.")
    subprocess.run(  # noqa: S603 - fixed tool and paths from the repository
        [lrelease, "-silent", str(source), "-qm", str(target)], check=True
    )


def missing_plural_forms(path: Path) -> list[str]:
    """Return the source text of every plural entry whose English forms aren't all filled in."""
    root = ET.parse(path).getroot()  # noqa: S314 - our own generated catalog
    missing = []
    for message in root.iter("message"):
        if message.get("numerus") != "yes":
            continue
        translation = message.find("translation")
        forms = [] if translation is None else translation.findall("numerusform")
        unfinished = translation is None or translation.get("type") == "unfinished"
        if unfinished or len(forms) < 2 or not all((form.text or "").strip() for form in forms):
            missing.append(message.findtext("source", default=""))
    return missing


def main() -> int:
    """Update or check the catalogue and return a process exit code."""
    parser = argparse.ArgumentParser(description="Update the message catalogue")
    parser.add_argument("--check", action="store_true", help="fail if the catalogue is stale")
    arguments = parser.parse_args()
    if not arguments.check:
        CATALOG.parent.mkdir(parents=True, exist_ok=True)
        update(CATALOG)
        compile_catalog(CATALOG, COMPILED)
        for source in missing_plural_forms(CATALOG):
            print(f"Fill in the singular and plural forms of {source!r} in {CATALOG.name}.")
        return 0
    problems = (
        [
            f"{CATALOG.name}: the plural entry {source!r} has no singular and plural forms"
            for source in missing_plural_forms(CATALOG)
        ]
        if CATALOG.exists()
        else []
    )
    with tempfile.TemporaryDirectory() as folder:
        fresh = Path(folder) / CATALOG.name
        compiled = Path(folder) / COMPILED.name
        if CATALOG.exists():
            shutil.copyfile(CATALOG, fresh)
        update(fresh)
        if not (CATALOG.exists() and filecmp.cmp(fresh, CATALOG, shallow=False)):
            problems.append(f"{CATALOG.name} is out of date; run python tools/i18n.py")
        else:
            compile_catalog(CATALOG, compiled)
            if not (COMPILED.exists() and filecmp.cmp(compiled, COMPILED, shallow=False)):
                problems.append(f"{COMPILED.name} is out of date; run python tools/i18n.py")
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
