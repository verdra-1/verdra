# Your first texture swap

A beginner's guide to seeing a Verdra replacement in a real Roblox game on Windows, through the
**Roblox Player** started by Verdra.

This is the **second attempt**. The first one (5 October 2026) showed only the original picture;
the most likely reason is that Roblox had the picture saved already. Verdra can now move Roblox's
saved assets aside before the test, and its log now names every picture Roblox asks for. You
keep the place, the two pictures and the replacement you made last time.

**Before you start:** you need the place you published last time, with the first picture on the
wall, and the replacement in Verdra's **My replacements** profile (original → replacement). Your
replacement profiles and settings live in `%LOCALAPPDATA%\Verdra`, so updating Verdra keeps them.

## Steps

1. **Close everything Roblox.** Close the Roblox Player and **Roblox Studio** (both must be
   closed: Verdra moves Roblox's saved assets only then). Quit Verdra (tray icon › Quit Verdra).
   In Task Manager (Ctrl+Shift+Esc), check that no **Roblox** or **RobloxStudioBeta** is left.

2. **Update Verdra.** In PowerShell:

   ```powershell
   cd "$env:USERPROFILE\Downloads\verdra-src"
   Remove-Item verdra-old -Recurse -Force -ErrorAction SilentlyContinue; Rename-Item verdra-main verdra-old
   Invoke-WebRequest https://github.com/verdra-1/verdra/archive/refs/heads/main.zip -OutFile verdra-main.zip
   Expand-Archive verdra-main.zip -DestinationPath . -Force
   cd verdra-main; uv sync --locked
   ```

3. **Look at Roblox's saved assets (read only).** In the same PowerShell window, run this; it
   only reads names, sizes and dates, and changes nothing. Copy what it prints into a text file
   called `before.txt`:

   ```powershell
   Get-ChildItem "$env:LOCALAPPDATA\Roblox" -Force -Filter 'rbx-storage*' | ForEach-Object { $size = if ($_.PSIsContainer) { (Get-ChildItem $_.FullName -Recurse -File -Force | Measure-Object Length -Sum).Sum } else { $_.Length }; '{0} | {1} bytes | {2:yyyy-MM-dd HH:mm}' -f $_.Name, $size, $_.LastWriteTime }
   ```

4. **Start Verdra.** Run `uv run python -m verdra`. Check that Settings › Advanced › **Detailed
   logging** is on. In **Replacements**, check that **My replacements** is ticked and shows your
   row (the original number and the replacement number).

5. **Apply now.** With Roblox and Studio still closed, click **Apply now** at the top. You should
   see two messages: "Moved Roblox's saved assets (…) to …\Roblox cache backup\…. Reset everything
   puts them back." and "Applied 1 replacement. They'll appear next time Roblox starts." If you
   see "Roblox Studio is open…" or "A Roblox Player that Verdra didn't start is running…", close
   it in Task Manager and click Apply now again.

6. **Join your place.** In your web browser, open your place (create.roblox.com › Creations ›
   your place › View on Roblox) and press the green **Play** button. Roblox starts through
   Verdra. Don't open Studio during the test.

7. **Look at the wall** and write down which picture you see: the first (original) or the second
   (replacement).

8. **Close the Player**, then run the command from step 3 again and copy what it prints into
   `after.txt`.

9. **Send the results.** Quit Verdra (tray icon › Quit Verdra), then send me:
   - which picture you saw (step 7);
   - `before.txt` and `after.txt`;
   - the file `%LOCALAPPDATA%\Verdra\Logs\verdra.log` (paste that path into File Explorer's
     address bar).

10. **Optional: undo.** Settings › System changes › **Reset everything** puts Roblox's saved
    assets back from the backup, along with every other change Verdra made (as in Stage 2).

## What Apply now changes on your PC

1. It makes the proxy use your replacements (in memory).
2. If routing is off, it starts it: Verdra's certificate block in the Roblox **Player**'s
   `ssl\cacert.pem` and the Roblox link handler, each in the list of system changes first.
3. Only if no Roblox Player and no Roblox Studio is running, it **moves** (never deletes) these
   four items from `%LOCALAPPDATA%\Roblox` into a new folder under
   `%LOCALAPPDATA%\Verdra\Roblox cache backup`: `rbx-storage.db`, `rbx-storage.db-wal`,
   `rbx-storage.db-shm` and the `rbx-storage` folder. The move is in the list of system changes
   first. Nothing else is touched: not `rbx-storage.id`, `rbx-storage-sc`, `LocalStorage`,
   `logs`, `GlobalBasicSettings_13.xml`, `frm.cfg`, any other settings file, or anything of
   Roblox Studio. Roblox downloads what it needs again.
4. If a Roblox that Verdra started is running, it asks first, closes only that one, moves the
   saved assets, and starts it again. It never closes Studio or a Roblox it didn't start.

**What is proven and what isn't:** those four items are the only database and storage folder
in Roblox's folder, and the plan calls them "the asset cache database". That they hold only
downloaded assets is probable, not proven (Roblox doesn't document it); steps 3 and 8 show
whether the Player writes to them while you play. Reset everything puts them back exactly; if
Roblox has made new ones in the meantime, Verdra keeps the old ones in the backup folder and
tells you where it is.

## What the log contains

Times, what Verdra did, the Roblox hosts it saw, and, while replacements are on, one line per
picture request: which asset numbers Roblox asked for, which ones were replaced, and the names
(not the values) of the fields in the request. Asset numbers are public. Login tokens and signed
links are always removed.

- Your **Windows user name** may appear inside folder paths. That's fine to send me; it's never
  committed to the repository.
- Your **Roblox user ID and Roblox user name** shouldn't appear. If you do see either, it's still
  fine to send me, and I'll fix the log so it never happens again.

## Undoing everything

Untick the profile and click **Apply now** to stop the swap. Settings › System changes ›
**Reset everything** removes everything Verdra changed on your PC and puts Roblox's saved assets
back.
