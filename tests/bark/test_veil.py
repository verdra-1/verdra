# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The redaction filter (Master plan 10.6)."""

import logging
from urllib.parse import quote

import pytest

from tests.ids import ABOVE_INT32, ABOVE_UINT32
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
    (
        "Downloading https://cdn.discordapp.com/attachments/1/2/wall.png"
        "?ex=6705f1a2&is=6704a022&hm=c0ffee1234abcdef&",
        "c0ffee1234abcdef",
    ),
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


# Signed-URL secrets (plan 16.2). Every value below is invented.
#: (query parameter as Roblox's CDN URLs spell it, an invented value).
SIGNED = [
    ("__token__", "exp=1700000000~acl=/sc3/*~hmac=0a1b2c3d4e5f60718293a4b5c6d7e8f9"),
    ("hdnts", "exp=1700000000~PathGlobs=/sc3/*~hmac=f9e8d7c6b5a4"),
    ("hmac", "00112233445566778899aabbccddeeff"),
    ("Signature", "Zm9vYmFy~YmF6cXV4-LS0t~a2V5_"),
    ("Policy", "eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly94In1dfQ__"),
    ("Key-Pair-Id", "K3EXAMPLEKEYPAIR"),
    ("sig", "c2lnbmF0dXJlLXZhbHVl"),
    ("signature", "lowercase-signature-value"),
    ("token", "opaque-token-value-77"),
    ("ticket", "TICKET-invented-ABC"),
    ("X-Amz-Signature", "abcdef0123456789abcdef"),
    ("X-Amz-Security-Token", "FwoGZXIvYXdzEXAMPLE"),
    ("suggestedBrowserTrackerId", "424242424242"),
    # Links people paste as replacements (Guide B used a Discord attachment link).
    ("ex", "6705f1a2"),
    ("is", "6704a022"),
    ("hm", "3f9d2c1b0a99887766554433221100ffeeddccbbaa99887766554433221100ff"),
    ("X-Goog-Signature", "5a4b3c2d1e0f"),
    ("X-Goog-Credential", "verdra-test%40example.iam.gserviceaccount.com"),
]
#: How a parameter can be introduced: plain, inside an Akamai token, or percent-encoded.
SEPARATORS = ["?", "&", ";", "~", "%26", "%3F", "%2526"]


@pytest.mark.parametrize(("name", "value"), SIGNED)
@pytest.mark.parametrize("separator", SEPARATORS)
def test_signed_url_secrets_are_redacted(name: str, value: str, separator: str) -> None:
    for spelling in (name, name.upper(), name.lower()):
        for equals in ("=", "%3D", "%253D"):
            text = f"GET fts.rbxcdn.com /sc3/abc{separator}{spelling}{equals}{value}&next=1"
            result = veil.redact_text(text)
            assert value not in result, text
            assert result.endswith(f"{veil.REDACTED}&next=1"), result


@pytest.mark.parametrize(
    "level", [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]
)
def test_signed_url_secrets_are_redacted_at_every_level(level: int) -> None:
    url = "https://fts.rbxcdn.com/sc0/abc?__token__=exp=1~acl=/*~hmac=SECRETHMAC&Signature=SIGX"
    record = logging.LogRecord("verdra.roots.hyphae", level, __file__, 1, "GET %s", (url,), None)
    assert veil.VeilFilter().filter(record)
    message = record.getMessage()
    assert "SECRETHMAC" not in message
    assert "SIGX" not in message
    assert message.startswith("GET https://fts.rbxcdn.com/sc0/abc?__token__=")


def test_harmless_query_parameters_stay() -> None:
    text = (
        "GET fts.rbxcdn.com /sc3/abc?encoding=gzip&version=3&Expires=1700000000"
        "&cursor=next&tokens=5&signatures=2&my_token=x"
    )
    assert veil.redact_text(text) == text


#: Lines in the shape of a real Stage 2 log (plan 16.2), rewritten with invented values: the
#: hosts and the shape of each path and query are real, every value is made up.
SAMPLE_LINES = [
    "2026-01-02 03:04:05,678 DEBUG   verdra.roots.hyphae: GET sc2.rbxcdn.com "
    "/c/0f1e2d3c4b5a69788796a5b4c3d2e1f0/00112233445566778899aabbccddeeff/main.m3u8"
    "?__token__=exp=1767225600~acl=/c/0f1e2d3c*~hmac=1111111111111111111111111111111111111111"
    "&Expires=1767225600&Policy=eyJTdGF0ZW1lbnQiOltdfQ__"
    "&Signature=AAAAaaaaBBBBbbbb~CCCCcccc-DDDDdddd~EEEE_&Key-Pair-Id=KINVENTEDPAIR1",
    "2026-01-02 03:04:05,679 DEBUG   verdra.roots.hyphae: GET sc5.rbxcdn.com "
    "/c/0f1e2d3c4b5a69788796a5b4c3d2e1f0/00112233445566778899aabbccddeeff/720/0000.webm"
    "?__token__=exp=1767225600~acl=/c/*~hmac=2222222222222222222222222222222222222222"
    "&Expires=1767225600&Policy=eyJJbnZlbnRlZCI6dHJ1ZX0_"
    "&Signature=FFFFffff~GGGGgggg~HHHHhhhh&Key-Pair-Id=KINVENTEDPAIR2",
    "2026-01-02 03:04:05,680 DEBUG   verdra.roots.hyphae: GET fts.rbxcdn.com "
    "/sc3/99887766554433221100ffeeddccbbaa?encoding=gzip&version=3"
    "&__token__=exp=1767225600~acl=/sc3/*~hmac=3333333333333333333333333333333333333333"
    "&Expires=1767225600&Policy=eyJBbm90aGVyIjoxfQ__&Signature=IIIIiiii~JJJJjjjj"
    "&Key-Pair-Id=KINVENTEDPAIR3"
    "&hdnts=exp=1767225600~PathGlobs=/sc3/*~hmac=4444444444444444444444444444444444444444",
    "2026-01-02 03:04:05,681 DEBUG   verdra.roots.hyphae: POST apis.roblox.com "
    "/browser-tracker-api/device/initialize?suggestedBrowserTrackerId=5555555555",
]
#: Every invented secret in SAMPLE_LINES.
SAMPLE_SECRETS = [
    *(str(n) * 40 for n in range(1, 5)),
    "1767225600~acl",
    "PathGlobs",
    "eyJ",
    "KINVENTEDPAIR",
    "AAAAaaaa",
    "FFFFffff",
    "IIIIiiii",
    "5555555555",
]


def test_rewritten_sample_lines_keep_no_secret() -> None:
    for line in SAMPLE_LINES:
        record = logging.LogRecord(
            "verdra.roots.hyphae", logging.DEBUG, __file__, 1, line, (), None
        )
        veil.VeilFilter().filter(record)
        result = record.getMessage()
        for secret in SAMPLE_SECRETS:
            assert secret not in result, (secret, result)
        # What a reader needs stays: the method, host, path and harmless parameters.
        method, host, path = line.split(": ", 1)[1].split(" ")
        assert f"{method} {host} {path.split('?')[0]}?" in result
    assert "encoding=gzip&version=3&__token__=" in veil.redact_text(SAMPLE_LINES[2])


# Support bundles (plan 16.2): user names in paths and long numeric IDs.
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            r"C:\Users\Alex Example\AppData\Local\Roblox\Versions\version-0a1b",
            r"C:\Users\<user>\AppData\Local\Roblox\Versions\version-0a1b",
        ),
        (r"c:\users\alex\AppData", r"c:\users\<user>\AppData"),
        ('{"path": "C:\\\\Users\\\\alex\\\\x"}', '{"path": "C:\\\\Users\\\\<user>\\\\x"}'),
        ("C:/Users/alex/Desktop", "C:/Users/<user>/Desktop"),
        ("/home/alex/.var/app", "/home/<user>/.var/app"),
        ("Saved in C:\\Users\\alex.", "Saved in C:\\Users\\<user>."),
        ("place 1818 universe 1234567 user 9876543210", "place 1818 universe <id> user <id>"),
        ("placeId=1234567890&x=1", "placeId=<id>&x=1"),
        (f"asset {ABOVE_UINT32} place {ABOVE_INT32}", "asset <id> place <id>"),
        ("/universes/v1/places/1234567890/universe", "/universes/v1/places/<id>/universe"),
        (
            "Roblox 0.741.0.7411058, pid 41234, port 51234",
            "Roblox 0.741.0.7411058, pid 41234, port 51234",
        ),
        ("hash 0a1234567b, abc1234567", "hash 0a1234567b, abc1234567"),
    ],
)
def test_anonymize_text(text: str, expected: str) -> None:
    assert veil.anonymize_text(text) == expected


def test_anonymize_text_replaces_the_given_user_names() -> None:
    text = "Signed in as Alex Example (alex.e) on alex-pc; alexandra stays"
    result = veil.anonymize_text(text, ["Alex Example", "alex.e", "alex"])
    assert result == "Signed in as <user> (<user>) on alex-pc; alexandra stays"


def test_anonymize_data() -> None:
    data = {
        "library": "C:\\Users\\alex\\Verdra",
        "ids": [1234567890, 42, True],
        "C:\\Users\\alex": {"Cookie": "a=1"},
    }
    assert veil.anonymize_data(data, ["alex"]) == {
        "library": "C:\\Users\\<user>\\Verdra",
        "ids": ["<id>", 42, True],
        "C:\\Users\\<user>": {"Cookie": veil.REDACTED},
    }


@pytest.mark.parametrize(
    "text",
    [text for text, _secret in SECRETS]
    + [f"GET /sc3/abc?{name}={value}&next=1" for name, value in SIGNED],
)
def test_redacting_twice_changes_nothing_more(text: str) -> None:
    """A line redacted at its source (roots/hyphae) passes the log filter again unchanged.

    The maintainer's log of 8 October showed "•••• (redacted) (redacted)" for every signed value.
    """
    once = veil.redact_text(text)
    assert veil.redact_text(once) == once
    assert "(redacted) (redacted)" not in veil.redact_text(once)
