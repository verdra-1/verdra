# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-21: content replacements. Roblox downloads the replacement's bytes instead.

A Local file target leaves the batch request as it is. The batch response says where the
original's content will be downloaded on the asset CDN; when Roblox downloads it, Verdra sends
the replacement, prepared ahead of time in the format the CDN answered with (PNG or KTX2).
Batches go through the fake Roblox server's compressed form, as the real Player sends them.
Every ID and address below is invented, except the public Toolbox image in `tests.ids`.
"""

from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from tests.roots.test_grafter import BATCH, HOST, FakeSettings, http, warnings_logged
from tests.roots.test_hyphae import FakeServer, Proxy, body_of, run
from tools import fake_roblox
from verdra.roots import hyphae, rules
from verdra.roots.symbionts.grafter import Grafter
from verdra.strata import ochre
from verdra.trunk.branches import grafts

CDN = rules.ASSET_CONTENT_HOST
#: The path the batch response names for the original's content (a content hash, invented).
PATH = "/0123456789abcdef0123456789abcdef"
ORIGINAL_PNG = ochre.to_png(ochre.Pixels(2, 1, bytes([255, 0, 0, 255, 255, 0, 0, 255])))
REPLACEMENT = ochre.Pixels(1, 2, bytes([0, 0, 255, 255, 0, 255, 0, 128]))
CONTENT = rules.Content(ochre.to_png(REPLACEMENT), ochre.write_ktx2(REPLACEMENT), "file")
ITEMS = [
    {"assetId": ABOVE_UINT32, "assetType": "Image", "requestId": "0",
     "contentRepresentationPriorityList": "W3sxfV0="},
    {"assetId": ABOVE_INT32, "assetType": "Image", "requestId": "1"},
]  # fmt: skip


def snapshot(content: dict[int, rules.Content] | None = None) -> rules.SnapshotHolder:
    holder = rules.SnapshotHolder()
    graft = rules.Graft(ABOVE_UINT32, None, "file", "./a.png", "P", "r", "Image")
    holder.publish(
        rules.GraftSnapshot(
            MappingProxyType({(ABOVE_UINT32, None): graft}),
            content=MappingProxyType(content if content is not None else {ABOVE_UINT32: CONTENT}),
        )
    )
    return holder


def located(items: list[dict[str, Any]], host: str = CDN) -> bytes:
    """The batch response: where each item's content will be downloaded."""
    answer = [
        {"requestId": item["requestId"], "location": f"https://{host}{PATH}{n}?sig=secret",
         "assetTypeId": 1, "assetId": item["assetId"]}
        for n, item in enumerate(items)
    ]  # fmt: skip
    return http(gzip.compress(json.dumps(answer).encode()), extra=b"Content-Encoding: gzip\r\n")


def get(target: str) -> bytes:
    return f"GET {target} HTTP/1.1\r\nHost: {CDN}\r\n\r\n".encode()


def play(
    tmp_path: Path, grafter: Grafter, download: bytes, *, host: str = CDN
) -> tuple[list[dict[str, Any]], bytes, FakeServer]:
    """The Player's two steps: the batch, then downloading the first item's content."""
    batch_server = FakeServer(tmp_path / "batch", {BATCH: located(ITEMS, host)}, host=HOST)
    cdn_server = FakeServer(tmp_path / "cdn", {f"{PATH}0?sig=secret".encode(): download}, host=CDN)
    pipeline = hyphae.Pipeline(request=[grafter], response=[grafter])
    for folder in (tmp_path / "batch", tmp_path / "cdn"):
        folder.mkdir(exist_ok=True)

    async def batch() -> list[object]:
        async with Proxy(batch_server, pipeline) as proxy:
            client = await proxy.connect()
            _raw, events = await client.send(fake_roblox.batch_request(ITEMS), method=b"POST")
            return events

    async def fetch() -> bytes:
        async with Proxy(cdn_server, pipeline) as proxy:
            client = await proxy.connect()
            _raw, events = await client.send(get(f"{PATH}0?sig=secret"))
            return body_of(events)

    answer = body_of(run(batch))
    items = json.loads(gzip.decompress(answer) if answer.startswith(b"\x1f\x8b") else answer)
    return items, run(fetch), batch_server


@pytest.mark.spec("S-21", 1)
@pytest.mark.parametrize(
    ("original", "extra", "served"),
    [
        (ORIGINAL_PNG, b"", CONTENT.png),
        (ochre.write_ktx2(ochre.read_image(ORIGINAL_PNG)), b"", CONTENT.ktx2),
        (gzip.compress(ORIGINAL_PNG), b"Content-Encoding: gzip\r\n", CONTENT.png),
    ],
    ids=["png", "ktx2", "png-gzip"],
)
def test_the_download_of_a_replaced_asset_gets_the_replacement_in_the_same_format(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, original: bytes, extra: bytes, served: bytes
) -> None:
    caplog.set_level(logging.DEBUG, logger="verdra.roots.symbionts.grafter")
    grafter = Grafter(snapshot())
    response = http(original, extra=extra + b"Content-MD5: b3JpZ2luYWw=\r\n")
    items, downloaded, batch_server = play(tmp_path, grafter, response)
    # The batch went on byte for byte (still gzip-compressed), and came back unchanged.
    assert batch_server.received[0].body == fake_roblox.batch_request(ITEMS).split(b"\r\n\r\n")[1]
    assert [item["assetId"] for item in items] == [ABOVE_UINT32, ABOVE_INT32]
    assert downloaded == served
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert f"{ABOVE_UINT32}=>file" in logged
    assert "secret" not in logged  # the signed query is never logged
    assert warnings_logged(caplog) == []


def test_a_header_about_the_original_bytes_is_dropped(tmp_path: Path) -> None:
    grafter = Grafter(snapshot())
    for folder in (tmp_path / "batch", tmp_path / "cdn"):
        folder.mkdir()
    response = http(ORIGINAL_PNG, extra=b'Content-MD5: b3JpZ2luYWw=\r\nETag: "o"\r\n')
    cdn = FakeServer(tmp_path / "cdn", {f"{PATH}0?sig=secret".encode(): response}, host=CDN)
    batch_server = FakeServer(tmp_path / "batch", {BATCH: located(ITEMS)}, host=HOST)
    pipeline = hyphae.Pipeline(request=[grafter], response=[grafter])

    async def both() -> bytes:
        async with Proxy(batch_server, pipeline) as proxy:
            client = await proxy.connect()
            await client.send(fake_roblox.batch_request(ITEMS), method=b"POST")
        async with Proxy(cdn, pipeline) as proxy:
            client = await proxy.connect()
            raw, _events = await client.send(get(f"{PATH}0?sig=secret"))
            return raw

    raw = run(both)
    head = raw.split(b"\r\n\r\n", 1)[0].lower()
    assert b"content-md5" not in head and b"etag" not in head
    assert f"content-length: {len(CONTENT.png)}".encode() in head


@pytest.mark.spec("S-21", 11)
def test_a_format_verdra_cant_make_lets_the_original_through_and_says_so(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    reasons: list[str] = []
    grafter = Grafter(snapshot(), on_unreadable=reasons.append)
    webp = b"RIFF\x10\x00\x00\x00WEBPVP8 "
    _items, downloaded, _server = play(tmp_path, grafter, http(webp))
    assert downloaded == webp
    assert warnings_logged(caplog) == [
        f"Roblox downloaded asset {ABOVE_UINT32} in a format Verdra can't make yet (WebP or RIFF), "
        "so the original shows."
    ]
    assert reasons == [f"asset {ABOVE_UINT32} in an unknown format"]


@pytest.mark.spec("S-21", 11)
def test_content_on_a_host_verdra_doesnt_decrypt_is_never_silent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    reasons: list[str] = []
    grafter = Grafter(snapshot(), on_unreadable=reasons.append)
    _items, downloaded, _server = play(tmp_path, grafter, http(ORIGINAL_PNG), host="c9.example")
    assert downloaded == ORIGINAL_PNG  # the address wasn't Verdra's to serve
    assert warnings_logged(caplog) == [
        f"Roblox was told to download asset {ABOVE_UINT32} from c9.example, which Verdra doesn't "
        "serve replacements on, so the original may show."
    ]
    assert reasons == [f"asset {ABOVE_UINT32} downloads from c9.example"]


def test_other_downloads_pass_byte_for_byte(tmp_path: Path) -> None:
    grafter = Grafter(snapshot())
    other = http(b"\x89PNG\r\n\x1a\nother content")
    cdn = FakeServer(tmp_path, {b"/somewhere-else": other}, host=CDN)
    pipeline = hyphae.Pipeline(request=[grafter], response=[grafter])

    async def fetch() -> bytes:
        async with Proxy(cdn, pipeline) as proxy:
            client = await proxy.connect()
            raw, _events = await client.send(get("/somewhere-else"))
            return raw

    assert run(fetch) == other


@pytest.mark.spec("S-21", 12)
def test_a_picture_from_the_pc_replaces_one_in_game_end_to_end(
    tmp_path: Path,
    qapp: QApplication,  # noqa: ARG001
) -> None:
    """Save a Local file replacement, Apply now, and the Player downloads the file's picture."""
    profiles = tmp_path / "profiles"
    service = grafts.Grafts(profiles, FakeSettings())
    profile = service.edit("create", "My replacements")
    (profiles / profile.name).mkdir(parents=True)
    picture = ochre.Pixels(3, 1, bytes([1, 2, 3, 255, 4, 5, 6, 255, 7, 8, 9, 255]))
    (profiles / profile.name / "wall.png").write_bytes(ochre.to_png(picture))
    service.edit(
        "add_replacement",
        profile.id,
        grafts.Original(asset_id=ABOVE_UINT32),
        grafts.Target(kind="file", value="./wall.png"),
        "Image",
    )  # Save
    assert service.publish() == 1  # Apply now
    assert service.warnings == {}
    assert service.holder.current.hosts() == {rules.ASSET_BATCH_HOST, CDN}
    ktx2 = ochre.write_ktx2(ochre.read_image(ORIGINAL_PNG))
    _items, downloaded, _server = play(tmp_path, Grafter(service.holder), http(ktx2))
    assert ochre.read_ktx2(downloaded) == picture  # the file's own pixels, as KTX2
