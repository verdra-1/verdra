# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Roblox web client (httpx): exact-domain cookies, CSRF refresh, timeouts, rate limits.

This first part is the asset lookup the replacement editor triggers (spec S-22; Master plan,
Settings › Privacy: "asset lookups the user triggers"): the type of one asset, from Roblox's
public asset details. It sends no cookie and no account, only a User-Agent naming Verdra; the
login part of the client (cookies for `.roblox.com` only, CSRF refresh) comes with Accounts.

Types are Roblox's public `Enum.AssetType` numbers. Content replacements (a file, a link) can
only stand in for a picture (Image), a mesh (Mesh) or a sound (Audio); an Asset ID replacement
must have the original's type.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from typing import Final

import httpx
import truststore

#: Public asset details (no sign-in needed): {"AssetTypeId": n, ...}.
DETAILS_URL: Final = "https://economy.roblox.com/v2/assets/{asset_id}/details"
#: Plan 10.6: timeouts of 5 s to connect and 15 s in all.
TIMEOUT: Final = httpx.Timeout(15.0, connect=5.0)

#: Enum.AssetType -> the family a content replacement must match ("" when none can).
FAMILIES: Final[dict[int, str]] = {1: "Image", 3: "Audio", 4: "Mesh"}
#: Enum.AssetType numbers with a name the editor shows (others are "another kind of item").
NAMES: Final[dict[int, str]] = {
    1: "picture",
    3: "sound",
    4: "mesh",
    10: "model",
    13: "decal",
    24: "keyframe animation",
    40: "mesh part",
    62: "video",
    63: "texture pack",
}


class PollinatorError(OSError):
    """Roblox couldn't be reached or answered unexpectedly; the message is the plain reason."""


@dataclass(frozen=True, slots=True)
class AssetKind:
    """What Roblox says an asset is."""

    type_id: int

    @property
    def family(self) -> str:
        """The family a file or link can replace ("Image", "Mesh" or "Audio"), else ""."""
        return FAMILIES.get(self.type_id, "")


def _client() -> httpx.Client:
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return httpx.Client(
        verify=context,
        timeout=TIMEOUT,
        follow_redirects=False,
        headers={"User-Agent": "Verdra", "Accept": "application/json"},
    )


def asset_kind(asset_id: int, client: httpx.Client | None = None) -> AssetKind | None:
    """Return what kind of asset `asset_id` is, or None if Roblox has no such asset.

    Raises:
        PollinatorError: Roblox couldn't be reached, or answered something unexpected.
    """
    owned = client is None
    client = client or _client()
    try:
        response = client.get(DETAILS_URL.format(asset_id=int(asset_id)))
    except httpx.HTTPError as error:
        msg = f"Roblox couldn't be reached ({type(error).__name__})"
        raise PollinatorError(msg) from error
    finally:
        if owned:
            client.close()
    if response.status_code in {400, 404}:
        return None
    if response.status_code != 200:  # noqa: PLR2004
        msg = f"Roblox answered {response.status_code}"
        raise PollinatorError(msg)
    try:
        type_id = response.json()["AssetTypeId"]
    except (ValueError, KeyError, TypeError) as error:
        msg = "Roblox's answer had no asset type"
        raise PollinatorError(msg) from error
    if not isinstance(type_id, int) or isinstance(type_id, bool):
        msg = "Roblox's answer had no asset type"
        raise PollinatorError(msg)
    return AssetKind(type_id)
