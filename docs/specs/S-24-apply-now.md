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
4. Cache clearing **moves**, never deletes, only the files recorded as cache in
   `docs/platforms/<os>.md` (W-06), into a new folder under Verdra's
   `Roblox cache backup` folder, records the move in the ledger first (kind
   `roblox_cache_moved`), and happens only while no Roblox Player and no Roblox Studio of this
   user runs. Studio, and a Player Verdra didn't start, are never closed: Apply now says why the
   cache stayed (M-CACHE-02, M-CACHE-03) and still publishes. Reset everything puts the cache
   back, all of it or nothing: if Roblox has made any of the same files since, the backup is
   kept and its folder named (M-CACHE-05).
5. Only the newest cache backup is kept. After a successful move, every older backup is
   deleted on a worker: each one's ledger entry is marked removed first (`deleted`), so Reset
   everything restores the newest backup and never a half-deleted one. A backup whose entry
   isn't done (a move a crash interrupted) is kept, because Reset everything still needs it;
   a folder left by a crash while deleting goes with the next deletion (M-CACHE-07,
   M-CACHE-08). Settings › System changes shows the space the backups use and "Delete backups…",
   which asks first (M-CACHE-09 to M-CACHE-11).

## Messages

- M-APPLY-01 (Toast) "Applied <n> replacements. Roblox is restarting."
- M-APPLY-02 (Toast) "Applied <n> replacements. They'll appear next time Roblox starts."
- M-APPLY-03 (Toast, new) "Applied <n> replacements. Assets Roblox already saved may change
  only after it refreshes them." (A restart in which the cache stayed.)
- M-CACHE-01 (Toast and Activity, new) "Moved Roblox's saved assets (<names>) to <folder>. Reset
  everything puts them back."
- M-CACHE-02 (Toast, new) "Roblox Studio is open, so Verdra didn't move Roblox's saved assets
  aside. Close Studio, then click Apply now again."
- M-CACHE-03 (Toast, new) "A Roblox Player that Verdra didn't start is running, so Verdra didn't
  move Roblox's saved assets aside. Close it, then click Apply now again."
- M-CACHE-04 (Activity, new) "Verdra couldn't move Roblox's saved assets aside (<reason>).
  Nothing was changed."
- M-CACHE-05 (Reset everything, new) "Roblox has made new saved assets since, so Verdra kept the
  old ones in <folder>. You can delete that folder."
- M-CACHE-06 (Job name, new) "Deleting backups of Roblox's saved assets"
- M-CACHE-07 (Activity, new) "Deleted <n> backups of Roblox's saved assets (<size>)."
- M-CACHE-08 (Activity, new) "Verdra couldn't delete every backup of Roblox's saved assets
  (<reason>). It tries again after the next Apply now."
- M-CACHE-09 (Settings, new) "Backups of Roblox's saved assets use <size>."
- M-CACHE-10 (Settings, new) "There are no backups of Roblox's saved assets."
- M-CACHE-11 (Dialog, new) "Delete the backups of Roblox's saved assets?" Button "Delete
  backups". Body "Reset everything can't put them back after this. Roblox downloads what it
  needs again."
- M-LAUNCH-03 (Dialog, S-12) "Restart Roblox now? Unsaved progress in your game may be lost."

## Acceptance tests

1. The full flow with a fake client completes within the 10 s budget.
2. No process other than the Roblox client Verdra launched is ended.
3. With Roblox not running, the snapshot is published and M-APPLY-02 shows; nothing is closed.
4. Canceling M-LAUNCH-03 publishes the snapshot and closes nothing.
5. The relaunch goes to the last joined game when Verdra knows it, and to the start screen
   otherwise.
6. Restarting Roblox (closing the Player Verdra started and starting it again) deletes and
   changes no file in Roblox's folder by itself; the only other changes are routing's own,
   already in the ledger.
7. In a folder holding every W-06 name, only the cache names move: every other file keeps its
   bytes and modified time, and the cache arrives in the backup unchanged. Nothing moves while a
   Player or Studio runs; the interface says why for Studio and for a Player Verdra didn't
   start, and closes neither.
8. Reset everything puts the moved cache back byte- and date-identical and removes the empty
   backup folder; if Roblox made new cache files since, it keeps the whole backup and names it.
9. A crash part-way through the move loses nothing: every file is in place or in the backup, the
   ledger holds the move, and Reset everything puts it back. A failed move puts back at once
   what had moved.
10. Only the newest backup stays after each Apply now, the older one's ledger entry removed;
    Reset everything restores the newest; a crash part-way through deleting an old backup
    leaves Reset everything correct and the leftover goes with the next deletion; a backup
    Reset still needs is never deleted; "Delete backups…" asks first, then deletes them all.

## Lives in

`trunk/branches/sprout.py`, `trunk/branches/grafts.py`, `canopy/crown/header.py`.

## Refinements from the plan

- Tests 3 to 6 are added for the branches of the flow and rule 4.
- **Cache clearing (2026-10-05).** Built as the maintainer approved it in principle (plan 16.2,
  5 October 2026): moving, never deleting; only with Player and Studio closed; only the names
  W-06 records as cache; in the ledger; restorable by Reset everything. The deviation of
  2026-10-04 (nothing cleared) is lifted. The cache names are `Observed` on the maintainer's PC
  and probably cache, not proven (W-06 in `docs/platforms/windows.md`); the re-test guide's
  read-only check comes first. The new ledger kind `roblox_cache_moved` is added to plan 9.4's
  list. Tests 7 to 9 are added for rule 4.
- Before 2026-10-05, rule 4 said the cache wasn't cleared until W-06 was recorded; the first
  swap test (`docs/m2/notes.md`) is why it now moves.
- A restart in which the cache moved ends with M-APPLY-01; one in which it stayed (Studio or
  another Player open) ends with M-APPLY-03.
- "The last join" is the place ID of the last `gamejoin.roblox.com` join Verdra saw. Reading it
  needs `gamejoin.roblox.com` in the interception set while Replacements are on (plan 10.2:
  "per-game detection"); only the place ID is kept, in memory.
- **Only the newest backup (owner, 2026-10-07).** Each Apply now kept every backup (the first
  was about 2.4 GB). Rule 5 and test 10 keep only the newest; the owner asked for it in plan
  16.2 ("Next steps", item 1).
