# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""strata/ochre: KTX2, PNG and JPEG reading and writing, and the limits of plan 10.7."""

from __future__ import annotations

import contextlib
import io
import struct

import pytest
import zstandard
from hypothesis import given, settings
from hypothesis import strategies as st
from PIL import Image

from verdra.strata import ochre


def pixels(width: int = 3, height: int = 2) -> ochre.Pixels:
    return ochre.Pixels(width, height, bytes((i * 7) % 256 for i in range(width * height * 4)))


def ktx2(vk_format: int, width: int, height: int, level: bytes, *, scheme: int = 0,
         unpacked: int | None = None) -> bytes:  # fmt: skip
    """A minimal KTX2 file around one level (no DFD: readers here don't need it)."""
    offset = 80 + 24
    header = struct.pack(
        "<12s9I", ochre.KTX2_IDENTIFIER, vk_format, 1, width, height, 0, 0, 1, 1, scheme
    )
    index = struct.pack("<4I2Q", 0, 0, 0, 0, 0, 0)
    entry = struct.pack("<3Q", offset, len(level), unpacked if unpacked is not None else len(level))
    return header + index + entry + level


def test_ktx2_round_trips_and_carries_a_data_format_descriptor() -> None:
    original = pixels(5, 3)
    for srgb, vk_format in ((True, 43), (False, 37)):
        data = ochre.write_ktx2(original, srgb=srgb)
        assert data.startswith(ochre.KTX2_IDENTIFIER)
        info = ochre.ktx2_info(data)
        assert (info.vk_format, info.width, info.height, info.levels) == (vk_format, 5, 3, 1)
        assert ochre.read_ktx2(data) == original
        dfd_offset, dfd_length = struct.unpack_from("<2I", data, 48)
        total, _vendor, version, block_size = struct.unpack_from("<IIHH", data, dfd_offset)
        assert total == dfd_length == 92 and version == 2 and block_size == 88
        # The level starts 16-byte aligned (any reader can map it).
        assert struct.unpack_from("<Q", data, 80)[0] % 16 == 0


def test_png_and_jpeg_read_as_rgba_and_png_round_trips() -> None:
    original = pixels(4, 4)
    assert ochre.read_image(ochre.to_png(original)) == original
    out = io.BytesIO()
    Image.new("RGB", (8, 6), (200, 10, 10)).save(out, "JPEG", quality=95)
    read = ochre.read_image(out.getvalue())
    assert (read.width, read.height) == (8, 6)
    red, green, blue, alpha = read.rgba[:4]
    assert red > 180 and green < 40 and blue < 40 and alpha == 255


def test_a_bc1_block_decodes() -> None:
    # One 4×4 BC1 block: colour 0 pure red (RGB565 0xF800), colour 1 blue, every index 0.
    block = struct.pack("<HHI", 0xF800, 0x001F, 0)
    read = ochre.read_ktx2(ktx2(131, 4, 4, block))
    assert read.rgba[:4] == bytes((255, 0, 0, 255))
    assert set(read.rgba[i : i + 4] for i in range(0, 64, 4)) == {bytes((255, 0, 0, 255))}


def test_a_zstandard_supercompressed_level_decodes() -> None:
    original = pixels(16, 16)
    packed = zstandard.ZstdCompressor().compress(original.rgba)
    data = ktx2(43, 16, 16, packed, scheme=2, unpacked=len(original.rgba))
    assert ochre.read_ktx2(data) == original


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"GIF89a" + b"\0" * 40, "isn't a KTX2, PNG, JPEG or DDS image"),
        (ochre.KTX2_IDENTIFIER + b"\0" * 10, "isn't a KTX2 file"),
        (ktx2(43, 0, 4, b"\0" * 16), "sides must be"),
        (ktx2(43, 16_385, 1, b"\0" * 16), "sides must be"),
        (ktx2(43, 4, 4, b"\0" * 8), "shorter than its size says"),
        (ktx2(999, 4, 4, b"\0" * 64), "texture format 999 isn't supported"),
        (ktx2(43, 4, 4, b"\0" * 64, scheme=1), "supercompression scheme 1"),
        (ktx2(43, 4, 4, b"not zstd", scheme=2, unpacked=64), "Zstandard data is damaged"),
        (ochre.PNG_SIGNATURE + b"\0" * 30, "damaged"),
    ],
)
def test_what_ochre_cant_read_is_refused_with_a_reason(data: bytes, reason: str) -> None:
    with pytest.raises(ochre.OchreError, match=reason):
        ochre.read_image(data)


def test_decompression_bombs_are_refused() -> None:
    # A KTX2 level claiming 2 GB, and a small one claiming more than 100 times its size.
    with pytest.raises(ochre.OchreError, match="1 GB"):
        ochre.read_ktx2(ktx2(43, 16_384, 16_384, b"\0" * 64, scheme=2, unpacked=2 << 30))
    with pytest.raises(ochre.OchreError, match="100"):
        ochre.read_ktx2(ktx2(43, 2048, 2048, b"\0" * 1000, scheme=2, unpacked=2048 * 2048 * 4))
    # A PNG of 16,000 × 16,000 pixels that compresses to almost nothing.
    out = io.BytesIO()
    Image.new("L", (16_000, 16_000)).save(out, "PNG")
    with pytest.raises(ochre.OchreError):
        ochre.read_image(out.getvalue())


@settings(max_examples=300, deadline=None)
@given(st.binary(max_size=400))
def test_random_bytes_never_raise_anything_but_ochre_error(data: bytes) -> None:
    for prefix in (b"", ochre.KTX2_IDENTIFIER, ochre.PNG_SIGNATURE, ochre.JPEG_SIGNATURE):
        with contextlib.suppress(ochre.OchreError):
            ochre.read_image(prefix + data)


@settings(max_examples=50, deadline=None)
@given(st.integers(1, 40), st.integers(1, 40), st.booleans(), st.data())
def test_any_rgba_image_round_trips_through_ktx2_and_png(
    width: int, height: int, srgb: bool, data: st.DataObject
) -> None:
    rgba = data.draw(st.binary(min_size=width * height * 4, max_size=width * height * 4))
    original = ochre.Pixels(width, height, rgba)
    assert ochre.read_image(ochre.write_ktx2(original, srgb=srgb)) == original
    assert ochre.read_image(ochre.to_png(original)) == original
