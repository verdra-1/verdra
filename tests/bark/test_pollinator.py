# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""bark/pollinator: the asset lookup the replacement editor triggers (spec S-22)."""

from __future__ import annotations

import httpx
import pytest

from tests.ids import ABOVE_UINT32
from verdra.bark import pollinator

#: The real client, taken before the test guard swaps in one that never connects.
REAL_CLIENT = pollinator._client  # noqa: SLF001


def client_answering(status: int, body: object, seen: list[httpx.Request]) -> httpx.Client:
    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if isinstance(body, bytes):
            return httpx.Response(status, content=body)
        return httpx.Response(status, json=body, headers={"Location": "http://elsewhere.example/"})

    return httpx.Client(transport=httpx.MockTransport(answer), headers={"User-Agent": "Verdra"})


@pytest.mark.parametrize(
    ("type_id", "family"), [(1, "Image"), (3, "Audio"), (4, "Mesh"), (13, ""), (10, "")]
)
def test_the_type_roblox_gives_and_the_family_it_belongs_to(type_id: int, family: str) -> None:
    seen: list[httpx.Request] = []
    client = client_answering(200, {"AssetTypeId": type_id, "Name": "x"}, seen)
    kind = pollinator.asset_kind(ABOVE_UINT32, client)
    assert kind == pollinator.AssetKind(type_id)
    assert kind is not None
    assert kind.family == family
    [request] = seen
    assert str(request.url) == f"https://economy.roblox.com/v2/assets/{ABOVE_UINT32}/details"
    assert request.method == "GET"
    assert "cookie" not in request.headers  # no account, no sign-in (plan 10.6)


@pytest.mark.parametrize("status", [400, 404])
def test_an_asset_roblox_doesnt_have_is_none(status: int) -> None:
    assert pollinator.asset_kind(1, client_answering(status, {"errors": []}, [])) is None


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (500, {"errors": []}),
        (429, {"errors": []}),
        (302, {}),  # a redirect is never followed
        (200, b"<html>"),
        (200, {"Name": "no type"}),
        (200, {"AssetTypeId": "1"}),
        (200, {"AssetTypeId": True}),
        (200, [1]),
    ],
)
def test_an_unexpected_answer_is_an_error(status: int, body: object) -> None:
    with pytest.raises(pollinator.PollinatorError):
        pollinator.asset_kind(1, client_answering(status, body, []))


def test_no_connection_is_an_error_with_a_plain_reason() -> None:
    # The test guard's client (tests/support/isolation) refuses every connection.
    with pytest.raises(pollinator.PollinatorError, match="couldn't be reached"):
        pollinator.asset_kind(1)


def test_the_real_client_follows_no_redirect_and_names_only_verdra() -> None:
    client = REAL_CLIENT()
    try:
        assert client.follow_redirects is False
        assert client.headers["User-Agent"] == "Verdra"
        assert client.timeout == pollinator.TIMEOUT
    finally:
        client.close()
