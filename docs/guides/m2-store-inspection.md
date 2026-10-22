# M2: a look at how Roblox saves pictures (about 10 minutes, read-only)

Roblox now refuses Verdra's certificate on both of its asset servers (the pass-through control,
22 October 2026). The one way left within Verdra's rules is to put a replacement where Roblox
looks before it downloads: the saved assets in `%LOCALAPPDATA%\Roblox` (decision record 0028,
option A). Roblox doesn't document how that store works, so this step only looks at it.

**Nothing in Roblox's folder is changed.** You copy the files to your Desktop, and Verdra's
inspector reads the copy. It refuses Roblox's own folder. The report holds only the store's
structure: table and column names, how values and file names look (for example "hex32"), counts,
sizes and file formats. It holds no value, no file content, no web address and no account data.
Read it before you send it.

This run also answers one open question from 22 October: does the original picture appear when
Verdra decrypts nothing?

**What to send:**

1. A screenshot of the wall (step 6).
2. `verdra-store-report.txt` from your Desktop (step 10).

## Before you start

1. Leave any game and close every Roblox window.
2. Open Task Manager (Ctrl+Shift+Esc). On the **Processes** tab, end every entry whose name
   starts with "Roblox".
3. Quit Verdra if it runs (tray icon › Quit Verdra).

## The checklist

1. **Detailed logging is on:** Settings › Detailed logging.
2. **Only the row this step needs:** in Replacements, keep only original **15553230204** ›
   **Local file** › `verdra-test-1600x900.png`. The command in step 1 makes Verdra decrypt
   nothing, so Roblox downloads the original picture itself (as in run 2 of the pass-through
   control).
3. **"Moved…" in Activity before the join:** click Apply now and check that Activity shows
   "Moved Roblox's saved assets…", so Roblox starts from an empty store and saves only what this
   join loads.

## Steps

1. Open PowerShell and run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Documents\verdra\tools\run-latest.ps1" --no-intercept assetdelivery.roblox.com,fts.rbxcdn.com
   ```

   Verdra shows the yellow notice "Pass-through control is on".

2. Go through the checklist: Detailed logging on, the one row, **Apply now** › "Moved…".
3. Start the game from the **Roblox website** (the green Play button).
4. Stay in the game for at least 2 minutes and walk up to the wall.
5. Expected: the **original** picture of asset 15553230204 (not your replacement).
6. Take a screenshot of the wall (Win+Alt+PrtScn).
7. Leave the game. In Task Manager, check that no "Roblox" entry is left (end it if one is).
   Quit Verdra (tray icon › Quit Verdra), and close the PowerShell window.
8. Open a new PowerShell window and copy the store to your Desktop. Run each line on its own:

   ```powershell
   New-Item -ItemType Directory "$env:USERPROFILE\Desktop\verdra-store-copy"
   ```

   ```powershell
   Copy-Item "$env:LOCALAPPDATA\Roblox\rbx-storage.db*" "$env:USERPROFILE\Desktop\verdra-store-copy"
   ```

   ```powershell
   Copy-Item "$env:LOCALAPPDATA\Roblox\rbx-storage" "$env:USERPROFILE\Desktop\verdra-store-copy" -Recurse
   ```

9. Run the inspector on the copy:

   ```powershell
   uv run --directory "$env:USERPROFILE\Documents\verdra" python tools\inspect_store.py "$env:USERPROFILE\Desktop\verdra-store-copy" --asset 15553230204 --out "$env:USERPROFILE\Desktop\verdra-store-report.txt"
   ```

   It prints the report and saves it as `verdra-store-report.txt` on your Desktop.
10. Open `verdra-store-report.txt`, read it, and send it with the screenshot.
11. Delete the folder `verdra-store-copy` from your Desktop. It is only a copy.

## What the report tells the maintainer

- **How Roblox finds a saved picture:** whether a table links asset IDs (such as 15553230204)
  to stored files, or stores them only by a content hash.
- **Whether the store is content-addressed:** whether each file's name is a hash of its own
  bytes. If it is, Roblox *could* check what it reads. That isn't proof that it does; a later
  test, which needs your approval, settles it.
- **What format the files are in** (KTX2 pictures, compressed data, meshes…), and so what
  Verdra would have to write.

Nothing is built from this report until you approve option A.
