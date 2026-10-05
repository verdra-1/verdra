# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Editor drawer (Asset ID · Local file · URL · Remove).

Spec S-22. The original is entered by asset ID; the target is chosen with the segmented control.
Save is disabled until the target is valid, with the reason as its tooltip (rule 1); Enter in
the target field saves. A Local file is checked by its content (format and size), stored as a
`./` path when it is inside the profile's folder, and can be dropped on the drawer; a URL must
be HTTPS and its host is shown under the field. Checking the original's type on Roblox arrives
with `bark/pollinator`.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QCoreApplication, QUrl, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from verdra.trunk.branches import grafts

#: The segmented control's buttons, in order.
KINDS = ("asset_id", "file", "url", "remove")


class Editor(QFrame):
    """The replacement editor drawer.

    Signals:
        saved(Original, Target, str): Save was pressed: the original, the target and the asset
            family the target's file belongs to ("" when unknown).

    The IDs travel inside Python objects, never as a Qt `int`: Qt's `int` is 32 bits and real
    asset IDs are larger (a Toolbox image can be 15553230204), so an `int` signal argument
    overflows and the save never reaches the screen.
    """

    saved = Signal(object, object, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAcceptDrops(True)
        #: The profile's own folder: Local files inside it are stored as `./` paths.
        self.folder = Path()
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
        for index, label in enumerate(
            (self.tr("Asset ID"), self.tr("Local file"), self.tr("URL"), self.tr("Remove"))
        ):
            button = QPushButton(label, self)
            button.setCheckable(True)
            button.setChecked(index == 0)
            self.kinds.addButton(button, index)
            kinds.addWidget(button)
        column.addLayout(kinds)

        field = QHBoxLayout()
        self.target = QLineEdit(self)
        self.target.returnPressed.connect(self._save)
        field.addWidget(self.target, 1)
        self.browse = QPushButton(self.tr("Choose file…"), self)
        self.browse.clicked.connect(self._browse)
        field.addWidget(self.browse)
        column.addLayout(field)
        self.detail = QLabel(self)
        self.detail.setWordWrap(True)
        column.addWidget(self.detail)
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
        self.kinds.idClicked.connect(self._kind_changed)
        self._kind_changed()

    def start(self, folder: Path | None = None) -> None:
        """Open the drawer empty, with the cursor in the original's field."""
        if folder is not None:
            self.folder = folder
        self.original.clear()
        self.target.clear()
        self.choose("asset_id")
        self.show()
        self.original.setFocus()

    def kind(self) -> str:
        """Return the chosen target kind."""
        return KINDS[max(self.kinds.checkedId(), 0)]

    def choose(self, kind: str) -> None:
        """Select a target kind, as clicking its button does."""
        button = self.kinds.button(KINDS.index(kind))
        button.setChecked(True)
        self._kind_changed()

    def use_file(self, path: Path) -> None:
        """Make `path` the Local file target (Choose file…, or a file dropped on the drawer)."""
        self.choose("file")
        self.target.setText(grafts.stored_path(path, self.folder))

    def value(self) -> str:
        """Return the target value as it will be saved."""
        text = self.target.text().strip()
        kind = self.kind()
        if kind == "asset_id":
            return str(int(text)) if text.isdigit() else text
        return "" if kind == "remove" else text

    def family(self) -> str:
        """Return the asset family of a Local file target, or ""."""
        if self.kind() != "file" or not self.value():
            return ""
        family, _problem = grafts.file_family(grafts.resolve(self.value(), self.folder))
        return family or ""

    def problem_text(self) -> str:
        """Return why Save is disabled, or "" when it can be pressed."""
        original, kind, target = self.original.text().strip(), self.kind(), self.value()
        original_ok = original.isdigit() and int(original) > 0
        if kind == "asset_id":
            if not (original_ok and target.isdigit() and int(target) > 0):
                return QCoreApplication.translate(
                    "M-EDIT-06", "Enter the asset ID to replace and the asset ID to use instead."
                )
            if int(original) == int(target):
                return QCoreApplication.translate(
                    "M-EDIT-07", "An asset can't replace itself. Enter a different asset ID."
                )
            return ""
        if not original_ok:
            return QCoreApplication.translate("M-EDIT-10", "Enter the asset ID to replace.")
        return grafts.target_problem(kind, target, self.folder) or ""

    # --- Drag and drop (Qt API) --------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - Qt API
        """Accept one dropped local file (Qt API)."""
        if _dropped_file(event.mimeData().urls()) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt API
        """Fill Local file with the dropped file (Qt API)."""
        path = _dropped_file(event.mimeData().urls())
        if path is not None:
            self.use_file(path)
            event.acceptProposedAction()

    # --- Inside -----------------------------------------------------------------------------

    def _kind_changed(self) -> None:
        kind = self.kind()
        names = {
            "asset_id": (self.tr("Target asset ID"), "9876543210"),
            "file": (self.tr("Target file"), ""),
            "url": (self.tr("Target link"), "https://"),
            "remove": (self.tr("Target"), ""),
        }
        name, placeholder = names[kind]
        self.target.setAccessibleName(name)
        self.target.setPlaceholderText(placeholder)
        self.target.setVisible(kind != "remove")
        self.browse.setVisible(kind == "file")
        self._validate()

    def _browse(self) -> None:
        chosen, _filter = QFileDialog.getOpenFileName(
            self,
            self.tr("Choose file"),
            str(self.folder),
            self.tr("Images, meshes and sounds")
            + " (*.png *.jpg *.jpeg *.ktx2 *.dds *.obj *.mesh *.ogg *.mp3)",
        )
        if chosen:
            self.use_file(Path(chosen))

    def _validate(self) -> None:
        problem = self.problem_text()
        self.save.setEnabled(not problem)
        self.save.setToolTip(problem)
        # The reason shows once something was typed; an empty drawer just waits.
        typed = self.original.text() or self.target.text()
        self.problem.setText(problem if typed else "")
        host = ""
        if self.kind() == "url" and grafts.url_problem(self.value()) is None:
            host = QCoreApplication.translate("M-EDIT-11", "Downloads from {host}.").format(
                host=QUrl(self.value()).host()
            )
        self.detail.setText(host)

    def _save(self) -> None:
        if not self.problem_text():
            original = grafts.Original(asset_id=int(self.original.text().strip()))
            target = grafts.Target(kind=cast("grafts.TargetKind", self.kind()), value=self.value())
            self.saved.emit(original, target, self.family())


def _dropped_file(urls: list[QUrl]) -> Path | None:
    if len(urls) == 1 and urls[0].isLocalFile():
        return Path(urls[0].toLocalFile())
    return None
