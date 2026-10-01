# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""The one redaction filter (10.6) used by logs, Traffic, exports and support bundles.

Secrets are removed at the source (Master plan 10.6): the values of the headers below, and any
Roblox login token anywhere in a text, become "•••• (redacted)". Every output path (log files,
the Activity screen, Traffic, HAR export, saved traffic and support bundles) runs its data through
this module; there is no second implementation.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from typing import Any, cast

REDACTED = "•••• (redacted)"

#: Headers whose values are always secret. Matched without regard to case.
SECRET_HEADERS = frozenset(
    {
        "cookie",
        "set-cookie",
        "authorization",
        "proxy-authorization",
        "x-csrf-token",
        "rbx-authentication-ticket",
    }
)

_HEADER_NAMES = "|".join(re.escape(name) for name in sorted(SECRET_HEADERS, key=len, reverse=True))

# "Cookie: value" as a header line or inside a sentence, up to the end of the line.
_HEADER_LINE = re.compile(rf"(?im)(?<![\w-])((?:{_HEADER_NAMES})\s*:[ \t]*)([^\r\n]+)")
# Secret names that appear as a cookie or field name rather than a header name.
_SECRET_FIELDS = "|".join([_HEADER_NAMES, r"\.ROBLOSECURITY"])
# 'Cookie': 'value' or "cookie": "value" as in a dict repr or JSON, and ('Cookie', 'value') as in
# a tuple repr. A quoted string followed by a colon is a key, not the value.
_QUOTED_PAIR = re.compile(
    rf"(?i)(['\"](?:{_SECRET_FIELDS})['\"]\s*[:,=]\s*)(['\"])((?:\\.|(?!\2).)*)(\2)(?!\s*:)"
)
# HAR-style objects: {"name": "Cookie", "value": "…"} in either order.
_NAME_THEN_VALUE = re.compile(
    rf"(?i)(['\"]name['\"]\s*:\s*['\"](?:{_SECRET_FIELDS})['\"]\s*,\s*['\"]value['\"]\s*:\s*)"
    r"(['\"])((?:\\.|(?!\2).)*)(\2)"
)
_VALUE_THEN_NAME = re.compile(
    r"(?i)(['\"]value['\"]\s*:\s*)(['\"])((?:\\.|(?!\2).)*)(\2)"
    rf"(\s*,\s*['\"]name['\"]\s*:\s*['\"](?:{_SECRET_FIELDS})['\"])"
)
# Cookie=value, as in a query string or keyword argument.
_ASSIGNMENT = re.compile(rf"(?i)(?<![\w-])((?:{_HEADER_NAMES})=)([^\s&;,'\"]+)")

# The Roblox login token: its well-known warning prefix and the value that follows, and any value
# of the cookie that carries it.
# "|" and ":" may also appear percent-encoded once or twice, as in a URL.
_BAR = r"(?:\||%(?:25)?7[Cc])"
_COLON = r"(?::|%(?:25)?3[Aa])"
_LOGIN_TOKEN = re.compile(
    rf"_{_BAR}WARNING{_COLON}-DO-NOT-SHARE-THIS\.(?:(?!{_BAR}).)*{_BAR}_[A-Za-z0-9+/=_.\-%]*"
)
_LOGIN_COOKIE = re.compile(r"(?i)(\.ROBLOSECURITY['\"]?\s*(?:=|:|%3[Dd])\s*['\"]?)([^;'\"\s,}&]+)")


def redact_text(text: str) -> str:
    """Return `text` with every secret header value and login token replaced."""
    text = _LOGIN_TOKEN.sub(REDACTED, text)
    text = _LOGIN_COOKIE.sub(lambda m: m.group(1) + REDACTED, text)
    text = _NAME_THEN_VALUE.sub(lambda m: m.group(1) + m.group(2) + REDACTED + m.group(4), text)
    text = _VALUE_THEN_NAME.sub(
        lambda m: m.group(1) + m.group(2) + REDACTED + m.group(4) + m.group(5), text
    )
    text = _QUOTED_PAIR.sub(lambda m: m.group(1) + m.group(2) + REDACTED + m.group(4), text)
    text = _HEADER_LINE.sub(lambda m: m.group(1) + REDACTED, text)
    return _ASSIGNMENT.sub(lambda m: m.group(1) + REDACTED, text)


def is_secret_header(name: str) -> bool:
    """Return whether a header's (or cookie's) value must never be shown or stored."""
    return name.strip().lower() in SECRET_HEADERS or name.strip().lower() == ".roblosecurity"


def redact_headers(headers: Mapping[str, str] | Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Return header pairs with secret values replaced and every other value scanned."""
    pairs = (
        list(cast("Mapping[str, str]", headers).items())
        if isinstance(headers, Mapping)
        else list(headers)
    )
    return [
        (name, REDACTED if is_secret_header(name) else redact_text(value)) for name, value in pairs
    ]


def redact_data(value: Any) -> Any:
    """Return a copy of JSON-like data with secrets replaced, at any depth.

    Mapping keys that name a secret header have their values replaced whole, and so do the values
    of HAR-style `{"name": "Cookie", "value": …}` objects and of `[name, value]` pairs whose name
    is secret. Every string is scanned with `redact_text`.
    """
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        mapping = cast("Mapping[Any, Any]", value)
        name = next((item for key, item in mapping.items() if _is_key(key, "name")), None)
        secret_object = isinstance(name, str) and is_secret_header(name)
        return {
            key: REDACTED
            if isinstance(key, str)
            and (is_secret_header(key) or (secret_object and _is_key(key, "value")))
            else redact_data(item)
            for key, item in mapping.items()
        }
    if isinstance(value, list | tuple):
        items = list(cast("Iterable[Any]", value))
        if len(items) == 2 and isinstance(items[0], str) and is_secret_header(items[0]):
            return [items[0], REDACTED]
        return [redact_data(item) for item in items]
    return value


def _is_key(key: object, name: str) -> bool:
    return isinstance(key, str) and key.lower() == name


class VeilFilter(logging.Filter):
    """A logging filter that redacts a record's message, arguments and exception text.

    It formats the message with its arguments first, so a secret passed as an argument is caught
    too, then stores the redacted text with no arguments left. Handlers that run after it never
    see the original values.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact the record in place and keep it."""
        record.msg = redact_text(record.getMessage())
        record.args = None
        if record.exc_info:
            formatter = logging.Formatter()
            record.exc_text = redact_text(formatter.formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_text(record.stack_info)
        return True
