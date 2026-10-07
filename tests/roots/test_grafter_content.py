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
import threading
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from tests.roots.test_grafter import BATCH, HOST, FakeSettings, http, warnings_logged
from tests.roots.test_hyphae import FakeServer, Proxy, body_of, run
from tools import fake_roblox
from verdra.bark import rain
from verdra.roots import hyphae, rules
from verdra.roots.symbionts.grafter import Grafter
from verdra.strata import clay, ochre
from verdra.trunk import tendrils
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
        folder.mkdir(parents=True, exist_ok=True)

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


# --- Links and Remove (S-21, step 3b) -----------------------------------------------------------


def service_with(tmp_path: Path, target: grafts.Target, **kwargs: Any) -> grafts.Grafts:
    profiles = tmp_path / "profiles"
    service = grafts.Grafts(profiles, FakeSettings(), **kwargs)
    profile = service.edit("create", "My replacements")
    service.edit(
        "add_replacement", profile.id, grafts.Original(asset_id=ABOVE_UINT32), target, "Image"
    )
    return service


@pytest.mark.spec("S-21", 16)
def test_remove_serves_a_transparent_picture_in_the_cdns_format(
    tmp_path: Path,
    qapp: QApplication,  # noqa: ARG001
) -> None:
    service = service_with(tmp_path, grafts.Target(kind="remove"))
    assert service.publish() == 1
    assert service.warnings == {}
    for name, original, read in (
        ("png", ORIGINAL_PNG, ochre.read_image),
        ("ktx2", ochre.write_ktx2(ochre.read_image(ORIGINAL_PNG)), ochre.read_ktx2),
    ):
        _items, downloaded, _server = play(tmp_path / name, Grafter(service.holder), http(original))
        assert read(downloaded) == ochre.Pixels(1, 1, b"\0\0\0\0")  # fully transparent


@pytest.mark.spec("S-21", 16)
def test_a_link_is_downloaded_once_then_served(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,  # noqa: ARG001
) -> None:
    picture = ochre.Pixels(2, 1, bytes([9, 8, 7, 255, 6, 5, 4, 255]))
    fetched: list[str] = []

    def fetch(url: str, folder: Path, **_kwargs: object) -> bytes:
        fetched.append(url)
        data = ochre.to_png(picture)
        rain.cache_path(url, folder).parent.mkdir(parents=True, exist_ok=True)
        rain.cache_path(url, folder).write_bytes(data)
        return data

    monkeypatch.setattr(rain, "fetch", fetch)
    link = "https://pictures.example/wall.png"
    service = service_with(tmp_path, grafts.Target(kind="url", value=link))
    assert service.publish() == 1
    assert service.publish() == 1  # the second Apply now uses the cached download
    assert fetched == [link]
    assert service.holder.current.content[ABOVE_UINT32].source == "url"
    _items, downloaded, _server = play(tmp_path, Grafter(service.holder), http(ORIGINAL_PNG))
    assert ochre.read_image(downloaded) == picture


@pytest.mark.spec("S-21", 16)
def test_a_link_downloads_on_a_worker_and_applies_when_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qtbot: QtBot
) -> None:
    gate = threading.Event()

    def fetch(url: str, folder: Path, **_kwargs: object) -> bytes:
        gate.wait(5)
        data = ochre.to_png(ochre.Pixels(1, 1, b"\1\2\3\xff"))
        rain.cache_path(url, folder).parent.mkdir(parents=True, exist_ok=True)
        rain.cache_path(url, folder).write_bytes(data)
        return data

    monkeypatch.setattr(rain, "fetch", fetch)
    pool = tendrils.Tendrils(workers=1)
    service = service_with(
        tmp_path, grafts.Target(kind="url", value="https://pictures.example/a.png"), pool=pool
    )
    try:
        service.publish()
        [reason] = service.warnings.values()
        assert reason == "Downloading this replacement. It applies as soon as it's ready."
        assert ABOVE_UINT32 not in service.holder.current.content  # the original passes for now
        with qtbot.waitSignal(service.changed, timeout=5000):
            gate.set()
        assert service.warnings == {}
        assert ABOVE_UINT32 in service.holder.current.content  # published without Apply now
    finally:
        pool.shutdown(grace=1)


@pytest.mark.spec("S-21", 16)
def test_a_failed_download_says_why_and_apply_now_tries_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,  # noqa: ARG001
) -> None:
    answers = [rain.RainError("the server answered 404")]

    def fetch(url: str, folder: Path, **_kwargs: object) -> bytes:
        if answers:
            raise answers.pop()
        data = ochre.to_png(ochre.Pixels(1, 1, b"\1\2\3\xff"))
        rain.cache_path(url, folder).parent.mkdir(parents=True, exist_ok=True)
        rain.cache_path(url, folder).write_bytes(data)
        return data

    monkeypatch.setattr(rain, "fetch", fetch)
    service = service_with(
        tmp_path, grafts.Target(kind="url", value="https://pictures.example/a.png")
    )
    service.publish()
    assert list(service.warnings.values()) == [
        "The replacement from pictures.example couldn't be downloaded: the server answered 404."
    ]
    service.publish()  # Apply now again
    assert service.warnings == {}
    assert ABOVE_UINT32 in service.holder.current.content


# --- Meshes (S-21, step 3c) ------------------------------------------------------------------

TRIANGLE = clay.Mesh(
    (
        clay.Vertex((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0)),
        clay.Vertex((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0)),
        clay.Vertex((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0)),
    ),
    ((0, 1, 2),),
)
#: What the CDN sends for a mesh: a FileMesh of some version (invented content).
ORIGINAL_MESH = clay.write_filemesh(clay.Mesh((), ()))


@pytest.mark.spec("S-21", 17)
@pytest.mark.parametrize("name", ["wall.mesh", "wall.obj"])
def test_a_mesh_from_the_pc_replaces_one_in_game(
    tmp_path: Path,
    qapp: QApplication,  # noqa: ARG001
    name: str,
) -> None:
    profiles = tmp_path / "profiles"
    service = grafts.Grafts(profiles, FakeSettings())
    profile = service.edit("create", "My replacements")
    (profiles / profile.name).mkdir(parents=True)
    data = clay.write_obj(TRIANGLE) if name.endswith(".obj") else clay.write_filemesh(TRIANGLE)
    (profiles / profile.name / name).write_bytes(data)
    service.edit(
        "add_replacement",
        profile.id,
        grafts.Original(asset_id=ABOVE_UINT32),
        grafts.Target(kind="file", value=f"./{name}"),
        "Mesh",
    )
    service.publish()
    assert service.warnings == {}
    _items, downloaded, _server = play(tmp_path, Grafter(service.holder), http(ORIGINAL_MESH))
    assert downloaded.startswith(b"version 2.00\n")
    served = clay.read_mesh(downloaded)
    assert served.faces == TRIANGLE.faces
    assert [v.position for v in served.vertices] == [v.position for v in TRIANGLE.vertices]


@pytest.mark.spec("S-21", 17)
def test_remove_serves_an_empty_mesh_for_a_mesh(
    tmp_path: Path,
    qapp: QApplication,  # noqa: ARG001
) -> None:
    service = service_with(tmp_path, grafts.Target(kind="remove"))
    service.publish()
    _items, downloaded, _server = play(tmp_path, Grafter(service.holder), http(ORIGINAL_MESH))
    assert clay.read_mesh(downloaded) == clay.Mesh((), ())


@pytest.mark.spec("S-21", 17)
@pytest.mark.parametrize(
    ("content", "download", "kind"),
    [
        (CONTENT, ORIGINAL_MESH, "mesh"),  # a picture replacing a mesh
        (rules.Content(b"", b"", "file", ORIGINAL_MESH), ORIGINAL_PNG, "picture"),
    ],
    ids=["picture-for-mesh", "mesh-for-picture"],
)
def test_a_replacement_of_another_type_lets_the_original_through_and_says_so(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    content: rules.Content,
    download: bytes,
    kind: str,
) -> None:
    reasons: list[str] = []
    grafter = Grafter(snapshot({ABOVE_UINT32: content}), on_unreadable=reasons.append)
    _items, downloaded, _server = play(tmp_path, grafter, http(download))
    assert downloaded == download
    assert warnings_logged(caplog) == [
        f"Roblox downloaded asset {ABOVE_UINT32} as a {kind}, but its replacement is another "
        "type of asset, so the original shows."
    ]
    assert reasons == [f"asset {ABOVE_UINT32} replaced by another type"]
