# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Accessibility basics from Master plan 12.5 on every M0 screen and dialog.

Text sizes 90 % to 130 % without clipping (review finding H5): at each size, every visible
label, button and choice field must be at least as large as Qt says its content needs.
"""

from collections.abc import Callable

import pytest
from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox, QLabel, QScrollArea, QWidget
from pytestqt.qtbot import QtBot

from verdra.canopy.crown.about import AboutDialog
from verdra.canopy.crown.seedling import Onboarding
from verdra.canopy.crown.window import Shell
from verdra.canopy.leaves.dialogs import DestructiveConfirmation, Explanation, RiskWarning
from verdra.canopy.leaves.switch import Switch
from verdra.canopy.screens.rings import BundleDialog
from verdra.trunk.sapwood.startup import Services

SCREENS = ["replacements", "library", "tweaks", "accounts", "activity", "settings", "traffic"]
SCALES = [90, 100, 115, 130]


def clipped(root: QWidget) -> list[str]:
    """Return one line per visible widget that is smaller than its content needs."""
    problems = []
    for widget in [root, *root.findChildren(QWidget)]:
        if not widget.isVisible() or widget.width() <= 0:
            continue
        if isinstance(widget, QLabel) and widget.text():
            if widget.wordWrap():
                need_width, need_height = 0, widget.heightForWidth(widget.width())
            else:
                hint = widget.sizeHint()
                need_width, need_height = hint.width(), hint.height()
            name = widget.text()[:40]
        elif isinstance(widget, QAbstractButton | QComboBox):
            hint = widget.sizeHint()
            need_width, need_height = hint.width(), hint.height()
            name = widget.text() if isinstance(widget, QAbstractButton) else widget.currentText()
        else:
            continue
        if widget.width() + 1 < need_width or widget.height() + 1 < need_height:
            problems.append(
                f"{type(widget).__name__} {name!r}: {widget.width()}x{widget.height()}, "
                f"needs {need_width}x{need_height}"
            )
    return problems


def settle(qtbot: QtBot) -> None:
    for _ in range(3):
        qtbot.wait(20)


@pytest.mark.parametrize("scale", SCALES)
def test_screens_do_not_clip_at_any_text_size(
    shell: Shell, services: Services, qtbot: QtBot, scale: int
) -> None:
    services.settings.set("advanced.advanced_mode", True)  # shows the Traffic screen too
    services.settings.set("appearance.text_scale", scale)
    window = shell.window
    window.resize(window.minimumSize())  # the smallest window the user can make
    window.show()
    problems = []
    for key in SCREENS:
        window.show_screen(key)
        settle(qtbot)
        problems += [f"{key}: {problem}" for problem in clipped(window)]
    assert problems == []


DIALOGS: dict[str, Callable[[QWidget, Services], QWidget]] = {
    "about": lambda parent, _services: AboutDialog(parent),
    "onboarding": lambda parent, services: Onboarding(services.settings, parent),
    "bundle": lambda parent, _services: BundleDialog(parent),
    "risk": lambda parent, _services: RiskWarning(
        "Turn on custom FastFlags?", "Two sentences about the risk. " * 4, parent
    ),
    "explanation": lambda parent, _services: Explanation(
        "Before you turn on privacy mode", "What changes and why. " * 4, parent=parent
    ),
    "destructive": lambda parent, _services: DestructiveConfirmation(
        "Remove 3 replacements?", "Remove", "They can't be restored.", parent
    ),
}


@pytest.mark.parametrize("scale", SCALES)
@pytest.mark.parametrize("name", DIALOGS)
def test_dialogs_do_not_clip_at_any_text_size(
    shell: Shell, services: Services, qtbot: QtBot, scale: int, name: str
) -> None:
    services.settings.set("appearance.text_scale", scale)
    dialog = DIALOGS[name](shell.window, services)
    qtbot.addWidget(dialog)
    dialog.show()
    settle(qtbot)
    assert clipped(dialog) == []


def test_text_size_reaches_widgets_that_already_exist(
    shell: Shell, services: Services, qtbot: QtBot
) -> None:
    # Review follow-up: a font change after the style sheet left existing widgets at 100 %.
    window = shell.window
    window.show()
    window.show_screen("activity")
    settle(qtbot)
    button = window.findChildren(QAbstractButton)[0]
    before = button.fontInfo().pixelSize()
    services.settings.set("appearance.text_scale", 130)
    settle(qtbot)
    assert button.fontInfo().pixelSize() > before


def focusable(root: QWidget) -> list[QWidget]:
    """Return every visible, enabled widget that the Tab key can reach."""
    return [
        widget
        for widget in root.findChildren(QWidget)
        if widget.isVisible()
        and widget.isEnabled()
        and widget.focusPolicy() & Qt.FocusPolicy.TabFocus
        and widget.width() > 0
    ]


def ring_problem(window: QWidget, widget: QWidget, ring: QColor) -> str | None:
    """Return why `widget` lacks plan 6.4's ring (2 px solid, 2 px outside it), or None.

    Compares the window's pixels before and after keyboard focus at the middle of each side:
    the 2 px band starting 2 px outside the control must turn ring-coloured, and the 2 px gap
    between the control and the ring must not change.
    """
    owner = widget  # the control the user sees: a spin box, not its inner line edit
    while (proxy := owner.focusProxy()) is not None:
        owner = proxy
    widget.clearFocus()
    if (focused := QApplication.focusWidget()) is not None:
        focused.clearFocus()  # no ring anywhere in the "before" image
    for area in scroll_areas(owner):  # what Tab does: scroll the control into view
        area.ensureWidgetVisible(owner, 8, 8)
    QApplication.processEvents()
    before = window.grab().toImage()
    widget.setFocus(Qt.FocusReason.TabFocusReason)
    QApplication.processEvents()
    after = window.grab().toImage()
    corner = owner.mapTo(window, QPoint(0, 0))
    left, top = corner.x(), corner.y()
    right, bottom = left + owner.width() - 1, top + owner.height() - 1
    mid_x, mid_y = (left + right) // 2, (top + bottom) // 2
    # Per side: the ring band (2 px, starting 2 px out) and the pixels that must not change:
    # the 2 px gap inside it and the pixel just outside it (so the ring is exactly 2 px wide).
    sides = {
        "left": (
            [(left - 4, mid_y), (left - 3, mid_y)],
            [(left - 2, mid_y), (left - 1, mid_y), (left - 5, mid_y)],
        ),
        "right": (
            [(right + 3, mid_y), (right + 4, mid_y)],
            [(right + 1, mid_y), (right + 2, mid_y), (right + 5, mid_y)],
        ),
        "top": (
            [(mid_x, top - 4), (mid_x, top - 3)],
            [(mid_x, top - 2), (mid_x, top - 1), (mid_x, top - 5)],
        ),
        "bottom": (
            [(mid_x, bottom + 3), (mid_x, bottom + 4)],
            [(mid_x, bottom + 1), (mid_x, bottom + 2), (mid_x, bottom + 5)],
        ),
    }
    visible = QRect(0, 0, after.width(), after.height())
    for area in scroll_areas(owner):
        viewport = area.viewport()
        visible &= QRect(viewport.mapTo(window, QPoint(0, 0)), viewport.size())
    checked = 0
    for side, (band, gap) in sides.items():
        if not all(visible.contains(x, y) for x, y in band + gap):
            continue  # this side is outside the window or scrolled out of view
        checked += 1
        for x, y in band:
            if not close(after.pixelColor(x, y), ring):
                return f"no ring on the {side} at ({x}, {y}): {after.pixelColor(x, y).name()}"
        for x, y in gap:
            if after.pixelColor(x, y) != before.pixelColor(x, y):
                return f"not a 2 px ring with a 2 px gap on the {side} at ({x}, {y})"
    return None if checked >= 2 else "the ring is outside the window"


def scroll_areas(widget: QWidget) -> list[QScrollArea]:
    found = []
    current = widget.parentWidget()
    while current is not None:
        if isinstance(current, QScrollArea):
            found.append(current)
        current = current.parentWidget()
    return found


def close(a: QColor, b: QColor) -> bool:
    return max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue())) <= 2


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("key", SCREENS)
def test_every_focusable_control_shows_the_offset_focus_ring(
    shell: Shell, services: Services, qtbot: QtBot, key: str, mode: str
) -> None:
    """Plan 5.2, 6.4 and 12.5: a 2 px ring with a 2 px offset on every focusable control, in
    both themes (review finding H6, drawn by the QProxyStyle in theme.py)."""
    services.settings.set("advanced.advanced_mode", True)
    services.settings.set("appearance.theme", mode)
    window = shell.window
    window.resize(1280, 800)
    window.show()
    window.show_screen(key)
    settle(qtbot)
    window.activateWindow()
    ring = shell.theme.color("focus-ring")
    problems = []
    for widget in focusable(window):
        problem = ring_problem(window, widget, ring)
        if problem is not None:
            label = getattr(widget, "text", lambda: "")()
            problems.append(f"{type(widget).__name__} {label!r}: {problem}")
    assert problems == []


def test_mouse_focus_shows_no_ring(shell: Shell, qtbot: QtBot) -> None:
    """The ring marks keyboard focus; a click doesn't draw it."""
    window = shell.window
    window.show()
    settle(qtbot)
    button = next(w for w in focusable(window) if isinstance(w, QAbstractButton))
    button.setFocus(Qt.FocusReason.TabFocusReason)
    settle(qtbot)
    assert shell.theme.focus_tracker.ring.isVisible()
    button.clearFocus()
    button.setFocus(Qt.FocusReason.MouseFocusReason)
    settle(qtbot)
    assert not shell.theme.focus_tracker.ring.isVisible()


@pytest.mark.parametrize("key", SCREENS)
def test_icon_buttons_are_at_least_28_px(
    shell: Shell, services: Services, qtbot: QtBot, key: str
) -> None:
    """Plan 6.3 (token hit-target-icon): every icon-only button is at least 28 × 28 (L5)."""
    services.settings.set("advanced.advanced_mode", True)
    window = shell.window
    window.show()
    window.show_screen(key)
    window.dew.show("Saved.")
    settle(qtbot)
    small = [
        f"{type(b).__name__} {b.accessibleName()!r} {b.width()}×{b.height()}"
        for b in window.findChildren(QAbstractButton)
        # Switches aren't icon buttons; the brand book keeps their standard pill size.
        if b.isVisible()
        and not b.text()
        and not isinstance(b, Switch)
        and (b.width() < 28 or b.height() < 28)
    ]
    assert small == []


def test_the_status_pill_reacts_only_to_a_left_click_inside(qtbot: QtBot) -> None:
    """L10: a right click, or a release outside the pill, isn't an activation."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    from verdra.canopy.leaves.badge import StatusPill

    pill = StatusPill()
    qtbot.addWidget(pill)
    pill.resize(120, 28)
    clicks: list[bool] = []
    pill.clicked.connect(lambda: clicks.append(True))

    def release(button: Qt.MouseButton, x: float) -> None:
        event = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(x, 10),
            QPointF(x, 10),
            button,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        pill.mouseReleaseEvent(event)

    release(Qt.MouseButton.RightButton, 10)
    release(Qt.MouseButton.LeftButton, 500)
    assert clicks == []
    release(Qt.MouseButton.LeftButton, 10)
    assert clicks == [True]


def test_the_ring_survives_its_control_being_deleted(shell: Shell, qtbot: QtBot) -> None:
    """Review round 2, F3: a focused control deleted while its window stays open (Settings ›
    Withdraw rebuilds its rows) must not leave a stale ring or break the next focus change."""
    from PySide6.QtWidgets import QPushButton

    window = shell.window
    window.show()
    settle(qtbot)
    doomed = QPushButton("Doomed", window.centralWidget())
    doomed.show()
    doomed.setFocus(Qt.FocusReason.TabFocusReason)
    settle(qtbot)
    ring = shell.theme.focus_tracker.ring
    assert ring.target is doomed and ring.isVisible()
    doomed.deleteLater()
    qtbot.waitUntil(lambda: ring.target is None)
    assert not ring.isVisible()
    other = next(w for w in focusable(window) if isinstance(w, QAbstractButton))
    other.setFocus(Qt.FocusReason.TabFocusReason)
    settle(qtbot)
    assert ring.target is other and ring.isVisible()
