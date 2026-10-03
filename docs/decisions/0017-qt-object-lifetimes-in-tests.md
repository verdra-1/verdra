# 0017. No Qt object outlives the test that made it; the guard has no exceptions

- **Status:** Accepted
- **Date:** 2026-10-03
- **Plan sections:** 12.1, 16.2 ("M1 decisions": a test that fails only sometimes is a real bug;
  the Qt lifetime guard has no exceptions), Reference R1

## Context

After #44 merged, `main` failed on Linux in two UI tests that passed elsewhere
([run 37110221102](https://github.com/verdra-1/verdra/actions/runs/37110221102)). #44 was
reverted (#45) and the cause was found in #46:

1. **Windows outlived their tests.** pytest-qt's teardown asks for `deleteLater()`, which runs
   only in a later test's event loop, so a window was destroyed in the middle of another test.
2. **Failure 1, cause proven and reproduced.** PySide keeps the Python wrapper of an
   `itemAt()` result alive with its layout. When Qt freed the item and a new object was made at
   the same address, PySide handed back the stale `QWidgetItem` wrapper. Forced address reuse
   gave the exact error in 1 of 300 trials with `itemAt()` and 0 of 300 without it.
3. **Failure 2, probable cause, not reproduced.** `Dew.eventFilter` ran on a toast stack whose
   attributes were already gone.
   - Evidence available: CI's traceback (Qt calling the filter during window teardown), and a
     probe showing main windows destroyed inside later tests (point 1).
   - Evidence not obtained: a run that fails this way on demand (12 repeat runs under CI's
     conditions, with frequent and forced garbage collection, all passed), and a trace tying
     that failure to a particular leftover window (the CI log has none).
   - So the cause is recorded as probable: the window teardown of point 1. Its precondition was
     removed, and the filter was hardened with a test that empties the attributes the same way.

## Decision

- Every test runs under `tests/support/qt_lifetimes.py`. After the test it carries out pending
  deletions, then fails if a window the test made is still alive, or if a layout-item wrapper is
  stale (its item is in no live layout). It applies to every test once a Qt application exists;
  there is no marker, fixture or list that exempts a test, and a test fails if one is added.
- Tests find a layout's widgets with `QLayout.indexOf`, never by keeping `itemAt()` results.
- The nightly workflow runs the whole suite several times in a shuffled order
  (`tests/support/shuffle.py`), so order-dependent failures show up before they reach `main`.
- A test that fails only sometimes is treated as a real bug: find the cause, fix it, add a guard
  for the whole category, and prove it with repeated shuffled runs (plan 16.2).

## Consequences

- A test that leaves a window or a stale wrapper behind fails with a message naming it and the
  fix, instead of breaking a later test at random.
- Each test pays for one pass over Shiboken's wrapper list; the suite got faster, not slower
  (#48: 92 s against 99 s before the guard covered every test).
- Exempting a test is not an option; the test or the app has to be fixed.
