# 0015. Diagnostic interception lives in a source-only module, roots/litmus.py

- **Status:** Accepted
- **Date:** 2026-10-03
- **Plan sections:** 8.2, 13.6, 16.2 ("Diagnostic interception at M1"), Reference R1, spec S-11
  (Behaviour "Diagnostic interception", tests 9 and 10)

## Context

Plan 16.2 settles that `--diagnose-interception` exists only when Verdra runs from source and is
absent from frozen builds. Spec S-11 test 10 asks that the frozen app reject the flag and that
`tools/check_build.py` prove the built folder holds no code path for it, through "a marker that
only the source-only module carries". The module tree of Reference R1 has no such module, so its
place has to be chosen. Two more facts shape the choice:

- `trunk/sapwood/cli` ignores unknown arguments on purpose (a launcher's extra arguments must not
  stop Verdra), so a frozen build has to refuse this one flag explicitly.
- The build puts modules into PyInstaller's compressed archive inside the executable, so a byte
  scan of the built folder alone would not find the marker.

## Decision

- The diagnostic code lives in one module, `src/verdra/roots/litmus.py` (litmus: a lichen dye used
  for testing). It builds the diagnostic interception (every 10.2 host, no symbionts, so nothing
  changes) and writes the TLS details of both sides of each connection to Activity (M-DIAG-02).
  It carries the string `MARKER`; nothing else does. The maintainer accepted the module on
  3 October 2026; Reference R1 and `docs/architecture.md` list it as source only.
- `trunk/sapwood/cli` accepts the flag only when Verdra isn't frozen and `roots/litmus.py` is
  present next to its package. Otherwise argparse rejects it with its own "unrecognized
  arguments" error and exit code 2, before logging, the window or routing start. The refusal
  needs no message ID: only developers pass the flag (plan 16.2, "M1 decisions").
- `packaging/verdra.spec` excludes `verdra.roots.litmus`. `tools/check_build.py` fails if the
  marker is in any loose file of the built folder or in any module of the executable's archive,
  or if an archived module has the diagnostic module's name; with `--launch` it also starts the
  built app with the flag and requires exit code 2 with no log written.
- With the flag, the window shows M-DIAG-01 as a Notice with no Dismiss button, and startup writes
  it to Activity. Routing itself is wired to the diagnostic interception when trunk starts the
  proxy (S-12 and S-14).

## Consequences

- The flag can't reach users by accident: a build that held the module would fail CI.
- R1 lists `roots/litmus.py` (accepted 3 October 2026, plan 16.2 "M1 decisions").
- At M2, when real features intercept, the module and the flag can be removed together with this
  record's checks.
