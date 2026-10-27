# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The header's status light (0027 §3): the five words, their leaf and keyboard activation."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from verdra.canopy.leaves.status_leaf import LeafState
from verdra.canopy.leaves.status_light import StatusLight, StatusWord, word_for


def test_each_word_carries_its_leaf_state() -> None:
    assert StatusWord.WORKING.leaf is LeafState.WORKING
    assert StatusWord.WAITING.leaf is LeafState.WAITING
    assert StatusWord.NEEDS_YOU.leaf is LeafState.NEEDS_YOU
    assert StatusWord.STOPPED.leaf is LeafState.STOPPED
    assert StatusWord.OFF.leaf is LeafState.OFF


def test_every_word_has_a_non_empty_label() -> None:
    labels = {word: word.label() for word in StatusWord}
    assert all(labels.values())
    # The five words are distinct, so colour is never the only difference (0027 §3).
    assert len(set(labels.values())) == len(StatusWord)


@pytest.mark.parametrize(
    ("state", "has_fix", "expected"),
    [
        ("routing", False, StatusWord.WORKING),
        ("routing", True, StatusWord.WORKING),
        ("error", True, StatusWord.STOPPED),
        ("error", False, StatusWord.STOPPED),
        ("degraded", True, StatusWord.NEEDS_YOU),
        ("degraded", False, StatusWord.WAITING),
        ("idle", True, StatusWord.OFF),
        ("idle", False, StatusWord.OFF),
    ],
)
def test_word_for_maps_each_state(state: str, has_fix: bool, expected: StatusWord) -> None:
    assert word_for(state, has_fix=has_fix) is expected


def test_it_starts_off(qtbot: QtBot) -> None:
    light = StatusLight()
    qtbot.addWidget(light)
    assert light.status_word is StatusWord.OFF
    assert light.leaf.state is LeafState.OFF


def test_set_word_shows_the_word_its_leaf_and_an_accessible_name(qtbot: QtBot) -> None:
    light = StatusLight()
    qtbot.addWidget(light)
    for word in StatusWord:
        light.set_word(word)
        assert light.status_word is word
        assert light.leaf.state is word.leaf
        assert light.word.text() == word.label()
        # The word is spoken, not only coloured (0027 §3): the accessible name carries it.
        assert light.accessibleName() == f"Routing status: {word.label()}"
        assert word.label() in light.toolTip()


@pytest.mark.parametrize("key", [Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_a_key_press_opens_the_popover(qtbot: QtBot, key: Qt.Key) -> None:
    light = StatusLight()
    qtbot.addWidget(light)
    clicks: list[None] = []
    light.clicked.connect(lambda: clicks.append(None))
    qtbot.keyClick(light, key)
    assert clicks == [None]


def test_a_mouse_release_opens_the_popover(qtbot: QtBot) -> None:
    light = StatusLight()
    qtbot.addWidget(light)
    light.show()
    qtbot.waitExposed(light)
    clicks: list[None] = []
    light.clicked.connect(lambda: clicks.append(None))
    qtbot.mouseClick(light, Qt.MouseButton.LeftButton)
    assert clicks == [None]


def test_it_takes_keyboard_focus(qtbot: QtBot) -> None:
    # The whole light is one focus stop, reachable by Tab (spec S-01).
    light = StatusLight()
    qtbot.addWidget(light)
    assert light.focusPolicy() & Qt.FocusPolicy.TabFocus
