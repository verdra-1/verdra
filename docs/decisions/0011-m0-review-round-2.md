# 0011. Decisions from the second M0 review round

- **Status:** Accepted
- **Date:** 2026-10-02
- **Plan sections:** 3.2, 4.3, 5.2, 6.3, 6.4, 6.8, 8.2, 8.4, 12.3, 16.2 ("M0 review round 2
  decisions"), Reference R1, R2, R4, R5

## Context

The maintainer answered the open findings of the first self-review (decision record 0010) and
changed the plan to match (16.2, 2 October 2026). This record lists what that means for the
code, so later sessions don't undo it.

## Decision

### Spelling in code

US spelling now covers code identifiers, settings keys, command-line flags and the tools' file
names, not only what the user sees. There are no users yet, so nothing is migrated. Renamed,
among others: `general.start_minimized`, `--minimized`, `tools/check_colors.py`,
`tools/licenses.py`, `[tool.verdra.licenses]`, `JobCanceledError` and the job state "canceled",
`CLIENT_BEHAVIOR`, every `color` identifier. Format IDs (`verdra.catalogue`) and the nature
names stay as they are; docstrings that mirror R1 job lines keep the plan's wording. The UI says
"catalog". `tools/check_spelling.py` now also checks every identifier and flag in `src/`,
`tools/`, `tests/` and `packaging/`.

### Settings

`advanced.detailed_logging_since` is in R2: a hidden UTC timestamp or null, set when detailed
logging is turned on and cleared when it's turned off, so detailed logging switches itself off
after 24 hours, also across restarts. An unknown key is reported once (remembered in
`state.json`); unknown keys alone never make Verdra rewrite the file.

### Interface

- `ink-disabled` stays as it is; plan 5.2 now asks for at least 2.5:1 on every ground in both
  themes (disabled controls are exempt under WCAG). A test checks bg, surface, surface-raised and
  surface-sunken.
- The focus ring (6.4: 2 px solid, 2 px offset) is drawn by `VerdraStyle`, a QProxyStyle on
  Fusion, as `PE_FrameFocusRect` on a transparent overlay around the keyboard-focused control. A
  style sheet can only paint inside a widget, so the offset needs the overlay; the style sheet's
  own focus borders are gone. A mouse click shows no ring.
- Every full sentence the app shows has a catalogue ID; IDs new to R5 are listed word for word
  in their spec (S-01, S-02, S-03), as R5 requires. Short labels need no ID but are in the
  catalogue. Plural forms work: `verdra_en.qm` is built from the catalogue and loaded at startup.
- Messages use their R5 kind: M-SET-01 and M-SET-02 are inline notices above the screens,
  M-SET-03 an inline notice on Settings and on every control it disables.
- The F1 overlay lists only shortcuts that work in this build.
- Custom icons as 6.8 lists them (graft, seed, tweaks, leaf, node, vine, seedling), each with a
  hand-tuned 16 px variant.

### Architecture

- canopy is widgets only (R1): the OS reduced-motion query, the legal texts, the build ID and
  the support-bundle paths come from trunk; settings are saved in the background. Reading
  Verdra's own bundled assets (tokens, icons, fonts) stays in `theme.py` and `splash.py`, as R1
  assigns it. An import-linter contract and a test check this.
- The layering can't be bypassed: ruff bans dynamic imports in `src/` (TID251), a test catches
  the built-in `__import__` and lower layers reached through names trunk re-exports, and
  `tests/test_layering.py` proves `lint-imports` breaks on injected forbidden imports.
- Qt modules outside 8.1 are blocked at import: `__main__` installs `startup.QtGuard` before the
  UI loads.
- Startup follows 8.4 exactly: the single-instance hand-over and the settings come before the Qt
  application.

### Licences and files

- AFL-2.1 (the libdbus-1 headers in Qt D-Bus) is a named exception, and NumPy's reason names
  the GCC Runtime Library Exception 3.1 (decision record 0010).
- Every source and config file Verdra writes carries the SPDX header, generated SVGs and the
  message catalogue included; `tests/test_headers.py` checks it.
- The colour gate also catches `rgb()`, `hsl()`, `QColor(…)` from numbers or names, Qt's named
  colours and CSS colour names.

### CI

CI runs on pull requests and on pushes to `main` only. Decision record 0012 says where each job
runs to save Actions minutes.

## Consequences

- New identifiers must use US spelling; the gate fails otherwise.
- New sentences need a catalogue ID and a line in their spec; the tests fail otherwise.
- The FastFlag tracker is credited in the README by name once the FastFlags feature chooses it
  (plan 3.4 names none yet).
