# S-20 Replacement profiles

**Status:** Agreed
**Milestone:** M2
**Risk badge:** Cosmetic
**Plan sections:** 7.2 (Replacements screen), 9.2 (`profiles/`), 9.3 (`verdra.profile` v1), 9.7
(atomic writes, `.bak`, migrations), 10.7 (imported profiles validated), 14 (M2: "Profile store
and schema"), Feature specs S-20, Reference R1 (`trunk/branches/grafts`,
`canopy/screens/grafts`), R5 (M-PROF-01 to M-PROF-03)

## Purpose

Organize replacements into named profiles that can be switched on and off.

## Behaviour

- **Profiles.** Create, rename, duplicate, delete, enable and disable profiles, and reorder them
  by drag. Each profile is one `verdra.profile` v1 file, `profiles/<name>.json` in the config
  folder (plan 9.2, 9.3), plus an optional folder `profiles/<name>/` for the files it uses,
  referenced inside the profile as `./<path>`.
- **Replacements.** Each replacement has an original (`asset_id`, and `slot` for one map of a
  TexturePack or `null`), a target (`kind` one of `asset_id`, `file`, `url`, `remove`, and its
  `value`), the original's `asset_type`, a `note`, and its own `enabled` switch.
- **Undo and redo** cover the last 50 edits of the session (add, edit, delete, reorder, enable,
  rename).
- **Watching.** The profiles folder is watched: a file added or changed outside Verdra is loaded
  within 2 s; if it changed while being edited in Verdra, the user picks "Keep mine" or "Use the
  file" (M-PROF-03).

## Rules

1. Order decides conflicts: a profile higher in the list wins for the same original asset (and
   slot). Within one profile, the later replacement for the same original wins.
2. Names must be valid file names on Windows and Linux (and macOS, for later): characters
   `<>:"/\|?*` and control characters are rejected as they are typed, as are names that are
   reserved on Windows (`CON`, `NUL`, `COM1`…), end with a dot or a space, or are longer than
   100 characters. Names are compared without regard to case (M-PROF-01).
3. At most 10,000 replacements per profile.
4. Files are written atomically with `.bak` (plan 9.7). A file that can't be parsed falls back to
   its `.bak`; if both fail, it is moved to `<name>.broken-<timestamp>` and an error notice names
   it. A file from a newer Verdra opens read-only.
5. A profile file is validated against `docs/schemas/verdra.profile.schema.json` before use
   (plan 10.7). Unknown keys are ignored and reported in Activity; a replacement that fails
   validation is kept in the file but left out of the rule snapshot, with its reason.

## Messages

- M-PROF-01 (inline) "A profile named <name> already exists."
- M-PROF-02 (Dialog) "Delete profile <name>?" Buttons "Delete", "Cancel".
- M-PROF-03 (Notice) "<name> was changed outside Verdra." Buttons "Keep mine", "Use the file".

## Acceptance tests

1. Round trip of every field through save and load, byte-identical for a file Verdra wrote.
2. External edits are picked up within 2 s; an edit during an unsaved change asks M-PROF-03 and
   each answer keeps the chosen version.
3. Conflict order is respected in the rule snapshot: the higher profile wins, and within a
   profile the later replacement wins.
4. Undo and redo across add, edit, delete, reorder, enable and rename, up to 50 steps.
5. Invalid names (each rule-2 case) are refused; names differing only in case clash (M-PROF-01).
6. A damaged profile falls back to its `.bak`; with both damaged it is moved aside and the
   others still load.
7. More than 10,000 replacements in a profile is refused when saving and when loading.

## Lives in

`trunk/branches/grafts.py`, `roots/rules.py` (the snapshot types), `canopy/screens/grafts/`,
`docs/schemas/verdra.profile.schema.json`.

## Refinements from the plan

- Tests 5 to 7 are added for rules 2 to 4.
- The profile order (rule 1) is kept in the setting `replacements.profile_order`, a list of
  profile IDs; a profile not in the list goes last, by name. The plan doesn't say where the
  order lives, and a profile file can't hold it without every reorder rewriting every file.
- "Within one profile, the later replacement wins" settles a case the plan leaves open.
