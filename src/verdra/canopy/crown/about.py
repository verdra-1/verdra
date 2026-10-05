# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""About dialog; licence, third-party notices and privacy viewers.

Master plan 3.2 and 7.7: the symbol and wordmark, the version and build, the NOTICE text with its
link clickable, the not-affiliated line (M-ABOUT-02), and buttons that show the licence, the
third-party notices and the privacy statement. The credit line (M-ABOUT-01) belongs in the README
only, never in the app (plan 3.3). The texts exist once, at the repository root, and the build
copies them into the app; trunk reads them (`trunk/sapwood/startup.legal_text`), since canopy
makes no disk calls of its own (Reference R1). THIRD_PARTY_NOTICES.md is generated into release
builds (plan 13.6).
"""

from __future__ import annotations

import html

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import verdra
from verdra.canopy.crown import theme
from verdra.trunk import rings
from verdra.trunk.sapwood import startup

LOCKUP_WIDTH = 220


def notice_html(text: str) -> str:
    """Return the NOTICE text as HTML with its addresses clickable."""
    lines = []
    for line in text.strip().splitlines():
        escaped = html.escape(line)
        for word in line.split():
            if word.startswith("https://"):
                link = html.escape(word)
                escaped = escaped.replace(link, f'<a href="{link}">{link}</a>')
        lines.append(escaped)
    return "<br>".join(lines)


class TextViewer(QDialog):
    """A read-only viewer for one legal text."""

    def __init__(self, title: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setAccessibleName(title)
        self.resize(640, 560)
        layout = QVBoxLayout(self)
        view = QPlainTextEdit(self)
        view.setReadOnly(True)
        view.setPlainText(text)
        view.setAccessibleName(title)
        theme.set_text_style(view, "mono")
        layout.addWidget(view)
        close = QPushButton(QCoreApplication.translate("About", "Close"), self)
        close.clicked.connect(self.accept)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)


class AboutDialog(QDialog):
    """The About dialog."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        title = QCoreApplication.translate("About", "About Verdra")
        self.setWindowTitle(title)
        self.setAccessibleName(title)
        self.setFixedWidth(520)
        tokens = theme.Tokens.load()
        layout = QVBoxLayout(self)
        padding = tokens.length("space-8")
        layout.setContentsMargins(padding, padding, padding, padding)
        layout.setSpacing(tokens.length("space-4"))

        current = theme.Theme.instance()
        dark = current is not None and current.mode == "dark"
        lockup = QLabel(self)
        lockup.setAccessibleName("Verdra")  # noqa: VT001 - the product name is never translated
        lockup.setPixmap(
            theme.svg_pixmap(
                theme.brand_file(
                    "lockup-horizontal-reversed.svg" if dark else "lockup-horizontal.svg"
                ),
                LOCKUP_WIDTH,
                self.devicePixelRatioF(),
            )
        )
        layout.addWidget(lockup, alignment=Qt.AlignmentFlag.AlignLeft)

        self.version = QLabel(
            QCoreApplication.translate("About", "Version {version} ({build})").format(
                version=verdra.__version__, build=rings.build_id()
            ),
            self,
        )
        self.version.setProperty("muted", True)
        layout.addWidget(self.version)

        notice = startup.legal_text("NOTICE") or ""
        self.notice = QLabel(notice_html(notice), self)
        self.notice.setTextFormat(Qt.TextFormat.RichText)
        self.notice.setOpenExternalLinks(True)
        self.notice.setWordWrap(True)
        self.notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.notice.setAccessibleName(QCoreApplication.translate("About", "Notice"))
        theme.set_text_style(self.notice, "caption")
        layout.addWidget(self.notice)

        self.not_affiliated = QLabel(
            QCoreApplication.translate(
                "M-ABOUT-02",
                "Verdra is an independent project and is not affiliated with or endorsed by Roblox "
                "Corporation. Roblox is a trademark of Roblox Corporation.",
            ),
            self,
        )
        self.not_affiliated.setWordWrap(True)
        self.not_affiliated.setProperty("muted", True)
        layout.addWidget(self.not_affiliated)

        buttons = self._viewer_buttons()
        buttons.addStretch()
        close = QPushButton(QCoreApplication.translate("About", "Close"), self)
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def _viewer_buttons(self) -> QHBoxLayout:
        buttons = QHBoxLayout()
        buttons.setSpacing(theme.Tokens.load().length("space-2"))
        self.viewers: dict[str, QPushButton] = {}
        for key, label, file in (
            ("license", QCoreApplication.translate("About", "License"), "LICENSE"),
            (
                "notices",
                QCoreApplication.translate("About", "Third-party notices"),
                "THIRD_PARTY_NOTICES.md",
            ),
            ("privacy", QCoreApplication.translate("About", "Privacy"), "PRIVACY.md"),
        ):
            button = QPushButton(label, self)
            text = startup.legal_text(file)
            if text is None:
                button.setEnabled(False)
                button.setToolTip(
                    QCoreApplication.translate(
                        "M-ABOUT-03", "Release builds include this text; this build doesn't."
                    )
                )
            else:
                button.clicked.connect(
                    lambda _checked=False, t=label, body=text: TextViewer(t, body, self).exec()
                )
            buttons.addWidget(button)
            self.viewers[key] = button
        return buttons
