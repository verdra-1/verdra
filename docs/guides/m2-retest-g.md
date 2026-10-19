# M2 final test: step (g) again (about 10 minutes)

Step (g) of the [final M2 test](m2-final-test.md) didn't pass on 16 October: the game joined
through Verdra, but Roblox asked for no picture and the wall showed the original. The most
likely cause: a Roblox that Verdra didn't start ran after Apply now and saved the original
pictures again, and Verdra started its own Roblox without moving them aside. Verdra now moves
them aside again right before it starts Roblox, and says so in Activity. This repeats step (g)
with a new ZIP. Nothing is published: the ZIP is a workflow artifact, kept 5 days (decision
record 0026).

**What to send, at most 5 files under 30 MB each:**

1. A screenshot of the wall.
2. A screenshot of Activity, showing the "Moved…" and "Started Roblox through Verdra" lines.
3. `verdra.log`.
4. Only if the status turns Degraded: a screenshot of its message, and the support bundle.

## Before you start: close every Roblox

1. Leave any game and close every Roblox window.
2. Open Task Manager (Ctrl+Shift+Esc). On the **Processes** tab, select each entry whose name
   starts with "Roblox" and click **End task**. Do the same for any other Roblox launcher you
   use. Leave Task Manager open: you need it again in step 12.
3. Quit Verdra if it runs (tray icon › Quit Verdra).

## The checklist

1. **Detailed logging is on:** Settings › Detailed logging (it turns itself off after 24 hours).
2. **Only the row this step needs, and its file exists:** in Replacements, keep one row (below)
   and remove the others (select, **Remove**), or untick profiles you don't need. On 16 October
   the first try used a file that had moved: check that `verdra-test-1600x900.png` is where the
   row says.
3. **"Moved…" directly before "Started Roblox through Verdra":** in Activity, the line
   "Moved Roblox's saved assets…" must come right before "Started Roblox through Verdra
   (process …)". If anything else is between them, or "Moved…" is missing, stop and send what
   you have.

## Steps

1. In Downloads, delete the folder `Verdra-0.0.1-windows` from the last test, and the old ZIP.
2. Open the run page from the maintainer's message, sign in to GitHub if asked, and under
   **Artifacts** click **Verdra-0.0.1-windows.zip**.
3. Right-click the ZIP › **Extract All…** and keep the folder Windows suggests
   (`Downloads\Verdra-0.0.1-windows`).
4. In that folder, open **Verdra** and double-click **verdra.exe**. If Windows says "Windows
   protected your PC", click **More info**, then **Run anyway**.
5. Check the status at the top right. If it says Roblox is running without Verdra, go back to
   "Before you start", step 2.
6. In Replacements, keep only: original **15553230204** › **Local file** ›
   `verdra-test-1600x900.png`. The row must not show a warning.
7. Click **Apply now**. Activity shows "Moved Roblox's saved assets…".
8. Start the game from the **Roblox website** (the green Play button), not from the Roblox app,
   so the join goes through Verdra. If Verdra asks "Roblox is already running without Verdra",
   click **Close Roblox and continue**.
9. In Activity, check the checklist's point 3: "Moved…", then directly "Started Roblox through
   Verdra". Take a screenshot of Activity.
10. In the game, take a screenshot of the wall (Win+Alt+PrtScn). Expected: the 1600 × 900
    picture.
11. Wait one minute in the game, then look at the status at the top right of Verdra's window.
    If it says **Degraded** or "Needs you", click it, take a screenshot of the message, click
    its button if it is **Save a support bundle…**, and save the file.
12. While you're still in the game, look in Task Manager: which Roblox entries are running?
    Write their names down (only the names).
13. Leave the game and quit Verdra (tray icon › Quit Verdra).

`verdra.log` is in `%LOCALAPPDATA%\Verdra\Logs` (paste that path into File Explorer's address
bar). Screenshots land in `Videos\Captures`.
