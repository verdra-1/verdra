# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-22 in the editor drawer: the asset type check against Roblox's answers (faked)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pytestqt.qtbot import QtBot

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from verdra.canopy.screens.grafts.editor import Editor
from verdra.trunk.branches import grafts

Done = Callable[[str | None, str], None]
NOT_FOUND = "No asset with ID {id} was found."
OFFLINE = "Roblox couldn't be reached to check this ID. You can save it anyway."


class FakeRoblox:
    """Answers lookups when the test says so, like a slow network."""

    def __init__(self) -> None:
        self.asked: list[int] = []
        self.pending: dict[int, Done] = {}

    def __call__(self, asset_id: int, done: Done) -> None:
        self.asked.append(asset_id)
        self.pending[asset_id] = done

    def answer(self, asset_id: int, kind: str | None, message: str = "") -> None:
        self.pending.pop(asset_id)(kind, message)


@pytest.fixture
def roblox() -> FakeRoblox:
    return FakeRoblox()


@pytest.fixture
def editor(roblox: FakeRoblox, qtbot: QtBot) -> Editor:
    made = Editor(lookup=roblox)
    qtbot.addWidget(made)
    made.start()
    return made


def pause(editor: Editor, qtbot: QtBot) -> None:
    """Wait until the typing pause has passed and its lookups were asked."""
    qtbot.waitUntil(lambda: not editor._pause.isActive(), timeout=2000)  # noqa: SLF001


@pytest.mark.spec("S-22", 4)
def test_typing_quickly_asks_once_per_pause(
    editor: Editor, roblox: FakeRoblox, qtbot: QtBot
) -> None:
    qtbot.keyClicks(editor.original, "1111111")
    assert roblox.asked == []  # nothing while typing
    pause(editor, qtbot)
    assert roblox.asked == [1111111]
    qtbot.keyClicks(editor.target, "2222222")
    pause(editor, qtbot)
    assert roblox.asked == [1111111, 2222222]  # the original isn't asked again
    editor.original.clear()
    qtbot.keyClicks(editor.original, "1111111")
    pause(editor, qtbot)
    assert roblox.asked == [1111111, 2222222]  # an answer already asked for is kept


@pytest.mark.spec("S-22", 4)
def test_a_slow_answer_to_an_old_input_never_overrides_a_newer_one(
    editor: Editor, roblox: FakeRoblox, qtbot: QtBot
) -> None:
    qtbot.keyClicks(editor.original, "1111")
    pause(editor, qtbot)
    editor.original.clear()
    qtbot.keyClicks(editor.original, "3333")
    qtbot.keyClicks(editor.target, "4444")
    pause(editor, qtbot)
    roblox.answer(3333, "Image")
    roblox.answer(4444, "Image")
    assert editor.save.isEnabled()
    roblox.answer(1111, None, NOT_FOUND.format(id=1111))  # late, for what was typed before
    assert editor.save.isEnabled()
    assert editor.problem.text() == ""


@pytest.mark.spec("S-22", 1)
def test_an_asset_roblox_doesnt_have_cant_be_saved(
    editor: Editor, roblox: FakeRoblox, qtbot: QtBot
) -> None:
    qtbot.keyClicks(editor.original, str(ABOVE_INT32))
    qtbot.keyClicks(editor.target, str(ABOVE_UINT32))
    pause(editor, qtbot)
    assert roblox.asked == [ABOVE_INT32, ABOVE_UINT32]  # real-size IDs reach the lookup whole
    assert editor.save.isEnabled()  # not refused before Roblox answers
    roblox.answer(ABOVE_INT32, "Image")
    roblox.answer(ABOVE_UINT32, None, NOT_FOUND.format(id=ABOVE_UINT32))
    assert not editor.save.isEnabled()
    assert editor.save.toolTip() == f"No asset with ID {ABOVE_UINT32} was found."
    assert editor.problem.text() == f"No asset with ID {ABOVE_UINT32} was found."


@pytest.mark.spec("S-22", 1)
def test_a_target_of_another_type_cant_be_saved(
    editor: Editor, roblox: FakeRoblox, qtbot: QtBot
) -> None:
    qtbot.keyClicks(editor.original, "1111")
    qtbot.keyClicks(editor.target, "4444")
    pause(editor, qtbot)
    roblox.answer(1111, "Audio")
    roblox.answer(4444, "Image")
    assert editor.save.toolTip() == "A picture can't replace a sound."
    assert not editor.save.isEnabled()


@pytest.mark.spec("S-22", 1)
def test_a_file_of_another_type_cant_be_saved_and_the_type_is_saved(
    editor: Editor, roblox: FakeRoblox, qtbot: QtBot, tmp_path: grafts.Path
) -> None:
    sound = tmp_path / "boom.ogg"
    sound.write_bytes(b"OggS\0\x02" + bytes(64))
    qtbot.keyClicks(editor.original, "1111")
    editor.use_file(sound)
    pause(editor, qtbot)
    assert roblox.asked == [1111]  # a file's type is read from the file, not asked
    roblox.answer(1111, "Image")
    assert editor.save.toolTip() == "A sound can't replace a picture."
    picture = tmp_path / "wall.png"
    picture.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(64))
    editor.use_file(picture)
    assert editor.save.isEnabled()
    with qtbot.waitSignal(editor.saved) as saved:
        editor.save.click()
    assert saved.args is not None
    assert saved.args[2] == "Image"


@pytest.mark.spec("S-22", 5)
def test_with_roblox_unreachable_an_asset_id_can_be_saved_with_a_note(
    editor: Editor, roblox: FakeRoblox, qtbot: QtBot
) -> None:
    qtbot.keyClicks(editor.original, "1111")
    qtbot.keyClicks(editor.target, "4444")
    pause(editor, qtbot)
    roblox.answer(1111, "", OFFLINE)
    roblox.answer(4444, "", OFFLINE)
    assert editor.save.isEnabled()
    assert editor.detail.text() == OFFLINE  # once, though both IDs went unchecked
    with qtbot.waitSignal(editor.saved) as saved:
        editor.save.click()
    assert saved.args is not None
    assert saved.args[2] == ""  # the type isn't known, so none is saved


def test_without_a_lookup_nothing_is_asked(qtbot: QtBot) -> None:
    editor = Editor()
    qtbot.addWidget(editor)
    editor.start()
    qtbot.keyClicks(editor.original, "1111")
    qtbot.keyClicks(editor.target, "4444")
    assert not editor._pause.isActive()  # noqa: SLF001
    assert editor.save.isEnabled()
