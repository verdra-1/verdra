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
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from tests.roots.test_hyphae import FakeServer, Proxy, body_of, run
from verdra.roots import hyphae, rules
from verdra.roots.symbionts.grafter import Grafter

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
def test_a_compressed_request_and_other_endpoints_pass_through(tmp_path: Path) -> None:
    grafter = Grafter(holder(SWAPS))
    items = json.dumps(REQUEST_ITEMS).encode()
    gzipped = hyphae.Request(HOST, b"POST", BATCH, ((b"Content-Encoding", b"gzip"),), items)
    assert grafter.on_request(gzipped) is None
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
        "Asset batch: 0 of 2 items replaced (asked for: 1111111, 2222222; "
        "item fields: requestId, assetId, assetType)"
    ]


def test_a_match_names_both_ids_and_skipped_batches_say_why(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="verdra.roots.symbionts.grafter")
    grafter = Grafter(holder({ABOVE_UINT32: ABOVE_INT32}))
    items = [
        {"requestId": "a", "assetId": ABOVE_UINT32},
        {"assetId": ABOVE_UINT32},  # no request ID: can't be mapped back, so it's left alone
        {"requestId": "c", "id": 5},  # another shape
    ]
    assert grafter.on_request(hyphae.Request(HOST, b"POST", BATCH, (), json.dumps(items).encode()))
    gzipped = hyphae.Request(HOST, b"POST", BATCH, ((b"Content-Encoding", b"gzip"),), b"\x1f\x8b")
    assert grafter.on_request(gzipped) is None
    unread = hyphae.Request(HOST, b"POST", BATCH, ())  # over the buffer limit: no body
    assert grafter.on_request(unread) is None
    assert debug_lines(caplog) == [
        f"Asset batch: 1 of 3 items replaced, 1 without a request ID left alone (asked for: "
        f"{ABOVE_UINT32}->{ABOVE_INT32}, {ABOVE_UINT32}, ?; item fields: requestId, assetId, id)",
        "An asset batch request was compressed (gzip); passed on unchanged",
        "An asset batch request was too large to read; passed on unchanged",
    ]


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
