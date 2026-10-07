# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Specs S-20, S-22 and S-24 in the interface: the Replacements screen and Apply now."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QObject, QPointF, Qt, QUrl, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QDialog, QWidget
from pytestqt.qtbot import QtBot

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from verdra.canopy.crown.dew import Toast
from verdra.canopy.crown.window import Shell
from verdra.canopy.leaves.dialogs import DestructiveConfirmation
from verdra.canopy.screens.grafts.screen import ReplacementsScreen
from verdra.roots import hyphae, rules
from verdra.roots.symbionts.grafter import Grafter
from verdra.soil import terrain
from verdra.strata import ochre
from verdra.trunk.branches import grafts, sprout
from verdra.trunk.sapwood import startup
from verdra.trunk.sapwood.startup import Services


class StubSprout(QObject):
    """Records what Apply now asks of trunk's Sprout."""

    refused = Signal(str)
    other_tool = Signal(str)
    backups_changed = Signal()
    others_changed = Signal(bool)
    held_back = Signal(str)
    handed_off = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []
        #: A Player this Verdra started is running.
        self.running = False
        #: Players Verdra didn't start, and Studios, that are running.
        self.others: tuple[int, ...] = ()
        self.studio: tuple[int, ...] = ()
        self.routing = True
        self.cache: sprout.CacheMove | None = sprout.CacheMove(
            ("rbx-storage.db", "rbx-storage"), Path("C:/Verdra/Roblox cache backup/1")
        )

    def roblox_running(self) -> bool:
        return self.running

    def roblox_processes(self) -> sprout.RunningRoblox:
        players = frozenset(((7,) if self.running else ()) + self.others)
        return sprout.RunningRoblox(players, bool(self.studio))

    def players_started_here(self) -> set[int]:
        return {7} if self.running else set()

    def refresh_others(self) -> frozenset[int]:
        self.others_changed.emit(bool(self.others))
        return frozenset(self.others)

    def close_roblox(self) -> None:
        self.calls.append("close")

    def clear_cache(self) -> sprout.CacheMove | None:
        self.calls.append("clear")
        return self.cache

    def launch(self, link: str | None = None) -> None:
        self.calls.append("launch")

    def start_routing(self) -> None:
        self.calls.append("start")


@pytest.fixture(autouse=True)
def catalog(qapp: QApplication) -> Iterator[None]:
    """The English catalogue, which gives M-APPLY-02 and M-APPLY-03 their plural forms."""
    translator = startup.install_translator(qapp, "en")
    assert translator is not None
    yield
    qapp.removeTranslator(translator)
    translator.deleteLater()


@pytest.fixture
def made(services: Services, qtbot: QtBot) -> Iterator[tuple[Shell, StubSprout]]:
    services.grafts = grafts.Grafts(terrain.config_dir() / "profiles", services.settings)
    stub = StubSprout()
    services.sprout = stub  # type: ignore[assignment]
    shell = Shell(services)
    shell.build()
    qtbot.addWidget(shell.window)
    yield shell, stub
    shell.window.allow_close = True
    shell.window.close()
    services.sprout = None
    stub.deleteLater()
    services.grafts.deleteLater()


def screen_of(shell: Shell) -> ReplacementsScreen:
    screen = shell.window.screens["replacements"]
    assert isinstance(screen, ReplacementsScreen)
    return screen


def toasts(shell: Shell) -> list[str]:
    return [t.text for t in shell.window.findChildren(Toast)]


@pytest.mark.spec("S-22", 3)
def test_a_first_replacement_from_the_empty_state_with_the_keyboard(
    made: tuple[Shell, StubSprout], qtbot: QtBot
) -> None:
    shell, _stub = made
    screen = screen_of(shell)
    assert screen.stack.currentWidget() is screen.empty
    add, presets = screen.empty.buttons
    assert add.isEnabled() and not presets.isEnabled()
    add.click()  # makes "My replacements" and opens the editor with the cursor in it
    assert screen.stack.currentWidget() is screen.main
    editor = screen.editor
    assert not editor.isHidden()
    assert not editor.save.isEnabled() and editor.save.toolTip()
    qtbot.keyClicks(editor.original, "1111111")
    editor.target.setFocus()
    qtbot.keyClicks(editor.target, "1111111")
    assert editor.save.toolTip() == "An asset can't replace itself. Enter a different asset ID."
    editor.target.clear()
    qtbot.keyClicks(editor.target, "2222222")
    assert editor.save.isEnabled()
    qtbot.keyClick(editor.target, Qt.Key.Key_Return)  # saves
    assert editor.isHidden()
    [profile] = shell.services.grafts.profiles  # type: ignore[union-attr]
    assert profile.name == "My replacements"
    assert [(r.original.asset_id, r.target.value) for r in profile.replacements] == [
        (1111111, "2222222")
    ]
    assert screen.table.rowCount() == 1
    cell = screen.table.item(0, 1)
    assert cell is not None and cell.text() == "2222222"
    saved = json.loads((terrain.config_dir() / "profiles" / "My replacements.json").read_bytes())
    assert saved["replacements"][0]["target"] == {"kind": "asset_id", "value": "2222222"}


@pytest.mark.spec("S-22", 2)
def test_a_local_file_dropped_on_the_drawer_is_saved_relative_to_the_profile(
    made: tuple[Shell, StubSprout], qtbot: QtBot
) -> None:
    shell, _stub = made
    screen = screen_of(shell)
    screen.empty.buttons[0].click()
    editor = screen.editor
    folder = terrain.config_dir() / "profiles" / "My replacements"
    assert editor.folder == folder
    picture = folder / "sky" / "top.png"
    picture.parent.mkdir(parents=True)
    qtbot.keyClicks(editor.original, "1111111")

    unsupported = folder / "notes.txt"
    unsupported.write_text("hello")
    drop(editor, unsupported)
    assert editor.kind() == "file"
    assert editor.save.toolTip() == (
        "This file type isn't supported. Use PNG, JPEG, KTX2, OBJ, MESH, OGG or MP3."
    )
    drop(editor, picture)
    assert editor.save.toolTip() == f"The file for this replacement is missing: {picture}."
    picture.write_bytes(b"\x89PNG\r\n\x1a\n")
    drop(editor, picture)  # the same path again is checked again
    assert editor.save.isEnabled()
    editor.save.click()

    service = shell.services.grafts
    assert service is not None
    saved = json.loads((folder.parent / "My replacements.json").read_bytes())
    assert saved["replacements"][0]["target"] == {"kind": "file", "value": "./sky/top.png"}
    assert saved["replacements"][0]["asset_type"] == "Image"
    note = screen.table.item(0, 3)
    # Only a PNG signature, not a picture: it is saved, but can't be used in game, and says why.
    assert note is not None and note.text().startswith("This file couldn't be used:")
    picture.write_bytes(ochre.to_png(ochre.Pixels(1, 1, b"\0\0\0\xff")))
    service.publish()
    screen.refresh()
    note = screen.table.item(0, 3)
    assert note is None or note.text() == ""  # a real picture: used in game, nothing to say


@pytest.mark.spec("S-22", 1)
def test_a_link_must_be_https_and_shows_its_host(
    made: tuple[Shell, StubSprout], qtbot: QtBot
) -> None:
    screen = screen_of(made[0])
    screen.empty.buttons[0].click()
    editor = screen.editor
    qtbot.keyClicks(editor.original, "1111111")
    editor.choose("url")
    assert not editor.browse.isVisibleTo(editor)
    qtbot.keyClicks(editor.target, "http://cdn.example/a.png")
    assert editor.save.toolTip() == "Only HTTPS links are allowed."
    assert editor.detail.text() == ""
    editor.target.clear()
    qtbot.keyClicks(editor.target, "https://cdn.example/a.png")
    assert editor.save.isEnabled()
    assert editor.detail.text() == "Downloads from cdn.example."
    qtbot.keyClick(editor.target, Qt.Key.Key_Return)
    service = made[0].services.grafts
    assert service is not None
    target = service.profiles[0].replacements[0].target
    assert (target.kind, target.value) == ("url", "https://cdn.example/a.png")


def test_remove_needs_only_the_original(made: tuple[Shell, StubSprout], qtbot: QtBot) -> None:
    screen = screen_of(made[0])
    screen.empty.buttons[0].click()
    editor = screen.editor
    editor.choose("remove")
    assert not editor.target.isVisibleTo(editor)
    assert editor.save.toolTip() == "Enter the asset ID to replace."
    qtbot.keyClicks(editor.original, "1111111")
    assert editor.save.isEnabled()
    editor.save.click()
    service = made[0].services.grafts
    assert service is not None
    target = service.profiles[0].replacements[0].target
    assert (target.kind, target.value) == ("remove", "")


def drop(widget: QWidget, path: Path) -> None:
    """Drop one local file on `widget`, as a file manager does."""
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(path))])
    position = QPointF(widget.rect().center())
    buttons, keys = Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    enter = QDragEnterEvent(position.toPoint(), Qt.DropAction.CopyAction, data, buttons, keys)
    QApplication.sendEvent(widget, enter)
    assert enter.isAccepted()
    QApplication.sendEvent(
        widget, QDropEvent(position, Qt.DropAction.CopyAction, data, buttons, keys)
    )


@pytest.mark.spec("S-20", 4)
def test_profiles_switch_undo_and_delete_from_the_screen(
    made: tuple[Shell, StubSprout], monkeypatch: pytest.MonkeyPatch, qtbot: QtBot
) -> None:
    shell, _stub = made
    screen = screen_of(shell)
    service = shell.services.grafts
    assert service is not None
    screen.empty.buttons[0].click()
    screen.editor.hide()
    qtbot.keyClicks(screen.new_name, "Night")
    qtbot.keyClick(screen.new_name, Qt.Key.Key_Return)
    assert [p.name for p in service.profiles] == ["Night", "My replacements"]
    current = screen.profiles.currentItem()
    assert current is not None and current.text() == "Night"
    qtbot.keyClicks(screen.new_name, "night")  # same name, other case
    qtbot.keyClick(screen.new_name, Qt.Key.Key_Return)
    assert screen.name_problem.text() == "A profile named night already exists."
    current = screen.profiles.currentItem()
    assert current is not None
    current.setCheckState(Qt.CheckState.Unchecked)
    assert not service.profiles[0].enabled
    screen.undo.click()
    assert service.profiles[0].enabled
    screen.redo.click()
    assert not service.profiles[0].enabled
    monkeypatch.setattr(DestructiveConfirmation, "exec", lambda _self: QDialog.DialogCode.Accepted)
    screen.delete_profile.click()
    assert [p.name for p in service.profiles] == ["My replacements"]


@pytest.mark.spec("S-24", 3)
def test_apply_now_without_roblox_running_publishes_and_says_next_time(
    made: tuple[Shell, StubSprout],
) -> None:
    shell, stub = made
    service = shell.services.grafts
    assert service is not None
    profile = service.edit("create", "A")
    service.edit(
        "add_replacement",
        profile.id,
        grafts.Original(asset_id=1111111),
        grafts.Target(kind="asset_id", value="2222222"),
    )
    assert service.holder.current.swaps() == {}  # nothing applies before Apply now
    header = shell.window.header
    assert header.apply_now.isEnabled()
    header.apply_now.click()
    assert service.holder.current.swaps() == {1111111: 2222222}
    assert stub.calls == ["clear"]  # nothing runs: the cache moves aside, nothing is closed
    assert toasts(shell)[-2:] == [
        "Moved Roblox's saved assets (rbx-storage.db, rbx-storage) to "
        f"{Path('C:/Verdra/Roblox cache backup/1')}. Reset everything puts them back.",
        "Applied 1 replacement. They'll appear next time Roblox starts.",
    ]
    stub.routing = False
    stub.calls.clear()
    header.apply_now.click()
    assert stub.calls == ["clear", "start"]  # S-24 rule 2: routing starts too


@pytest.mark.spec("S-24", 4)
def test_canceling_the_restart_publishes_and_closes_nothing(
    made: tuple[Shell, StubSprout], monkeypatch: pytest.MonkeyPatch
) -> None:
    shell, stub = made
    stub.running = True
    asked: list[str] = []

    def answer(dialog: DestructiveConfirmation) -> int:
        asked.append(dialog.findChildren(type(shell.window.header.apply_now))[-1].text())
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(DestructiveConfirmation, "exec", answer)
    shell.window.header.apply_now.click()
    assert asked == ["Restart Roblox"]
    assert stub.calls == []
    assert toasts(shell)[-1] == "Applied 0 replacements. They'll appear next time Roblox starts."


@pytest.mark.spec("S-24", 2)
def test_confirming_restarts_only_the_roblox_verdra_launched(
    made: tuple[Shell, StubSprout], monkeypatch: pytest.MonkeyPatch
) -> None:
    shell, stub = made
    stub.running = True
    monkeypatch.setattr(DestructiveConfirmation, "exec", lambda _self: QDialog.DialogCode.Accepted)
    shell.window.header.apply_now.click()
    # Sprout closes only its own launches (S-12 rule 4), then the cache moves, then Roblox starts.
    assert stub.calls == ["close", "clear", "launch"]
    assert toasts(shell)[-1] == "Applied 0 replacements. Roblox is restarting."


@pytest.mark.spec("S-24", 7)
@pytest.mark.parametrize(
    ("others", "studio", "told"),
    [
        ((), (9,), "Roblox Studio is open, so Verdra didn't move Roblox's saved assets aside."),
        ((9,), (), "A Roblox Player that Verdra didn't start is running, so Verdra didn't move"),
    ],
)
def test_the_cache_stays_while_studio_or_another_player_runs(
    made: tuple[Shell, StubSprout],
    monkeypatch: pytest.MonkeyPatch,
    others: tuple[int, ...],
    studio: tuple[int, ...],
    told: str,
) -> None:
    shell, stub = made
    stub.others, stub.studio = others, studio
    shell.window.header.apply_now.click()  # none of Verdra's own Players runs
    assert stub.calls == []  # nothing moved, nothing closed: Studio and others are never closed
    assert toasts(shell)[-2].startswith(told)
    assert toasts(shell)[-1] == "Applied 0 replacements. They'll appear next time Roblox starts."
    stub.running = True  # with Verdra's own Player too: it restarts, the cache still stays
    monkeypatch.setattr(DestructiveConfirmation, "exec", lambda _self: QDialog.DialogCode.Accepted)
    shell.window.header.apply_now.click()
    assert stub.calls == ["close", "launch"]
    assert toasts(shell)[-1].startswith("Applied 0 replacements. Assets Roblox already saved")


def test_without_the_service_the_screen_and_apply_now_say_why(shell: Shell) -> None:
    screen = screen_of(shell)
    assert not any(b.isEnabled() for b in screen.empty.buttons)
    assert not shell.window.header.apply_now.isEnabled()


def test_startup_publishes_saved_replacements(home: Path, services: Services) -> None:
    folder = terrain.config_dir() / "profiles"
    first = grafts.Grafts(folder, services.settings)
    profile = first.edit("create", "A")
    first.edit(
        "add_replacement",
        profile.id,
        grafts.Original(asset_id=5),
        grafts.Target(kind="asset_id", value="6"),
    )
    again = grafts.Grafts(folder, services.settings)
    assert again.publish() == 1
    assert again.holder.current.swaps() == {5: 6}
    first.deleteLater()
    again.deleteLater()


@pytest.mark.spec("S-23", 1)
def test_preview_changes_shows_totals_winners_and_what_they_override(
    made: tuple[Shell, StubSprout], monkeypatch: pytest.MonkeyPatch
) -> None:
    from verdra.canopy.screens.grafts.preview import PreviewDialog  # noqa: PLC0415

    shell, _stub = made
    service = shell.services.grafts
    assert service is not None
    low = service.edit("create", "Low")
    high = service.edit("create", "High")
    for profile, target in ((low, "100"), (high, "111")):
        service.edit(
            "add_replacement",
            profile.id,
            grafts.Original(asset_id=1111111),
            grafts.Target(kind="asset_id", value=target),
            "Image",
        )
    shown: list[PreviewDialog] = []
    monkeypatch.setattr(PreviewDialog, "exec", lambda dialog: shown.append(dialog) or 0)
    screen_of(shell).preview.click()
    [dialog] = shown
    assert dialog.totals.text() == "1 asset will change; 1 conflict."
    group = dialog.tree.topLevelItem(0)
    assert group is not None and group.text(0) == "Image"
    winner = group.child(0)
    assert winner is not None
    assert [winner.text(i) for i in range(3)] == ["1111111", "Asset 111", "High"]
    lost = winner.child(0)
    assert lost is not None
    assert [lost.text(i) for i in range(3)] == ["Overridden", "Asset 100", "Low"]
    dialog.deleteLater()


@pytest.mark.spec("S-22", 3)
def test_replacement_shortcuts_add_undo_redo_and_apply(
    made: tuple[Shell, StubSprout], qtbot: QtBot
) -> None:
    shell, stub = made
    service = shell.services.grafts
    assert service is not None
    keys = shell.shortcuts.shortcuts
    assert {"Ctrl+N", "Ctrl+Z", "Shift+Ctrl+Z", "Ctrl+Return"} <= shell.shortcuts.working
    shell.window.show_screen("settings")
    keys["Ctrl+N"].activated.emit()  # from any screen: Replacements, first profile, editor
    screen = screen_of(shell)
    assert shell.window.stack.currentWidget() is screen
    assert [p.name for p in service.profiles] == ["My replacements"]
    assert not screen.editor.isHidden()
    qtbot.keyClicks(screen.editor.original, "1111111")
    qtbot.keyClicks(screen.editor.target, "2222222")
    qtbot.keyClick(screen.editor.target, Qt.Key.Key_Return)
    assert len(service.profiles[0].replacements) == 1

    keys["Ctrl+Z"].activated.emit()
    assert service.profiles[0].replacements == []
    keys["Shift+Ctrl+Z"].activated.emit()
    assert len(service.profiles[0].replacements) == 1
    shell.window.show_screen("settings")  # undo belongs to the Replacements screen
    keys["Ctrl+Z"].activated.emit()
    assert len(service.profiles[0].replacements) == 1

    keys["Ctrl+Return"].activated.emit()
    assert service.holder.current.swaps() == {1111111: 2222222}
    assert stub.calls == ["clear"]  # Roblox isn't running: nothing to restart, the cache moves


@pytest.mark.spec("S-22", 3)
def test_the_first_texture_swap_guide_steps_6_to_9_with_real_size_ids(
    made: tuple[Shell, StubSprout], qtbot: QtBot
) -> None:
    """docs/guides/first-texture-swap.md steps 6 to 9, through the real widgets and the proxy."""
    shell, stub = made
    service = shell.services.grafts
    assert service is not None
    # Step 6: Replacements › Add replacement, type both IDs, press Save; the row appears.
    shell.window.show_screen("replacements")
    screen = screen_of(shell)
    screen.empty.buttons[0].click()
    editor = screen.editor
    qtbot.keyClicks(editor.original, str(ABOVE_UINT32))
    qtbot.keyClicks(editor.target, str(ABOVE_INT32))
    assert editor.save.isEnabled(), editor.save.toolTip()
    qtbot.mouseClick(editor.save, Qt.MouseButton.LeftButton)
    assert editor.isHidden()
    assert screen.table.rowCount() == 1
    cells = [screen.table.item(0, column) for column in range(3)]
    assert [c.text() if c else None for c in cells] == [
        str(ABOVE_UINT32),
        str(ABOVE_INT32),
        "Asset ID",
    ]
    saved = json.loads((terrain.config_dir() / "profiles" / "My replacements.json").read_bytes())
    assert saved["replacements"][0]["original"] == {"asset_id": ABOVE_UINT32, "slot": None}
    assert saved["replacements"][0]["target"] == {"kind": "asset_id", "value": str(ABOVE_INT32)}
    # Step 7: Apply now with Roblox closed: the snapshot holds the exact IDs, and the toast says so.
    shell.window.header.apply_now.click()
    assert service.holder.current.swaps() == {ABOVE_UINT32: ABOVE_INT32}
    assert service.holder.current.hosts() == {rules.ASSET_BATCH_HOST}
    assert toasts(shell)[-1] == "Applied 1 replacement. They'll appear next time Roblox starts."
    assert stub.calls == ["clear"]
    # Steps 8 and 9: the Player's asset batch asks for the target; the answer comes back under
    # the original's ID, in both the number and the text form.
    grafter = Grafter(service.holder)
    for sent in (ABOVE_UINT32, str(ABOVE_UINT32)):
        items = [{"requestId": "r-0", "assetId": sent, "assetType": "Image"}]
        request = hyphae.Request(
            rules.ASSET_BATCH_HOST, b"POST", rules.ASSET_BATCH_PATH.encode(), (),
            json.dumps(items).encode(),
        )  # fmt: skip
        assert grafter.wants_request_body(request)
        asked = grafter.on_request(request)
        assert asked is not None and asked.body is not None
        target = ABOVE_INT32 if isinstance(sent, int) else str(ABOVE_INT32)
        assert json.loads(asked.body)[0]["assetId"] == target
        answer = [{"requestId": "r-0", "assetId": target, "location": "https://cdn.example/x"}]
        response = hyphae.Response(200, (), body=json.dumps(answer).encode())
        assert grafter.wants_response_body(asked, response)
        back = grafter.on_response(asked, response)
        assert back is not None and back.body is not None
        assert json.loads(back.body)[0]["assetId"] == sent


@pytest.mark.spec("S-20", 7)
def test_a_save_the_profile_refuses_shows_why_in_the_drawer(
    made: tuple[Shell, StubSprout], qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(grafts, "MAX_REPLACEMENTS", 1)
    screen = screen_of(made[0])
    screen.empty.buttons[0].click()
    editor = screen.editor
    for target in (ABOVE_INT32, ABOVE_INT32 + 1):
        editor.start(editor.folder)
        qtbot.keyClicks(editor.original, str(ABOVE_UINT32))
        qtbot.keyClicks(editor.target, str(target))
        qtbot.mouseClick(editor.save, Qt.MouseButton.LeftButton)
    assert not editor.isHidden()  # the second save was refused and the drawer stays open
    assert editor.problem.text() == "A profile can hold at most 1 replacements."
    service = made[0].services.grafts
    assert service is not None
    assert len(service.profiles[0].replacements) == 1


@pytest.mark.spec("S-21", 16)
def test_apply_now_says_when_replacements_couldnt_be_prepared(
    made: tuple[Shell, StubSprout],
) -> None:
    shell, _stub = made
    service = shell.services.grafts
    assert service is not None
    profile = service.edit("create", "A")
    service.edit(
        "add_replacement",
        profile.id,
        grafts.Original(asset_id=1111111),
        grafts.Target(kind="file", value="./gone.png"),
    )
    shell.window.header.apply_now.click()
    assert "1 replacement couldn't be prepared. See the warnings in Replacements." in toasts(shell)
