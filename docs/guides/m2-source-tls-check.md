# M2 step (g): the source run that tells where the fault is (about 10 minutes)

On 21 October the downloaded app (the ZIP) let Roblox connect for pictures, then Roblox hung up
before it asked for any: the wall stayed blank. Two things changed since the last test that
worked (15 October, from source): Verdra is now the built app, and Roblox has updated. This run
starts Verdra from source on today's Roblox, so only one of the two is different. Detailed
logging now also records which protocols Roblox asks for and how it hangs up.

**What to send, 3 files:**

1. A screenshot of the wall.
2. The copy of `verdra.log` you make in step 9.
3. A screenshot of the PowerShell window's first lines (they name the commit).

## Before you start

1. **Let Roblox finish updating, so it doesn't update during the test.** Start the Roblox app
   from the Start menu (not through Verdra) and wait until its home screen shows. If it
   updated, close it and start it once more. Then close it.
2. Open Task Manager (Ctrl+Shift+Esc). On the **Processes** tab, end every entry whose name
   starts with "Roblox" (select it, **End task**).
3. Quit Verdra if it runs (tray icon › Quit Verdra), including the downloaded app.

## The checklist

1. **Detailed logging is on:** Settings › Detailed logging (it turns itself off after 24 hours,
   so it was off when you started on 21 October). Turn it on before you join, in step 2.
2. **Only the row this step needs:** in Replacements, keep only original **15553230204** ›
   **Local file** › `verdra-test-1600x900.png`, with no warning on the row. Untick or remove
   everything else.
3. **"Moved…" in Activity before the join:** after Apply now, Activity shows "Moved Roblox's
   saved assets…" before you click Play.

## Steps

1. Open PowerShell and run this command:

   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Documents\verdra\tools\run-latest.ps1" --format-check
   ```

   Take the screenshot of its first lines (the commit). Keep the window open; closing it
   closes Verdra.
2. In Verdra, turn on **Settings › Detailed logging** (checklist point 1).
3. In Replacements, keep only the row of checklist point 2.
4. Click **Apply now**. Activity shows "Moved Roblox's saved assets…".
5. Start the game from the **Roblox website** (the green Play button). If Verdra asks "Roblox
   is already running without Verdra", click **Close Roblox and continue**.
6. If Activity says "Roblox updated" during the test, Roblox updated after all. Leave the
   game, then start again at step 4.
7. **Stay in the game for at least 2 minutes.** Walk up to the wall.
8. Take the screenshot of the wall (Win+Alt+PrtScn). It lands in `Videos\Captures`.
9. **While you're still in the game, with Verdra running,** copy the log. Paste this into File
   Explorer's address bar and press Enter:

   ```text
   %LOCALAPPDATA%\Verdra\Logs
   ```

   Copy `verdra.log` to your Desktop (right-click › Copy, then on the Desktop right-click ›
   Paste).
10. Only now leave the game and quit Verdra (tray icon › Quit Verdra).

## What the result means

You don't need to read the log; the maintainer does. If you want to look: open the copy in
Notepad and search (Ctrl+F) for `POST assetdelivery`.

- **The wall shows the picture, and the log has "POST assetdelivery…" lines.** The source
  run works on today's Roblox, so the fault is in how the downloaded app is built. The fix
  makes the built app's secure connections the same as a source run's. You then test one new
  ZIP.
- **The wall stays blank, and the log has "closed a secure connection … before its first
  request" lines.** Roblox changed how it downloads. Verdra then has to learn what Roblox now
  asks for (most likely the newer web protocol, HTTP/2). That is a bigger piece of work, and
  M2 isn't finished until it is built.

Either way, the new lines starting "TLS with Roblox for assetdelivery.roblox.com" record what
Roblox asked for, so the next step is planned from evidence. They hold no password, cookie or
account data: protocol and cipher names, and the certificate Verdra made.
