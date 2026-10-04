# Windows platform facts

Filled in from [protocol.md](protocol.md). Until a row is `Confirmed`, no code may depend on it
(plan 16.4). States are defined in [README.md](README.md).

## Machine

| Field | Maintainer's PC | CI runner |
|---|---|---|
| OS, version, build | Windows 11 Home, build 26200 | Windows Server 2025 Datacenter, build 26100 |
| Architecture | In the report (not yet in the repository) | x64 (64-bit) |
| Roblox | Player 0.741.0.7411058, per-user install (Studio also installed) | `version-02c37bc51a384b8f`, all-users install (installer run as administrator) |
| Checked by, date | Maintainer, Stage 1 script, 2026-10-04 | Platform facts workflow, 2026-10-03 |
| Evidence folder | `evidence/windows/` | `evidence/windows/` |

## Facts

Plan 11.1 is the reference; "PC" below means: Confirmed on maintainer's PC (Windows 11 Home, build 26200, Roblox Player 0.741.0.7411058, 2026-10-04).

| ID | Plan says | Recorded value | State | Date | Evidence |
|---|---|---|---|---|---|
| W-01 | `%LOCALAPPDATA%\Roblox\Versions\version-*\RobloxPlayerBeta.exe` | PC: per-user install under `%LOCALAPPDATA%\Roblox\Versions\version-*`. Roblox Studio can have version folders there too: a **Player** version folder is one that contains `RobloxPlayerBeta.exe`; Studio folders (`RobloxStudioBeta.exe`) are never touched. Several version folders can exist side by side | Confirmed on maintainer's PC (Windows 11 Home, build 26200, Roblox Player 0.741.0.7411058, 2026-10-04) | 2026-10-04 | Stage 1 report from the maintainer, 2026-10-04 (redacted copy `evidence/windows/maintainer-pc-2026-10-04.txt` follows once the file is in the repository) |
| W-02 | All-users installs under `Program Files\Roblox\Versions` or `Program Files (x86)\Roblox\Versions`, handler then under HKLM | PC: no all-users install (both folders checked). CI runner, installer run as administrator: `C:\Program Files\Roblox\Versions\version-02c37bc51a384b8f` | Confirmed on maintainer's PC (Windows 11 Home, build 26200, Roblox Player 0.741.0.7411058, 2026-10-04); Observed on CI runner (Program Files) | 2026-10-04 | Stage 1 report from the maintainer, 2026-10-04 (redacted copy `evidence/windows/maintainer-pc-2026-10-04.txt` follows once the file is in the repository); [CI run](https://github.com/verdra-1/verdra/actions/runs/37163188729/job/111320711417), `evidence/windows/ci-run-37163188729.txt` |
| W-03 | Handler in `HKCU\Software\Classes\roblox-player`; HKLM for all-users installs | PC: `HKCU\Software\Classes\roblox-player\shell\open\command` = `"<version folder>\RobloxPlayerBeta.exe" %1`, with a `version` value naming the current version folder; nothing in HKLM. CI runner (administrator install): the same layout under HKLM, no HKCU key | Confirmed on maintainer's PC (Windows 11 Home, build 26200, Roblox Player 0.741.0.7411058, 2026-10-04); Observed on CI runner (HKLM) | 2026-10-04 | Stage 1 report from the maintainer, 2026-10-04 (redacted copy `evidence/windows/maintainer-pc-2026-10-04.txt` follows once the file is in the repository); [CI run](https://github.com/verdra-1/verdra/actions/runs/37163188729/job/111320711417), `evidence/windows/ci-run-37163188729.txt` |
| W-04 | Microsoft Store package (detection, and whether proxy variables reach it) | PC: no Microsoft Store Roblox. Whether proxy variables reach a Store build: no Store install to test on | Detection: Confirmed on maintainer's PC (Windows 11 Home, build 26200, Roblox Player 0.741.0.7411058, 2026-10-04). Store behavior: Unconfirmed | 2026-10-04 | Stage 1 report from the maintainer, 2026-10-04 (redacted copy `evidence/windows/maintainer-pc-2026-10-04.txt` follows once the file is in the repository) |
| W-05 | Trust file `ssl\cacert.pem` in each version folder | PC: `ssl\cacert.pem` exists in each version folder and is not read-only. Its hashes differ between the Player and Studio folders (evidence only: Verdra never touches Studio's). Sizes: copied from the report once it is in the repository | Confirmed on maintainer's PC (Windows 11 Home, build 26200, Roblox Player 0.741.0.7411058, 2026-10-04) | 2026-10-04 | Stage 1 report from the maintainer, 2026-10-04 (redacted copy `evidence/windows/maintainer-pc-2026-10-04.txt` follows once the file is in the repository) |
| W-06 | Cache files under `%LOCALAPPDATA%\Roblox` and `%TEMP%\Roblox` (exact list) | PC: top-level names in `%LOCALAPPDATA%\Roblox` copied from the report once it is in the repository, without the `<numeric folder, likely the user ID>`. `GlobalBasicSettings_13.xml` and `frm.cfg` are candidates for the frame-rate cap (M4), unconfirmed. Which files are cache (S-12 cache clearing) isn't settled by a listing | Names: Confirmed on maintainer's PC (Windows 11 Home, build 26200, Roblox Player 0.741.0.7411058, 2026-10-04). Cache files and frame-rate file: Unconfirmed | 2026-10-04 | Stage 1 report from the maintainer, 2026-10-04 (redacted copy `evidence/windows/maintainer-pc-2026-10-04.txt` follows once the file is in the repository) |
| W-07 | `ClientSettings\ClientAppSettings.json`; global settings XML | PC: no `ClientSettings` folder in the Player version folder by default. Verdra creates it when needed, recorded as a `client_settings_file` ledger entry. Whether Roblox reads it is confirmed at M4 | Absence: Confirmed on maintainer's PC (Windows 11 Home, build 26200, Roblox Player 0.741.0.7411058, 2026-10-04). Roblox reading it: Unconfirmed (M4) | 2026-10-04 | Stage 1 report from the maintainer, 2026-10-04 (redacted copy `evidence/windows/maintainer-pc-2026-10-04.txt` follows once the file is in the repository) |
| W-08 | Single-instance object name | Confirmed at M5 with multi-instance (plan 16.2) | Not at M1 | | |
| W-09 | A running Roblox's proxy variables can be read (S-15) | Needs a running Roblox: Stage 2 | Unconfirmed | | |
| W-10 | The hosts file is readable without administrator rights (S-15) | PC: readable as a normal user | Confirmed on maintainer's PC (Windows 11 Home, build 26200, Roblox Player 0.741.0.7411058, 2026-10-04) | 2026-10-04 | Stage 1 report from the maintainer, 2026-10-04 (redacted copy `evidence/windows/maintainer-pc-2026-10-04.txt` follows once the file is in the repository) |
| V0 | Client honors `HTTPS_PROXY` / `HTTP_PROXY` | Needs a running game: Stage 2 | Unconfirmed | | |

## Maintainer's PC compared with the CI runner

| Topic | Maintainer's PC | CI runner |
|---|---|---|
| System | Windows 11 Home, build 26200, normal user | Windows Server 2025, build 26100, administrator |
| Install (W-01, W-02) | Per-user, `%LOCALAPPDATA%\Roblox\Versions` | All-users, `C:\Program Files\Roblox\Versions` |
| Link handler (W-03) | HKCU, with a `version` value | HKLM, same layout and `version` value |
| Roblox Studio | Installed; its version folders sit beside the Player's | Not installed |
| Trust file (W-05) | `ssl\cacert.pem` in each version folder, not read-only | Not recorded (the stage 1 script then looked only at per-user folders) |
| Roblox folder (W-06) | Its own list (see W-06), including a numeric folder | `Downloads`, `LocalStorage`, `logs`, `RobloxPlayerInstaller` |
| `ClientSettings` (W-07) | None | None |
| Hosts file (W-10) | Readable as a normal user | Readable, but as administrator |
| Microsoft Store (W-04) | None | None |

## Differences from the plan

None open. The CI runner's all-users install under `Program Files` (2026-10-03) is now in plan 11.1.
