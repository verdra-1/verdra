# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Splash window (480 × 300) and the Living V growth animation.

Master plan 4.5. Both leaves grow from the node outward, scaling from 0 to 1 around the point
where they meet (32, 55.5 on the 64 grid): the left leaf first and the right leaf 80 ms later,
each over 560 ms with the `bloom` easing. Then the node pulses once (1 → 1.15 → 1 over 240 ms),
and the wordmark fades in over 240 ms. With reduced motion, the whole lockup fades in over
150 ms and nothing scales. The splash stays at least 900 ms and closes when the window is ready.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QGuiApplication, QPainter, QPaintEvent
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

import verdra
from verdra.canopy.crown import theme

WIDTH, HEIGHT = 480, 300
SYMBOL_HEIGHT = 96
WORDMARK_CAP_HEIGHT = 32
MINIMUM_MS = 900
GRID = 64.0
ANCHOR = QPointF(32.0, 55.5)
NODE_CENTER = QPointF(32.0, 59.6)
LEAF_MS = 560
RIGHT_LEAF_DELAY_MS = 80
PULSE_MS = 240
WORDMARK_MS = 240
PULSE_SCALE = 0.15
SYMBOL_BOX = (5.0, 6.0, 59.0, 63.0)  # ink bounds of the symbol on the 64 grid (approximate top)
CAP_TO_UNITS = 0.70  # the wordmark's cap height as a share of its view-box height


class Splash(QWidget):
    """The frameless splash with its timeline driven by one animation (0 to 1)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(WIDTH, HEIGHT)
        self.setAccessibleName(self.tr("Verdra is starting"))
        current = theme.Theme.instance()
        dark = current is not None and current.mode == "dark"
        suffix = "-reversed" if dark else ""
        self._symbol = QSvgRenderer(
            QByteArray(theme.brand_file(f"symbol{suffix}.svg").read_bytes())
        )
        self._wordmark = QSvgRenderer(
            QByteArray(theme.brand_file(f"wordmark{suffix}.svg").read_bytes())
        )
        self.reduced = current is not None and current.reduce_motion
        self.total_ms = (
            current.tokens.reduced_fade()
            if self.reduced and current
            else RIGHT_LEAF_DELAY_MS + LEAF_MS + PULSE_MS
        )
        self.elapsed_ms = 0.0
        self.shown_at: float | None = None
        self._then: Callable[[], None] | None = None
        self._timeline = QVariantAnimation(self)
        self._timeline.setStartValue(0.0)
        self._timeline.setEndValue(float(self.total_ms))
        self._timeline.setDuration(self.total_ms)
        self._timeline.valueChanged.connect(self._advance)
        self._bloom = current.tokens.easing("bloom") if current else theme.bezier(0.16, 1, 0.3, 1)
        self._close_timer = QTimer(self)

    def start(self) -> None:
        """Show the splash centred on the primary screen and run the animation."""
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            center = screen.availableGeometry().center()
            self.move(center.x() - WIDTH // 2, center.y() - HEIGHT // 2)
        self.shown_at = time.monotonic()
        self.show()
        self._timeline.start()

    def finish(self, then: Callable[[], None] | None = None) -> None:
        """Close once the splash has been visible for at least 900 ms, then call `then`."""
        self._then = then
        # A timer may fire a little early (coarse timers by up to 5 %, and on Windows even a
        # precise timer can come in under a millisecond short), so the elapsed time is checked
        # again whenever it fires: the 900 ms minimum is a promise.
        self._close_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._close_timer.setSingleShot(True)
        self._close_timer.timeout.connect(self._close_when_due)
        self._close_when_due()

    def _close_when_due(self) -> None:
        waited = 0.0 if self.shown_at is None else (time.monotonic() - self.shown_at) * 1000
        if waited < MINIMUM_MS:
            self._close_timer.start(math.ceil(MINIMUM_MS - waited) + 1)
            return
        self.close()
        self.deleteLater()  # it is shown once; nothing keeps a closed splash
        if self._then is not None:
            self._then()

    def _advance(self, value: object) -> None:
        self.elapsed_ms = float(value)  # type: ignore[arg-type]
        self.update()

    # --- Timeline -------------------------------------------------------------------------

    def leaf_scale(self, delay_ms: float) -> float:
        """Return a leaf's scale (0 to 1) at the current time."""
        if self.reduced:
            return 1.0
        progress = min(1.0, max(0.0, (self.elapsed_ms - delay_ms) / LEAF_MS))
        return self._bloom.valueForProgress(progress)

    def node_scale(self) -> float:
        """Return the node's scale: 1, rising to 1.15 and back during the pulse."""
        if self.reduced:
            return 1.0
        start = RIGHT_LEAF_DELAY_MS + LEAF_MS
        progress = (self.elapsed_ms - start) / PULSE_MS
        if progress <= 0 or progress >= 1:
            return 1.0
        return 1.0 + PULSE_SCALE * (1 - abs(2 * progress - 1))

    def opacity(self) -> float:
        """Return the whole lockup's opacity (only below 1 under reduced motion)."""
        if not self.reduced:
            return 1.0
        return min(1.0, self.elapsed_ms / max(1, self.total_ms))

    def wordmark_opacity(self) -> float:
        """Return the wordmark's opacity: it fades in as the node pulse ends."""
        if self.reduced:
            return self.opacity()
        start = RIGHT_LEAF_DELAY_MS + LEAF_MS + PULSE_MS - WORDMARK_MS
        return min(1.0, max(0.0, (self.elapsed_ms - start) / WORDMARK_MS))

    # --- Painting -------------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        """Paint background, the growing symbol, the wordmark and the version."""
        current = theme.Theme.instance()
        tokens = current.tokens if current else theme.Tokens.load()
        mode: theme.Mode = current.mode if current else "light"
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), tokens.color("bg", mode))
        painter.setOpacity(self.opacity())

        scale = SYMBOL_HEIGHT / GRID
        wordmark_box = self._wordmark.viewBoxF()
        wordmark_height = WORDMARK_CAP_HEIGHT / CAP_TO_UNITS
        wordmark_width = wordmark_box.width() * wordmark_height / max(1.0, wordmark_box.height())
        gap = 0.25 * SYMBOL_HEIGHT
        block = SYMBOL_HEIGHT + gap + wordmark_height
        top = (HEIGHT - block) / 2 - 8
        origin = QPointF((WIDTH - GRID * scale) / 2, top)

        for element, delay in (("left-leaf", 0.0), ("right-leaf", float(RIGHT_LEAF_DELAY_MS))):
            self._draw_part(
                painter,
                element,
                origin=origin,
                scale=scale,
                anchor=ANCHOR,
                grow=self.leaf_scale(delay),
            )
        self._draw_part(
            painter, "node", origin=origin, scale=scale, anchor=NODE_CENTER, grow=self.node_scale()
        )

        painter.save()
        painter.setOpacity(painter.opacity() * self.wordmark_opacity())
        target = QRectF(
            (WIDTH - wordmark_width) / 2, top + SYMBOL_HEIGHT + gap, wordmark_width, wordmark_height
        )
        self._wordmark.render(painter, target)
        painter.restore()

        theme.set_text_style(self, "caption")
        painter.setFont(self.font())
        painter.setPen(tokens.color("ink-muted", mode))
        version = self.tr("Version {version}").format(version=verdra.__version__)
        painter.drawText(QRectF(0, HEIGHT - 32, WIDTH, 20), Qt.AlignmentFlag.AlignCenter, version)
        painter.end()

    def _draw_part(
        self,
        painter: QPainter,
        element: str,
        *,
        origin: QPointF,
        scale: float,
        anchor: QPointF,
        grow: float,
    ) -> None:
        if grow <= 0:
            return
        bounds = self._symbol.boundsOnElement(element)
        painter.save()
        painter.translate(origin)
        painter.scale(scale, scale)
        painter.translate(anchor)
        painter.scale(grow, grow)
        painter.translate(-anchor)
        self._symbol.render(painter, element, bounds)
        painter.restore()
