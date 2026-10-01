# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""The redaction filter (Master plan 10.6)."""

import logging

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
