# M2 final test: step (g) again (about 5 minutes)

Step (g) of the [final M2 test](m2-final-test.md) failed on 15 October: with the release dry-run
ZIP the wall stayed grey. The cause found on a Windows runner is fixed (a Roblox started by the
built Verdra inherited Verdra's own program folder), and the dry run now refuses to make a ZIP
that doesn't serve a replacement in a test. This repeats only step (g), with a new ZIP. Nothing
is published: the ZIP is a workflow artifact, kept 5 days (decision record 0026).

**What to send, at most 5 files under 30 MB each:**

1. A screenshot of the wall.
2. A screenshot of Activity.
3. `verdra.log`.
4. Only if the status turns Degraded: a screenshot of its message, and the support bundle.

## Before you start: the checklist

1. **Detailed logging is on:** Settings › Detailed logging (it turns itself off after 24 hours).
   The ZIP's Verdra uses the same settings as Verdra from source.
2. **Only the row this step needs:** in Replacements, keep one row (below) and remove the
   others (select, **Remove**), or untick profiles you don't need.
3. **"Moved…" in Activity before the join:** click **Apply now**, check that Activity shows
   "Moved Roblox's saved assets…", and only then join.

## Steps

1. Quit Verdra if it runs (tray icon › Quit Verdra) and close the Roblox Player.
2. In Downloads, delete the folder `Verdra-0.0.1-windows` from the last test.
3. Open the run page from the maintainer's message, sign in to GitHub if asked, and under
   **Artifacts** click **Verdra-0.0.1-windows.zip**.
4. Right-click the ZIP › **Extract All…** and keep the folder Windows suggests
   (`Downloads\Verdra-0.0.1-windows`).
5. In that folder, open **Verdra** and double-click **verdra.exe**. If Windows says "Windows
   protected your PC", click **More info**, then **Run anyway**.
6. In Replacements, keep only: original **15553230204** › **Local file** ›
   `verdra-test-1600x900.png`.
7. Click **Apply now**, check "Moved…" in Activity, and join your place.
8. Take a screenshot of the wall (Win+Alt+PrtScn). Expected: the 1600 × 900 picture.
9. Wait one minute in the game, then open Verdra and take a screenshot of **Activity**.
   Expected: no line saying "Roblox isn't reaching Verdra" or "couldn't open a secure
   connection".
10. Look at the status at the top right of Verdra's window. If it says **Degraded**, click it,
    take a screenshot of the message, click **Save a support bundle…** and save the file.
11. Leave the game and quit Verdra (tray icon › Quit Verdra).

`verdra.log` is in `%LOCALAPPDATA%\Verdra\Logs` (paste that path into File Explorer's address
bar). Screenshots land in `Videos\Captures`.
