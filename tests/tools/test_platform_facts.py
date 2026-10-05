# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The Platform facts workflow keeps the limits of plan 16.2 ("M1 decisions").

It installs the Roblox Player on a throwaway Windows CI runner and records facts: no login, no
game launch, no contact with Roblox beyond the installer download. These checks read the
workflow and its script and fail if one of them could do more. (Its Linux job left with Linux,
decision record 0018.)
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "platform-facts.yml"
INSTALL = ROOT / "tools" / "platforms" / "install-roblox-windows.ps1"

#: Anything that would log in, read account data or reach past the installer download.
NEVER = re.compile(
    r"cookie|ROBLOSECURITY|LocalStorage|(?<!persist-)credential|password|login|placeId|roblox://|"
    r"roblox-player:|games/start|auth\.roblox|apis\.roblox",
    re.IGNORECASE,
)


def code(path: Path) -> str:
    """The file without comments (PowerShell `<# #>` blocks and `#` lines)."""
    text = re.sub(r"<#.*?#>", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_the_workflow_starts_only_by_hand_with_read_only_permissions() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert list(workflow[True]) == ["workflow_dispatch"]  # YAML reads the key `on` as True
    assert workflow["permissions"] == {}
    for job in workflow["jobs"].values():
        assert job["permissions"] == {"contents": "read"}


def test_nothing_logs_in_launches_a_game_or_reads_account_data() -> None:
    for path in (WORKFLOW, INSTALL):
        found = NEVER.search(code(path))
        assert found is None, (path.name, found)


def test_only_windows_runners_are_used() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert {job["runs-on"] for job in workflow["jobs"].values()} == {"windows-latest"}


def test_the_only_download_is_the_official_installer() -> None:
    assert re.findall(r"https?://[^\s'\"]+", code(INSTALL)) == [
        "https://www.roblox.com/download/client?os=win"
    ]
    assert re.findall(r"https?://[^\s'\"]+", code(WORKFLOW)) == []
    assert len(re.findall(r"Invoke-WebRequest", code(INSTALL))) == 1
    assert re.search(r"\b(curl|wget)\b", code(WORKFLOW)) is None


def test_the_installer_runs_only_when_its_signature_is_valid() -> None:
    text = code(INSTALL)
    assert text.index("Get-AuthenticodeSignature") < text.index("Start-Process")
    assert "if ($signature.Status -ne 'Valid')" in text
