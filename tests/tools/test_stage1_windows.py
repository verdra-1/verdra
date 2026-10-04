# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""The stage 1 Windows script (tools/platforms/stage1-windows.ps1) only reads.

The maintainer runs it on their own PC (docs/platforms/protocol.md, stage 1). Two checks:

- on every system, the script uses only commands from a read-only list, contains no network,
  process-starting or file-changing command, writes one file, and never names Roblox's cookie
  or login storage;
- on the Windows runner, it runs against a fake Roblox folder and writes nothing but its report,
  which lists that folder and hides the user folder.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "platforms" / "stage1-windows.ps1"

#: Every PowerShell command the script may use: each reads, or only shapes text.
READ_ONLY = {
    "Get-ChildItem", "Get-CimInstance", "Get-AppxPackage", "Get-FileHash", "Get-Content",
    "Get-Date", "Test-Path", "Join-Path", "Sort-Object", "ForEach-Object", "Where-Object",
    "Measure-Object", "Write-Host", "New-Object",
    # The script's own helpers.
    "Hide-User", "Add-Line", "Add-Section",
    # The one write: the report itself (checked below to be the only one).
    "Set-Content",
}  # fmt: skip
#: Words that would mean the script changes, downloads, starts or reads something it mustn't.
FORBIDDEN = re.compile(
    r"Invoke-|WebClient|WebRequest|RestMethod|DownloadString|https?://|Start-Process|"
    r"Remove-|New-Item|Copy-Item|Move-Item|Rename-Item|Set-Item|Clear-|Add-Content|"
    r"Out-File|Stop-|Restart-|reg(\.exe)?\s+(add|delete|import)|cookie|LocalStorage|"
    r"\.ROBLOSECURITY|Credential",
    re.IGNORECASE,
)


def code_lines() -> list[str]:
    """The script without its comment blocks and comment lines."""
    text = re.sub(r"<#.*?#>", "", SCRIPT.read_text(encoding="utf-8"), flags=re.DOTALL)
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


def test_the_script_uses_only_read_only_commands() -> None:
    code = "\n".join(code_lines())
    used = set(re.findall(r"\b[A-Z][a-z]+-[A-Z][A-Za-z]+\b", code))
    assert used <= READ_ONLY, sorted(used - READ_ONLY)
    assert not FORBIDDEN.search(code), FORBIDDEN.search(code)
    writes = [line.strip() for line in code_lines() if "Set-Content" in line]
    assert writes == ["Set-Content -LiteralPath $OutFile -Value $report -Encoding UTF8"]
    reads = [line.strip() for line in code_lines() if "Get-Content" in line]
    assert len(reads) == 1 and "$hosts" in reads[0]  # the hosts file, counted, not copied


@pytest.mark.skipif(sys.platform != "win32", reason="runs Windows PowerShell")
def test_the_script_reads_a_roblox_folder_and_writes_only_its_report(tmp_path: Path) -> None:
    local = tmp_path / "AppData" / "Local"
    version = local / "Roblox" / "Versions" / "version-0123456789abcdef"
    (version / "ssl").mkdir(parents=True)
    (version / "RobloxPlayerBeta.exe").write_bytes(b"MZ not a real program")
    pem = b"-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----\n"
    (version / "ssl" / "cacert.pem").write_bytes(pem)
    (local / "Roblox" / "GlobalBasicSettings_13.xml").write_text("<settings/>", encoding="utf-8")
    # An install made as administrator (Platform facts run 37163188729): under Program Files.
    programs = tmp_path / "Program Files"
    shared = programs / "Roblox" / "Versions" / "version-fedcba9876543210"
    (shared / "ClientSettings").mkdir(parents=True)
    (shared / "RobloxPlayerBeta.exe").write_bytes(b"MZ shared")
    report = tmp_path / "out" / "report.txt"
    report.parent.mkdir()
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")}
    files = {p: p.read_bytes() for p in before if p.is_file()}
    # Upper case: on Windows `os.environ` keeps names in upper case, and a second spelling of
    # the same name would reach the script as a duplicate that loses (CI run 37163543239).
    environment = os.environ | {
        "LOCALAPPDATA": str(local),
        "USERPROFILE": str(tmp_path),
        "PROGRAMFILES": str(programs),
        "PROGRAMFILES(X86)": str(tmp_path / "Program Files (x86)"),
    }
    powershell = shutil.which("powershell.exe")
    assert powershell is not None
    result = subprocess.run(  # noqa: S603 - Windows PowerShell running the repository's script
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
         "-OutFile", str(report)],
        env=environment, capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    after = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")}
    # Windows PowerShell itself (not the script) keeps a startup cache in its own folder and
    # makes the Roaming folder if it is missing, on every run of any script (CI run 37161489112).
    own = (local / "Microsoft" / "Windows" / "PowerShell", tmp_path / "AppData" / "Roaming")
    powershell_parents = {local / "Microsoft", local / "Microsoft" / "Windows"}

    def powershells(path: Path) -> bool:
        return path in powershell_parents or any(path.is_relative_to(o) for o in own)

    appeared = {p for p in set(after) - set(before) if not powershells(p)}
    assert appeared == {report}  # nothing but the report appeared
    assert set(before) <= set(after)  # nothing disappeared
    # And nothing that was there changed: every file keeps its contents and date. (A folder's
    # date moves whenever an entry is added inside it, so folders are checked by `appeared`.)
    assert {p: p.read_bytes() for p in files} == files
    assert {p: after[p] for p in files} == {p: before[p] for p in files}
    text = report.read_text(encoding="utf-8-sig")
    assert str(tmp_path) not in text  # the user folder is hidden
    assert r"%USERPROFILE%\AppData\Local\Roblox\Versions\version-0123456789abcdef" in text
    assert "RobloxPlayerBeta.exe | 21 bytes" in text
    assert f"SHA-256 {hashlib.sha256(pem).hexdigest().upper()}" in text
    assert "Settings file name: GlobalBasicSettings_13.xml" in text
    shown = r"%USERPROFILE%\Program Files\Roblox\Versions\version-fedcba9876543210"
    assert f"Version folder: {shown}" in text
    assert "RobloxPlayerBeta.exe | 9 bytes" in text
    assert f"Present: {shown}\\ClientSettings" in text
    assert r"Not present: %USERPROFILE%\Program Files (x86)\Roblox\Versions" in text
    assert "== W-10 The hosts file is readable as a normal user ==" in text
    assert text.rstrip().endswith("End of report.")
