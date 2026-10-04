# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Editor drawer (Asset ID · Local file · URL · Remove).

Spec S-22. The original is entered by asset ID; the target is chosen with the segmented control.
This first build edits Asset ID targets: Local file, URL and Remove arrive with the codecs
(strata/ochre and strata/clay) and stay disabled with M-SOON-01. Save is disabled until both IDs
are valid, with the reason as its tooltip (rule 1); Enter in the target field saves.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.leaves.empty import soon


class Editor(QFrame):
    """The replacement editor drawer.

    Signals:
        saved(int, str): Save was pressed: the original asset ID and the target asset ID.
    """

    saved = Signal(int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        column = QVBoxLayout(self)
        column.addWidget(QLabel(self.tr("Add replacement"), self))

        column.addWidget(QLabel(self.tr("Original asset ID"), self))
        self.original = QLineEdit(self)
        self.original.setAccessibleName(self.tr("Original asset ID"))
        self.original.setPlaceholderText("1234567890")
        column.addWidget(self.original)

        column.addWidget(QLabel(self.tr("Replace with"), self))
        kinds = QHBoxLayout()
        self.kinds = QButtonGroup(self)
        not_yet = soon()
        for index, label in enumerate(
            (self.tr("Asset ID"), self.tr("Local file"), self.tr("URL"), self.tr("Remove"))
        ):
            button = QPushButton(label, self)
            button.setCheckable(True)
            if index == 0:
                button.setChecked(True)
            else:
                button.setEnabled(False)
                button.setToolTip(not_yet)
            self.kinds.addButton(button, index)
            kinds.addWidget(button)
        column.addLayout(kinds)

        self.target = QLineEdit(self)
        self.target.setAccessibleName(self.tr("Target asset ID"))
        self.target.setPlaceholderText("9876543210")
        self.target.returnPressed.connect(self._save)
        column.addWidget(self.target)
        self.problem = QLabel(self)
        self.problem.setWordWrap(True)
        column.addWidget(self.problem)
        column.addStretch(1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.cancel = QPushButton(self.tr("Cancel"), self)
        self.cancel.clicked.connect(self.hide)
        self.save = QPushButton(self.tr("Save"), self)
        self.save.setProperty("primary", True)
        self.save.clicked.connect(self._save)
        footer.addWidget(self.cancel)
        footer.addWidget(self.save)
        column.addLayout(footer)

        self.original.textChanged.connect(self._validate)
        self.target.textChanged.connect(self._validate)
        self._validate()

    def start(self) -> None:
        """Open the drawer empty, with the cursor in the original's field."""
        self.original.clear()
        self.target.clear()
        self.show()
        self.original.setFocus()

    def problem_text(self) -> str:
        """Return why Save is disabled, or "" when both IDs are valid."""
        original, target = self.original.text().strip(), self.target.text().strip()
        if not (original.isdigit() and int(original) > 0 and target.isdigit() and int(target) > 0):
            return QCoreApplication.translate(
                "M-EDIT-06", "Enter the asset ID to replace and the asset ID to use instead."
            )
        if int(original) == int(target):
            return QCoreApplication.translate(
                "M-EDIT-07", "An asset can't replace itself. Enter a different asset ID."
            )
        return ""

    def _validate(self) -> None:
        problem = self.problem_text()
        self.save.setEnabled(not problem)
        self.save.setToolTip(problem)
        # The reason shows once something was typed; an empty drawer just waits.
        self.problem.setText(problem if self.original.text() or self.target.text() else "")

    def _save(self) -> None:
        if not self.problem_text():
            self.saved.emit(int(self.original.text().strip()), str(int(self.target.text().strip())))
