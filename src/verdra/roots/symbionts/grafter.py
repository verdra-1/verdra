# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Rewrites asset batch requests and responses; serves replacement content.

Spec S-21. This part swaps asset IDs: in a batch request (`POST /v1/assets/batch` on
`assetdelivery.roblox.com`, fact V1), each item whose asset ID has a replacement asks for the
target ID instead, and every other field of the item is kept. The response is mapped back by
each item's request ID, so the client receives the content for the item it asked for, with the
original ID wherever the response names one.

Anything the grafter doesn't recognize (a body that isn't a JSON array of objects, a compressed
request, a response it can't map back) passes through unchanged (rule 4). Everything it needs is
in the snapshot it read when the request arrived; it does no disk or network work (rule 2).
"""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from dataclasses import replace
from typing import Any, Final

from verdra.roots import hyphae, rules

log = logging.getLogger(__name__)

#: Batches waiting for their response; old ones are forgotten (an upstream that never answered).
_PENDING_LIMIT: Final = 1024
_ASSET_ID: Final = "assetId"
_REQUEST_ID: Final = "requestId"


class Grafter:
    """The grafter symbiont (Reference R1, roots/symbionts/grafter)."""

    name = "grafter"

    def __init__(self, holder: rules.SnapshotHolder) -> None:
        self.holder = holder
        # id(request) -> (the request, {request ID: the original asset ID as the client sent it})
        self._pending: OrderedDict[int, tuple[hyphae.Request, dict[Any, Any]]] = OrderedDict()
        self._noted: set[str] = set()

    # --- Requests --------------------------------------------------------------------------

    def wants_request_body(self, request: hyphae.Request) -> bool:
        """Only asset batches, and only while some asset ID has a replacement."""
        return _is_batch(request) and bool(self.holder.current.swaps())

    def on_request(self, request: hyphae.Request) -> hyphae.Request | None:
        """Ask for each replaced asset's target instead; None if nothing changes."""
        if request.body is None or not _is_batch(request) or _encoded(request.headers):
            return None
        swaps = self.holder.current.swaps()
        items = self._items(request.body, "request")
        if items is None or not swaps:
            return None
        originals: dict[Any, Any] = {}
        for item in items:
            sent = item.get(_ASSET_ID)
            asset_id = _as_id(sent)
            if asset_id is None or asset_id not in swaps or _REQUEST_ID not in item:
                continue
            target = swaps[asset_id]
            item[_ASSET_ID] = str(target) if isinstance(sent, str) else target
            originals[_key(item[_REQUEST_ID])] = sent
        if not originals:
            return None
        changed = replace(request, body=json.dumps(items, separators=(",", ":")).encode())
        self._pending[id(changed)] = (changed, originals)
        while len(self._pending) > _PENDING_LIMIT:
            self._pending.popitem(last=False)
        log.debug("Asset batch: %d of %d items replaced", len(originals), len(items))
        return changed

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
        items = self._items(response.body, "response")
        if items is None:
            return None
        changed = False
        for item in items:
            request_id = item.get(_REQUEST_ID)
            if request_id is None or _key(request_id) not in originals:
                continue
            if _ASSET_ID in item:
                original = originals[_key(request_id)]
                item[_ASSET_ID] = _like(original, item[_ASSET_ID])
                changed = True
        if not changed:
            return None
        return replace(response, body=json.dumps(items, separators=(",", ":")).encode())

    def _items(self, body: bytes, where: str) -> list[dict[str, Any]] | None:
        try:
            items = json.loads(body)
        except ValueError, UnicodeDecodeError:
            items = None
        if isinstance(items, list) and all(isinstance(item, dict) for item in items):
            return items  # type: ignore[return-value]
        if where not in self._noted:  # once per session (rule 4)
            self._noted.add(where)
            log.debug(
                "An asset batch %s wasn't a JSON array of objects; passed on unchanged", where
            )
        return None


def _is_batch(request: hyphae.Request) -> bool:
    return (
        rules.host_name(request.host) == rules.ASSET_BATCH_HOST
        and request.method == b"POST"
        and rules.canonical_path(request.target) == rules.ASSET_BATCH_PATH
        and not rules.is_protected(request.host, request.target)
    )


def _encoded(headers: hyphae.Headers) -> bool:
    return any(
        name.lower() == b"content-encoding" and value.strip().lower() not in (b"", b"identity")
        for name, value in headers
    )


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
