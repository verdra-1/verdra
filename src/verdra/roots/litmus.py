# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Diagnostics, source runs only, excluded from builds (decision 0015): diagnostic interception
(TLS details logged) and format capture (what the CDN sends for chosen assets).

Format capture (`--format-capture <asset IDs>`, plan 16.2 of 8 October 2026, spec S-21 test 18):
`FormatCapture` reports what Roblox's CDN really sends for chosen assets, which the grafter
leaves alone meanwhile (see the class).

Diagnostic interception:

Spec S-11 (tests 9 and 10), plan 16.2. It exists so the M1 gate can check verified TLS and ECDSA
leaf acceptance on real clients before any feature intercepts. The interception it builds
decrypts every host of plan 10.2, runs no symbiont (so every request and response passes
byte for byte), and writes the TLS details of both sides of each connection to Activity
(M-DIAG-02). `trunk/sapwood/cli` offers `--diagnose-interception` only while this module can be
imported from source; `packaging/verdra.spec` leaves it out of every build, and
`tools/check_build.py` fails if `MARKER` turns up anywhere in a built folder (decision record
0015).
"""

from __future__ import annotations

import json
import logging
import ssl
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal
from urllib.parse import urlsplit

import zstandard
from PySide6.QtCore import QCoreApplication

import verdra
from verdra.bark import veil
from verdra.roots import hyphae, rules
from verdra.strata import ochre

log = logging.getLogger(__name__)

#: Only this module carries this text; a built folder that contains it fails the build check.
MARKER: Final = "verdra/litmus: diagnostic interception, source only"
#: Plan 10.2 (roots/rules), the exact list confirmed by capture at M1.
HOSTS: Final = rules.ROBLOX_HOSTS
#: The leaf key S-10 issues (bark/resin), reported for the client side.
LEAF_KEY: Final = "ECDSA P-256"


class DiagnosticHosts(Collection[str]):
    """The 10.2 hosts, in any letter case and with or without a trailing dot."""

    def __contains__(self, host: object) -> bool:
        return isinstance(host, str) and rules.is_roblox_host(host)

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(HOSTS))

    def __len__(self) -> int:
        return len(HOSTS)


def interception(
    leaves: hyphae.LeafContexts,
    open_upstream: hyphae.Opener,
    *,
    idle_timeout: float = 30.0,
    on_verification_failure: Callable[[str, str], None] | None = None,
) -> hyphae.Interception:
    """Return the diagnostic interception: every 10.2 host, no symbionts, TLS details logged.

    `on_verification_failure` hears of every server certificate that fails (status Degraded).
    """
    hosts = DiagnosticHosts()
    return hyphae.Interception(
        leaves,
        lambda: hosts,
        open_upstream,
        hyphae.Pipeline,
        on_tls=log_tls,
        on_verification_failure=on_verification_failure,
        idle_timeout=idle_timeout,
    )


def log_tls(host: str, side: Literal["client", "upstream"], tls: ssl.SSLObject) -> None:
    """Write one side's TLS details to Activity (M-DIAG-02)."""
    cipher = tls.cipher()
    if side == "client":
        where = QCoreApplication.translate("M-DIAG-02", "Roblox to Verdra")
        detail = QCoreApplication.translate("M-DIAG-02", "Verdra's certificate, key {key}").format(
            key=LEAF_KEY
        )
    else:
        where = QCoreApplication.translate("M-DIAG-02", "Verdra to the server")
        verified = tls.context.verify_mode == ssl.CERT_REQUIRED and tls.context.check_hostname
        detail = (
            QCoreApplication.translate("M-DIAG-02", "the server's certificate verified")
            if verified
            else QCoreApplication.translate("M-DIAG-02", "the server's certificate not verified")
        )
    log.info(
        "%s",
        QCoreApplication.translate(
            "M-DIAG-02", "Diagnostic interception, {host} ({where}): {version}, {cipher}, {detail}."
        ).format(
            host=host,
            where=where,
            version=tls.version() or "?",
            cipher=cipher[0] if cipher else "?",
            detail=detail,
        ),
    )


# --- Format capture (--format-capture, plan 16.2, 8 October 2026) ---------------------------

#: A Zstandard frame starts with these four bytes (RFC 8878).
ZSTD_MAGIC: Final = b"\x28\xb5\x2f\xfd"
#: Report values are cut to this many characters (a batch item's metadata can be long).
_VALUE_LIMIT: Final = 2000
#: Item fields whose values could name the player or the place; the report shows their names only.
_PRIVATE_FIELDS: Final = frozenset({"serverplaceid", "requestid", "placeid", "universeid"})
_VK_NAMES: Final = {
    0: "UNDEFINED (Basis Universal)", 23: "R8G8B8_UNORM", 29: "R8G8B8_SRGB",
    37: "R8G8B8A8_UNORM", 43: "R8G8B8A8_SRGB", 131: "BC1_RGB_UNORM", 132: "BC1_RGB_SRGB",
    133: "BC1_RGBA_UNORM", 134: "BC1_RGBA_SRGB", 135: "BC2_UNORM", 136: "BC2_SRGB",
    137: "BC3_UNORM", 138: "BC3_SRGB", 139: "BC4_UNORM", 141: "BC5_UNORM", 145: "BC7_UNORM",
    146: "BC7_SRGB", 147: "ETC2_R8G8B8_UNORM", 148: "ETC2_R8G8B8_SRGB",
    151: "ETC2_R8G8B8A8_UNORM", 152: "ETC2_R8G8B8A8_SRGB", 157: "ASTC_4x4_UNORM",
    158: "ASTC_4x4_SRGB",
}  # fmt: skip
_COLOR_MODELS: Final = {
    1: "RGBSDA", 128: "BC1A", 129: "BC2", 130: "BC3", 131: "BC4", 132: "BC5", 134: "BC7",
    160: "ETC1", 161: "ETC2", 162: "ASTC", 163: "ETC1S", 166: "UASTC",
}  # fmt: skip


@dataclass
class _Watched:
    """One captured asset: what the batch asked for and answered, as the report shows it."""

    asset_id: int
    asked: dict[str, str]
    answered: dict[str, str] = field(default_factory=dict[str, str])
    location: str = ""
    downloads: int = 0


class FormatCapture:
    """A symbiont that writes what Roblox's CDN really sends for chosen assets (source runs only).

    It never changes anything: the batch items asking for the chosen asset IDs (as sent upstream,
    after the grafter) are noted with their answers, and when Roblox downloads one of them from
    the address its answer gave, the status, headers and body layout go into a text report in
    `folder` (M-DIAG-04). The grafter leaves the chosen originals alone meanwhile, so the real
    response reaches Roblox. With `save_bodies`, the body Verdra saw (after undoing any
    Content-Encoding) is saved next to the report.
    """

    name = "format capture"

    def __init__(self, ids: frozenset[int], folder: Path, *, save_bodies: bool = False) -> None:
        self.ids = ids
        self.folder = folder
        self.save_bodies = save_bodies
        #: The reports written so far.
        self.reports: list[Path] = []
        self._batches: dict[int, dict[str, _Watched]] = {}
        self._paths: dict[str, _Watched] = {}
        self._fetching: dict[int, _Watched] = {}

    def wants_request_body(self, request: hyphae.Request) -> bool:
        """Asset batches only."""
        return _is_batch(request)

    def on_request(self, request: hyphae.Request) -> None:
        """Note batch items asking for a chosen asset, and downloads of their content."""
        if _is_batch(request) and request.body is not None:
            watched = {
                str(item["requestId"]): _Watched(asset_id, _shown(item))
                for item in _json_items(request.body)
                if (asset_id := _asset_id(item)) in self.ids and "requestId" in item
            }
            if watched:
                self._batches[id(request)] = watched
        elif _is_download(request):
            found = self._paths.get(rules.canonical_path(request.target))
            if found is not None:
                self._fetching[id(request)] = found

    def wants_response_body(self, request: hyphae.Request, response: hyphae.Response) -> bool:
        """The answers to the batches and downloads noted."""
        return id(request) in self._batches or id(request) in self._fetching

    def on_response(self, request: hyphae.Request, response: hyphae.Response) -> None:
        """Note the batch answers; write a report for each download of a chosen asset."""
        watched = self._batches.pop(id(request), None)
        if watched is not None and response.body is not None:
            for item in _json_items(response.body):
                found = watched.get(str(item.get("requestId")))
                if found is None:
                    continue
                found.answered = _shown(item)
                location = item.get("location")
                if isinstance(location, str):
                    parts = urlsplit(location)
                    found.location = f"{parts.hostname}{parts.path}"
                    self._paths[rules.canonical_path(parts.path or "/")] = found
        fetching = self._fetching.pop(id(request), None)
        if fetching is not None:
            self._write(fetching, request, response)

    def _write(self, watched: _Watched, request: hyphae.Request, response: hyphae.Response) -> None:
        watched.downloads += 1
        stem = f"format-capture-{watched.asset_id}-{watched.downloads}"
        text = report(watched, request, response)
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            path = self.folder / f"{stem}.txt"
            path.write_text(text, encoding="utf-8")
            if self.save_bodies and response.body is not None:
                (self.folder / f"{stem}.bin").write_bytes(response.body)
        except OSError as error:
            log.warning(
                "%s",
                QCoreApplication.translate(
                    "M-DIAG-05", "Format capture of asset {asset} couldn't be written: {reason}."
                ).format(asset=watched.asset_id, reason=error.strerror or type(error).__name__),
            )
            return
        self.reports.append(path)
        log.info(
            "%s",
            QCoreApplication.translate(
                "M-DIAG-04", "Format capture of asset {asset} written to {file}."
            ).format(asset=watched.asset_id, file=path),
        )


def report(watched: _Watched, request: hyphae.Request, response: hyphae.Response) -> str:
    """The text report of one captured download (no personal values: see `_shown`)."""
    path, _mark, query = request.target.decode("latin-1").partition("?")
    names = [part.split("=", 1)[0] for part in query.split("&") if part]
    lines = [
        f"Verdra {verdra.__version__} format capture, {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        "",
        f"Asset {watched.asset_id}",
        "",
        "Batch item as sent to Roblox:",
        *_pairs(watched.asked),
        "Batch answer for it:",
        *_pairs(watched.answered),
        f"  location: {watched.location or '(none)'} (query values left out)",
        "",
        f"Download: {request.method.decode('latin-1')} {request.host}{_hidden(path)}",
        f"  query names: {', '.join(names) or '(none)'}",
        *(f"  > {name}: {value}" for name, value in _headers(request.headers)),
        "",
        f"Response: {response.status} {response.reason.decode('latin-1', 'replace')}",
        *(f"  < {name}: {value}" for name, value in _headers(response.headers)),
        "",
        *body_lines(response.body),
    ]
    return "\n".join(lines) + "\n"


def body_lines(body: bytes | None) -> list[str]:
    """What a downloaded body is: size, zstd framing, and the KTX2 layout inside."""
    if body is None:
        return ["Body: not read (over 64 MB, or in an encoding Verdra can't undo)"]
    framed = "yes" if body.startswith(ZSTD_MAGIC) else "no"
    lines = [
        f"Body (after Verdra undid any Content-Encoding): {len(body)} bytes",
        f"  first 16 bytes: {body[:16].hex(' ')}",
        f"  starts with the zstd magic 28 B5 2F FD: {framed}",
    ]
    inner = body
    if body.startswith(ZSTD_MAGIC):
        try:
            inner = zstandard.ZstdDecompressor().decompress(
                body, max_output_size=ochre.MAX_DECOMPRESSED
            )
        except zstandard.ZstdError as error:
            return [*lines, f"  zstd: couldn't be decompressed ({error})"]
        lines += [
            f"  decompressed (zstd): {len(inner)} bytes",
            f"  first 16 bytes after: {inner[:16].hex(' ')}",
        ]
    if not inner.startswith(ochre.KTX2_IDENTIFIER):
        return [*lines, "  not a KTX2 file"]
    try:
        layout = ochre.ktx2_layout(inner)
    except ochre.OchreError as error:
        return [*lines, f"  KTX2: {error}"]
    return lines + ktx2_lines(layout, inner)


def ktx2_lines(layout: ochre.Ktx2Layout, data: bytes) -> list[str]:
    """A KTX2 layout, one fact a line."""
    scheme = ochre.SUPERCOMPRESSION_NAMES.get(layout.supercompression, "unknown")
    dfd = dict(layout.dfd)
    model = dfd.get("colorModel")
    lines = [
        "KTX2:",
        f"  vkFormat: {layout.vk_format} ({_VK_NAMES.get(layout.vk_format, 'unknown')})",
        f"  typeSize: {layout.type_size}",
        f"  pixel size: {layout.width} x {layout.height} x {layout.depth}",
        f"  layers: {layout.layers}, faces: {layout.faces}, levels: {layout.levels}",
        f"  supercompressionScheme: {layout.supercompression} ({scheme})",
        f"  DFD: offset {layout.dfd_offset}, length {layout.dfd_length}; "
        f"key/value data: offset {layout.kvd_offset}, length {layout.kvd_length}; "
        f"supercompression global data: offset {layout.sgd_offset}, length {layout.sgd_length}",
        f"  DFD block: {', '.join(f'{k} {v}' for k, v in dfd.items()) or '(none)'}"
        + (f" (color model {_COLOR_MODELS.get(model, 'unknown')})" if model is not None else ""),
        f"  DFD samples: {layout.samples}",
        f"  keys: {', '.join(layout.keys) or '(none)'}",
        "  level index (offset, length, uncompressed length, starts with zstd magic):",
    ]
    for number, level in enumerate(layout.level_index):
        magic = data[level.offset : level.offset + 4] == ZSTD_MAGIC
        lines.append(
            f"    {number}: {level.offset}, {level.length}, {level.uncompressed_length}, "
            f"{'yes' if magic else 'no'}"
        )
    return lines


def _json_items(body: bytes) -> list[dict[str, Any]]:
    try:
        items = json.loads(body)
    except ValueError, UnicodeDecodeError:
        return []
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _asset_id(item: dict[str, Any]) -> int | None:
    value = item.get("assetId")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return int(value) if isinstance(value, str) and value.isdigit() else None


def _shown(item: dict[str, Any]) -> dict[str, str]:
    """An item's fields as the report shows them: private values hidden, long ones cut."""
    shown: dict[str, str] = {}
    for key, value in item.items():
        if key.lower() in _PRIVATE_FIELDS:
            shown[key] = "(hidden)"
        elif key == "location":
            continue  # shown as host and path only
        else:
            text = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
            text = veil.redact_text(text)
            shown[key] = text if len(text) <= _VALUE_LIMIT else text[:_VALUE_LIMIT] + " (cut)"
    return shown


def _pairs(fields: dict[str, str]) -> list[str]:
    return [f"  {key}: {value}" for key, value in fields.items()] or ["  (nothing)"]


def _headers(headers: hyphae.Headers) -> list[tuple[str, str]]:
    """Header names and values, redacted, with long numbers (place or user IDs) hidden."""
    pairs = [(n.decode("latin-1"), v.decode("latin-1", "replace")) for n, v in headers]
    return [(name, veil.anonymize_text(value)) for name, value in veil.redact_headers(pairs)]


def _hidden(path: str) -> str:
    return veil.redact_text(path)


def _is_batch(request: hyphae.Request) -> bool:
    return (
        rules.host_name(request.host) == rules.ASSET_BATCH_HOST
        and request.method == b"POST"
        and rules.canonical_path(request.target) == rules.ASSET_BATCH_PATH
        and not rules.is_protected(request.host, request.target)
    )


def _is_download(request: hyphae.Request) -> bool:
    return (
        rules.host_name(request.host) == rules.ASSET_CONTENT_HOST
        and request.method == b"GET"
        and not rules.is_protected(request.host, request.target)
    )


#: The hosts a format capture needs decrypted, whatever the replacements are.
CAPTURE_HOSTS: Final = frozenset({rules.ASSET_BATCH_HOST, rules.ASSET_CONTENT_HOST})
