# S-24 Apply now

**Status:** Agreed
**Milestone:** M2
**Risk badge:** none
**Plan sections:** 7.1 (header, Apply now), 12.4 (the 10 s budget), 14 (M2: "Preview changes;
Apply now"), Feature specs S-24, S-12 (cache clearing, closing only Verdra's clients),
Reference R1 (`trunk/branches/sprout`, `canopy/crown/header`), R5 (M-APPLY-01, M-APPLY-02,
M-LAUNCH-03)

## Purpose

Make changes visible in game in one click.

## Behaviour

1. Save pending edits.
2. Publish a new rule snapshot (S-21).
3. If routing is off, start it.
4. If Roblox is running, confirm (M-LAUNCH-03), ask it to close, and end it after 5 s.
5. Clear Roblox's asset cache (S-12 cache clearing).
6. Relaunch through Verdra into the same game if Verdra knows it (from the last join),
   otherwise to Roblox's start screen.

Progress shows in a toast, which ends with M-APPLY-01, or M-APPLY-02 when Roblox wasn't running
(then steps 4 to 6 are skipped).

## Rules

1. Only clients launched by Verdra are closed (S-12 rule 4); never other apps or other Roblox
   instances.
2. If routing is off, Apply now starts it first; a refusal (S-12, S-15) stops Apply now with
   that refusal's message, and the snapshot stays published.
3. Canceling M-LAUNCH-03 publishes the snapshot but doesn't restart Roblox, and says M-APPLY-02.
4. Cache clearing deletes only the files recorded in `docs/platforms/<os>.md` (S-12 rule 5).
   Until the cache files are recorded (W-06), the cache isn't cleared and the toast says that
   changes to assets Roblox has already cached appear after Roblox clears them itself.

## Messages

- M-APPLY-01 (Toast) "Applied <n> replacements. Roblox is restarting."
- M-APPLY-02 (Toast) "Applied <n> replacements. They'll appear next time Roblox starts."
- M-APPLY-03 (Toast, new) "Applied <n> replacements. Assets Roblox already saved may change
  only after it refreshes them."
- M-LAUNCH-03 (Dialog, S-12) "Restart Roblox now? Unsaved progress in your game may be lost."

## Acceptance tests

1. The full flow with a fake client completes within the 10 s budget.
2. No process other than the Roblox client Verdra launched is ended.
3. With Roblox not running, the snapshot is published and M-APPLY-02 shows; nothing is closed.
4. Canceling M-LAUNCH-03 publishes the snapshot and closes nothing.
5. The relaunch goes to the last joined game when Verdra knows it, and to the start screen
   otherwise.
6. Until the cache files are recorded (rule 4), Apply now deletes and changes no file in Roblox's
   folder (the W-06 names: the cache database and its journal files, cache folders, local
   storage, logs, settings files, downloads, Studio's version folders) and records no new system
   change; the only changes on disk are routing's own, already in the ledger.

## Lives in

`trunk/branches/sprout.py`, `trunk/branches/grafts.py`, `canopy/crown/header.py`.

## Refinements from the plan

- Tests 3 to 6 are added for the branches of the flow and rule 4.
- Rule 4 and M-APPLY-03 cover the time before W-06 is recorded: the plan's step "clear Roblox's
  asset cache" can't be built before the cache files are known (plan 16.4). Replacements served
  by Asset ID still apply at once, because the batch request is rewritten whether or not the
  client cached the original's content location.
- Until W-06 is recorded, a restart ends with M-APPLY-03 rather than M-APPLY-01 (rule 4);
  M-APPLY-01 is used once the cache is cleared.
- "The last join" is the place ID of the last `gamejoin.roblox.com` join Verdra saw. Reading it
  needs `gamejoin.roblox.com` in the interception set while Replacements are on (plan 10.2:
  "per-game detection"); only the place ID is kept, in memory.
