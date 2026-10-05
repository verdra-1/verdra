# SPDX-FileCopyrightText: 2026 q0f7
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
    "Hide-User", "Hide-Numbers", "Add-Line", "Add-Section",
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
    # Names made only of digits (a Roblox user ID, say) never reach the report.
    (local / "Roblox" / "1234567890").mkdir()
    (local / "Roblox" / "42").write_bytes(b"x")
    # An install made as administrator (Platform facts run 37163188729): under Program Files.
    programs = tmp_path / "Program Files"
    shared = programs / "Roblox" / "Versions" / "version-fedcba9876543210"
    (shared / "ClientSettings").mkdir(parents=True)
    (shared / "RobloxPlayerBeta.exe").write_bytes(b"MZ shared")
    report = tmp_path / "out" / "report.txt"
    report.parent.mkdir()
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")}
    files = {p: p.read_bytes() for p in before if p.is_file()}
    environment = os.environ | {"LOCALAPPDATA": str(local), "USERPROFILE": str(tmp_path)}
    powershell = shutil.which("powershell.exe")
    assert powershell is not None
    result = subprocess.run(  # noqa: S603 - Windows PowerShell running the repository's script
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
         "-OutFile", str(report), "-ProgramFolders", str(programs)],
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
    print(text)  # shown when an assertion below fails
    assert str(tmp_path) not in text  # the user folder is hidden
    assert r"%USERPROFILE%\AppData\Local\Roblox\Versions\version-0123456789abcdef" in text
    assert "RobloxPlayerBeta.exe | 21 bytes" in text
    assert f"SHA-256 {hashlib.sha256(pem).hexdigest().upper()}" in text
    assert "Settings file name: GlobalBasicSettings_13.xml" in text
    shown = r"%USERPROFILE%\Program Files\Roblox\Versions\version-fedcba9876543210"
    assert f"Version folder: {shown}" in text
    assert "RobloxPlayerBeta.exe | 9 bytes" in text
    assert f"Present: {shown}\\ClientSettings" in text
    assert "1234567890" not in text
    assert "| 42" not in text
    assert text.count("<numeric name>") == 2
    assert "== W-10 The hosts file is readable as a normal user ==" in text
    assert text.rstrip().endswith("End of report.")


@pytest.mark.skipif(sys.platform != "win32", reason="runs Windows PowerShell")
def test_by_default_the_script_checks_both_program_files_folders(tmp_path: Path) -> None:
    """The real run passes no -ProgramFolders: the default must name both all-users folders."""
    report = tmp_path / "report.txt"
    powershell = shutil.which("powershell.exe")
    assert powershell is not None
    result = subprocess.run(  # noqa: S603 - Windows PowerShell running the repository's script
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
         "-OutFile", str(report)],
        capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    text = report.read_text(encoding="utf-8-sig")
    print(text)  # shown when an assertion below fails
    w02 = text.split("== W-02")[1].split("== W-03")[0]
    for name in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        assert str(Path(os.environ[name]) / "Roblox" / "Versions") in w02


def numeric_pattern() -> re.Pattern[str]:
    """The pattern the script's Hide-Numbers uses."""
    found = re.search(r"Replace\(\$Text, '([^']+)', '<numeric name>'\)", SCRIPT.read_text("utf-8"))
    assert found is not None, "the script has no Hide-Numbers pattern"
    return re.compile(found[1])


@pytest.mark.parametrize(
    ("line", "shown"),
    [
        ("  folder | 1234567890", "  folder | <numeric name>"),
        ("  file | 42", "  file | <numeric name>"),
        (r"C:\Roblox\1234\x.xml | 3 bytes", r"C:\Roblox\<numeric name>\x.xml | 3 bytes"),
        (r"C:\Roblox\1234 | 3 bytes", r"C:\Roblox\<numeric name> | 3 bytes"),
        ("  RobloxPlayerBeta.exe | 21 bytes | 2026-10-04 | product version 0, 741, 0, 7411058",
         "  RobloxPlayerBeta.exe | 21 bytes | 2026-10-04 | product version 0, 741, 0, 7411058"),
        ("OS: Windows 11 Home | version 10.0.26200 | build 26200 | 64-bit",
         "OS: Windows 11 Home | version 10.0.26200 | build 26200 | 64-bit"),
        ("Readable: 21 lines (contents not copied)", "Readable: 21 lines (contents not copied)"),
        ("  folder | 12ab", "  folder | 12ab"),
    ],
)  # fmt: skip
def test_names_made_only_of_digits_are_hidden(line: str, shown: str) -> None:
    """The script's own pattern (the same in .NET and Python for this syntax)."""
    assert numeric_pattern().sub("<numeric name>", line) == shown
