# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spelling gate: no British spellings in text the user sees.

Master plan 4.3 and 16.2 (M0 review decisions, rounds 1 and 2), decision records 0010 and
0011: every string the user sees uses US spelling, including names taken from the plan, and so
do code identifiers, settings keys, command-line flags and the code's file names. The plan's own
prose, format IDs (`verdra.catalogue`) and the nature names keep theirs. This gate reads:

- every source string of the message catalogue (`src/verdra/assets/i18n/verdra_en.ts`), which
  holds every string the app shows;
- the user-facing documents `README.md` and `PRIVACY.md` (the About dialog shows the latter),
  outside code spans, fenced code blocks and link targets;
- every identifier, and every command-line flag written as a string, in the Python files under
  `src/`, `tools/`, `tests/` and `packaging/`, and those files' names. Docstrings, comments and
  other strings are prose and are not checked here.

Words that must stay as they are (a file name, a quoted identifier) go in
`[tool.verdra.spelling] allow` in pyproject.toml, each with a reason.

Usage: uv run python tools/check_spelling.py
"""

from __future__ import annotations

import io
import re
import sys
import tokenize
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "src" / "verdra" / "assets" / "i18n" / "verdra_en.ts"
DOCUMENTS = (ROOT / "README.md", ROOT / "PRIVACY.md")
CODE_FOLDERS = ("src", "tools", "tests", "packaging")
#: The words of an identifier: "css_colour" → css, colour; "JobCancelledError" → Job, Cancelled.
IDENTIFIER_WORD = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])")
FLAG = re.compile(r"""^[rbuRBU]*(['"])(--?[a-z][a-z0-9-]*)\1$""")

# British spelling (as a regular expression over one word) and its US form.
BRITISH: dict[str, str] = {
    r"behaviours?": "behavior",
    r"colour\w*": "color",
    r"licences?|licenced": "license",
    r"cancell(?:ed|ing)": "canceled, canceling",
    r"(?:un|mis)?recognis\w*": "recognize",
    r"(?:re|dis)?organis\w*": "organize",
    r"minimis\w*": "minimize",
    r"maximis\w*": "maximize",
    r"favourit\w*": "favorite",
    r"centre[sd]?": "center",
    r"analys(?:e|ed|es|ing)": "analyze",
    r"catalogues?": "catalog",
    r"honour\w*|labour\w*|neighbour\w*|flavour\w*|humour\w*|rumour\w*|harbour\w*": "-or",
    r"endeavour\w*|savour\w*|vapour\w*|armour\w*|odour\w*|valour\w*|parlour\w*": "-or",
    r"(?:customis|optimis|prioritis|synchronis|authoris|initialis|summaris|finalis)\w*": "-ize",
    r"(?:normalis|visualis|apologis|categoris|serialis|localis|personalis|memoris)\w*": "-ize",
    r"(?:utilis|criticis|realis|standardis|sanitis)\w*|emphasis(?:e|ed|es|ing)": "-ize",
    r"(?:travell|modell|labell|signall|fuell|tunnell|levell)(?:ed|ing|er|ers)": "single l",
    r"grey\w*": "gray",
    r"whilst": "while",
    r"amongst": "among",
    r"programmes?": "program",
    r"defence|offence|pretence": "-se",
    r"artefacts?": "artifact",
    r"judgements?": "judgment",
    r"dialogues?": "dialog",
    r"enrolments?|fulfil|fulfilment": "enroll, fulfill",
    r"practis(?:e|ed|es|ing)": "practice",
    r"aluminium|cheques?|tyres?": "US form",
}
WORD = re.compile(r"[A-Za-z]+")
PATTERNS = [(re.compile(rf"(?i)^(?:{british})$"), us) for british, us in BRITISH.items()]


@dataclass(frozen=True)
class Finding:
    """One British spelling in user-facing text."""

    where: str
    word: str
    us: str

    def __str__(self) -> str:
        return f"{self.where}: British spelling {self.word!r}; use the US form ({self.us})"


def british(word: str) -> str | None:
    """Return the US form to use if `word` is a British spelling, else None."""
    for pattern, us in PATTERNS:
        if pattern.match(word):
            return us
    return None


def check_text(text: str, where: str, allow: set[str]) -> list[Finding]:
    """Return every British spelling in one piece of user-facing text."""
    findings = []
    for word in WORD.findall(text):
        us = british(word)
        if us is not None and word.lower() not in allow:
            findings.append(Finding(where, word, us))
    return findings


def prose(markdown: str) -> list[tuple[int, str]]:
    """Return (line number, text) for the prose of a Markdown file.

    Fenced code blocks, inline code spans and link targets are left out: they hold file names,
    commands and addresses, not text the user reads as language.
    """
    lines, fenced = [], False
    for number, line in enumerate(markdown.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        text = re.sub(r"`[^`]*`", " ", line)
        text = re.sub(r"\]\([^)]*\)|<https?://[^>]*>|https?://\S+", " ", text)
        lines.append((number, text))
    return lines


def catalog_strings(path: Path) -> list[tuple[str, str]]:
    """Return (context, source text) for every message in a Qt Linguist file."""
    root = ET.parse(path).getroot()  # noqa: S314 - our own generated catalogue
    strings = []
    for context in root.iter("context"):
        name = context.findtext("name", default="")
        for message in context.iter("message"):
            strings.append((name, message.findtext("source", default="")))
    return strings


def code_files(root: Path = ROOT) -> list[Path]:
    """Return the Python files (and PyInstaller spec files) under the code folders."""
    files: list[Path] = []
    for folder in CODE_FOLDERS:
        base = root / folder
        if base.exists():
            files += [p for p in base.rglob("*") if p.suffix in {".py", ".spec"} and p.is_file()]
    return sorted(files)


def check_identifiers(source: str, where: str, allow: set[str]) -> list[Finding]:
    """Return every British spelling in one Python file's identifiers and flag strings."""
    findings: list[Finding] = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenError, SyntaxError:
        return findings
    for token in tokens:
        if token.type == tokenize.NAME:
            words = IDENTIFIER_WORD.findall(token.string)
        elif token.type == tokenize.STRING and (flag := FLAG.match(token.string)):
            words = IDENTIFIER_WORD.findall(flag.group(2))
        else:
            continue
        for word in words:
            us = british(word)
            if us is not None and word.lower() not in allow:
                line = f"{where}:{token.start[0]}"
                findings.append(Finding(f"{line} ({token.string})", word, us))
    return findings


def load_allow(root: Path = ROOT) -> set[str]:
    """Return the allowlisted words (lower case) from pyproject.toml."""
    with (root / "pyproject.toml").open("rb") as handle:
        table = tomllib.load(handle)["tool"]["verdra"].get("spelling", {})
    return {word.lower() for word in table.get("allow", {})}


def check(
    catalog: Path = CATALOG, documents: tuple[Path, ...] = DOCUMENTS, root: Path = ROOT
) -> list[Finding]:
    """Return every British spelling in the catalogue and the user-facing documents."""
    allow = load_allow(root)
    findings: list[Finding] = []
    if catalog.exists():
        for context, source in catalog_strings(catalog):
            findings += check_text(source, f"{catalog.relative_to(root)} [{context}]", allow)
    for document in documents:
        if document.exists():
            for number, line in prose(document.read_text(encoding="utf-8")):
                findings += check_text(line, f"{document.relative_to(root)}:{number}", allow)
    for path in code_files(root):
        where = path.relative_to(root).as_posix()
        for word in IDENTIFIER_WORD.findall(path.stem):
            us = british(word)
            if us is not None and word.lower() not in allow:
                findings.append(Finding(f"{where} (file name)", word, us))
        findings += check_identifiers(path.read_text(encoding="utf-8"), where, allow)
    return findings


def main() -> int:
    """Run the gate and return a process exit code."""
    findings = check()
    for finding in findings:
        print(finding)
    if findings:
        print(f"{len(findings)} British spelling(s) (decision records 0010 and 0011).")
        return 1
    print("User-facing text and code identifiers use US spelling.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
