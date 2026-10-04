# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Immutable rule snapshot types shared by trunk and the proxy.

So far: the hosts of plan 10.2, which the diagnostic interception (S-11) and the coexistence
check (S-15) both use, and the protected endpoints (plan 16.2) that no feature may touch.
"""

from __future__ import annotations

import itertools
import posixpath
import re
from typing import Final
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
