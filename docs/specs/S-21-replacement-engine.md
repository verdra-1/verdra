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
   without an asset ID, a response it can't map back) passes through byte-identical. While any
   replacement is active, a batch it can't read (an encoding Verdra can't decode, damaged or
   oversized compressed data, a body that isn't a JSON array of objects) is never silent: a
   warning names the reason (M-GRAFT-04) and the routing status turns Degraded (M-GRAFT-03,
   S-14 (d)). Other cases are logged at Debug level.
5. No replacement can touch a protected endpoint (plan 16.2): every rule goes through
   `rules.refuse_protected`, and the proxy never calls a symbiont for one (S-11 rule 6).
6. A replacement's file is read only from the place the profile names; a missing file shows
   M-GRAFT-02 on that replacement and the original passes through.

## Messages

- M-DIAG-03 (Notice and Activity, source runs only) "Format capture is on for <ids>. Their
  replacements are off while it runs, and what Roblox's CDN sends for them is written to
  <folder>. Restart Verdra without --format-capture to turn it off."
- M-DIAG-04 (Activity, source runs only) "Format capture of asset <asset> written to <file>."
- M-DIAG-05 (Activity, source runs only) "Format capture of asset <asset> couldn't be written:
  <reason>."
- M-DIAG-06 (Activity, source runs only) "Control experiment: Roblox's download of asset
  <original> gets asset <donor>'s real bytes from the CDN."
- M-DIAG-07 (Activity, source runs only) "Control experiment: asset <donor> downloads from
  <host>, not from the original's host, so it couldn't be swapped in."
- M-DIAG-08 (Notice and Activity, source runs only) "Control experiment is on: when Roblox
  downloads asset <original>, it gets asset <donor>'s real bytes from the CDN, and replacements
  of <original> are off. Restart Verdra without --control-swap to turn it off."
- M-DIAG-09 (Activity, source runs only) "Format capture: asset <asset> downloads from <host>,
  which Verdra doesn't read, so its format can't be captured."
- M-GRAFT-01 (Toast) "<n> replacements couldn't be prepared. See the warnings in Replacements."
- M-GRAFT-02 (inline warning) "The file for this replacement is missing: <path>."
- M-GRAFT-03 (status reason, new) "Some asset requests couldn't be read, so replacements may not
  apply."
- M-GRAFT-06 (Replacement warning, new) "This file couldn't be used: <reason>."
- M-GRAFT-07 (Activity, new) "Roblox was told to download asset <asset> from <host>, which Verdra
  doesn't serve replacements on, so the original may show."
- M-GRAFT-08 (Activity, new) "Roblox downloaded asset <asset> in a format Verdra can't make yet
  (<format>), so the original shows."
- M-GRAFT-09 (Replacement warning and job name, new) "Downloading this replacement. It applies as
  soon as it's ready." Job: "Downloading a replacement"
- M-GRAFT-10 (Replacement warning and Activity, new) "The replacement from <host> couldn't be
  downloaded: <reason>."
- M-GRAFT-11 (Activity, new) "Downloaded the replacement from <host>. It applies from now on."
- M-GRAFT-12 (Activity, new) "Roblox downloaded asset <asset> as a <kind>, but its replacement is
  another type of asset, so the original shows." (<kind> is "picture" or "mesh".)
- M-GRAFT-05 (Activity, new) "Roblox asked for the replaced asset <asset> by its content hash,
  which Verdra can't replace yet, so the original may show."
- M-GRAFT-04 (Activity, new) "An asset batch <part> couldn't be read (<reason>), so
  replacements may not apply to it." (<part> is "request" or "response".)

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
10. A batch compressed with gzip, deflate or zstd (as the Roblox Player sends most of them)
    asks for the replacement and is sent on uncompressed with a correct length; one without a
    match passes byte for byte; a compressed response is mapped back.
11. Damaged compressed data, an encoding Verdra can't decode, and a body that would decode past
    plan 10.7's limits (100 times its size, or the 64 MB buffer) pass through byte for byte,
    with M-GRAFT-04 and the status Degraded (M-GRAFT-03); decoding stops at the limit.
12. The maintainer's scenario end to end: a profile saved with a real-size original, Apply now,
    the original asked for in a gzip batch, and the client downloads the replacement's content.
13. An item asked for by hash is logged with its hash (hex digits only) and asset type; its
    response is read, and one that names a replaced asset gives M-GRAFT-05 and Degraded.
14. Every representation variant of a replaced asset (with or without `serverPlaceId`,
    `contentRepresentationPriorityList`, `doNotFallbackToBaselineRepresentation`) asks for the
    replacement, and every other field of the item and of its response stays as it was.
15. A Local file picture saved in a profile is served when the Player downloads the original
    from the address a gzip batch response gave: as PNG or KTX2, whichever the CDN sent (also
    when the CDN's answer is compressed), with the file's own pixels; other downloads pass byte
    for byte; a format Verdra can't make and a host it doesn't decrypt pass the original with a
    warning and Degraded.
16. Remove serves a transparent picture as PNG or KTX2; a link is downloaded once (on a worker
    when there is one), left out with M-GRAFT-09 until then, applied without another Apply now
    when ready, and served like a file; a failed download says why (M-GRAFT-10) and Apply now
    tries again; Apply now shows M-GRAFT-01 when a replacement couldn't be prepared. bark/rain
    fetches HTTPS only, refuses a redirect to anything else, stops at its limit and caches by
    the link's SHA-256.
17. A FileMesh or OBJ from the PC is served as FileMesh 2.00 with the same triangles when the
    CDN answers with a FileMesh; Remove serves an empty mesh; a picture for a mesh, or a mesh for
    a picture, lets the original through with M-GRAFT-12 and Degraded.
18. (diagnostic, source runs only) With `--format-capture <asset IDs>`, the CDN's answer for those
    assets reaches Roblox unchanged, even with a replacement set, and a text report holds the
    batch item and its answer (place and request IDs hidden, query values left out), the
    download's status and redacted headers, whether the body is a zstd frame, and the KTX2
    layout inside (vkFormat, size, levels, supercompression, descriptor, keys, level index).
19. (diagnostic, source runs only) With `--control-swap ORIGINAL=DONOR`, the batch also asks for
    the donor (an extra item Roblox never sees in the answer), and Roblox's download of the
    original's address gets the CDN's real answer for the donor, headers included; a donor on
    another host is never swapped in (M-DIAG-07).

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
  is until my test result is in"). Lifted for Local file images on 2026-10-07, after the first
  swap worked (plan 16.2, "Next steps", item 3), and for links and Remove the same day.
- **Local file images (2026-10-07).** When the snapshot is built, the file is read and decoded
  once (strata/ochre, plan 10.7 limits) and written as PNG and as uncompressed RGBA8 KTX2, the
  two formats an image download can come in (`grafts.prepare_content`, rule 2). The batch item is
  asked for unchanged; the response's `location` on `fts.rbxcdn.com` is remembered (its path and
  query, never logged with the query); when the Player downloads it, Verdra sends the prepared
  bytes in the format the CDN answered with, drops headers about the original's bytes
  (Content-MD5, ETag, Last-Modified) and sends a correct length. Never silent: content on a
  host Verdra doesn't decrypt (M-GRAFT-07), a download format Verdra can't make (M-GRAFT-08, for
  example WebP), and a file that can't be used (M-GRAFT-06, left out). Meshes, sounds and slots
  stay M-SOON-01 until their steps. Not verified yet: that the Player accepts an uncompressed
  KTX2 in place of the CDN's own; the owner's test session for files, links and Remove shows it.
- **Links and Remove (2026-10-07).** A link is downloaded by bark/rain (HTTPS only, a redirect
  to anything else refused, 64 MB at most, kept under the SHA-256 of the link in
  `<config>/Downloads`) on a worker the first time Apply now publishes it; until then it is left
  out with M-GRAFT-09 and the original passes. Once downloaded, the snapshot is published again
  and the replacement applies from the next connection without another Apply now (M-GRAFT-11).
  A failed download is left out with M-GRAFT-10 and tried again at the next Apply now. Its
  picture is prepared like a Local file's. Remove serves a fully transparent picture in
  whichever image format the CDN answers with; it is made in memory (1 × 1 pixel), not at build
  time into `assets/`, because it is a handful of bytes. Remove for meshes, sounds and
  animations comes with those steps (a download in another format gives M-GRAFT-08). Apply now
  shows M-GRAFT-01 when any replacement couldn't be prepared.
- **After the first swap test (2026-10-05).** The Asset ID kind also covers single-asset
  requests: `GET /v1/asset/?id=…` and `/v2/asset/?id=…` (seen in the test's log) and
  `/v1/assetId/<id>` and `/v2/assetId/<id>` (from the service's public API description) ask for
  the target ID, with every other part of the address kept. Every batch is logged at Debug level
  whatever the outcome (how many items were replaced, the asset IDs asked for, the items' field
  names, and why a batch was passed on unchanged), and each response's mapping likewise; asset
  IDs are public, and no other value is logged.
- **After the second swap test (2026-10-07).** The Roblox Player sent 14 of its 15 batches
  gzip-compressed, and the grafter passed every compressed one on unread, so the original was
  never swapped (`docs/m2/notes.md`). roots/hyphae now decodes request bodies as it already
  decoded response bodies (gzip, deflate, zstd; Brotli isn't among the plan's dependencies and
  is reported as unreadable), within plan 10.7's limits. A changed batch is sent on uncompressed
  with Content-Encoding removed and a correct Content-Length, rather than compressed again: the
  same Player sent one batch uncompressed in the same session and the server answered it, and
  sending the decoded bytes leaves nothing to get wrong in a second encoder. Each Debug line
  says how the batch was compressed. Rule 4 is tightened and tests 10 to 12 are added at the
  maintainer's request ("never silent again"); the fake Roblox server sends compressed batches
  by default.
- **Items asked for by hash (2026-10-07).** In the log of the first swap that works, two items
  per run named a `hash` instead of an `assetId`. A hash names content, not an asset; the
  client can only ask for content by a hash it already has. For an asset a place names by ID,
  such as the replaced picture, the only places the original's hash could come from are
  Roblox's saved assets (moved aside by Apply now) or a response for the original (never sent:
  every request for it by ID asks for the replacement). So, after Apply now moved the cache,
  the original can come back by hash only if something names its content by hash directly, or
  the cache stayed because Studio or another Player was open (M-CACHE-02, M-CACHE-03). Verdra
  can't tell from a hash which asset it is, and finding out ahead of time would need a lookup
  at Roblox that plan 10.2 doesn't list, so hash items aren't changed. Instead they are logged,
  their response is read, and a response that names a replaced asset is never silent
  (M-GRAFT-05, Degraded); test 13. Test 14 checks every representation variant seen. What the
  two hash items were isn't known yet: the next log names their hash, type and answer.
- **Meshes (2026-10-07).** A Local file or a link that is a FileMesh (versions 1.00 to 5.00)
  or an OBJ is read by strata/clay (plan 10.7 limits) and written as FileMesh 2.00 when the
  snapshot is built; when the Player downloads the original and the CDN answers with a FileMesh,
  Verdra sends that instead. Remove sends an empty mesh (nothing drawn). A replacement of
  another type than the download (a picture for a mesh, or the other way round) lets the
  original through with M-GRAFT-12 and Degraded; the asset type check warns before that, in the
  editor. Bones, skinning and levels of detail beyond the first aren't kept (S-33). Not verified
  yet: that the Player draws a FileMesh 2.00 where the CDN's own was a newer version; the
  owner's mesh test session shows it.
- **Format capture (2026-10-08, after Guide B on the maintainer's PC).** Replaced pictures were
  served but not drawn, and every CDN download asked for `encoding=zstd&version=1`. To see what
  the real answer looks like, `--format-capture <asset IDs>` (with `--save-bodies` to keep the
  bodies too) reports each download of those assets to
  `%LOCALAPPDATA%\Verdra\diagnostics\format-capture-<asset>-<n>.txt` and leaves their
  replacements off, so the real answer reaches Roblox. It runs after the grafter on requests
  (so it sees an Asset ID replacement's target as sent) and before it on responses (so it sees
  the CDN's own answer), and decrypts the batch and CDN hosts even with no replacement. It lives
  in `roots/litmus` with the other source-only diagnostic: frozen builds refuse the flags (exit
  code 2) and leave the module out (decision record 0015). Nothing in a report names the player
  or the place; the reports stay on the PC.
- **Control experiment (2026-10-08).** `--control-swap 15553230204=11473800131` tests H4 (docs/m2/
  notes.md): Roblox asks for the wall's picture at its own content address and gets
  11473800131's real CDN bytes and headers there, nothing made up.
  - **11473800131 shows on the wall:** Roblox doesn't check the bytes against the address, so
    serving at the CDN address works and only Verdra's own file is wrong (H1 to H3). The fix
    makes Verdra's answer match the captured format exactly (framing, KTX2 layout, levels,
    headers).
  - **The wall stays gray (or shows the original):** Roblox rejects bytes that don't match the
    address it asked for (H4), so no content can be served at the original's address. The fix
    changes the route instead: the batch answer for a replaced asset names an address for the
    replacement's own content, which Verdra answers itself.

- **Roblox's texture layout (2026-10-08).** The control experiment ruled out H4 and the format
  capture showed what the CDN sends for a picture (decision record 0022). strata/ochre now
  writes Verdra's pictures that way (`write_roblox_ktx2`): BC1 when fully opaque, else BC3; one
  level, Zstandard supercompression; the CDN's Data Format Descriptor and its 19 keys (real
  averages; observed constants written as seen, meaning unknown; `contentHash` the MD5 of the
  uncompressed level); within 1024 pixels a side, each side rounded down to a multiple of 64
  (of 4 under 64); colors stored as they are, no gamma either way. Remove is the smallest fully
  transparent BC3 texture. The block encoder is Verdra's own (numpy, no new dependency).
  The grafter sends it the way the CDN sent the original: with Content-Encoding: zstd when
  the CDN's answer had it (roots/hyphae compresses a changed body when a symbiont sets
  `Response.coding`), with the CDN's Content-Type and a correct Content-Length.
- **Capture fixes (2026-10-08).** The first captures were all numbered "-1": the number
  restarted with each batch, so later downloads overwrote the report. Reports are now numbered
  per asset across batches and runs, and an existing file is never overwritten. Header values
  that name the play session, a request trace, the place or the universe
  (`Roblox-Play-Session-Id`, `traceparent`, `Roblox-Place-Id`, CDN request IDs such as
  `X-Amz-Cf-Id` and `Akamai-GRN`) are shown as "(hidden)". A FileMesh body is described by its
  version and header, and a download address on a host Verdra doesn't read gives M-DIAG-09
  instead of no report.
