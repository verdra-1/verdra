# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Tests for the translation gate."""

from pathlib import Path

from tools.check_strings import findings

SOURCE = """
class Panel:
    def build(self, label, button):
        label.setText("Applied 12 replacements.")           # flagged
        label.setText(self.tr("Applied 12 replacements."))  # fine
        label.setToolTip(f"Port {port} is in use")          # flagged
        label.setObjectName("statusPill")                   # not user-facing
        button = QPushButton("Apply now")                    # flagged
        button = QPushButton(self.tr("Apply now"))           # fine
        label.setText("Verdra")  # noqa: VT001 - product name
        label.setText("")                                    # empty
        label.setText("12")                                  # no letters
"""


def test_flags_only_untranslated_text(tmp_path: Path) -> None:
    module = tmp_path / "panel.py"
    module.write_text(SOURCE, encoding="utf-8")
    lines = [line for line, _column, _message in findings(module)]
    assert lines == [4, 6, 8]
