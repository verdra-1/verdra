# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Strings gate: user-facing text must go through Qt's translation functions.

Master plan 6.7 and 12.3. Finds string literals and f-strings passed straight to Qt calls that
show text to people (`setText`, `setToolTip`, `QPushButton(...)` and so on) under `src/verdra/`,
where they should be wrapped in `self.tr(...)` or `QCoreApplication.translate(...)`.

Output uses ruff's `path:line:col: CODE message` format, and a line can opt out with
`# noqa: VT001` plus a reason (for example a product name that is never translated).

Usage: python tools/check_strings.py [paths...]   (no paths: every module under src/verdra/)
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE = "VT001"

# Methods whose given argument positions are user-facing text.
TEXT_METHODS: dict[str, tuple[int, ...]] = {
    "setText": (0,),
    "setWindowTitle": (0,),
    "setToolTip": (0,),
    "setStatusTip": (0,),
    "setWhatsThis": (0,),
    "setPlaceholderText": (0,),
    "setAccessibleName": (0,),
    "setAccessibleDescription": (0,),
    "setTitle": (0,),
    "setLabelText": (0,),
    "setInformativeText": (0,),
    "setDetailedText": (0,),
    "setTabText": (1,),
    "setTabToolTip": (1,),
    "setItemText": (1,),
    "addTab": (1,),
    "insertTab": (2,),
    "addItem": (0,),
    "addAction": (0,),
    "addMenu": (0,),
    "addButton": (0,),
    "showMessage": (0, 1),
    "setHeaderLabels": (0,),
    "setHorizontalHeaderLabels": (0,),
    "setToolTipText": (0,),
}

# Widget and action constructors whose first text-like argument is user-facing.
TEXT_CONSTRUCTORS = {
    "QLabel",
    "QPushButton",
    "QToolButton",
    "QCheckBox",
    "QRadioButton",
    "QGroupBox",
    "QAction",
    "QMenu",
    "QMessageBox",
}

NOQA = re.compile(r"#\s*noqa:\s*[\w, ]*\bVT001\b")


def is_text(node: ast.expr) -> bool:
    """Return whether an argument is literal text a person would read."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return any(character.isalpha() for character in node.value)
    if isinstance(node, ast.JoinedStr):
        return any(
            isinstance(part, ast.Constant) and any(c.isalpha() for c in str(part.value))
            for part in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return is_text(node.left) or is_text(node.right)
    if isinstance(node, (ast.List, ast.Tuple)):
        return any(is_text(element) for element in node.elts)
    return False


def call_name(node: ast.Call) -> str | None:
    """Return the called function's or method's bare name."""
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def findings(path: Path) -> Iterator[tuple[int, int, str]]:
    """Yield (line, column, message) for each untranslated user-facing string in a file."""
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    for node in ast.walk(ast.parse(source, filename=str(path))):
        if not isinstance(node, ast.Call):
            continue
        name = call_name(node)
        if name in TEXT_METHODS and isinstance(node.func, ast.Attribute):
            positions = TEXT_METHODS[name]
        elif name in TEXT_CONSTRUCTORS:
            positions = (0, 1)
        else:
            continue
        candidates = [node.args[i] for i in positions if i < len(node.args)]
        candidates += [kw.value for kw in node.keywords if kw.arg in {"text", "title"}]
        for argument in candidates:
            if is_text(argument) and not NOQA.search(lines[argument.lineno - 1]):
                yield (
                    argument.lineno,
                    argument.col_offset + 1,
                    f"untranslated text passed to {name}(); wrap it in self.tr()",
                )


def main(argv: list[str]) -> int:
    """Run the gate and return a process exit code."""
    paths = [Path(arg).resolve() for arg in argv] or sorted((ROOT / "src" / "verdra").rglob("*.py"))
    count = 0
    for path in paths:
        for line, column, message in findings(path):
            print(f"{path.relative_to(ROOT).as_posix()}:{line}:{column}: {CODE} {message}")
            count += 1
    return 1 if count else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
