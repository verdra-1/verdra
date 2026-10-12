# M2 exit gate

Plan section 14, M2 Graft: replacements (0.1.0, private preview). The exit gate reads: "a texture
swap and a mesh swap are visible in game on Windows; 0.1.0 tagged for you and invited testers."
This page gives the evidence for each part, as of 12 October 2026, and says plainly what is not
verified.

## Result

| Exit gate item | State | Evidence |
|---|---|---|
| A texture swap is visible in game on Windows | **Met** (11 and 12 October) | Below, "Texture swap" |
| A mesh swap is visible in game on Windows | **Met** (12 October) | Below, "Mesh swap" |
| 0.1.0 tagged for the owner and invited testers | **Open**: waits for the owner's yes to the release notes ([docs/releases/0.1.0.md](../releases/0.1.0.md)) | Decision record 0025 |

M2 is done when 0.1.0 is tagged and the release build's quick test (next test guide, step (g))
passes.

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
  choice, decision record 0022); what Roblox does with a smaller picture of its own was never
  captured, and a small picture was not tried in game.
- **One-color pictures.** `constantColor` is written as "0" (the client reads the texture); a
  one-color picture was not tried in game, and what Roblox writes for one is unknown.
- **glTF meshes.** Not planned: Verdra takes Roblox mesh files and OBJ only.
- **Draco compression in Verdra's output.** Verdra writes Draco's raw (uncompressed) codings, so
  its meshes are larger than Roblox's own; Roblox drew them, but compressed codings are not used.
- **Levels of detail.** Verdra sends one level of detail; Roblox's own meshes have up to five. A
  replaced mesh far away is drawn with its full detail; that was not looked at from a distance.
- **(b) geometry.** The asset-ID mesh swap showed a different shape; that it is exactly the other
  asset's geometry was not checked independently.
- **Large pictures in game.** Decision record 0024's fix is tested in CI and on the owner's file,
  not yet in game (step (e)).
- **The release build.** The ZIP from GitHub Releases has not been started on a real machine
  (step (g)); CI checks it on a Windows runner (Qt modules, legal texts, no diagnostics, one
  start).
- **TexturePack slots** (one map of a material, such as its normal map) are not built.
- **Sounds and other types from a file or link** are not built (M-SOON-01); a file or link
  replacement works for pictures and meshes. Asset ID swaps were tried with pictures and meshes
  only.
- **Roblox Studio** is not supported; only the Roblox Player was tested.
- **Content-hash requests.** If Roblox asks for an asset by its content hash, Verdra can't
  replace it yet; Activity says so and the status turns Degraded.
