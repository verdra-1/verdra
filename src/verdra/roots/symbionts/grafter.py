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
from collections.abc import Callable
from dataclasses import replace
from typing import Any, Final

from PySide6.QtCore import QCoreApplication

from verdra.roots import hyphae, rules

log = logging.getLogger(__name__)

#: Batches waiting for their response; old ones are forgotten (an upstream that never answered).
_PENDING_LIMIT: Final = 1024
_ASSET_ID: Final = "assetId"
_REQUEST_ID: Final = "requestId"
#: At most this many asset IDs per log line, so one large batch stays one readable line.
_LOGGED_IDS: Final = 100
#: Single-asset requests: `/v1/asset/?id=…` (and v2), and `/v1/assetId/<id>` (and v2).
_SINGLE_QUERY_PATHS: Final = frozenset({"/v1/asset", "/v2/asset"})
_QUERY_ID = re.compile(r"(?i)(^|&)(id=)(\d+)(?=&|$)")
_PATH_ID = re.compile(r"(?i)^(/v[12]/assetid/)(\d+)(?=/|$)")


class Grafter:
    """The grafter symbiont (Reference R1, roots/symbionts/grafter)."""

    name = "grafter"

    def __init__(
        self,
        holder: rules.SnapshotHolder,
        on_unreadable: Callable[[str], None] | None = None,
    ) -> None:
        self.holder = holder
        #: Called (on the proxy's thread) with the reason whenever a batch couldn't be read while
        #: a replacement is active; the routing status turns Degraded (S-14).
        self.on_unreadable = on_unreadable
        # id(request) -> (the request, {request ID: the original asset ID as the client sent it})
        self._pending: OrderedDict[int, tuple[hyphae.Request, dict[Any, Any]]] = OrderedDict()

    # --- Requests --------------------------------------------------------------------------

    def wants_request_body(self, request: hyphae.Request) -> bool:
        """Only asset batches, and only while some asset ID has a replacement."""
        return _is_batch(request) and bool(self.holder.current.swaps())

    def on_request(self, request: hyphae.Request) -> hyphae.Request | None:
        """Ask for each replaced asset's target instead; None if nothing changes."""
        if _is_batch(request):
            return self._batch_request(request)
        if _is_single(request):
            return self._single_request(request)
        return None

    def _batch_request(self, request: hyphae.Request) -> hyphae.Request | None:
        swaps = self.holder.current.swaps()
        if not swaps:
            return None
        if request.body is None:
            self._unreadable("request", "over 64 MB")
            return None
        items = _items(request.body)
        if items is None:
            self._unreadable("request", "not a JSON array of objects")
            return None
        originals: dict[Any, Any] = {}
        asked: list[str] = []
        without_request_id = 0
        for item in items:
            sent = item.get(_ASSET_ID)
            asset_id = _as_id(sent)
            asked.append(str(sent) if asset_id is not None else "?")
            if asset_id is None or asset_id not in swaps:
                continue
            if _REQUEST_ID not in item:
                without_request_id += 1
                continue
            target = swaps[asset_id]
            item[_ASSET_ID] = str(target) if isinstance(sent, str) else target
            originals[_key(item[_REQUEST_ID])] = sent
            asked[-1] += f"->{target}"
        log.debug(
            "Asset batch (%s): %d of %d items replaced%s (asked for: %s; item fields: %s)",
            f"{request.coding}-compressed" if request.coding else "not compressed",
            len(originals),
            len(items),
            f", {without_request_id} without a request ID left alone" if without_request_id else "",
            _listed(asked),
            _fields(items),
        )
        if not originals:
            return None
        changed = replace(request, body=json.dumps(items, separators=(",", ":")).encode())
        self._pending[id(changed)] = (changed, originals)
        while len(self._pending) > _PENDING_LIMIT:
            self._pending.popitem(last=False)
        return changed

    def _single_request(self, request: hyphae.Request) -> hyphae.Request | None:
        swaps = self.holder.current.swaps()
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
        """Only the responses to batches this grafter changed."""
        return id(request) in self._pending and self._pending[id(request)][0] is request

    def on_response(
        self, request: hyphae.Request, response: hyphae.Response
    ) -> hyphae.Response | None:
        """Put each replaced item's original asset ID back; None if nothing changes."""
        pending = self._pending.pop(id(request), None)
        if pending is None or pending[0] is not request or response.body is None:
            return None
        originals = pending[1]
        items = _items(response.body)
        if items is None:
            if 200 <= response.status < 300:  # noqa: PLR2004 - a success that can't be mapped back
                self._unreadable("response", "not a JSON array of objects")
            return None
        mapped = 0
        changed = False
        for item in items:
            request_id = item.get(_REQUEST_ID)
            if request_id is None or _key(request_id) not in originals:
                continue
            mapped += 1
            if _ASSET_ID in item:
                original = originals[_key(request_id)]
                item[_ASSET_ID] = _like(original, item[_ASSET_ID])
                changed = True
        log.debug(
            "Asset batch response: %d of %d replaced items found by request ID (item fields: %s)",
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
            if _is_batch(request) and self.holder.current.swaps():
                self._unreadable("request", reason)
            return
        pending = self._pending.pop(id(request), None)
        if pending is not None and pending[0] is request and 200 <= response.status < 300:  # noqa: PLR2004
            self._unreadable("response", reason)

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


def _items(body: bytes) -> list[dict[str, Any]] | None:
    try:
        items = json.loads(body)
    except ValueError, UnicodeDecodeError:
        return None
    if isinstance(items, list) and all(isinstance(item, dict) for item in items):
        return items  # type: ignore[return-value]
    return None


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
