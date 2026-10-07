# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-21: the grafter swaps asset IDs in batches and maps the response back.

The batch shape (fact V1) is written from public descriptions until the M2 real-machine test
confirms it; every ID below is invented.
"""

from __future__ import annotations

import builtins
import gzip
import json
import logging
import socket
import zlib
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from tests.roots.test_hyphae import FakeServer, Proxy, body_of, run
from tools import fake_roblox
from verdra.roots import hyphae, rules
from verdra.roots.symbionts.grafter import Grafter
from verdra.trunk.branches import grafts

HOST = "assetdelivery.roblox.com"
BATCH = b"/v1/assets/batch"


def snapshot(swaps: dict[int, int]) -> rules.GraftSnapshot:
    return rules.GraftSnapshot(
        MappingProxyType(
            {
                (original, None): rules.Graft(original, None, "asset_id", str(target), "P", "r")
                for original, target in swaps.items()
            }
        )
    )


def holder(swaps: dict[int, int]) -> rules.SnapshotHolder:
    made = rules.SnapshotHolder()
    made.publish(snapshot(swaps))
    return made


def post(body: bytes, *, extra: bytes = b"") -> bytes:
    return (
        b"POST " + BATCH + b" HTTP/1.1\r\nHost: " + HOST.encode() + b"\r\n"
        b"Content-Type: application/json\r\n" + extra + b"Content-Length: "
        + str(len(body)).encode() + b"\r\n\r\n" + body
    )  # fmt: skip


def http(body: bytes, *, extra: bytes = b"") -> bytes:
    return (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n" + extra
        + b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
    )  # fmt: skip


#: What the client asks for: one texture to replace (number form), one decal to replace (text
#: form), and one asset that stays.
REQUEST_ITEMS = [
    {"requestId": "r-0", "assetId": 1111111, "assetType": "Image", "extra": {"keep": [1, 2]}},
    {"requestId": "r-1", "assetId": "2222222", "assetType": "Decal"},
    {"requestId": "r-2", "assetId": 3333333, "assetType": "Mesh"},
]
SWAPS = {1111111: 9999991, 2222222: 9999992}


def answer_for(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What the server answers: each item's content location, and the ID it was asked for."""
    return [
        {
            "requestId": item["requestId"],
            "location": f"https://fts.rbxcdn.com/sc0/{item['assetId']}",
            "assetTypeId": 1,
            "assetId": item["assetId"],
        }
        for item in items
    ]


@pytest.mark.spec("S-21", 1)
@pytest.mark.parametrize("encoding", ["identity", "gzip"])
def test_an_asset_id_replacement_is_asked_for_and_mapped_back(
    tmp_path: Path, encoding: str
) -> None:
    swapped = [dict(item) for item in REQUEST_ITEMS]
    swapped[0]["assetId"] = 9999991
    swapped[1]["assetId"] = "9999992"
    answer = json.dumps(answer_for(swapped)).encode()
    extra = b""
    if encoding == "gzip":
        answer, extra = gzip.compress(answer), b"Content-Encoding: gzip\r\n"
    server = FakeServer(tmp_path, {BATCH: http(answer, extra=extra)}, host=HOST)
    grafter = Grafter(holder(SWAPS))
    pipeline = hyphae.Pipeline(request=[grafter], response=[grafter])

    async def body() -> list[object]:
        async with Proxy(server, pipeline) as proxy:
            client = await proxy.connect()
            _raw, events = await client.send(
                post(json.dumps(REQUEST_ITEMS).encode()), method=b"POST"
            )
            return events

    events = run(body)
    # Roblox's server was asked for the targets; every other field of each item is kept.
    assert json.loads(server.received[0].body) == swapped
    # The client gets the content for the items it asked for, under the original IDs.
    received = json.loads(body_of(events))
    expected = answer_for(swapped)
    expected[0]["assetId"] = 1111111
    expected[1]["assetId"] = "2222222"
    assert received == expected
    assert received[2] == answer_for(REQUEST_ITEMS)[2]  # the item that stays is unchanged


@pytest.mark.spec("S-21", 1)
def test_real_size_ids_are_swapped_and_mapped_back_exactly(tmp_path: Path) -> None:
    items = [
        {"requestId": "big-0", "assetId": ABOVE_UINT32, "assetType": "Image"},
        {"requestId": "big-1", "assetId": str(ABOVE_INT32), "assetType": "Decal"},
    ]
    swapped = [{**items[0], "assetId": ABOVE_INT32}, {**items[1], "assetId": str(ABOVE_UINT32)}]
    server = FakeServer(
        tmp_path, {BATCH: http(json.dumps(answer_for(swapped)).encode())}, host=HOST
    )
    grafter = Grafter(holder({ABOVE_UINT32: ABOVE_INT32, ABOVE_INT32: ABOVE_UINT32}))
    pipeline = hyphae.Pipeline(request=[grafter], response=[grafter])

    async def body() -> list[object]:
        async with Proxy(server, pipeline) as proxy:
            client = await proxy.connect()
            _raw, events = await client.send(post(json.dumps(items).encode()), method=b"POST")
            return events

    events = run(body)
    assert json.loads(server.received[0].body) == swapped
    received = json.loads(body_of(events))
    assert [item["assetId"] for item in received] == [ABOVE_UINT32, str(ABOVE_INT32)]


@pytest.mark.spec("S-21", 6)
@pytest.mark.parametrize(
    ("request_body", "response_body"),
    [
        (b"not json", b"[]"),
        (b'{"assetId": 1111111}', b"[]"),  # an object, not an array
        (b'[1111111, "x"]', b"[]"),  # an array of non-objects
        (json.dumps(REQUEST_ITEMS).encode(), b'{"errors": []}'),  # a response it can't map back
        (json.dumps(REQUEST_ITEMS).encode(), b"\xff\xfe broken"),
    ],
)
def test_what_the_grafter_doesnt_recognize_passes_through(
    tmp_path: Path, request_body: bytes, response_body: bytes
) -> None:
    raw_answer = http(response_body)
    server = FakeServer(tmp_path, {BATCH: raw_answer}, host=HOST)
    grafter = Grafter(holder(SWAPS))
    pipeline = hyphae.Pipeline(request=[grafter], response=[grafter])

    async def body() -> bytes:
        async with Proxy(server, pipeline) as proxy:
            client = await proxy.connect()
            raw, _events = await client.send(post(request_body), method=b"POST")
            return raw

    raw = run(body)
    assert raw == raw_answer  # byte-identical
    if not request_body.startswith(b"["):
        assert server.received[0].body == request_body
    assert grafter._pending == {}  # noqa: SLF001 - nothing left waiting


@pytest.mark.spec("S-21", 6)
def test_other_endpoints_pass_through() -> None:
    grafter = Grafter(holder(SWAPS))
    items = json.dumps(REQUEST_ITEMS).encode()
    for host, method, target in (
        ("apis.roblox.com", b"POST", BATCH),
        (HOST, b"GET", BATCH),
        (HOST, b"POST", b"/v1/asset/"),
    ):
        other = hyphae.Request(host, method, target, (), items)
        assert not grafter.wants_request_body(other)
        assert grafter.on_request(other) is None
    # Spellings of the batch path count as the batch path.
    spelled = hyphae.Request(HOST, b"POST", b"//v1/./assets/batch?x=1", (), items)
    assert grafter.on_request(spelled) is not None


def test_nothing_is_asked_for_while_no_asset_id_is_replaced() -> None:
    grafter = Grafter(rules.SnapshotHolder())
    request = hyphae.Request(HOST, b"POST", BATCH, (), json.dumps(REQUEST_ITEMS).encode())
    assert not grafter.wants_request_body(request)
    assert grafter.on_request(request) is None


@pytest.mark.spec("S-21", 7)
def test_the_proxy_hook_does_no_disk_or_network_work(monkeypatch: pytest.MonkeyPatch) -> None:
    grafter = Grafter(holder(SWAPS))

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("disk or network access in the proxy hook")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    request = hyphae.Request(HOST, b"POST", BATCH, (), json.dumps(REQUEST_ITEMS).encode())
    assert grafter.wants_request_body(request)
    changed = grafter.on_request(request)
    assert changed is not None
    response = hyphae.Response(200, (), b"OK", json.dumps(answer_for(REQUEST_ITEMS)).encode())
    assert grafter.wants_response_body(changed, response)
    assert grafter.on_response(changed, response) is not None


@pytest.mark.spec("S-21", 8)
def test_a_snapshot_published_mid_batch_doesnt_change_that_batch() -> None:
    held = holder(SWAPS)
    grafter = Grafter(held)
    request = hyphae.Request(HOST, b"POST", BATCH, (), json.dumps(REQUEST_ITEMS).encode())
    changed = grafter.on_request(request)
    assert changed is not None
    held.publish(snapshot({3333333: 7777777}))  # a new snapshot while the batch is out
    sent = json.loads(changed.body or b"")
    response = hyphae.Response(200, (), b"OK", json.dumps(answer_for(sent)).encode())
    mapped = grafter.on_response(changed, response)
    assert mapped is not None
    ids = [item["assetId"] for item in json.loads(mapped.body or b"")]
    assert ids == [1111111, "2222222", 3333333]  # mapped with the snapshot the batch started with
    # The next batch uses the new snapshot.
    following = grafter.on_request(request)
    assert following is not None
    assert [i["assetId"] for i in json.loads(following.body or b"")] == [
        1111111,
        "2222222",
        7777777,
    ]


def test_forgotten_batches_are_bounded() -> None:
    grafter = Grafter(holder(SWAPS))
    request = hyphae.Request(HOST, b"POST", BATCH, (), json.dumps(REQUEST_ITEMS).encode())
    kept = [grafter.on_request(request) for _ in range(1100)]  # responses that never came
    assert len(grafter._pending) == 1024  # noqa: SLF001
    assert all(k is not None for k in kept)


# --- What the grafter logs, and the single-asset routes (first swap test, 5 October 2026) --------


def debug_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "verdra.roots.symbionts.grafter"]


def warnings_logged(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "verdra.roots.symbionts.grafter" and r.levelno == logging.WARNING
    ]


def test_every_batch_is_logged_even_when_nothing_matches(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The first swap test's log had no grafter line at all: a batch with no match said nothing."""
    caplog.set_level(logging.DEBUG, logger="verdra.roots.symbionts.grafter")
    grafter = Grafter(holder({ABOVE_UINT32: ABOVE_INT32}))
    items = [
        {"requestId": "a", "assetId": 1111111, "assetType": "Image"},
        {"requestId": "b", "assetId": "2222222", "assetType": "Decal"},
    ]
    request = hyphae.Request(HOST, b"POST", BATCH, (), json.dumps(items).encode())
    assert grafter.on_request(request) is None
    assert debug_lines(caplog) == [
        "Asset batch (not compressed): 0 of 2 items replaced (asked for: 1111111, 2222222; "
        "item fields: requestId, assetId, assetType)"
    ]


def test_a_match_names_both_ids_and_unread_batches_say_why(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="verdra.roots.symbionts.grafter")
    reasons: list[str] = []
    grafter = Grafter(holder({ABOVE_UINT32: ABOVE_INT32}), on_unreadable=reasons.append)
    items = [
        {"requestId": "a", "assetId": ABOVE_UINT32},
        {"assetId": ABOVE_UINT32},  # no request ID: can't be mapped back, so it's left alone
        {"requestId": "c", "id": 5},  # another shape
    ]
    body = json.dumps(items).encode()
    assert grafter.on_request(hyphae.Request(HOST, b"POST", BATCH, (), body, coding="gzip"))
    unread = hyphae.Request(HOST, b"POST", BATCH, ())  # over the buffer limit: no body
    assert grafter.on_request(unread) is None
    assert grafter.on_request(hyphae.Request(HOST, b"POST", BATCH, (), b"{}")) is None
    assert debug_lines(caplog) == [
        f"Asset batch (gzip-compressed): 1 of 3 items replaced, 1 without a request ID left alone "
        f"(asked for: {ABOVE_UINT32}->{ABOVE_INT32}, {ABOVE_UINT32}, ?; "
        "item fields: requestId, assetId, id)",
        "An asset batch request couldn't be read (over 64 MB), so replacements may not apply "
        "to it.",
        "An asset batch request couldn't be read (not a JSON array of objects), so replacements "
        "may not apply to it.",
    ]
    assert warnings_logged(caplog) == debug_lines(caplog)[1:]
    assert reasons == ["over 64 MB", "not a JSON array of objects"]


def test_the_log_names_fields_and_asset_ids_never_other_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="verdra.roots.symbionts.grafter")
    grafter = Grafter(holder({ABOVE_UINT32: ABOVE_INT32}))
    items = [{"requestId": "secret-request", "assetId": ABOVE_UINT32, "token": "secret-token"}]
    asked = grafter.on_request(hyphae.Request(HOST, b"POST", BATCH, (), json.dumps(items).encode()))
    assert asked is not None
    location = "https://fts.rbxcdn.com/sc1/abc?__token__=exp=1~hmac=secret-signature"
    answer = [{"requestId": "secret-request", "location": location, "assetId": ABOVE_INT32}]
    response = hyphae.Response(200, (), body=json.dumps(answer).encode())
    assert grafter.on_response(asked, response) is not None
    logged = "\n".join(debug_lines(caplog))
    assert "Asset batch response: 1 of 1 replaced items found by request ID" in logged
    assert "item fields: requestId, location, assetId" in logged
    assert "secret" not in logged


def test_a_response_without_asset_ids_stays_byte_identical() -> None:
    grafter = Grafter(holder({ABOVE_UINT32: ABOVE_INT32}))
    items = [{"requestId": "a", "assetId": ABOVE_UINT32}]
    asked = grafter.on_request(hyphae.Request(HOST, b"POST", BATCH, (), json.dumps(items).encode()))
    assert asked is not None
    body = b'[ {"requestId": "a",   "location": "https://fts.rbxcdn.com/sc1/x"} ]'
    assert grafter.on_response(asked, hyphae.Response(200, (), body=body)) is None


SINGLE_ROUTES = [
    (
        f"/v1/asset/?id={ABOVE_UINT32}&permissionContext=ignoreUniverse",
        f"/v1/asset/?id={ABOVE_INT32}&permissionContext=ignoreUniverse",
    ),
    (f"/v1/asset?ID={ABOVE_UINT32}", f"/v1/asset?ID={ABOVE_INT32}"),
    (f"/v2/asset/?x=1&id={ABOVE_UINT32}", f"/v2/asset/?x=1&id={ABOVE_INT32}"),
    (f"/v1/assetId/{ABOVE_UINT32}", f"/v1/assetId/{ABOVE_INT32}"),
    (f"/v2/assetId/{ABOVE_UINT32}/version/3", f"/v2/assetId/{ABOVE_INT32}/version/3"),
]


@pytest.mark.spec("S-21", 1)
@pytest.mark.parametrize(("asked", "sent"), SINGLE_ROUTES)
def test_a_single_asset_request_asks_for_the_target(tmp_path: Path, asked: str, sent: str) -> None:
    """Seen in the first swap test: GET /v1/asset/?id=… alongside the batches."""
    server = FakeServer(tmp_path, {sent.encode(): http(b"content")}, host=HOST)
    grafter = Grafter(holder({ABOVE_UINT32: ABOVE_INT32}))
    pipeline = hyphae.Pipeline(request=[grafter], response=[grafter])
    get = (f"GET {asked} HTTP/1.1\r\nHost: {HOST}\r\n\r\n").encode()

    async def body() -> list[object]:
        async with Proxy(server, pipeline) as proxy:
            client = await proxy.connect()
            _raw, events = await client.send(get, method=b"GET")
            return events

    assert body_of(run(body)) == b"content"
    assert [r.target for r in server.received] == [sent.encode()]


def test_single_asset_requests_without_a_replacement_or_id_pass_unchanged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="verdra.roots.symbionts.grafter")
    grafter = Grafter(holder({ABOVE_UINT32: ABOVE_INT32}))
    for target in (b"/v1/asset/?id=1111111", b"/v1/asset/?assetName=x", b"/v1/assetId/1/version/x"):
        assert grafter.on_request(hyphae.Request(HOST, b"GET", target, ())) is None
    assert debug_lines(caplog)[:2] == [
        "Asset request for 1111111: no replacement",
        "An asset request named no asset ID it could read; passed on unchanged",
    ]
    for host, method, target in (
        ("apis.roblox.com", b"GET", f"/v1/asset/?id={ABOVE_UINT32}".encode()),
        (HOST, b"POST", f"/v1/asset/?id={ABOVE_UINT32}".encode()),
        (HOST, b"GET", f"/v1/assets/{ABOVE_UINT32}".encode()),
    ):
        assert grafter.on_request(hyphae.Request(host, method, target, ())) is None
    nothing = Grafter(holder({}))
    assert nothing.on_request(hyphae.Request(HOST, b"GET", b"/v1/asset/?id=5", ())) is None


# --- Compressed batches (second swap test, 7 October 2026) ---------------------------------------
# The Roblox Player sent 14 of its 15 asset batches gzip-compressed, and the grafter passed every
# compressed one on unread. roots/hyphae now decodes them (RFC 9110 section 8.4), within plan
# 10.7's limits, and the fake Roblox server sends compressed batches by default.

#: A stand-in for the maintainer's replacement (above an unsigned 32-bit int, like theirs).
REPLACEMENT = 2**33 + 11
ITEMS = [
    {"requestId": "0", "assetId": ABOVE_UINT32, "assetType": "Image", "xcachesplit": 1},
    {"requestId": "1", "assetId": 1111111, "assetType": "Image", "xcachesplit": 1},
]


def batch_exchange(
    tmp_path: Path,
    raw_request: bytes,
    swaps: dict[int, int],
    *,
    answer: bytes | None = None,
    reasons: list[str] | None = None,
    max_body: int = hyphae.MAX_BUFFERED_BODY,
) -> tuple[FakeServer, bytes]:
    """Send one raw batch request through the proxy; return the server and the raw answer."""
    raw_answer = http(answer if answer is not None else b"[]")
    server = FakeServer(tmp_path, {BATCH: raw_answer}, host=HOST)
    grafter = Grafter(holder(swaps), on_unreadable=None if reasons is None else reasons.append)
    pipeline = hyphae.Pipeline(request=[grafter], response=[grafter])

    async def body() -> bytes:
        async with Proxy(server, pipeline, max_body=max_body) as proxy:
            client = await proxy.connect()
            raw, _events = await client.send(raw_request, method=b"POST")
            return raw

    return server, run(body)


def header(received: object, name: bytes) -> bytes | None:
    headers = received.headers  # type: ignore[attr-defined]
    return next((v for n, v in headers if n.lower() == name), None)


@pytest.mark.spec("S-21", 1)
@pytest.mark.parametrize("encoding", ["gzip", "deflate", "zstd"])
def test_a_compressed_batch_asks_for_the_replacement(
    tmp_path: Path, encoding: fake_roblox.BatchEncoding, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="verdra.roots.symbionts.grafter")
    raw = fake_roblox.batch_request(ITEMS, encoding=encoding)
    server, _answer = batch_exchange(tmp_path, raw, {ABOVE_UINT32: REPLACEMENT})
    sent = server.received[0]
    # Sent on uncompressed (the Player itself sent one batch that way, and the server answered
    # it), with a correct length and nothing else changed.
    assert json.loads(sent.body) == [{**ITEMS[0], "assetId": REPLACEMENT}, ITEMS[1]]
    assert header(sent, b"content-encoding") is None
    assert header(sent, b"content-length") == str(len(sent.body)).encode()
    assert header(sent, b"content-type") == b"application/json"
    assert debug_lines(caplog)[:1] == [
        f"Asset batch ({encoding}-compressed): 1 of 2 items replaced (asked for: "
        f"{ABOVE_UINT32}->{REPLACEMENT}, 1111111; item fields: requestId, assetId, assetType, "
        "xcachesplit)"
    ]


@pytest.mark.spec("S-21", 6)
@pytest.mark.parametrize("encoding", ["gzip", "deflate", "zstd", "identity"])
def test_a_compressed_batch_without_a_match_passes_byte_for_byte(
    tmp_path: Path, encoding: fake_roblox.BatchEncoding
) -> None:
    raw = fake_roblox.batch_request(ITEMS, encoding=encoding)
    reasons: list[str] = []
    server, _answer = batch_exchange(tmp_path, raw, {ABOVE_INT32: REPLACEMENT}, reasons=reasons)
    head, _, body = raw.partition(b"\r\n\r\n")
    sent = server.received[0]
    assert sent.body == body
    sent_head = b"\r\n".join(n + b": " + v for n, v in sent.headers)
    assert sent_head.split(b"\r\n") == head.split(b"\r\n")[1:]  # same headers, same order
    assert reasons == []


def raw_batch(body: bytes, encoding: bytes) -> bytes:
    return post(body, extra=b"Content-Encoding: " + encoding + b"\r\n")


BOMB = gzip.compress(b"[" + b" " * 2_000_000 + b"]")  # a valid batch, 2 MB from 2 KB: over 100:1


@pytest.mark.spec("S-21", 6)
@pytest.mark.parametrize(
    ("body", "encoding", "reason"),
    [
        (b"\x1f\x8b\x08\x00broken", b"gzip", "damaged gzip data"),
        (gzip.compress(json.dumps(ITEMS).encode())[:-12], b"gzip", "damaged gzip data"),
        (b"not deflate", b"deflate", "damaged deflate data"),
        (b"(\xb5/\xfd broken", b"zstd", "damaged zstd data"),
        (BOMB, b"gzip", "gzip data that would be too large once decompressed"),
        (json.dumps(ITEMS).encode(), b"br", "compressed as br, which Verdra can't read"),
    ],
)
def test_an_unreadable_batch_passes_unchanged_and_says_so(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    body: bytes,
    encoding: bytes,
    reason: str,
) -> None:
    """Never silent while a replacement is active: a warning and Degraded (S-21, S-14)."""
    caplog.set_level(logging.DEBUG, logger="verdra.roots.symbionts.grafter")
    reasons: list[str] = []
    server, answer = batch_exchange(
        tmp_path, raw_batch(body, encoding), {ABOVE_UINT32: REPLACEMENT}, reasons=reasons
    )
    assert server.received[0].body == body  # passed on byte for byte
    assert answer == http(b"[]")
    assert reasons == [reason]
    assert warnings_logged(caplog) == [
        f"An asset batch request couldn't be read ({reason}), so replacements may not apply to it."
    ]


def test_a_bomb_is_refused_without_decoding_it_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan 10.7: decoding stops at the limit; the bomb's full size is never in memory."""
    bomb = gzip.compress(b"\0" * (hyphae.MAX_BUFFERED_BODY * 4))
    sizes: list[int] = []
    real = zlib.decompressobj

    class Watched:
        def __init__(self, wbits: int) -> None:
            self.inner = real(wbits)

        def decompress(self, data: bytes, max_length: int = 0) -> bytes:
            out = self.inner.decompress(data, max_length)
            sizes.append(len(out))
            return out

        def __getattr__(self, name: str) -> object:
            return getattr(self.inner, name)

    monkeypatch.setattr(zlib, "decompressobj", Watched)
    decoded = hyphae.decode(((b"Content-Encoding", b"gzip"),), bomb)
    assert decoded.body is None
    assert decoded.problem == "gzip data that would be too large once decompressed"
    assert max(sizes) <= hyphae.MAX_RATIO * len(bomb) + 1


def test_unreadable_batches_say_nothing_while_no_replacement_is_active(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    reasons: list[str] = []
    raw = raw_batch(b"broken", b"gzip")
    server, _answer = batch_exchange(tmp_path, raw, {}, reasons=reasons)
    assert server.received[0].body == b"broken"
    assert reasons == []
    assert warnings_logged(caplog) == []


@pytest.mark.spec("S-21", 1)
def test_a_compressed_response_is_mapped_back_and_an_unreadable_one_says_so(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    swapped = [{**ITEMS[0], "assetId": REPLACEMENT}, ITEMS[1]]
    answer = json.dumps(answer_for(swapped)).encode()
    for body, extra, mapped in (
        (gzip.compress(answer), b"Content-Encoding: gzip\r\n", True),
        (b"\x1f\x8bbroken", b"Content-Encoding: gzip\r\n", False),
    ):
        reasons: list[str] = []
        raw_answer = http(body, extra=extra)
        server = FakeServer(tmp_path, {BATCH: raw_answer}, host=HOST)
        grafter = Grafter(holder({ABOVE_UINT32: REPLACEMENT}), on_unreadable=reasons.append)
        pipeline = hyphae.Pipeline(request=[grafter], response=[grafter])

        async def run_one(
            server: FakeServer = server, pipeline: hyphae.Pipeline = pipeline
        ) -> tuple[bytes, list[object]]:
            async with Proxy(server, pipeline) as proxy:
                client = await proxy.connect()
                return await client.send(fake_roblox.batch_request(ITEMS), method=b"POST")

        raw, events = run(run_one)
        if mapped:
            assert [i["assetId"] for i in json.loads(body_of(events))] == [ABOVE_UINT32, 1111111]
            assert reasons == []
        else:
            assert raw == raw_answer  # byte for byte
            assert reasons == ["damaged gzip data"]
            assert grafter._pending == {}  # noqa: SLF001


class FakeSettings:
    """The one setting the replacement service reads and writes."""

    def __init__(self) -> None:
        self.values: dict[str, Any] = {"replacements.profile_order": []}

    def value(self, key: str) -> Any:
        return self.values[key]

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value


@pytest.mark.spec("S-21", 1)
def test_the_maintainers_scenario_end_to_end(tmp_path: Path, qapp: object) -> None:  # noqa: ARG001
    """Save (15553230204 → a replacement) → Apply now → the Player asks in a gzip batch → the
    content it downloads is the replacement's.

    The replacement here is a stand-in of the same size as the maintainer's own.
    """
    settings = FakeSettings()
    service = grafts.Grafts(tmp_path / "profiles", settings)
    profile = service.edit("create", "My replacements")
    service.edit(
        "add_replacement",
        profile.id,
        grafts.Original(asset_id=ABOVE_UINT32),
        grafts.Target(kind="asset_id", value=str(REPLACEMENT)),
    )  # Save
    assert service.publish() == 1  # Apply now publishes the snapshot the proxy reads

    def location(asset_id: int) -> str:
        return f"/sc1/content-of-{asset_id}"

    def answer(items: list[dict[str, Any]]) -> bytes:
        located = [
            {"requestId": i["requestId"], "location": f"https://fts.rbxcdn.com{location(i['assetId'])}",
             "assetTypeId": 1, "assetId": i["assetId"]}
            for i in items
        ]  # fmt: skip
        return gzip.compress(json.dumps(located).encode())

    asked = [{"requestId": "0", "assetId": ABOVE_UINT32, "assetType": "Image"}]
    upstream_view = [{**asked[0], "assetId": REPLACEMENT}]
    server = FakeServer(
        tmp_path,
        {
            BATCH: http(answer(upstream_view), extra=b"Content-Encoding: gzip\r\n"),
            location(REPLACEMENT).encode(): http(b"the replacement's picture"),
            location(ABOVE_UINT32).encode(): http(b"the original picture"),
        },
        host=HOST,
    )
    reasons: list[str] = []
    grafter = Grafter(service.holder, on_unreadable=reasons.append)
    pipeline = hyphae.Pipeline(request=[grafter], response=[grafter])

    async def player() -> tuple[list[dict[str, Any]], bytes]:
        async with Proxy(server, pipeline) as proxy:
            client = await proxy.connect()
            _raw, events = await client.send(fake_roblox.batch_request(asked), method=b"POST")
            items = json.loads(body_of(events))
            path = items[0]["location"].removeprefix("https://fts.rbxcdn.com").encode()
            download = await proxy.connect()
            _raw, content = await download.send(
                b"GET " + path + b" HTTP/1.1\r\nHost: " + HOST.encode() + b"\r\n\r\n"
            )
            return items, body_of(content)

    items, picture = run(player)
    assert json.loads(server.received[0].body) == upstream_view  # Roblox was asked for it
    assert items[0]["requestId"] == "0" and items[0]["assetId"] == ABOVE_UINT32  # as asked
    assert picture == b"the replacement's picture"
    assert reasons == []
