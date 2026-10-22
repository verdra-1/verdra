# M2 exit gate

Plan section 14, M2 Graft: replacements. The exit gate reads: "a texture swap and a mesh swap are
visible in game on Windows; 0.1.0 tagged for you and invited testers." On 13 October 2026 the
owner decided there is no public release before 1.0.0 (plan 16.2, decision record 0026): "0.1.0"
is the internal label for "M2 complete", with no tag and no outside testers. This page gives the
evidence for each part and says plainly what is not verified.

## Result

| Exit gate item | State | Evidence |
|---|---|---|
| A texture swap is visible in game on Windows | **Met** (11 and 12 October) | Below, "Texture swap" |
| A mesh swap is visible in game on Windows | **Met** (12 October) | Below, "Mesh swap" |
| 0.1.0 (internal milestone label, no tag; decision record 0026) | **Open**: steps (e), (e2), (e3) and (f) passed on 15 October; step (g) failed from 15 October on: since then Roblox refuses Verdra's certificate on both asset servers (pass-through control, 22 October); M2 needs a new way to apply replacements (decision record 0028, option A, pending the owner's approval) | Below, "Final M2 test, 15 October 2026" and "Step (g) repeated" |

M2 is complete (internal milestone 0.1.0) when the final M2 test passes: a large, a tiny and a
one-color picture in game, the mesh report, and the release dry-run ZIP started on the owner's
PC.

## Final M2 test, 15 October 2026

On the owner's PC, run from source for (e) to (f) and with the release dry-run ZIP of run
38469127840 for (g). Checked against the owner's results (format-check reports 29 to 37 and
the report for asset 498788302, screenshots, `verdra.log`); none of those files is committed.

| Step | Result | What the reports show |
|---|---|---|
| (e) a large picture (1600 × 900) | **Passed**: visible, corners where they belong, not mirrored | Packs 64 × 36, 512 × 288 and 1024 × 576; `RobloxOriginalWidth/Height` 1600 × 900, transcoded 1024 × 576 |
| (e2) a tiny picture (32 × 32) | **Passed**: visible; the quarters look slightly soft up close | Packs 4 × 4, 32 × 32 and 64 × 64 (each side at least 64, decision record 0022); original 32 × 32, transcoded 64 × 64 |
| (e3) a one-color picture (512 × 512) | **Passed**: the color shows near and far | Packs 32 × 32, 256 × 256 and 512 × 512; original and transcoded 512 × 512 |
| (f) the mesh report | **Passed**: the report appears | FileMesh 7.00, 1106 bytes before compression; COREMESH v2 (Draco 2.2, 24 points, 12 faces), LODS v1 |
| (g) the release dry-run ZIP | **Failed**: a grey wall, no picture, no mesh; `verdra.log` has no proxy line between 19:59:13 and 20:05:46 | See below |

**(g), cause and fix.** Diagnosed with evidence, not yet confirmed on the owner's PC:

- On a Windows runner the built app routes, adds its certificate to the Player's trust file,
  passes connections through and completes the TLS handshake for an intercepted host (CI
  smoke test, `tools/smoke_build.py`).
- A Player started by the built app inherited the built app's own folder: PyInstaller's
  bootloader sets the DLL search directory to `_internal`, and its runtime hooks put
  `_internal` on PATH and set QT_PLUGIN_PATH, QML2_IMPORT_PATH and `_PYI_*` variables. A
  source run passes on a clean environment. Fixed: Verdra starts Roblox with the user's own
  environment and no inherited DLL directory, and the smoke test checks the Player's
  environment.
- In (g) the status didn't turn Degraded (a), so Roblox's connections did reach Verdra; but
  no request was ever decrypted. That fits a Player that fails its TLS handshakes with Verdra,
  and the old proxy dropped failed handshakes without a word. Now each is logged (M-PROXY-06)
  and turns the status Degraded (f), as does a launch with replacements active and no
  decrypted request within 60 s (M-STATUS-08, with "Save a support bundle…").
- That the Player's inherited DLL directory is what broke its handshakes is an inference:
  the repeat of step (g) with a fresh dry-run ZIP decides it.

The release dry run now fails unless the ZIP's app passes the smoke test, which serves one
picture replacement through a fake Roblox upstream and checks the log.

## Step (g) repeated, 16 and 21 October 2026

Both with the release dry-run ZIP on the owner's PC; checked against `verdra.log`, the
screenshots and (21 October) two frames of a video. None of those files is committed.

- **16 October** (fresh ZIP with the environment fix): a grey wall again. The log showed 46
  connections passed through, none to assetdelivery, and no proxy line at all for the
  intercepted host: that build logged nothing for a connection that ended without a request.
  The retest-(g) fixes added those lines.
- **21 October** (main d45e08f, release dry run 39320481846): a blank wall and floor panel.
  - Between 18:14:52 and 18:15:16, ten "Intercepting a connection to
    assetdelivery.roblox.com:443" lines, each followed 2 to 9 ms later by "Roblox closed a
    secure connection to assetdelivery.roblox.com before its first request".
  - So: ten handshakes completed, no TLS failure and no warning, and not one request
    (`POST /v1/assets/batch`).
  - Roblox updated itself at 18:15:25, after those ten. The second start, at 18:17:43 (after
    Apply now), is the last line of the log, so nothing was recorded for the updated Player.

**Verified on 21 October:**

- The honest status: at 18:15:46 it turned Degraded with "Roblox is going through Verdra but
  hasn't asked for any pictures, meshes or sounds since it started" (M-STATUS-09), not "isn't
  reaching Verdra".
- Apply while Roblox runs: at 18:17:34, "Saved. Close Roblox, then join again through Verdra to
  see the change." (M-APPLY-08).
- Each "Moved…" line appears once.

**What the whole log shows, 7 to 21 October:**

- Every source run with a game joined had asset requests: 65 to 196 a day, and "Served the
  replacement" 31 times in all on 8, 11, 12 and 15 October. The last request was at 19:51:55 on
  15 October, after a Roblox update at 14:53:59 that day.
- No run of the built app ever had one: 15 October from 20:04, 16 and 21 October. On
  15 October the ZIP started Roblox 12 minutes after that last source request, and Verdra
  noticed no Roblox update in between. Verdra only notices an update while it runs, so one
  between 19:54 and 19:59, while it was closed, can't be ruled out.

**What the log can't say:** which protocols Roblox asked for, or how it closed. Detailed
logging now records both (S-11, "TLS details at Debug"). The next step is a source run on
today's Roblox ([guide](../guides/m2-source-tls-check.md)):

- If it also closes before its first request, Roblox changed: Verdra would have to speak what
  Roblox now wants (most likely HTTP/2) on the connections it decrypts. That is new work in
  M2's core, not a build fix.
- If it works, the built app's TLS differs from a source run's: make them the same, and add a
  smoke test whose client offers HTTP/2 first.

### The source run, 21 October 2026, 22:22 to 22:29

From source (main ee5979b, OpenSSL 3.5.9, Python 3.14.8) on the updated Roblox, with no
Roblox update during the test. Two starts of Roblox (22:24:48 and, after Apply now, 22:27:38).

- **It fails exactly like the ZIP.** 26 connections to assetdelivery between 22:24:53 and
  22:28:40, and every one ends the same way. The handshake completes with TLS 1.3,
  TLS_AES_256_GCM_SHA384 and X25519MLKEM768. Then, 0 to 1 ms later, "closed … before its first
  request (… a plain TCP close)". There were no TLS alerts, no requests and nothing served.
  The wall stayed blank: neither the replacement nor the original.
- **Not HTTP/2.** Roblox offered only `http/1.1` and Verdra chose it, on all 26 connections.
- **Not the build.** The source run has the same TLS server as the built app (the CI smoke
  test, 21 October), and it fails the same way.
- **Confirmed again:** the honest Degraded status at 22:25:48 (M-STATUS-09), and the
  Apply-while-running message at 22:27:36 (M-APPLY-08).
- **The 15 October puzzle, not resolved.** That evening a source run worked at 19:51 and the
  ZIP failed at 20:04. Today's cause fits if Roblox's behavior changed in between, with no
  update Verdra saw. That is possible if the change came while Verdra was closed, or from
  Roblox's servers rather than an update. It isn't proven.

What's left: Roblox accepts Verdra's certificate during the handshake (it is trusted through
the Player's certificate file), then drops the connection without a word. That points to a
check made after the handshake, such as pinning the server's key, which a certificate from
Verdra's own authority can't pass. It isn't proven. The pass-through control
([guide](../guides/m2-pass-through-control.md)) tests it: assetdelivery passed through
untouched, the real server's certificate logged for comparison, and, separately, Verdra's
authority sent along with its certificate.

### The pass-through control, 22 October 2026

Three source runs (main 8012450; logs checked, not committed). Details and times are in
decision record 0028.

- **Run 1, assetdelivery passed through:** Roblox dropped all 77 connections Verdra decrypted
  on fts.rbxcdn.com, the picture server, in the same way (19:56:03 to 19:56:24).
- **Run 2, nothing decrypted:** the real certificates are from public authorities (Sectigo,
  Amazon), RSA 2048, with 3 Certificate Transparency timestamps each. Roblox needed one
  connection to the picture server, with no retries.
- **Run 3, Verdra's authority sent along:** assetdelivery dropped all 30 connections, 29 plain
  closes and one reset.

So both asset servers refuse Verdra's certificate after the handshake, whatever chain it sends.
Decrypting them, the way M2 replaced assets until 15 October, no longer works. The direction is
decision record 0028's option A: put replacements into Roblox's saved assets. It starts with a
read-only look at a copy of the store (guide `docs/guides/m2-store-inspection.md`), and it
writes nothing into Roblox's files until the owner approves.

## Texture swap

All on the owner's PC (Windows 11, Roblox Player 0.742), run from source, with the format check
showing what Verdra sent. Details in [docs/platforms/windows.md](../platforms/windows.md).

| Check | Result | Evidence |
|---|---|---|
| Asset ID → asset ID | Visible (7 October; again 12 October as step (d) of the mesh test) | `first-swap-works-2026-10-07.txt`, `mesh-swap-2026-10-12.txt` |
| Local file: opaque PNG 576 × 512 and 1024 × 1024 (BC1), PNG with transparency (BC3) | Visible, transparency right | `textures-render-2026-10-11.txt` |
| HTTPS link | Visible | `textures-render-2026-10-11.txt` |
| Remove | The decal disappears | `textures-render-2026-10-11.txt` |
| From far away (three packs of mip levels) | Visible, no black areas | `mip-packs-2026-10-12.txt` (reports 11 to 16, videos) |

## Mesh swap

Owner's PC, 12 October 2026, `--format-check 498788302` (a FileMesh 7.00 mesh), anonymised in
`docs/platforms/evidence/windows/mesh-swap-2026-10-12.txt`.

| Check | Result | Evidence |
|---|---|---|
| (a) Local file, OBJ emblem (352 faces) | Visible | Report 1 (FileMesh 7.00, Draco 2.2, 5 attributes, LODS), log line, frame |
| (a2) Local file, textured cube (12 faces) | Visible | Report 2, log line, frame |
| (b) Asset ID → another public mesh | Visible | Frame |
| (c) Remove | Gone | Report 3 (one zero-area triangle), frame |
| (d) Texture ID → ID still works | Visible | Frame |

A replaced mesh is drawn with the part's own texture through the new mesh's UVs. That is
expected: the texture is a separate asset, and Verdra replaces the geometry only. The user guide
([docs/guides/replacements.md](../guides/replacements.md)) says so.

## Found in the mesh test, since fixed

- (e) A 1600 × 900 PNG was refused when saved ("127-fold"): a compression-ratio limit was
  applied to pictures. Fixed by decision record 0024 (pull request 128): limits come from the
  header (16,384 pixels a side, 64 megapixels), there is no ratio limit for pictures, and large
  pictures are scaled down. The owner's file reads as 1600 × 900 and is sent as 1024 × 576 in
  three packs (checked on the session machine). **In-game re-test open** (next test guide,
  step (e)).
- "The format check wrote no mesh report" was not a fault: reports 1 to 4 for 498788302 are in
  the owner's diagnostics folder, written at 20:15, 20:16, 20:19 and 20:21 UTC. Step (b) has no
  report by design, because the request is rewritten to ask for the other asset, so the download
  isn't 498788302's. The next test guide, step (f), confirms the report appears.

## CI evidence

Every gate runs on `windows-latest` for every pull request and for `main` (decision records
0012, 0018). `main` after pull request 128:
[CI run 38307284282](https://github.com/verdra-1/verdra/actions/runs/38307284282) and
[Windows test build 38307284592](https://github.com/verdra-1/verdra/actions/runs/38307284592).
The texture and mesh writers are tested against the structures captured from Roblox's CDN
(decision records 0022 and 0023): DracoPy decodes every mesh Verdra writes, and the KTX2 packs
are read back level by level.

## Built for M2 (plan section 14)

| Plan item | State |
|---|---|
| Specs S-20 to S-24 merged | Done |
| strata/ochre: KTX2 reader and writer, block decoding (texture2ddecoder), PNG conversion | Done; the writer makes Roblox's layout (decision record 0022) |
| strata/ochre: TexturePack slots | **Not built**: a profile can name a TexturePack map (`roots/rules.py`), but preparing such a replacement reports M-SOON-01 (`trunk/branches/grafts.py`); a replacement applies to the whole asset |
| strata/clay: FileMesh read and write for every documented version; OBJ import and export | Read 1.00 to 7.00; write 2.00 and 7.00 (7.00 is what Verdra serves); OBJ both ways |
| Profile store and schema; grafter (ID swap, remove, local file, URL, slots); rule snapshots | Done, except slots (above) |
| Replacements screen, editor drawer, validation, previews; Preview changes; Apply now | Done |

## Not verified

Said plainly, so nobody reads more into the result than was tested:

- **Pictures smaller than 64 pixels a side.** Verdra makes each side at least 64 (its own
  choice, decision record 0022); a 32 × 32 picture shows in game (step (e2)), slightly soft up
  close. What Roblox does with a smaller picture of its own was never captured.
- **One-color pictures.** `constantColor` is written as "0" (the client reads the texture); a
  one-color picture shows in game (step (e3)), but what Roblox writes for one is unknown.
- **glTF meshes.** Not planned: Verdra takes Roblox mesh files and OBJ only.
- **Draco compression in Verdra's output.** Verdra writes Draco's raw (uncompressed) codings, so
  its meshes are larger than Roblox's own; Roblox drew them, but compressed codings are not used.
- **Levels of detail.** Verdra sends one level of detail; Roblox's own meshes have up to five. A
  replaced mesh far away is drawn with its full detail; that was not looked at from a distance.
- **(b) geometry.** The asset-ID mesh swap showed a different shape; that it is exactly the other
  asset's geometry was not checked independently.
- **The release dry-run ZIP.** Started on the owner's PC on 15, 16 and 21 October and failed
  each time (step (g) above), and so did a source run on 21 October: the cause is on Roblox's
  side, not the build. The pass-through control (22 October) showed both asset servers refuse
  Verdra's certificate after the handshake. Pinning fits best; what exactly Roblox checks isn't
  observed.
- **The Qt source addresses** in the third-party notices (download.qt.io) weren't reachable from
  the session that wrote them. Needed: someone opens them once and checks they list the bundled
  Qt and Qt for Python version, or the notices name another address that does. It blocks nothing
  before 1.0 (nothing is published); whether 1.0 should carry its own copy of those sources is
  for the lawyer review of plan section 3 (M8).
- **TexturePack slots** (one map of a material, such as its normal map) are not built.
- **Sounds and other types from a file or link** are not built (M-SOON-01); a file or link
  replacement works for pictures and meshes. Asset ID swaps were tried with pictures and meshes
  only.
- **Roblox Studio** is not supported; only the Roblox Player was tested.
- **Content-hash requests.** If Roblox asks for an asset by its content hash, Verdra can't
  replace it yet; Activity says so and the status turns Degraded.
