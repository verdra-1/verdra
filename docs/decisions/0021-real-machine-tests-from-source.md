# 0021. Real-machine tests run Verdra from source with tools\run-latest.ps1

- **Status:** Accepted
- **Date:** 2026-10-08
- **Plan sections:** 16.2 (real-machine tests, 8 October 2026), 13.5; amends 0019

## Context

Decision record 0019 made a test build ZIP the way the owner tests: download the artifact,
unzip, approve "Windows protected your PC", replace the old folder. Diagnostics such as
`--diagnose-interception` refuse to run in a frozen build (decision record 0015), so a test that
needs one couldn't use the ZIP, and each new build meant downloading and unzipping again. The
owner decided on 8 October 2026 that real-machine tests run from source.

## Decision

- The owner keeps a git clone of this repository and, before every test, runs one command in
  it: `powershell -ExecutionPolicy Bypass -File tools\run-latest.ps1`
  (guide: `docs/guides/run-from-source.md`).
- The script checks that its folder is the verdra repository and that git and uv exist, then:
  - switches to `main` and pulls with `--ff-only`. With local changes or local commits it stops
    and explains. It never resets, cleans, stashes, forces or deletes anything.
  - runs `uv sync --locked --python <.python-version>`, then starts Verdra with
    `uv run --locked python -m verdra`. Anything after the script's name goes to Verdra (a
    diagnostic option).
- Tests: on every system, the script contains no destructive command and is plain ASCII (Windows
  PowerShell 5.1 reads files without a byte-order mark in the local code page). On the Windows
  runner, it runs against throwaway repositories with a fake `uv`: a clean folder is
  fast-forwarded, a folder with changes or local commits is refused and left as it was, a folder
  that isn't verdra is refused, and Verdra gets the arguments given.
- `.github/workflows/test-build.yml` and the ZIP stay (decision record 0019), but no test needs
  them any more.

## Open item

How releases are distributed is not decided. The owner's recommendation for 0.1.0 is GitHub
Releases in this same repository, built by CI from the tagged source, not a separate
repository. It is decided before 0.1.0 is tagged.

## Consequences

- Test guides start with the one command and need no download, unzip or SmartScreen step.
- The owner needs git and uv once (the guide installs only what's missing).
