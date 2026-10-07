# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The Qt lifetime guard (tests/support/qt_lifetimes) catches what outlives a test."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from tests.support import qt_lifetimes


def test_a_window_left_alive_is_named(qapp: QApplication) -> None:
    before = set(qt_lifetimes.windows())
    window = QWidget()
    window.setObjectName("forgotten")
    window.show()
    problems = qt_lifetimes.problems_after(before)
    assert len(problems) == 1
    assert problems[0].startswith("windows still alive after the test that made them: QWidget")
    assert "'forgotten'" in problems[0]
    assert qt_lifetimes.windows().keys() <= before  # and the guard deleted it


def test_a_stale_layout_item_wrapper_is_named(qapp: QApplication) -> None:
    """The #33 / #44 pattern: an itemAt() wrapper outlives its item, freed when the widget left."""
    from PySide6.QtCore import QCoreApplication, QEvent

    before = set(qt_lifetimes.windows())
    window = QWidget()
    layout = QVBoxLayout(window)
    label = QLabel("x")
    layout.addWidget(label)
    layout.itemAt(0)  # PySide keeps this wrapper registered as long as the layout's wrapper
    assert qt_lifetimes.stale_item_wrappers() == []  # still in its layout: harmless
    label.deleteLater()  # the widget leaves; Qt frees its layout item
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    window.deleteLater()
    problems = qt_lifetimes.problems_after(before)
    assert problems == [
        "1 stale Python wrapper(s) of layout items (QWidgetItem): their items left the layout, "
        "and PySide would hand the wrapper back for a new object made at the same address. "
        "Don't keep itemAt() results; find widgets with layout.indexOf(widget)."
    ]
    assert qt_lifetimes.item_wrappers() == []  # deleting the window released it


def test_wrappers_of_items_still_in_their_layout_are_fine(qapp: QApplication) -> None:
    """PySide wraps a filled sub-layout's items on addLayout(); that alone isn't a problem."""
    before = set(qt_lifetimes.windows())
    window = QWidget()
    outer = QVBoxLayout(window)
    inner = QVBoxLayout()
    inner.addWidget(QLabel("x"))
    outer.addLayout(inner)
    assert len(qt_lifetimes.item_wrappers()) == 1
    window.deleteLater()
    assert qt_lifetimes.problems_after(before) == []


def test_a_clean_test_passes(qapp: QApplication) -> None:
    before = set(qt_lifetimes.windows())
    window = QWidget()
    QVBoxLayout(window).addWidget(QLabel("x"))
    window.deleteLater()
    assert qt_lifetimes.problems_after(before) == []


def test_tests_without_the_qt_fixtures_are_checked_too() -> None:
    """No exceptions (plan 16.2): the guard doesn't depend on which fixtures a test asked for."""
    app = QApplication.instance() or QApplication([])
    assert app is not None
    before = set(qt_lifetimes.windows())
    window = QWidget()
    layout = QVBoxLayout(window)
    label = QLabel("x")
    layout.addWidget(label)
    layout.itemAt(0)
    label.deleteLater()
    qt_lifetimes.flush_deletions()
    window.deleteLater()
    problems = qt_lifetimes.problems_after(before)
    assert len(problems) == 1
    assert problems[0].startswith("1 stale Python wrapper(s) of layout items (QWidgetItem)")


def test_the_guard_has_no_way_to_exempt_a_test() -> None:
    """Plan 16.2, decision record 0017: no marker, fixture override or list can switch it off."""
    import ast
    import inspect
    import re
    from pathlib import Path

    from tests import conftest

    source = inspect.getsource(qt_lifetimes)
    tree = ast.parse(source)
    fixture = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "qt_lifetimes"
    )
    # The fixture takes nothing it could read a marker, a fixture name or a test name from.
    assert [arg.arg for arg in fixture.args.args] == []
    lowered = source.lower()
    for word in ("request", "marker", "get_closest_marker", "skip", "exempt", "allow", "ignore"):
        assert word not in lowered, f"the guard mentions {word!r}"
    # It is always on, and nothing else defines (and so overrides) its fixture.
    assert "tests.support.qt_lifetimes" in conftest.pytest_plugins
    tests = Path(__file__).resolve().parent
    overrides = [
        str(path.relative_to(tests))
        for path in tests.rglob("*.py")
        if path.name != "qt_lifetimes.py"
        and re.search(r"^\s*def qt_lifetimes\(", path.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert overrides == []


def test_a_timer_left_running_is_named_and_stopped(
    qapp: QApplication,  # noqa: ARG001
    tmp_path: Path,
) -> None:
    """Guard 4: the settings save timer that broke tests/soil/test_atomic.py (7 October 2026)."""
    from verdra.trunk.almanac.store import SettingsStore

    before = set(qt_lifetimes.windows())
    timers_before = set(qt_lifetimes.running_timers())
    store = SettingsStore(tmp_path / "settings.json")
    store.load()
    store.set("appearance.theme", "dark")  # starts the 300 ms save timer
    problems = qt_lifetimes.problems_after(before, timers_before)
    assert len(problems) == 1
    assert (
        "Qt timers still running after the test that started them: SettingsStore (300 ms)"
        in (problems[0])
    )
    assert qt_lifetimes.running_timers().keys() <= timers_before  # stopped, so it can't fire later
    # Finishing what owns it, as the shared fixtures now do, leaves nothing running.
    store.set("appearance.theme", "light")
    store.flush(final=True)
    assert qt_lifetimes.problems_after(before, timers_before) == []
