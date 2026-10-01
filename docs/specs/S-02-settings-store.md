# S-02 Settings store

**Status:** Built
**Milestone:** M0
**Risk badge:** none
**Plan sections:** 7.7, 9.1, 9.2, 9.3, 9.7, Reference R2

## Purpose

Typed, versioned, crash-safe settings with one screen that shows them all.

## Behaviour

- Settings live in `settings.json` in the config folder (plan 9.1), format `verdra.settings`,
  version 1. Every key, type, default and range is defined once, as msgspec structs in
  `trunk/almanac/schema.py`, following Reference R2.
- At startup the file is loaded, validated against the schema and migrated if it is older. A
  missing file means defaults (and no notice).
- Validation, key by key (R2):
  - a missing key takes its default;
  - an unknown key is kept in the file but ignored, and reported once in Activity;
  - a value of the wrong type or out of range is replaced by the default and reported in
    Activity.
- Every change is saved atomically, debounced by 300 ms: several changes within that window are
  written once. Pending changes are flushed on quit. Other parts of the app subscribe to changes
  by key and are notified on the Qt thread.
- Reading falls back in this order (plan 9.7): `settings.json`; if it can't be parsed,
  `settings.json.bak` (M-SET-01); if both fail, the damaged file is moved to
  `settings.json.broken-<timestamp>` and defaults are used (M-SET-02).
- A file with a higher `version` than this Verdra knows opens **read-only**: the values it has
  are used where the schema understands them, nothing is ever written back, and M-SET-03 is
  shown.
- Migrations are pure functions from version N to N+1, chained, with a fixture file and a test
  per step.
- The Settings screen shows every key from R2's groups General, Routing, Library, Appearance,
  Privacy & safety and Advanced, with the labels from R2, plus the System changes group (filled
  by S-16). Feature-state keys (R2 "Feature state") are edited on their own screens, not here.
  Each group has "Reset to defaults", which resets that group's keys only.
- Controls for features that don't exist yet are shown disabled with a tooltip saying why.

## Rules

1. Every write goes through `soil/atomic.py`: temporary file in the same folder, write, fsync,
   `os.replace`, and on macOS and Linux an fsync of the folder. The previous good file is kept as
   `settings.json.bak`.
2. Unknown keys are preserved on save, so a newer Verdra's settings survive a downgrade round
   trip.
3. A newer-version file is never overwritten.
4. Secrets are never stored in settings (plan 10.6).
5. The file is UTF-8, two-space indented, with a newline at the end, and starts with `format` and
   `version`.
6. UI state (window geometry, splitters, columns, sidebar, last screen) is not a setting; it
   lives in `state.json`, which is free-form and safe to delete.

## Messages

- M-SET-01 "Your settings file was damaged. Verdra restored the last good copy."
- M-SET-02 "Your settings file couldn't be read, so Verdra started with default settings. The
  damaged file was kept as <name>."
- M-SET-03 "This file was made by a newer Verdra. Update Verdra to edit it."

## Acceptance tests

1. A process killed during a write leaves a valid `settings.json` (old or new), never a partial
   file.
2. A corrupt `settings.json` with a good `.bak` → the `.bak` is restored and M-SET-01 is shown.
3. Both corrupt → defaults are used, the damaged file is moved to
   `settings.json.broken-<timestamp>`, and M-SET-02 names it.
4. Every older fixture version migrates to the current version with the expected values.
5. A newer-version file opens read-only with M-SET-03 and is never overwritten.
6. Unknown keys are kept on save and reported once in Activity.
7. A wrong-type or out-of-range value is replaced by its default and reported in Activity.
8. Ten changes within 300 ms produce exactly one write.
9. Every key in R2's Settings-screen groups has a control on the Settings screen, and "Reset to
   defaults" resets only that group.
10. Every R2 key exists in the schema with the R2 default.

## Lives in

`trunk/almanac/*`, `soil/atomic.py`, `soil/terrain.py` (folder paths), `canopy/screens/settings.py`.

## Refinements from the plan

- **`advanced.worker_threads`**: S-04 in the plan says 2 to 8 workers; R2 says 1 to 16. This
  spec and S-04 follow R2 (the settings reference); S-04 in the plan needs the matching edit.
- **Text size values**: plan 6.2 offers 90, 100, 115 and 130 %; R2 (`appearance.text_scale`)
  says "90–130, step 10". The schema accepts exactly the four values from 6.2, which the S-01
  spec also uses; R2 needs the matching edit.
- **`advanced.detailed_logging_since`** (not in R2) records when detailed logging was turned on,
  so it can turn itself off after 24 hours across restarts (S-03). It isn't shown on the screen.
- "Unknown keys kept but ignored" (plan S-02) and "reported once" (R2) are combined.
- Read-only behaviour for newer files is defined precisely (values used, never written).
