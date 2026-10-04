# Your first texture swap

A beginner's guide to seeing a Verdra replacement in a Roblox game, on Windows. It takes about
20 minutes. You need Roblox Studio (already on your PC) and the Verdra source checkout from
Stage 2.

You'll make a tiny place with one picture on a wall. Then you tell Verdra to show a different
picture instead. If the wall shows the other picture in the game, the swap works. Only your own
screen changes; the place itself stays as you published it.

## Steps

1. **Update Verdra.** In the Verdra folder from Stage 2, run:

   ```sh
   git pull
   uv sync --locked
   uv run python -m verdra
   ```

   Don't add `--diagnose-interception` this time: that mode changes nothing on purpose. In
   Settings › Advanced, turn on **Detailed logging**.

2. **Make a place with a picture.** In Roblox Studio, open a new **Baseplate**. Insert a **Part**
   and stand it up like a wall. From the Toolbox, search **Decals**, pick any picture, and drop
   it on the Part.

3. **Copy the first picture's number.** Click the decal (Explorer › Part › Decal). In
   Properties, **Texture** reads like `rbxassetid://1234567890`. Write down the number. This is
   the **original**.

4. **Copy a second picture's number.** Drop a *different* decal from the Toolbox on the Part,
   write down its Texture number the same way (the **replacement**), then delete that second
   decal so only the first one is on the wall.

5. **Publish and close Studio.** File › Publish to Roblox, give the place any name, and close
   Studio. Don't play the place yet: Roblox may save the first picture and keep showing it.

6. **Add the replacement in Verdra.** Close Roblox if it's open. On the **Replacements** screen,
   click **Add replacement**. Put the original number in **Original asset ID** and the
   replacement number in the field under **Replace with** (Asset ID is already chosen), then
   press **Save**.

7. **Apply.** Click **Apply now** at the top. You should see: "Applied 1 replacement. They'll
   appear next time Roblox starts."

8. **Play through Verdra.** In the Library, click **Launch Roblox**. Find your place under
   **Creations** on the Roblox home screen (or open its page in your browser and press Play;
   Verdra takes over that link too) and join it.

9. **Look at the wall.** You should see the **second** picture. Then, in Verdra, switch the
   profile **My replacements** off (the check box beside its name), click **Apply now**, confirm
   **Restart Roblox**, and join again: the first picture is back. If it isn't, write down what
   you saw; that tells us how Roblox keeps pictures it already downloaded.

10. **Send the results.** Quit Verdra, then send:
    - `%LOCALAPPDATA%\Verdra\Logs\verdra.log`;
    - which picture you saw in step 9, each time (first or second);
    - any Roblox error text.

## What the log should show

After step 8, Activity (and the log) has a line like this for each batch that asked for the
picture:

```text
Asset batch: 1 of 12 items replaced
```

If the second picture shows but that line never appears, or the first picture shows, the log
tells us which part of the swap to look at.

## Undoing everything

Switching the profile off and clicking **Apply now** stops the swap. Settings › System changes ›
**Reset everything** removes everything Verdra changed on your PC, as in Stage 2.
