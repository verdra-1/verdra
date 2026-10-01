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

from PySide6.QtCore import QByteArray, QEasingCurve, QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QIcon,
    QPainter,
    QPalette,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QWidget

import verdra
from verdra.soil import humus

Mode = Literal["light", "dark"]
ASSETS = Path(verdra.__file__).resolve().parent / "assets"
TOKENS_FILE = ASSETS / "brand" / "tokens.json"
TEXT_STYLE_PROPERTY = "textStyle"

_RGBA = re.compile(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)")
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9-]*)\}")


def parse_colour(value: str) -> QColor:
    """Return a QColor for a token value: `#RRGGBB` or `rgba(r, g, b, a)`."""
    match = _RGBA.fullmatch(value.strip())
    if match:
        red, green, blue = (int(match.group(n)) for n in (1, 2, 3))
        return QColor(red, green, blue, round(float(match.group(4)) * 255))
    colour = QColor(value)
    if not colour.isValid():
        raise ValueError(f"not a colour: {value!r}")
    return colour


def css_colour(colour: QColor) -> str:
    """Return a colour as Qt style sheets read it."""
    if colour.alpha() == 255:
        return colour.name()
    return f"rgba({colour.red()}, {colour.green()}, {colour.blue()}, {colour.alpha()})"


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
        self._colours = {token["name"]: token["value"] for token in data["color"]["tokens"]}
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

    def colour_names(self) -> list[str]:
        """Return every colour token's name."""
        return list(self._colours)

    def colour(self, name: str, mode: Mode) -> QColor:
        """Return a colour token's value in a theme, following aliases."""
        value = self._colours[name]
        if isinstance(value, dict):
            value = value.get(mode, value[self._themes[0]])
        if value.startswith("{") and value.endswith("}"):
            return self.colour(value[1:-1], mode)
        return parse_colour(value)

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
        colour = tokens.colour(name, mode)
        for target in groups or [group.Active, group.Inactive, group.Disabled]:
            for each in roles:
                result.setColor(target, each, colour)

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


# The style sheet template. Every `{name}` is a token: a colour (as the current theme has it),
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
#sidebar QToolButton:focus { border: {focus-width}px solid {focus-ring}; }

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
QPushButton:focus { border: {focus-width}px solid {focus-ring}; }
QPushButton:disabled { color: {ink-disabled}; border-color: {divider}; background: {surface}; }
QPushButton[primary="true"] { background: {primary}; color: {on-primary}; border: none; }
QPushButton[primary="true"]:hover { background: {primary-hover}; }
QPushButton[primary="true"]:pressed { background: {primary-pressed}; }
QPushButton[primary="true"]:focus { border: {focus-width}px solid {focus-ring}; }
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
QToolButton:checked { background: {primary-tint}; color: {ink}; }
QToolButton:focus { border: {focus-width}px solid {focus-ring}; }

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {
    background: {surface-sunken}; color: {ink}; border: {border-width}px solid {border-strong};
    border-radius: {radius-s}px; padding: {space-1}px {space-2}px; min-height: {hit-target-icon}px;
    selection-background-color: {primary}; selection-color: {on-primary};
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {
    border: {focus-width}px solid {focus-ring};
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {
    color: {ink-disabled};
    border-color: {divider};
}
QComboBox QAbstractItemView {
    background: {surface-raised}; color: {ink}; border: {border-width}px solid {divider};
    selection-background-color: {primary-tint}; selection-color: {ink};
}
QCheckBox:focus, QRadioButton:focus {
    border: {focus-width}px solid {focus-ring};
    border-radius: {radius-s}px;
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
    for name in tokens.colour_names():
        values[name] = css_colour(tokens.colour(name, mode))
    tint = tokens.colour("primary-tint", mode)
    tint.setAlphaF(0.6)
    values["primary-tint-60"] = css_colour(tint)

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


@cache
def _icon_source(name: str) -> str:
    for folder in ("custom", "lucide"):
        path = ASSETS / "icons" / folder / f"{name}.svg"
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise KeyError(f"no icon named {name!r}")


def icon_pixmap(name: str, colour: QColor, size: int, ratio: float = 1.0) -> QPixmap:
    """Render an icon from the bundled set in one colour."""
    svg = _icon_source(name).replace("currentColor", colour.name())
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
    """Render a bundled SVG file (a brand file) with its longest side `size` pixels long."""
    renderer = QSvgRenderer(QByteArray(path.read_bytes()))
    box = renderer.viewBoxF()
    scale = size / max(box.width(), box.height(), 1.0)
    width = max(1, round(box.width() * scale * ratio))
    height = max(1, round(box.height() * scale * ratio))
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, width, height))
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
    normal = icon_pixmap(name, tokens.colour(rest, mode), size, ratio)
    hot = icon_pixmap(name, tokens.colour(active, mode), size, ratio)
    result.addPixmap(normal, QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(hot, QIcon.Mode.Active, QIcon.State.Off)
    result.addPixmap(hot, QIcon.Mode.Normal, QIcon.State.On)
    result.addPixmap(hot, QIcon.Mode.Active, QIcon.State.On)
    result.addPixmap(
        icon_pixmap(name, tokens.colour("ink-disabled", mode), size, ratio), QIcon.Mode.Disabled
    )
    return result


def brand_file(name: str) -> Path:
    """Return the path of a generated brand SVG (symbol, wordmark, tray icons)."""
    return ASSETS / "brand" / name


# --- The live theme -------------------------------------------------------------------------


class Theme(QObject):
    """Applies the tokens to the running app and follows the settings and the OS.

    Signals:
        changed(): The theme, text size, density or motion preference changed; widgets that
            paint themselves should repaint.
    """

    changed = Signal()
    _instance: Theme | None = None

    def __init__(self, app: QApplication, settings: Any, tokens: Tokens | None = None) -> None:
        super().__init__(app)
        self.app = app
        self.settings = settings
        self.tokens = tokens or Tokens.load()
        self.mode: Mode = "light"
        self.text_scale = 100
        self.density = "comfortable"
        self.reduce_motion = False
        self._os_reduce_motion = humus.prefers_reduced_motion()
        Theme._instance = self
        register_fonts(self.tokens)
        app.setStyle("Fusion")
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
        self.app.setPalette(palette(self.tokens, self.mode))
        self.app.setStyleSheet(stylesheet(self.tokens, self.mode))
        self.app.setFont(font(self.tokens, "body", self.text_scale))
        for widget in self.app.allWidgets():
            name = widget.property(TEXT_STYLE_PROPERTY)
            if isinstance(name, str) and name:
                widget.setFont(font(self.tokens, name, self.text_scale))
        self.changed.emit()

    def colour(self, name: str) -> QColor:
        """Return a colour token in the current theme."""
        return self.tokens.colour(name, self.mode)

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
