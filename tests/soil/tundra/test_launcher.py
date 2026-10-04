# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-12 on Linux: finding Sober and launching it through flatpak (docs/platforms/linux.md)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from verdra.soil import humus, terrain, tundra
from verdra.soil.tundra import launcher


def test_sober_is_found_with_flatpak_info_and_carries_the_unconfirmed_l02() -> None:
    asked: list[list[str]] = []

    def installed(command: list[str]) -> str | None:
        asked.append(command)
        return "ID: org.vinegarhq.Sober"

    [client] = launcher.find_clients(installed)
    assert asked == [["flatpak", "info", terrain.SOBER_FLATPAK_ID]]
    assert client.scope == "flatpak"
    assert client.found_by == "package"
    assert client.trust_files == ()
    assert client.unconfirmed == ("L-02",)
    assert launcher.find_clients(lambda _command: None) == []


@pytest.mark.spec("S-12", 5)
def test_sober_is_launched_with_the_proxy_variables_and_the_link_unchanged() -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def spawn(arguments: list[str], **options: Any) -> Any:
        calls.append((arguments, options))
        return type("Process", (), {"pid": 77})()

    client = humus.RobloxClient(
        scope="flatpak", executable=Path("/usr/bin/flatpak"), found_by="package"
    )
    link = "roblox-player:1+launchmode:play+gameinfo:a%20b"
    environment = {"PATH": "/usr/bin", "LANG": "C"}
    assert launcher.launch(client, link, 49443, environment, spawn) == 77
    [(arguments, options)] = calls
    assert arguments == [
        str(client.executable),
        "run",
        "--env=HTTPS_PROXY=http://127.0.0.1:49443",
        "--env=HTTP_PROXY=http://127.0.0.1:49443",
        terrain.SOBER_FLATPAK_ID,
        link,
    ]
    assert options["env"] == environment


def test_linux_doesnt_take_links_or_name_trust_files_until_l02(tmp_path: Path) -> None:
    assert tundra.PLATFORM.link_handler() == humus.Unsupported(system="linux", reason="unconfirmed")
    assert tundra.PLATFORM.trust_files_in(tmp_path) == []
