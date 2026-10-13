# Replacing pictures and meshes

Verdra changes how a Roblox game looks on your own computer only. Other players see the game as
usual. This page covers what works today (milestone M2).

## Make a replacement

1. Open **Replacements** and click **Add replacement**.
2. **Original asset ID:** the number of the picture or mesh you want to change. Verdra checks
   with Roblox what kind of asset it is.
3. **Replace with**, one of:
   - **Asset ID:** another Roblox asset of the same kind.
   - **Local file:** a picture (PNG, JPEG, KTX2 or DDS) or a mesh (Roblox mesh file or OBJ) from
     your computer. Drop it on the editor or choose it.
   - **URL:** an HTTPS link to a picture or mesh. Verdra downloads it once, the first time you
     click Apply now.
   - **Remove:** a picture becomes invisible and a mesh disappears.
4. Click **Save**.

## Apply it

1. Close the Roblox Player and Roblox Studio.
2. Click **Apply now**. Verdra moves the assets Roblox already saved aside (only moves, never
   deletes; Reset everything puts them back), so Roblox has to download them again and gets your
   replacement.
3. Start the game through Verdra.

## What to expect

- **A replaced mesh keeps the part's own texture.** Verdra replaces the shape only. The part's
  texture is a separate asset, drawn on the new shape through its texture coordinates, so it can
  look stretched or patterned. To change it too, replace the texture as well.
- **Large pictures are made smaller.** Pictures up to 16,384 pixels a side (and 64 megapixels)
  are accepted; Verdra scales them down to the size Roblox uses. Each side becomes a multiple of
  64 pixels, at least 64.
- **A mesh is sent with one level of detail**, so it looks the same near and far.
- **Some requests can't be replaced yet.** If Roblox asks for an asset by its content hash,
  Activity says so and the status turns Degraded; the original shows.
- **Not yet:** sounds and other asset types from a file or URL, and one map of a material
  (TexturePack slots). These show "This part of Verdra isn't built yet."

## Undo

- Untick a profile or delete a replacement, then click **Apply now** again.
- **Settings › System changes › Reset everything…** removes everything Verdra changed on this
  computer and puts Roblox's saved assets back.
