# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Linux: paused, planned later; every module returns "unsupported on this system".

Decision record 0018 (Master plan 16.2, 5 October 2026): Windows is the only platform until
further notice, and Linux is paused like macOS. Nothing Linux-specific is built, tested,
packaged or released while it is paused. The package stays so the Platform protocol keeps three
implementations and Linux can return without restructuring. `PLATFORM` and every module's
`support()` answer with the same `Unsupported` result.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from typing import TYPE_CHECKING, Final, Literal

from verdra.soil import humus

if TYPE_CHECKING:
    import ssl
    from pathlib import Path

#: What every job answers on Linux while it is paused (decision record 0018).
UNSUPPORTED: Final = humus.Unsupported(system="linux", reason="paused")


class Tundra:
    """The Linux platform, paused: it reports itself unsupported."""

    @property
    def system(self) -> Literal["linux"]:
        """The system this package is for."""
        return "linux"

    @property
    def name(self) -> str:
        """The system's name as people read it in messages (M-PLAT-01)."""
        return "Linux"

    def support(self) -> humus.Unsupported | None:
        """Return why Verdra doesn't run on Linux."""
        return UNSUPPORTED

    def prefers_reduced_motion(self) -> bool | None:
        """Return None: nothing is read from an unsupported system."""
        return None

    def load_cert_chain(self, context: ssl.SSLContext, certificate: bytes, key: bytes) -> None:
        """Refuse: Linux is paused (decision record 0018)."""
        raise NotImplementedError(UNSUPPORTED)

    def roblox_clients(self) -> list[humus.RobloxClient] | humus.Unsupported:
        """Return why not: Linux is paused."""
        return UNSUPPORTED

    def trust_files_in(self, version_folder: Path) -> list[Path]:
        """Return none: Linux is paused."""
        return []

    def launch_roblox(
        self,
        client: humus.RobloxClient,
        link: str | None,
        proxy_port: int,
        environment: Mapping[str, str],
        spawn: humus.Spawn = subprocess.Popen,
    ) -> int:
        """Refuse: Linux is paused (decision record 0018)."""
        raise NotImplementedError(UNSUPPORTED)

    def link_handler(self) -> humus.LinkHandler | humus.Unsupported:
        """Return why not: Linux is paused."""
        return UNSUPPORTED

    def hosts_file(self) -> Path:
        """Refuse: Linux is paused (decision record 0018)."""
        raise NotImplementedError(UNSUPPORTED)

    def running_clients(
        self, client: humus.RobloxClient
    ) -> list[humus.RunningClient] | humus.Unsupported:
        """Return why not: Linux is paused."""
        return UNSUPPORTED

    def roblox_processes(self) -> humus.RobloxProcesses | humus.Unsupported:
        """Return why not: this system is not supported."""
        return UNSUPPORTED

    def roblox_cache_files(self) -> list[Path] | humus.Unsupported:
        """Return why not: this system is not supported."""
        return UNSUPPORTED


PLATFORM: Final = Tundra()
