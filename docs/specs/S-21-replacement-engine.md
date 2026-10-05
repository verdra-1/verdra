# S-21 Replacement engine

**Status:** Agreed
**Milestone:** M2
**Risk badge:** Cosmetic
**Plan sections:** 8.3 (proxy thread), 10.1, 10.2 (assetdelivery and the CDN hosts, needed by
Replacements), 10.7 (untrusted input, size limits), 14 (M2: "symbionts/grafter (ID swap, remove,
local file, URL, slots); rule snapshots"), 16.2 (protected endpoints), Feature specs S-21, S-33
(the ochre and clay codecs it uses), Reference R1 (`roots/symbionts/grafter`,
`trunk/branches/grafts`, `strata/ochre`, `strata/clay`), R5 (M-GRAFT-01, M-GRAFT-02)

## Purpose

Make Roblox receive the replacement instead of the original asset.

## Behaviour

- **Rule snapshot.** `trunk/branches/grafts` compiles the enabled replacements of the enabled
  profiles, in order (S-20 rule 1), into one immutable snapshot (`roots/rules`): for each
  original (asset ID and slot), the winning target, ready to use. Publishing a snapshot swaps it
  in atomically; requests already in flight finish with the one they started with.
- **Interception set.** While a snapshot has any replacement, the intercepted hosts are
  `assetdelivery.roblox.com` and, when a replacement serves content (file, URL, remove, slot),
  the asset CDN host `fts.rbxcdn.com` (plan 16.2). With no replacement, nothing is decrypted
  for Replacements.
- **Asset ID.** In the asset batch request (`POST /v1/assets/batch`), the original ID of each
  item is swapped for the target ID; every other field of that item is kept. The response is
  mapped back by the item's request ID, so the client receives it for the item it asked for, with
  the original ID wherever the response names one.
- **Remove.** The client receives a blank asset of the right type: a transparent image, an empty
  mesh, silent audio or an empty animation, generated at build time into `assets/`.
- **Local file or URL.** The batch request is left unchanged. The response tells Verdra where
  the original's content lives; when the client then downloads that location, Verdra serves the
  replacement instead, converted to the format and representation the client asked for (KTX2
  for textures, the matching FileMesh version for meshes). URL targets are downloaded (bark/rain)
  and converted ahead of time, when the snapshot is built; if one isn't ready, the original
  passes through and the replacement shows a warning (M-GRAFT-01).
- **TexturePack slots.** A replacement with a slot changes only that map (color, normal,
  metalness, roughness); a combined metalness and roughness map is recomposed from its parts.

## Rules

1. Converted outputs are cached by the SHA-256 of the input and the target format.
2. No disk or network work happens inside the proxy hook (S-11): everything a request needs is
   in the snapshot, prepared by a background job.
3. Unsupported combinations (an image replacing a mesh) are refused in the editor (S-22) and
   left out of the snapshot; they are never sent.
4. Anything the grafter doesn't recognize (a batch body that isn't the expected JSON, an item
   without an asset ID, a response it can't map back) passes through byte-identical, and is
   noted once per session at Debug level.
5. No replacement can touch a protected endpoint (plan 16.2): every rule goes through
   `rules.refuse_protected`, and the proxy never calls a symbiont for one (S-11 rule 6).
6. A replacement's file is read only from the place the profile names; a missing file shows
   M-GRAFT-02 on that replacement and the original passes through.

## Messages

- M-GRAFT-01 (Toast) "<n> replacements couldn't be prepared. See the warnings in Replacements."
- M-GRAFT-02 (inline warning) "The file for this replacement is missing: <path>."

## Acceptance tests

1. Each target kind, against recorded batch and CDN fixtures, produces the expected
   client-visible response: the swapped item comes back under the original's request ID and
   asset ID, and every other item and field is unchanged.
2. A slot replacement changes only its map.
3. A missing URL target passes the original through and flags the replacement.
4. Mesh conversion output parses with the FileMesh reader for each supported version.
5. (manual) Each kind is visible in game on each platform.
6. A batch body the grafter doesn't recognize, and a response it can't map back, pass through
   byte-identical.
7. The proxy hook does no disk or network access (both are blocked during the test and every
   kind still works).
8. A snapshot published while a batch is in flight doesn't change that batch.
9. With no replacement, routing decrypts nothing for Replacements; with only Asset ID
   replacements it decrypts `assetdelivery.roblox.com` alone; a snapshot published while
   routing applies from the next connection.

## Lives in

`roots/symbionts/grafter.py`, `roots/rules.py`, `trunk/branches/grafts.py`, `strata/ochre/`,
`strata/clay/`, `assets/` (blank assets).

## Refinements from the plan

- Tests 6 to 9 are added for rules 2 and 4, the snapshot swap and the interception set.
- **Facts.** The asset batch request and response shape (an array of items with an asset ID and
  a request ID; the response naming each item's content location) and the CDN host that serves
  asset content (`fts.rbxcdn.com`, seen in the Stage 2 capture) are recorded as fact V1 in
  `docs/platforms/`. Until the M2 real-machine test confirms V1, the fixtures are hand-written
  from public descriptions, and rule 4 makes any difference a pass-through rather than a broken
  game.
- The interception set is the smallest that the snapshot needs (plan 10.1: "Only Roblox hosts
  that an active feature needs are decrypted").
- The first build step is the Asset ID kind, which needs no codec; the other kinds follow with
  `strata/ochre` and `strata/clay`.
- **Until the grafter serves content**, Local file, URL and Remove replacements are left out of
  the snapshot with M-SOON-01 (`grafts.SERVED`), so the interception set stays
  `assetdelivery.roblox.com` and real traffic is unchanged while the first real-machine test of
  Asset ID swaps runs (maintainer, 2026-10-04: "Keep the grafter's real-traffic behaviour as it
  is until my test result is in").
- **After the first swap test (2026-10-05).** The Asset ID kind also covers single-asset
  requests: `GET /v1/asset/?id=…` and `/v2/asset/?id=…` (seen in the test's log) and
  `/v1/assetId/<id>` and `/v2/assetId/<id>` (from the service's public API description) ask for
  the target ID, with every other part of the address kept. Every batch is logged at Debug level
  whatever the outcome (how many items were replaced, the asset IDs asked for, the items' field
  names, and why a batch was passed on unchanged), and each response's mapping likewise; asset
  IDs are public, and no other value is logged.
