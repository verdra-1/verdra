# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
<#
Verdra, Platform facts workflow only (never on a person's computer): downloads the official
Roblox Player installer from roblox.com and runs it on a throwaway CI runner, so the Stage 1
script can then record the install (plan 16.2, "M1 decisions").

No login, no account, no cookies, no game launch. The only contact with Roblox is the installer
download and what the installer itself does. The installer gets at most $Seconds seconds; every
Roblox process still running then is stopped, and the log says which ones there were.

Usage: install-roblox-windows.ps1 OUTPUT_FILE
#>
param(
    [Parameter(Mandatory = $true)][string]$OutFile,
    [int]$Seconds = 300
)

$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutFile) | Out-Null
$log = New-Object System.Collections.Generic.List[string]
function Log([string]$Text) { $log.Add($Text); Write-Host $Text }

$url = 'https://www.roblox.com/download/client?os=win'
$installer = Join-Path $env:RUNNER_TEMP 'RobloxPlayerInstaller.exe'
Log 'Verdra platform facts, Windows CI runner: installing Roblox Player'
Log ('Date: ' + (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm') + ' UTC')
Log "Download: $url"
try {
    $response = Invoke-WebRequest -Uri $url -OutFile $installer -PassThru -UseBasicParsing
    Log "HTTP $($response.StatusCode); final address $($response.BaseResponse.RequestMessage.RequestUri)"
} catch {
    Log "Download failed: $($_.Exception.Message)"
    Set-Content -LiteralPath $OutFile -Value $log -Encoding UTF8
    exit 1
}
$file = Get-Item -LiteralPath $installer
Log ("Installer: $($file.Length) bytes | SHA-256 $((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash) | product version $($file.VersionInfo.ProductVersion)")
$signature = Get-AuthenticodeSignature -LiteralPath $installer
Log ("Signature: $($signature.Status) | $($signature.SignerCertificate.Subject)")
if ($signature.Status -ne 'Valid') {
    Log 'Not run: the installer does not carry a valid signature.'
    Set-Content -LiteralPath $OutFile -Value $log -Encoding UTF8
    exit 1
}

$before = @(Get-Process | ForEach-Object { $_.Id })
$process = Start-Process -FilePath $installer -PassThru
if ($process.WaitForExit($Seconds * 1000)) {
    Log "Installer finished by itself with exit code $($process.ExitCode)."
} else {
    Log "Installer still running after $Seconds seconds; it is stopped."
}
Start-Sleep -Seconds 5
$left = @(Get-Process | Where-Object { $before -notcontains $_.Id -and $_.ProcessName -like '*Roblox*' })
foreach ($item in $left) {
    Log "Still running, stopped: $($item.ProcessName) (process $($item.Id))"
    Stop-Process -Id $item.Id -Force -ErrorAction SilentlyContinue
}
if ($left.Count -eq 0) { Log 'No Roblox process left running.' }
Set-Content -LiteralPath $OutFile -Value $log -Encoding UTF8
