# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The format capture (roots/litmus, source runs only): what Roblox's CDN really sends.

Plan 16.2 (8 October 2026): replaced pictures weren't drawn on the maintainer's PC, and every CDN
download asked for `encoding=zstd&version=1`. The capture lets the real response for chosen asset
IDs through unchanged and writes a text report: status, headers (redacted), zstd framing, and the
KTX2 layout. Every KTX2 file and zstd frame here is synthetic; every ID and address is invented,
except the public Toolbox image IDs in `tests.ids`.
"""

from __future__ import annotations

import gzip
import json
import logging
import struct
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
import zstandard

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from tests.roots.test_grafter import BATCH, HOST, http
from tests.roots.test_hyphae import FakeServer, Proxy, body_of, run
from tools import fake_roblox
from verdra.roots import hyphae, litmus, rules
from verdra.roots.symbionts.grafter import Grafter
from verdra.strata import clay, ochre
from verdra.trunk.sapwood import cli

CDN = rules.ASSET_CONTENT_HOST
PATH = "/sc3/0123456789abcdef0123456789abcdef"
QUERY = "?encoding=zstd&version=1&Signature=invented-secret"
PLACE = 9876543210  # an invented place ID: never in a report
#: Invented per-session and per-request values (the 8 October captures showed real ones).
SESSION = "11111111-2222-4333-8444-555555555555"
TRACE = "fedcba9876543210fedcba9876543210"
EDGE = "invented-edge-request-id"


def ktx2(*, vk_format: int = 146, levels: int = 2, scheme: int = 2) -> bytes:
    """A synthetic KTX2: a BC7 4×4 texture with `levels` levels, zstd-supercompressed."""
    kvd_entry = b"KTXwriter\x00Verdra test\x00"
    kvd = struct.pack("<I", len(kvd_entry)) + kvd_entry + b"\x00" * (-len(kvd_entry) % 4)
    # Basic descriptor block: vendor 0, type 0, version 2, size 24, colour model BC7 (134),
    # primaries 1, transfer sRGB (2), flags 0, 4×4 texel block (stored as 3,3), 16 bytes a plane.
    block = struct.pack("<IHHBBBB4B8B", 0, 2, 24, 134, 1, 2, 0, 3, 3, 0, 0, 16, 0, 0, 0, 0, 0, 0, 0)
    dfd = struct.pack("<I", 4 + len(block)) + block
    level_data = [b"\x11" * 16 for _ in range(levels)]
    packed = [zstandard.ZstdCompressor().compress(d) if scheme == 2 else d for d in level_data]
    start = 80 + 24 * levels
    dfd_offset, kvd_offset = start, start + len(dfd)
    offset = kvd_offset + len(kvd)
    index = b""
    for data, raw in zip(packed, level_data, strict=True):
        index += struct.pack("<3Q", offset, len(data), len(raw))
        offset += len(data)
    header = struct.pack(
        "<12s9I", ochre.KTX2_IDENTIFIER, vk_format, 1, 4, 4, 0, 0, 1, levels, scheme
    ) + struct.pack("<4I2Q", dfd_offset, len(dfd), kvd_offset, len(kvd), 0, 0)
    return header + index + dfd + kvd + b"".join(packed)


# --- The KTX2 layout (strata/ochre) -----------------------------------------------------------


def test_the_layout_of_a_zstd_supercompressed_bc7_texture() -> None:
    layout = ochre.ktx2_layout(ktx2())
    assert (layout.vk_format, layout.width, layout.height, layout.levels) == (146, 4, 4, 2)
    assert layout.supercompression == 2
    assert ochre.SUPERCOMPRESSION_NAMES[layout.supercompression] == "Zstandard"
    assert layout.dfd["colorModel"] == 134
    assert layout.dfd["transferFunction"] == 2
    assert layout.dfd["bytesPlane0"] == 16
    assert layout.samples == 0
    assert layout.keys == ("KTXwriter",)
    assert [level.uncompressed_length for level in layout.level_index] == [16, 16]


def test_the_layout_of_verdras_own_rgba8_texture() -> None:
    data = ochre.write_ktx2(ochre.Pixels(2, 2, bytes(16)))
    layout = ochre.ktx2_layout(data)
    assert (layout.vk_format, layout.levels, layout.supercompression) == (43, 1, 0)
    assert layout.dfd["colorModel"] == 1  # RGBSDA
    assert layout.samples == 4
    assert layout.keys == ()


@pytest.mark.parametrize(
    "data", [b"", b"not a texture", ochre.KTX2_IDENTIFIER + bytes(20), ktx2()[:90]]
)
def test_a_broken_ktx2_is_refused_with_a_reason(data: bytes) -> None:
    with pytest.raises(ochre.OchreError):
        ochre.ktx2_layout(data)


# --- The body part of a report ----------------------------------------------------------------


def test_a_zstd_framed_body_is_opened_and_its_ktx2_described() -> None:
    text = "\n".join(litmus.body_lines(zstandard.ZstdCompressor().compress(ktx2())))
    assert "starts with the zstd magic 28 B5 2F FD: yes" in text
    assert f"decompressed (zstd): {len(ktx2())} bytes" in text
    assert "vkFormat: 146 (BC7_SRGB)" in text
    assert "supercompressionScheme: 2 (Zstandard)" in text
    assert "(color model BC7)" in text
    assert "keys: KTXwriter" in text
    assert "0: " in text and ", 16, yes" in text  # each level is a zstd frame


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (ochre.write_ktx2(ochre.Pixels(1, 1, bytes(4))), "vkFormat: 43 (R8G8B8A8_SRGB)"),
        (b"\x89PNG\r\n\x1a\n", "not a KTX2 file"),
        (litmus.ZSTD_MAGIC + b"damaged", "couldn't be decompressed"),
        (None, "Body: not read"),
    ],
)
def test_other_bodies_are_described_plainly(body: bytes | None, expected: str) -> None:
    assert expected in "\n".join(litmus.body_lines(body))


# --- The capture, end to end through the proxy ------------------------------------------------


def answer(items: list[dict[str, Any]]) -> bytes:
    """The batch answer, as gzip, with metadata the report must show and a place ID it mustn't."""
    entries = [
        {"requestId": item["requestId"], "location": f"https://{CDN}{PATH}{QUERY}",
         "assetTypeId": 1, "isArchived": False,
         "contentRepresentationSpecifier": {"format": "ktx2", "majorVersion": "1"},
         "assetMetadatas": [{"metadataType": 1, "value": "ktx2"}]}
        for item in items
    ]  # fmt: skip
    return http(gzip.compress(json.dumps(entries).encode()), extra=b"Content-Encoding: gzip\r\n")


def capture_run(
    tmp_path: Path, asked: int
) -> tuple[litmus.FormatCapture, bytes, list[dict[str, Any]]]:
    """The Player's two steps through a grafter and a capture of ABOVE_UINT32 and ABOVE_INT32."""
    items = [{"assetId": asked, "assetType": "Image", "requestId": "r1", "serverPlaceId": PLACE}]
    texture = zstandard.ZstdCompressor().compress(ktx2())
    download = (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\nContent-Encoding: zstd\r\n"
        b"Set-Cookie: session=invented\r\nRoblox-Place-Id: " + str(PLACE).encode() + b"\r\n"
        b"X-Amz-Cf-Id: " + EDGE.encode() + b"\r\nAkamai-GRN: " + EDGE.encode() + b"\r\n"
        b"Content-Length: " + str(len(texture)).encode() + b"\r\n\r\n" + texture
    )
    holder = rules.SnapshotHolder()
    graft = rules.Graft(ABOVE_UINT32, None, "file", "./a.png", "P", "r", "Image")
    content = rules.Content(b"", ochre.write_ktx2(ochre.Pixels(1, 1, bytes(4))), "file")
    holder.publish(
        rules.GraftSnapshot(
            MappingProxyType({(ABOVE_UINT32, None): graft}),
            content=MappingProxyType({ABOVE_UINT32: content}),
        )
    )
    ids = frozenset({ABOVE_UINT32, ABOVE_INT32})
    grafter = Grafter(holder, leave=ids)
    capture = litmus.FormatCapture(ids, tmp_path / "diagnostics")
    pipeline = hyphae.Pipeline(request=[grafter, capture], response=[capture, grafter])
    for folder in (tmp_path / "batch", tmp_path / "cdn"):
        folder.mkdir(parents=True, exist_ok=True)
    batch_server = FakeServer(tmp_path / "batch", {BATCH: answer(items)}, host=HOST)
    cdn_server = FakeServer(tmp_path / "cdn", {f"{PATH}{QUERY}".encode(): download}, host=CDN)

    async def batch() -> list[object]:
        async with Proxy(batch_server, pipeline) as proxy:
            client = await proxy.connect()
            _raw, events = await client.send(fake_roblox.batch_request(items), method=b"POST")
            return events

    async def fetch() -> list[object]:
        async with Proxy(cdn_server, pipeline) as proxy:
            client = await proxy.connect()
            request = (
                f"GET {PATH}{QUERY} HTTP/1.1\r\nHost: {CDN}\r\n"
                f"Roblox-Play-Session-Id: {SESSION}\r\ntraceparent: 00-{TRACE}-0011223344556677-00"
                f"\r\nRoblox-Place-Id: 12\r\n\r\n"
            ).encode()
            _raw, events = await client.send(request)
            return events

    run(batch)
    served = body_of(run(fetch))
    return capture, served, items


@pytest.mark.spec("S-21", 18)
def test_a_captured_download_passes_unchanged_and_is_reported(tmp_path: Path) -> None:
    capture, served, _items = capture_run(tmp_path, ABOVE_UINT32)
    # The real answer reaches Roblox: no replacement, even though one is set for this asset.
    assert zstandard.ZstdDecompressor().decompress(served, max_output_size=1 << 20) == ktx2()
    [path] = capture.reports
    assert path.parent == tmp_path / "diagnostics"
    text = path.read_text(encoding="utf-8")
    assert f"Asset {ABOVE_UINT32}" in text
    assert 'contentRepresentationSpecifier: {"format":"ktx2","majorVersion":"1"}' in text
    assert 'assetMetadatas: [{"metadataType":1,"value":"ktx2"}]' in text
    assert f"location: {CDN}{PATH} (query values left out)" in text
    assert "query names: encoding, version, Signature" in text
    assert "< Content-Encoding: zstd" in text
    assert "starts with the zstd magic 28 B5 2F FD: no" in text  # Verdra undid the encoding
    assert "vkFormat: 146 (BC7_SRGB)" in text
    # Nothing that names the player, the place or a secret.
    for private in (str(PLACE), "invented-secret", "session=invented", '"r1"', SESSION, TRACE):
        assert private not in text
    assert EDGE not in text
    assert "serverPlaceId: (hidden)" in text
    for name in ("Roblox-Play-Session-Id", "traceparent", "Roblox-Place-Id", "X-Amz-Cf-Id"):
        assert f"{name}: (hidden)" in text  # a short place ID too, not just long numbers


def test_reports_are_numbered_per_asset_and_never_overwritten(tmp_path: Path) -> None:
    """On 8 October every report was "-1": the number restarted with each batch."""
    folder = tmp_path / "diagnostics"
    folder.mkdir()
    (folder / f"format-capture-{ABOVE_UINT32}-1.txt").write_text("an earlier run", "utf-8")
    capture = litmus.FormatCapture(frozenset({ABOVE_UINT32}), folder, save_bodies=True)
    request = hyphae.Request(CDN, b"GET", PATH.encode(), ())
    response = hyphae.Response(200, (), b"OK", b"body")
    for _batch in range(3):  # each batch notes the asset anew
        capture._write(litmus._Watched(ABOVE_UINT32, {}), request, response)  # noqa: SLF001
    capture._write(litmus._Watched(ABOVE_INT32, {}), request, response)  # noqa: SLF001
    assert [path.name for path in capture.reports] == [
        f"format-capture-{ABOVE_UINT32}-2.txt",
        f"format-capture-{ABOVE_UINT32}-3.txt",
        f"format-capture-{ABOVE_UINT32}-4.txt",
        f"format-capture-{ABOVE_INT32}-1.txt",
    ]
    assert (folder / f"format-capture-{ABOVE_UINT32}-1.txt").read_text("utf-8") == "an earlier run"
    assert (folder / f"format-capture-{ABOVE_UINT32}-4.bin").read_bytes() == b"body"


def test_a_mesh_body_is_described() -> None:
    mesh = clay.write_filemesh(clay.Mesh((), ()))
    text = "\n".join(litmus.body_lines(mesh))
    assert "FileMesh:" in text
    assert "version: 2.00" in text
    assert "header size: 12" in text
    assert "not a KTX2 file" not in text
    assert "version: 1.00" in "\n".join(litmus.body_lines(b"version 1.00\n0\n"))


def test_a_download_on_another_host_is_never_silent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    capture = litmus.FormatCapture(frozenset({ABOVE_UINT32}), tmp_path)
    items = [{"assetId": ABOVE_UINT32, "assetType": "Mesh", "requestId": "r1"}]
    batch = hyphae.Request(HOST, b"POST", BATCH, (), json.dumps(items).encode())
    capture.on_request(batch)
    located = [{"requestId": "r1", "location": "https://c0.example.invalid/mesh?x=1"}]
    with caplog.at_level(logging.WARNING, logger="verdra.roots.litmus"):
        capture.on_response(batch, hyphae.Response(200, (), b"OK", json.dumps(located).encode()))
    [line] = [r.getMessage() for r in caplog.records]
    assert f"asset {ABOVE_UINT32} downloads from c0.example.invalid" in line


def test_an_asset_not_chosen_is_not_reported(tmp_path: Path) -> None:
    capture, _served, _items = capture_run(tmp_path, 1234567)
    assert capture.reports == []


def test_the_capture_flags_need_the_source(monkeypatch: pytest.MonkeyPatch) -> None:
    arguments = cli.parse([cli.CAPTURE_FLAG, f"{ABOVE_UINT32},{ABOVE_INT32}", cli.BODIES_FLAG])
    assert arguments.format_capture == (ABOVE_UINT32, ABOVE_INT32)
    assert arguments.save_bodies
    assert cli.parse([]).format_capture == ()
    with pytest.raises(SystemExit) as refused:
        cli.parse([cli.CAPTURE_FLAG, "not-an-id"])
    assert refused.value.code == 2
    monkeypatch.setattr(cli, "diagnosis_available", lambda: False)
    with pytest.raises(SystemExit) as frozen:
        cli.parse([cli.CAPTURE_FLAG, str(ABOVE_UINT32)])
    assert frozen.value.code == 2
