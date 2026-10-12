# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""strata/ochre: KTX2, PNG and JPEG reading and writing, and the limits of plan 10.7."""

from __future__ import annotations

import contextlib
import io
import struct
import zlib

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
        (ktx2(43, 0, 4, b"\0" * 16), "has no pixels"),
        (ktx2(43, 16_385, 1, b"\0" * 16), "a side can be at most 16,384 pixels"),
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


def test_decompression_bombs_are_refused_before_decoding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refused from the header: no pixel is decoded (decoding would fail this test)."""

    def no_decoding(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("decoded a picture that should have been refused")

    # A PNG of 16,000 × 16,000 pixels that compresses to almost nothing: within the side
    # limit, over the pixel limit (it would need 1 GB as RGBA).
    huge = io.BytesIO()
    Image.new("1", (16_000, 16_000)).save(huge, "PNG")
    with pytest.raises(ochre.OchreError, match=r"16,000×16,000 pixels \(256\.0 megapixels\)"):
        ochre.read_image(huge.getvalue())
    # A header claiming 20,000 × 20,000 on top of a few bytes.
    header = io.BytesIO()
    Image.new("RGB", (8, 8)).save(header, "PNG")
    claimed = bytearray(header.getvalue())
    claimed[16:24] = struct.pack(">II", 20_000, 20_000)  # IHDR width and height
    claimed[29:33] = struct.pack(">I", zlib.crc32(bytes(claimed[12:29])))  # and its checksum
    monkeypatch.setattr(Image.Image, "convert", no_decoding)
    monkeypatch.setattr(Image.Image, "load", no_decoding)
    with pytest.raises(ochre.OchreError, match="20,000×20,000 pixels; a side can be at most"):
        ochre.read_image(bytes(claimed))


def test_a_ktx2_level_must_have_the_size_its_header_implies() -> None:
    # A 16 × 16 RGBA level is 1,024 bytes; one claiming 2 GB is refused before decompressing.
    with pytest.raises(ochre.OchreError, match="says 2,147,483,648 bytes, but a 16×16"):
        ochre.read_ktx2(ktx2(43, 16, 16, b"\0" * 64, scheme=2, unpacked=2 << 30))


def test_flat_pictures_that_compress_very_well_are_read() -> None:
    """12 October 2026: a 1600×900 PNG (45 KB, flat color with text) was refused as growing
    127-fold. Pictures have no ratio limit; their pixel count bounds them."""
    flat = io.BytesIO()
    picture = Image.new("P", (6000, 3000), 1)  # a palette picture, as logos often are
    picture.putpalette([0, 0, 0, 40, 120, 200, 255, 0, 0])
    picture.putpixel((5, 5), 2)
    picture.save(flat, "PNG", optimize=True)
    data = flat.getvalue()
    assert 6000 * 3000 * 4 / len(data) > 1000  # noqa: PLR2004 - over 1,000-fold
    read = ochre.read_image(data)
    assert (read.width, read.height) == (6000, 3000)
    assert ochre.roblox_size(read.width, read.height) == (1024, 512)  # downscaled, not refused
    # The same for a texture: a flat 2,048 × 2,048 KTX2 level, Zstandard-supercompressed.
    level = bytes(2048 * 2048 * 4)
    packed = zstandard.ZstdCompressor().compress(level)
    assert len(level) / len(packed) > 1000  # noqa: PLR2004
    assert (
        ochre.read_ktx2(ktx2(43, 2048, 2048, packed, scheme=2, unpacked=len(level))).width == 2048
    )  # noqa: PLR2004


def test_a_truncated_picture_is_refused_with_a_reason() -> None:
    whole = io.BytesIO()
    Image.new("RGB", (200, 200), (1, 2, 3)).save(whole, "PNG")
    with pytest.raises(ochre.OchreError, match="damaged"):
        ochre.read_image(whole.getvalue()[: len(whole.getvalue()) // 2])


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
