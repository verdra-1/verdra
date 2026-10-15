# S-25 Row status

**Status:** Agreed (approved by the owner on 14 October 2026)
**Milestone:** M2 follow-up, Editor 2.0 phase A (internal label 0.1.x)
**Risk badge:** Cosmetic
**Plan sections:** 5.6 (tokens), 7.2 (Replacements screen), 12.5 (accessibility), 16.2 (Editor 2.0,
13 October 2026), Feature specs S-20, S-21, S-24; design `docs/design/editor-2.md` sections A, B
and J; Reference R1 (`trunk/branches/grafts`, `roots/symbionts/grafter`,
`canopy/screens/grafts`), R5 (M-ROW-01 to M-ROW-15)

## Purpose

Show at a glance, for every replacement, what the game gets now and what is waiting.

## Behaviour

- **One status per row**, shown three ways: a colored left edge, a pill with a word, and a
  detail line where useful. Color is never the only signal.

  | Status | Edge and pill | Word (message) | When |
  | --- | --- | --- | --- |
  | Draft | dashed neutral outline | Draft (M-ROW-01) | the editor is open on a row that isn't saved |
  | Not applied yet | `warning` | New · not applied (M-ROW-02) | saved, and no applied version, or switched on since it was applied off |
  | Edited | `primary` | Edited · apply to update (M-ROW-03) | applied, and the saved version differs in a way the game sees (S-26 rule 5) |
  | Deleted | `primary`, struck through | Deleted · apply to remove (M-ROW-12) | deleted after it was applied; the game still gets it (question N1) |
  | Live · not seen yet | `success` | Live · not seen yet (M-ROW-04) | applied and on, no served event since Roblox started |
  | Live · seen | `success`, edge twice as thick | Live · seen <n>× (M-ROW-05) | applied and on, and Roblox loaded it <n> times since it started (loads, not packs) |
  | Problem | `danger` | Problem · <reason> (M-ROW-06) | it can't be prepared, or its applied file is missing |
  | Off | `ink-disabled`, row dimmed | Off (M-ROW-07) | switched off and applied off |

- **Precedence**, when more than one applies: Draft, Problem, Deleted, Edited, Not applied yet,
  Off, Live · seen, Live · not seen yet. A row is never shown in two states.
- **Tooltip** on the pill: one sentence (M-ROW-08); for Live · seen it also gives the last load
  time; for Problem the full reason.
- **Details** under the pill when they matter: "Another replacement for this asset wins
  (profile <name>)." (M-ROW-13) for a live row that loses a conflict (S-20 rule 1); "The file
  changed after it was applied." (M-ROW-15) on an Edited row whose saved file is the same path.
- **Waiting banner** above the table when something waits: M-ROW-09 ("<n> changes are waiting.
  They reach the game when you click Review & apply."). A change is a row that is Not applied
  yet, Edited, Deleted, or switched off since it was applied, or a profile switch or order change
  (S-27 rule 2).
- **Button** "Review & apply (<n>)" in the header (M-ROW-10), "Review & apply" when nothing waits
  (then disabled, with M-REVIEW-08 as its tooltip).
- **Filters**: chips with counts, All, Live, Waiting, Problem, Off (M-ROW-11), then one chip per
  asset family present (Images, Meshes, Sounds…). Live counts both Live states; Waiting counts
  Not applied yet, Edited and Deleted. One chip at a time, plus one family chip.
- **The seen counter counts loads, not packs** (owner, 14 October 2026, question N2). The grafter
  sees each batch item it replaces (an Asset ID swap) or answers itself (a file, a link, Remove).
  A picture item names its pack in its representation (fidelity `ff ff ff fc 0N`, N = 1 to 3 for
  packs 0 to 2), whether Verdra swaps its ID or serves its content, so the same rule applies to
  both:
  - a picture item for **pack 0** is a load;
  - a picture item for **pack 1 or 2** is a load only if it is the first item for that original
    since Roblox started (pack 0 wasn't asked for); otherwise it is a further pack of a load;
  - every other replaced item (a mesh, a sound, any non-picture swap) is a load.

  The grafter keeps, per original, only "seen since Roblox started", in memory, and tells trunk
  through a callback like the existing `on_unreadable` (rule 2). Trunk counts loads per original
  and the time of the last one, and resets both when Roblox is started through Verdra or Verdra
  starts. Every replaced item writes one DEBUG log line that says which it is: "Replaced asset
  <id> in a batch: load (<kind>, pack <n>)" or "Replaced asset <id> in a batch: further pack
  (<kind>, pack <n>)" (pack "-" when the item names none), so acceptance test 3 compares the
  count with the load lines.
- **The routing pill** (S-14) stays separate and unchanged.

## Rules

1. Status is computed in `trunk` from: the saved version, the applied version (S-26), the last
   prepare result (`Grafts.warnings`), the applied file checks (S-26 rule 6), and the seen
   count. `canopy` only draws it.
2. The proxy hook does no disk or network work for the counter (S-11): it calls the callback,
   which only queues the event to the Qt thread.
3. Tokens only (plan 5.6): `success` for Live, `primary` for Edited and Deleted, `warning` for Not
   applied yet, `danger` for Problem, `ink-disabled` for Off; light and dark themes from
   `tokens.json`; no color literal anywhere.
4. Every pill has an accessible name equal to its word and detail ("Live, seen 3 times"), and the
   row's accessible description includes it, so a screen reader reads the status (plan 12.5).
5. A status change animates with the `quick` motion token (150 ms); with reduced motion it is at
   most a fade (`motion.reduced`, 150 ms), never a movement.
6. A sound, or any type Verdra can't serve from a file or link yet, saved as a file or link, is
   Problem with M-SOON-01's sentence as its reason, never Not applied yet.

## Messages

- M-ROW-01 "Draft"
- M-ROW-02 "New · not applied"
- M-ROW-03 "Edited · apply to update"
- M-ROW-04 "Live · not seen yet"
- M-ROW-05 "Live · seen <n>×" (plural forms: "Live · seen 1×", "Live · seen <n>×")
- M-ROW-06 "Problem · <reason>" (short reasons: "file missing", "too large", "can't read the
  file", "link failed", "wrong type", "not built yet")
- M-ROW-07 "Off"
- M-ROW-08 (tooltips, one per status)
  - Draft: "This replacement isn't saved yet."
  - Not applied yet: "Saved. It reaches the game when you click Review & apply."
  - Edited: "Changed since it was applied. The game keeps the applied version until you click
    Review & apply."
  - Deleted: "Deleted. The game keeps it until you click Review & apply."
  - Live · not seen yet: "Applied. Roblox hasn't asked for this asset since it started."
  - Live · seen: "Roblox loaded it <n> times since it started (last at <time>; a picture arrives
    in up to 3 parts)." (plural forms; the part in parentheses after the time only for pictures)
  - Problem: "<full reason> The game gets <the applied version | the original>."
  - Off: "Kept in the profile but not used. The game gets the original."
- M-ROW-09 (Banner) "<n> changes are waiting. They reach the game when you click Review & apply."
  (singular: "1 change is waiting. It reaches the game when you click Review & apply.")
- M-ROW-10 (Button) "Review & apply (<n>)", "Review & apply"
- M-ROW-11 (Filter chips) "All", "Live", "Waiting", "Problem", "Off", each with its count; family
  chips use the type names of S-22 ("Images", "Meshes", "Sounds")
- M-ROW-12 "Deleted · apply to remove"
- M-ROW-13 (Detail) "Another replacement for this asset wins (profile <name>)."
- M-ROW-14 (Problem reason) "The file for this replacement is missing: <name>. The game keeps the
  applied version until you apply." (the applied copy, S-26 rule 4)
- M-ROW-15 (Detail) "The file changed after it was applied."

## Acceptance tests

1. Each status is reached from fixture profiles exactly as the transitions in design section B
   and question N1 say, and precedence picks one status when several apply.
2. Editing a live row and saving shows Edited, and the published snapshot still holds the
   applied version (design J1, first half; the second half is S-26 test 1).
3. With the fake Roblox server, the seen count of a row equals the number of "Replaced asset …:
   load" log lines for its original since Roblox was started through Verdra; a picture asked for
   in packs 0, 1 and 2 counts once, packs 1 and 2 alone count once, an Asset ID swap of a picture
   counts like served content, and the count resets when Roblox is started again (design J3).
4. Every status has a distinct word and accessible name; rendering each pill in a grayscale
   screenshot still tells all of them apart by text (design J4).
5. The banner and the button count the same changes as the review dialog lists (S-27 test 1).
6. Filters show only matching rows, and their counts add up.
7. The proxy callback does no disk or network work (a test that fails if the callback touches a
   file or a socket) and costs under 1 µs per event in the S-11 benchmark.
8. (manual) On the owner's PC, a row turns Live · seen after joining a game that uses the asset,
   and the count matches the log (design J3, real machine).

## Lives in

`trunk/branches/grafts.py` (status), `roots/symbionts/grafter.py` and `roots/rules.py` (served
callback), `canopy/screens/grafts/screen.py` (table, banner, filters), `canopy/crown/header.py`
(the button).

## Refinements from the design

- Deleted is an eighth look, not an eighth state (question N1): it uses Edited's color and only
  appears between deleting an applied row and the next apply.
- "Seen" counts loads, as the owner decided (question N2, 14 October 2026). Two refinements of
  the owner's wording: an Asset ID swap of a picture also arrives in up to three pack requests,
  so the pack rule applies to it too (the batch item names its pack either way); and a pack 1 or
  2 asked for minutes after pack 0 (the player walking closer) is a further pack, not a new load,
  so the rule uses "first item for that original since Roblox started" rather than a time
  window. Both refinements were accepted by the owner on 15 October 2026.
- Not settled by evidence yet: whether Roblox asks for pack 0 again without a new load (for
  example after dropping it from memory). The 12 October capture shows the original's three
  packs downloaded twice (17:38 and 17:42), but not whether a second join came between. The final
  M2 test's log (one join per step) shows how often pack 0 is asked for per join; if it is more
  than once, the rule changes before phase A is built, with that evidence.
- The counter resets when Roblox is started through Verdra, the only start Verdra sees for sure;
  a Roblox the user started without Verdra isn't routed (S-12) and can't load replacements.
- Built (pull request c of phase A): `rules.Loads` counts loads in memory (about 0.25 µs per
  item on the session machine); `grafter.item_pack` reads the pack from a batch item's
  representation; sprout resets the counts just before it starts Roblox; `grafts.row_state`
  gives each row's status and `Grafts.waiting` the count for the banner and button. An applied
  row whose file is gone shows M-ROW-14 rather than the plain reason, because it says the game
  keeps the applied version. The interface (pills, banner, filters) comes with pull request d.
  The file check hashes on the thread that asks; pull request d moves it to a worker (S-26
  rule 6).

