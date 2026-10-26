# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The status light: the whole Verdra leaf, one colour and shape per state (0027 item 4).

The whole Verdra leaf is the status light: it takes the state's colour and also has its own shape
per state, so it reads in grayscale and in Windows contrast themes. The working leaf breathes
slowly, but only in the window (the tray icon, drawn from the same SVGs, never animates). The
leaf shapes and colours live in the generated ``leaf-<state>-<theme>.svg`` brand assets; this
widget renders them for the current theme and runs the breathing.

The accessible name is the caller's to set (the status word comes from the message catalogue
where the leaf is placed), so this stays a pure visual component.
"""

from __future__ import annotations

import math
from enum import Enum

from PySide6.QtCore import QRectF, QSize, QVariantAnimation
from PySide6.QtGui import QPaintEvent
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QSizePolicy, QWidget

from verdra.canopy.crown import theme

#: One breathing cycle of the working leaf, in milliseconds (slow, calm).
BREATHE_MS = 2400
#: The working leaf fades between this opacity and full while it breathes.
BREATHE_MIN_OPACITY = 0.55


class LeafState(Enum):
    """The five status-light states. The value is the asset name (``leaf-<value>-<theme>.svg``)."""

    WORKING = "working"
    WAITING = "waiting"
    NEEDS_YOU = "needs-you"
    STOPPED = "stopped"
    OFF = "off"


class StatusLeaf(QWidget):
    """The status leaf at a fixed pixel size; ``set_state`` changes the state it shows."""

    def __init__(self, size: int = 24, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self._state = LeafState.OFF
        self._renderer = QSvgRenderer(self)
        self._phase = 0.0  # 0..1 breathing position (0 = full)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # Loop forever; it runs only while the working leaf is shown and motion is allowed.
        self._breath = QVariantAnimation(self)
        self._breath.setStartValue(0.0)
        self._breath.setEndValue(1.0)
        self._breath.setDuration(BREATHE_MS)
        self._breath.setLoopCount(-1)
        self._breath.valueChanged.connect(self._on_breath)
        current = theme.Theme.instance()
        if current is not None:
            current.changed.connect(self._reload)
        self._reload()

    @property
    def state(self) -> LeafState:
        """Return the state the leaf shows."""
        return self._state

    def set_state(self, state: LeafState) -> None:
        """Show a state, and start or stop the breathing to match it."""
        if state is self._state:
            return
        self._state = state
        self._reload()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        """Return the leaf's fixed size."""
        return QSize(self._size, self._size)

    def _reload(self) -> None:
        """Load the SVG for the current state and theme, and update the breathing."""
        current = theme.Theme.instance()
        mode: theme.Mode = current.mode if current else "light"
        path = theme.brand_file(f"leaf-{self._state.value}-{mode}.svg")
        self._renderer.load(path.as_posix())
        self._update_breath()
        self.update()

    def _update_breath(self) -> None:
        """Run the breathing only for the working leaf, in the window, with motion allowed."""
        current = theme.Theme.instance()
        reduce_motion = current.reduce_motion if current else False
        breathe = self._state is LeafState.WORKING and self.isVisible() and not reduce_motion
        if breathe and self._breath.state() != QVariantAnimation.State.Running:
            self._breath.start()
        elif not breathe and self._breath.state() == QVariantAnimation.State.Running:
            self._breath.stop()
            self._phase = 0.0
            self.update()

    def _on_breath(self, value: object) -> None:
        self._phase = float(value) if isinstance(value, (int, float)) else 0.0
        self.update()

    def showEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)  # type: ignore[arg-type]
        self._update_breath()

    def hideEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        super().hideEvent(event)  # type: ignore[arg-type]
        self._update_breath()

    def _opacity(self) -> float:
        """Return the current paint opacity: full, unless the working leaf is mid-breath."""
        if self._breath.state() != QVariantAnimation.State.Running:
            return 1.0
        # A smooth pulse: full at the ends of the cycle, BREATHE_MIN_OPACITY at the middle.
        dip = (1.0 - math.cos(2.0 * math.pi * self._phase)) / 2.0
        return 1.0 - (1.0 - BREATHE_MIN_OPACITY) * dip

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        """Render the leaf SVG into the widget, applying the breathing opacity."""
        from PySide6.QtGui import QPainter  # noqa: PLC0415

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity())
        side = min(self.width(), self.height())
        offset_x = (self.width() - side) / 2.0
        offset_y = (self.height() - side) / 2.0
        self._renderer.render(painter, QRectF(offset_x, offset_y, side, side))
        painter.end()
