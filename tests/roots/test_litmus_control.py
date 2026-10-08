# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The control experiment (roots/litmus, source runs only): the donor's real bytes, sent to the
original's address.

Plan 16.2 (8 October 2026), hypothesis H4: does Roblox draw bytes that don't match the address it
asked for? `ControlSwap` asks the batch for the donor beside the original, hides that extra
answer from Roblox, and sends the original's download to the donor's address, so Roblox gets the
CDN's real answer for the donor. Every ID and address is invented, except the public Toolbox
image IDs in `tests.ids`.
"""

from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from tests.roots.test_grafter import BATCH, HOST, http
from tests.roots.test_hyphae import FakeServer, Proxy, body_of, run
from tools import fake_roblox
from verdra.roots import hyphae, litmus, rules
from verdra.roots.symbionts.grafter import Grafter
from verdra.trunk.sapwood import cli

CDN = rules.ASSET_CONTENT_HOST
ORIGINAL, DONOR = ABOVE_UINT32, ABOVE_INT32
ORIGINAL_AT = "/sc3/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa?encoding=zstd&version=1&Signature=one"
DONOR_AT = "/sc2/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb?encoding=zstd&version=1&Signature=two"


def batch_answer(donor_host: str) -> bytes:
    answer = [
        {"requestId": "r1", "location": f"https://{CDN}{ORIGINAL_AT}", "assetTypeId": 1},
        {"requestId": "r2", "location": f"https://{CDN}/sc1/cccc?x=1", "assetTypeId": 1},
        {"requestId": "r1-verdra-donor", "location": f"https://{donor_host}{DONOR_AT}",
         "assetTypeId": 1},
    ]  # fmt: skip
    return http(gzip.compress(json.dumps(answer).encode()), extra=b"Content-Encoding: gzip\r\n")


def download(body: bytes, mark: bytes) -> bytes:
    return (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\nX-Which: " + mark + b"\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
    )


def control_run(
    tmp_path: Path, donor_host: str = CDN
) -> tuple[list[dict[str, Any]], list[object], FakeServer, litmus.ControlSwap]:
    items = [
        {"assetId": ORIGINAL, "assetType": "Image", "requestId": "r1"},
        {"assetId": 1234567, "assetType": "Image", "requestId": "r2"},
    ]
    control = litmus.ControlSwap(ORIGINAL, DONOR)
    grafter = Grafter(rules.SnapshotHolder(), leave=frozenset({ORIGINAL}))
    pipeline = hyphae.Pipeline(request=[control, grafter], response=[control, grafter])
    for folder in (tmp_path / "batch", tmp_path / "cdn"):
        folder.mkdir(parents=True, exist_ok=True)
    batch_server = FakeServer(tmp_path / "batch", {BATCH: batch_answer(donor_host)}, host=HOST)
    cdn_server = FakeServer(
        tmp_path / "cdn",
        {
            ORIGINAL_AT.encode(): download(b"original bytes", b"original"),
            DONOR_AT.encode(): download(b"donor bytes", b"donor"),
        },
        host=CDN,
    )

    async def batch() -> list[object]:
        async with Proxy(batch_server, pipeline) as proxy:
            client = await proxy.connect()
            _raw, events = await client.send(fake_roblox.batch_request(items), method=b"POST")
            return events

    async def fetch() -> list[object]:
        async with Proxy(cdn_server, pipeline) as proxy:
            client = await proxy.connect()
            request = f"GET {ORIGINAL_AT} HTTP/1.1\r\nHost: {CDN}\r\n\r\n".encode()
            _raw, events = await client.send(request)
            return events

    answer = body_of(run(batch))
    seen = json.loads(gzip.decompress(answer) if answer.startswith(b"\x1f\x8b") else answer)
    return seen, run(fetch), batch_server, control


@pytest.mark.spec("S-21", 19)
def test_the_originals_download_gets_the_donors_real_bytes_and_headers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="verdra"):
        seen, events, batch_server, control = control_run(tmp_path)
    # Roblox's batch carried the donor too, but Roblox never sees that extra answer.
    [sent] = batch_server.received
    asked = json.loads(gzip.decompress(sent.body) if sent.body[:2] == b"\x1f\x8b" else sent.body)
    assert [(i["assetId"], i["requestId"]) for i in asked] == [
        (ORIGINAL, "r1"), (1234567, "r2"), (DONOR, "r1-verdra-donor"),
    ]  # fmt: skip
    assert [item["requestId"] for item in seen] == ["r1", "r2"]
    # The download of the original's address got the donor's real answer, headers included.
    assert body_of(events) == b"donor bytes"
    response = next(e for e in events if type(e).__name__ == "Response")
    assert (b"x-which", b"donor") in [(n.lower(), v) for n, v in response.headers]  # type: ignore[attr-defined]
    assert control.swapped == 1
    assert f"gets asset {DONOR}'s real bytes" in caplog.text


def test_a_donor_on_another_host_is_never_swapped_in(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="verdra"):
        _seen, events, _server, control = control_run(tmp_path, donor_host="c7.rbxcdn.com")
    assert body_of(events) == b"original bytes"
    assert control.swapped == 0
    assert "downloads from c7.rbxcdn.com" in caplog.text


def test_the_control_flag_needs_the_source_and_two_different_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert cli.parse([cli.CONTROL_FLAG, f"{ORIGINAL}={DONOR}"]).control_swap == (ORIGINAL, DONOR)
    assert cli.parse([]).control_swap is None
    for bad in (str(ORIGINAL), f"{ORIGINAL}={ORIGINAL}", "a=b"):
        with pytest.raises(SystemExit):
            cli.parse([cli.CONTROL_FLAG, bad])
    monkeypatch.setattr(cli, "diagnosis_available", lambda: False)
    with pytest.raises(SystemExit) as frozen:
        cli.parse([cli.CONTROL_FLAG, f"{ORIGINAL}={DONOR}"])
    assert frozen.value.code == 2
