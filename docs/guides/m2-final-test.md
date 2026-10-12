# M2 final test: a large picture, the mesh report, the release

Three short checks on your PC. Steps (e) and (f) run Verdra from source, as before; step (g)
tries the release you download from GitHub, and waits until you have said yes to 0.1.0 and the
release page exists.

Send at most **5 files, each under 30 MB**: the log, the diagnostics folder as a ZIP, the video
from (e), and the screenshots from (g).

## Before you start: the checklist

1. **Detailed logging is on:** Settings › Detailed logging (it turns itself off after 24 hours).
2. **Only the rows these steps need:** in Replacements, keep only the two rows below and remove
   or untick every other one.
3. **"Moved…" in Activity before each join:** click Apply now, check that Activity shows
   "Moved Roblox's saved assets…", and only then join.

## (e) and (f): one source run

1. Close the Roblox Player and Roblox Studio. Quit Verdra if it runs (tray icon › Quit Verdra).
2. Open PowerShell and start Verdra with the format check for the picture and the mesh:

   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Documents\verdra\tools\run-latest.ps1" --format-check 15553230204,498788302
   ```

3. In Replacements, make (or keep) exactly these two rows:
   - Original **15553230204** › **Local file** › your **1600 × 900 PNG** (the one refused last
     time). It should now save without a message.
   - Original **498788302** › **Local file** › the **cube** file from the mesh test.
4. Click **Apply now** and check the "Moved…" line in Activity.
5. Join your place.
6. **(e)** Start a screen recording (Win+Alt+R), stand far from the wall, and walk slowly toward
   it, about 15 seconds. Stop the recording (Win+Alt+R).
   Expected: the picture is visible from far away and close up, never black.
7. **(f)** Look at the mesh part. Expected: the cube, drawn with the part's own texture (that is
   normal: Verdra replaces the shape only).
8. Close the Player, then quit Verdra (tray icon › Quit Verdra).

What to send from (e) and (f):

- The log: `%LOCALAPPDATA%\Verdra\Logs\verdra.log`.
- The diagnostics folder `%LOCALAPPDATA%\Verdra\diagnostics` as a ZIP (right-click › Send to ›
  Compressed (zipped) folder). It should hold `format-check-498788302-…` reports from today:
  that confirms the mesh report appears.
- The video from (e), from `Videos\Captures`.

## (g): the release build

Only once the release page https://github.com/verdra-1/verdra/releases/tag/v0.1.0 exists.

1. Make sure Verdra from source isn't running (tray icon › Quit Verdra, and close its PowerShell
   window).
2. On the release page, download **Verdra-0.1.0-windows.zip** (it lands in Downloads).
3. Right-click the ZIP › **Extract All…** and keep the folder Windows suggests
   (`Downloads\Verdra-0.1.0-windows`). Don't extract it into Documents: your source folder
   `Documents\verdra` has the same name, and Windows treats `Verdra` and `verdra` as one.
4. Open `Verdra-0.1.0-windows\Verdra` and double-click **verdra.exe**. If Windows says "Windows
   protected your PC", click **More info**, then **Run anyway**.
5. In Verdra, click **About** at the bottom of the sidebar, then **Third-party notices**. Take a
   screenshot (Win+Shift+S) of the window that opens.
6. In Replacements, keep only the picture row (15553230204 › your PNG); untick the mesh row.
7. Click **Apply now**, check the "Moved…" line in Activity, and join your place.
8. Take a screenshot of the wall. Expected: your picture.
9. Close the Player and quit Verdra.

What to send from (g): the two screenshots. If something looked wrong, also the log again.
