# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The message catalogue holds messages only, no code comments (Reference R5)."""

from pathlib import Path

from tools import i18n


def test_code_comments_are_dropped(tmp_path: Path) -> None:
    catalog = tmp_path / "verdra_en.ts"
    catalog.write_text(
        "<message>\n"
        "    <source>Verdra is quitting.</source>\n"
        "    <extracomment>The Qt modules Verdra may load (Master plan 8.1).</extracomment>\n"
        '    <translation type="unfinished"></translation>\n'
        "</message>\n",
        encoding="utf-8",
    )
    i18n.drop_code_comments(catalog)
    assert catalog.read_text(encoding="utf-8") == (
        "<message>\n"
        "    <source>Verdra is quitting.</source>\n"
        '    <translation type="unfinished"></translation>\n'
        "</message>\n"
    )


def test_the_catalog_carries_no_code_comments() -> None:
    assert "<extracomment>" not in i18n.CATALOG.read_text(encoding="utf-8")


def test_a_count_goes_through_self_tr_so_the_catalog_gets_plural_forms() -> None:
    """lupdate makes a plural entry only from `self.tr(text, message_id, n)`: a count passed to
    `QCoreApplication.translate` gives a plain entry ("1 changes are waiting"), or none at all
    when the count isn't a plain name."""
    import ast  # noqa: PLC0415

    found = []
    for path in sorted((i18n.ROOT / "src" / "verdra").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "translate"
                and len(node.args) + len(node.keywords) >= 4  # noqa: PLR2004 - (context, text, comment, n)
            ):
                found.append(f"{path.name}:{node.lineno}")
    assert found == []


def test_every_message_with_a_count_is_a_plural_entry() -> None:
    import xml.etree.ElementTree as ET  # noqa: PLC0415, N817

    root = ET.parse(i18n.CATALOG).getroot()  # noqa: S314 - our own file
    plain = [
        message.findtext("source", "")
        for message in root.iter("message")
        if "%n" in message.findtext("source", "") and message.get("numerus") != "yes"
    ]
    assert plain == []


def test_every_context_is_a_class_or_a_message_id() -> None:
    """lupdate names a context after the class around a `self.tr`; when it misreads the code it
    makes one up ("QCoreApplication.self"), and Qt never finds that message's translation."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415, N817

    root = ET.parse(i18n.CATALOG).getroot()  # noqa: S314 - our own file
    odd = [name for c in root.iter("context") if "." in (name := c.findtext("name", ""))]
    assert odd == []


def test_no_plural_entry_is_left_unfinished() -> None:
    """lrelease leaves "unfinished" entries out of the compiled catalogue, so their singular
    form would never show ("Apply 1 changes")."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415, N817

    root = ET.parse(i18n.CATALOG).getroot()  # noqa: S314 - our own file
    unfinished = [
        message.findtext("source", "")
        for message in root.iter("message")
        if message.get("numerus") == "yes"
        and (translation := message.find("translation")) is not None
        and translation.get("type") == "unfinished"
    ]
    assert unfinished == []
