# M2 notes

Decisions and open points while M2 (Graft: replacements) is built.

## Deviation: Apply now doesn't clear Roblox's cache yet

**Spec:** S-24 behavior step 5 says Apply now clears Roblox's asset cache.

**Built:** Apply now deletes and changes nothing in Roblox's folders (S-24 rule 4, test 6). It
publishes the replacements, starts routing if needed, and restarts only the Roblox Verdra
launched.

**Why:** plan 16.4 forbids code that depends on an unconfirmed fact, and which files are cache
(fact W-06) isn't settled by a folder listing. The maintainer's Stage 1 report lists, in
`%LOCALAPPDATA%\Roblox`, `rbx-storage.db` with its `-shm` and `-wal` files, `rbx-storage`
folders, `LocalStorage`, `logs`, settings files and more. A listing can't show which of these
hold only re-downloadable assets, whether Roblox Studio writes to the same ones, or whether the
database can be removed while its journal files exist. Deleting the wrong file could lose a
user's settings or local data, and a deletion can't be undone by Reset everything.

**What's needed to build it safely:**

1. Evidence of which files the Player uses as its asset cache: the first-texture-swap test log
   (below), and one read-only listing of names, sizes and modification times of
   `%LOCALAPPDATA%\Roblox` before and after a Player session and before and after a Studio
   session (names only, never contents).
2. A design the maintainer approves before any deletion is written: exactly which files, Player
   only, never Studio's, `LocalStorage`, `logs` or settings files; only while no Roblox process
   runs; each deletion written to the ledger first (a `cache_cleared` entry naming the files,
   sizes and hashes; its undo is "nothing to restore", reported as such, because a cache is
   re-downloaded).
3. Tests on a fixture folder with every W-06 name, including files with similar names, proving
   only the approved files go (S-12 test 4, carried to M2).

Until then the restart toast is M-APPLY-03 ("Assets Roblox already saved may change only after it
refreshes them").

## What the cache means for the first texture swap

The swap (Asset ID kind) works by rewriting the Player's asset batch request
(`POST assetdelivery.roblox.com/v1/assets/batch`). If the Player doesn't ask for the original
asset at all, because it already has what it needs, Verdra never sees the request and the
picture can't change, even though Verdra works.

**Evidence from the Stage 2 log** (2026-10-04, the same place joined twice in one Player
session pair; counts only):

| | First join | Second join |
|---|---|---|
| Batch requests to `/v1/assets/batch` | 97 | 107 |
| Asset files downloaded from `fts.rbxcdn.com` | 173 | 189 |
| Files downloaded in both joins | 0 | |

So on the second join of the same place the Player still sent about as many batch requests, but
downloaded none of the files it had downloaded the first time. That points to: the Player keeps
downloaded **files**, and still **asks** for the assets each time. If that holds, an Asset ID swap
is seen even when the original's file is cached, because the request for the original is
rewritten to the replacement, and the replacement's file is new.

**What this doesn't prove:** the log has no request bodies, so it can't show whether every asset
was asked for again, or only the ones not cached. Whether Studio and the Player share the cache
in `%LOCALAPPDATA%\Roblox` is also unknown. In the test, Studio shows the original picture
before the Player does, so a shared cache is a possible reason for a failed swap.

**How the test log tells them apart:** with detailed logging, Verdra writes
`Asset batch: <n> of <m> items replaced` whenever a batch held the original. If the original
picture shows and that line is missing while `POST assetdelivery.roblox.com /v1/assets/batch`
lines are present, the Player didn't ask for the original: cache (or an ID mismatch, such as a
decal ID instead of the image ID). If the line is there and the original picture still shows,
the problem is after the request.

The safe cache-clearing design will be proposed from that log, and nothing in Roblox's folders
will be deleted until the maintainer approves it.
