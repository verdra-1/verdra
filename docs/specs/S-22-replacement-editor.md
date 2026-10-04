# S-22 Replacement editor

**Status:** Agreed
**Milestone:** M2
**Risk badge:** Cosmetic
**Plan sections:** 4.3 (wording), 7.2 (Replacements screen, editor drawer), 10.7 (HTTPS only, the
hosts a profile downloads from), 12.5 (keyboard access), 14 (M2: "Replacements screen with
editor drawer, validation, previews"), Feature specs S-22, Reference R1
(`canopy/screens/grafts/editor`, `canopy/leaves/fields`, `canopy/leaves/drawer`), R5 (M-EDIT-01
to M-EDIT-04)

## Purpose

Add and edit a replacement without knowing file formats.

## Behaviour

- **Drawer.** "Add replacement" and editing a row open the editor drawer (plan 7.2) on the
  Replacements screen.
- **Original.** Entered by asset ID, or picked from the Library with "Use as original" (M3).
- **Target.** A segmented control: Asset ID · Local file · URL · Remove; a slot picker appears
  for TexturePack originals.
- **Live validation.**
  - Asset ID: resolves on Roblox through `bark/pollinator`, debounced 400 ms, and has a type
    compatible with the original's (M-EDIT-01, M-EDIT-02).
  - Local file: exists and has a supported format for the original's type (M-EDIT-04).
  - URL: HTTPS only (M-EDIT-03); its host is shown under the field.
- **Previews.** Before and after, from the Library or fetched on demand.
- **Drag and drop.** Dropping a file on the drawer fills Local file. A file inside the profile's
  folder is stored as a relative `./` path; any other file is stored as an absolute path.

## Rules

1. Save is disabled until validation passes, and its tooltip gives the reason.
2. Validation never blocks the UI thread: lookups run as background jobs (S-04) and a newer
   input cancels an older lookup.
3. When Roblox can't be reached, an Asset ID target is accepted with a warning that it couldn't
   be checked, rather than blocking offline editing.

## Messages

- M-EDIT-01 (inline) "No asset with ID <id> was found."
- M-EDIT-02 (inline) "A <type> can't replace a <type>."
- M-EDIT-03 (inline) "Only HTTPS links are allowed."
- M-EDIT-04 (inline) "This file type isn't supported for <type>. Use PNG, JPEG, KTX2, OBJ, MESH,
  OGG or MP3 as fits."
- M-EDIT-05 (inline, new) "Roblox couldn't be reached to check this ID. You can save it anyway."
- M-EDIT-06 (Save tooltip, new) "Enter the asset ID to replace and the asset ID to use instead."
- M-EDIT-07 (Save tooltip, new) "An asset can't replace itself. Enter a different asset ID."

## Acceptance tests

1. Each validation rule with valid and invalid inputs (fake Roblox lookups).
2. A relative path is stored for files inside the profile folder; an absolute one otherwise.
3. Keyboard-only add and save.
4. Typing quickly sends one lookup per pause of 400 ms, and a slow answer to an old input never
   overrides a newer one.
5. With Roblox unreachable, an Asset ID target can be saved and shows M-EDIT-05.

## Lives in

`canopy/screens/grafts/editor.py`, `canopy/leaves/fields.py`, `canopy/leaves/drawer.py`,
`trunk/branches/grafts.py` (validation), `bark/pollinator.py` (lookups).

## Refinements from the plan

- Rule 3 and M-EDIT-05 settle offline editing, which the plan doesn't cover: a profile made on
  a train shouldn't be blocked by a lookup.
- Tests 4 and 5 are added for rules 2 and 3.
- "Use as original" needs the Library (M3); until then the original is entered by ID.
- Built in steps: the first build edits Asset ID targets and checks them locally (M-EDIT-06,
  M-EDIT-07); Local file, URL and Remove stay disabled with M-SOON-01 until the codecs land, and
  the Roblox lookup (M-EDIT-01, M-EDIT-02, M-EDIT-05) comes with `bark/pollinator`. The drawer
  sits beside the table on the Replacements screen.
