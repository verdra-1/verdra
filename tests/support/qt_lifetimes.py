# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Guard: no Qt object a test made outlives that test (enabled for every test in tests/conftest).

Twice a UI test failed only sometimes, on Linux, because a Qt object outlived the test that made
it (#33 and the failure on main after #44). pytest-qt's `deleteLater()` only takes effect in a
later test's event loop, so a window was destroyed in the middle of another test, and a Python
wrapper of a layout item that Qt had freed was handed back for a new object made at the same
address. After every test this guard:

1. carries out the deletions the test asked for (pending `deleteLater()` calls), inside that test;
2. fails if a window or dialog the test made is still alive, naming it;
3. fails if a Python wrapper of a layout item (`QWidgetItem`,
   `QSpacerItem`) is stale: its item is in no live layout any more. PySide makes such wrappers
   for `itemAt()` and when a filled layout is added with `addLayout()`, and keeps them
   registered by address after Qt frees the item. (A wrapper whose item is still in its layout
   is harmless.) `QLayout.indexOf(item)` compares addresses only, so the check never reads a
   freed item.

A failure names the leftover and the fix; the leftover is then closed and deleted so it can't
spill into the next test. The guard has no exceptions (plan 16.2, "M1 decisions"): it checks every
test once a Qt application exists, whether or not the test asked for the `qapp` or `qtbot`
fixture, and no test can opt out.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QLayout, QLayoutItem, QWidget


def windows() -> dict[int, QWidget]:
    """Return the live top-level windows that have no parent, by C++ address."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return {}
    return {
        shiboken6.getCppPointer(widget)[0]: widget
        for widget in app.topLevelWidgets()
        if widget.parentWidget() is None and shiboken6.isValid(widget)
    }


def flush_deletions() -> None:
    """Carry out every pending `deleteLater()` now."""
    if QCoreApplication.instance() is not None:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def item_wrappers() -> list[QLayoutItem]:
    """Return live Python wrappers of layout items that aren't layouts themselves.

    Shiboken's own registry lists every wrapper it still maps to an address, including a stale
    one (PySide can't know Qt freed the item), and is much smaller than every Python object.
    """
    return [
        item
        for item in shiboken6.getAllValidWrappers()
        if isinstance(item, QLayoutItem) and not isinstance(item, QLayout)
    ]


def stale_item_wrappers() -> list[QLayoutItem]:
    """Return item wrappers whose item is in no live layout (Qt may have freed it)."""
    wrappers = shiboken6.getAllValidWrappers()
    layouts = [o for o in wrappers if isinstance(o, QLayout) and shiboken6.isValid(o)]
    items = [o for o in wrappers if isinstance(o, QLayoutItem) and not isinstance(o, QLayout)]
    del wrappers
    return [item for item in items if all(layout.indexOf(item) < 0 for layout in layouts)]


def describe(widget: QWidget) -> str:
    name = widget.objectName()
    return f"{type(widget).__name__}{f' {name!r}' if name else ''}"


def problems_after(before: set[int]) -> list[str]:
    """Return what this test left behind, then clean it up.

    Stale layout-item wrappers are looked for first, while the test's windows are still alive:
    deleting a window releases them, which would hide a stale wrapper the test made.
    """
    problems: list[str] = []
    stale = stale_item_wrappers()
    if stale:
        kinds = ", ".join(sorted({type(item).__name__ for item in stale}))
        problems.append(
            f"{len(stale)} stale Python wrapper(s) of layout items ({kinds}): their items "
            "left the layout, and PySide would hand the wrapper back for a new object made "
            "at the same address. Don't keep itemAt() results; find widgets with "
            "layout.indexOf(widget)."
        )
        del stale
    flush_deletions()
    leftovers = [widget for address, widget in windows().items() if address not in before]
    if leftovers:
        names = ", ".join(sorted(describe(widget) for widget in leftovers))
        problems.append(
            f"windows still alive after the test that made them: {names}. Register each with "
            "qtbot.addWidget() or delete it (deleteLater) before the test ends."
        )
        for widget in leftovers:
            widget.close()
            widget.deleteLater()
        flush_deletions()
    return problems


@pytest.fixture(autouse=True)
def qt_lifetimes() -> Iterator[None]:
    """Fail a test that leaves Qt windows or layout-item wrappers behind."""
    before = set(windows())
    yield
    if QCoreApplication.instance() is None:
        return
    problems = problems_after(before)
    if problems:
        pytest.fail("Qt objects outlived the test:\n- " + "\n- ".join(problems), pytrace=False)
