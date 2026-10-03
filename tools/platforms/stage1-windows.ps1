# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
<#
Verdra, stage 1 of docs/platforms/protocol.md on Windows: records where Roblox is installed.

What it does: reads folder listings, file sizes, dates and SHA-256 hashes under the Roblox
folders, the roblox-player link handler in the registry, the Windows version, whether a
Microsoft Store Roblox is installed, and how many lines the hosts file has.

What it never does: it changes nothing, needs no administrator rights, starts nothing, sends
nothing anywhere (no network commands at all) and never opens Roblox's login, cookies or
settings files: only the names of the files directly in the Roblox folder are listed.

It writes exactly one file, the report (by default verdra-stage1-windows.txt on the Desktop).
(Windows PowerShell itself, not this script, refreshes its own small startup cache in its own
folder whenever it runs.)
In the report your user folder is written as %USERPROFILE%, so your user name isn't in it.

Run:  powershell -NoProfile -ExecutionPolicy Bypass -File stage1-windows.ps1
#>
param(
    [string]$OutFile = (Join-Path ([Environment]::GetFolderPath('Desktop')) 'verdra-stage1-windows.txt')
)

$ErrorActionPreference = 'Continue'
$report = New-Object System.Collections.Generic.List[string]

function Hide-User([string]$Text) {
    # The user folder becomes %USERPROFILE%, so the report doesn't carry the user name.
    if ($env:USERPROFILE) {
        $Text = [regex]::Replace($Text, [regex]::Escape($env:USERPROFILE), '%USERPROFILE%', 'IgnoreCase')
    }
    return $Text
}

function Add-Line([string]$Text) { $report.Add((Hide-User $Text)) }

function Add-Section([string]$Id, [string]$Title) {
    $report.Add('')
    $report.Add("== $Id $Title ==")
}

$roblox = Join-Path $env:LOCALAPPDATA 'Roblox'
$versions = Join-Path $roblox 'Versions'

Add-Line 'Verdra stage 1 facts, Windows (docs/platforms/protocol.md)'
Add-Line ('Date: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm'))

Add-Section 'Step 0' 'The machine'
$os = Get-CimInstance -ClassName Win32_OperatingSystem
Add-Line ("OS: $($os.Caption) | version $($os.Version) | build $($os.BuildNumber) | $($os.OSArchitecture)")

Add-Section 'W-01' 'Per-user Roblox install'
if (Test-Path -LiteralPath $versions) {
    Get-ChildItem -LiteralPath $versions -Directory | Sort-Object Name | ForEach-Object {
        Add-Line ("Version folder: $($_.FullName)")
        Get-ChildItem -LiteralPath $_.FullName -File -Filter '*.exe' | Sort-Object Name | ForEach-Object {
            $version = $_.VersionInfo.ProductVersion
            Add-Line ("  $($_.Name) | $($_.Length) bytes | $($_.LastWriteTime.ToString('yyyy-MM-dd')) | product version $version")
        }
    }
} else {
    Add-Line "Not found: $versions"
}

Add-Section 'W-02' 'All-users install'
# An installer run as administrator installs for all users; on a CI runner it went to Program
# Files, not Program Files (x86) (Platform facts run 37163188729), so both are checked.
$allUsers = @(${env:ProgramFiles}, ${env:ProgramFiles(x86)} | Where-Object { $_ } | Sort-Object -Unique | ForEach-Object {
    Join-Path $_ 'Roblox\Versions'
})
foreach ($folder in $allUsers) {
    if (Test-Path -LiteralPath $folder) {
        Add-Line "Present: $folder"
        Get-ChildItem -LiteralPath $folder -Directory | Sort-Object Name | ForEach-Object {
            Add-Line ("Version folder: $($_.FullName)")
            Get-ChildItem -LiteralPath $_.FullName -File -Filter '*.exe' | Sort-Object Name | ForEach-Object {
                $version = $_.VersionInfo.ProductVersion
                Add-Line ("  $($_.Name) | $($_.Length) bytes | $($_.LastWriteTime.ToString('yyyy-MM-dd')) | product version $version")
            }
        }
    } else {
        Add-Line "Not present: $folder"
    }
}

Add-Section 'W-03' 'The roblox-player link handler'
foreach ($key in @('HKCU:\Software\Classes\roblox-player', 'HKLM:\Software\Classes\roblox-player')) {
    if (Test-Path -LiteralPath $key) {
        Add-Line "Key: $key"
        Get-ChildItem -LiteralPath $key -Recurse | ForEach-Object {
            $item = $_
            foreach ($name in $item.GetValueNames()) {
                $shown = if ($name) { $name } else { '(default)' }
                Add-Line ("  $($item.Name.Replace('HKEY_CURRENT_USER', 'HKCU').Replace('HKEY_LOCAL_MACHINE', 'HKLM')) | $shown = $($item.GetValue($name))")
            }
        }
    } else {
        Add-Line "Not present: $key"
    }
}

Add-Section 'W-04' 'Microsoft Store Roblox'
$store = @(Get-AppxPackage -Name '*Roblox*' -ErrorAction SilentlyContinue)
if ($store.Count -gt 0) {
    foreach ($package in $store) {
        Add-Line ("Package: $($package.Name) | $($package.PackageFamilyName) | version $($package.Version)")
    }
} else {
    Add-Line 'No Microsoft Store Roblox package.'
}

Add-Section 'W-05' 'Trust files in each version folder'
$found = @(@($versions) + $allUsers | Where-Object { Test-Path -LiteralPath $_ } | ForEach-Object {
    Get-ChildItem -LiteralPath $_ -Recurse -File -Filter '*.pem'
} | Sort-Object FullName)
foreach ($file in $found) {
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    Add-Line ("$($file.FullName) | $($file.Length) bytes | SHA-256 $hash | read-only $($file.IsReadOnly)")
}
if ($found.Count -eq 0) { Add-Line 'No .pem file in any version folder.' }

Add-Section 'W-06' 'What is directly in the Roblox folder (names only, nothing opened)'
if (Test-Path -LiteralPath $roblox) {
    Get-ChildItem -LiteralPath $roblox | Sort-Object Name | ForEach-Object {
        $kind = if ($_.PSIsContainer) { 'folder' } else { 'file' }
        Add-Line ("  $kind | $($_.Name)")
    }
} else {
    Add-Line "Not found: $roblox"
}

Add-Section 'W-07' 'Client settings folder and settings file names'
$settings = @(@($versions) + $allUsers | Where-Object { Test-Path -LiteralPath $_ } | ForEach-Object {
    Get-ChildItem -LiteralPath $_ -Directory | ForEach-Object { Join-Path $_.FullName 'ClientSettings' }
} | Where-Object { Test-Path -LiteralPath $_ })
if ($settings.Count -gt 0) { $settings | ForEach-Object { Add-Line "Present: $_" } }
else { Add-Line 'No ClientSettings folder in any version folder.' }
if (Test-Path -LiteralPath $roblox) {
    Get-ChildItem -LiteralPath $roblox -File -Filter '*.xml' | Sort-Object Name | ForEach-Object {
        Add-Line "Settings file name: $($_.Name)"
    }
}

Add-Section 'W-10' 'The hosts file is readable as a normal user'
$hosts = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
try {
    $count = (Get-Content -LiteralPath $hosts -ErrorAction Stop | Measure-Object -Line).Lines
    Add-Line "Readable: $count lines (contents not copied)"
} catch {
    Add-Line ("Not readable: $($_.Exception.Message)")
}

Add-Line ''
Add-Line 'End of report.'
Set-Content -LiteralPath $OutFile -Value $report -Encoding UTF8
Write-Host ''
Write-Host 'Done. Your report is here:'
Write-Host $OutFile
