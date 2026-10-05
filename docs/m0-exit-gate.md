# M0 exit gate

> **Current state (5 October 2026):** Windows is the only platform; Linux is paused, planned
> later, and macOS is deferred ([decision record 0018](decisions/0018-windows-only.md)). What this document says about Linux
> describes the time it was written.

Master plan 14, M0: "the app starts on Windows and Linux, themes switch live, settings survive a
forced kill during a write, every CI gate is green." In autopilot mode (plan 16.2) the exit gate
is judged on CI evidence (see [Coverage](#coverage)); this checklist covers what needs a real
desktop. It runs in the first real-machine test session, together with the M1 real-machine
checks, on `main` after the M0 pull requests are merged; fill in the [results table](#results)
then. M0 counts as done only when these steps have passed.

Machines: Windows 11, and Ubuntu 24.04 (once in a Wayland session, once in an X11 session; a
virtual machine on the Windows PC is fine for these steps). macOS is deferred until after 1.0
(decision record 0014) and isn't tested.

## Setup (every machine)

```sh
git clone https://github.com/verdra-1/verdra.git
cd verdra
uv sync --locked
uv run python -m verdra
```

Where Verdra keeps its files (PRIVACY.md lists the same paths):

| | Windows | Ubuntu |
|---|---|---|
| `settings.json` | `%LOCALAPPDATA%\Verdra\settings.json` | `~/.config/verdra/settings.json` |
| Log | `%LOCALAPPDATA%\Verdra\Logs\verdra.log` | `~/.local/state/verdra/logs/verdra.log` |

Next to `settings.json` are `settings.json.bak` (the last good copy) and, only while a write is
interrupted, a temporary file `.settings.json.<random>.tmp` (hidden: `ls -a`, or
`Get-ChildItem -Force` on Windows). Verdra deletes leftover temporary files the next time it
loads the settings.

On Ubuntu, check the session type with `echo $XDG_SESSION_TYPE` (`wayland` or `x11`). To get an
X11 session, log out, click the gear icon on the login screen and choose "Ubuntu on Xorg". Run
every Ubuntu step in both sessions.

## Steps

Each step says what passes. Anything else is a fail: note what you saw and, if you can, a
screenshot and the log file.

### 1. The app starts

1. Turn on Settings › Advanced › Detailed logging, quit Verdra from the tray menu, start it
   again.
2. **Pass:** the splash plays, then the main window appears with the sidebar, header and status
   pill; no error dialog. The log has `Startup: window shown after N ms` with N at most 1500
   (plan 12.4; S-01 test 15).
3. **Fail:** no window, a crash or traceback in the terminal, an error dialog, or N above 1500 on
   a machine that isn't under load.

### 2. Themes switch live

1. In Settings › Appearance, set Theme to "Match system".
2. Switch the OS between light and dark while Verdra is open: Windows Settings › Personalization
   › Colors › Choose your mode; Ubuntu Settings › Appearance › Style.
3. **Pass:** every part of the window (sidebar, header, screens, any open dialog) changes within
   about a second, without a restart, and back again.
4. **Fail:** no change, a change only after a restart, or parts left in the old theme.

### 3. Settings survive a forced kill during a write

The plan's exit-gate item. Do it twice: once with a script that writes the settings file
continuously (the kill is sure to land during a write), once with the real app.

**3a. Automated test** (the same test CI runs on the Windows and Linux runners):

```sh
uv run pytest tests/trunk/almanac/test_store.py -k kill_during_write -v
```

**Pass:** `1 passed`. It kills a writer 8 times at random moments during writes and checks
that the file is valid every time, that loading shows no notice and that no temporary file is
left.

**3b. Write storm, killed by hand, 5 times.** Quit Verdra first. Save this as `storm.py` in the
`verdra` folder (it writes the real `settings.json`, switching the theme setting back and forth
as fast as it can):

```python
import os
from PySide6.QtCore import QCoreApplication
from verdra.soil import terrain
from verdra.trunk.almanac.store import SettingsStore

app = QCoreApplication([])
store = SettingsStore(terrain.config_dir() / terrain.SETTINGS_FILE)
store.load()
print("PID", os.getpid(), "writing", store.path, flush=True)
while True:
    for theme in ("light", "dark"):
        store.set("appearance.theme", theme)
        store.flush(final=True)
```

Terminal 1: `uv run python storm.py` (it prints its PID). Wait 2 seconds, then in terminal 2:

| | Kill | Check the file | List temporary files |
|---|---|---|---|
| Windows (PowerShell) | `taskkill /F /PID <pid>` | `uv run python -m json.tool "$env:LOCALAPPDATA\Verdra\settings.json"` | `Get-ChildItem -Force "$env:LOCALAPPDATA\Verdra" -Filter ".settings.json.*.tmp"` |
| Ubuntu | `kill -9 <pid>` | `uv run python -m json.tool ~/.config/verdra/settings.json` | `ls -a ~/.config/verdra` |

Repeat 5 times. Then start Verdra (`uv run python -m verdra`).

- **Pass:** after every kill, `json.tool` prints the settings without an error (a
  `.settings.json.*.tmp` file may be there: that is the interrupted write). After Verdra starts:
  no notice about a damaged or unreadable settings file (M-SET-01, M-SET-02), the theme is
  "light" or "dark", `json.tool` still passes, and no `.settings.json.*.tmp` file is left.
- **Fail:** `json.tool` reports an error at any point; Verdra shows M-SET-01 or M-SET-02; a
  `settings.json.broken-<time>` file appears; a temporary file is still there after Verdra has
  started.

**3c. The real app, 5 times.** With Verdra running, change a setting in Settings (for example
switch Text size) and within a second kill Verdra:

- Windows (PowerShell): `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object CommandLine -like '*-m verdra*' | ForEach-Object { taskkill /F /PID $_.ProcessId }`
- Ubuntu: `pkill -9 -f 'python -m verdra'`

Start Verdra again each time. **Pass and fail** as in 3b; the setting shows either its old or
its new value.

Remove `storm.py` afterwards. To start over with default settings, quit Verdra and delete the
settings folder from the table above.

### 4. The rest of S-01 that CI can't check

1. **Single instance (S-01 tests 1 and 7).** With Verdra open, run `uv run python -m verdra`
   again; then run `uv run python -m verdra "roblox-player:1+launchmode:play"`. **Pass:** the
   second launch exits within about a second and the first window comes to the front; Activity
   shows "Another launch of Verdra brought this window to the front." and, for the link,
   "Verdra received a Roblox link. Opening games from links isn't available in this version
   yet." **Fail:** a second window, or no Activity line.
2. **Tray (S-01 tests 8 and 14).** Quit Verdra, delete `state.json` (next to `settings.json`;
   it remembers that the notice was shown), start Verdra and close the window with the close
   button. **Pass:** the window hides; the OS shows the notification "Verdra is still running in
   the tray. Quit it from the tray menu." on this first close only, and Activity shows the same
   sentence; the tray icon is there and its menu opens; left-click brings the window back; "Quit Verdra" in the menu quits. **Fail:** no tray
   icon, no notification on the first close, a notification on a later close, or Verdra still
   running after Quit. On Ubuntu the tray needs the "Ubuntu AppIndicators"
   extension, which Ubuntu turns on by default.
3. **Focus ring.** Press Tab through the window. **Pass:** each control shows a 2 px ring just
   outside its edge; clicking with the mouse shows no ring. **Fail:** a control you can't reach,
   or no visible ring.
4. **Text size.** Settings › Appearance › Text size at 90 % and 130 %. **Pass:** nothing is cut
   off or overlaps. **Fail:** clipped or overlapping text.
5. **About.** **Pass:** the buttons read "License", "Third-party notices" and "Privacy"; License
   and Privacy open their texts; Third-party notices is disabled with the tooltip "Release
   builds include this text; this build doesn't." (a source run has no notices file); there is
   no credit line. **Fail:** anything else.

## Results

One row per machine and step. Result: Pass, Fail or Skipped (say why in Notes).

| OS | Step | Result | Notes |
|---|---|---|---|
| Windows 11 | 1 App starts | | |
| Windows 11 | 2 Themes switch live | | |
| Windows 11 | 3a Kill test (automated) | | |
| Windows 11 | 3b Write storm, 5 kills | | |
| Windows 11 | 3c Real app, 5 kills | | |
| Windows 11 | 4 Rest of S-01 | | |
| Ubuntu 24.04, Wayland | 1 App starts | | |
| Ubuntu 24.04, Wayland | 2 Themes switch live | | |
| Ubuntu 24.04, Wayland | 3a Kill test (automated) | | |
| Ubuntu 24.04, Wayland | 3b Write storm, 5 kills | | |
| Ubuntu 24.04, Wayland | 3c Real app, 5 kills | | |
| Ubuntu 24.04, Wayland | 4 Rest of S-01 | | |
| Ubuntu 24.04, X11 | 1 App starts | | |
| Ubuntu 24.04, X11 | 2 Themes switch live | | |
| Ubuntu 24.04, X11 | 3c Real app, 5 kills | | |
| Ubuntu 24.04, X11 | 4 Rest of S-01 | | |

## Coverage

Every M0 item from Master plan 14, and where it is checked.

| M0 item | CI | This checklist | Notes |
|---|---|---|---|
| You: two-factor authentication and SSH commit signing on verdra-1 | | | Yours. The M0 commits are not signed with your key (they are signed off with the DCO trailer). |
| You: create the repository; apply the 13.2 settings | | | Yours. Branch protection is optional: CI and the autopilot rules stand in for it (plan 16.2). |
| You: new session without the old archive | | | Done. |
| Skeleton files (LICENSE, NOTICE, README with credits, not-affiliated and use-at-your-own-risk sections, SECURITY, PRIVACY, CONTRIBUTING with DCO, CODE_OF_CONDUCT, CHANGELOG) | SPDX header test; the build check compares LICENSE, NOTICE and PRIVACY.md | | The other files are checked by review only (present on every branch). |
| pyproject.toml, .python-version (3.14), uv.lock, licence allowlist, pre-commit | Lockfile and license gates | | pre-commit runs locally only. |
| ci.yml and nightly.yml with every 12.3 gate; release.yml as a stub | Every pull request | | nightly.yml runs only from `main` (schedule or manual start); it is started by hand once after the M0 merge. |
| Package skeleton and import-linter contracts | Docs and layering gates | | |
| Brand assets: tokens, logo SVGs, icons.py with every 4.6 size, fonts with their OFL texts | Icon check, raster-size test, token tests | | |
| Decision records 0001 to 0006 | Docs gate | | 0001 to 0014 exist. |
| Specs S-01 to S-04 merged, then built | Every automatable acceptance test, on the Windows and Linux runners | Step 4 (S-01 tests 1, 7, 14, 15) | |
| You: test machines ready | | All steps | The Windows PC, and Ubuntu in a virtual machine on it. |
| Exit gate: the app starts on Windows and Linux | Built app starts offscreen on both runners | Step 1 | |
| Exit gate: themes switch live | S-01 test 2 (offscreen) | Step 2 | |
| Exit gate: settings survive a forced kill during a write | S-02 test 1 on both runners | Steps 3a to 3c | |
| Exit gate: every CI gate is green | Every pull request | | |
