# The store format

Everything observed so far, transcribed from decision record 0028 ("A, step 1: the result" and
"A, step 3, scoped only"). Read-only observations on the owner's PC, from a copy of the store;
none of the files is committed.

## What the inspection of 22 October 2026 saw

One plain join with nothing decrypted: Apply now moved the store at 21:56:33, Roblox started at
21:57:09, 167 s in all. The owner then inspected a copy with `tools/inspect_store.py`.

- **The database, `rbx-storage.db`:** one table, `files`, with 212 rows, keyed by a 16-byte `id`.
  - The other columns are `content`, `size`, `hits`, `atime`, `category`, `score` and `ttl`.
  - `content` holds the entry inline on 141 rows (blobs of 312, 786 or 787 bytes), and is NULL
    on 71.
  - After a join on 23 October SQLite's own statistics table, `sqlite_stat1`, sat beside `files`.
- **The folder, `rbx-storage`:** 71 files, 8.3 MB in all, from 9,786 to 859,481 bytes each.
  - They sit one level deep, in 2-hex folders.
  - Each is named by its 16-byte id in hex; 71 of the 212 ids name a file.
- **The bytes:**
  - No file starts with a known format (all 71 "unknown"), so Roblox puts a header of its own in
    front of what it stores.
  - That header is unknown.
  - No file's name is the MD5, SHA-1 or SHA-256 of its bytes.

## The payload behind the header

- On 11 October the CDN sent pictures as KTX2 with zstd (decision record 0022), a format Verdra
  already writes.
- The store-swap tool found pictures by reading the KTX2 keys Roblox stores inside each entry,
  behind its header and through zstd.
  - `RobloxOriginalWidth/Height` give a picture's original size.
  - One picture's three mip packs share every key except `packIndex`.

## How the header gets learned

Compare, read-only, one stored entry with the same asset's raw CDN download: a `--format-capture`
body, which stays on the owner's PC. Verdra's encoder already writes the KTX2 behind the header
(decision record 0022). `strata/ochre`'s `ktx2_layout` reads a KTX2 file's layout.

Not yet learned:
- the header's framing;
- the rule that decides inline versus a file;
- exactly how mip packs map to rows and files.
