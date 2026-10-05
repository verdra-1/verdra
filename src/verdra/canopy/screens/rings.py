# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Activity screen.

Spec S-03 and Master plan 7.7: the log list with a level filter, search, "Copy", "Open log
folder" and "Export support bundle…". Every record shown is already redacted; the support bundle
is written in the background and announced with M-LOG-01.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.crown import theme
from verdra.canopy.crown.dew import Kind
from verdra.trunk import rings

if TYPE_CHECKING:
    from verdra.canopy.crown.dew import Dew
    from verdra.trunk.sapwood.startup import Services


def levels() -> list[tuple[int, str]]:
    """Return the level filter's entries: (logging level, label)."""
    return [
        (logging.INFO, QCoreApplication.translate("Activity", "Info")),
        (logging.WARNING, QCoreApplication.translate("Activity", "Warning")),
        (logging.ERROR, QCoreApplication.translate("Activity", "Error")),
        (logging.DEBUG, QCoreApplication.translate("Activity", "Debug")),
    ]


class BundleDialog(QDialog):
    """Asks whether the support bundle should include the replacement profiles."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        title = QCoreApplication.translate("M-LOG-02", "Export a support bundle?")
        self.setWindowTitle(title)
        self.setAccessibleName(title)
        tokens = theme.Tokens.load()
        layout = QVBoxLayout(self)
        padding = tokens.length("space-8")
        layout.setContentsMargins(padding, padding, padding, padding)
        layout.setSpacing(tokens.length("space-4"))
        heading = QLabel(title, self)
        theme.set_text_style(heading, "title-m")
        layout.addWidget(heading)
        body = QLabel(
            QCoreApplication.translate(
                "M-LOG-02",
                "The bundle holds Verdra's version, your system, the routing status, the last "
                "2,000 log lines, your settings and the list of system changes. Secrets are "
                "removed. Nothing is uploaded; you decide where to send it.",
            ),
            self,
        )
        body.setWordWrap(True)
        body.setFixedWidth(420)
        layout.addWidget(body)
        self.include_profiles = QCheckBox(
            QCoreApplication.translate("Activity", "Include my replacement profiles"), self
        )
        layout.addWidget(self.include_profiles)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton(QCoreApplication.translate("Dialogs", "Cancel"), self)
        cancel.clicked.connect(self.reject)
        export = QPushButton(QCoreApplication.translate("Activity", "Export…"), self)
        export.setProperty("primary", True)
        export.setDefault(True)
        export.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(export)
        layout.addLayout(buttons)


class ActivityScreen(QWidget):
    """The Activity screen."""

    def __init__(
        self,
        services: Services | None = None,
        dew: Dew | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.services = services
        self.dew = dew
        tokens = theme.Tokens.load()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.length("space-3"))

        filters, actions = self._toolbar()
        layout.addLayout(filters)
        layout.addLayout(actions)

        self.table = QTableView(self)
        self.table.setAccessibleName(QCoreApplication.translate("Activity", "Activity records"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.setWordWrap(False)
        self.filter = rings.ActivityFilter(self)
        if services is not None:
            self.filter.setSourceModel(services.rings.model(self))
        self.table.setModel(self.filter)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self.search.textChanged.connect(self.filter.set_text)
        self._levels_changed()
        if services is not None and not services.settings.value("advanced.detailed_logging"):
            debug = self.level_buttons[logging.DEBUG]
            debug.setToolTip(
                QCoreApplication.translate(
                    "M-LOG-03", "Debug records appear only while detailed logging is on."
                )
            )

    def _toolbar(self) -> tuple[QHBoxLayout, QHBoxLayout]:
        """Return the filter row (levels, search) and the action row, so neither is squeezed
        at the largest text size (plan 12.5)."""
        spacing = theme.Tokens.load().length("space-2")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(spacing)
        actions = QHBoxLayout()
        actions.setSpacing(spacing)
        actions.addStretch()
        self.level_buttons: dict[int, QToolButton] = {}
        for level, name in levels():
            button = QToolButton(self)
            button.setText(name)
            button.setCheckable(True)
            button.setChecked(level != logging.DEBUG)
            button.setAccessibleName(
                QCoreApplication.translate("Activity", "Show {level} records").format(level=name)
            )
            button.setToolTip(button.accessibleName())
            button.toggled.connect(self._levels_changed)
            toolbar.addWidget(button)
            self.level_buttons[level] = button
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(QCoreApplication.translate("Activity", "Search Activity"))
        self.search.setAccessibleName(QCoreApplication.translate("Activity", "Search Activity"))
        self.search.setClearButtonEnabled(True)
        toolbar.addWidget(self.search, 1)
        self.copy = QPushButton(QCoreApplication.translate("Activity", "Copy"), self)
        self.copy.clicked.connect(self.copy_records)
        actions.addWidget(self.copy)
        self.open_folder = QPushButton(
            QCoreApplication.translate("Activity", "Open log folder"), self
        )
        self.open_folder.clicked.connect(self._open_log_folder)
        actions.addWidget(self.open_folder)
        self.export = QPushButton(
            QCoreApplication.translate("Activity", "Export support bundle…"), self
        )
        self.export.clicked.connect(self.export_bundle)
        actions.addWidget(self.export)
        return toolbar, actions

    def _levels_changed(self) -> None:
        levels = [level for level, button in self.level_buttons.items() if button.isChecked()]
        self.filter.set_levels(levels)

    def visible_records(self) -> list[rings.ActivityRecord]:
        """Return the records the filter shows, in order."""
        result: list[rings.ActivityRecord] = []
        for row in range(self.filter.rowCount()):
            record = self.filter.data(self.filter.index(row, 0), Qt.ItemDataRole.UserRole)
            if isinstance(record, rings.ActivityRecord):
                result.append(record)
        return result

    def copy_records(self) -> str:
        """Copy the selected records (or every visible one) to the clipboard; return the text."""
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        records = self.visible_records()
        chosen = [records[row] for row in rows] if rows else records
        text = "\n".join(record.line() for record in chosen)
        QGuiApplication.clipboard().setText(text)
        return text

    def _open_log_folder(self) -> None:
        if self.services is not None:
            rings.open_folder(self.services.rings.logs_dir)

    def export_bundle(self) -> None:
        """Ask about profiles, ask where to save, and write the bundle in the background."""
        if self.services is None:
            return
        dialog = BundleDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        default = rings.default_bundle_path()
        target, _ = QFileDialog.getSaveFileName(
            self,
            QCoreApplication.translate("Activity", "Save support bundle"),
            str(default),
            QCoreApplication.translate("Activity", "ZIP archives (*.zip)"),
        )
        if target:
            self.write_bundle(Path(target), include_profiles=dialog.include_profiles.isChecked())

    def write_bundle(self, target: Path, *, include_profiles: bool) -> Any:
        """Write the support bundle to `target` as a background job and return the job."""
        assert self.services is not None  # noqa: S101 - only called with services
        services = self.services
        sources = rings.bundle_sources(services.settings)
        job = services.tendrils.submit(
            QCoreApplication.translate("Activity", "Exporting the support bundle"),
            lambda _handle: rings.export_support_bundle(
                target, services.rings, sources, include_profiles=include_profiles
            ),
        )
        job.succeeded.connect(lambda path: self._saved(Path(path)))
        return job

    def _saved(self, path: Path) -> None:
        if self.dew is None:
            return
        text = QCoreApplication.translate("M-LOG-01", "Support bundle saved to {path}.").format(
            path=path
        )

        def show_in_folder() -> None:
            rings.open_folder(path)

        self.dew.show(
            text,
            Kind.SUCCESS,
            (QCoreApplication.translate("M-LOG-01", "Show in folder"), show_in_folder),
        )
