# M2 step (g): the pass-through control (about 12 minutes)

On 21 October, run from source, Roblox finished every secure connection to Verdra for
assetdelivery.roblox.com and then hung up before asking for anything, 26 times. Both sides
agreed on everything the log shows (TLS 1.3, HTTP/1.1). What's left is that Roblox doesn't
accept something about Verdra's certificate after the connection is made. This test changes one
thing at a time:

- **Run 1:** Verdra doesn't decrypt assetdelivery at all and passes it through, like every other
  Roblox server. The pictures themselves still come through Verdra's decryption
  (fts.rbxcdn.com). Verdra also writes down the real server's certificate, to compare with its
  own.
- **Run 2, only if the wall is blank in run 1:** Verdra decrypts nothing.
- **Run 3:** everything decrypted as usual, but Verdra also sends its own certificate authority
  with each certificate. If that alone fixes the wall, the cause is how the certificate is
  sent, nothing deeper.

Replacements can't show in runs 1 and 2: what matters there is whether the **original** picture
appears. Nothing is installed or changed beyond what Verdra always does.

**What to send, at most 5 files:**

1. A screenshot of the wall in each run you did (2 or 3 pictures).
2. `verdra.log`, copied once at the end (step 13).
3. A screenshot of the PowerShell window's first lines from run 1 (the commit).

## Before you start

1. **Let Roblox finish updating, so it doesn't update during the test.** Start the Roblox app
   from the Start menu (not through Verdra) and wait until its home screen shows. If it
   updated, close it and start it once more. Then close it.
2. Open Task Manager (Ctrl+Shift+Esc). On the **Processes** tab, end every entry whose name
   starts with "Roblox".
3. Quit Verdra if it runs (tray icon › Quit Verdra).

## The checklist (before every run)

1. **Detailed logging is on:** Settings › Detailed logging.
2. **Only the row this step needs:** in Replacements, keep only original **15553230204** ›
   **Local file** › `verdra-test-1600x900.png`.
3. **"Moved…" in Activity before each join:** click Apply now and check that Activity shows
   "Moved Roblox's saved assets…" before you click Play.

## Run 1: assetdelivery passed through

1. Open PowerShell and run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Documents\verdra\tools\run-latest.ps1" --no-intercept assetdelivery.roblox.com
   ```

   Take the screenshot of its first lines. Verdra shows a yellow notice starting "Pass-through
   control is on".
2. Go through the checklist (Detailed logging, the one row, **Apply now** › "Moved…").
3. Start the game from the **Roblox website** (the green Play button). If Verdra asks "Roblox
   is already running without Verdra", click **Close Roblox and continue**.
4. Stay in the game for at least 2 minutes, walk up to the wall, and take a screenshot
   (Win+Alt+PrtScn).
5. Leave the game, then quit Verdra (tray icon › Quit Verdra).

**Wall blank?** Do run 2 next. **Original picture (not yours)?** Skip run 2 and go to run 3.

## Run 2 (only if run 1's wall was blank): nothing decrypted

6. In PowerShell run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Documents\verdra\tools\run-latest.ps1" --no-intercept assetdelivery.roblox.com,fts.rbxcdn.com
   ```

7. The checklist, the join from the website, at least 2 minutes, a screenshot of the wall,
   leave the game, quit Verdra, as in run 1.

## Run 3: Verdra's certificate authority sent along

8. In PowerShell run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Documents\verdra\tools\run-latest.ps1" --send-ca
   ```

   The yellow notice starts "Verdra sends its own certificate authority".
9. Go through the checklist, then join from the website.
10. Stay at least 2 minutes and take a screenshot of the wall. Expected if nothing changed: blank.
11. While still in the game, look at Verdra's status at the top right. Note whether it says
    Degraded.
12. Leave the game, but don't quit Verdra yet.
13. Copy the log: paste this into File Explorer's address bar and press Enter, then copy
    `verdra.log` to your Desktop.

    ```text
    %LOCALAPPDATA%\Verdra\Logs
    ```

14. Quit Verdra (tray icon › Quit Verdra).

## What the results mean

- **Run 1 shows the original picture:** the download path is healthy, and the only thing that
  breaks it is Verdra decrypting assetdelivery with its own certificate. The log then also
  says whether Roblox still accepts Verdra on the picture server (fts.rbxcdn.com). If it does,
  one way forward keeps today's design but reads only the picture server. If not, M2 needs a
  different design. Either way, you decide the direction before anything is built.
- **Run 1 blank, run 2 shows the original:** Roblox refuses Verdra on the picture server too.
  This is the same conclusion as above, for both servers.
- **Runs 1 and 2 both blank:** Roblox no longer fetches this picture over the connections
  Verdra sees. The log shows where its traffic went instead. That is a different and bigger
  problem.
- **Run 3 shows your picture:** sending the certificate authority along fixes it. That is a
  small change, and nothing deeper is needed.

The log lines starting "The real server for assetdelivery.roblox.com" describe Roblox's own
certificate (who issued it, its key and its timestamps) for the comparison. They hold no
password, cookie or account data.
