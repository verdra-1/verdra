# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The status-light leaf (decision record 0027 item 4): shape per state and in-window breathing."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSize, QVariantAnimation
from pytestqt.qtbot import QtBot

from verdra.canopy.crown import theme
from verdra.canopy.leaves.status_leaf import LeafState, StatusLeaf


def shown(qtbot: QtBot, leaf: StatusLeaf) -> StatusLeaf:
    qtbot.addWidget(leaf)
    leaf.show()
    qtbot.waitExposed(leaf)
    return leaf


def running(leaf: StatusLeaf) -> bool:
    return leaf._breath.state() == QVariantAnimation.State.Running  # noqa: SLF001


def test_it_starts_off_at_its_fixed_size(qtbot: QtBot) -> None:
    leaf = StatusLeaf(size=20)
    qtbot.addWidget(leaf)
    assert leaf.state is LeafState.OFF
    assert leaf.sizeHint() == QSize(20, 20)


def test_every_state_loads_a_valid_leaf_asset(qtbot: QtBot) -> None:
    leaf = shown(qtbot, StatusLeaf())
    for state in LeafState:
        leaf.set_state(state)
        assert leaf._renderer.isValid(), state  # noqa: SLF001


def test_only_the_working_leaf_breathes(qtbot: QtBot) -> None:
    leaf = shown(qtbot, StatusLeaf())
    leaf.set_state(LeafState.WORKING)
    assert running(leaf)
    for state in (LeafState.WAITING, LeafState.NEEDS_YOU, LeafState.STOPPED, LeafState.OFF):
        leaf.set_state(state)
        assert not running(leaf), state


def test_a_hidden_working_leaf_does_not_breathe(qtbot: QtBot) -> None:
    # "In the window only": a leaf that isn't shown (or the tray's static icon) never animates.
    leaf = StatusLeaf()
    qtbot.addWidget(leaf)
    leaf.set_state(LeafState.WORKING)
    assert not running(leaf)


def test_reduced_motion_stops_the_breathing(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    # Build first (no Theme instance in tests, so __init__ connects to nothing), then make the
    # theme report reduced motion before changing state.
    leaf = shown(qtbot, StatusLeaf())

    class Stub:
        mode = "light"
        reduce_motion = True

    monkeypatch.setattr(theme.Theme, "instance", classmethod(lambda _cls: Stub()))
    leaf.set_state(LeafState.WORKING)
    assert not running(leaf)
    assert leaf._opacity() == 1.0  # noqa: SLF001


def test_opacity_is_full_when_not_breathing(qtbot: QtBot) -> None:
    leaf = shown(qtbot, StatusLeaf())
    leaf.set_state(LeafState.OFF)
    assert leaf._opacity() == 1.0  # noqa: SLF001


def test_the_breath_dips_the_opacity_at_mid_cycle(qtbot: QtBot) -> None:
    from verdra.canopy.leaves.status_leaf import BREATHE_MIN_OPACITY

    leaf = shown(qtbot, StatusLeaf())
    leaf.set_state(LeafState.WORKING)  # breathing is running
    leaf._phase = 0.5  # noqa: SLF001 - mid-cycle is the deepest dip
    assert leaf._opacity() == pytest.approx(BREATHE_MIN_OPACITY)  # noqa: SLF001
    leaf._phase = 0.0  # noqa: SLF001 - the ends of the cycle are full
    assert leaf._opacity() == pytest.approx(1.0)  # noqa: SLF001


def test_every_state_paints(qtbot: QtBot) -> None:
    leaf = shown(qtbot, StatusLeaf(size=32))
    for state in LeafState:
        leaf.set_state(state)
        assert not leaf.grab().isNull()  # forces paintEvent
