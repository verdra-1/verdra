# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""No label is ever cut off at the smallest window size (plan 12.5, Guide B on Windows).

On the maintainer's PC the Replacements toolbar showed "replacem" and "riew chan": with the
editor drawer open, the screen needed more width than the smallest window has, so Qt squeezed
the buttons below their text. This checks every screen, at every text size, at the smallest
window, Replacements with its editor open: the window's content must fit, and no visible
button or tab may be narrower than its own size hint.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QAbstractButton
from pytestqt.qtbot import QtBot

from verdra.canopy.crown.window import MINIMUM_SIZE, Shell
from verdra.canopy.screens.grafts.screen import ReplacementsScreen
from verdra.soil import terrain
from verdra.trunk.branches import grafts
from verdra.trunk.sapwood.startup import Services

#: Reference R2: appearance.text_scale.
TEXT_SCALES = (90, 100, 115, 130)


@pytest.fixture(params=TEXT_SCALES, ids=[f"text-{s}" for s in TEXT_SCALES])
def smallest(request: pytest.FixtureRequest, services: Services, qtbot: QtBot) -> Iterator[Shell]:
    services.settings.set("appearance.text_scale", request.param)
    services.grafts = grafts.Grafts(terrain.config_dir() / "profiles", services.settings)
    services.grafts.edit("create", "My replacements")
    shell = Shell(services)
    shell.build()
    qtbot.addWidget(shell.window)
    shell.window.resize(MINIMUM_SIZE)
    shell.window.show()
    yield shell
    shell.window.allow_close = True
    shell.window.close()
    services.grafts.deleteLater()


def squeezed(shell: Shell) -> list[str]:
    """The visible buttons narrower than their own size hint, with both widths."""
    return [
        f"{button.text()!r}: {button.width()} < {button.sizeHint().width()}"
        for button in shell.window.findChildren(QAbstractButton)
        if button.isVisibleTo(shell.window)
        and button.text()
        and button.width() < button.sizeHint().width()
    ]


@pytest.mark.spec("S-01", 16)
def test_every_screen_fits_the_smallest_window(smallest: Shell, qtbot: QtBot) -> None:
    window = smallest.window
    smallest.show_others(True)  # the M-LAUNCH-08 banner with its two buttons, on every screen
    for name in window.screens:
        window.show_screen(name)
        screen = window.screens[name]
        if isinstance(screen, ReplacementsScreen):
            screen.add_replacement()  # the editor drawer open: the widest it gets
            screen.editor.choose("file")  # with "Choose file…" showing
        qtbot.wait(10)
        assert window.minimumSizeHint().width() <= MINIMUM_SIZE.width(), name
        assert squeezed(smallest) == [], name
