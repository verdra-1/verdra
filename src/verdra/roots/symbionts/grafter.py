# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Rewrites asset batch requests and responses; serves replacement content.

Spec S-21. This part swaps asset IDs on `assetdelivery.roblox.com`:

- In a batch request (`POST /v1/assets/batch`, fact V1), each item whose asset ID has a
  replacement asks for the target ID instead, and every other field of the item is kept. The
  response is mapped back by each item's request ID, so the client receives the content for the
  item it asked for, with the original ID wherever the response names one.
- A single-asset request (`GET /v1/asset/?id=…` and `/v2/asset/?id=…`, seen in the first swap
  test's log, and `/v1/assetId/<id>` and `/v2/assetId/<id>`, from the service's public API
  description) asks for the target ID instead; every other part of the address is kept.

Roblox sends most batches compressed (gzip, seen in the second swap test's log): roots/hyphae
decodes them first, and a changed batch is sent on uncompressed with a correct length.

Anything the grafter doesn't recognize (a response it can't map back) passes through unchanged
(rule 4). Everything it needs is in the snapshot it read when the request arrived; it does no
disk or network work (rule 2).

While any replacement is active, a batch it can't read (an encoding Verdra can't decode,
damaged or oversized compressed data, a body that isn't a JSON array of objects) is never
silent: it passes through unchanged, a warning names the reason (M-GRAFT-04) and
`on_unreadable` turns the routing status Degraded (M-GRAFT-03, spec S-14).

What it saw is logged at Debug level (Settings › Advanced › Detailed logging), one line per
batch whatever the outcome: how many items were replaced, the asset IDs asked for (with each
match), how the body was compressed, and the field names of the items. Asset IDs are public; no
other value is logged (field names only, never a value such as a download link, which carries a
signature).
"""

from __future__ import annotations

import json
import logging
import re
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final
from urllib.parse import urlsplit

from PySide6.QtCore import QCoreApplication

from verdra.roots import hyphae, rules

log = logging.getLogger(__name__)

#: Batches waiting for their response; old ones are forgotten (an upstream that never answered).
_PENDING_LIMIT: Final = 1024
_ASSET_ID: Final = "assetId"
_REQUEST_ID: Final = "requestId"
#: An item can name its content by hash instead of by asset ID (seen on 7 October 2026).
_HASH: Final = "hash"
_ASSET_TYPE: Final = "assetType"
_LOCATION: Final = "location"
#: Content downloads to watch: the CDN addresses the batch responses gave for replaced content.
_DOWNLOADS_LIMIT: Final = 1024
_PNG: Final = b"\x89PNG\r\n\x1a\n"
_KTX2: Final = b"\xabKTX 20\xbb\r\n\x1a\n"
_FILEMESH: Final = re.compile(rb"version \d\.\d\d\r?\n")
#: Response headers about the original bytes that don't describe the replacement.
_STALE_HEADERS: Final = frozenset({b"content-md5", b"etag", b"last-modified"})
#: What a content hash looks like; anything else is logged as "not a hash", never verbatim.
_HEX_HASH = re.compile(r"[0-9A-Fa-f]{8,128}")
#: At most this many asset IDs per log line, so one large batch stays one readable line.
_LOGGED_IDS: Final = 100
#: Single-asset requests: `/v1/asset/?id=…` (and v2), and `/v1/assetId/<id>` (and v2).
_SINGLE_QUERY_PATHS: Final = frozenset({"/v1/asset", "/v2/asset"})
_QUERY_ID = re.compile(r"(?i)(^|&)(id=)(\d+)(?=&|$)")
_PATH_ID = re.compile(r"(?i)^(/v[12]/assetid/)(\d+)(?=/|$)")


@dataclass(slots=True)
class _Found:
    """What one batch request holds, item by item (see `_take`)."""

    originals: dict[Any, Any] = field(default_factory=dict[Any, Any])
    hashed: dict[Any, str] = field(default_factory=dict[Any, str])
    served: dict[Any, int] = field(default_factory=dict[Any, int])
    without_request_id: int = 0


def _take(
    item: dict[str, Any],
    swaps: Mapping[int, int],
    content: Mapping[int, rules.Content],
    found: _Found,
) -> str:
    """Handle one batch item and return how the log names it.

    An Asset ID replacement asks for the target instead (mapped back by request ID); a content
    replacement is asked for unchanged, and Verdra serves its content when Roblox downloads it
    from the address the response gives (S-21); an item asked for by hash is noted.
    """
    sent = item.get(_ASSET_ID)
    asset_id = _as_id(sent)
    if asset_id is None:
        _note_hash(item, found.hashed)
        return "?"
    label = str(sent)
    if asset_id not in swaps and asset_id not in content:
        return label
    if _REQUEST_ID not in item:
        found.without_request_id += 1
        return label
    key = _key(item[_REQUEST_ID])
    if asset_id in swaps:
        target = swaps[asset_id]
        item[_ASSET_ID] = str(target) if isinstance(sent, str) else target
        found.originals[key] = sent
        return f"{label}->{target}"
    found.served[key] = asset_id
    return f"{label}=>{content[asset_id].source}"


@dataclass(frozen=True, slots=True)
class _Pending:
    """A batch waiting for its response."""

    request: hyphae.Request
    #: Request ID key -> the original asset ID as the client sent it (the replaced items).
    originals: dict[Any, Any]
    #: Request ID key -> the hash, for items asked for by hash instead of by asset ID.
    hashed: dict[Any, str]
    #: The replacements when the batch was sent (S-21 test 8).
    swaps: Mapping[int, int]
    #: Request ID key -> original asset ID, for items whose content Verdra serves itself.
    served: dict[Any, int] = field(default_factory=dict[Any, int])
    #: The prepared content when the batch was sent.
    content: Mapping[int, rules.Content] = field(default_factory=dict[int, rules.Content])


class Grafter:
    """The grafter symbiont (Reference R1, roots/symbionts/grafter)."""

    name = "grafter"

    def __init__(
        self,
        holder: rules.SnapshotHolder,
        on_unreadable: Callable[[str], None] | None = None,
        *,
        leave: frozenset[int] = frozenset(),
    ) -> None:
        self.holder = holder
        #: Originals left alone whatever the snapshot says (a format capture is watching them,
        #: roots/litmus, source runs only): their batch items and downloads pass unchanged.
        self.leave = leave
        #: Called (on the proxy's thread) with the reason whenever a batch couldn't be read while
        #: a replacement is active; the routing status turns Degraded (S-14).
        self.on_unreadable = on_unreadable
        # id(request) -> the batch, waiting for its response
        self._pending: OrderedDict[int, _Pending] = OrderedDict()
        # CDN target (path and query) -> (original asset ID, its content), from batch responses
        self._downloads: OrderedDict[bytes, tuple[int, rules.Content]] = OrderedDict()
        # id(request) -> (the download request, original asset ID, its content)
        self._fetching: dict[int, tuple[hyphae.Request, int, rules.Content]] = {}

    # --- Requests --------------------------------------------------------------------------

    def _active(self) -> tuple[Mapping[int, int], Mapping[int, rules.Content]]:
        """The snapshot's swaps and content, without the originals left alone."""
        snapshot = self.holder.current
        swaps, content = snapshot.swaps(), snapshot.content
        if self.leave:
            swaps = {k: v for k, v in swaps.items() if k not in self.leave}
            content = {k: v for k, v in content.items() if k not in self.leave}
        return swaps, content

    def wants_request_body(self, request: hyphae.Request) -> bool:
        """Only asset batches, and only while some asset has a replacement."""
        swaps, content = self._active()
        return _is_batch(request) and bool(swaps or content)

    def on_request(self, request: hyphae.Request) -> hyphae.Request | None:
        """Ask for each replaced asset's target instead; None if nothing changes."""
        if _is_batch(request):
            return self._batch_request(request)
        if _is_single(request):
            return self._single_request(request)
        if _is_download(request):
            self._download_request(request)
        return None

    def _batch_request(self, request: hyphae.Request) -> hyphae.Request | None:
        swaps, content = self._active()
        if not swaps and not content:
            return None
        if request.body is None:
            self._unreadable("request", "over 64 MB")
            return None
        items = _items(request.body)
        if items is None:
            self._unreadable("request", "not a JSON array of objects")
            return None
        found = _Found()
        asked = [_take(item, swaps, content, found) for item in items]
        originals, hashed, served = found.originals, found.hashed, found.served
        without_request_id = found.without_request_id
        log.debug(
            "Asset batch (%s): %d of %d items replaced%s (asked for: %s; item fields: %s)",
            f"{request.coding}-compressed" if request.coding else "not compressed",
            len(originals) + len(served),
            len(items),
            f", {without_request_id} without a request ID left alone" if without_request_id else "",
            _listed(asked),
            _fields(items),
        )
        changed = None
        if originals:
            changed = replace(request, body=json.dumps(items, separators=(",", ":")).encode())
        if originals or hashed or served:
            # A batch with hash items is watched too: its response says which asset each was.
            sent_request = changed if changed is not None else request
            self._pending[id(sent_request)] = _Pending(
                sent_request, originals, hashed, swaps, served, content
            )
            while len(self._pending) > _PENDING_LIMIT:
                self._pending.popitem(last=False)
        return changed

    def _single_request(self, request: hyphae.Request) -> hyphae.Request | None:
        swaps, _content = self._active()
        if not swaps:
            return None
        target = request.target.decode("latin-1")
        path, mark, query = target.partition("?")
        path_match = _PATH_ID.match(path)
        query_match = _QUERY_ID.search(query) if mark else None
        match = path_match or query_match
        if match is None:
            log.debug("An asset request named no asset ID it could read; passed on unchanged")
            return None
        original = int(match.group(3) if match is query_match else match.group(2))
        replacement = swaps.get(original)
        log.debug(
            "Asset request for %d: %s",
            original,
            f"replaced by {replacement}" if replacement is not None else "no replacement",
        )
        if replacement is None:
            return None
        if path_match is not None:
            path = path_match.group(1) + str(replacement) + path[path_match.end() :]
        else:
            query = _QUERY_ID.sub(
                lambda m: m.group(1) + m.group(2) + str(replacement), query, count=1
            )
        return replace(request, target=(path + mark + query).encode("latin-1"))

    # --- Responses -------------------------------------------------------------------------

    def wants_response_body(self, request: hyphae.Request, response: hyphae.Response) -> bool:
        """Responses to the batches this grafter watches, and the content downloads it serves."""
        fetching = self._fetching.get(id(request))
        if fetching is not None:
            return fetching[0] is request
        pending = self._pending.get(id(request))
        return pending is not None and pending.request is request

    def on_response(
        self, request: hyphae.Request, response: hyphae.Response
    ) -> hyphae.Response | None:
        """Put each replaced item's original asset ID back; None if nothing changes.

        A content download Verdra serves gets the replacement's bytes instead.
        """
        if id(request) in self._fetching:
            return self._download_response(request, response)
        pending = self._pending.pop(id(request), None)
        if pending is None or pending.request is not request or response.body is None:
            return None
        originals = pending.originals
        items = _items(response.body)
        if items is None:
            if 200 <= response.status < 300:  # noqa: PLR2004 - a success that can't be mapped back
                self._unreadable("response", "not a JSON array of objects")
            return None
        mapped = 0
        changed = False
        for item in items:
            request_id = item.get(_REQUEST_ID)
            if _key(request_id) in pending.hashed:
                self._hash_answered(pending, item)
            if _key(request_id) in pending.served:
                self._content_located(pending, item)
            if request_id is None or _key(request_id) not in originals:
                continue
            mapped += 1
            if _ASSET_ID in item:
                original = originals[_key(request_id)]
                item[_ASSET_ID] = _like(original, item[_ASSET_ID])
                changed = True
        if originals:
            log.debug(
                "Asset batch response: %d of %d replaced items found by request ID "
                "(item fields: %s)",
                mapped,
                len(originals),
                _fields(items),
            )
        if not changed:
            return None
        return replace(response, body=json.dumps(items, separators=(",", ":")).encode())

    def on_unread(
        self, request: hyphae.Request, response: hyphae.Response | None, reason: str
    ) -> None:
        """roots/hyphae couldn't read a body the grafter asked for (see `wants_*_body`)."""
        if response is None:
            if _is_batch(request) and self._active()[0]:
                self._unreadable("request", reason)
            return
        fetching = self._fetching.pop(id(request), None)
        if fetching is not None and 200 <= response.status < 300:  # noqa: PLR2004
            log.warning(
                "%s",
                QCoreApplication.translate(
                    "M-GRAFT-08",
                    "Roblox downloaded asset {asset} in a format Verdra can't make yet ({format}), "
                    "so the original shows.",
                ).format(asset=fetching[1], format=reason),
            )
            if self.on_unreadable is not None:
                self.on_unreadable(reason)
            return
        pending = self._pending.pop(id(request), None)
        if (
            pending is not None
            and (pending.originals or pending.served)
            and pending.request is request
            and 200 <= response.status < 300  # noqa: PLR2004
        ):
            self._unreadable("response", reason)

    def _content_located(self, pending: _Pending, item: dict[str, Any]) -> None:
        """Remember where Roblox will download a replaced asset's content (S-21)."""
        original = pending.served[_key(item.get(_REQUEST_ID))]
        location = item.get(_LOCATION)
        parts = urlsplit(location) if isinstance(location, str) else None
        if parts is None or rules.host_name(parts.hostname or "") != rules.ASSET_CONTENT_HOST:
            where = parts.hostname if parts is not None and parts.hostname else "no address"
            log.warning(
                "%s",
                QCoreApplication.translate(
                    "M-GRAFT-07",
                    "Roblox was told to download asset {asset} from {host}, which Verdra doesn't "
                    "serve replacements on, so the original may show.",
                ).format(asset=original, host=where),
            )
            if self.on_unreadable is not None:
                self.on_unreadable(f"asset {original} downloads from {where}")
            return
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        self._downloads[target.encode("latin-1", "replace")] = (
            original,
            pending.content[original],
        )
        while len(self._downloads) > _DOWNLOADS_LIMIT:
            self._downloads.popitem(last=False)
        log.debug(
            "Asset %d's content will be downloaded from %s%s; Verdra serves its replacement",
            original,
            rules.ASSET_CONTENT_HOST,
            parts.path,
        )

    def _download_request(self, request: hyphae.Request) -> None:
        found = self._downloads.get(request.target)
        if found is not None:
            self._fetching[id(request)] = (request, *found)

    def _download_response(
        self, request: hyphae.Request, response: hyphae.Response
    ) -> hyphae.Response | None:
        _request, original, content = self._fetching.pop(id(request))
        body = response.body
        if not 200 <= response.status < 300 or body is None:  # noqa: PLR2004
            return None
        if body.startswith(_KTX2):
            served, kind = content.ktx2, "KTX2"
        elif body.startswith(_PNG):
            served, kind = content.png, "PNG"
        elif _FILEMESH.match(body):
            served, kind = content.mesh, "FileMesh"
        else:
            served, kind = b"", ""
        if kind and not served:
            log.warning(
                "%s",
                QCoreApplication.translate(
                    "M-GRAFT-12",
                    "Roblox downloaded asset {asset} as a {kind}, but its replacement is another "
                    "type of asset, so the original shows.",
                ).format(asset=original, kind="mesh" if kind == "FileMesh" else "picture"),
            )
            if self.on_unreadable is not None:
                self.on_unreadable(f"asset {original} replaced by another type")
            return None
        if not kind:
            log.warning(
                "%s",
                QCoreApplication.translate(
                    "M-GRAFT-08",
                    "Roblox downloaded asset {asset} in a format Verdra can't make yet ({format}), "
                    "so the original shows.",
                ).format(asset=original, format=_format_name(body)),
            )
            if self.on_unreadable is not None:
                self.on_unreadable(f"asset {original} in an unknown format")
            return None
        log.debug(
            "Served the replacement for asset %d (%s, %d bytes, from its %s)",
            original,
            kind,
            len(served),
            content.source,
        )
        headers = tuple((n, v) for n, v in response.headers if n.lower() not in _STALE_HEADERS)
        return replace(response, headers=headers, body=served)

    def _hash_answered(self, pending: _Pending, item: dict[str, Any]) -> None:
        """Log which asset a hash item turned out to be; never silent if it is a replaced one."""
        named = _as_id(item.get(_ASSET_ID))
        hash_text = pending.hashed[_key(item.get(_REQUEST_ID))]
        log.debug(
            "Asset batch response for hash %s: %s (item fields: %s)",
            hash_text,
            f"asset {named}" if named is not None else "names no asset ID",
            _fields([item]),
        )
        if named is None or named not in pending.swaps:
            return
        log.warning(
            "%s",
            QCoreApplication.translate(
                "M-GRAFT-05",
                "Roblox asked for the replaced asset {asset} by its content hash, which Verdra "
                "can't replace yet, so the original may show.",
            ).format(asset=named),
        )
        if self.on_unreadable is not None:
            self.on_unreadable(f"asset {named} asked for by hash")

    def _unreadable(self, where: str, reason: str) -> None:
        """A batch couldn't be read while a replacement is active: never silent (S-21)."""
        log.warning(
            "%s",
            QCoreApplication.translate(
                "M-GRAFT-04",
                "An asset batch {part} couldn't be read ({reason}), so replacements may not apply "
                "to it.",
            ).format(part=where, reason=reason),
        )
        if self.on_unreadable is not None:
            self.on_unreadable(reason)


def _is_batch(request: hyphae.Request) -> bool:
    return (
        rules.host_name(request.host) == rules.ASSET_BATCH_HOST
        and request.method == b"POST"
        and rules.canonical_path(request.target) == rules.ASSET_BATCH_PATH
        and not rules.is_protected(request.host, request.target)
    )


def _is_single(request: hyphae.Request) -> bool:
    if (
        rules.host_name(request.host) != rules.ASSET_BATCH_HOST
        or request.method != b"GET"
        or rules.is_protected(request.host, request.target)
    ):
        return False
    path = rules.canonical_path(request.target)
    return path in _SINGLE_QUERY_PATHS or _PATH_ID.match(path) is not None


def _note_hash(item: dict[str, Any], hashed: dict[Any, str]) -> None:
    """Remember and log an item asked for by hash instead of by asset ID."""
    if _HASH not in item:
        return
    hashed[_key(item.get(_REQUEST_ID))] = _hash_text(item[_HASH])
    log.debug(
        "Asset batch item asked for by hash: %s (asset type: %s)",
        hashed[_key(item.get(_REQUEST_ID))],
        _type_text(item.get(_ASSET_TYPE)),
    )


def _is_download(request: hyphae.Request) -> bool:
    return (
        rules.host_name(request.host) == rules.ASSET_CONTENT_HOST
        and request.method == b"GET"
        and not rules.is_protected(request.host, request.target)
    )


def _format_name(body: bytes) -> str:
    """A short, safe name for what a download holds (never its bytes)."""
    for magic, name in ((b"RIFF", "WebP or RIFF"), (b"\xff\xd8\xff", "JPEG"), (b"DDS ", "DDS")):
        if body.startswith(magic):
            return name
    return "unknown"


def _items(body: bytes) -> list[dict[str, Any]] | None:
    try:
        items = json.loads(body)
    except ValueError, UnicodeDecodeError:
        return None
    if isinstance(items, list) and all(isinstance(item, dict) for item in items):
        return items  # type: ignore[return-value]
    return None


def _hash_text(value: object) -> str:
    """A hash as logged: hex digits only; any other value is never written to the log."""
    if isinstance(value, str) and _HEX_HASH.fullmatch(value):
        return value.lower()
    return "(not a hex hash)"


def _type_text(value: object) -> str:
    """An asset type as logged: a short word or number only."""
    if isinstance(value, int | str) and re.fullmatch(r"[A-Za-z0-9]{1,40}", str(value)):
        return str(value)
    return "unknown"


def _listed(values: list[str]) -> str:
    shown = ", ".join(values[:_LOGGED_IDS])
    return shown + (f", and {len(values) - _LOGGED_IDS} more" if len(values) > _LOGGED_IDS else "")


def _fields(items: list[dict[str, Any]]) -> str:
    """The field names the items use (never their values), in first-seen order."""
    names: dict[str, None] = {}
    for item in items:
        names.update(dict.fromkeys(str(key) for key in item))
    return ", ".join(names) or "none"


def _as_id(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _key(request_id: object) -> object:
    return json.dumps(request_id, sort_keys=True)


def _like(original: object, current: object) -> object:
    """The original ID, in the response's own type (number or text)."""
    if isinstance(current, str):
        return str(original)
    return _as_id(original) if _as_id(original) is not None else original
