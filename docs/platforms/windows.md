# Windows platform facts

Filled in from [protocol.md](protocol.md). Until a row is `Confirmed`, no code may depend on it
(plan 16.4). States are defined in [README.md](README.md).

## Machine

| Field | Value |
|---|---|
| OS, version, build | |
| Architecture | |
| Roblox version folder | |
| Checked by, date | |
| Evidence folder | `evidence/windows/` |

## Facts

| ID | Plan says | Recorded value | State | Date | Evidence |
|---|---|---|---|---|---|
| W-01 | `%LOCALAPPDATA%\Roblox\Versions\version-*\RobloxPlayerBeta.exe` | | Unconfirmed | | |
| W-02 | All-users installs under `Program Files (x86)\Roblox\Versions` | Installed as administrator, the current installer used `C:\Program Files\Roblox\Versions\version-02c37bc51a384b8f` (not `Program Files (x86)`); the stage 1 script now checks both | Differs (CI runner, Windows Server 2025, installer run as administrator) | 2026-10-03 | [CI run](https://github.com/verdra-1/verdra/actions/runs/37163188729/job/111320711417), `evidence/windows/ci-run-37163188729.txt` |
| W-03 | Handler in `HKCU\Software\Classes\roblox-player` | For an administrator install: `HKLM\Software\Classes\roblox-player\shell\open\command` = `"…\Versions\version-02c37bc51a384b8f\RobloxPlayerBeta.exe" %1`, with a `version` value; no HKCU key. The per-user (HKCU) case waits for the maintainer's PC | Observed for administrator installs (CI runner) | 2026-10-03 | [CI run](https://github.com/verdra-1/verdra/actions/runs/37163188729/job/111320711417), `evidence/windows/ci-run-37163188729.txt` |
| W-04 | Microsoft Store package (detection, and whether proxy variables reach it) | Detection works (`Get-AppxPackage` ran; no package on the runner). Proxy variables: stage 2 | Unconfirmed (detection observed on CI runner) | 2026-10-03 | [CI run](https://github.com/verdra-1/verdra/actions/runs/37163188729/job/111320711417), `evidence/windows/ci-run-37163188729.txt` |
| W-05 | Trust file `ssl\cacert.pem` in each version folder | | Unconfirmed | | |
| W-06 | Cache files under `%LOCALAPPDATA%\Roblox` and `%TEMP%\Roblox` (exact list) | | Unconfirmed | | |
| W-07 | `ClientSettings\ClientAppSettings.json`; global settings XML | | Unconfirmed | | |
| W-08 | Single-instance object name | Confirmed at M5 with multi-instance (plan 16.2) | Not at M1 | | |
| W-09 | A running Roblox's proxy variables can be read (S-15) | | Unconfirmed | | |
| W-10 | The hosts file is readable without administrator rights (S-15) | Readable on the runner, but the runner works as administrator, so this doesn't settle it: the maintainer's PC does | Unconfirmed | 2026-10-03 | [CI run](https://github.com/verdra-1/verdra/actions/runs/37163188729/job/111320711417), `evidence/windows/ci-run-37163188729.txt` |
| V0 | Client honors `HTTPS_PROXY` / `HTTP_PROXY` | | Unconfirmed | | |

## Differences from the plan

- W-02 (CI runner, 2026-10-03): an administrator install of the current Roblox Player goes to
  `C:\Program Files\Roblox\Versions`, not `Program Files (x86)`. Reported to the maintainer; no code
  depends on W-02 yet.
