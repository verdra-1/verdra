# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Turns tokens.json into QPalette and a style sheet; live light/dark switching; text scale;
density.

Master plan 5.6 and 6. Every colour, size and duration comes from `assets/brand/tokens.json` by
name. The style sheet is generated from a template whose only colour references are `{token}`
placeholders, so it never contains a literal colour. Base style is Fusion on every platform.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

import shiboken6
from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFocusEvent,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QIcon,
    QPainter,
    QPaintEvent,
    QPalette,
    QPen,
    QPixmap,
    QRegion,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QProxyStyle,
    QStyle,
    QStyleOption,
    QWidget,
)

import verdra

Mode = Literal["light", "dark"]
ASSETS = Path(verdra.__file__).resolve().parent / "assets"
TOKENS_FILE = ASSETS / "brand" / "tokens.json"
TEXT_STYLE_PROPERTY = "textStyle"

_RGBA = re.compile(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)")
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9-]*)\}")


def parse_color(value: str) -> QColor:
    """Return a QColor for a token value: `#RRGGBB` or `rgba(r, g, b, a)`."""
    match = _RGBA.fullmatch(value.strip())
    if match:
        red, green, blue = (int(match.group(n)) for n in (1, 2, 3))
        return QColor(red, green, blue, round(float(match.group(4)) * 255))
    color = QColor(value)
    if not color.isValid():
        raise ValueError(f"not a colour: {value!r}")
    return color


def css_color(color: QColor) -> str:
    """Return a colour as Qt style sheets read it."""
    if color.alpha() == 255:
        return color.name()
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


@dataclass(frozen=True)
class TextStyle:
    """One entry of the type scale (Master plan 6.1)."""

    name: str
    family: str
    size: int
    line_height: int
    weight: int
    tracking_percent: float
    uppercase: bool


class Tokens:
    """The design tokens, read once from tokens.json."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        self._themes = [theme["id"] for theme in data["color"]["themes"]]
        self._colors = {token["name"]: token["value"] for token in data["color"]["tokens"]}
        self._lengths: dict[str, int] = {}
        for family in ("spacing", "radius", "border", "layout"):
            for token in data[family]["tokens"]:
                self._lengths[token["name"]] = int(str(token["value"]).removesuffix("px"))
        self._motion = {token["name"]: token for token in data["motion"]["tokens"]}
        self._styles = {
            style["name"]: TextStyle(
                name=style["name"],
                family=style["family"],
                size=style["size"],
                line_height=style["lineHeight"],
                weight=style["weight"],
                tracking_percent=style.get("trackingPercent", 0),
                uppercase=style.get("uppercase", False),
            )
            for style in data["type"]["styles"]
        }

    @classmethod
    @cache
    def load(cls) -> Tokens:
        """Return the bundled tokens."""
        return cls(json.loads(TOKENS_FILE.read_text(encoding="utf-8")))

    def color_names(self) -> list[str]:
        """Return every colour token's name."""
        return list(self._colors)

    def color(self, name: str, mode: Mode) -> QColor:
        """Return a colour token's value in a theme, following aliases."""
        value = self._colors[name]
        if isinstance(value, dict):
            value = value.get(mode, value[self._themes[0]])
        if value.startswith("{") and value.endswith("}"):
            return self.color(value[1:-1], mode)
        return parse_color(value)

    def length(self, name: str) -> int:
        """Return a spacing, radius, border or layout token in pixels."""
        return self._lengths[name]

    def style(self, name: str) -> TextStyle:
        """Return a text style from the type scale."""
        return self._styles[name]

    def families(self, role: str) -> list[str]:
        """Return a font role's family list, most preferred first."""
        return list(self._data["type"]["families"][role])

    def font_files(self) -> list[Path]:
        """Return the bundled font files."""
        return [ASSETS / font["file"] for font in self._data["type"]["fonts"]]

    def duration(self, name: str) -> int:
        """Return a motion token's duration in milliseconds."""
        return int(self._motion[name]["duration"])

    def easing(self, name: str) -> QEasingCurve:
        """Return a motion token's cubic Bézier easing as a QEasingCurve."""
        return bezier(*self._motion[name]["easing"])

    def exit_easing(self) -> QEasingCurve:
        """Return the easing every exit uses."""
        return bezier(*self._data["motion"]["exit"]["easing"])

    def exit_duration(self, name: str) -> int:
        """Return the exit duration for a motion token: two-thirds of its entry."""
        return round(self.duration(name) * self._data["motion"]["exit"]["durationFactor"])

    def reduced_fade(self) -> int:
        """Return the longest fade that replaces movement under reduced motion."""
        return int(self._data["motion"]["reduced"]["maxFadeDuration"])


def bezier(x1: float, y1: float, x2: float, y2: float) -> QEasingCurve:
    """Return a CSS-style cubic Bézier easing curve."""
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(QPointF(x1, y1), QPointF(x2, y2), QPointF(1, 1))
    return curve


# --- Palette and style sheet ----------------------------------------------------------------


def palette(tokens: Tokens, mode: Mode) -> QPalette:
    """Return the app palette for a theme (Master plan 5.6)."""
    result = QPalette()
    role = QPalette.ColorRole
    group = QPalette.ColorGroup

    def put(
        roles: list[QPalette.ColorRole], name: str, groups: list[QPalette.ColorGroup] | None = None
    ) -> None:
        color = tokens.color(name, mode)
        for target in groups or [group.Active, group.Inactive, group.Disabled]:
            for each in roles:
                result.setColor(target, each, color)

    put([role.Window, role.AlternateBase], "bg")
    put([role.WindowText, role.Text, role.ButtonText], "ink")
    put([role.Base, role.Button], "surface")
    put([role.PlaceholderText], "ink-muted")
    put([role.ToolTipBase], "tooltip-bg")
    put([role.ToolTipText], "tooltip-ink")
    put([role.Highlight], "primary")
    put([role.HighlightedText, role.BrightText], "on-primary")
    put([role.Link, role.LinkVisited, role.Accent], "primary")
    put([role.Light], "surface")
    put([role.Midlight], "divider")
    put([role.Mid, role.Dark], "border-strong")
    put([role.Shadow], "palette-shadow")
    put([role.WindowText, role.Text, role.ButtonText], "ink-disabled", [group.Disabled])
    return result


# The style sheet template. Every `{name}` is a token: a color (as the current theme has it),
# or a length in pixels. Derived values (`{primary-tint-60}`) are added in `stylesheet`.
STYLESHEET = """
QWidget { color: {ink}; }
QMainWindow, QDialog { background: {bg}; }
QToolTip {
    background: {tooltip-bg};
    color: {tooltip-ink};
    border: none;
    padding: {space-1}px {space-2}px;
}

#sidebar { background: {bg}; border-right: {border-width}px solid {divider}; }
#sidebar QToolButton {
    background: transparent; border: none; border-radius: {radius-m}px;
    padding: {space-2}px {space-3}px; color: {ink-muted}; text-align: left;
}
#sidebar QToolButton:hover { background: {primary-tint-60}; color: {ink}; }
#sidebar QToolButton:checked { background: {primary-tint}; color: {ink}; }

#header { background: {bg}; border-bottom: {border-width}px solid {divider}; }
#content { background: {bg}; }
#panel {
    background: {surface};
    border: {border-width}px solid {divider};
    border-radius: {radius-m}px;
}

QPushButton {
    background: {surface}; color: {ink}; border: {border-width}px solid {border-strong};
    border-radius: {radius-m}px; padding: 0 {space-3}px; min-height: {hit-target-text}px;
}
QPushButton:hover { background: {primary-tint-60}; }
QPushButton:pressed { background: {primary-tint}; }
QPushButton:disabled { color: {ink-disabled}; border-color: {divider}; background: {surface}; }
QPushButton[primary="true"] { background: {primary}; color: {on-primary}; border: none; }
QPushButton[primary="true"]:hover { background: {primary-hover}; }
QPushButton[primary="true"]:pressed { background: {primary-pressed}; }
QPushButton[primary="true"]:disabled { background: {surface-sunken}; color: {ink-disabled}; }
QPushButton[quiet="true"] { background: transparent; border: none; color: {primary}; }
QPushButton[quiet="true"]:hover { text-decoration: underline; }

QToolButton {
    border: none;
    border-radius: {radius-s}px;
    padding: {space-1}px;
    background: transparent;
}
QToolButton:hover { background: {primary-tint-60}; }

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {
    background: {surface-sunken}; color: {ink}; border: {border-width}px solid {border-strong};
    border-radius: {radius-s}px; padding: {space-1}px {space-2}px; min-height: {hit-target-icon}px;
    selection-background-color: {primary}; selection-color: {on-primary};
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {
    color: {ink-disabled};
    border-color: {divider};
}
QComboBox::drop-down {
    subcontrol-origin: padding; subcontrol-position: center right;
    width: {space-6}px; border: none; background: transparent;
}
QSpinBox::up-button, QSpinBox::down-button {
    width: {space-6}px; border: none; background: transparent;
}
QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; }
QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; }
QComboBox::down-arrow, QSpinBox::down-arrow {
    image: url({arrow-down}); width: {space-3}px; height: {space-3}px;
}
QSpinBox::up-arrow { image: url({arrow-up}); width: {space-3}px; height: {space-3}px; }
QComboBox::down-arrow:disabled, QSpinBox::down-arrow:disabled { image: url({arrow-down-disabled}); }
QSpinBox::up-arrow:disabled { image: url({arrow-up-disabled}); }
QComboBox QAbstractItemView {
    background: {surface-raised}; color: {ink}; border: {border-width}px solid {divider};
    selection-background-color: {primary-tint}; selection-color: {ink};
}

QMenu {
    background: {surface-raised};
    color: {ink};
    border: {border-width}px solid {divider};
    padding: {space-1}px;
}
QMenu::item {
    padding: {space-1}px {space-6}px {space-1}px {space-3}px;
    border-radius: {radius-s}px;
}
QMenu::item:selected { background: {primary-tint}; color: {ink}; }
QMenu::item:disabled { color: {ink-disabled}; }
QMenu::separator { height: {border-width}px; background: {divider}; margin: {space-1}px 0; }

QTableView, QListView, QTreeView {
    background: {surface}; alternate-background-color: {bg}; color: {ink};
    border: {border-width}px solid {divider}; border-radius: {radius-m}px;
    gridline-color: {divider}; selection-background-color: {primary-tint}; selection-color: {ink};
}
QHeaderView::section {
    background: {surface}; color: {ink-muted}; border: none;
    border-bottom: {border-width}px solid {divider}; padding: {space-1}px {space-2}px;
}

QFrame[popover="true"] {
    background: {surface-raised};
    border: {border-width}px solid {divider};
    border-radius: {radius-m}px;
}
QFrame[toast="true"] {
    background: {surface-raised};
    border: {border-width}px solid {divider};
    border-radius: {radius-m}px;
}
QLabel[muted="true"] { color: {ink-muted}; }
QLabel[link="true"] { color: {primary}; }
"""


def stylesheet(tokens: Tokens, mode: Mode) -> str:
    """Fill the style sheet template from the tokens for one theme."""
    values: dict[str, str] = {}
    for name in tokens.color_names():
        values[name] = css_color(tokens.color(name, mode))
    tint = tokens.color("primary-tint", mode)
    tint.setAlphaF(0.6)
    values["primary-tint-60"] = css_color(tint)
    # The combo and spin box chevrons, generated from the tokens by tools/icons.py.
    for direction in ("up", "down"):
        for suffix in ("", "-disabled"):
            arrow = ASSETS / "brand" / f"arrow-{direction}-{mode}{suffix}.svg"
            values[f"arrow-{direction}{suffix}"] = arrow.as_posix()

    def fill(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in values:
            return values[name]
        return str(tokens.length(name))

    return _PLACEHOLDER.sub(fill, STYLESHEET)


# --- Fonts ----------------------------------------------------------------------------------


def register_fonts(tokens: Tokens) -> list[str]:
    """Register the bundled fonts with Qt and return the families they provide."""
    families: list[str] = []
    for path in tokens.font_files():
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families += QFontDatabase.applicationFontFamilies(font_id)
    return families


def font(tokens: Tokens, name: str, scale: int = 100) -> QFont:
    """Return a QFont for a text style at a text-size percentage (pixel sizes, plan 6.2)."""
    style = tokens.style(name)
    result = QFont()
    result.setFamilies(tokens.families(style.family))
    result.setPixelSize(max(1, round(style.size * scale / 100)))
    result.setWeight(QFont.Weight(style.weight))
    if style.tracking_percent:
        result.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100 + style.tracking_percent)
    if style.uppercase:
        result.setCapitalization(QFont.Capitalization.AllUppercase)
    if style.family == "mono":
        result.setStyleHint(QFont.StyleHint.Monospace)
    return result


def set_text_style(widget: QWidget, name: str) -> None:
    """Give a widget a text style; the theme keeps its font current when the text size changes."""
    widget.setProperty(TEXT_STYLE_PROPERTY, name)
    theme = Theme.instance()
    tokens = theme.tokens if theme else Tokens.load()
    widget.setFont(font(tokens, name, theme.text_scale if theme else 100))


# --- Icons ----------------------------------------------------------------------------------


#: Icons at this size or smaller use a custom icon's hand-tuned 16 px variant (plan 6.8).
SMALL_ICON = 16


@cache
def _icon_source(name: str, small: bool = False) -> str:
    folders = (("custom", "16"), ("custom",), ("lucide",)) if small else (("custom",), ("lucide",))
    for folder in folders:
        path = ASSETS.joinpath("icons", *folder, f"{name}.svg")
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise KeyError(f"no icon named {name!r}")


def icon_pixmap(name: str, color: QColor, size: int, ratio: float = 1.0) -> QPixmap:
    """Render an icon from the bundled set in one colour."""
    svg = _icon_source(name, size <= SMALL_ICON).replace("currentColor", color.name())
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixels = max(1, round(size * ratio))
    pixmap = QPixmap(pixels, pixels)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, pixels, pixels))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def svg_pixmap(path: Path, size: int, ratio: float = 1.0) -> QPixmap:
    """Render a bundled SVG file (a brand file) into a square pixmap, keeping its aspect."""
    renderer = QSvgRenderer(QByteArray(path.read_bytes()))
    pixels = max(1, round(size * ratio))
    pixmap = QPixmap(pixels, pixels)
    pixmap.fill(Qt.GlobalColor.transparent)
    box = renderer.viewBoxF()
    scale = pixels / max(box.width(), box.height(), 1.0)
    width, height = box.width() * scale, box.height() * scale
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF((pixels - width) / 2, (pixels - height) / 2, width, height))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def icon(
    name: str,
    rest: str = "ink-muted",
    size: int = 20,
    *,
    active: str = "ink",
) -> QIcon:
    """Return a QIcon recoloured from tokens: `rest` normally, `active` on hover and checked."""
    theme = Theme.instance()
    tokens = theme.tokens if theme else Tokens.load()
    mode: Mode = theme.mode if theme else "light"
    app = QGuiApplication.instance()
    ratio = app.devicePixelRatio() if isinstance(app, QGuiApplication) else 1.0
    result = QIcon()
    normal = icon_pixmap(name, tokens.color(rest, mode), size, ratio)
    hot = icon_pixmap(name, tokens.color(active, mode), size, ratio)
    result.addPixmap(normal, QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(hot, QIcon.Mode.Active, QIcon.State.Off)
    result.addPixmap(hot, QIcon.Mode.Normal, QIcon.State.On)
    result.addPixmap(hot, QIcon.Mode.Active, QIcon.State.On)
    result.addPixmap(
        icon_pixmap(name, tokens.color("ink-disabled", mode), size, ratio), QIcon.Mode.Disabled
    )
    return result


def brand_file(name: str) -> Path:
    """Return the path of a generated brand SVG (symbol, wordmark, tray icons)."""
    return ASSETS / "brand" / name


# --- The live theme -------------------------------------------------------------------------


class VerdraStyle(QProxyStyle):
    """Fusion with Verdra's focus ring: 2 px solid, 2 px outside the control (plan 5.2, 6.4).

    A style sheet can only draw inside a widget, so the ring is drawn on a `FocusRing` overlay
    around the focused control, through this style's PE_FrameFocusRect. The focus rectangles
    that controls would draw inside themselves are left out, so there is exactly one ring.
    """

    def __init__(self, tokens: Tokens) -> None:
        """Base the style on Fusion (plan 6: the same base style on every platform)."""
        super().__init__("Fusion")
        self.tokens = tokens
        self.mode: Mode = "light"

    def ring_width(self) -> int:
        """Return the ring's width in pixels (token focus-width)."""
        return self.tokens.length("focus-width")

    def ring_offset(self) -> int:
        """Return the gap between the control and its ring in pixels (token focus-offset)."""
        return self.tokens.length("focus-offset")

    def drawPrimitive(  # noqa: N802 - Qt's method name
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw the ring for the overlay; skip focus rectangles inside controls."""
        if element != QStyle.PrimitiveElement.PE_FrameFocusRect:
            super().drawPrimitive(element, option, painter, widget)
            return
        if not isinstance(widget, FocusRing):
            return
        width = self.ring_width()
        radius = self.tokens.length("radius-m") + self.ring_offset()
        pen = QPen(self.tokens.color("focus-ring", self.mode), width)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        half = width / 2
        painter.drawRoundedRect(
            QRectF(option.rect).adjusted(half, half, -half, -half), radius, radius
        )
        painter.restore()


class FocusRing(QWidget):
    """A transparent overlay that shows the focus ring around the keyboard-focused control.

    It sits on the control's window, follows the control when it moves or resizes, and hides
    when focus goes away or comes from the mouse (the ring marks keyboard focus).
    """

    def __init__(self, style: VerdraStyle) -> None:
        """Track focus across the application."""
        super().__init__(None)
        self._style = style
        self.target: QWidget | None = None
        self._placing = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("focusRing")
        self.hide()

    def follow(self, widget: QWidget | None, reason: Qt.FocusReason) -> None:
        """Ring `widget`, or hide when it is None or focused with the mouse."""
        if self.target is not None and shiboken6.isValid(self.target):
            self._watch(self.target, watch=False)
            self.target.destroyed.disconnect(self._target_destroyed)
        self.target = None
        keyboard = reason != Qt.FocusReason.MouseFocusReason
        if widget is None or not keyboard or widget.window() is widget or widget is self:
            self.hide()
            return
        # The inner line edit of a spin box or editable combo box passes focus to the control
        # (its focus proxy); the ring goes around the whole control.
        while (proxy := widget.focusProxy()) is not None:
            widget = proxy
        self.target = widget
        self._watch(widget, watch=True)
        widget.destroyed.connect(self._target_destroyed)
        self.place()

    def _target_destroyed(self) -> None:
        # The focused control was deleted (a list row rebuilt, say): drop the ring.
        self.target = None
        if shiboken6.isValid(self):
            self.hide()

    def place(self) -> None:
        """Put the overlay around the target, on the target's window."""
        target = self.target
        if target is None or not shiboken6.isValid(target) or not target.isVisible():
            self.hide()
            return
        if self._placing:
            return
        self._placing = True
        try:
            window = target.window()
            if self.parentWidget() is not window:
                self.setParent(window)
            margin = self._style.ring_offset() + self._style.ring_width()
            corner = target.mapTo(window, QPoint(0, 0))
            geometry = QRect(
                corner.x() - margin,
                corner.y() - margin,
                target.width() + 2 * margin,
                target.height() + 2 * margin,
            )
            if geometry != self.geometry():
                self.setGeometry(geometry)
            # Inside a scroll area, show only the part of the ring within its viewport.
            visible = QRect(QPoint(0, 0), geometry.size())
            for viewport in _viewports(target):
                area = QRect(viewport.mapTo(window, QPoint(0, 0)), viewport.size())
                visible &= area.translated(-geometry.topLeft())
            if visible.isEmpty():
                self.hide()
                return
            self.setMask(QRegion(visible))
            if not self.isVisible():
                self.show()
            self.raise_()
        finally:
            self._placing = False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt's name
        """Re-place the ring when the target or one of its parents moves, resizes or hides."""
        if event.type() in {
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.Hide,
        }:
            self.place()
        return False

    def _watch(self, widget: QWidget, *, watch: bool) -> None:
        current: QWidget | None = widget
        while current is not None and shiboken6.isValid(current):
            if watch:
                current.installEventFilter(self)
            else:
                current.removeEventFilter(self)
            if current.isWindow():
                break
            current = current.parentWidget()

    def paintEvent(self, _event: QPaintEvent) -> None:  # noqa: N802 - Qt's method name
        """Draw the ring through the style."""
        option = QStyleOption()
        option.initFrom(self)
        option.rect = self.rect()
        painter = QPainter(self)
        self._style.drawPrimitive(QStyle.PrimitiveElement.PE_FrameFocusRect, option, painter, self)
        painter.end()


def _viewports(widget: QWidget) -> list[QWidget]:
    """Return the scroll-area viewports that contain `widget`, innermost first."""
    found = []
    current = widget.parentWidget()
    while current is not None and not current.isWindow():
        area = current.parentWidget()
        if isinstance(area, QAbstractScrollArea) and area.viewport() is current:
            found.append(current)
        current = area
    return found


class FocusTracker(QObject):
    """Moves the focus ring to each control that receives focus, with the focus reason.

    The ring lives on the focused control's window and goes when that window does, so the
    tracker makes a new one when it needs one.
    """

    def __init__(self, app: QApplication, style: VerdraStyle) -> None:
        """Watch every focus change in `app`."""
        super().__init__(app)
        self.style = style
        self._ring: FocusRing | None = None
        app.installEventFilter(self)

    @property
    def ring(self) -> FocusRing:
        """Return the focus ring, making a new one if its window has been closed."""
        if self._ring is None or not shiboken6.isValid(self._ring):
            self._ring = FocusRing(self.style)
        return self._ring

    def update(self) -> None:
        """Repaint the ring (after a theme change)."""
        if self._ring is not None and shiboken6.isValid(self._ring):
            self._ring.update()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt's name
        """Follow focus-in events; drop the ring when its control loses focus."""
        kind = event.type()
        if kind == QEvent.Type.FocusIn and isinstance(watched, QWidget):
            if isinstance(event, QFocusEvent) and watched.hasFocus():
                self.ring.follow(watched, event.reason())
            return False
        ring = self._ring
        lost = kind == QEvent.Type.FocusOut and ring is not None and shiboken6.isValid(ring)
        if lost and ring is not None and watched is ring.target:
            ring.follow(None, Qt.FocusReason.OtherFocusReason)
        return False


class Theme(QObject):
    """Applies the tokens to the running app and follows the settings and the OS.

    Signals:
        changed(): The theme, text size, density or motion preference changed; widgets that
            paint themselves should repaint.
    """

    changed = Signal()
    _instance: Theme | None = None

    def __init__(
        self,
        app: QApplication,
        settings: Any,
        tokens: Tokens | None = None,
        os_reduce_motion: bool | None = None,
    ) -> None:
        """Set up the theme for `app` and apply it.

        Args:
            app: The application.
            settings: The settings store (appearance keys, change signal).
            tokens: The design tokens; loaded from the bundled tokens.json if not given.
            os_reduce_motion: The OS's reduced-motion preference, which trunk asks the system
                for at startup (canopy makes no OS calls of its own, Reference R1); None if
                unknown.
        """
        super().__init__(app)
        self.app = app
        self.settings = settings
        self.tokens = tokens or Tokens.load()
        self.mode: Mode = "light"
        self.text_scale = 100
        self.density = "comfortable"
        self.reduce_motion = False
        self._os_reduce_motion = os_reduce_motion
        previous, Theme._instance = Theme._instance, self
        register_fonts(self.tokens)
        # Fusion on every platform, with Verdra's focus ring (plan 6.4, QProxyStyle).
        self.style = VerdraStyle(self.tokens)
        app.setStyle(self.style)
        if previous is not None and shiboken6.isValid(previous.focus_tracker):
            app.removeEventFilter(previous.focus_tracker)
        self.focus_tracker = FocusTracker(app, self.style)
        app.styleHints().colorSchemeChanged.connect(self._os_scheme_changed)
        settings.changed.connect(self._setting_changed)
        self.apply()

    @classmethod
    def instance(cls) -> Theme | None:
        """Return the running theme, if the app has one."""
        return cls._instance

    def resolve_mode(self) -> Mode:
        """Return the theme to show: the setting, or the OS scheme for "Match system"."""
        chosen = self.settings.value("appearance.theme")
        if chosen in ("light", "dark"):
            return chosen
        return "dark" if self.os_scheme() == Qt.ColorScheme.Dark else "light"

    def os_scheme(self) -> Qt.ColorScheme:
        """Return the colour scheme the OS reports."""
        return self.app.styleHints().colorScheme()

    def apply(self) -> None:
        """Apply palette, style sheet, fonts and preferences from the current settings."""
        self.mode = self.resolve_mode()
        self.text_scale = int(self.settings.value("appearance.text_scale"))
        self.density = str(self.settings.value("appearance.density"))
        choice = self.settings.value("appearance.reduce_motion")
        self.reduce_motion = choice == "on" or (choice == "system" and bool(self._os_reduce_motion))
        # The font goes first: setting the style sheet re-polishes every widget, which is what
        # makes widgets that already exist take the new text size (plan 6.2, live).
        self.app.setFont(font(self.tokens, "body", self.text_scale))
        self.app.setPalette(palette(self.tokens, self.mode))
        self.app.setStyleSheet(stylesheet(self.tokens, self.mode))
        self.style.mode = self.mode
        self.focus_tracker.update()
        for widget in self.app.allWidgets():
            name = widget.property(TEXT_STYLE_PROPERTY)
            if isinstance(name, str) and name:
                widget.setFont(font(self.tokens, name, self.text_scale))
        self.changed.emit()

    def color(self, name: str) -> QColor:
        """Return a colour token in the current theme."""
        return self.tokens.color(name, self.mode)

    def padding(self) -> int:
        """Return panel padding for the current density (space-4, or space-3 when compact)."""
        return self.tokens.length("space-3" if self.density == "compact" else "space-4")

    def row_height(self) -> int:
        """Return the table row height for the current density."""
        return self.tokens.length(
            "row-height-compact" if self.density == "compact" else "row-height"
        )

    def _os_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self.settings.value("appearance.theme") == "system":
            self.apply()

    def _setting_changed(self, key: str, _value: object) -> None:
        if key.startswith("appearance."):
            self.apply()
