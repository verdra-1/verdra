# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
<#
.SYNOPSIS
    Update this copy of Verdra to the newest main and start it (real-machine tests).

.DESCRIPTION
    Run from the verdra folder:

        powershell -ExecutionPolicy Bypass -File tools\run-latest.ps1

    It checks that this folder is the verdra repository and that git and uv are installed, switches
    to main and takes the newest commits with a fast-forward only, sets up the Python Verdra pins
    (.python-version) and the locked packages with uv, then starts Verdra. Anything after the
    script's name goes to Verdra (for example a diagnostic option).

    It never deletes, resets or overwrites anything: with local changes, or when main can't be
    fast-forwarded, it stops and says why.

.PARAMETER NoStart
    Update and set up, but don't start Verdra (used by the tests).
#>
# Read by hand, not with param(): Verdra's own options ("--diagnose-interception") must reach it
# as they are, which PowerShell's parameter binding doesn't promise.
$NoStart = $false
$VerdraArguments = @()
foreach ($Argument in $args) {
    if ($Argument -eq '-NoStart') { $NoStart = $true } else { $VerdraArguments += $Argument }
}

# git and uv write progress to stderr; every step checks $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'

function Say([string]$Text) {
    Write-Host $Text
}

function Stop-Here([string]$Text) {
    Write-Host ''
    Write-Host $Text -ForegroundColor Yellow
    Write-Host 'Nothing was changed.' -ForegroundColor Yellow
    exit 1
}

$Root = Split-Path -Parent $PSScriptRoot

# 1. This folder is the verdra repository.
$Project = Join-Path $Root 'pyproject.toml'
if (-not (Test-Path (Join-Path $Root '.git')) -or -not (Test-Path $Project) -or
    -not (Select-String -Path $Project -Pattern '^name = "verdra"$' -Quiet)) {
    Stop-Here ("This script must stay in the tools folder of your verdra folder (the one you " +
        "downloaded with git). It is in $Root, which isn't one.")
}
Set-Location $Root

# 2. git and uv are installed.
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Stop-Here ('git is not installed. Install it with: winget install --id Git.Git -e, then ' +
        'close this window, open a new PowerShell in the verdra folder and run this again.')
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Stop-Here ('uv is not installed. Install it with: winget install --id astral-sh.uv -e, then ' +
        'close this window, open a new PowerShell in the verdra folder and run this again.')
}

# 3. No local changes: an update must never overwrite them.
$Changes = @(git status --porcelain)
if ($LASTEXITCODE -ne 0) {
    Stop-Here 'git could not read this folder. Is it the verdra folder you downloaded with git?'
}
if ($Changes.Count -gt 0) {
    Say 'These files in the verdra folder were changed or added here:'
    $Changes | ForEach-Object { Say "    $_" }
    Stop-Here ('Verdra only updates a folder without local changes, so nothing of yours is ' +
        'lost. If you did not mean to change them, ask for help before deleting anything.')
}

# 4. Switch to main and take the newest commits, fast-forward only.
Say 'Getting the newest Verdra (main)...'
git switch main
if ($LASTEXITCODE -ne 0) {
    Stop-Here 'git could not switch to main. Send this window''s text to the maintainer.'
}
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) {
    Stop-Here ('main here has commits that are not on GitHub, or there is no connection, so ' +
        'it could not be updated by simply moving forward.')
}
$Commit = (git rev-parse --short HEAD)
Say "Verdra is at commit $Commit."

# 5. The pinned Python and the locked packages.
$Python = (Get-Content (Join-Path $Root '.python-version') -TotalCount 1).Trim()
Say "Setting up Python $Python and Verdra's packages (the first time takes a few minutes)..."
uv sync --locked --python $Python
if ($LASTEXITCODE -ne 0) {
    Stop-Here 'uv could not set up Verdra. Send this window''s text to the maintainer.'
}

# 6. Start Verdra.
if ($NoStart) {
    Say 'Up to date. Not starting Verdra (-NoStart).'
    exit 0
}
Say 'Starting Verdra. Keep this window open while you test; closing it closes Verdra.'
uv run --locked --python $Python python -m verdra @VerdraArguments
exit $LASTEXITCODE
