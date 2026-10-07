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
- M-EDIT-02 (inline) "A <target> can't replace a <original>."
- M-EDIT-03 (inline) "Only HTTPS links are allowed."
- M-EDIT-04 (inline) "This file type isn't supported for <type>. Use PNG, JPEG, KTX2, OBJ, MESH,
  OGG or MP3 as fits."
- M-EDIT-05 (inline, new) "Roblox couldn't be reached to check this ID. You can save it anyway."
- M-EDIT-06 (Save tooltip, new) "Enter the asset ID to replace and the asset ID to use instead."
- M-EDIT-07 (Save tooltip, new) "An asset can't replace itself. Enter a different asset ID."
- M-EDIT-08 (inline, new) "This file type isn't supported. Use PNG, JPEG, KTX2, OBJ, MESH, OGG
  or MP3."
- M-EDIT-09 (inline, new) "This file is too big. The limit is <size> MB."
- M-EDIT-10 (Save tooltip, new) "Enter the asset ID to replace."
- M-EDIT-11 (under the URL field, new) "Downloads from <host>."
- M-EDIT-12 (Save tooltip, new) "Choose a file to use instead."

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
- Second step (2026-10-04): Local file, URL and Remove are enabled. A Local file is checked by
  its first bytes (PNG, JPEG, KTX2, DDS, FileMesh, OGG, MP3; OBJ, which has no signature, by its
  `.obj` suffix and first line) and by the plan 10.7 size limits (mesh 64 MB, audio 50 MB, and
  64 MB for an image file, whose pixels strata/ochre limits). Until `bark/pollinator` tells the
  original's type, the file's family (Image, Mesh, Audio) is saved as the asset type and an
  unsupported file shows M-EDIT-08, which names no type; M-EDIT-04 and M-EDIT-02 replace it with
  the lookup. Choose file… opens a file dialog. M-EDIT-09 to M-EDIT-12 cover the size limit, the
  original's field, the link's host and an empty file field. These targets are saved but not
  served yet: they stay out of the snapshot with M-SOON-01 shown in the table's Note column,
  so routing decrypts no more than for Asset ID swaps until the grafter serves content (S-21).
- Keyboard (test 3): Ctrl/Cmd+N opens the drawer from any screen (making a first profile if
  there is none); Ctrl/Cmd+Z and Shift+Ctrl/Cmd+Z undo and redo replacement edits while the
  Replacements screen shows (a focused text field keeps its own undo); Ctrl/Cmd+Enter runs
  Apply now (S-01's shortcuts, wired once Replacements exist).
- Built in steps: the first build edits Asset ID targets and checks them locally (M-EDIT-06,
  M-EDIT-07); Local file, URL and Remove stay disabled with M-SOON-01 until the codecs land, and
  the Roblox lookup (M-EDIT-01, M-EDIT-02, M-EDIT-05) comes with `bark/pollinator`. The drawer
  sits beside the table on the Replacements screen.
- Third step (2026-10-07), the type check: `bark/pollinator` asks Roblox's public asset details
  (`economy.roblox.com/v2/assets/<id>/details`, no sign-in, no cookie, a User-Agent naming
  Verdra only) what the original and an Asset ID target are, 400 ms after typing pauses, as a
  background job (M-EDIT-13 names it). Each ID is asked once per drawer and the answer is kept
  under that ID, so a slow answer about an earlier input only ever describes that earlier ID and
  never overrides the newer one (rule 2, test 4): nothing needs canceling. An Asset ID target must
  have the original's type; a file or a link must fit its family (Image, Mesh, Audio), so a
  picture can't replace a sound (M-EDIT-02, whose types are named in plain words: picture,
  sound, mesh, decal, model…). A link's type is known only once it's downloaded, so it is
  checked when the snapshot is built: a replacement whose content doesn't fit the saved type is
  left out with M-EDIT-02 as its reason (S-21 rule 3). Remove fits any picture or mesh. The
  original's type, once Roblox says it, is saved as the replacement's asset type, else the
  file's family; with Roblox unreachable nothing is refused and M-EDIT-05 shows under the field.
  M-EDIT-04 (a file type unsupported for a known type) is folded into M-EDIT-02 for now.
- M-EDIT-13 (job name, new) "Checking an asset ID"
