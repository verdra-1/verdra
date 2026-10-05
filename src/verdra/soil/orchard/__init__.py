# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""macOS: deferred until after 1.0; every module returns "unsupported on this system".

Decision record 0014 (Master plan 16.2): nothing macOS-specific is built, tested, packaged or
released before the deferral is lifted. The package stays so the Platform protocol keeps three
implementations and macOS can return without restructuring. `PLATFORM` and every module's
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

#: What every job answers on macOS while it is deferred (decision record 0014).
UNSUPPORTED: Final = humus.Unsupported(system="macos", reason="deferred")


class Orchard:
    """The macOS platform, deferred: it reports itself unsupported."""

    @property
    def system(self) -> Literal["macos"]:
        """The system this package is for."""
        return "macos"

    @property
    def name(self) -> str:
        """The system's name as people read it in messages (M-PLAT-01)."""
        return "macOS"

    def support(self) -> humus.Unsupported | None:
        """Return why Verdra doesn't run on macOS."""
        return UNSUPPORTED

    def prefers_reduced_motion(self) -> bool | None:
        """Return None: nothing is read from an unsupported system."""
        return None

    def load_cert_chain(self, context: ssl.SSLContext, certificate: bytes, key: bytes) -> None:
        """Refuse: macOS is deferred until after 1.0 (decision record 0014)."""
        raise NotImplementedError(UNSUPPORTED)

    def roblox_clients(self) -> list[humus.RobloxClient] | humus.Unsupported:
        """Return why not: macOS is deferred."""
        return UNSUPPORTED

    def trust_files_in(self, version_folder: Path) -> list[Path]:
        """Return none: macOS is deferred."""
        return []

    def launch_roblox(
        self,
        client: humus.RobloxClient,
        link: str | None,
        proxy_port: int,
        environment: Mapping[str, str],
        spawn: humus.Spawn = subprocess.Popen,
    ) -> int:
        """Refuse: macOS is deferred until after 1.0 (decision record 0014)."""
        raise NotImplementedError(UNSUPPORTED)

    def link_handler(self) -> humus.LinkHandler | humus.Unsupported:
        """Return why not: macOS is deferred."""
        return UNSUPPORTED

    def hosts_file(self) -> Path:
        """Refuse: macOS is deferred until after 1.0 (decision record 0014)."""
        raise NotImplementedError(UNSUPPORTED)

    def running_clients(
        self, client: humus.RobloxClient
    ) -> list[humus.RunningClient] | humus.Unsupported:
        """Return why not: macOS is deferred."""
        return UNSUPPORTED


PLATFORM: Final = Orchard()
