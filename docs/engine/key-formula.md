# The store key

Transcribed from decision record 0028 ("A, step 1" and "A, step 3, scoped only"). Not yet
answered.

## The problem

Each entry in Roblox's saved-asset store is keyed by a 16-byte `id`. To put a replacement where
the Player looks, Verdra must compute the key of the entry the Player looks up for the original
asset.

## Why the asset ID isn't the answer

The store inspection of 22 October 2026 looked for asset 15553230204 in a copy of the store, and
it appears in no table. The key doesn't hold the asset ID. The inspection also found that no
stored file's name is the MD5, SHA-1 or SHA-256 of its bytes. So the key isn't a hash of the
stored file as a whole.

0028's reading: the key is probably derived from the request or from the content's address.

## Candidate inputs

- **The content address from Roblox's batch answer.** The answer to the Player's batch request
  (`POST assetdelivery.roblox.com/v1/assets/batch`) names each item's location on
  `fts.rbxcdn.com`. The likely candidate for the key is a digest of that address.
- **Roblox's public asset-delivery API.** A request of Verdra's own could give the same address.
  - Whether that API answers without a login isn't known.
  - Verdra never sends a login or a cookie (plan 16.2). If the API needs one, this path is
    closed, and the record says so.

Other inputs 0028 names for testing candidates:

- addresses the owner's own source run records with `--format-capture`;
- either way, Verdra could find the original only after Roblox has saved it once, or learn its
  address first.

## How candidates get tested

A read-only `--check-key` mode, on a **copy** of the store, would compute candidate keys from
candidate strings and test them against the ids present. It never runs on Roblox's own folder,
the way `tools/inspect_store.py` refuses it.
