# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Immutable rule snapshot types shared by trunk and the proxy.

The hosts of plan 10.2, which the interception (S-11, S-21) and the coexistence check (S-15)
use; the protected endpoints (plan 16.2) that no feature may touch; and the replacement snapshot
(S-21) that trunk compiles and the proxy reads.
"""

from __future__ import annotations

import itertools
import posixpath
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal
from urllib.parse import unquote

#: Plan 10.2: the hosts Verdra may decrypt while a feature needs them, exactly as confirmed by
#: capture on Windows at M1 (plan 16.2, "Stage 2 on Windows"). Any other host is a tunnel.
ROBLOX_HOSTS: Final = frozenset(
    {
        "apis.roblox.com",
        "assetdelivery.roblox.com",
        "clientsettings.roblox.com",
        "clientsettingscdn.roblox.com",
        "gamejoin.roblox.com",
        "apis.rbxcdn.com",
        "fts.rbxcdn.com",
        "tr.rbxcdn.com",
        "sc0.rbxcdn.com",
        "sc0ak.rbxcdn.com",
        "sc0aws.rbxcdn.com",
        "sc2.rbxcdn.com",
        "sc5.rbxcdn.com",
    }
)

#: Plan 16.2: Roblox's own integrity and safety traffic, seen in the Stage 2 capture. Requests
#: to these paths (and below them) pass through byte-for-byte; no symbiont ever sees them.
PROTECTED_PATHS: Final = frozenset(
    {
        ("apis.roblox.com", "/validate-machine"),  # machine validation
        ("apis.roblox.com", "/rm3-evidence-filter"),  # screenshot evidence uploads
        ("apis.roblox.com", "/realtime-replay-api"),  # replay recording for safety reports
        ("apis.roblox.com", "/account-security-service"),  # account security prompts
        ("apis.roblox.com", "/browser-tracker-api"),  # device identification
    }
)


class ProtectedEndpointError(ValueError):
    """A rule tried to touch one of Roblox's integrity or safety endpoints."""


def host_name(host: str) -> str:
    """Return `host` in the form the lists above use: lowercase, no trailing dot."""
    return host.lower().rstrip(".")


def is_roblox_host(host: str) -> bool:
    """Return whether `host` is one of plan 10.2's hosts."""
    return host_name(host) in ROBLOX_HOSTS


def canonical_paths(target: str | bytes) -> list[str]:
    """Return every path a server could resolve a request target to, most decoded last.

    The query and fragment are dropped; then, at each depth of percent-decoding (none, once,
    up to four times), the path is case folded, repeated slashes and dot segments resolved,
    and backslashes and path parameters taken both literally and as servers may read them.
    `//X/../Validate-Machine/` and `/%76alidate-machine?a` both give `/validate-machine`.
    """
    text = target.decode("latin-1") if isinstance(target, bytes) else target
    if "://" in text:  # absolute form: drop the scheme and authority
        text = "/" + text.split("://", 1)[1].partition("/")[2]
    text = text.split("#", 1)[0].split("?", 1)[0]
    forms = [text]
    for _ in range(4):
        decoded = unquote(forms[-1])
        if decoded == forms[-1]:
            break
        forms.append(decoded)
    paths: list[str] = []
    for form in forms:
        # Servers differ on "?" after decoding, backslashes and path parameters: try each way.
        for raw in itertools.product(
            (form, form.split("?", 1)[0]),
            (False, True),
            (False, True),
        ):
            text, backslash, parameters = raw
            folded = text.lower()
            if backslash:
                folded = folded.replace("\\", "/")
            if parameters:
                folded = re.sub(r";[^/]*", "", folded)
            path = "/" + posixpath.normpath("/" + folded).lstrip("/")
            if path not in paths:
                paths.append(path)
    return paths


def canonical_path(target: str | bytes) -> str:
    """Return the most decoded of `canonical_paths(target)`."""
    return canonical_paths(target)[-1]


def is_protected(host: str, target: str | bytes) -> bool:
    """Return whether a request for `target` on `host` is a protected endpoint (plan 16.2).

    A path is protected when any way of resolving it is a listed path or below it.
    """
    name = host_name(host)
    return any(
        name == protected_host and (path == prefix or path.startswith(prefix + "/"))
        for path in canonical_paths(target)
        for protected_host, prefix in PROTECTED_PATHS
    )


def refuse_protected(host: str, target: str | bytes) -> None:
    """Raise `ProtectedEndpointError` if a rule for `host` and `target` would touch a
    protected endpoint. Every rule a feature makes passes through here (plan 16.2)."""
    if is_protected(host, target):
        raise ProtectedEndpointError(f"{host_name(host)}{canonical_path(target)}")


# --- Replacements (specs S-20, S-21) -------------------------------------------------------------

#: Plan 10.2: where asset batches are rewritten, and where asset content is served from (V1).
ASSET_BATCH_HOST: Final = "assetdelivery.roblox.com"
ASSET_BATCH_PATH: Final = "/v1/assets/batch"
ASSET_CONTENT_HOST: Final = "fts.rbxcdn.com"

TargetKind = Literal["asset_id", "file", "url", "remove"]
Slot = Literal["color", "normal", "metalness", "roughness"]
#: An original asset, and the TexturePack map it names (None for the whole asset).
Original = tuple[int, Slot | None]


@dataclass(frozen=True, slots=True)
class Graft:
    """One replacement as the proxy uses it: the original, and what to send instead."""

    original: int
    slot: Slot | None
    kind: TargetKind
    #: The target asset ID in decimal, a file path, an HTTPS URL, or "" for remove.
    value: str
    #: Where it comes from, for Preview changes and warnings.
    profile: str
    replacement: str
    #: The original's asset type as the profile names it ("Image", "Mesh"…), for Preview changes.
    asset_type: str = ""


@dataclass(frozen=True, slots=True)
class GraftSnapshot:
    """The winning replacement for each original, and the ones each winner overrides (S-23).

    Immutable: the proxy reads one snapshot for a whole request, and a new one is swapped in
    whole (S-21).
    """

    grafts: Mapping[Original, Graft] = field(default_factory=lambda: MappingProxyType({}))
    overridden: Mapping[Original, tuple[Graft, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def swaps(self) -> dict[int, int]:
        """Return {original asset ID: target asset ID} for the whole-asset ID swaps."""
        return {
            graft.original: int(graft.value)
            for (original, slot), graft in self.grafts.items()
            if slot is None and graft.kind == "asset_id"
        }

    def hosts(self) -> frozenset[str]:
        """Return the hosts this snapshot needs decrypted (plan 10.1: only what a feature uses)."""
        if not self.grafts:
            return frozenset()
        if all(g.kind == "asset_id" and g.slot is None for g in self.grafts.values()):
            return frozenset({ASSET_BATCH_HOST})
        return frozenset({ASSET_BATCH_HOST, ASSET_CONTENT_HOST})


class SnapshotHolder:
    """The current snapshot, published from the Qt thread and read on the proxy's thread.

    Replacing the attribute is one reference assignment, so a reader sees the old snapshot or the
    new one, never a mix.
    """

    def __init__(self) -> None:
        self.current = GraftSnapshot()

    def publish(self, snapshot: GraftSnapshot) -> None:
        """Make `snapshot` the one every new request uses."""
        self.current = snapshot
