# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-25: the load counter ("Live · seen N×") counts loads, not packs (owner, question N2)."""

from __future__ import annotations

import base64
import builtins
import json
import logging
import socket
import time
from typing import Any

import pytest

from tests.ids import ABOVE_INT32, ABOVE_UINT32
from tests.roots.test_grafter import BATCH, HOST, holder
from verdra.roots import hyphae, rules
from verdra.roots.symbionts.grafter import Grafter, item_pack


def representation(fidelity: bytes | str) -> str:
    """A batch item's contentRepresentationPriorityList, as Roblox sends it (base64 JSON)."""
    value = fidelity if isinstance(fidelity, str) else base64.b64encode(fidelity).decode()
    choices = [{"format": "ktx2", "majorVersion": "1", "fidelity": value}]
    return base64.b64encode(json.dumps(choices).encode()).decode()


def item(asset_id: int, request_id: str, pack: int | None) -> dict[str, Any]:
    found: dict[str, Any] = {"requestId": request_id, "assetId": asset_id}
    if pack is not None:
        found["contentRepresentationPriorityList"] = representation(
            b"\xff\xff\xff\xfc" + bytes([pack + 1])
        )
    return found


@pytest.mark.parametrize(
    ("fidelity", "pack"),
    [
        (b"\xff\xff\xff\xfc\x01", 0),
        (b"\xff\xff\xff\xfc\x02", 1),
        (b"\xff\xff\xff\xfc\x03", 2),
        (b"\xff\xff\xff\xfc\x04", None),  # no fourth pack
        (b"\xff\xff\xff\xfc\x00", None),
        ("ALL", None),  # a mesh
        (b"\x01\x02", None),
    ],
)
def test_the_pack_comes_from_the_items_fidelity(fidelity: bytes | str, pack: int | None) -> None:
    found = {"contentRepresentationPriorityList": representation(fidelity)}
    assert item_pack(found) == pack


@pytest.mark.parametrize(
    "listed",
    [
        None,
        5,
        "not base64!",
        base64.b64encode(b"not json").decode(),
        base64.b64encode(b"[]").decode(),
    ],
)
def test_an_item_naming_no_readable_pack_has_none(listed: object) -> None:
    assert item_pack({"contentRepresentationPriorityList": listed}) is None


def test_a_load_is_pack_0_or_a_first_pack_and_everything_else() -> None:
    loads = rules.Loads(clock=lambda: 100.0)
    assert loads.record(ABOVE_INT32, 0)  # a picture: pack 0 is a load
    assert not loads.record(ABOVE_INT32, 1)  # its further packs aren't
    assert not loads.record(ABOVE_INT32, 2)
    assert loads.record(ABOVE_UINT32, 2)  # pack 0 never asked for: the first pack is the load
    assert not loads.record(ABOVE_UINT32, 1)
    assert loads.record(7777777, None)  # a mesh, a sound, any other item: each is a load
    assert loads.record(7777777, None)
    assert loads.record(ABOVE_INT32, 0)  # pack 0 again: a new load
    assert loads.counts == {ABOVE_INT32: 2, ABOVE_UINT32: 1, 7777777: 2}
    assert loads.last[ABOVE_INT32] == 100.0
    loads.reset()
    assert loads.counts == {} and loads.last == {}
    assert loads.record(ABOVE_UINT32, 1)  # after a restart, the first pack is a load again


@pytest.mark.spec("S-25", 3)
def test_the_grafter_counts_loads_and_logs_each_item_as_load_or_further_pack(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ID swaps of pictures follow the pack rule too; the count equals the "load" lines."""
    caplog.set_level(logging.DEBUG, logger="verdra.roots.symbionts.grafter")
    loads = rules.Loads()
    grafter = Grafter(holder({ABOVE_INT32: 1111111, ABOVE_UINT32: 2222222}), loads=loads)

    def batch(*items: dict[str, Any]) -> None:
        body = json.dumps(list(items)).encode()
        assert grafter.on_request(hyphae.Request(HOST, b"POST", BATCH, (), body)) is not None

    batch(item(ABOVE_INT32, "a", 0))
    batch(item(ABOVE_INT32, "b", 1))  # seconds later, in another batch
    batch(item(ABOVE_INT32, "c", 2), item(ABOVE_UINT32, "d", None))
    batch(item(ABOVE_INT32, "e", 0))  # a new load
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Replaced asset")]
    assert lines == [
        f"Replaced asset {ABOVE_INT32} in a batch: load (ID swap, pack 0)",
        f"Replaced asset {ABOVE_INT32} in a batch: further pack (ID swap, pack 1)",
        f"Replaced asset {ABOVE_INT32} in a batch: further pack (ID swap, pack 2)",
        f"Replaced asset {ABOVE_UINT32} in a batch: load (ID swap, pack -)",
        f"Replaced asset {ABOVE_INT32} in a batch: load (ID swap, pack 0)",
    ]
    for original in (ABOVE_INT32, ABOVE_UINT32):
        load_lines = [line for line in lines if f"asset {original} " in line and ": load" in line]
        assert loads.counts[original] == len(load_lines)


@pytest.mark.spec("S-25", 7)
def test_recording_a_load_touches_no_file_and_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """S-11: the proxy hook does no disk or network work."""

    def refuse(*_args: object, **_kwargs: object) -> None:
        msg = "the load counter must not touch files or sockets"
        raise AssertionError(msg)

    loads = rules.Loads(notify=lambda _original: None)
    monkeypatch.setattr(builtins, "open", refuse)
    monkeypatch.setattr(socket, "socket", refuse)
    for pack in (0, 1, 2, None):
        loads.record(ABOVE_INT32, pack)
    assert loads.counts[ABOVE_INT32] == 2


def test_recording_a_load_is_cheap() -> None:
    """S-25 test 7 asks for under 1 µs per event; measured about 0.25 µs on the session machine,
    so this allows a slow CI runner five times that."""
    loads = rules.Loads()
    count = 100_000
    started = time.perf_counter()
    for index in range(count):
        loads.record(index % 500, index % 3)
    assert (time.perf_counter() - started) / count < 5e-6
