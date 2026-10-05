# Windows platform facts

Filled in from [protocol.md](protocol.md). Until a row is `Confirmed`, no code may depend on it
(plan 16.4). States are defined in [README.md](README.md).

## Machine

| Field | Maintainer's PC | CI runner |
|---|---|---|
| OS, version, build | Windows 11 Home, version 10.0.26200, build 26200, 64-bit | Windows Server 2025 Datacenter, build 26100, 64-bit |
| Roblox | Player 0.741.0.7411058 in `version-02c37bc51a384b8f`, per-user; Studio 0.713.0.7130910 in `version-913142fd943640d2` | Player in `version-02c37bc51a384b8f`, all-users (installer run as administrator); no Studio |
| Checked by, date | Maintainer: Stage 1 script and Stage 2, 2026-10-04 | Platform facts workflow, 2026-10-03 |
| Evidence | `evidence/windows/maintainer-pc-2026-10-04.txt` (Stage 1), `evidence/windows/stage2-2026-10-04.txt` (Stage 2, anonymised) | `evidence/windows/ci-run-37163188729.txt` |

## Facts

"PC" below means: confirmed on maintainer's PC (Windows 11 Home, build 26200, Roblox Player
0.741.0.7411058, 2026-10-04). Plan 11.1 is the reference.

| ID | Plan says | Recorded value | State | Date | Evidence |
|---|---|---|---|---|---|
| W-01 | `%LOCALAPPDATA%\Roblox\Versions\version-*\RobloxPlayerBeta.exe` | Per-user version folders in `%LOCALAPPDATA%\Roblox\Versions`; several side by side. **Player** folder `version-02c37bc51a384b8f`: `RobloxPlayerBeta.exe` (141,403,600 bytes, 0.741.0.7411058), `RobloxCrashHandler.exe`, `RobloxPlayerInstaller.exe`. **Studio** folder `version-913142fd943640d2`: `RobloxStudioBeta.exe` (0.713.0.7130910) and Studio's own programs. A Player folder is one holding `RobloxPlayerBeta.exe`; Studio folders (`RobloxStudioBeta.exe`) are never touched | Confirmed, PC | 2026-10-04 | Stage 1 |
| W-02 | All-users installs under `Program Files\Roblox\Versions` or `Program Files (x86)\Roblox\Versions`, handler then under HKLM | PC: neither folder exists. CI runner (installer run as administrator): `C:\Program Files\Roblox\Versions\version-02c37bc51a384b8f` | Confirmed, PC (none); observed on CI runner | 2026-10-04 | Stage 1; CI run |
| W-03 | Handler in `HKCU\Software\Classes\roblox-player` | `HKCU\Software\Classes\roblox-player\shell\open\command`: `(default)` = `"<version folder>\RobloxPlayerBeta.exe" %1`, `version` = `version-02c37bc51a384b8f` (the current Player folder); `DefaultIcon` = the same program. Nothing in HKLM | Confirmed, PC | 2026-10-04 | Stage 1 |
| W-04 | Microsoft Store package (detection, and whether proxy variables reach it) | No Store Roblox (`Get-AppxPackage -Name *Roblox*` finds none). Whether proxy variables reach a Store build: no Store install to test | Detection: Confirmed, PC. Store behavior: Unconfirmed | 2026-10-04 | Stage 1 |
| W-05 | Trust file `ssl\cacert.pem` in each version folder | Player: `ssl\cacert.pem`, 228,725 bytes, not read-only. Studio: `ssl\cacert.pem`, 233,371 bytes, not read-only. Their SHA-256 hashes differ (in the evidence; Verdra never touches Studio's). Stage 2: Verdra's block went into the Player's file only and Reset removed it | Confirmed, PC | 2026-10-04 | Stage 1; Stage 2 |
| W-06 | Cache files under `%LOCALAPPDATA%\Roblox` and `%TEMP%\Roblox` (exact list) | Top-level names in `%LOCALAPPDATA%\Roblox`: folders `AssistantSettings`, `ClientSettings`, `DefaultInstances`, `Downloads`, `LocalStorage`, `logs`, `notifications`, `OTAPatchBackups`, `OTAPlugins`, `placeIDEState`, `rbx-storage`, `rbx-storage-sc`, `RobloxPlayerInstaller`, `RobloxStudio`, `RobloxStudioInstaller`, `tmp-capture-storage`, `UniversalApp`, `Versions`, and `<numeric folder, likely the user ID>`; files `AnalysticsSettings.xml`, `frm.cfg`, `GlobalBasicSettings_13.xml`, `GlobalBasicSettings_13_Studio.xml`, `GlobalSettings_13.xml`, `mcp.bat`, `rbx-storage.db`, `rbx-storage.db-shm`, `rbx-storage.db-wal`, `rbx-storage.id`. `GlobalBasicSettings_13.xml` and `frm.cfg` are candidates for the frame-rate cap (M4), unconfirmed. **Cache (S-24, 2026-10-05):** `rbx-storage.db` with its SQLite write-ahead files `rbx-storage.db-wal` and `rbx-storage.db-shm`, and the `rbx-storage` folder: the only database in the folder, which plan 11.1 calls "the asset cache database", one per user next to both the Player's and Studio's settings files. Not cache, or not known to be: `rbx-storage.id`, `rbx-storage-sc`, `tmp-capture-storage`, `LocalStorage`, `logs`, every settings file, `RobloxStudio` and everything else listed | Names: Confirmed, PC. Cache: Observed (names), probable, not proven; the re-test's read-only check shows whether the Player writes there during a join. Frame-rate file: Unconfirmed | 2026-10-05 | Stage 1; `docs/m2/notes.md` |
| W-07 | `ClientSettings\ClientAppSettings.json`; global settings XML | No `ClientSettings` folder in the Player version folder by default; Verdra creates it when needed, as a `client_settings_file` ledger entry. (A top-level `%LOCALAPPDATA%\Roblox\ClientSettings` folder exists; Verdra doesn't use it.) Global settings XML: `GlobalBasicSettings_13.xml`, `GlobalSettings_13.xml`. Whether Roblox reads a `ClientAppSettings.json` Verdra writes is confirmed at M4 | Absence: Confirmed, PC. Roblox reading it: Unconfirmed (M4) | 2026-10-04 | Stage 1 |
| W-08 | Single-instance object name | Confirmed at M5 with multi-instance (plan 16.2) | Not at M1 | | |
| W-09 | A running Roblox's proxy variables can be read (S-15) | Readable as the same user, without administrator rights: the coexistence check read `HTTPS_PROXY` and `HTTP_PROXY` = `http://127.0.0.1:49443` from three running Players | Confirmed, PC | 2026-10-04 | Stage 2 |
| W-10 | The hosts file is readable without administrator rights (S-15) | Readable as a normal user (20 lines) | Confirmed, PC | 2026-10-04 | Stage 1 |
| V0 | Client honors `HTTPS_PROXY` / `HTTP_PROXY` | The Player launched with the variables sent all its HTTPS traffic through Verdra: 133 connections to 13 hosts, two game joins | Confirmed, PC | 2026-10-04 | Stage 2 |
| V1 | Asset batch requests (`POST assetdelivery.roblox.com/v1/assets/batch`) are JSON arrays of items with an asset ID and a request ID; the response names each item's content location, served from `fts.rbxcdn.com` (S-21) | Seen in the Stage 2 capture: 204 batch requests and the `fts.rbxcdn.com` downloads that follow them (paths only; bodies weren't logged) | Unconfirmed: the body shape is confirmed by the M2 real-machine test | 2026-10-04 | `evidence/windows/stage2-2026-10-04.txt` |

## Maintainer's PC compared with the CI runner

Every difference between the Stage 1 report and the CI runner's findings:

| Topic | Maintainer's PC | CI runner |
|---|---|---|
| System | Windows 11 Home, build 26200, normal user | Windows Server 2025, build 26100, administrator |
| Install (W-01, W-02) | Per-user, `%LOCALAPPDATA%\Roblox\Versions` | All-users, `C:\Program Files\Roblox\Versions` |
| Player version folder | `version-02c37bc51a384b8f` | `version-02c37bc51a384b8f` (the same build) |
| Programs in the Player folder | `RobloxPlayerBeta.exe`, `RobloxCrashHandler.exe`, `RobloxPlayerInstaller.exe` | Not listed (the stage 1 script then looked only at per-user folders) |
| Roblox Studio | Installed (`version-913142fd943640d2`) | Not installed |
| Link handler (W-03) | HKCU, with `version` and `DefaultIcon` | HKLM, same layout; no HKCU key |
| Trust file (W-05) | Player and Studio `cacert.pem`, both not read-only, different sizes and hashes | Not recorded |
| Roblox folder (W-06) | 29 entries (above), including a numeric folder | 4 entries: `Downloads`, `LocalStorage`, `logs`, `RobloxPlayerInstaller` |
| Settings XML files (W-07) | `AnalysticsSettings.xml`, `GlobalBasicSettings_13.xml`, `GlobalBasicSettings_13_Studio.xml`, `GlobalSettings_13.xml` | None |
| `ClientSettings` in a version folder (W-07) | None | None |
| Hosts file (W-10) | Readable, 20 lines, as a normal user | Readable, 21 lines, as administrator |
| Microsoft Store (W-04) | None | None |

## Stage 2 results (maintainer's PC, 2026-10-04)

From the maintainer's `verdra.log`, anonymised in `evidence/windows/stage2-2026-10-04.txt`
(the raw log isn't committed). Verdra ran from source with `--diagnose-interception` and
detailed logging.

| Step | What the log proves | What it doesn't prove | Result |
|---|---|---|---|
| 1–2 Install uv, download Verdra | Verdra ran from source (steps 3 onward) | Nothing more | Pass |
| 3 Start with `--diagnose-interception` | "Verdra 0.0.1 started on Windows"; M-DIAG-01 as an Activity line and as the notice | | Pass |
| 4 Setup, detailed logging | DEBUG lines are present, so detailed logging was on | The onboarding choices themselves (not logged) | Pass |
| 5 Launch Roblox | Routing changed from Idle to Routing; Roblox's traffic arrived through the proxy at once (V0) | Which button started it (the Library's "Launch Roblox" or Start routing) | Pass |
| 6 A game, 2 minutes | A game join (`gamejoin.roblox.com/v1/join-game`) through Verdra. On all 133 intercepted connections the Player accepted Verdra's ECDSA P-256 leaf over TLS 1.3, and every upstream certificate verified (none "not verified"). R-17 closed for Windows (plan 16.2). | How the game looked; that comes from the maintainer ("no Roblox error") | Pass |
| 7 Play from the browser | A second launch handed Verdra a link (M-SHELL-07), the coexistence check ran for that launch, and 3.5 s later a second game join went through Verdra. The maintainer's YES/NO field came back unfilled, so this result rests on the log | That the game window was the one the link asked for | Pass (log) |
| 8 Quit while Roblox runs, restart | M-SHELL-02 appears **twice**, 37 s apart. Activity records a dialog when it **appears**, not the answer; Verdra kept running after the first, so it was answered Cancel, Esc or closed (Cancel is the default button, so Enter also cancels). The second was answered Quit and shutdown followed 1 s later. On restart with Roblox running, the coexistence check read the running Player's proxy variables (W-09) and routing started | What was clicked the first time. Dialog answers are now logged (detailed logging) so the next log shows it | Pass |
| 9 Reset everything | "Removed 2 changes. Verdra left nothing behind.": the link handler and Verdra's block in the Player's `cacert.pem`. The ledger held no Studio file, so Reset had nothing to undo there | That the Player's `cacert.pem` is byte-identical afterwards, and that Studio's still has its Stage 1 hash. The tests prove the mechanism (`tests/trunk/branches/test_sprout.py`); re-running the Stage 1 script would prove it on the PC | Pass |
| 10 Send the log | Received | | Pass |

Also seen: one `sc5.rbxcdn.com` connection closed with "Upstream … failed: Connection lost".
It was Roblox closing its own connection to Verdra while a video segment was still being
relayed, which Verdra mislabeled as an upstream failure (evidence and fix:
[verdra-1/verdra#67](https://github.com/verdra-1/verdra/pull/67)). Window visible after launch on this PC: 1,461 ms and 1,020 ms (plan 12.4: ≤ 1.5 s).

## First texture swap test (maintainer's PC, 2026-10-05): not seen

From the maintainer's `verdra.log`, anonymised in `evidence/windows/first-swap-2026-10-05.txt`
(the raw log isn't committed). The full analysis is in [`docs/m2/notes.md`](../m2/notes.md).

| Step (guide) | What the log proves | What it doesn't prove | Result |
|---|---|---|---|
| 1–5 Update, place, pictures, publish | Verdra ran (started on Windows, routing on) | The place and pictures (not logged) | Pass (as reported) |
| 6 Save the replacement | Saved after verdra-1/verdra#84 ("Applied 1 replacement" follows) | | Pass |
| 7 Apply now | "Applied 1 replacement"; three restarts asked and confirmed | | Pass |
| 8 Join from the browser | A second launch handed Verdra a link; 64 asset batches and 2 single-asset requests then went through Verdra | Which Player rendered the game: one started by Verdra's previous run was still running and was never closed | Pass (log) |
| 9 The wall | The original showed every time (the maintainer) | Why: no grafter line at all, and the grafter then said nothing for a batch without a match or one it skipped | **Fail** |

V1 (the batch body shape) stays Unconfirmed: the bodies weren't logged. The next log names the
asset IDs and item field names of every batch (verdra-1/verdra#87).

## Differences from the plan

- Plan 16.2 lists `sc2` and `sc5.rbxcdn.com` as speed tests. In this log `sc0`, `sc0ak` and
  `sc0aws` served the speed test (`/test-50kb.png`), while `sc2` served a video playlist
  (`main.m3u8`) and `sc5` a video segment (`.webm`). The host list is the same; only the
  description differs. Reported to the maintainer.
