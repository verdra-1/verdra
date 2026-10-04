# Your first texture swap

A beginner's guide to seeing a Verdra replacement in a real Roblox game on Windows, through the
**Roblox Player** started by Verdra. It takes about 25 minutes.

You'll make a tiny place with one picture on a wall, using two pictures that already exist in
Roblox's public library (nothing to upload or wait for). Then you tell Verdra to show the second
picture instead of the first, and join the place in the Roblox Player. If the wall shows the
second picture, the swap works. Only your screen changes; the place stays as you published it.

**Why a place of your own and not a public game:** this needs the number of a picture you can
see on screen. In a public game nobody can tell which picture is which number without tools,
and the game can change at any time. Two pictures from the Toolbox give you both numbers in
Studio's Properties panel, and nothing else in the place can get in the way.

**What it costs:** nothing. Publishing a place and using Toolbox pictures are free; the place
stays private (only you can join it).

**Roblox Studio is only used to build the place.** Pressing Play inside Studio would not go
through Verdra and would prove nothing; the test is the Roblox Player in steps 7 and 8.

## Steps

1. **Replace your Verdra folder with the new version.** Your settings, the replacement profiles
   and the list of system changes live in `%LOCALAPPDATA%\Verdra`, not in the folder you
   downloaded, so this keeps them (that's intended).
   - Stage 2 ended with **Reset everything**, so nothing on your PC points at the old folder. If
     you skipped it, start the old Verdra once and run Settings › System changes › Reset
     everything first.
   - Quit Verdra if it's running (tray icon › Quit Verdra).
   - Rename your old folder (for example `verdra-main`) to `verdra-old`. Delete it after the
     test.
   - Download the new version: <https://github.com/verdra-1/verdra/archive/refs/heads/main.zip>.
     Right-click the ZIP › **Extract All…**, and extract it where the old folder was. Windows
     makes a folder `verdra-main` with another `verdra-main` inside; use the inner one, the one
     that holds `pyproject.toml`.
   - Open **PowerShell** in that folder (in File Explorer, open it, click the address bar, type
     `powershell`, press Enter), then run:

     ```powershell
     uv sync --locked
     uv run python -m verdra
     ```

   - In Verdra, open Settings › Advanced and turn on **Detailed logging**. Check that Settings ›
     Routing › **Open games started from the Roblox website through Verdra** is on (it is by
     default).

2. **Make a place.** Open Roblox Studio, choose **Baseplate**. Insert a **Part** (Home › Part)
   and make it big and upright like a wall (Scale tool, or Properties › Size `20, 12, 1`).

3. **Put the first picture on the wall.** Open the Toolbox (View › Toolbox), choose **Decals**,
   search for something easy to recognize (for example `red apple`), and drag one onto the Part.
   Click the decal in the Explorer (Part › Decal). In Properties, **Texture** reads like
   `rbxassetid://1234567890`. Write down the number: this is the **original**.

4. **Get the second picture's number.** Drag a clearly different decal (for example `blue
   circle`) onto the Part, write down its Texture number the same way (the **replacement**),
   then delete that second decal (select it in the Explorer, press Delete). Only the first
   picture is left on the wall.

5. **Publish and close Studio.** File › **Publish to Roblox**, give it any name, keep the
   defaults, and publish. Close Studio. Don't play the place in the Player yet, so the Player
   has never seen the first picture.

6. **Add the replacement in Verdra.** In Verdra, open **Replacements** and click **Add
   replacement**. Put the original number in **Original asset ID** and the replacement number in
   the field under **Replace with** (Asset ID is already chosen), then press **Save**. The row
   appears in the table.

7. **Apply.** Make sure Roblox isn't open, then click **Apply now** at the top. You should see:
   "Applied 1 replacement. They'll appear next time Roblox starts." If routing was off, Verdra
   starts it now (the status pill at the top turns to Routing).

8. **Join the place in the Roblox Player, through Verdra.** In your web browser, open
   <https://create.roblox.com/dashboard/creations>, click your new place, then **View on
   Roblox** (or the three dots › Copy URL, and open it), and press the green **Play** button.
   Because Verdra opens games started from the Roblox website, the Player starts through Verdra; Verdra's Activity
   shows "Another launch of Verdra brought this window to the front."

9. **Look at the wall.** You should see the **second** picture. Write down which one you see.
   - Optional check that it switches back: close the Roblox Player, then in Verdra untick the
     profile **My replacements**, click **Apply now**, and join again from the browser as in
     step 8. Write down which picture you see this time. (Roblox may keep pictures it already downloaded,
     so the first picture coming back late or not at all is useful information, not a fail.)

10. **Send the results.** Quit Verdra (tray icon › Quit Verdra), then send me:
    - the file `%LOCALAPPDATA%\Verdra\Logs\verdra.log` (paste that path into File Explorer's
      address bar);
    - which picture you saw in step 9, and in the optional check if you did it (first or
      second);
    - any Roblox error text, exactly as shown.

## What Apply now changes on your PC

Nothing in Roblox's own folders. In this version, Apply now:

1. makes the proxy use your current replacements (in memory; your profile files were already
   saved when you pressed Save);
2. if routing is off, starts it, which is the same routing as in Stage 2: Verdra's certificate
   block in the Roblox **Player**'s `ssl\cacert.pem`, and the Roblox link handler, each written
   to the list of system changes first and removed by Reset everything;
3. if Roblox is running, asks first, then closes only the Roblox that Verdra started and starts
   it again through Verdra.

It does **not** delete or change `rbx-storage.db`, `rbx-storage.db-shm`, `rbx-storage.db-wal`,
the `rbx-storage` folder, `LocalStorage`, `logs`, `GlobalBasicSettings_13.xml`, `frm.cfg`,
`Downloads`, or anything of Roblox Studio. Clearing Roblox's cache waits until we know exactly
which files are cache (moved to M2); until then Apply now says so instead of deleting anything.
An automated test checks this on every change: it puts those exact names in a test Roblox
folder, runs Apply now's steps, and fails if a single byte or date changes or if a new system
change is recorded.

## What the log contains

The log has times, what Verdra did, the Roblox hosts it saw, and, while replacements are on, the
address of each picture request (`POST assetdelivery.roblox.com /v1/assets/batch`) with a line
like `Asset batch: 1 of 12 items replaced`. Login tokens and signed links are always removed.

- Your **Windows user name** may appear inside folder paths. That's fine to send me; it's never
  committed to the repository.
- Your **Roblox user ID and Roblox user name** shouldn't appear: Verdra reads only the picture
  requests, doesn't read who you are, and doesn't write the Roblox link from your browser to the
  log. I can't check that on your machine before you send it; if you do see either, it's still
  fine to send me, and I'll fix the log so it never happens again.

## Undoing everything

Untick the profile and click **Apply now** to stop the swap. Settings › System changes ›
**Reset everything** removes everything Verdra changed on your PC, as in Stage 2. Delete the
place in Studio or on create.roblox.com if you like; it costs nothing to keep.
