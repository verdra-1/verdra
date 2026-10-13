# S-26 Editing replacements in place

**Status:** Draft (waits for the owner's approval; no code before it)
**Milestone:** M2 follow-up, Editor 2.0 phase A (internal label 0.1.x)
**Risk badge:** Cosmetic
**Plan sections:** 7.2 (Replacements screen, editor drawer), 9.2 and 9.3 (`verdra.profile`), 9.7
(atomic writes, `.bak`, migrations), 10.7 (limits), 12.5 (keyboard), 16.2 (Editor 2.0,
13 October 2026), Feature specs S-20, S-21, S-22; design `docs/design/editor-2.md` sections A, C
and I; Reference R1 (`trunk/branches/grafts`, `canopy/screens/grafts`), R5 (M-EDIT-14 to
M-EDIT-23)

## Purpose

Change any replacement, live or not, without deleting and recreating it, while the game keeps
what was applied until the user applies again.

## Behaviour

- **Two versions per row.** Every row has a saved version (what the user last saved) and, once it
  has been applied, an applied version (what the game gets now). The table and the editor show
  the saved version; the game, Verdra's next start and a finished link download use the applied
  version. Review & apply (S-27) makes saved the new applied.
- **Opening a row.** Clicking a row, or Enter on it, opens the editor drawer (S-22) titled "Edit
  replacement" (M-EDIT-14) with every field filled in: original ID and slot, kind, file or link,
  note. Its status pill (S-25) shows in the drawer's header.
- **Saving** with "Save · apply later" (M-EDIT-15) stores the saved version only. Changing the
  original of a live row is allowed; the review shows it as "stops replacing A, starts replacing
  B" (S-27).
- **Revert to live version** (M-EDIT-16) in the drawer and the row menu sets saved back to
  applied; it is offered only for an Edited or Deleted row.
- **The switch.** Each row has an on/off switch in the table (Space toggles it); switching
  changes the saved version only.
- **Row menu** (right-click or the ⋯ button): Edit, Duplicate, Move to profile…, Revert to live
  version, Delete… (M-EDIT-17). Duplicate puts a copy right below, switched Off, with the note
  "Copy of <note>" (question N7). Move to profile… moves the row with both versions; moving
  changes nothing in the game until applied when it changes a conflict's winner (S-27 rule 2).
- **Multi-selection** (Shift and Ctrl click, Ctrl+A): Switch on, Switch off, Delete…, Move to
  profile…, Apply only these (M-EDIT-18); "Apply only these" opens the review (S-27) with just
  those rows selected.
- **Inline edits**: the switch; the note by double-click (Enter saves, Esc cancels); a file
  dropped onto a row's replacement cell becomes its Local file target (checked as in S-22).
- **Deleting** asks first (M-EDIT-19). A row that was never applied goes at once. An applied row
  stays, struck through, as Deleted · apply to remove (S-25) until applied; Undo or Revert brings
  it back.
- **Undo and redo** (Ctrl+Z; Ctrl+Y and Shift+Ctrl+Z) cover every edit, switch, delete,
  duplicate and move, up to 50 steps (S-20). They change saved versions only, never applied ones.
- **Asset names.** When the original's ID is entered, the name from the type check's answer
  (S-22, the same public asset details) is saved with the row and shown next to its ID
  ("15553230204 · Wall picture"); rows saved before get it when the editor opens. No lookup
  happens just to show the table.

## Rules

1. **What publishes what.** Startup and a finished link download publish the applied versions.
   Review & apply publishes the applied versions with the chosen saved versions promoted. Nothing
   else publishes. (Today startup and a finished download publish what is saved.)
2. **Applied versions on disk.** The applied version is stored in the profile file, so Verdra's
   next start publishes the same set the game had.
3. **Profiles too.** Each profile stores its applied switch, and the setting
   `replacements.applied_order` the applied profile order; the snapshot is compiled from those,
   so a profile switch or reorder also waits for Review & apply (question N5).
4. **Applied copies.** When a Local file or link is applied, Verdra keeps a copy of its source
   bytes in `%LOCALAPPDATA%\Verdra\Applied\<sha256>` (content-addressed: two rows with the same
   file share one copy) and records the SHA-256 in the applied version. The applied version is
   prepared from that copy, so it keeps working if the user's file changes or disappears. A copy
   that no applied version names any more is deleted after the next successful apply. Links
   already have such a copy (`Downloads`, by SHA-256, bark/rain); the applied version names it
   and it isn't deleted while named.
5. **What counts as a change** the game sees: the original (ID and slot), the target kind and
   value, the switch, and for a file the content (its SHA-256). The note and the asset name are
   saved without making a row Edited.
6. **File checks.** For each applied or saved Local file, Verdra keeps the size and modified time
   it last hashed. They are checked when the window becomes active, before the review opens, and
   on the profile-folder watch (S-20); only when they differ is the file hashed again, on a
   worker. A missing file makes the row Problem (M-ROW-14); a changed file makes it Edited with
   M-ROW-15 (question N3). The applied copy keeps working either way.
7. **Limits.** At most 10,000 rows per profile (S-20 rule 3) counts Deleted rows too. Applied
   copies are limited per file by plan 10.7, and in total to 2 GB; past that, the review refuses
   with M-EDIT-23 until rows are deleted and applied.
8. **Keyboard**: Enter opens the editor, Space switches, Delete asks to delete, Ctrl+Z, Ctrl+Y and
   Shift+Ctrl+Z undo and redo, Ctrl+Enter opens the review, Esc closes the drawer (asking first
   when there are unsaved fields: M-EDIT-20).

## Data model: `verdra.profile` version 2

Each replacement keeps today's fields, which are its saved version, and gains:

- `name` (string, default ""): the original's asset name, for display only.
- `deleted` (bool, default false): deleted after it was applied; removed from the file when the
  deletion is applied.
- `applied` (object or null): the applied version, or null if never applied:
  `{ "original": {"asset_id", "slot"}, "target": {"kind", "value"}, "enabled", "asset_type",
  "sha256" (file and link targets, else null), "at" (UTC time of the apply) }`.
- `view` (object, default {}): reserved for phases B and C (for example the shape chosen in Try
  it on, compare mode, camera); ignored by phase A, kept when saving, at most 4 KB per row.

Each profile gains `applied_enabled` (bool or null: never applied). Unknown keys inside `view`
are kept as they are, so phases B and C add their per-row settings without a new version.

Phase B and C needs that stay outside the profile, by design: previews and their cache
(`%LOCALAPPDATA%\Verdra\Previews`, design H), original thumbnails and Library copies (M3), and
the seen counter (memory). None of them needs a profile change.

## Migration from version 1

- A version 1 file is read as today and turned into version 2 in memory: every replacement's
  saved version stays as it is, and its applied version is set equal to it, because under
  version 1 everything saved was applied at the next start. A file target is hashed and copied
  into `Applied` at that moment; if the file is missing, the row gets no applied copy and shows
  Problem (M-ROW-14), as it would have failed to prepare. A link's applied version names its
  cached copy if there is one. Each profile's `applied_enabled` is its `enabled`, and
  `replacements.applied_order` is `replacements.profile_order`.
- The version 1 file is kept as `<name>.json.v1` next to the new one (plan 9.7), written once,
  never overwritten.
- After migration every row is Live · not seen yet, Off or Problem; nothing is waiting, so the
  first start of the new Verdra changes nothing in the game.
- An older Verdra opening a version 2 file opens it read-only (S-20 rule 4), as for any newer
  file.

## Messages

- M-EDIT-14 (Drawer title) "Edit replacement" (adding stays "Add replacement")
- M-EDIT-15 (Button) "Save · apply later"
- M-EDIT-16 (Button and menu) "Revert to live version"
- M-EDIT-17 (Row menu) "Edit", "Duplicate", "Move to profile…", "Revert to live version",
  "Delete…"
- M-EDIT-18 (Bulk actions) "Switch on", "Switch off", "Delete…", "Move to profile…", "Apply only
  these"
- M-EDIT-19 (Dialog) "Delete this replacement?" / "Delete %n replacements?" Body for applied
  rows: "The game keeps it until you click Review & apply. Undo brings it back." (plural: "…keeps
  them… brings them back."); for rows never applied: "Undo brings it back." Buttons "Delete",
  "Cancel".
- M-EDIT-20 (Dialog) "Discard your changes to this replacement?" Buttons "Discard", "Keep
  editing".
- M-EDIT-21 (Note of a duplicate) "Copy of <note>" ("Copy" when the note is empty)
- M-EDIT-22 (Toast) "Moved %n replacements to <profile>." (plural forms)
- M-EDIT-23 (Review refusal) "Applied copies of your files would use more than 2 GB. Delete
  replacements you don't need, then apply again."

## Acceptance tests

1. A live row edited and saved stays served in its applied version (fake Roblox server); after
   Review & apply the new version is served, shown by the log's served lines (design J1).
2. Switching a live row off and applying makes the fake server's client get the original;
   switching it on again shows Not applied yet (design J2).
3. Startup and a finished link download publish the applied versions, not the saved ones (rule 1:
   fails today).
4. Changing or deleting an applied Local file keeps the applied version served from its copy;
   the row shows Edited with M-ROW-15, or Problem with M-ROW-14.
5. Revert to live version makes saved equal applied and the row Live again.
6. Undo and redo across edit, switch, delete, duplicate and move, 50 steps, never touching an
   applied version.
7. A version 1 profile migrates as described: applied equals saved, copies made, the `.v1` file
   kept, nothing waiting, and the published snapshot equals the one version 1 published.
8. A version 2 file round-trips byte-identically, including unknown keys inside `view`.
9. Applied copies no applied version names are deleted after an apply, and never before.
10. Keyboard only: open, edit, switch, delete with confirmation, undo, redo and open the review.
11. Changing a live row's original makes the review show "stops replacing A, starts replacing
    B" (with S-27 test 2).

## Lives in

`trunk/branches/grafts.py`, `docs/schemas/verdra.profile.schema.json`, `soil/terrain.py` (the
Applied folder), `trunk/sapwood/startup.py`, `canopy/screens/grafts/screen.py`,
`canopy/screens/grafts/editor.py`.

## Refinements from the design

- "Applied" is kept on disk, not only in memory, because Verdra publishes at startup (rule 2).
- The design's "turns Problem when the file changes" is split: missing → Problem, changed →
  Edited (question N3).
- Profile switches and order wait for Review & apply like rows do (question N5).
- `view` is the room phases B and C need inside a row, so they need no version 3.
