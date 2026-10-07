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
the problem is after the request. (Corrected after the test below: the line was also missing
when the grafter skipped a batch without saying so, so its absence alone didn't prove that.)

The safe cache-clearing design will be proposed from that log, and nothing in Roblox's folders
will be deleted until the maintainer approves it.

## First texture swap test, first attempt (2026-10-05): not seen

The maintainer replaced one Toolbox picture (the original, its Texture number from Studio) with
another and saw only the original, through several Apply now restarts and joins. Evidence:
`docs/platforms/evidence/windows/first-swap-2026-10-05.txt` (counts and anonymised names only).

**What the log proves**

- The replacement was published ("Applied 1 replacement") and routing was on.
- 64 batch requests (`POST /v1/assets/batch`) and 2 single-asset requests
  (`GET /v1/asset/?id=…`) passed through Verdra, which read them. Nothing else was decrypted.
- The grafter wrote no line at all. Before verdra-1/verdra#87 it logged only when it replaced
  something; it also skipped silently a compressed batch, a batch too large to read, and items
  without a request ID. So the log proves only that no batch was **replaced**, not why.
- The two single-asset requests asked for other assets (videos, by their requested format), so
  they weren't the picture; but that route was not handled at all, so a picture fetched that way
  could never have been swapped (now handled, with tests).
- Neither asset ID appears in any request address. Download addresses on `fts.rbxcdn.com` and
  the other CDN hosts are content hashes, never asset IDs, so no CDN route carries the ID.
- The Player found running at startup (process ID in the log) carried Verdra's proxy address, so
  an earlier Verdra started it; Verdra had just started and hadn't. "Restart Roblox" closes only
  the Players the current run started, so that Player was never closed during the test.

**What the log doesn't prove (and the next log will)**

- Whether any batch held the original: bodies weren't logged. The next log names every asset ID
  asked for and the item field names, one line per batch, and says why a batch was skipped.
- Which cache held the picture. Probable, in order: (1) the Player's own cache, since the run
  before (Save didn't work then) restarted Roblox twice while nothing was replaced, so the Player
  most likely loaded the original itself; (2) the Player kept running from that run, holding the
  picture in memory; (3) the cache Studio shares, where the picture was placed first.
- That the original number was the image the game loads: the guide says to copy the Texture
  property, which is the image Studio resolved from the decal. Verdra's sandbox can't reach
  Roblox's API to check the two numbers' asset types (blocked by its network policy).

**Do Studio and the Player share `%LOCALAPPDATA%\Roblox\rbx-storage*`?**

- Proven (W-06, the maintainer's PC): there is one Roblox folder per user, holding one
  `rbx-storage.db` (with `-shm` and `-wal`, the SQLite write-ahead files) and the folders
  `rbx-storage` and `rbx-storage-sc`, next to both the Player's settings file
  (`GlobalBasicSettings_13.xml`) and Studio's (`GlobalBasicSettings_13_Studio.xml`), and a
  separate `RobloxStudio` folder. No Studio-only storage database appears in the listing.
- Probable, not proven: both apps use that one storage as their download cache. Roblox doesn't
  document its cache, and a listing can't show which program writes which file. The read-only
  check in the re-test guide (sizes and modified times before and after a join) shows whether the
  Player writes to it; whether Studio does would need the same check around a Studio session.

**What changes**

- The grafter logs every batch (verdra-1/verdra#87) and handles the single-asset routes.
- Apply now moves the download cache to a backup folder, only with Player and Studio closed
  (spec S-24, the cache-clearing design approved in principle on 2026-10-05), which also removes
  the "Player kept running" case: Apply now asks for every Player to be closed first.


## Second texture swap test (2026-10-07): not seen; cause found

Same place, pictures and replacement as the first attempt, after verdra-1/verdra#87 and #88.
Evidence: `docs/platforms/evidence/windows/second-swap-2026-10-07.txt` (counts and anonymised
names only).

**What the log proves**

- Apply now moved the four cache items, and the maintainer's listing shows the Player made them
  again during the join (2.47 GB before, 11 MB after), so the old cache wasn't in play.
- 15 batch requests passed through Verdra. 14 were gzip-compressed, and the grafter passed each
  of them on unread ("An asset batch request was compressed (gzip); passed on unchanged"). The
  one uncompressed batch asked for a single other asset. So the original was almost certainly
  in a compressed batch, which the grafter never looked into: **the cause**.
- The fake Roblox server used by the tests only sent uncompressed batches, so no test could see
  it.

**What changes (verdra-1/verdra fix/compressed-asset-batches)**

- roots/hyphae decodes request bodies for the symbionts (gzip, deflate, zstd), within plan
  10.7's limits (100:1 and the 64 MB buffer, checked while decoding). A changed batch goes on
  uncompressed with a correct length; an unchanged one goes on byte for byte.
- A batch that can't be read while a replacement is active is never silent: a warning with the
  reason (M-GRAFT-04) and the status Degraded (M-GRAFT-03).
- Each Debug line names the asset IDs asked for, the ones replaced, and how the batch was
  compressed.
- The fake Roblox server sends compressed batches by default, and a test runs the maintainer's
  scenario end to end (saved profile, Apply now, a gzip batch, the replacement's content).

**The items Apply now leaves in place**

- `rbx-storage.id`: 8 bytes, last changed the day before the test and unchanged by the join, so
  the Player doesn't write it while playing. Eight bytes is the size of one 64-bit number, most
  likely an identifier for the storage, not downloaded content (probable, not proven). Moving it
  isn't needed to clear downloaded assets, and moving it could change that identifier, so it
  stays.
- `rbx-storage-sc`: a folder that held no files before or after the join (its date changed, so
  something opened it). An empty folder holds no saved picture, so moving it isn't needed.
- Not verified: what either is for. Roblox doesn't document them.

## First texture swap works (2026-10-07)

With main after verdra-1/verdra#91 the Player showed the replacement (11473800131) in place of
the original (15553230204). Evidence: `docs/platforms/evidence/windows/first-swap-works-2026-10-07.txt`.

| | What it shows |
|---|---|
| **The log proves** | In each of the two runs with the fixed build, the original was asked for in three batches, all gzip-compressed (in batches of 61, 2 and 1 items, then 61, 1 and 1); each time the grafter asked for the replacement instead, and each response was rewritten by request ID ("1 of 1 replaced items found by request ID"). No grafter warning, so no batch went unread. Apply now moved the cache first. |
| **The log doesn't prove** | What the Player drew: the log ends at the batch response, and the downloads from the CDN host pass through as tunnels. Whether every representation of the picture went through the replacement: two items per run were asked for by hash, not by asset ID (analysed in S-21's refinement for hash items). Anything about Studio, which stayed closed. |
| **The owner saw** | The replacement on the wall, stable from every angle and distance for 65 seconds of video; the original never came back. A light halo along the paint's top edge and slight shimmer at a distance were seen; the owner checks them with the image placed directly in Studio (most likely Roblox's texture filtering and the image's transparent edges). |

The first attempts' causes, in order: the original already in Roblox's cache (now moved aside by
Apply now), then gzip-compressed batches passed on unread (verdra-1/verdra#91).

## Items asked for by hash (2026-10-07)

Two items per run in the log asked for content by `hash` (fields: hash,
contentRepresentationPriorityList, doNotFallbackToBaselineRepresentation, assetType, accept,
requestId); their values weren't logged then.

- **Proven:** every request for the replaced picture by asset ID was replaced (3 per run), in
  every variant seen, and the picture stayed replaced for the whole video.
- **Reasoned, not proven:** a hash names content the client already knows the hash of. Once
  Apply now has moved Roblox's saved assets, the original's hash can only reach the client from
  something that names that content by hash directly; the replaced picture is named by ID.
- **Not known:** what the two hash items are. The log now names each one's hash (hex digits
  only), asset type, and the asset ID its response names; a response naming a replaced asset
  gives a warning (M-GRAFT-05) and the status Degraded.
- **Not done, and why:** turning a hash into an asset ID ahead of time would need a lookup at
  Roblox that plan 10.2 doesn't list. If the next log shows a replaced asset asked for by hash,
  that is a decision for the owner.

## Local file pictures (2026-10-07)

Built and tested against the fake Roblox server (S-21 test 15); the owner's test session for
files, links and Remove is next. What the tests can't show, and that session will: whether the
CDN sends the Player PNG or KTX2 for an in-game picture (the log names the format served:
"Served the replacement for asset … (KTX2, …)"), and whether the Player accepts an uncompressed
KTX2 where the CDN's own was compressed.
