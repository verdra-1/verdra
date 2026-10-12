# 0024. Pictures are limited by their size, not by how well they compress

- **Status:** Accepted
- **Date:** 2026-10-12
- **Plan sections:** 10.7 (limits), 14 (M2); spec S-33

## Context

On the maintainer's PC (12 October 2026) a 1600 × 900 PNG of 45,306 bytes, mostly flat color
with text, was refused seven times: "it would grow 127-fold when decompressed (the limit is
100)". `strata/ochre` applied plan 10.7's "ratio 100:1" to a picture's decoded pixels
(1600 × 900 × 4 = 5.76 MB). But plan 10.7 sets the ratio "per archive or chunk"; pictures have
their own limit there (16,384 × 16,384 pixels). Flat pictures (logos, interface art, text)
compress over 1,000-fold as a matter of course, so the ratio refused ordinary files, while the
pixel count is what decides the memory a picture costs.

## Decision

- Pictures (PNG, JPEG, DDS through Pillow; KTX2): no compression-ratio limit. Before anything is
  decoded, the header's size is checked:
  - each side at most 16,384 pixels (plan 10.7);
  - at most 67,108,864 pixels in all (8,192 × 8,192, 256 MB as RGBA). This is stricter than the
    side limit alone, which allows 16,384 × 16,384 = 1 GB of pixels: decoding and converting
    one such picture would need several GB on an ordinary 8 GB PC. 64 megapixels still covers an
    8K screenshot (33 MP) and a 48 MP phone photo.
- A KTX2 level must declare exactly the size its pixel size and format imply (and at most 1 GB);
  then it is decompressed with that size as the cap. A flat texture compresses over 1,000-fold
  too.
- Pictures larger than Verdra's texture size (1,024 a side) are scaled down, never refused for
  that (decision record 0022).
- Messages say the size plainly: "the picture is 20,000×20,000 pixels; a side can be at most
  16,384 pixels", or "… (256.0 megapixels); the most Verdra reads is 67.1 megapixels, for
  example 8,192×8,192".
- Pillow's own bomb guard (a warning from about 89 megapixels) is set to the same limit, since
  Verdra checks first.

## Every other place that bounds decompression (checked 12 October 2026)

| Where | Limit | Still right? |
|---|---|---|
| `roots/hyphae`: HTTP request and response bodies (gzip, deflate, zstd) | 100 times the received size, 1 GB, the 64 MB buffer, checked while decoding | Yes: a stream with no declared size; the ratio is plan 10.7's "per chunk" case. A body over it passes on unread, with a warning and Degraded |
| `strata/clay`: 6.00 and 7.00 meshes (Draco) | 64 MB a file and 4,000,000 elements; the declared counts of a sequential Draco mesh are now checked before DracoPy decodes (it would allocate for them first) | Yes, with that addition |
| `strata/ochre`: KTX2 levels | the size implied by the header (above) | Changed by this record |
| `bark/rain`: link downloads | 64 MB, no decompression of its own | Yes |

## Consequences

- The 1600 × 900 picture is read (1,024 × 576 texture, three packs); the next real-machine test
  shows it in game.
- A picture over 64 megapixels is refused with its size; the plan's per-side limit stays as it
  was. Plan 10.7's text names both.
