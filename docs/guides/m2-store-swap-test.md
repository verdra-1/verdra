# M2: the store-swap test (about 12 minutes)

Option A of decision record 0028 would put your replacement where Roblox looks before it
downloads: its saved assets. This test answers the one question that decides whether that can
work: **does Roblox check what it reads from its saved assets?**

The test swaps two pictures Roblox itself saved, then joins again.

- **The wall shows another picture:** Roblox doesn't check, and option A can work.
- **The wall shows its own picture again:** Roblox noticed and fetched it again, and option A is
  blocked.

**What is changed, and how it is undone:**

- Apply now first moves your real saved assets into Verdra's backup (as always). Roblox then
  builds a fresh store in one join, and only that fresh store is touched.
- Only Roblox's own bytes are used: the swap exchanges two pictures' entries.
- The tool works only when no Roblox and no Roblox Studio is running.
- Before it writes, it saves the original bytes and records the change in Settings › System
  changes, so `undo` (step 12) or Reset everything puts them back.
- It prints only sizes, formats and counts.

After the test, don't start an older downloaded Verdra ZIP: it doesn't know this new kind of
system change. Running from source, as here, is fine.

**What to send:**

1. Screenshots of the wall from step 6 and step 10.
2. The text the tool prints in steps 8, 9 and 11 (select it in PowerShell, right-click to copy,
   paste into a text file).
3. `verdra.log` (step 13).

## Before you start

1. Leave any game and close every Roblox window.
2. Open Task Manager (Ctrl+Shift+Esc). On the **Processes** tab, end every entry whose name
   starts with "Roblox".
3. Quit Verdra if it runs (tray icon › Quit Verdra).

## The checklist

1. **Detailed logging is on:** Settings › Detailed logging.
2. **Only the row this step needs:** in Replacements, keep only original **15553230204** ›
   **Local file** › `verdra-test-1600x900.png`. Verdra decrypts nothing in this test (the
   command in step 1), so the row only lets Apply now move the saved assets.
3. **"Moved…" in Activity before the first join:** click Apply now and check that Activity
   shows "Moved Roblox's saved assets…".

## Steps

**Keep Verdra open from step 1 to step 12, and don't click Apply now again.** A restart or a
second Apply now would move the swapped store aside before the second join.

1. Open PowerShell and run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Documents\verdra\tools\run-latest.ps1" --no-intercept assetdelivery.roblox.com,fts.rbxcdn.com
   ```

2. Go through the checklist: Detailed logging on, the one row, **Apply now** › "Moved…".
3. Start the game from the **Roblox website** (the green Play button).
4. Stay in the game for at least 1 minute and walk up to the wall.
5. Expected: the original picture of 15553230204.
6. Take a screenshot of the wall (Win+Alt+PrtScn).
7. Leave the game. In Task Manager, end any entry starting with "Roblox". Don't quit Verdra.
8. Open a **second** PowerShell window and let the tool show what it would swap (it only
   reads):

   ```powershell
   uv run --directory "$env:USERPROFILE\Documents\verdra" python -m tools.store_swap plan --original 500x500
   ```

   It lists the pictures in the store and ends with "Would swap picture … (the wall) with
   picture …". If it starts with "Nothing was changed", stop here and send what you have.
9. Swap them:

   ```powershell
   uv run --directory "$env:USERPROFILE\Documents\verdra" python -m tools.store_swap swap --original 500x500 --yes
   ```

   It ends with "every write read back as written".
10. Start the game from the Roblox website again (don't click Apply now). Stay at least
    1 minute, walk up to the wall, and take a screenshot. Look at the wall: is it the same
    picture as in step 6, or another one?
11. Leave the game, end any "Roblox" entry in Task Manager, then run in the second window:

    ```powershell
    uv run --directory "$env:USERPROFILE\Documents\verdra" python -m tools.store_swap check
    ```

12. Put the original bytes back:

    ```powershell
    uv run --directory "$env:USERPROFILE\Documents\verdra" python -m tools.store_swap undo
    ```

13. Quit Verdra (tray icon › Quit Verdra). Copy `verdra.log` from `%LOCALAPPDATA%\Verdra\Logs`
    (paste that path into File Explorer's address bar) to your Desktop.

## What the result means

- **Step 10 shows another picture, and step 11 says the entries are still as the test wrote
  them:** Roblox doesn't check what it reads. Option A can work. Building it needs your
  separate yes (decision record 0028).
- **Step 10 shows the original again, and step 11 says Roblox rewrote the entries:** Roblox
  noticed the swap, either by checking the bytes or because the entries had expired. The
  maintainer tells the two apart from `verdra.log` (whether Roblox downloaded the picture again)
  and proposes the next test.
- **Step 11 says the entries are no longer in the store:** the swapped store was moved aside
  before the second join (for example by a second Apply now). The test didn't run. It can be
  repeated.
