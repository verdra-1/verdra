# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Settings screen, including System changes and Reset everything.

Spec S-02. Every key of Reference R2's Settings-screen groups has a control here, with the R2
label. Changes go straight to the settings store, which validates and saves them. Each group has
"Reset to defaults". Controls whose feature isn't built yet are disabled with a tooltip saying
why. A settings file from a newer Verdra makes the whole screen read-only (M-SET-03).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from PySide6.QtCore import QCoreApplication, QDateTime, QLocale, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.crown import theme
from verdra.canopy.crown.about import TextViewer
from verdra.canopy.leaves.dialogs import DestructiveConfirmation
from verdra.canopy.leaves.empty import soon
from verdra.canopy.leaves.notice import Notice, Tone
from verdra.canopy.leaves.progress import ProgressBar
from verdra.canopy.leaves.switch import Switch
from verdra.trunk import tendrils
from verdra.trunk.branches import fallow
from verdra.trunk.sapwood import startup

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Row:
    """One setting on the screen."""

    key: str
    label: str
    kind: str  # "switch", "choice", "number", "text"
    choices: tuple[tuple[Any, str], ...] = ()
    minimum: int = 0
    maximum: int = 0
    caption: str = ""
    unavailable: str = ""  # a reason the control is disabled for now
    visible_when: tuple[str, tuple[Any, ...]] | None = None


def feature_names() -> dict[str, str]:
    """Return the plain name of each feature that needs an accepted warning (R2, R6)."""
    return {
        "accounts": QCoreApplication.translate("Settings", "Accounts"),
        "custom_flags": QCoreApplication.translate("Settings", "Custom FastFlags"),
        "multi_instance": QCoreApplication.translate("Settings", "Multi-instance"),
        "subplaces": QCoreApplication.translate("Settings", "Subplaces"),
        "displayed_name": QCoreApplication.translate("Settings", "Name display"),
        "traffic_editing": QCoreApplication.translate("Settings", "Traffic editing"),
    }


#: The columns of the System changes list, as functions so the titles follow the language.
CHANGE_COLUMNS: tuple[Callable[[], str], ...] = (
    lambda: QCoreApplication.translate("Settings", "Change"),
    lambda: QCoreApplication.translate("Settings", "Where"),
    lambda: QCoreApplication.translate("Settings", "Made"),
    lambda: QCoreApplication.translate("Settings", "State"),
)


def change_cells(change: fallow.Change) -> tuple[str, str, str, str]:
    """Return the text of one row of the System changes list."""
    made = QDateTime.fromMSecsSinceEpoch(round(change.created.timestamp() * 1000))
    states = {
        "pending": QCoreApplication.translate("Settings", "Pending"),
        "done": QCoreApplication.translate("Settings", "Done"),
        "failed": QCoreApplication.translate("Settings", "Failed"),
    }
    state = states.get(change.state, change.state)
    if change.reason:
        state = QCoreApplication.translate("Settings", "{state}: {reason}").format(
            state=state, reason=change.reason
        )
    return (
        fallow.kind_names().get(change.kind, change.kind),
        change.target,
        QLocale().toString(made, QLocale.FormatType.ShortFormat),
        state,
    )


def groups() -> list[tuple[str, str, list[Row]]]:
    """Return (group key, title, rows) for every Settings-screen group, in plan 7.7's order."""
    return [
        (
            "general",
            QCoreApplication.translate("Settings", "General"),
            [
                Row(
                    "general.start_with_system",
                    QCoreApplication.translate("Settings", "Start Verdra when you sign in"),
                    "switch",
                    unavailable=soon(),
                ),
                Row(
                    "general.start_minimized",
                    QCoreApplication.translate("Settings", "Start in the tray"),
                    "switch",
                    caption=QCoreApplication.translate(
                        "M-SET-04", "Only when Verdra starts with the system."
                    ),
                ),
                Row(
                    "general.close_to_tray",
                    QCoreApplication.translate(
                        "Settings", "Keep running in the tray when the window closes"
                    ),
                    "switch",
                ),
                Row(
                    "general.route_on_launch",
                    QCoreApplication.translate("Settings", "Start routing when Verdra opens"),
                    "switch",
                ),
                Row(
                    "general.check_updates",
                    QCoreApplication.translate("Settings", "Check for updates"),
                    "switch",
                    caption=QCoreApplication.translate("M-SET-05", "At most once a day."),
                ),
                Row(
                    "general.update_channel",
                    QCoreApplication.translate("Settings", "Update channel"),
                    "choice",
                    (
                        ("stable", QCoreApplication.translate("Settings", "Stable")),
                        ("beta", QCoreApplication.translate("Settings", "Beta")),
                    ),
                ),
            ],
        ),
        (
            "routing",
            QCoreApplication.translate("Settings", "Routing"),
            [
                Row(
                    "routing.mode",
                    QCoreApplication.translate("Settings", "How Roblox is routed"),
                    "choice",
                    (
                        (
                            "per_app",
                            QCoreApplication.translate("Settings", "Per app (recommended)"),
                        ),
                        (
                            "hosts_file",
                            QCoreApplication.translate(
                                "Settings", "Hosts file (needs administrator rights)"
                            ),
                        ),
                    ),
                    caption=QCoreApplication.translate("M-SET-06", "Switching restarts routing."),
                ),
                Row(
                    "routing.proxy_port",
                    QCoreApplication.translate("Settings", "Local port"),
                    "number",
                    minimum=1024,
                    maximum=65535,
                ),
                Row(
                    "routing.handle_roblox_links",
                    QCoreApplication.translate(
                        "Settings", "Open games started from the Roblox website through Verdra"
                    ),
                    "switch",
                ),
                Row(
                    "routing.close_roblox_on_quit",
                    QCoreApplication.translate("Settings", "Close Roblox when Verdra quits"),
                    "switch",
                ),
                Row(
                    "routing.upstream.kind",
                    QCoreApplication.translate("Settings", "Internet connection"),
                    "choice",
                    (
                        ("system", QCoreApplication.translate("Settings", "Use system settings")),
                        ("direct", QCoreApplication.translate("Settings", "Direct")),
                        ("http", QCoreApplication.translate("Settings", "HTTP proxy")),
                        ("socks5", QCoreApplication.translate("Settings", "SOCKS5 proxy")),
                    ),
                ),
                Row(
                    "routing.upstream.host",
                    QCoreApplication.translate("Settings", "Proxy address"),
                    "text",
                    visible_when=("routing.upstream.kind", ("http", "socks5")),
                ),
                Row(
                    "routing.upstream.port",
                    QCoreApplication.translate("Settings", "Proxy port"),
                    "number",
                    minimum=0,
                    maximum=65535,
                    caption=QCoreApplication.translate("M-SET-07", "0 means not set."),
                    visible_when=("routing.upstream.kind", ("http", "socks5")),
                ),
                Row(
                    "routing.upstream.username",
                    QCoreApplication.translate("Settings", "Proxy user name"),
                    "text",
                    visible_when=("routing.upstream.kind", ("socks5",)),
                ),
            ],
        ),
        (
            "library",
            QCoreApplication.translate("Settings", "Library"),
            [
                Row(
                    "library.capture",
                    QCoreApplication.translate("Settings", "Capture new assets"),
                    "switch",
                ),
                Row(
                    "library.size_cap_gb",
                    QCoreApplication.translate("Settings", "Library size limit (GB)"),
                    "number",
                    minimum=1,
                    maximum=100,
                ),
                Row(
                    "library.location",
                    QCoreApplication.translate("Settings", "Library location"),
                    "text",
                    caption=QCoreApplication.translate(
                        "M-SET-08", "Empty means the default folder."
                    ),
                    unavailable=soon(),
                ),
            ],
        ),
        (
            "appearance",
            QCoreApplication.translate("Settings", "Appearance"),
            [
                Row(
                    "appearance.theme",
                    QCoreApplication.translate("Settings", "Theme"),
                    "choice",
                    (
                        ("system", QCoreApplication.translate("Settings", "Match system")),
                        ("light", QCoreApplication.translate("Settings", "Light")),
                        ("dark", QCoreApplication.translate("Settings", "Dark")),
                    ),
                ),
                Row(
                    "appearance.text_scale",
                    QCoreApplication.translate("Settings", "Text size"),
                    "choice",
                    tuple((n, f"{n} %") for n in (90, 100, 115, 130)),
                ),
                Row(
                    "appearance.reduce_motion",
                    QCoreApplication.translate("Settings", "Reduce motion"),
                    "choice",
                    (
                        ("system", QCoreApplication.translate("Settings", "Auto")),
                        ("on", QCoreApplication.translate("Settings", "On")),
                        ("off", QCoreApplication.translate("Settings", "Off")),
                    ),
                ),
                Row(
                    "appearance.density",
                    QCoreApplication.translate("Settings", "Density"),
                    "choice",
                    (
                        ("comfortable", QCoreApplication.translate("Settings", "Comfortable")),
                        ("compact", QCoreApplication.translate("Settings", "Compact")),
                    ),
                ),
            ],
        ),
        (
            "privacy",
            QCoreApplication.translate("Settings", "Privacy & safety"),
            [
                Row(
                    "privacy.keep_traffic",
                    QCoreApplication.translate("Settings", "Keep traffic between sessions"),
                    "switch",
                    unavailable=soon(),
                ),
            ],
        ),
        (
            "advanced",
            QCoreApplication.translate("Settings", "Advanced"),
            [
                Row(
                    "advanced.advanced_mode",
                    QCoreApplication.translate("Settings", "Advanced mode"),
                    "switch",
                    caption=QCoreApplication.translate("M-SET-09", "Shows the Traffic screen."),
                ),
                Row(
                    "advanced.detailed_logging",
                    QCoreApplication.translate("Settings", "Detailed logging"),
                    "switch",
                    caption=QCoreApplication.translate(
                        "M-SET-10", "Still redacted. Turns itself off after 24 hours."
                    ),
                ),
                Row(
                    "advanced.worker_threads",
                    QCoreApplication.translate("Settings", "Background workers"),
                    "number",
                    minimum=2,
                    maximum=8,
                    caption=QCoreApplication.translate("M-SET-11", "Applies after a restart."),
                ),
            ],
        ),
    ]


def confirm_reset(parent: QWidget | None = None) -> DestructiveConfirmation:
    """Return M-RESET-03: "Reset everything" or "Cancel", with Cancel as the default.

    It carries the option "Also delete my profiles, library and settings" as `erase`, off.
    """
    question = DestructiveConfirmation(
        QCoreApplication.translate(
            "M-RESET-03", "Remove everything Verdra changed on this computer?"
        ),
        QCoreApplication.translate("M-RESET-03", "Reset everything"),
        QCoreApplication.translate("M-RESET-03", "Your profiles and library stay."),
        parent,
    )
    erase = QCheckBox(
        QCoreApplication.translate("Settings", "Also delete my profiles, library and settings"),
        question,
    )
    question.layout_.insertWidget(question.layout_.count() - 1, erase)
    question.erase = erase  # type: ignore[attr-defined]
    return question


class ResetDialog(QDialog):
    """Reset everything's progress: each change as it is removed, then the summary (S-16)."""

    def __init__(
        self, job: tendrils.Job, parent: QWidget | None = None, *, erase: bool = False
    ) -> None:
        super().__init__(parent)
        self.job = job
        #: The option "Also delete my profiles, library and settings" was ticked.
        self.erase = erase
        #: Set once reset removed everything with the option ticked: Verdra quits on Close.
        self.quit_to_erase = False
        title = QCoreApplication.translate("Settings", "Reset everything")
        self.setWindowTitle(title)
        self.setAccessibleName(title)
        self.setModal(True)
        tokens = theme.Tokens.load()
        layout = QVBoxLayout(self)
        padding = tokens.length("space-8")
        layout.setContentsMargins(padding, padding, padding, padding)
        layout.setSpacing(tokens.length("space-4"))
        heading = QLabel(title, self)
        theme.set_text_style(heading, "title-m")
        layout.addWidget(heading)
        self.progress = ProgressBar(self)
        self.progress.setAccessibleName(
            QCoreApplication.translate("Settings", "Reset everything progress")
        )
        layout.addWidget(self.progress)
        self.items = QListWidget(self)
        self.items.setAccessibleName(QCoreApplication.translate("Settings", "Changes"))
        self.items.setWordWrap(True)
        layout.addWidget(self.items, 1)
        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        self.summary.hide()
        layout.addWidget(self.summary)
        self.close_button = QPushButton(QCoreApplication.translate("Settings", "Close"), self)
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        layout.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignRight)
        self.resize(tokens.length("space-12") * 12, tokens.length("space-12") * 8)
        job.progressed.connect(self._progressed)
        job.succeeded.connect(self._succeeded)
        job.failed.connect(self._failed)

    def _progressed(self, percent: int | None, step: str) -> None:
        self.progress.set_value(percent)
        if step:
            self.items.addItem(step)
            self.items.scrollToBottom()

    def _succeeded(self, summary: fallow.Summary) -> None:
        self.progress.set_value(100)
        text = fallow.summary_line(summary)
        if self.erase and summary.failed:
            text += " " + QCoreApplication.translate(
                "M-RESET-10",
                "Your profiles, library and settings were kept, because some changes couldn't "
                "be removed.",
            )
        elif self.erase:
            self.quit_to_erase = True
            text += " " + QCoreApplication.translate(
                "M-RESET-09",
                "When you close this window, Verdra deletes your profiles, library and settings "
                "and quits.",
            )
        if self.erase:
            log.info("%s", text)
        self._finish(text)

    def _failed(self, _reason: str) -> None:
        self._finish(self.job.message())

    def _finish(self, text: str) -> None:
        self.summary.setText(text)
        self.summary.show()
        self.close_button.setEnabled(True)
        self.close_button.setDefault(True)
        self.close_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def reject(self) -> None:
        """Escape closes the dialog only once reset has finished: it can't stop halfway."""
        if self.job.done:
            super().reject()


class SettingsScreen(QWidget):
    """The Settings screen."""

    def __init__(
        self,
        settings: Any,
        run_setup: Callable[[], None] | None = None,
        parent: QWidget | None = None,
        *,
        list_changes: Callable[[], list[fallow.Change]] = fallow.system_changes,
        pool: tendrils.Tendrils | None = None,
        on_erase: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.controls: dict[str, QWidget] = {}
        self.rows: dict[str, Row] = {}
        self.row_widgets: dict[str, QWidget] = {}
        self.reset_buttons: dict[str, QPushButton] = {}
        self._loading = False
        tokens = theme.Tokens.load()

        body = self._scroll_body()
        self.column = QVBoxLayout(body)
        self.column.setSpacing(tokens.length("space-6"))

        if settings.read_only:
            self.column.addWidget(
                Notice(
                    QCoreApplication.translate(
                        "M-SET-03",
                        "This file was made by a newer Verdra. Update Verdra to edit it.",
                    ),
                    Tone.WARNING,
                    body,
                )
            )

        for key, title, rows in groups():
            panel = self._panel(body, title)
            for row in rows:
                self.rows[row.key] = row
                panel.layout().addWidget(self._row(panel, row))  # type: ignore[union-attr]
            if key == "general" and run_setup is not None:
                setup = QPushButton(
                    QCoreApplication.translate("Settings", "Run setup again"), panel
                )
                setup.clicked.connect(run_setup)
                panel.layout().addWidget(setup, alignment=Qt.AlignmentFlag.AlignLeft)  # type: ignore[union-attr]
                self.run_setup_button = setup
            if key == "privacy":
                self._privacy_extras(panel)
            reset = QPushButton(QCoreApplication.translate("Settings", "Reset to defaults"), panel)
            reset.setProperty("quiet", True)
            reset.setAccessibleName(
                QCoreApplication.translate("Settings", "Reset {group} to defaults").format(
                    group=title
                )
            )
            reset.clicked.connect(
                lambda _checked=False, group=key: self.settings.reset_group(group)
            )
            reset.setEnabled(not settings.read_only)
            panel.layout().addWidget(reset, alignment=Qt.AlignmentFlag.AlignRight)  # type: ignore[union-attr]
            self.reset_buttons[key] = reset
            self.column.addWidget(panel)

        changes = self._panel(body, QCoreApplication.translate("Settings", "System changes"))
        self._system_changes(changes, list_changes)
        self.reset_everything = QPushButton(
            QCoreApplication.translate("Settings", "Reset everything…"), changes
        )
        self.pool = pool
        #: Quits Verdra so shutdown deletes its own folders (the reset option, spec S-16).
        self.on_erase = on_erase
        if pool is None:
            self.reset_everything.setEnabled(False)
            self.reset_everything.setToolTip(soon())
        self.reset_everything.clicked.connect(self.start_reset)
        self.reset_dialog: ResetDialog | None = None
        changes.layout().addWidget(self.reset_everything, alignment=Qt.AlignmentFlag.AlignLeft)  # type: ignore[union-attr]
        self.column.addWidget(changes)
        self.column.addStretch()

        settings.changed.connect(self._changed)
        self._load_all()
        self.refresh_changes()

    # --- Building -------------------------------------------------------------------------

    def _scroll_body(self) -> QWidget:
        """Return the scrolling page that holds every group."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # A container, not a control: Tab moves through the settings inside it, and the scroll
        # area follows the focused one (plan 12.5).
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        outer.addWidget(scroll)
        body = QWidget(scroll)
        scroll.setWidget(body)
        return body

    def _panel(self, parent: QWidget, title: str) -> QFrame:
        tokens = theme.Tokens.load()
        panel = QFrame(parent)
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        padding = tokens.length("space-4")
        layout.setContentsMargins(padding, padding, padding, padding)
        layout.setSpacing(tokens.length("space-3"))
        heading = QLabel(title, panel)
        theme.set_text_style(heading, "title-m")
        layout.addWidget(heading)
        return panel

    def _row(self, parent: QWidget, row: Row) -> QWidget:
        container = QWidget(parent)
        line = QHBoxLayout(container)
        line.setContentsMargins(0, 0, 0, 0)
        text = QVBoxLayout()
        text.setSpacing(0)
        label = QLabel(row.label, container)
        text.addWidget(label)
        if row.caption:
            caption = QLabel(row.caption, container)
            caption.setProperty("muted", True)
            theme.set_text_style(caption, "caption")
            text.addWidget(caption)
        line.addLayout(text, 1)
        control = self._control(container, row)
        control.setAccessibleName(row.label)
        label.setBuddy(control)
        line.addWidget(control)
        if row.unavailable:
            control.setEnabled(False)
            control.setToolTip(row.unavailable)
        if self.settings.read_only:
            control.setEnabled(False)
            control.setToolTip(
                QCoreApplication.translate(
                    "M-SET-03", "This file was made by a newer Verdra. Update Verdra to edit it."
                )
            )
        self.controls[row.key] = control
        self.row_widgets[row.key] = container
        return container

    def _control(self, parent: QWidget, row: Row) -> QWidget:
        if row.kind == "switch":
            switch = Switch(parent)
            switch.toggled.connect(lambda value, key=row.key: self._store(key, value))
            return switch
        if row.kind == "choice":
            combo = QComboBox(parent)
            for value, text in row.choices:
                combo.addItem(text, value)
            combo.setMinimumWidth(220)
            combo.currentIndexChanged.connect(
                lambda index, key=row.key, box=combo: self._store(key, box.itemData(index))
            )
            return combo
        if row.kind == "number":
            spin = QSpinBox(parent)
            spin.setRange(row.minimum, row.maximum)
            spin.setMinimumWidth(120)
            spin.valueChanged.connect(lambda value, key=row.key: self._store(key, value))
            return spin
        field = QLineEdit(parent)
        field.setMinimumWidth(220)
        field.editingFinished.connect(lambda key=row.key, edit=field: self._store(key, edit.text()))
        return field

    def _privacy_extras(self, panel: QWidget) -> None:
        heading = QLabel(QCoreApplication.translate("Settings", "Warnings you accepted"), panel)
        theme.set_text_style(heading, "body-strong")
        panel.layout().addWidget(heading)  # type: ignore[union-attr]
        self.acceptances = QVBoxLayout()
        panel.layout().addLayout(self.acceptances)  # type: ignore[union-attr]
        statement = QLabel(
            QCoreApplication.translate(
                "M-SET-14",
                "Verdra sends nothing about you anywhere. It talks only to Roblox, GitHub (update "
                "check and presets) and the sites your profiles name.",
            ),
            panel,
        )
        statement.setWordWrap(True)
        statement.setProperty("muted", True)
        panel.layout().addWidget(statement)  # type: ignore[union-attr]
        # R2: the statement comes "with a link to the privacy text" (the same text as About).
        self.privacy_link = QPushButton(
            QCoreApplication.translate("Settings", "Privacy statement"), panel
        )
        self.privacy_link.setProperty("quiet", "true")
        self.privacy_link.clicked.connect(self.show_privacy)
        panel.layout().addWidget(self.privacy_link)  # type: ignore[union-attr]

    def show_privacy(self) -> None:
        """Open the privacy statement (PRIVACY.md), as About › Privacy does."""
        text = startup.legal_text("PRIVACY.md")
        if text is not None:
            TextViewer(QCoreApplication.translate("About", "Privacy"), text, self).exec()

    # --- Values ---------------------------------------------------------------------------

    def _system_changes(
        self, panel: QFrame, list_changes: Callable[[], list[fallow.Change]]
    ) -> None:
        """Build the System changes list (spec S-16); `refresh_changes` fills it."""
        self._list_changes = list_changes
        self.changes_empty = QLabel(
            QCoreApplication.translate(
                "M-SET-12", "Verdra hasn't changed anything outside its own folders."
            ),
            panel,
        )
        self.changes_empty.setProperty("muted", True)
        #: Shown while the ledger can't be read (M-RESET-05); made when needed, because a
        #: notice writes its sentence to Activity.
        self.changes_error: Notice | None = None
        self.changes_table = QTableWidget(0, len(CHANGE_COLUMNS), panel)
        self.changes_table.setAccessibleName(
            QCoreApplication.translate("Settings", "System changes Verdra made")
        )
        self.changes_table.setHorizontalHeaderLabels([title() for title in CHANGE_COLUMNS])
        self.changes_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.changes_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.changes_table.setAlternatingRowColors(True)
        self.changes_table.setShowGrid(False)
        self.changes_table.setWordWrap(False)
        self.changes_table.verticalHeader().hide()
        header = self.changes_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._changes_layout = cast(QVBoxLayout, panel.layout())  # made by _panel
        self._changes_layout.addWidget(self.changes_empty)
        self._changes_layout.addWidget(self.changes_table)

    def refresh_changes(self) -> None:
        """Read the system changes again and show them (on build and whenever shown)."""
        try:
            changes = self._list_changes()
        except fallow.LedgerUnreadableError as error:
            if self.changes_error is None:
                self.changes_error = Notice(
                    QCoreApplication.translate(
                        "M-RESET-05", "Verdra can't read its list of system changes in {path}."
                    ).format(path=error.path),
                    Tone.DANGER,
                    self.changes_table.parentWidget(),
                )
                self._changes_layout.insertWidget(1, self.changes_error)
            self.changes_empty.hide()
            self.changes_table.hide()
            return
        if self.changes_error is not None:
            self.changes_error.hide()
            self.changes_error.deleteLater()
            self.changes_error = None
        self.changes_empty.setVisible(not changes)
        self.changes_table.setVisible(bool(changes))
        self.changes_table.setRowCount(len(changes))
        for row, change in enumerate(changes):
            for column, text in enumerate(change_cells(change)):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.changes_table.setItem(row, column, item)

    def start_reset(self) -> ResetDialog | None:
        """Ask M-RESET-03, then run Reset everything and show its progress (spec S-16).

        Returns the progress dialog, or None if the user canceled or reset can't run here.
        """
        if self.pool is None or self.reset_dialog is not None:
            return self.reset_dialog
        question = confirm_reset(self)
        erase = question.erase  # type: ignore[attr-defined]
        if question.exec() != QDialog.DialogCode.Accepted:
            return None
        dialog = ResetDialog(fallow.start(self.pool), self, erase=erase.isChecked())
        dialog.finished.connect(self._reset_closed)
        self.reset_dialog = dialog
        dialog.open()
        return dialog

    def _reset_closed(self) -> None:
        quit_to_erase = self.reset_dialog is not None and self.reset_dialog.quit_to_erase
        if self.reset_dialog is not None:
            self.reset_dialog.deleteLater()
            self.reset_dialog = None
        self.refresh_changes()
        if quit_to_erase and self.on_erase is not None:
            self.on_erase()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt's name
        """Show the ledger as it is now: routing may have changed it since the last visit."""
        self.refresh_changes()
        super().showEvent(event)

    def _load_all(self) -> None:
        self._loading = True
        try:
            for key in self.controls:
                self._show_value(key, self.settings.value(key))
            self._refresh_visibility()
            self._refresh_acceptances()
        finally:
            self._loading = False

    def _show_value(self, key: str, value: Any) -> None:
        control = self.controls[key]
        control.blockSignals(True)
        try:
            if isinstance(control, Switch):
                control.setChecked(bool(value))
            elif isinstance(control, QComboBox):
                index = control.findData(value)
                control.setCurrentIndex(max(index, 0))
            elif isinstance(control, QSpinBox):
                control.setValue(int(value))
            elif isinstance(control, QLineEdit):
                control.setText(str(value))
        finally:
            control.blockSignals(False)

    def _store(self, key: str, value: Any) -> None:
        if self._loading or self.settings.read_only:
            return
        self.settings.set(key, value)

    def _changed(self, key: str, value: Any) -> None:
        if key in self.controls:
            self._show_value(key, value)
        self._refresh_visibility()
        if key == "privacy.risk_acceptances":
            self._refresh_acceptances()

    def _refresh_visibility(self) -> None:
        for key, row in self.rows.items():
            if row.visible_when is not None:
                other, values = row.visible_when
                self.row_widgets[key].setVisible(self.settings.value(other) in values)

    def _refresh_acceptances(self) -> None:
        while self.acceptances.count():
            item = self.acceptances.takeAt(0)
            if item is not None and (widget := item.widget()) is not None:
                widget.deleteLater()
        accepted = self.settings.value("privacy.risk_acceptances")
        if not accepted:
            none = QLabel(
                QCoreApplication.translate("M-SET-13", "You haven't accepted any warnings.")
            )
            none.setProperty("muted", True)
            self.acceptances.addWidget(none)
            return
        for feature in sorted(accepted):
            line = QWidget()
            row = QHBoxLayout(line)
            row.setContentsMargins(0, 0, 0, 0)
            name = feature_names().get(feature, feature)
            row.addWidget(QLabel(name), 1)
            withdraw = QPushButton(QCoreApplication.translate("Settings", "Withdraw"))
            withdraw.setAccessibleName(
                QCoreApplication.translate("Settings", "Withdraw {feature}").format(feature=name)
            )
            withdraw.clicked.connect(lambda _checked=False, name=feature: self._withdraw(name))
            row.addWidget(withdraw)
            self.acceptances.addWidget(line)

    def _withdraw(self, feature: str) -> None:
        accepted = dict(self.settings.value("privacy.risk_acceptances"))
        accepted.pop(feature, None)
        self.settings.set("privacy.risk_acceptances", accepted)
