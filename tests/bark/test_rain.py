# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Plan 10.7: verified downloads (bark/rain). No test reaches the network: a fake opener answers."""

from __future__ import annotations

import io
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from verdra.bark import rain


class Answer(io.BytesIO):
    status = 200


def opener_for(body: bytes, seen: list[urllib.request.Request] | None = None) -> rain.Opener:
    def opener(request: urllib.request.Request, _timeout: float) -> Answer:
        if seen is not None:
            seen.append(request)
        return Answer(body)

    return opener


def test_a_download_is_kept_under_the_sha256_of_its_link(tmp_path: Path) -> None:
    seen: list[urllib.request.Request] = []
    url = "https://pictures.example/wall.png?size=big"
    data = rain.fetch(url, tmp_path, user_agent="Verdra/9", opener=opener_for(b"picture", seen))
    assert data == b"picture"
    assert rain.cached(url, tmp_path) == b"picture"
    assert rain.cache_path(url, tmp_path).parent == tmp_path
    assert len(rain.cache_path(url, tmp_path).name) == 64  # hex SHA-256, any link a safe name
    [request] = seen
    assert request.get_header("User-agent") == "Verdra/9"
    assert request.get_header("Cookie") is None  # nothing about the user is sent
    assert rain.cached("https://pictures.example/other.png", tmp_path) is None


@pytest.mark.parametrize("url", ["http://pictures.example/a.png", "ftp://x/a", "https:///a.png"])
def test_only_https_links_are_fetched(tmp_path: Path, url: str) -> None:
    def never(*_args: object) -> Answer:
        raise AssertionError("no connection may be made")

    with pytest.raises(rain.RainError, match="only HTTPS links"):
        rain.fetch(url, tmp_path, opener=never)


def test_reading_stops_at_the_limit(tmp_path: Path) -> None:
    with pytest.raises(rain.RainError, match="bigger than 1 MB"):
        rain.fetch(
            "https://x.example/big", tmp_path, limit=1024 * 1024,
            opener=opener_for(b"x" * (1024 * 1024 + 1)),
        )  # fmt: skip
    assert rain.cached("https://x.example/big", tmp_path) is None  # nothing kept


def test_http_and_connection_errors_say_why(tmp_path: Path) -> None:
    def not_found(request: urllib.request.Request, _timeout: float) -> Answer:
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", None, None)  # type: ignore[arg-type]

    def refused(_request: urllib.request.Request, _timeout: float) -> Answer:
        raise urllib.error.URLError("connection refused")

    with pytest.raises(rain.RainError, match="the server answered 404"):
        rain.fetch("https://x.example/a", tmp_path, opener=not_found)
    with pytest.raises(rain.RainError, match=r"couldn't be downloaded \(connection refused\)"):
        rain.fetch("https://x.example/a", tmp_path, opener=refused)


def test_a_redirect_to_a_non_https_address_is_refused() -> None:
    handler = rain._HttpsOnly()  # noqa: SLF001
    request = urllib.request.Request("https://x.example/a")
    with pytest.raises(rain.RainError, match="non-HTTPS address"):
        handler.redirect_request(request, None, 302, "Found", {}, "http://x.example/a")
    followed = handler.redirect_request(request, None, 302, "Found", {}, "https://y.example/a")
    assert followed is not None and followed.full_url == "https://y.example/a"
