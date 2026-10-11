# Running Verdra from source for a test

From 8 October 2026 every real-machine test runs Verdra from its source on GitHub (decision
record 0021). You set up a folder once; before each test, one command brings it up to date and
starts Verdra. Your settings and replacement profiles stay in `%LOCALAPPDATA%\Verdra`, as with
the test build.

## Once: setting up (only what's missing)

Open **PowerShell** (Start menu, type `powershell`, press Enter) for each step.

1. Check git. Type this and press Enter:

   ```powershell
   git --version
   ```

   If it says "not recognized", install git:

   ```powershell
   winget install --id Git.Git -e --source winget
   ```

   Then close PowerShell and open it again (a new window finds the new program).

2. Check uv:

   ```powershell
   uv --version
   ```

   If it says "not recognized", install uv:

   ```powershell
   winget install --id astral-sh.uv -e
   ```

   Then close PowerShell and open it again.

3. Make room for the download. Windows doesn't tell `Verdra` and `verdra` apart, so an older
   `Documents\Verdra` folder (for example an unzipped test build) is in the way. Rename it to
   `Verdra-old` in File Explorer (right-click › Rename). Never delete it: it may hold something
   you need later. Skip this step if there is no such folder.

4. Go to your Documents folder:

   ```powershell
   cd "$env:USERPROFILE\Documents"
   ```

5. Download Verdra:

   ```powershell
   git clone https://github.com/verdra-1/verdra
   ```

   This makes a folder `Documents\verdra`. Don't change files in it; the update refuses to touch
   a folder with your own changes, so nothing of yours is ever overwritten.

## Every time: one command

1. Quit Verdra if it runs (tray icon › Quit Verdra), and any test build of it.
2. Open PowerShell and run (the `$` at the start of `$env:` matters):

   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Documents\verdra\tools\run-latest.ps1"
   ```

   The full path works whichever folder PowerShell is in. It says which commit it is at, sets
   up Python and Verdra's packages (a few minutes the first time, seconds after that) and
   starts Verdra. Keep that window open while you test: closing it closes Verdra. A guide that
   needs a diagnostic option adds it at the end of the same command.

If it stops with a yellow message, it changed nothing. The message says what to do (for
example the winget command for a missing program, or how to download a fresh copy); if it
doesn't help, send the window's text to the maintainer.

## Before every test: the checklist

Every test guide starts with these three checks:

1. **Detailed logging is on**: Settings › Detailed logging. It switches itself off after 24 hours,
   so turn it on again for each test day.
2. **Only the rows the step needs**: in Replacements, remove every other replacement row, or
   untick the profiles you don't need, so an older row can't change the result.
3. **"Moved…" in Activity before each join**: click Apply now, check that Activity shows the
   "Moved Roblox's saved assets…" line, and only then join the game.
