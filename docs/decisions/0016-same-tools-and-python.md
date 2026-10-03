# 0016. Same tools and the same Python locally as in CI

- **Status:** Accepted
- **Date:** 2026-10-03
- **Plan sections:** 12.3, 12.6, 16.2 ("M1 decisions")

## Context

Two failures on pull request #44 passed every local check and failed in CI:

- `tools/check_build.py` imported PyInstaller at the top. PyInstaller is in the `build` group,
  which the Static gates and Tests jobs don't install; locally every group was installed, so
  pyright and the tests found it.
- A test built a client TLS object with hostname checking on and no server name. CI's runners
  had moved to Python 3.14.8, which refuses that; the local Python was 3.14.7, which allowed it.
  `.python-version` said only `3.14`, so each machine took whatever patch it had. CI's own two
  systems differed too: in Nightly run 37126695568 the Windows runner used 3.14.7 (its uv cache
  key names it) while the Linux runner used 3.14.8.

## Decision

- **Same dependency groups.** `tools/gates.py` reads `.github/workflows/ci.yml` and runs every
  `run:` step of each job in order, in the checkout, with that job's environment. Each job starts
  with its own `uv sync` step, and a step that widens the groups (the licence step's
  `uv sync --all-groups`) widens them only for the steps after it, as on the runner. Steps that
  need the runner (system packages, the other runners' coverage) are skipped and listed;
  pip-audit and gitleaks run with `--network`. Local gates are run with this script.
- **Same Python.** `.python-version` pins the exact patch, now **3.14.8**: the newest 3.14 that
  both CI and the development machine can install (uv 0.12.22 knows it; 0.12.21 didn't), and the
  one CI's runners were already using. Every CI test and build job checks that it runs exactly
  that patch, `tools/gates.py` checks it before anything else, and a test asserts it.
- **Newest Python, nightly.** A nightly job runs the whole suite on the newest 3.14.x on Windows
  and Linux. A failure opens an issue; it never blocks merges.
- **Moving the pin** is an ordinary pull request with a full green run.

## Consequences

- A check that passes only because another job's groups are installed fails locally too:
  `tools/gates.py --jobs checks` on #44's first head fails at "Types" with the same error as CI,
  while pyright with every group installed reports 0 errors.
- Local and CI Python can't drift apart silently; an upstream change shows up nightly first.
- Release builds use the newest patch that passes (plan 16.2).
