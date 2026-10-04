# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Find Roblox, start it with the proxy variables, register the roblox-player: handler.

Spec S-12 on Linux, built on docs/platforms/linux.md (CI runner, Sober 1.8.0, 2026-10-03):

- L-01: Sober is the Flatpak `org.vinegarhq.Sober`, found with `flatpak info`; it is launched
  with `flatpak run --env=HTTPS_PROXY=… --env=HTTP_PROXY=… org.vinegarhq.Sober <link>` (plan
  11.3). Whether Sober honors those variables is V0, checked in stage 2.
- L-02: where Sober reads its CA bundle isn't confirmed (Sober ships no trust file; its data
  folder only exists after a first start). So a Sober client carries the unconfirmed fact
  `L-02` and routing refuses it with a plain message instead of guessing, and Verdra doesn't
  take over `roblox-player:` links on Linux yet: they would reach Sober unrouted.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from verdra.soil import humus, terrain


def find_clients(
    read_command: Callable[[list[str]], str | None] = humus.read_command,
) -> list[humus.RobloxClient]:
    """Return Sober if `flatpak info` knows it (L-01), with the unconfirmed L-02."""
    if read_command(["flatpak", "info", terrain.SOBER_FLATPAK_ID]) is None:
        return []
    flatpak = shutil.which("flatpak") or "flatpak"
    return [
        humus.RobloxClient(
            scope="flatpak",
            executable=Path(flatpak),
            found_by="package",
            unconfirmed=("L-02",),
        )
    ]


def launch(
    client: humus.RobloxClient,
    link: str | None,
    proxy_port: int,
    environment: Mapping[str, str],
    spawn: humus.Spawn = subprocess.Popen,
) -> int:
    """Start Sober through `flatpak run` with the proxy variables; return the PID of flatpak."""
    variables = humus.proxy_environment({}, proxy_port)
    arguments = [
        str(client.executable),
        "run",
        *(f"--env={name}={value}" for name, value in variables.items()),
        terrain.SOBER_FLATPAK_ID,
        *([link] if link else []),
    ]
    process = spawn(arguments, env=dict(environment), close_fds=True)
    return int(process.pid)
