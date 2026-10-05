# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Toasts: queue, stacking (at most 3), timers, one optional action, mirror to Activity.

Master plan 7.1: toasts sit at the bottom right, 16 px from the window's edges, at most three
at a time (the oldest leaves first). They dismiss themselves after 6 s unless they hold an action
or report an error. Every toast is also written to Activity (spec S-03).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from verdra.canopy.crown import theme
from verdra.canopy.leaves.progress import ProgressBar

if TYPE_CHECKING:
    from verdra.trunk.tendrils import Job

log = logging.getLogger(__name__)

MAX_TOASTS = 3
DISMISS_MS = 6_000
EDGE = 16
WIDTH = 360


class Kind(Enum):
    """What a toast reports; sets its icon and colour."""

    INFO = ("info", "ink-muted")
    SUCCESS = ("circle-check", "success")
    WARNING = ("triangle-alert", "warning")
    ERROR = ("circle-x", "danger")


class Toast(QFrame):
    """One toast: icon, text, an optional progress bar, at most one action, and a close button.

    Signals:
        closed(): The toast has gone.
    """

    closed = Signal()

    def __init__(
        self,
        text: str,
        kind: Kind = Kind.INFO,
        action: tuple[str, Callable[[], None]] | None = None,
        *,
        progress: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self.text = text
        self.setProperty("toast", True)
        self.setFixedWidth(WIDTH)
        self.setAccessibleName(text)
        tokens = theme.Tokens.load()
        outer = QHBoxLayout(self)
        outer.setContentsMargins(*([tokens.length("space-3")] * 4))
        outer.setSpacing(tokens.length("space-2"))

        icon_name, token = kind.value
        self.icon = QLabel(self)
        current = theme.Theme.instance()
        color = current.color(token) if current else tokens.color(token, "light")
        self.icon.setPixmap(theme.icon_pixmap(icon_name, color, 20, self.devicePixelRatioF()))
        self.icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        outer.addWidget(self.icon)

        middle = QVBoxLayout()
        middle.setSpacing(tokens.length("space-2"))
        self.label = QLabel(text, self)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        middle.addWidget(self.label)
        self.bar: ProgressBar | None = None
        if progress:
            self.bar = ProgressBar(self)
            self.bar.show_leaf = True
            middle.addWidget(self.bar)
        self.action_button: QPushButton | None = None
        if action is not None:
            label, callback = action
            self.action_button = QPushButton(label, self)
            self.action_button.setProperty("quiet", True)
            self.action_button.clicked.connect(callback)
            self.action_button.clicked.connect(self.dismiss)
            middle.addWidget(self.action_button, alignment=Qt.AlignmentFlag.AlignLeft)
        outer.addLayout(middle, 1)

        self.close_button = self._close_button()
        outer.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignTop)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.dismiss)
        self._gone = False
        self.slide: QPropertyAnimation | None = None
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity_effect)

    def _close_button(self) -> QToolButton:
        button = QToolButton(self)
        button.setIcon(theme.icon("x", size=16))
        target = theme.Tokens.load().length("hit-target-icon")  # plan 6.3: at least 28 × 28
        button.setMinimumSize(target, target)
        button.setAccessibleName(self.tr("Close notification"))
        button.setToolTip(self.tr("Close notification"))
        button.clicked.connect(self.dismiss)
        return button

    @property
    def sticky(self) -> bool:
        """Return whether the toast stays until closed: it holds an action or reports an error."""
        return self.action_button is not None or self.kind is Kind.ERROR or self.bar is not None

    def dismiss(self) -> None:
        """Remove the toast."""
        if self._gone:
            return
        self._gone = True
        self.timer.stop()
        self.hide()
        self.closed.emit()
        self.deleteLater()


class Dew(QObject):
    """The toast stack over one window."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.host = host
        self.toasts: list[Toast] = []
        host.installEventFilter(self)

    def show(
        self,
        text: str,
        kind: Kind = Kind.INFO,
        action: tuple[str, Callable[[], None]] | None = None,
        *,
        progress: bool = False,
    ) -> Toast:
        """Show a toast and write it to Activity."""
        level = {Kind.ERROR: logging.ERROR, Kind.WARNING: logging.WARNING}.get(kind, logging.INFO)
        log.log(level, "%s", text)
        toast = Toast(text, kind, action, progress=progress, parent=self.host)
        toast.closed.connect(lambda: self._remove(toast))
        while len(self.toasts) >= MAX_TOASTS:
            self.toasts[0].dismiss()
        self.toasts.append(toast)
        toast.show()
        toast.raise_()
        self._layout()
        self._enter(toast)
        if not toast.sticky:
            toast.timer.start(DISMISS_MS)
        return toast

    def show_job(self, job: Job) -> Toast:
        """Show a running job's progress with "Cancel"; afterwards report how it ended."""
        cancel = self.tr("Cancel")
        toast = self.show(job.step or job.name, Kind.INFO, (cancel, job.cancel), progress=True)
        toast.label.setText(job.name)
        bar = toast.bar
        assert bar is not None  # noqa: S101 - created with progress=True
        bar.set_value(job.progress)

        def progressed(percent: int | None, step: str) -> None:
            bar.set_value(percent)
            toast.label.setText(f"{job.name} · {step}" if step else job.name)

        job.progressed.connect(progressed)
        job.finished.connect(toast.dismiss)
        return toast

    def report_job(self, job: Job) -> Toast | None:
        """Show M-JOB-01 or M-JOB-02 for a job that was cancelled or failed."""
        message = job.message()
        if not message:
            return None
        kind = Kind.ERROR if job.reason else Kind.INFO
        return self.show(message, kind)

    def _remove(self, toast: Toast) -> None:
        if toast in self.toasts:
            self.toasts.remove(toast)
            self._layout()

    def _layout(self) -> None:
        tokens = theme.Tokens.load()
        gap = tokens.length("space-2")
        bottom = self.host.height() - EDGE
        for toast in reversed(self.toasts):
            if toast.slide is not None:
                toast.slide.stop()  # The new position wins over a slide still running.
                toast.slide = None
            layout = toast.layout()
            height = (
                layout.totalHeightForWidth(WIDTH)
                if layout is not None
                else toast.sizeHint().height()
            )
            toast.resize(WIDTH, height)
            x = self.host.width() - EDGE - toast.width()
            y = bottom - toast.height()
            toast.move(QPoint(x, y))
            bottom = y - gap

    def _enter(self, toast: Toast) -> None:
        current = theme.Theme.instance()
        if current is None:
            return
        fade = QPropertyAnimation(toast.opacity_effect, b"opacity", toast)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        if current.reduce_motion:
            fade.setDuration(current.tokens.reduced_fade())
            fade.setEasingCurve(QEasingCurve(QEasingCurve.Type.Linear))
        else:
            fade.setDuration(current.tokens.duration("settle"))
            fade.setEasingCurve(current.tokens.easing("settle"))
            slide = QPropertyAnimation(toast, b"pos", toast)
            slide.setDuration(current.tokens.duration("settle"))
            slide.setEasingCurve(current.tokens.easing("settle"))
            slide.setStartValue(toast.pos() + QPoint(0, 8))
            slide.setEndValue(toast.pos())
            slide.finished.connect(lambda: setattr(toast, "slide", None))
            toast.slide = slide
            slide.start()
        fade.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        """Keep the stack in the corner when the window resizes.

        Qt can still call the filter while the window is being torn down, after Python has
        already emptied this object's attributes (seen on CI, run 37110221102); then it does
        nothing.
        """
        if event.type() == QEvent.Type.Resize and "host" in vars(self) and watched is self.host:
            self._layout()
        return False
