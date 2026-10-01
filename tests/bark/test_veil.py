# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""The redaction filter (Master plan 10.6)."""

import logging
from urllib.parse import quote

import pytest

from verdra.bark import veil

# A made-up login token in the published format; not a real credential.
TOKEN = (
    "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-"
    "your-ROBUX-and-items.|_0123456789ABCDEFabcdef0123456789ABCDEF"
)

#: (text containing a secret, the secret) for every pattern in 10.6.
SECRETS = [
    ("Cookie: session=abc123", "session=abc123"),
    ("set-cookie: theme=dark; Path=/", "theme=dark"),
    ("Authorization: Bearer eyJhbGciOi", "eyJhbGciOi"),
    ("Proxy-Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
    ("X-CSRF-TOKEN: f00dfeed", "f00dfeed"),
    ("rbx-authentication-ticket: TICKET-9", "TICKET-9"),
    ("headers={'Cookie': 'a=1', 'Accept': '*/*'}", "a=1"),
    ('{"authorization": "Bearer xyz", "host": "roblox.com"}', "Bearer xyz"),
    (f"token={TOKEN}", "0123456789ABCDEF"),
    (f"Saw .ROBLOSECURITY={TOKEN}; path=/", "0123456789ABCDEF"),
    (".ROBLOSECURITY=plainvalue42; domain=.roblox.com", "plainvalue42"),
    ("GET /v1?X-CSRF-TOKEN=abc999&page=2", "abc999"),
    # Review finding H1: HAR-style name/value objects, encoded tokens, JSON cookie keys.
    (str({"name": "Cookie", "value": "sess=HAR1"}), "HAR1"),
    ('{"name": "Authorization", "value": "Bearer HAR2"}', "HAR2"),
    ('{"value": "HAR3", "name": "set-cookie"}', "HAR3"),
    ('{"name": ".ROBLOSECURITY", "value": "HAR4"}', "HAR4"),
    (str([("Cookie", "TUPLE1")]), "TUPLE1"),
    ("https://x.example/?t=" + quote(TOKEN), "0123456789ABCDEF"),
    ("https://x.example/?t=" + quote(quote(TOKEN)), "0123456789ABCDEF"),
    ('{".ROBLOSECURITY": "JSON1"}', "JSON1"),
    ("{'.ROBLOSECURITY': 'JSON2'}", "JSON2"),
    ("cookie=.ROBLOSECURITY%3DENC1&x=1", "ENC1"),
]


@pytest.mark.parametrize(("text", "secret"), SECRETS)
def test_redact_text(text: str, secret: str) -> None:
    result = veil.redact_text(text)
    assert secret not in result
    assert veil.REDACTED in result


def test_harmless_text_is_untouched() -> None:
    text = "Applied 12 replacements to asset 7547298786 (Accept: */*, cookies are off)."
    assert veil.redact_text(text) == text


def test_redact_headers_and_data() -> None:
    headers = veil.redact_headers({"Cookie": "a=1", "Accept": "text/html", "X-Note": TOKEN})
    assert headers == [
        ("Cookie", veil.REDACTED),
        ("Accept", "text/html"),
        ("X-Note", veil.REDACTED),
    ]
    data = veil.redact_data({"request": {"headers": {"AUTHORIZATION": "x"}, "body": [TOKEN, 3]}})
    assert data == {
        "request": {"headers": {"AUTHORIZATION": veil.REDACTED}, "body": [veil.REDACTED, 3]}
    }


def test_filter_redacts_message_arguments_and_exception() -> None:
    record = logging.LogRecord(
        "verdra.x", logging.INFO, __file__, 1, "Sent %s", ("Cookie: s=1",), None
    )
    try:
        raise ValueError(f"bad {TOKEN}")
    except ValueError:
        import sys

        record.exc_info = sys.exc_info()
    assert veil.VeilFilter().filter(record)
    assert record.getMessage() == f"Sent Cookie: {veil.REDACTED}"
    assert record.exc_info is None
    assert record.exc_text is not None
    assert "0123456789ABCDEF" not in record.exc_text
    assert "ValueError" in record.exc_text


@pytest.mark.parametrize(
    "data",
    [
        [["Cookie", "SECRETX"]],
        [("Authorization", "SECRETX")],
        {"headers": [{"name": "Cookie", "value": "SECRETX"}]},
        {"cookies": [{"name": ".ROBLOSECURITY", "value": "SECRETX", "path": "/"}]},
        {"headers": [{"Value": "SECRETX", "Name": "x-csrf-token"}]},
    ],
)
def test_redact_data_handles_pairs_and_har_objects(data: object) -> None:
    result = veil.redact_data(data)
    assert "SECRETX" not in str(result)
    assert veil.REDACTED in str(result)


def test_har_style_names_stay_readable() -> None:
    assert veil.redact_data({"name": "Accept", "value": "*/*"}) == {
        "name": "Accept",
        "value": "*/*",
    }
    text = veil.redact_text('{"name": "Cookie", "value": "s=1"}')
    assert text == '{"name": "Cookie", "value": "' + veil.REDACTED + '"}'
