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

import io
import struct
import warnings
from dataclasses import dataclass
from typing import Final

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
        1,  # colour model RGBSDA
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
