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
| W-02 | All-users installs under `Program Files (x86)\Roblox\Versions` | | Unconfirmed | | |
| W-03 | Handler in `HKCU\Software\Classes\roblox-player` | | Unconfirmed | | |
| W-04 | Microsoft Store package (detection, and whether proxy variables reach it) | | Unconfirmed | | |
| W-05 | Trust file `ssl\cacert.pem` in each version folder | | Unconfirmed | | |
| W-06 | Cache files under `%LOCALAPPDATA%\Roblox` and `%TEMP%\Roblox` (exact list) | | Unconfirmed | | |
| W-07 | `ClientSettings\ClientAppSettings.json`; global settings XML | | Unconfirmed | | |
| W-08 | Single-instance object name | Confirmed at M5 with multi-instance (plan 16.2) | Not at M1 | | |
| W-09 | A running Roblox's proxy variables can be read (S-15) | | Unconfirmed | | |
| W-10 | The hosts file is readable without administrator rights (S-15) | | Unconfirmed | | |
| V0 | Client honors `HTTPS_PROXY` / `HTTP_PROXY` | | Unconfirmed | | |

## Differences from the plan

None recorded.
