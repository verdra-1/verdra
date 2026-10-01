# 0005. Data layout on disk

- **Status:** Accepted
- **Date:** 2026-10-01
- **Plan sections:** 9.1, 9.2, 9.3, 9.7

## Context

Verdra keeps settings, profiles, a change ledger, captured assets and logs. People share
profiles, back folders up, and expect uninstalling to remove everything. Files must survive a
crash mid-write, and future versions must be able to read old files.

## Decision

- **Locations** come from platformdirs, per kind (config, library, logs, exports), using the
  folders in plan 9.1. Secrets live only in the OS secret store.
- **Config folder** holds `settings.json`, `state.json`, `changes.json`, `profiles/`, `climate/`,
  `tweaks/`, `presets/`, `trust/ca.crt` and (only when kept) `traffic.json` (9.2). UI state
  (window geometry, splitters, columns) lives in `state.json`, not in settings.
- **Formats:** every JSON file starts with `format` and `version`; UTF-8, two-space indent,
  newline at the end. Public formats get a JSON Schema in `docs/schemas/`.
- **Writes** go through one helper, `soil/atomic.py`: temporary file in the same folder, write,
  fsync, `os.replace`, and on macOS and Linux an fsync of the folder. Settings, ledger and
  profiles keep the previous version as `.bak`.
- **Reads:** on a parse error the `.bak` is tried; if both fail, the file is moved to
  `<name>.broken-<timestamp>` and defaults are used, with a notice naming the file.
- **Migrations** are pure functions from version N to N+1, chained, one test per step. A file
  from a newer Verdra opens read-only.

## Consequences

- The library can move (Settings › Library) because nothing hard-codes its path.
- Every writer must use `soil/atomic.py`; a second write path would be a defect.
- Uninstall plus Reset everything can name the exact folders to remove (PRIVACY.md).
