# M2 final test: three pictures, the mesh report, the dry-run ZIP

The last real-machine test of milestone M2. Steps (e) to (f) run Verdra from source in one run;
step (g) starts the release dry-run ZIP, the exact files a user would get. Nothing is published:
the ZIP is a short-lived workflow artifact (decision record 0026).

You need the three test pictures (`verdra-test-1600x900.png`, `verdra-test-tiny-32px.png`,
`verdra-test-one-colour.png`) and the cube mesh file from the 12 October test.

**What to send, at most 5 files under 30 MB each:**

1. The clip from (e), 10 to 15 seconds.
2. The clip from (e2), 10 to 15 seconds.
3. **One ZIP** with: `verdra.log`, the `diagnostics` folder, and the screenshots from (e3), (f)
   and (g). How to make it is at the end.

Clips and screenshots: Win+Alt+R starts and stops a recording, Win+Alt+PrtScn takes a
screenshot; both land in `Videos\Captures`.

## Before you start: the checklist

1. **Detailed logging is on:** Settings › Detailed logging (it turns itself off after 24 hours).
2. **Only the rows each step needs:** in Replacements, remove every row the step doesn't list
   (select it, click **Remove** below the table), or untick profiles you don't need.
3. **"Moved…" in Activity before each join:** click **Apply now**, check that Activity shows
   "Moved Roblox's saved assets…", and only then join.
4. **Wait 10 seconds between two clicks on Apply now.** A second click sooner says "Apply now is
   still restarting Roblox. Try again in a moment."

Changing a picture: today a saved row can't be edited, so remove the old row (select, **Remove**)
and add the new one (**Add replacement**). Editing in place comes with Editor 2.0.

## (e), (e2), (e3) and (f): one source run

1. Close the Roblox Player and Roblox Studio. Quit Verdra if it runs (tray icon › Quit Verdra).
2. Open PowerShell and start Verdra with the format check for the wall picture and the mesh:

   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Documents\verdra\tools\run-latest.ps1" --format-check 15553230204,498788302
   ```

### (e) The 1600 × 900 picture, and (f) the mesh

3. In Replacements, keep exactly these two rows:
   - Original **15553230204** › **Local file** › `verdra-test-1600x900.png`. It saves without a
     message now.
   - Original **498788302** › **Local file** › the cube mesh file.
4. Click **Apply now**, check "Moved…" in Activity, and join your place.
5. **(e)** Stand far from the wall. Start a recording and walk slowly toward the wall for 10 to
   15 seconds, then stop it.
   Expected: the picture is visible from far away and close up, never black. The corner labels
   read the right way: TOP LEFT red at the top left, TOP RIGHT yellow at the top right, BOTTOM
   LEFT blue, BOTTOM RIGHT purple. Text that reads backward means the picture is mirrored. Verdra
   sends it as 1024 × 576 (16:9 like the original); the wall's shape decides how stretched it
   looks.
6. **(f)** Look at the mesh part and take a screenshot.
   Expected: the cube, drawn with the part's own texture (normal: Verdra replaces the shape only,
   which is also why the 12 October meshes looked dark and patterned).
7. Leave the game (close the Player).

### (e2) The tiny picture

8. In Replacements, remove both rows and add only: original **15553230204** › **Local file** ›
   `verdra-test-tiny-32px.png`.
9. Wait 10 seconds since the last Apply, click **Apply now**, check "Moved…", and join.
10. Start a recording close to the wall, walk slowly backward for 10 to 15 seconds, then stop it.
    Expected close up: four sharp quarters, red top left, yellow top right, blue bottom left,
    purple bottom right. Verdra sends the 32 × 32 picture as 64 × 64 (each side at least 64,
    decision record 0022). From very far away the quarters may blend into one mixed color: at that
    distance Roblox draws the smallest pack, a single 4 × 4 block that can hold only two colors.
    That is expected, not a fault. A black or missing picture is a fault.
11. Leave the game.

### (e3) The one-color picture

12. Remove the row and add only: original **15553230204** › **Local file** ›
    `verdra-test-one-colour.png`.
13. Wait 10 seconds, click **Apply now**, check "Moved…", and join.
14. Take one screenshot from close up and one from far away.
    Expected: the wall is bright magenta (pink-purple) everywhere, near and far, with no black
    or other color.
15. Leave the game and quit Verdra (tray icon › Quit Verdra). Close the PowerShell window.

## (g) The dry-run ZIP

The maintainer starts the release dry run and sends you the link to its run page. The ZIP is
kept there for 5 days.

1. Make sure Verdra from source isn't running (tray icon › Quit Verdra, PowerShell window
   closed).
2. Open the run page, sign in to GitHub if asked, and under **Artifacts** click
   **Verdra-0.0.1-windows.zip** (the version label of the code; it lands in Downloads).
3. Right-click the ZIP › **Extract All…** and keep the folder Windows suggests
   (`Downloads\Verdra-0.0.1-windows`). Don't extract it into Documents: your source folder
   `Documents\verdra` has the same name, and Windows treats `Verdra` and `verdra` as one.
4. Open that folder's **Verdra** folder and double-click **verdra.exe**. If Windows says
   "Windows protected your PC", click **More info**, then **Run anyway**.
5. Click **About** at the bottom of the sidebar, then **Third-party notices**, and take a
   screenshot of the window that opens. Close it.
6. In Replacements, keep only one row: original **15553230204** › **Local file** ›
   `verdra-test-1600x900.png`.
7. Click **Apply now**, check "Moved…", and join your place.
8. Take a screenshot of the wall. Expected: the 1600 × 900 picture.
9. Leave the game and quit Verdra (tray icon › Quit Verdra).

## Making the ZIP (file 3)

1. Make a new folder on your desktop, for example `verdra-test`.
2. Copy into it:
   - `verdra.log` from `%LOCALAPPDATA%\Verdra\Logs` (paste that path into File Explorer's
     address bar);
   - the whole `diagnostics` folder from `%LOCALAPPDATA%\Verdra`;
   - the screenshots from (e3), (f) and (g) from `Videos\Captures`.
3. Right-click the folder › **Send to** › **Compressed (zipped) folder**.

Then send that ZIP and the two clips.
