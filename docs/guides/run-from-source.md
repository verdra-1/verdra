# Running Verdra from source for a test

From 8 October 2026 every real-machine test runs Verdra from its source on GitHub (decision
record 0021). You set up a folder once; before each test, one command brings it up to date and
starts Verdra. Your settings and replacement profiles stay in `%LOCALAPPDATA%\Verdra`, as with
the test build.

## Once: setting up (only what's missing)

1. Open **PowerShell** (Start menu, type `powershell`, press Enter).
2. Check git: type `git --version` and press Enter. If it says "not recognized", install it with
   `winget install --id Git.Git -e`, then close PowerShell and open it again.
3. Check uv: type `uv --version`. If it says "not recognized", install it with
   `winget install --id astral-sh.uv -e`, then close PowerShell and open it again.
4. Download Verdra into your Documents folder:

   ```powershell
   cd "$env:USERPROFILE\Documents"
   git clone https://github.com/verdra-1/verdra
   ```

   This makes a folder `Documents\verdra`. Don't change files in it; the update refuses to touch a
   folder with your own changes, so nothing of yours is ever overwritten.

## Every time: one command

1. Quit Verdra if it runs (tray icon › Quit Verdra), and any test build of it.
2. Open PowerShell (Start menu, type `powershell`, press Enter) and run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Documents\verdra\tools\run-latest.ps1"
   ```

   The full path works whichever folder PowerShell is in. It says which commit it is at, sets
   up Python and Verdra's packages (a few minutes the first time, seconds after that) and
   starts Verdra. Keep that window open while you test: closing it closes Verdra. A guide that
   needs a diagnostic option adds it at the end of the same command.

   The first time after setting up an older copy, update it once by hand:
   `cd "$env:USERPROFILE\Documents\verdra"`, then `git pull --ff-only`.

If it stops with a yellow message, it changed nothing; send the window's text to the maintainer.
