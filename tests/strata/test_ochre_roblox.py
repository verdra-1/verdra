# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Verdra's pictures in the layout Roblox's CDN sends (strata/ochre, decision record 0022).

The layout was captured on the maintainer's PC on 8 October 2026: BC1 (opaque) or BC3 (with
alpha), one level, Zstandard supercompression, Roblox's Data Format Descriptor and 19 keys, and
each side rounded down to a multiple of 64. Every image here is synthetic; no Roblox content is
used. Decoding goes through texture2ddecoder, a decoder independent of Verdra's encoder.
"""

from __future__ import annotations

import hashlib
import time

import numpy as np
import pytest
import zstandard

from verdra.roots import litmus
from verdra.strata import ochre

#: The keys Roblox's files carry, in their (sorted) order.
ROBLOX_KEYS = (
    "RobloxOriginalHeight", "RobloxOriginalWidth", "acrVersion", "avgAlpha", "avgBlue",
    "avgGreen", "avgRed", "colorSpace", "constantColor", "contentHash", "packIndex", "pack_0",
    "pack_1", "pack_2", "transcodedHeight", "transcodedWidth", "weightedAvgBlue",
    "weightedAvgGreen", "weightedAvgRed",
)  # fmt: skip


def picture(width: int, height: int, *, alpha: int | None = None) -> np.ndarray:
    """A smooth synthetic picture (like a photo); constant `alpha`, or a gradient if None… 255."""
    y, x = np.mgrid[0:height, 0:width].astype(np.float64)
    rgba = np.empty((height, width, 4), np.uint8)
    rgba[..., 0] = np.sin(x / 37) * 110 + 128
    rgba[..., 1] = np.cos(y / 29) * 110 + 128
    rgba[..., 2] = (x + y) / max(width + height, 1) * 255
    rgba[..., 3] = 255 if alpha is None else alpha
    return rgba


def pixels(array: np.ndarray) -> ochre.Pixels:
    return ochre.Pixels(array.shape[1], array.shape[0], array.tobytes())


def keys(data: bytes) -> dict[str, str]:
    layout = ochre.ktx2_layout(data)
    found: dict[str, str] = {}
    position = layout.kvd_offset
    while position < layout.kvd_offset + layout.kvd_length:
        size = int.from_bytes(data[position : position + 4], "little")
        key, _, value = data[position + 4 : position + 4 + size].partition(b"\x00")
        found[key.decode()] = value.rstrip(b"\x00").decode()
        position += 4 + size + (-size % 4)
    return found


def level(data: bytes) -> bytes:
    entry = ochre.ktx2_layout(data).level_index[0]
    return zstandard.ZstdDecompressor().decompress(
        data[entry.offset : entry.offset + entry.length], max_output_size=entry.uncompressed_length
    )


def psnr(first: np.ndarray, second: np.ndarray) -> float:
    mse = float(((first.astype(np.float64) - second.astype(np.float64)) ** 2).mean())
    return 99.0 if mse == 0 else 10 * np.log10(255**2 / mse)


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((1023, 682), (960, 640)),  # observed on the CDN
        ((500, 500), (448, 448)),  # observed on the CDN
        ((1024, 1024), (1024, 1024)),
        ((2048, 1024), (1024, 512)),  # over 1024: scaled down first
        ((4000, 300), (1024, 64)),
        ((63, 10), (60, 8)),  # under 64: multiples of 4
        ((1, 1), (4, 4)),  # never under one block
    ],
)
def test_the_size_rule(size: tuple[int, int], expected: tuple[int, int]) -> None:
    assert ochre.roblox_size(*size) == expected


def test_the_layout_matches_the_cdns_as_the_capture_report_shows_it() -> None:
    """Verdra's output through the same report code as the capture of Roblox's files."""
    opaque = ochre.write_roblox_ktx2(pixels(picture(1023, 682)))
    text = "\n".join(litmus.body_lines(opaque))
    for line in (
        "vkFormat: 131 (BC1_RGB_UNORM)",
        "typeSize: 1",
        "pixel size: 960 x 640 x 0",
        "layers: 0, faces: 1, levels: 1",
        "supercompressionScheme: 2 (Zstandard)",
        "DFD: offset 104, length 44",
        "supercompression global data: offset 0, length 0",
        "colorModel 128, colorPrimaries 1, transferFunction 1, flags 0, texelBlockDimension0 3, "
        "texelBlockDimension1 3, bytesPlane0 8 (color model BC1A)",
        "DFD samples: 1",
        "keys: " + ", ".join(ROBLOX_KEYS),
    ):
        assert line in text, line
    assert ", yes" in text.splitlines()[-1]  # the level is one zstd frame
    with_alpha = ochre.write_roblox_ktx2(pixels(picture(500, 500, alpha=148)))
    text = "\n".join(litmus.body_lines(with_alpha))
    for line in (
        "vkFormat: 137 (BC3_UNORM)",
        "pixel size: 448 x 448 x 0",
        "DFD: offset 104, length 60",
        "colorModel 130, colorPrimaries 1, transferFunction 1, flags 0, texelBlockDimension0 3, "
        "texelBlockDimension1 3, bytesPlane0 16 (color model BC3)",
        "DFD samples: 2",
    ):
        assert line in text, line
    layout = ochre.ktx2_layout(with_alpha)
    assert layout.level_index[0].offset == layout.kvd_offset + layout.kvd_length


@pytest.mark.parametrize("alpha", [None, 200])
def test_a_round_trip_through_an_independent_decoder_keeps_the_picture(
    alpha: int | None,
) -> None:
    source = picture(512, 320, alpha=alpha)
    decoded = ochre.read_ktx2(ochre.write_roblox_ktx2(pixels(source)))
    out = np.frombuffer(decoded.rgba, np.uint8).reshape(320, 512, 4)
    assert psnr(out[..., :3], source[..., :3]) > 38
    assert np.abs(out[..., 3].astype(int) - source[..., 3]).max() <= 2


def test_odd_sizes_are_resized_and_still_look_the_same() -> None:
    source = picture(333, 211)
    data = ochre.write_roblox_ktx2(pixels(source))
    decoded = ochre.read_ktx2(data)
    assert (decoded.width, decoded.height) == (320, 192)  # each side down to a multiple of 64
    out = np.frombuffer(decoded.rgba, np.uint8).reshape(192, 320, 4)
    reference = np.asarray(
        ochre.Image.fromarray(source, "RGBA").resize((320, 192), ochre.Image.Resampling.LANCZOS)
    )
    assert psnr(out[..., :3], reference[..., :3]) > 35
    assert keys(data)["RobloxOriginalWidth"] == "333"
    assert keys(data)["transcodedHeight"] == "192"


def test_colors_are_stored_as_they_are_no_gamma_either_way() -> None:
    """Roblox's files say "Linear" and UNORM: a pixel of 128 must come back as 128."""
    gray = np.full((8, 8, 4), 128, np.uint8)
    gray[..., 3] = 255
    decoded = ochre.read_ktx2(ochre.write_roblox_ktx2(pixels(gray)))
    values = np.frombuffer(decoded.rgba, np.uint8).reshape(8, 8, 4)[..., :3]
    # RGB565 keeps 5 or 6 bits a channel (128 comes back as 130 or 132); a gamma conversion
    # either way would move 128 by about 70.
    assert np.abs(values.astype(int) - 128).max() <= 5
    assert keys(ochre.write_roblox_ktx2(pixels(gray)))["colorSpace"] == "Linear"


def test_the_keys_hold_real_values() -> None:
    source = picture(64, 64, alpha=None)
    source[:32, :, 3] = 0  # the top half transparent
    source[:32, :, :3] = 0
    data = ochre.write_roblox_ktx2(pixels(source))
    found = keys(data)
    assert tuple(found) == ROBLOX_KEYS
    assert found["avgAlpha"] == "128"  # half 0, half 255
    channels = source.reshape(-1, 4).astype(np.float64)
    weights = channels[:, 3]
    assert found["avgRed"] == str(round(channels[:, 0].mean()))
    weighted_red = (channels[:, 0] * weights).sum() / weights.sum()
    assert found["weightedAvgRed"] == str(round(weighted_red))
    assert int(found["weightedAvgRed"]) > int(found["avgRed"])  # as on the CDN's alpha picture
    assert (found["acrVersion"], found["constantColor"], found["packIndex"]) == ("7rdo", "0", "2")
    assert found["contentHash"] == hashlib.md5(level(data), usedforsecurity=False).hexdigest()
    assert ochre.write_roblox_ktx2(pixels(source)) == data  # deterministic


def test_remove_is_the_smallest_fully_transparent_bc3_texture() -> None:
    clear = ochre.write_roblox_ktx2(ochre.Pixels(4, 4, bytes(64)))
    layout = ochre.ktx2_layout(clear)
    assert (layout.vk_format, layout.width, layout.height) == (ochre.VK_BC3_UNORM, 4, 4)
    assert keys(clear)["avgAlpha"] == "0"
    decoded = ochre.read_ktx2(clear)
    assert set(decoded.rgba[3::4]) == {0}


def test_tiny_and_very_large_pictures() -> None:
    tiny = ochre.ktx2_layout(ochre.write_roblox_ktx2(pixels(picture(1, 1))))
    assert (tiny.vk_format, tiny.width, tiny.height) == (ochre.VK_BC1_RGB_UNORM, 4, 4)
    started = time.perf_counter()
    large = ochre.ktx2_layout(ochre.write_roblox_ktx2(pixels(picture(4096, 2048))))
    assert (large.width, large.height) == (1024, 512)
    assert time.perf_counter() - started < 20  # measured about 1 s on the CI runner's class


def test_blocks_need_sides_divisible_by_four() -> None:
    with pytest.raises(ochre.OchreError):
        ochre.encode_bc1(np.zeros((6, 8, 4), np.uint8))


def test_a_one_color_block_decodes_to_that_color() -> None:
    solid = np.zeros((4, 4, 4), np.uint8)
    solid[..., :3] = (200, 40, 90)
    solid[..., 3] = 255
    decoded = ochre.read_ktx2(ochre.write_roblox_ktx2(pixels(solid)))
    values = np.frombuffer(decoded.rgba, np.uint8).reshape(4, 4, 4)[..., :3]
    assert np.abs(values.astype(int) - (200, 40, 90)).max() <= 4  # RGB565 precision
