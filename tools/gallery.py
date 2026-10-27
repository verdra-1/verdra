# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""D1 screenshot gallery and the law 1 check (design laws, decision record 0027).

Builds today's app offscreen over a throwaway `VERDRA_HOME` (no routing, no Roblox, nothing on
the system changes), opens every screen, dialog and state it can reach, and for each
configuration saves a PNG of each scene and checks every visible widget against law 1
("nothing is cut off"):

- a button, check box, radio button or tab narrower than its own size hint;
- a one-line label whose text is wider than its room, or a wrapped label taller than its room;
- a combo box narrower than its longest choice;
- a table header narrower than its title, and a table cell whose text doesn't fit (reported
  apart: law 2 lets paths, links, asset names and log messages shorten in the middle);
- a label that shows "…" while its tooltip holds a longer text (elided).

Configurations: text scale 100, 115, 150 and 200 % (150 and 200 % are set on the theme
directly, since Settings offers 90 to 130 % today), light and dark, the smallest and the
default window, and the pseudo-language of law 1 (strings under 20 characters doubled, longer
ones 40 % longer, with accents). Windows contrast themes aren't rendered: CI can't switch one
on without changing the runner's system settings, and Verdra doesn't read them yet (audit).

    uv run python tools/gallery.py OUT                 every configuration, report only
    uv run python tools/gallery.py OUT --strict        exit 1 if a redesigned screen breaks law 1
    uv run python tools/gallery.py OUT --quick         100 % light, both windows (local)

Writes OUT/<config>/<NN-scene>.png, OUT/law1.json (every finding) and OUT/law1.md (a summary).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import math
import os
import re
import sys
import tempfile
from collections.abc import Callable, Collection, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

TEXT_SCALES = (100, 115, 150, 200)
THEMES = ("light", "dark")
WINDOWS = ("minimum", "default")
#: One pixel of slack: text metrics and widget widths round differently.
SLACK = 1
#: Qt's own margin around a line edit's text, each side (QLineEdit's horizontal margin).
PLACEHOLDER_MARGIN = 2

#: Screens whose redesign (D3) has landed and must stay within law 1 ("nothing is cut off").
#: `--strict` fails on any law 1 finding in one of these scenes (the CI gate); every other scene
#: is still report-only while its redesign is pending — D1 left ~334 findings across the
#: un-redesigned app, and failing on those would block every unrelated change. Each D3 pull
#: request adds its scene name(s) here as it lands (plan Part C phase 2; decision record 0027).
#: Names are the base scene names in `_scenes()`, e.g. "window-frame", "status-error".
CLEAN_SCREENS: frozenset[str] = frozenset({"window-frame"})


def _scene_base(scene: str) -> str:
    """The base name of a scene: without its `NN-` number prefix or `-minimum`/`-default` size."""
    scene = re.sub(r"^\d+-", "", scene)
    return re.sub(r"-(minimum|default)$", "", scene)


#: Letters with an accent, for the pseudo-language (law 1).
_ACCENTED = str.maketrans("aceinouyACEINOUY", "áçéîñöüýÁÇÉÎÑÖÜÝ")
_FILLER = "Ŀőŗéḿ ïƥŝűḿ ďőłőŗ ŝïţ áḿéţ "


def pseudo(text: str) -> str:
    """Return `text` in the pseudo-language of law 1, its placeholders and markup intact.

    Under 20 characters it is doubled ("Apply now" → "Áppły ñöw Áppły ñöw"); longer, it gets
    40 % more characters. `{name}`, `%n`, `%1`, `<tags>`, `&entities;` and line breaks stay.
    """
    if not text.strip():
        return text
    parts: list[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        end = {"{": "}", "<": ">", "&": ";"}.get(char)
        stop = text.find(end, i) if end else -1
        if end and stop != -1 and (char != "&" or stop - i < 10):
            parts.append(text[i : stop + 1])
            i = stop + 1
        elif char == "%" and i + 1 < len(text) and (text[i + 1].isdigit() or text[i + 1] == "n"):
            parts.append(text[i : i + 2])
            i += 2
        else:
            parts.append(char.translate(_ACCENTED))
            i += 1
    accented = "".join(parts)
    if len(text) < 20:  # noqa: PLR2004 - law 1's threshold
        return f"{accented} {accented}" if "\n" not in text else f"{accented}\n{accented}"
    extra = math.ceil(len(text) * 0.4)
    filler = (_FILLER * (extra // len(_FILLER) + 1))[:extra].strip()
    return f"{accented} {filler}"


@dataclass
class Finding:
    """One widget whose text doesn't fit (law 1), or a shortened table cell (law 2)."""

    config: str
    scene: str
    kind: str  # "button", "label", "wrapped label", "combo", "tab", "header", "elided", "cell"
    widget: str
    text: str
    needed: int
    available: int


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list[Finding])
    scenes: list[str] = field(default_factory=list[str])

    def law_one(self) -> list[Finding]:
        """The findings that break law 1 (table cells are law 2 and listed apart)."""
        return [f for f in self.findings if f.kind != "cell"]

    def enforced(self, clean: Collection[str]) -> list[Finding]:
        """Law 1 findings on a redesigned screen: what `--strict` fails on (A.7, decision 0027).

        Every other screen stays report-only while its redesign (D3) is pending; each D3 pull
        request adds its scene's base name to `clean` (CLEAN_SCREENS) as it lands. Scenes are
        matched by base name (without the `NN-` number prefix or `-minimum`/`-default` size
        suffix), so the set keeps working as scenes are added and renumbered.
        """
        return [f for f in self.law_one() if _scene_base(f.scene) in clean]


def cut_off(root: Any, config: str, scene: str) -> list[Finding]:
    """Return every visible widget under `root` whose text doesn't fit (law 1)."""
    from PySide6.QtWidgets import QAbstractItemView, QWidget  # noqa: PLC0415

    found: list[Finding] = []
    for widget in [root, *root.findChildren(QWidget)]:
        if widget is not root and not (widget.isVisibleTo(root) and widget.isVisible()):
            continue
        name = type(widget).__name__ + (f"#{widget.objectName()}" if widget.objectName() else "")
        for kind, text, needed, available in _widget_cut_off(widget):
            found.append(Finding(config, scene, kind, name, text[:200], needed, available))
        if isinstance(widget, QAbstractItemView) and widget.model() is not None:
            found.extend(_view_cut_off(widget, config, scene))
    return found


Problem = tuple[str, str, int, int]  # kind, text, needed, available


def _widget_cut_off(widget: Any) -> list[Problem]:
    """What doesn't fit in one widget: its own text, or one of its tabs."""
    from PySide6.QtWidgets import (  # noqa: PLC0415
        QAbstractButton,
        QComboBox,
        QLabel,
        QLineEdit,
        QStyle,
        QStyleOptionFrame,
        QTabBar,
    )

    problems: list[Problem] = []
    if isinstance(widget, QAbstractButton) and widget.text():
        hint = widget.sizeHint().width()
        if widget.width() + SLACK < hint:
            problems.append(("button", widget.text(), hint, widget.width()))
    elif isinstance(widget, QLabel) and widget.text() and widget.pixmap().isNull():
        problems.extend(_label_cut_off(widget))
    elif isinstance(widget, QLineEdit) and widget.placeholderText() and not widget.text():
        option = QStyleOptionFrame()
        widget.initStyleOption(option)
        contents = widget.style().subElementRect(
            QStyle.SubElement.SE_LineEditContents, option, widget
        )
        room = contents.width() - 2 * PLACEHOLDER_MARGIN
        needed = widget.fontMetrics().horizontalAdvance(widget.placeholderText())
        if needed > room + SLACK:
            problems.append(("placeholder", widget.placeholderText(), needed, room))
    elif isinstance(widget, QComboBox) and widget.count():
        hint = widget.sizeHint().width()
        if widget.width() + SLACK < hint:
            problems.append(("combo", widget.currentText(), hint, widget.width()))
    if isinstance(widget, QTabBar):
        for index in range(widget.count()):
            rect, tab = widget.tabRect(index), widget.tabSizeHint(index)
            if rect.width() + SLACK < tab.width():
                problems.append(("tab", widget.tabText(index), tab.width(), rect.width()))
    return problems


def _label_cut_off(label: Any) -> list[Problem]:
    from PySide6.QtCore import Qt  # noqa: PLC0415
    from PySide6.QtGui import Qt as GuiQt  # noqa: PLC0415 - mightBeRichText lives in QtGui
    from PySide6.QtGui import QTextDocument  # noqa: PLC0415

    text = label.text()
    rich = label.textFormat() == Qt.TextFormat.RichText or (
        label.textFormat() == Qt.TextFormat.AutoText and GuiQt.mightBeRichText(text)
    )
    plain = text
    if rich:
        document = QTextDocument()
        document.setHtml(text)
        plain = document.toPlainText()
    problems: list[Problem] = []
    if label.wordWrap():
        needed = label.heightForWidth(label.width())
        if label.height() > 0 and needed > label.height() + SLACK:
            problems.append(("wrapped label", plain, needed, label.height()))
    else:
        room = label.contentsRect().width() - 2 * max(label.margin(), 0)
        metrics = label.fontMetrics()
        widest = max((metrics.horizontalAdvance(line) for line in plain.split("\n")), default=0)
        if widest > room + SLACK:
            problems.append(("label", plain, widest, room))
    tip = label.toolTip()
    if "…" in plain and tip and len(tip) > len(plain):
        problems.append(("elided", f"{plain} (full: {tip})", len(tip), len(plain)))
    return problems


def _view_cut_off(view: Any, config: str, scene: str) -> list[Finding]:
    """Headers narrower than their title, and cells narrower than their text (Qt's own size
    hints, which include the cell's margins); cells are law 2's business and listed apart."""
    from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt  # noqa: PLC0415
    from PySide6.QtWidgets import QTableView  # noqa: PLC0415

    found: list[Finding] = []
    model = view.model()
    # A list model hides columnCount (one column); every other model takes a parent index.
    columns = 1 if isinstance(model, QAbstractListModel) else model.columnCount(QModelIndex())
    name = type(view).__name__ + (f"#{view.objectName()}" if view.objectName() else "")
    table = isinstance(view, QTableView)
    if table:
        header = view.horizontalHeader()
        for column in range(columns):
            title = str(model.headerData(column, Qt.Orientation.Horizontal) or "")
            needed = header.sectionSizeHint(column)
            size = header.sectionSize(column)
            if title and not view.isColumnHidden(column) and size + SLACK < needed:
                found.append(Finding(config, scene, "header", name, title, needed, size))
    for row in range(min(model.rowCount(QModelIndex()), 50)):
        for column in range(columns):
            if table and view.isColumnHidden(column):
                continue
            index = model.index(row, column)
            text = str(model.data(index, Qt.ItemDataRole.DisplayRole) or "")
            rect = view.visualRect(index)
            # What shows: the cell, cut at the edge of the view's visible area.
            shown = min(rect.right(), view.viewport().width()) - max(rect.left(), 0)
            needed = view.sizeHintForIndex(index).width()
            if text and rect.width() > 0 and needed > shown + SLACK:
                found.append(Finding(config, scene, "cell", name, text, needed, max(shown, 0)))
    return found


# --- The app, offscreen ------------------------------------------------------------------------


class Overrides:
    """The settings store, with some appearance values set for one configuration."""

    def __init__(self, settings: Any, values: dict[str, Any]) -> None:
        self._settings = settings
        self._values = values

    def value(self, key: str) -> Any:
        return self._values[key] if key in self._values else self._settings.value(key)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._settings, name)


@dataclass(frozen=True)
class Config:
    theme: str
    scale: int
    pseudo: bool = False

    @property
    def name(self) -> str:
        return f"{self.theme}-{self.scale}" + ("-pseudo" if self.pseudo else "")


def configurations(*, quick: bool) -> list[Config]:
    if quick:
        return [Config("light", 100)]
    made = [Config(theme, scale) for theme in THEMES for scale in TEXT_SCALES]
    made += [Config(theme, 115, pseudo=True) for theme in THEMES]
    return made


def _services(app: Any) -> Any:
    from verdra.soil import terrain  # noqa: PLC0415
    from verdra.trunk import rings, tendrils  # noqa: PLC0415
    from verdra.trunk.almanac.store import SettingsStore, StateStore  # noqa: PLC0415
    from verdra.trunk.branches import grafts  # noqa: PLC0415
    from verdra.trunk.sapwood import cli  # noqa: PLC0415
    from verdra.trunk.sapwood.single import SingleInstance  # noqa: PLC0415
    from verdra.trunk.sapwood.startup import Services  # noqa: PLC0415

    settings = SettingsStore()
    settings.load()
    settings.set("general.onboarding_done", True)
    state = StateStore()
    state.load()
    logs = rings.Rings()
    logs.start()
    made = Services(
        app=app,
        arguments=cli.Arguments(),
        settings=settings,
        state=state,
        rings=logs,
        tendrils=tendrils.Tendrils(workers=1),
        single=SingleInstance(f"verdra-gallery-{os.getpid()}"),
    )
    made.grafts = grafts.Grafts(terrain.config_dir() / "profiles", settings)
    return made


def _sample_data(services: Any) -> None:
    """A profile with rows a user would make, and Activity lines from a session."""
    from verdra.trunk.branches import grafts  # noqa: PLC0415

    service = services.grafts
    service.edit("create", "Night mode")
    profile = service.edit("create", "My replacements")
    rows = [
        (15553230204, "file", r"C:\Users\Player\Pictures\Verdra tests\verdra-test-1600x900.png"),
        (498788302, "file", r"C:\Users\Player\Documents\Meshes\cube-with-a-long-name.obj"),
        (1111111, "asset_id", "2222222"),
        (12345678901, "url", "https://example.com/textures/brick-wall-weathered-2048.png"),
        (3333333, "remove", ""),
    ]
    for original, kind, value in rows:
        service.edit(
            "add_replacement",
            profile.id,
            grafts.Original(asset_id=original),
            grafts.Target(kind=kind, value=value),  # type: ignore[arg-type]
        )
    log = logging.getLogger("verdra.gallery")
    log.info("Routing status changed from Idle to Routing.")
    log.info("Started Roblox through Verdra (process 4242).")
    log.warning(
        "A Roblox Player that Verdra didn't start is running, so Verdra didn't move Roblox's "
        "saved assets aside. Close it, then click Apply now again."
    )
    log.info(
        r"Moved Roblox's saved assets (rbx-storage.db, rbx-storage) to C:\Users\Player\AppData"
        r"\Local\Verdra\Roblox cache backup\2026-10-16 20.40.17. Reset everything puts them back."
    )


Scene = Callable[[Any], Any]


def _window_frame(shell: Any) -> Any:
    """The window frame on its own (D3 screen 1): the sidebar and the header, so law 1 is
    enforced on the chrome without the un-redesigned screen bodies the window otherwise carries."""
    from PySide6.QtCore import QCoreApplication  # noqa: PLC0415
    from PySide6.QtWidgets import QHBoxLayout, QWidget  # noqa: PLC0415

    from verdra.canopy.crown.header import Header  # noqa: PLC0415
    from verdra.canopy.crown.sidebar import Sidebar  # noqa: PLC0415
    from verdra.roots.gardener import RoutingStatus, State  # noqa: PLC0415

    box = QWidget()
    box.resize(960, 680)
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    bar = Sidebar(box)
    if shell.services.grafts is not None:
        bar.set_profiles(shell.services.grafts.profiles)
    row.addWidget(bar)
    head = Header(box)
    head.set_title(QCoreApplication.translate("Sidebar", "Replacements"))
    head.set_routing(RoutingStatus(State.ROUTING))
    row.addWidget(head, 1)
    box.show()
    return box


def _scenes() -> list[tuple[str, str, Scene]]:
    """(name, window size or "dialog", how to show it) for every scene, in gallery order."""
    from PySide6.QtWidgets import QApplication  # noqa: PLC0415

    from verdra.canopy.crown.about import AboutDialog, TextViewer  # noqa: PLC0415
    from verdra.canopy.crown.seedling import Onboarding  # noqa: PLC0415
    from verdra.canopy.crown.shortcuts import ShortcutHelp  # noqa: PLC0415
    from verdra.canopy.leaves.dialogs import (  # noqa: PLC0415
        Choice,
        DestructiveConfirmation,
        Explanation,
        Information,
        RiskWarning,
    )
    from verdra.canopy.screens.rings import BundleDialog  # noqa: PLC0415
    from verdra.roots.gardener import RoutingStatus, State, Trigger  # noqa: PLC0415

    def screen(key: str) -> Scene:
        def show(shell: Any) -> Any:
            shell.window.show_screen(key)
            return shell.window

        return show

    def editor(shell: Any) -> Any:
        shell.add_replacement()
        return shell.window

    def banner_and_toasts(shell: Any) -> Any:
        shell.window.show_screen("replacements")
        shell.show_others(True)
        shell.window.dew.show(
            "Saved, but your replacements won't show until the Roblox running without Verdra "
            "is closed.",
            action=("Close that Roblox", lambda: None),
        )
        return shell.window

    def popover(status: Any) -> Scene:
        def show(shell: Any) -> Any:
            shell.window.header.set_routing(status)
            shell.window.header.open_popover()
            return shell.window.header.popover

        return show

    def dialog(make: Callable[[Any], Any]) -> Scene:
        def show(shell: Any) -> Any:
            made = make(shell)
            made.show()
            return made

        return show

    def settings_group(index: int) -> Scene:
        def show(shell: Any) -> Any:
            from PySide6.QtWidgets import QFrame, QScrollArea  # noqa: PLC0415

            shell.window.show_screen("settings")
            page = shell.window.screens["settings"]
            scroll = page.findChild(QScrollArea)
            panels = [
                p for p in page.findChildren(QFrame, "panel") if p.parent() is scroll.widget()
            ]
            if index >= len(panels):
                return None  # fewer groups than scenes
            QApplication.processEvents()
            scroll.verticalScrollBar().setValue(panels[index].y())
            QApplication.processEvents()
            return shell.window

        return show

    statuses = [
        ("idle", RoutingStatus(State.IDLE)),
        ("routing", RoutingStatus(State.ROUTING)),
        (
            "other-roblox",
            RoutingStatus(
                State.DEGRADED,
                Trigger.OTHER_PLAYER,
                "Roblox is already running without Verdra. Close it completely, then click "
                "Apply now.",
            ),
        ),
        (
            "no-asset-requests",
            RoutingStatus(
                State.DEGRADED,
                Trigger.NOT_REACHING,
                "Roblox isn't reaching Verdra: nothing from it came through in the minute after "
                "it started, so replacements can't apply. Save a support bundle and send it "
                "with your report.",
            ),
        ),
        (
            "error",
            RoutingStatus(
                State.ERROR,
                Trigger.PROXY_FAILED,
                "Verdra couldn't start routing: port 49443 is in use and no other port was free.",
            ),
        ),
    ]
    made: list[tuple[str, str, Scene]] = [
        ("window-frame", "frame", _window_frame),
        ("replacements", "window", screen("replacements")),
        ("replacements-editor", "window", editor),
        ("replacements-banner-toast", "window", banner_and_toasts),
        ("library", "window", screen("library")),
        ("tweaks", "window", screen("tweaks")),
        ("accounts", "window", screen("accounts")),
        ("activity", "window", screen("activity")),
        ("settings", "window", screen("settings")),
        *[(f"settings-group-{n + 1}", "window", settings_group(n)) for n in range(1, 10)],
        *[(f"status-{name}", "popup", popover(status)) for name, status in statuses],
        ("about", "dialog", dialog(lambda shell: AboutDialog(shell.window))),
        (
            "license",
            "dialog",
            dialog(lambda shell: TextViewer("License", _legal("LICENSE"), shell.window)),
        ),
        (
            "third-party-notices",
            "dialog",
            dialog(
                lambda shell: TextViewer(
                    "Third-party notices", _legal("THIRD_PARTY_NOTICES.md"), shell.window
                )
            ),
        ),
        ("onboarding", "dialog", dialog(lambda shell: Onboarding(shell.services.settings))),
        ("shortcuts", "dialog", dialog(lambda shell: ShortcutHelp(shell.window))),
        ("support-bundle", "dialog", dialog(lambda shell: BundleDialog(shell.window))),
        (
            "confirm-delete-profile",
            "dialog",
            dialog(
                lambda shell: DestructiveConfirmation(
                    "Delete profile My replacements?",
                    "Delete profile",
                    "Its 5 replacements are deleted with it. Undo brings them back.",
                    shell.window,
                )
            ),
        ),
        (
            "choice-roblox-running",
            "dialog",
            dialog(
                lambda shell: Choice(
                    "Roblox is already running without Verdra",
                    "If Verdra starts this game now, it opens in that Roblox and your "
                    "replacements don't show. Close it first, so the game opens through Verdra.",
                    "Close Roblox and continue",
                    "Continue anyway",
                    shell.window,
                )
            ),
        ),
        (
            "information-close-roblox",
            "dialog",
            dialog(
                lambda shell: Information(
                    "How to close Roblox completely",
                    "1. Leave your game and close every Roblox window.\n"
                    "2. If Roblox still runs, open Task Manager (Ctrl+Shift+Esc), select each "
                    '"Roblox" entry and click End task.\n'
                    "3. Back in Verdra, click Apply now, then join your game.",
                    shell.window,
                )
            ),
        ),
        (
            "risk-warning",
            "dialog",
            dialog(
                lambda shell: RiskWarning(
                    "Turn on Custom FastFlags?",
                    "Roblox may treat changed client settings as a breach of its rules.",
                    shell.window,
                )
            ),
        ),
        (
            "explanation",
            "dialog",
            dialog(
                lambda shell: Explanation(
                    "Multi-instance changes how Roblox starts",
                    "Verdra starts more than one Roblox at a time.",
                    account_sensitive=True,
                    parent=shell.window,
                )
            ),
        ),
    ]
    return made


def _legal(name: str) -> str:
    from verdra.trunk.sapwood import startup  # noqa: PLC0415

    return startup.legal_text(name) or ""


@contextlib.contextmanager
def _pseudo_language(app: Any, on: bool) -> Iterator[None]:
    """Install the pseudo-language translator for one configuration."""
    if not on:
        yield
        return
    from PySide6.QtCore import QTranslator  # noqa: PLC0415

    class Pseudo(QTranslator):
        def translate(  # type: ignore[override]
            self,
            context: str,
            source: str,
            disambiguation: str | None = None,
            n: int = -1,
        ) -> str:
            return pseudo(source)

        def isEmpty(self) -> bool:  # noqa: N802 - Qt API
            return False

    translator = Pseudo(app)
    app.installTranslator(translator)
    try:
        yield
    finally:
        app.removeTranslator(translator)
        translator.deleteLater()


def run(out: Path, *, quick: bool) -> Report:
    """Render every scene in every configuration into `out`; return what law 1 found."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication  # noqa: PLC0415

    from verdra.soil import terrain  # noqa: PLC0415

    report = Report()
    app = QApplication.instance() or QApplication(["verdra-gallery"])
    with tempfile.TemporaryDirectory() as home:
        os.environ[terrain.HOME_OVERRIDE_VARIABLE] = home
        services = _services(app)
        _sample_data(services)
        try:
            for config in configurations(quick=quick):
                with _pseudo_language(app, config.pseudo):
                    _render(app, services, config, out / config.name, report)
        finally:
            services.tendrils.shutdown(grace=0.5)
            services.settings.flush(final=True)
            services.rings.stop()
    return report


def _render(app: Any, services: Any, config: Config, folder: Path, report: Report) -> None:
    from PySide6.QtWidgets import QApplication  # noqa: PLC0415

    from verdra.canopy.crown import window as window_module  # noqa: PLC0415

    folder.mkdir(parents=True, exist_ok=True)
    services.settings.set("appearance.theme", config.theme)
    sizes = {"minimum": window_module.MINIMUM_SIZE, "default": window_module.DEFAULT_SIZE}
    number = 0
    for size_name in WINDOWS:
        shell = window_module.Shell(services)
        shell.theme.settings = Overrides(services.settings, {"appearance.text_scale": config.scale})
        shell.theme.apply()
        shell.build()
        shell.window.resize(sizes[size_name])
        shell.window.show()
        try:
            for name, kind, show in _scenes():
                if kind != "window" and size_name != "default":
                    continue  # dialogs and popups once per configuration
                shown = show(shell)
                if shown is None:
                    continue
                number += 1
                scene = f"{number:02d}-{name}" + (f"-{size_name}" if kind == "window" else "")
                for _ in range(3):
                    QApplication.processEvents()
                shown.grab().save(str(folder / f"{scene}.png"))
                report.scenes.append(f"{config.name}/{scene}")
                report.findings.extend(cut_off(shown, config.name, scene))
                if shown is not shell.window:
                    shown.close()
                    shown.deleteLater()
                for toast in list(shell.window.dew.toasts):
                    toast.dismiss()
                if shell.others_banner is not None:
                    shell.show_others(False)
        finally:
            shell.window.allow_close = True
            shell.window.close()
            shell.window.deleteLater()
            QApplication.processEvents()


def summary(report: Report) -> str:
    """The law 1 findings as Markdown, grouped by kind and text (one line per distinct text)."""
    lines = [
        "# Law 1 findings",
        "",
        f"{len(report.scenes)} scenes; {len(report.law_one())} findings break law 1; "
        f"{len(report.findings) - len(report.law_one())} table cells are shortened (law 2 "
        "allows that for paths, links, asset names and log messages only).",
        "",
    ]
    grouped: dict[tuple[str, str, str], list[Finding]] = {}
    for finding in report.findings:
        grouped.setdefault((finding.kind, finding.widget, finding.text), []).append(finding)
    for (kind, widget, text), items in sorted(grouped.items(), key=lambda item: item[0]):
        configs = sorted({f.config for f in items})
        scenes = sorted({f.scene for f in items})
        worst = max(items, key=lambda f: f.needed - f.available)
        lines.append(
            f"- **{kind}** `{widget}` {json.dumps(text, ensure_ascii=False)}: needs "
            f"{worst.needed}, has {worst.available}; in {', '.join(configs)}; scenes "
            f"{', '.join(scenes[:4])}{' …' if len(scenes) > 4 else ''}"  # noqa: PLR2004
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D1 screenshot gallery and law 1 check.")
    parser.add_argument("out", type=Path, help="the folder for the screenshots and the report")
    parser.add_argument("--quick", action="store_true", help="100 %% light only")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 if a redesigned (clean) screen breaks law 1; other screens stay report-only",
    )
    args = parser.parse_args(argv)
    report = run(args.out, quick=args.quick)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "law1.json").write_text(
        json.dumps([asdict(f) for f in report.findings], indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    text = summary(report)
    (args.out / "law1.md").write_text(text, encoding="utf-8")
    print(text.splitlines()[2])
    enforced = report.enforced(CLEAN_SCREENS)
    if CLEAN_SCREENS:
        print(f"{len(CLEAN_SCREENS)} redesigned screens enforced; {len(enforced)} break law 1")
    else:
        print("no redesigned screens yet; law 1 is report-only (D1)")
    if args.strict and enforced:
        scenes = ", ".join(sorted({f.scene for f in enforced}))
        print(f"law 1 broken in redesigned screens: {scenes}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
