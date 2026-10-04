# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Immutable rule snapshot types shared by trunk and the proxy.

So far: the hosts of plan 10.2, which the diagnostic interception (S-11) and the coexistence
check (S-15) both use.
"""

from __future__ import annotations

from typing import Final

#: Plan 10.2: the hosts Verdra may decrypt while a feature needs them. The asset CDN hosts are
#: matched by suffix until capture confirms the exact list (plan 10.2, M1).
ROBLOX_HOSTS: Final = frozenset(
    {
        "assetdelivery.roblox.com",
        "clientsettings.roblox.com",
        "clientsettingscdn.roblox.com",
        "gamejoin.roblox.com",
        "apis.roblox.com",
    }
)
CDN_SUFFIX: Final = ".rbxcdn.com"


def is_roblox_host(host: str) -> bool:
    """Return whether `host` is one of plan 10.2's hosts (any CDN host under rbxcdn.com)."""
    name = host.lower().rstrip(".")
    return name in ROBLOX_HOSTS or name.endswith(CDN_SUFFIX)
