# 0022. Verdra's pictures in Roblox's own texture layout, with Verdra's own BC1/BC3 encoder

- **Status:** Accepted
- **Date:** 2026-10-08
- **Plan sections:** 10.7, 12.3, 16.2 (Next steps, item 4); specs S-21, S-33

## Context

On 8 October 2026 the control experiment (`--control-swap`) showed a picture on the wall when
Roblox got another asset's real CDN answer at the original's address, so Roblox doesn't check
the bytes against the address (H4 ruled out). Verdra's own uncompressed RGBA8 KTX2 wasn't drawn,
so its file is what's wrong. The format capture the same day shows what the CDN sends for a
picture (`docs/platforms/evidence/windows/format-capture-and-control-2026-10-08.txt`):

- HTTP 200, `Content-Type: application/octet-stream`, `Content-Encoding: zstd`;
- a KTX2 with BC1 blocks (vkFormat 131, an opaque picture) or BC3 blocks (vkFormat 137, one with
  alpha), one level, Zstandard supercompression (the level is one zstd frame with its content
  size and no checksum), no supercompression global data;
- a Basic Data Format Descriptor at offset 104 (linear transfer, BT.709 primaries), the key/value
  data right after it and the level right after that;
- 19 keys; each side rounded down to a multiple of 64 (1023 × 682 became 960 × 640, 500 × 500
  became 448 × 448).

The maintainer asked for that layout, with an encoder under an Apache-compatible licence and
with Windows wheels, or Verdra's own in numpy.

## Decision

- strata/ochre writes Verdra's pictures in that layout (`write_roblox_ktx2`): BC1 when every
  pixel is opaque, else BC3; one level; zstd supercompression (level 9, content size, no
  checksum); the CDN's Data Format Descriptor byte for byte; the 19 keys sorted.
- Size: a picture over 1024 pixels a side is scaled to fit 1024 (aspect kept); then each side of
  64 or more is rounded down to a multiple of 64, a smaller one to a multiple of 4 (at least 4).
  Pillow's Lanczos filter resizes.
- Keys: `RobloxOriginalWidth/Height` are the picture's own size, `transcodedWidth/Height` the
  texture's; `avgRed/Green/Blue/Alpha` are the texture's rounded means and
  `weightedAvgRed/Green/Blue` its means weighted by alpha (equal to the plain means for an
  opaque picture, as on the CDN). `acrVersion` "7rdo", `colorSpace` "Linear", `constantColor`
  "0", `packIndex` "2", `pack_1` "1,3", `pack_2` "0,1" and `pack_0` ("4,6" above 512 pixels a
  side, "4,5" otherwise) are written as observed; their meaning is unknown. `contentHash` on the
  CDN is 32 hex digits but not the MD5 of the file or of the level; Verdra writes the MD5 of the
  uncompressed level (deterministic, the same picture gives the same file).
- Colors are stored as they are: the descriptor says linear and the formats are UNORM, so no
  gamma conversion either way.
- Remove is the smallest fully transparent BC3 texture (4 × 4, avgAlpha 0).
- The block encoder is Verdra's own, in numpy, written from the public BC1/BC3 (S3TC) block
  format: each block's endpoints lie along its principal color axis (power iteration),
  quantized to RGB565, four-color mode, the nearest palette entry per pixel; BC3 alpha uses the
  eight-value mode with the block's highest and lowest alpha. No new dependency: numpy, Pillow,
  zstandard (BSD-3-Clause) and texture2ddecoder (MIT, used by the tests as an independent
  decoder) are already in the lock file and pass the allowlist; NOTICE doesn't change.

## Consequences

- Measured on the session machine (Linux, one core): 0.44 to 0.73 s for a 1024 × 1024 picture;
  pictures are prepared once, when Apply now builds the snapshot. Quality on synthetic photos:
  color PSNR 42.7 to 44.9 dB, alpha 54.2 dB through texture2ddecoder.
- It is served with Content-Encoding: zstd when the CDN's answer had it, the CDN's Content-Type
  and a correct Content-Length (roots/hyphae, `Response.coding`); the owner's next test shows
  whether Roblox draws it.
- If a later capture shows other formats (for example mipmaps or another vkFormat), this record
  is amended with the evidence.
