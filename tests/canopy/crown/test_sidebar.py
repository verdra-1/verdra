# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The sidebar grows so a nav label is never cut off at larger text (D1 blocker 4, law 1)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tools import gallery
from verdra.canopy.crown.sidebar import Sidebar


@dataclass(frozen=True)
class _Profile:
    id: str
    name: str
    enabled: bool = True
    replacements: list[int] = field(default_factory=list)


def _profile(name: str, replacements: int, *, enabled: bool = True) -> _Profile:
    return _Profile(
        id=name.lower(), name=name, enabled=enabled, replacements=list(range(replacements))
    )


@pytest.fixture
def big_font(qapp: QApplication) -> Iterator[None]:
    """About 260 % text, where "Replacements" no longer fits the 220 px design width."""
    original = qapp.font()
    large = QFont(original)
    large.setPointSize(26)
    qapp.setFont(large)
    yield
    qapp.setFont(original)


def shown(qtbot: QtBot, bar: Sidebar) -> Sidebar:
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitExposed(bar)
    layout = bar.layout()
    assert layout is not None
    layout.activate()
    QApplication.processEvents()
    return bar


def test_the_expanded_sidebar_fits_its_labels_at_large_text(qtbot: QtBot, big_font: None) -> None:
    bar = shown(qtbot, Sidebar())
    assert not bar.collapsed
    assert bar.width() > bar._base_width  # it grew past the design width
    clipped = [f.text for f in gallery.cut_off(bar, "test", "sidebar") if f.kind == "button"]
    assert clipped == []


def test_collapsing_still_goes_to_the_icon_width(qtbot: QtBot, big_font: None) -> None:
    bar = shown(qtbot, Sidebar())
    bar.set_collapsed(True)
    assert bar.width() == bar.collapsed_width  # icons only, whatever the text size
    bar.set_collapsed(False)
    assert bar.width() == bar.expanded_width > bar._base_width


def test_small_text_never_shrinks_below_the_design_width_or_clips(
    qtbot: QtBot, qapp: QApplication
) -> None:
    """At small text the sidebar never shrinks below its design width, and never clips a label
    (including Library's "coming later" note, whose width the sidebar accounts for). It may sit a
    little above the design width where a row's widget minimums need it; exact widths are the
    platform's to decide, so this checks the invariants, not a pixel count."""
    original = qapp.font()
    small = QFont(original)
    small.setPointSize(6)
    qapp.setFont(small)
    try:
        bar = shown(qtbot, Sidebar())
        assert bar.width() >= bar._base_width  # never narrower than the design width
        clipped = [f.text for f in gallery.cut_off(bar, "test", "sidebar") if f.kind != "cell"]
        assert clipped == []
    finally:
        qapp.setFont(original)


def test_the_profile_card_names_the_active_profile(qtbot: QtBot) -> None:
    bar = shown(qtbot, Sidebar())
    bar.set_profiles([_profile("My replacements", 5), _profile("Night", 2)])
    assert bar.profile_name.text() == "My replacements"  # the first (active) one
    assert bar.profile_count.text() == "5 replacements"
    assert bar.profile_count.isVisibleTo(bar)


def test_the_profile_card_has_an_empty_state(qtbot: QtBot) -> None:
    bar = shown(qtbot, Sidebar())
    bar.set_profiles([])
    assert bar.profile_name.text() == "No profile yet"
    assert bar.profile_count.text() == ""
    assert not bar.profile_count.isVisibleTo(bar)


def test_library_is_marked_coming_later(qtbot: QtBot) -> None:
    # Honest: Library isn't built, so the sidebar says so rather than opening a dead screen.
    bar = shown(qtbot, Sidebar())
    assert bar.later_caption.text() == "coming later"
    assert "coming later" in bar.buttons["library"].accessibleName()


def test_collapsing_hides_the_profile_card_and_the_coming_later_note(qtbot: QtBot) -> None:
    bar = shown(qtbot, Sidebar())
    bar.set_profiles([_profile("My replacements", 5)])
    bar.set_collapsed(True)
    assert not bar.profile_card.isVisibleTo(bar)
    assert not bar.later_caption.isVisibleTo(bar)
    bar.set_collapsed(False)
    assert bar.profile_card.isVisibleTo(bar)
    assert bar.later_caption.isVisibleTo(bar)
