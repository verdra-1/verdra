# S-27 Review and apply

**Status:** Agreed (approved by the owner on 14 October 2026)
**Milestone:** M2 follow-up, Editor 2.0 phase A (internal label 0.1.x)
**Risk badge:** Cosmetic
**Plan sections:** 7.1 (header), 7.2 (Replacements screen), 12.4 (the 10 s Apply budget), 12.5
(keyboard), 16.2 (Editor 2.0, 13 October 2026), Feature specs S-23, S-24; design
`docs/design/editor-2.md` sections A, E and J; Reference R1 (`trunk/branches/grafts`,
`canopy/screens/grafts`, `canopy/crown/window`), R5 (M-REVIEW-01 to M-REVIEW-12)

## Purpose

One last look at every change before it reaches the game, and nothing reaches the game that
wasn't in that look.

## Behaviour

- **Opening.** "Review & apply (n)" in the header, Ctrl+Enter, or "Apply only these" (S-26) opens
  the dialog "Review changes before applying" (M-REVIEW-01). It replaces the direct Apply now
  button; Apply now's steps (S-24) run after the dialog's confirm.
- **Summary line** under the title (M-REVIEW-02): how many changes, and whether Roblox restarts.
- **One line per change**, in table order, with before → after:

  | Change | Badge | Detail (M-REVIEW-03) |
  | --- | --- | --- |
  | A row never applied | New | "New: <target>" |
  | An Edited row | Changed | "Edited: <old target> → <new target>"; for a new original "Stops replacing <A>, starts replacing <B>." |
  | A row switched off | Turning off | "Turned off: goes back to the original <type>." |
  | An Off row switched on | Turning on | "Turned on: <target>" |
  | A Deleted row | Deleted | "Deleted: goes back to the original <type>." |
  | A profile switch | Profile on / Profile off | "Profile <name> turning off: <n> replacements go back to the originals." (and on) |
  | A new winner after a reorder or move | Changed | "Asset <id> now comes from profile <name>." |
  | A Problem row with a waiting change | Problem | "<reason> Fix it or turn the row off. It will be skipped." and a "Fix" link that opens the row |
  | A link still downloading | Waiting | "Downloading from <host>. It applies as soon as it's ready." |

- **Thumbnails** (phase A): after-thumbnails for picture files and links, decoded on a worker
  from the same prepared content the proxy will serve (no second conversion), 64 × 64; the
  family icon otherwise and for the original, until phase B brings originals. Warnings stay
  visible on the line: scaled size ("Scaled to 1024 × 576."), and the type mismatch of S-22.
- **Selection.** Each line has a checkbox, all checked; "Apply <n> changes" applies the checked
  ones (M-REVIEW-05). Opened from "Apply only these", only those rows are checked. Unchecked
  changes stay waiting.
- **Restart.** A checkbox "Restart Roblox after applying" (M-REVIEW-04), on by default when a
  Roblox Player Verdra started runs, off and disabled when none runs (the changes reach the next
  start), and disabled with its reason when only a Player Verdra didn't start runs (S-12 rule 4,
  M-CACHE-03).
- **Applying.** Promotes the checked changes' saved versions to applied (S-26), publishes the
  snapshot compiled from the applied versions, then runs S-24's steps: waiting for links
  (M-APPLY-04), moving Roblox's cache (only while no Player or Studio runs, S-24 rule 4), and
  restarting the Player Verdra started when the checkbox is on. The M-LAUNCH-03 question isn't
  asked again: the dialog was the question.
- **After applying**, a toast M-REVIEW-06 with "Undo" (M-REVIEW-07) for as long as the toast
  shows (10 s, or until the next apply). Undo puts the previous applied set back, publishes it,
  and restarts Roblox again if this apply restarted it; saved versions stay, so undone rows show
  Edited or New again (question N6).
- **Back to editing** closes the dialog and changes nothing.

## Rules

1. The list is computed in `trunk` (`pending_changes()`), from saved versus applied versions of
   rows and profiles (S-26); the banner, the button count and the dialog use the same function.
2. A change is listed only if it changes what the game would get: a note or name alone is never
   listed (S-26 rule 5); a profile switch or reorder that changes no winner is applied silently
   with the rest, and says so in one line: "Profile order changed; no asset changes."
3. Apply publishes exactly the snapshot compiled from the applied set after the checked changes
   are promoted, and nothing else: a test compares it with the snapshot the dialog previewed.
4. A Problem row is skipped: its saved version isn't promoted, its applied version (if any) stays
   live, and the summary counts it apart ("1 change will be skipped.").
5. Undo keeps one level: the applied set before the last apply. A second apply replaces it.
6. The 10 s cooldown after a restart (S-24, M-APPLY-07) holds for Apply and for Undo; during it
   the dialog's Apply button is disabled with M-APPLY-07 as its tooltip.
7. Each apply writes one Activity line naming the counts (M-REVIEW-09) and one line per change at
   INFO in the log (M-GRAFT-13 style: a file by its name, a link by its host, never a full link).
8. Keyboard: Tab through lines and checkboxes, Space toggles a checkbox, Enter on "Fix" opens the
   row, Ctrl+Enter applies, Esc goes back to editing.

## Messages

- M-REVIEW-01 (Dialog title) "Review changes before applying"; the list's accessible name "Changes"
- M-REVIEW-02 (Summary) "<n> changes. Roblox needs a restart to load them; unsaved progress in
  your game may be lost." / "<n> changes. They reach the game the next time Roblox starts." /
  with skipped rows "<n> will be skipped." appended (plural forms)
- M-REVIEW-03 (Line details) as in the table above: "New: <target>", "Edited: <old> → <new>",
  "Stops replacing <A>, starts replacing <B>.", "Turned off: goes back to the original <type>.",
  "Turned on: <target>", "Deleted: goes back to the original <type>.", "Profile <name> turning
  off: <n> replacements go back to the originals.", "Profile <name> turning on: <n> replacements
  apply.", "Asset <id> now comes from profile <name>.", "<reason> Fix it or turn the row off. It
  will be skipped.", "Downloading from <host>. It applies as soon as it's ready.", "Profile
  order changed; no asset changes."; badges "New", "Changed", "Turning off", "Turning on",
  "Deleted", "Profile on", "Profile off", "Problem", "Waiting"; link "Fix"
- M-REVIEW-04 (Checkbox) "Restart Roblox after applying"; disabled tooltips "Roblox isn't
  running. The changes reach the game the next time it starts." and M-CACHE-03's sentence
- M-REVIEW-05 (Buttons) "Back to editing", "Apply <n> changes" (plural forms), "Apply" when
  nothing is checked (disabled)
- M-REVIEW-06 (Toast) "<n> changes applied. Roblox is restarting." / "<n> changes applied. They
  reach the game the next time Roblox starts." (plural forms), button "Undo"
- M-REVIEW-07 (Toast) "Put back the replacements applied before." / with a restart: "Put back
  the replacements applied before. Roblox is restarting."
- M-REVIEW-08 (Button tooltip) "Nothing is waiting. Every replacement is already live."
- M-REVIEW-09 (Activity) "Applied <n> changes: %a new, %c changed, %o off, %d deleted." (only the
  non-zero parts)
- M-REVIEW-10 (Line warning) "Scaled to <w> × <h>."
- M-REVIEW-11 (Summary, skipped) "<n> will be skipped." (plural forms)
- M-REVIEW-12 (Toast) "Can't undo now: the replacements changed since." (Undo after the applied
  set changed again)
- M-APPLY-07 reworded: "Verdra is still restarting Roblox. Try again in a moment."
- M-REVIEW-03 (Line detail, added with pull request f3) "Profile <name> deleted: <n> replacements
  go back to the originals." (plural forms; badge "Deleted")
- M-PROF-12 (Name refusal, added with pull request f3) "The profile <name> is deleted, but the
  game keeps it until you apply. Apply its deletion first, then use the name again."

## Acceptance tests

1. For fixture profiles with every kind of change (new, edited, new original, off, on, deleted,
   profile off and on, reorder with and without a new winner, problem, downloading link), the
   dialog lists each change once and nothing else, and the banner and button count the same
   (design J5, first part).
2. Applying publishes exactly the snapshot the dialog computed: the fake proxy serves the new
   versions of checked changes and the old versions of unchecked ones (design J5, second part).
3. Apply only selected leaves unchecked changes waiting, with their rows still in their waiting
   status.
4. Undo after apply restores the previous applied set, published and served; a second apply
   makes the earlier Undo unavailable (design J5, third part).
5. A Problem row is skipped, its applied version stays served, and the summary says so.
6. The restart checkbox follows Roblox's state (Verdra's Player, none, another Player), and no
   process other than Verdra's Player is closed (S-24 test 2).
7. With the dialog confirmed, the whole flow with a fake client meets the 10 s budget of S-24
   test 1, the dialog's own thumbnails excluded (they are made before it opens, on a worker).
8. Keyboard only: open with Ctrl+Enter, uncheck a line, apply, undo.
9. (manual) On the owner's PC, an edited live picture stays the old one in game until Apply,
   then shows the new one after the restart (design J1 with J5).

## Lives in

`trunk/branches/grafts.py` (`pending_changes()`, promotion, undo of the applied set),
`canopy/screens/grafts/review.py` (new), `canopy/crown/header.py`, `canopy/crown/window.py`
(the apply flow of S-24).

## Refinements from the design

- Profile switches, reorders and moves are listed (question N5), so "Apply never changes anything
  not shown in this list" holds for them too.
- The review is also the restart question (M-LAUNCH-03 isn't asked a second time).
- Undo is one level and lasts while its toast shows (question N6).
- Phase A shows after-thumbnails only (question N10); before-thumbnails come with phase B.
- Built (pull request f1 of phase A, trunk only): `pending_changes()` gives the lines with a key
  each (a replacement's ID, `profile:<id>`, or `order` for every line the profile order makes);
  `waiting()` counts them, the order once. `apply(chosen)` promotes only the chosen keys and skips
  Problem rows with their reason (M-GRAFT-13); a profile applied for the first time without the
  order goes where it stands among the applied ones. `undo_apply` puts the applied set before the
  last apply back (one level; a deletion applied away comes back as Deleted). Apply now uses the
  same path until the dialog (f2) replaces it.
- Built (pull request f2 of phase A): the dialog, "Review & apply (n)" in the header, Ctrl+Enter,
  "Apply only these", "Fix", the restart checkbox, the toast with Undo. Found while building it:
  S-24's texts send the user back to apply again after Studio or another Player closed
  (M-CACHE-02, M-CACHE-03, M-LAUNCH-08, M-LAUNCH-18), so that the cache can move. A button
  disabled when nothing waits would leave no way to do that, so the button stays enabled: with
  nothing waiting it applies again without a review (S-24's flow, with M-LAUNCH-03), and M-REVIEW-08
  is its tooltip. Those texts now say "click Review & apply". Undo's toast lasts 10 s counted from
  the end of the restart cooldown (rule 6), so an apply that restarted Roblox can be undone too.
  S-01's "Apply now" in the header and Ctrl+Enter now mean Review & apply; the tray's unbuilt
  "Apply now" item keeps its plan name until the tray is built.
- Built (pull request f3 of phase A): deleting a profile that was applied marks it deleted
  (`deleted` in the profile file, schema version 2): it leaves the list and the header, the game
  keeps its applied replacements, and the review lists "Profile <name> deleted" until its deletion
  is applied; Undo (M-PROF-09) takes the mark back. A profile never applied goes at once. While
  the deletion waits its name stays taken, because the file is named after it (M-PROF-12).
