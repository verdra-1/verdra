# 0023. Verdra's meshes in Roblox's own layout: FileMesh 7.00 with Verdra's own Draco writer

- **Status:** Accepted
- **Date:** 2026-10-12
- **Plan sections:** 10.7, 12.3, 14 (M2: "a mesh swap … visible in game"), 16.2; specs S-21, S-33

## Context

Verdra served mesh replacements as FileMesh 2.00, never tried in game. On 12 October 2026 the
format capture saved the CDN's answer for a public mesh (498788302,
`docs/platforms/evidence/windows/mip-packs-2026-10-12.txt`); the bytes stay on the session
machine. Byte by byte (the meaning of each field from the public FileMesh and Draco format
descriptions, checked against the capture):

| Bytes | Value in the capture | Meaning |
|---|---|---|
| `version 7.00\n` | | FileMesh version line |
| chunk header | `COREMESH`, u32 2, u32 27127 | 8-byte name, chunk version, data size |
| COREMESH data | u32 27123, then 27123 bytes | Draco length (= size − 4), then the Draco bitstream |
| Draco header | `DRACO`, 2, 2, 1, 0, u16 0 | Draco 2.2; triangular mesh; sequential method; no flags |
| connectivity | varint 1364, varint 831, 1, u16 indices | faces, points; uncompressed indices, 16-bit as points < 65,536 |
| attributes | 1 decoder, 5 attributes | position f32×3 id 0; generic f32×3 id 1 (unit vectors: the normal); texture coordinate f32×2 id 2; generic u8×4 id 3 (all 0: **observed, meaning unknown**); color u8×4 id 4 (all 255) |
| codings | 0, 2, 0, 1, 1 | raw for position and texture coordinate; quantization (11 bits) for the normal; integer coding for ids 3 and 4 |
| chunk header | `LODS`, u32 1, u32 31 | |
| LODS data | u16 4, u8 2, u32 6, offsets 0, 744, 1118, 1286, 1342, 1364 | face offsets of 5 levels of detail (the last = all faces); the type 4 and the 2 high-quality levels: **observed, meaning unknown** |

Decoding the capture's bitstream with DracoPy (Google's Draco library) gave the same counts
and attributes.

## Decision

- `strata/clay` writes every mesh replacement and Remove as FileMesh 7.00 in that layout
  (`write_filemesh7`): the same chunks in the same order, the same Draco header, connectivity
  method, index width rule and attribute list (types, data types, components, ids, order).
- The Draco bitstream is Verdra's own minimal writer, from the public Draco format: every
  attribute uses the raw ("generic") coding. The capture compresses ids 1, 3 and 4; any Draco
  decoder reads both. DracoPy can't be used to write it: it gives the attributes other ids and
  another order (position last, id 6). DracoPy (Apache-2.0, already a dependency, Windows
  wheels for Python 3.14 in the lock) reads 6.00 and 7.00 meshes and is the independent decoder
  in the tests.
- One level of detail: LODS offsets `0, <faces>`, type 4 as captured, 1 high-quality level
  (Verdra's choice: its meshes have one level).
- Normals: an OBJ without `vn` lines gets area-weighted vertex normals. The generic u8×4
  attribute is written as 0 and the color as 255, as captured.
- Remove: one triangle with no area at the origin (valid geometry, nothing drawn), since an
  empty Draco mesh may not decode.
- Limits: at most 1,000,000 triangles and 64 MB (plan 10.7), refused with a plain reason.
- Reading a 7.00 mesh (a Local file) keeps the first level of detail.
- glTF isn't added: plan section 14 lists OBJ import and export only.

## Consequences

- Size: raw attributes make Verdra's meshes larger than Roblox's (the capture re-written:
  37,803 instead of 27,190 bytes before HTTP compression).
- Not verified yet: that the Player draws Verdra's 7.00 mesh; the next real-machine test shows
  it, with `--format-check` reporting what Verdra sent next to the capture.
- The build must carry DracoPy's native module: `tools/check_build.py` now fails a build
  without it (and without texture2ddecoder's), since both are loaded only when needed.
- Third-party licence texts of bundled libraries (DracoPy, Draco) are a 0.1.0 release item.
