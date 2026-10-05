# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Plan 16.2 (M0 review round 3, F13): every Activity line written for the user has a message ID.

Info, Warning and Error records reach Activity, so their text must come from the message
catalogue (`QCoreApplication.translate`, whose context is the ID). The format string itself
may only hold placeholders, so no English sentence can slip into Activity without an ID.
Debug lines are technical detail and are exempt; so are the arguments, which carry the
translated sentence or technical detail such as an exception's type.
"""

import ast
import re
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parent.parent / "src" / "verdra"
USER_LEVELS = frozenset({"info", "warning", "error", "exception", "critical"})
LEVEL_NAMES = frozenset({"INFO", "WARNING", "ERROR", "CRITICAL"})
#: A format string that carries no words of its own: only %-placeholders and punctuation.
PLACEHOLDERS_ONLY = re.compile(r"[\s%s:;,.()\-]*")


def _format_string(call: ast.Call) -> ast.expr | None:
    """Return the message argument of a logging call at Info level or above, else None."""
    function = call.func
    if not isinstance(function, ast.Attribute):
        return None
    if function.attr in USER_LEVELS and call.args:
        return call.args[0]
    if function.attr == "log" and len(call.args) >= 2:
        level = call.args[0]
        named = isinstance(level, ast.Attribute) and level.attr in LEVEL_NAMES
        # A level held in a variable (Notice, toasts) is checked where the text is made.
        return call.args[1] if named else None
    return None


def worded_log_lines(source: str, where: str) -> list[str]:
    """Return every Info-or-above logging call whose format string contains words."""
    problems: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        message = _format_string(node)
        if isinstance(message, ast.Constant) and isinstance(message.value, str):
            if not PLACEHOLDERS_ONLY.fullmatch(message.value):
                problems.append(f"{where}:{node.lineno}: {message.value!r}")
        elif isinstance(message, ast.JoinedStr):
            problems.append(f"{where}:{node.lineno}: an f-string")
    return problems


def test_every_user_facing_log_line_comes_from_the_catalog() -> None:
    problems: list[str] = []
    for path in sorted(SOURCE.rglob("*.py")):
        where = path.relative_to(SOURCE).as_posix()
        problems += worded_log_lines(path.read_text(encoding="utf-8"), where)
    assert problems == []


@pytest.mark.parametrize(
    "line",
    [
        'log.info("Verdra is quitting.")',
        'log.warning("Setting %s: unknown setting", key)',
        'log.error(f"{name} failed")',
        'logging.getLogger(__name__).info("Detailed logging turned itself off.")',
        'log.log(logging.WARNING, "Port %s was busy", port)',
    ],
)
def test_a_worded_log_line_is_caught(line: str) -> None:
    assert worded_log_lines(line, "x.py") != []


@pytest.mark.parametrize(
    "line",
    [
        'log.info("%s", QCoreApplication.translate("M-SHELL-08", "Verdra is quitting."))',
        'log.error("%s: %s", name, type(error).__name__, exc_info=error)',
        'log.debug("Startup: %s after %d ms.", name, ms)',
        'log.log(level, "%s", text)',
    ],
)
def test_translated_and_technical_lines_pass(line: str) -> None:
    assert worded_log_lines(line, "x.py") == []
