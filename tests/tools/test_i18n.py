# SPDX-FileCopyrightText: 2026 The Verdra Authors
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
