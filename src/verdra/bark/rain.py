# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Verified downloads: HTTPS only, size limits per type, SHA-256 cache.

Plan 10.7 ("Downloads (bark/rain)"): a link a profile names is fetched over HTTPS only (a
redirect to anything else is refused), verified against the OS trust store (truststore), read
up to a size limit and no further, and kept in a cache folder under the SHA-256 of the link, so
the next Apply now doesn't fetch it again. Nothing else is sent: no cookies, no account, only a
User-Agent naming Verdra and its version (plan 10.6: no telemetry).
"""

from __future__ import annotations

import hashlib
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

import truststore

from verdra.soil import atomic

#: Plan 10.7: no download is read past this size (the largest per-type limit, meshes and images).
MAX_DOWNLOAD: Final = 64 * 1024 * 1024
TIMEOUT_S: Final = 30.0
_CHUNK: Final = 64 * 1024


class RainError(OSError):
    """A download failed; the message is the plain reason."""


def cache_path(url: str, folder: Path) -> Path:
    """Return where the download of `url` is kept: its SHA-256, so any link is a safe name."""
    return folder / hashlib.sha256(url.encode("utf-8")).hexdigest()


def cached(url: str, folder: Path) -> bytes | None:
    """Return the cached download of `url`, or None if it hasn't been fetched."""
    try:
        return atomic.read_bytes(cache_path(url, folder))
    except OSError:
        return None


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to another HTTPS address."""

    def redirect_request(  # noqa: PLR0917 - urllib's own signature
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        if urlsplit(newurl).scheme.lower() != "https":
            reason = f"the link redirects to a non-HTTPS address ({urlsplit(newurl).scheme})"
            raise RainError(reason)
        return super().redirect_request(req, fp, code, msg, headers, newurl)  # type: ignore[arg-type]


def _context() -> ssl.SSLContext:
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


Opener = Callable[[urllib.request.Request, float], object]


def _default_opener(request: urllib.request.Request, timeout: float) -> object:
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=_context()), _HttpsOnly()
    )
    return opener.open(request, timeout=timeout)


def fetch(
    url: str,
    folder: Path,
    *,
    limit: int = MAX_DOWNLOAD,
    user_agent: str = "Verdra",
    opener: Opener = _default_opener,
) -> bytes:
    """Download `url` (HTTPS only, at most `limit` bytes), keep it in `folder`, return it.

    Raises:
        RainError: not HTTPS, a failed connection or certificate, an HTTP error, or too big.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() != "https" or not parts.hostname:
        msg = "only HTTPS links are allowed"
        raise RainError(msg)
    request = urllib.request.Request(  # noqa: S310 - the scheme is checked above
        url, headers={"User-Agent": user_agent, "Accept": "*/*"}
    )
    try:
        response = opener(request, TIMEOUT_S)
        status = getattr(response, "status", 200)
        if not 200 <= status < 300:  # noqa: PLR2004
            msg = f"the server answered {status}"
            raise RainError(msg)
        data = bytearray()
        while chunk := response.read(_CHUNK):  # type: ignore[attr-defined]
            data += chunk
            if len(data) > limit:
                msg = f"it is bigger than {limit // (1024 * 1024)} MB"
                raise RainError(msg)
    except RainError:
        raise
    except urllib.error.HTTPError as error:
        msg = f"the server answered {error.code}"
        raise RainError(msg) from error
    except (urllib.error.URLError, OSError, ssl.SSLError) as error:
        reason = getattr(error, "reason", error)
        msg = f"it couldn't be downloaded ({reason})"
        raise RainError(msg) from error
    atomic.write_atomic(cache_path(url, folder), bytes(data))
    return bytes(data)
