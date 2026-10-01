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
# 'Cookie': 'value' or "cookie": "value" as in a dict repr or JSON.
_QUOTED_PAIR = re.compile(
    rf"(?i)(['\"](?:{_HEADER_NAMES})['\"]\s*[:,=]\s*)(['\"])((?:\\.|(?!\2).)*)(\2)"
)
# Cookie=value, as in a query string or keyword argument.
_ASSIGNMENT = re.compile(rf"(?i)(?<![\w-])((?:{_HEADER_NAMES})=)([^\s&;,'\"]+)")

# The Roblox login token: its well-known warning prefix and the value that follows, and any value
# of the cookie that carries it.
_LOGIN_TOKEN = re.compile(r"_\|WARNING:-DO-NOT-SHARE-THIS\.[^|]*\|_[A-Za-z0-9+/=_.\-]*")
_LOGIN_COOKIE = re.compile(r"(?i)(\.ROBLOSECURITY\s*[=:]\s*['\"]?)([^;'\"\s,}]+)")


def redact_text(text: str) -> str:
    """Return `text` with every secret header value and login token replaced."""
    text = _LOGIN_TOKEN.sub(REDACTED, text)
    text = _LOGIN_COOKIE.sub(lambda m: m.group(1) + REDACTED, text)
    text = _QUOTED_PAIR.sub(lambda m: m.group(1) + m.group(2) + REDACTED + m.group(4), text)
    text = _HEADER_LINE.sub(lambda m: m.group(1) + REDACTED, text)
    return _ASSIGNMENT.sub(lambda m: m.group(1) + REDACTED, text)


def is_secret_header(name: str) -> bool:
    """Return whether a header's value must never be shown or stored."""
    return name.strip().lower() in SECRET_HEADERS


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

    Mapping keys that name a secret header have their values replaced whole; every string is
    scanned with `redact_text`.
    """
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            key: REDACTED if isinstance(key, str) and is_secret_header(key) else redact_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact_data(item) for item in value]
    return value


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
