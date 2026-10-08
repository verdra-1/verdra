# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Textures: KTX2 reader and writer, block decoding through texture2ddecoder, PNG conversion,
TexturePack slots.

Spec S-33 (strata/ochre), written from the Khronos KTX 2.0 specification. Pure functions over
bytes: `read_image` turns KTX2, PNG, JPEG or DDS into `Pixels` (8-bit RGBA, top row first);
`write_ktx2` writes the base level as uncompressed RGBA8, with its Data Format Descriptor;
`to_png` writes a PNG. Every reader checks the limits of plan 10.7 before it allocates (16,384
pixels a side, 1 GB decompressed, 100:1 ratio) and raises `OchreError` with a plain reason for
anything it can't read; random bytes never raise anything else.
"""

from __future__ import annotations

import hashlib
import io
import struct
import warnings
from dataclasses import dataclass
from typing import Final

import numpy as np
import texture2ddecoder
import zstandard
from PIL import Image

#: Plan 10.7: the largest image side, decompressed size and compression ratio Verdra accepts.
MAX_SIDE: Final = 16_384
MAX_DECOMPRESSED: Final = 1 << 30
MAX_RATIO: Final = 100

KTX2_IDENTIFIER: Final = b"\xabKTX 20\xbb\r\n\x1a\n"
_HEADER = struct.Struct("<12s9I")  # identifier, vkFormat … supercompressionScheme
_INDEX = struct.Struct("<4I2Q")  # dfd offset/length, kvd offset/length, sgd offset/length
_LEVEL = struct.Struct("<3Q")  # byteOffset, byteLength, uncompressedByteLength
PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE: Final = b"\xff\xd8\xff"
DDS_SIGNATURE: Final = b"DDS "

# Vulkan format numbers (KTX 2.0 uses VkFormat) for what ochre reads.
VK_R8G8B8A8_UNORM: Final = 37
VK_R8G8B8A8_SRGB: Final = 43
VK_R8G8B8_UNORM: Final = 23
VK_R8G8B8_SRGB: Final = 29
_BLOCKS: Final = {
    # vkFormat: (texture2ddecoder function name, bytes per 4×4 block)
    131: ("decode_bc1", 8),  # BC1_RGB_UNORM
    132: ("decode_bc1", 8),  # BC1_RGB_SRGB
    133: ("decode_bc1", 8),  # BC1_RGBA_UNORM
    134: ("decode_bc1", 8),  # BC1_RGBA_SRGB
    137: ("decode_bc3", 16),  # BC3_UNORM
    138: ("decode_bc3", 16),  # BC3_SRGB
    139: ("decode_bc4", 8),  # BC4_UNORM
    141: ("decode_bc5", 16),  # BC5_UNORM
    145: ("decode_bc7", 16),  # BC7_UNORM
    146: ("decode_bc7", 16),  # BC7_SRGB
    147: ("decode_etc2", 8),  # ETC2_R8G8B8_UNORM
    148: ("decode_etc2", 8),  # ETC2_R8G8B8_SRGB
    151: ("decode_etc2a8", 16),  # ETC2_R8G8B8A8_UNORM
    152: ("decode_etc2a8", 16),  # ETC2_R8G8B8A8_SRGB
    157: ("decode_astc", 16),  # ASTC_4x4_UNORM
    158: ("decode_astc", 16),  # ASTC_4x4_SRGB
}
_SUPERCOMPRESSION_NONE: Final = 0
_SUPERCOMPRESSION_ZSTD: Final = 2


class OchreError(ValueError):
    """An image can't be read or written; the message is the plain reason (M-FMT-01)."""


@dataclass(frozen=True, slots=True)
class Pixels:
    """An 8-bit RGBA image, top row first, four bytes a pixel."""

    width: int
    height: int
    rgba: bytes

    def __post_init__(self) -> None:
        _check_size(self.width, self.height)
        if len(self.rgba) != self.width * self.height * 4:
            msg = f"{len(self.rgba)} bytes don't make a {self.width}×{self.height} RGBA image"
            raise OchreError(msg)


def _check_size(width: int, height: int) -> None:
    if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE):
        msg = f"the image is {width}×{height}; sides must be 1 to {MAX_SIDE:,} pixels"
        raise OchreError(msg)


def _check_growth(packed: int, unpacked: int) -> None:
    """Plan 10.7: at most 1 GB decompressed, and at most 100 times the packed size."""
    if unpacked > MAX_DECOMPRESSED:
        msg = f"it would decompress to {unpacked:,} bytes (the limit is 1 GB)"
        raise OchreError(msg)
    if packed > 0 and unpacked > packed * MAX_RATIO and unpacked > 1 << 20:
        msg = f"it would grow {unpacked // packed}-fold when decompressed (the limit is 100)"
        raise OchreError(msg)


# --- Reading ---------------------------------------------------------------------------------


def read_image(data: bytes) -> Pixels:
    """Read KTX2, PNG, JPEG or DDS into RGBA pixels (KTX2: the base level)."""
    if data.startswith(KTX2_IDENTIFIER):
        return read_ktx2(data)
    if data.startswith((PNG_SIGNATURE, JPEG_SIGNATURE, DDS_SIGNATURE)):
        return _read_with_pillow(data)
    msg = "it isn't a KTX2, PNG, JPEG or DDS image"
    raise OchreError(msg)


def _read_with_pillow(data: bytes) -> Pixels:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                _check_size(image.width, image.height)
                _check_growth(len(data), image.width * image.height * 4)
                rgba = image.convert("RGBA")
                return Pixels(rgba.width, rgba.height, rgba.tobytes())
    except OchreError:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, EOFError) as error:
        msg = f"the image data is damaged ({type(error).__name__})"
        raise OchreError(msg) from error
    except Image.DecompressionBombWarning as error:  # type: ignore[misc]
        raise OchreError(str(error)) from error


@dataclass(frozen=True, slots=True)
class Ktx2Info:
    """What a KTX2 header says."""

    vk_format: int
    width: int
    height: int
    levels: int
    supercompression: int


def ktx2_info(data: bytes) -> Ktx2Info:
    """Read and check a KTX2 header (without decoding any pixels)."""
    if len(data) < _HEADER.size + _INDEX.size or not data.startswith(KTX2_IDENTIFIER):
        msg = "it isn't a KTX2 file"
        raise OchreError(msg)
    (_, vk_format, _type_size, width, height, depth, layers, faces, levels, scheme) = (
        _HEADER.unpack_from(data, 0)
    )
    if depth > 1 or layers > 1 or faces not in (0, 1):
        msg = "3D, array and cube-map textures aren't supported"
        raise OchreError(msg)
    _check_size(width, max(height, 1))
    if levels > 32:
        msg = f"it claims {levels} mip levels"
        raise OchreError(msg)
    return Ktx2Info(vk_format, width, max(height, 1), max(levels, 1), scheme)


@dataclass(frozen=True, slots=True)
class Ktx2Level:
    """One entry of a KTX2 level index."""

    offset: int
    length: int
    uncompressed_length: int


@dataclass(frozen=True, slots=True)
class Ktx2Layout:
    """Everything a KTX2 file's header, index and descriptor say, for a diagnostic report.

    Unlike `ktx2_info`, nothing is refused: a cube map, an array or an unknown format is
    described as it is. `dfd` is the first descriptor block's fields; `keys` the key/value
    data's keys (values aren't read).
    """

    vk_format: int
    type_size: int
    width: int
    height: int
    depth: int
    layers: int
    faces: int
    levels: int
    supercompression: int
    dfd_offset: int
    dfd_length: int
    kvd_offset: int
    kvd_length: int
    sgd_offset: int
    sgd_length: int
    level_index: tuple[Ktx2Level, ...]
    dfd: dict[str, int]
    samples: int
    keys: tuple[str, ...]


#: KTX 2.0 supercompressionScheme values.
SUPERCOMPRESSION_NAMES: Final = {0: "none", 1: "BasisLZ", 2: "Zstandard", 3: "ZLIB"}
_DFD_BLOCK = struct.Struct("<IHHBBBB4B8B")


def ktx2_layout(data: bytes) -> Ktx2Layout:
    """Describe a KTX2 file's layout (header, level index, descriptor, keys) without decoding.

    Raises:
        OchreError: not a KTX2 file, or it ends inside its header or level index.
    """
    if len(data) < _HEADER.size + _INDEX.size or not data.startswith(KTX2_IDENTIFIER):
        msg = "it isn't a KTX2 file"
        raise OchreError(msg)
    (_, vk_format, type_size, width, height, depth, layers, faces, levels, scheme) = (
        _HEADER.unpack_from(data, 0)
    )
    dfd_offset, dfd_length, kvd_offset, kvd_length, sgd_offset, sgd_length = _INDEX.unpack_from(
        data, _HEADER.size
    )
    start = _HEADER.size + _INDEX.size
    count = max(levels, 1)
    if count > 32 or len(data) < start + _LEVEL.size * count:  # noqa: PLR2004
        msg = "the file ends inside its level index"
        raise OchreError(msg)
    index = tuple(
        Ktx2Level(*_LEVEL.unpack_from(data, start + _LEVEL.size * n)) for n in range(count)
    )
    dfd, samples = _dfd_summary(data, dfd_offset, dfd_length)
    keys = _kvd_keys(data, kvd_offset, kvd_length)
    return Ktx2Layout(
        vk_format, type_size, width, height, depth, layers, faces, levels, scheme,
        dfd_offset, dfd_length, kvd_offset, kvd_length, sgd_offset, sgd_length,
        index, dfd, samples, keys,
    )  # fmt: skip


def _dfd_summary(data: bytes, offset: int, length: int) -> tuple[dict[str, int], int]:
    """The first descriptor block's fields (Khronos Data Format 1.3), and its sample count."""
    if length < 4 + _DFD_BLOCK.size or offset + length > len(data):
        return {}, 0
    fields = _DFD_BLOCK.unpack_from(data, offset + 4)
    first, version, block_size = fields[0], fields[1], fields[2]
    summary = {
        "vendorId": first & 0x1FFFF,
        "descriptorType": first >> 17,
        "versionNumber": version,
        "descriptorBlockSize": block_size,
        "colorModel": fields[3],
        "colorPrimaries": fields[4],
        "transferFunction": fields[5],
        "flags": fields[6],
        "texelBlockDimension0": fields[7],
        "texelBlockDimension1": fields[8],
        "bytesPlane0": fields[11],
    }
    return summary, max(0, (block_size - _DFD_BLOCK.size) // 16)


def _kvd_keys(data: bytes, offset: int, length: int) -> tuple[str, ...]:
    """The keys of the key/value data (each entry: length, key NUL value, padding to 4)."""
    keys: list[str] = []
    position, end = offset, min(offset + length, len(data))
    while length and position + 4 <= end and len(keys) < 64:  # noqa: PLR2004
        (size,) = struct.unpack_from("<I", data, position)
        entry = data[position + 4 : position + 4 + size]
        if not size or len(entry) < size:
            break
        keys.append(entry.split(b"\x00", 1)[0].decode("utf-8", "replace"))
        position += 4 + size + (-size % 4)
    return tuple(keys)


def read_ktx2(data: bytes) -> Pixels:
    """Decode a KTX2 file's base level to RGBA pixels."""
    info = ktx2_info(data)
    level_index = _HEADER.size + _INDEX.size
    if len(data) < level_index + _LEVEL.size * info.levels:
        msg = "the file ends inside its level index"
        raise OchreError(msg)
    offset, length, unpacked_length = _LEVEL.unpack_from(data, level_index)  # level 0 = base
    if offset + length > len(data) or length == 0:
        msg = "the base level lies outside the file"
        raise OchreError(msg)
    packed = data[offset : offset + length]
    if info.supercompression == _SUPERCOMPRESSION_ZSTD:
        _check_growth(length, unpacked_length)
        try:
            level = zstandard.ZstdDecompressor().decompress(packed, max_output_size=unpacked_length)
        except zstandard.ZstdError as error:
            msg = "its Zstandard data is damaged"
            raise OchreError(msg) from error
    elif info.supercompression == _SUPERCOMPRESSION_NONE:
        level = packed
    else:
        msg = f"supercompression scheme {info.supercompression} isn't supported"
        raise OchreError(msg)
    return _decode_level(info.vk_format, info.width, info.height, level)


def _decode_level(vk_format: int, width: int, height: int, level: bytes) -> Pixels:
    if vk_format in (VK_R8G8B8A8_UNORM, VK_R8G8B8A8_SRGB):
        need = width * height * 4
        if len(level) < need:
            msg = "the base level is shorter than its size says"
            raise OchreError(msg)
        return Pixels(width, height, bytes(level[:need]))
    if vk_format in (VK_R8G8B8_UNORM, VK_R8G8B8_SRGB):
        need = width * height * 3
        if len(level) < need:
            msg = "the base level is shorter than its size says"
            raise OchreError(msg)
        rgb = Image.frombytes("RGB", (width, height), bytes(level[:need]))
        return Pixels(width, height, rgb.convert("RGBA").tobytes())
    if vk_format not in _BLOCKS:
        msg = f"texture format {vk_format} isn't supported"
        raise OchreError(msg)
    name, block_bytes = _BLOCKS[vk_format]
    need = ((width + 3) // 4) * ((height + 3) // 4) * block_bytes
    if len(level) < need:
        msg = "the base level is shorter than its size says"
        raise OchreError(msg)
    decode = getattr(texture2ddecoder, name)
    args = (
        (bytes(level[:need]), width, height, 4, 4)
        if name == "decode_astc"
        else (bytes(level[:need]), width, height)
    )
    bgra = decode(*args)
    image = Image.frombytes("RGBA", (width, height), bgra, "raw", "BGRA")
    return Pixels(width, height, image.tobytes())


# --- Writing ---------------------------------------------------------------------------------


def write_ktx2(pixels: Pixels, *, srgb: bool = True) -> bytes:
    """Write `pixels` as a one-level, uncompressed RGBA8 KTX2 file (sRGB unless told linear)."""
    vk_format = VK_R8G8B8A8_SRGB if srgb else VK_R8G8B8A8_UNORM
    dfd = _rgba8_dfd(srgb=srgb)
    level_index = _HEADER.size + _INDEX.size
    dfd_offset = level_index + _LEVEL.size
    data_offset = dfd_offset + len(dfd)
    data_offset += -data_offset % 16  # aligned for any reader
    header = _HEADER.pack(
        KTX2_IDENTIFIER, vk_format, 1, pixels.width, pixels.height, 0, 0, 1, 1,
        _SUPERCOMPRESSION_NONE,
    )  # fmt: skip
    index = _INDEX.pack(dfd_offset, len(dfd), 0, 0, 0, 0)
    level = _LEVEL.pack(data_offset, len(pixels.rgba), len(pixels.rgba))
    body = header + index + level + dfd
    return body + b"\x00" * (data_offset - len(body)) + pixels.rgba


def _rgba8_dfd(*, srgb: bool) -> bytes:
    """The Basic Data Format Descriptor block for 8-bit RGBA (KTX 2.0, Khronos Data Format)."""
    samples = b""
    for index, channel in enumerate((0, 1, 2, 15)):  # R, G, B, alpha
        channel_type = channel | (0x10 if srgb and channel == 15 else 0)  # alpha stays linear
        samples += struct.pack("<HBB4BII", index * 8, 7, channel_type, 0, 0, 0, 0, 0, 255)
    block_size = 24 + len(samples)
    transfer = 2 if srgb else 1  # sRGB, linear
    block = struct.pack(
        "<IHHBBBB4B8B",
        0,  # vendor 0 (Khronos), descriptor type 0 (basic)
        2,  # version 2
        block_size,
        1,  # color model RGBSDA
        1,  # primaries BT.709
        transfer,
        0,  # straight alpha
        0, 0, 0, 0,  # one texel a block
        4, 0, 0, 0, 0, 0, 0, 0,  # four bytes in plane 0
    ) + samples  # fmt: skip
    return struct.pack("<I", 4 + len(block)) + block


def to_png(pixels: Pixels) -> bytes:
    """Write `pixels` as a PNG."""
    out = io.BytesIO()
    Image.frombytes("RGBA", (pixels.width, pixels.height), pixels.rgba).save(out, "PNG")
    return out.getvalue()


# --- Roblox's texture layout (what the asset CDN sends; captured 8 October 2026) -------------
#
# docs/platforms/evidence/windows/format-capture-and-control-2026-10-08.txt: a KTX2 with BC1
# blocks (an opaque picture) or BC3 blocks (one with alpha), one level, Zstandard
# supercompression, a Data Format Descriptor shaped like the CDN's, and Roblox's 19 keys. The
# block encoder is Verdra's own (numpy), written from the public BC1/BC3 (S3TC) block format:
# endpoints along each block's principal color axis, then the nearest palette entry per pixel.

#: The longest side Verdra makes (Roblox's own pictures stay within 1024 pixels).
ROBLOX_MAX_SIDE: Final = 1024
VK_BC1_RGB_UNORM: Final = 131
VK_BC3_UNORM: Final = 137
#: The level's zstd frame: Roblox's carried the content size and no checksum.
_ZSTD_LEVEL: Final = 9
#: Observed values whose meaning isn't known; written as the CDN wrote them.
_OBSERVED_KEYS: Final = {
    "acrVersion": "7rdo",
    "colorSpace": "Linear",
    "constantColor": "0",
    "packIndex": "2",
    "pack_1": "1,3",
    "pack_2": "0,1",
}


def roblox_size(width: int, height: int) -> tuple[int, int]:
    """The size Verdra's texture gets: within 1024 a side, each side a multiple of 64.

    Observed on the CDN: 1023 × 682 became 960 × 640 and 500 × 500 became 448 × 448, each side
    rounded down to a multiple of 64. A side under 64 is rounded down to a multiple of 4 (the
    block size), and never below 4.
    """
    scale = min(1.0, ROBLOX_MAX_SIDE / max(width, height, 1))
    return _roblox_side(round(width * scale)), _roblox_side(round(height * scale))


def _roblox_side(side: int) -> int:
    if side >= 64:  # noqa: PLR2004
        return side // 64 * 64
    return max(4, side // 4 * 4)


def write_roblox_ktx2(pixels: Pixels) -> bytes:
    """Write `pixels` in the CDN's layout: BC1 if fully opaque, else BC3 (decision record 0022).

    The color values are stored as they are (UNORM, the "Linear" color space Roblox's own
    files name): no gamma conversion either way, so a pixel of 128 decodes as 128 again.
    """
    width, height = roblox_size(pixels.width, pixels.height)
    rgba = _resized(pixels, width, height)
    opaque = bool((rgba[..., 3] == 255).all())  # noqa: PLR2004
    level = encode_bc1(rgba) if opaque else encode_bc3(rgba)
    vk_format = VK_BC1_RGB_UNORM if opaque else VK_BC3_UNORM
    dfd = _bc_dfd(opaque=opaque)
    keys = _roblox_keys(rgba, (pixels.width, pixels.height), level)
    kvd = b"".join(_kvd_entry(key, value) for key, value in sorted(keys.items()))
    packed = zstandard.ZstdCompressor(
        level=_ZSTD_LEVEL, write_checksum=False, write_content_size=True
    ).compress(level)
    dfd_offset = _HEADER.size + _INDEX.size + _LEVEL.size
    kvd_offset = dfd_offset + len(dfd)
    level_offset = kvd_offset + len(kvd)
    header = _HEADER.pack(
        KTX2_IDENTIFIER, vk_format, 1, width, height, 0, 0, 1, 1, _SUPERCOMPRESSION_ZSTD
    )
    index = _INDEX.pack(dfd_offset, len(dfd), kvd_offset, len(kvd), 0, 0)
    return header + index + _LEVEL.pack(level_offset, len(packed), len(level)) + dfd + kvd + packed


def _resized(pixels: Pixels, width: int, height: int) -> np.ndarray:
    array = np.frombuffer(pixels.rgba, np.uint8).reshape(pixels.height, pixels.width, 4)
    if (width, height) == (pixels.width, pixels.height):
        return array
    image = Image.fromarray(array, "RGBA").resize((width, height), Image.Resampling.LANCZOS)
    return np.asarray(image, np.uint8)


def _roblox_keys(rgba: np.ndarray, original: tuple[int, int], level: bytes) -> dict[str, str]:
    """Roblox's 19 keys. Averages are over the texture Verdra sends; weighted ones by alpha.

    contentHash: Roblox's isn't the MD5 of the file or of the level, and what it hashes isn't
    known. Verdra's is the MD5 of the uncompressed level (the blocks), so equal textures get
    equal hashes.
    """
    channels = rgba.reshape(-1, 4).astype(np.float64)
    means = channels.mean(axis=0)
    alpha = channels[:, 3]
    total = alpha.sum()
    weighted = (channels[:, :3] * alpha[:, None]).sum(axis=0) / total if total else np.zeros(3)
    height, width = rgba.shape[:2]
    keys = dict(_OBSERVED_KEYS)
    keys |= {
        "RobloxOriginalWidth": str(original[0]),
        "RobloxOriginalHeight": str(original[1]),
        "transcodedWidth": str(width),
        "transcodedHeight": str(height),
        "avgRed": str(round(means[0])),
        "avgGreen": str(round(means[1])),
        "avgBlue": str(round(means[2])),
        "avgAlpha": str(round(means[3])),
        "weightedAvgRed": str(round(weighted[0])),
        "weightedAvgGreen": str(round(weighted[1])),
        "weightedAvgBlue": str(round(weighted[2])),
        # Observed "4,6" for 960 × 640 and "4,5" for 448 × 448; meaning unknown.
        "pack_0": "4,6" if max(width, height) > 512 else "4,5",  # noqa: PLR2004
        "contentHash": hashlib.md5(level, usedforsecurity=False).hexdigest(),
    }
    return keys


def _kvd_entry(key: str, value: str) -> bytes:
    """One key/value entry (KTX 2.0 section 3.11): length, key NUL value NUL, padding to 4."""
    entry = key.encode("utf-8") + b"\x00" + value.encode("utf-8") + b"\x00"
    return struct.pack("<I", len(entry)) + entry + b"\x00" * (-len(entry) % 4)


def _bc_dfd(*, opaque: bool) -> bytes:
    """The Basic Data Format Descriptor the CDN's BC1 or BC3 files carry (linear, BT.709)."""
    if opaque:  # BC1A color model, one 64-bit sample of channel 0
        model, plane, samples = 128, 8, [(0, 63, 0)]
    else:  # BC3: alpha (channel 15) in bits 0-63, color in bits 64-127
        model, plane, samples = 130, 16, [(0, 63, 15), (64, 63, 0)]
    body = b"".join(
        struct.pack("<HBB4BII", offset, length, channel, 0, 0, 0, 0, 0, 0xFFFFFFFF)
        for offset, length, channel in samples
    )
    block = (
        struct.pack(
            "<IHHBBBB4B8B",
            0,
            2,
            24 + len(body),
            model,
            1,
            1,
            0,
            3,
            3,
            0,
            0,
            plane,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )  # fmt: skip
        + body
    )
    return struct.pack("<I", 4 + len(block)) + block


# --- BC1 and BC3 block encoding ------------------------------------------------------------------


def _blocks(rgba: np.ndarray) -> np.ndarray:
    """The image as 4 × 4 blocks, row by row: shape (blocks, 16, 4)."""
    height, width = rgba.shape[:2]
    if height % 4 or width % 4:
        msg = "a block-compressed texture needs sides that are multiples of 4"
        raise OchreError(msg)
    return (
        rgba.reshape(height // 4, 4, width // 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 4)
    )


def _expand565(packed: np.ndarray) -> np.ndarray:
    """RGB565 values back to 8-bit colors, as decoders expand them."""
    red = (packed >> 11) & 31
    green = (packed >> 5) & 63
    blue = packed & 31
    return np.stack(
        [(red << 3) | (red >> 2), (green << 2) | (green >> 4), (blue << 3) | (blue >> 2)], axis=-1
    ).astype(np.float32)


def _color_blocks(colors: np.ndarray) -> np.ndarray:
    """BC1 color blocks (four-color mode) for (blocks, 16, 3) colors: (blocks, 8) bytes."""
    mean = colors.mean(axis=1)
    offsets = colors - mean[:, None, :]
    covariance = np.einsum("nki,nkj->nij", offsets, offsets)
    axis = np.full(mean.shape, 1 / np.sqrt(3), np.float32)
    for _ in range(6):  # power iteration towards the principal axis
        axis = np.einsum("nij,nj->ni", covariance, axis)
        norm = np.linalg.norm(axis, axis=1, keepdims=True)
        axis = np.where(norm > 1e-6, axis / np.maximum(norm, 1e-6), 1 / np.sqrt(3))  # noqa: PLR2004
    along = np.einsum("nki,ni->nk", offsets, axis)
    high = np.clip(mean + axis * along.max(axis=1, keepdims=True), 0, 255)
    low = np.clip(mean + axis * along.min(axis=1, keepdims=True), 0, 255)
    first, second = _to565(high), _to565(low)
    swap = first < second
    first, second = np.where(swap, second, first), np.where(swap, first, second)
    c0, c1 = _expand565(first), _expand565(second)
    palette = np.stack([c0, c1, (2 * c0 + c1) / 3, (c0 + 2 * c1) / 3], axis=1)
    distance = ((colors[:, :, None, :] - palette[:, None, :, :]) ** 2).sum(axis=-1)
    indices = distance.argmin(axis=-1).astype(np.uint32)
    indices[first == second] = 0  # one color: index 0 everywhere
    bits = (indices << (2 * np.arange(16, dtype=np.uint32))).sum(axis=1, dtype=np.uint32)
    out = np.zeros(len(colors), dtype=[("c0", "<u2"), ("c1", "<u2"), ("bits", "<u4")])
    out["c0"], out["c1"], out["bits"] = first, second, bits
    return out.view(np.uint8).reshape(-1, 8)


def _to565(color: np.ndarray) -> np.ndarray:
    red = np.rint(color[:, 0] * 31 / 255).astype(np.uint16)
    green = np.rint(color[:, 1] * 63 / 255).astype(np.uint16)
    blue = np.rint(color[:, 2] * 31 / 255).astype(np.uint16)
    return (red << 11) | (green << 5) | blue


def _alpha_blocks(alpha: np.ndarray) -> np.ndarray:
    """BC3 alpha blocks (eight-value mode) for (blocks, 16) alphas: (blocks, 8) bytes."""
    high = alpha.max(axis=1).astype(np.float32)
    low = alpha.min(axis=1).astype(np.float32)
    # Entry 0 is `high`, entry 1 `low`, entries 2-7 lie between: (8 - i) sevenths of `high`.
    weights = np.array([7, 0, 6, 5, 4, 3, 2, 1], np.float32)
    palette = (high[:, None] * weights + low[:, None] * (7 - weights)) / 7
    distance = np.abs(alpha[:, :, None].astype(np.float32) - palette[:, None, :])
    indices = distance.argmin(axis=-1).astype(np.uint64)
    indices[high == low] = 0
    bits = (indices << (3 * np.arange(16, dtype=np.uint64))).sum(axis=1, dtype=np.uint64)
    out = np.zeros((len(alpha), 8), np.uint8)
    out[:, 0], out[:, 1] = high.astype(np.uint8), low.astype(np.uint8)
    out[:, 2:] = bits.astype("<u8").view(np.uint8).reshape(-1, 8)[:, :6]
    return out


def encode_bc1(rgba: np.ndarray) -> bytes:
    """Encode an (height, width, 4) image with sides divisible by 4 as BC1 blocks (opaque)."""
    blocks = _blocks(rgba)
    return _color_blocks(blocks[..., :3].astype(np.float32)).tobytes()


def encode_bc3(rgba: np.ndarray) -> bytes:
    """Encode an (height, width, 4) image with sides divisible by 4 as BC3 blocks."""
    blocks = _blocks(rgba)
    color = _color_blocks(blocks[..., :3].astype(np.float32))
    alpha = _alpha_blocks(blocks[..., 3])
    return np.concatenate([alpha, color], axis=1).tobytes()
