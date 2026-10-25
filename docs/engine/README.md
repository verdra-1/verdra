# The engine: option A

How Verdra gets replacements into the game now that decryption no longer works. Everything here
is transcribed from [decision record 0028](../decisions/0028-m2-after-roblox-drops-decrypted-connections.md),
its approval [0030](../decisions/0030-option-a-approved-and-resumed.md) and
[0029](../decisions/0029-terms-of-service-question-decided.md). Those records hold the evidence,
and they win where this page differs.

## What option A is

Verdra writes the replacement into the store the Roblox Player reads before it downloads, with
no TLS at all. The store is `rbx-storage.db` and the `rbx-storage` folder in `%LOCALAPPDATA%\Roblox`.

- **Builds on:** Verdra already moves that store aside, recorded in the ledger and undone by
  Reset everything (S-24).
- **Gains:** no decryption means no certificate in Roblox's files, so the kind of check that
  stopped decryption can't break it.

## Why it was chosen

Up to 15 October 2026 Verdra replaced pictures and meshes by decrypting two of Roblox's servers,
assetdelivery.roblox.com and fts.rbxcdn.com. From 21 October every decrypted connection completed
its TLS handshake and was then closed by the Player before any request. The runs point to a check
made after the handshake. Pinning fits best, but it is an inference, not proven: the client's
code isn't read (clean room), and nothing in the logs names the check.

0028 weighed four options:

- **D.** Pass assetdelivery through and decrypt only the picture server. Rejected by test: fts
  drops Verdra's connections the same way.
- **B.** Satisfy the check. Rejected by test: the full chain is refused too, and public Certificate
  Transparency timestamps can't be obtained by a private authority.
- **C.** Change the Roblox client so it doesn't check. Out of bounds, and not proposed.
- **A.** Write into the saved assets: the direction.

The store-swap test of 23 October 2026 settled whether A can work. In a fresh store, two
pictures' packs were swapped with Roblox closed, and on the rejoin the wall showed the swapped
picture. The Player draws what sits under a key and doesn't re-check it on a disk read, even
across sizes and formats.

## Safety rules

From 0028's writer bullets ([writer.md](writer.md)) and 0030's conditions:

- Writes only while no Roblox Player or Studio runs.
- Backs up what it replaces, records each write in the ledger, and Reset everything restores it.
- Writes only a store format it recognizes; an unknown one stops it with a plain message.
- Reads back every write.
- Cosmetic, local to the user's own machine and files, reversible.
- Intercepts no traffic, presents no certificate, never touches authentication, payments,
  moderation, anti-cheat or any security surface, never injects into the Player or patches the
  client binary, and pirates or redistributes nothing.
- Verdra never sends a login or a cookie.

## The order of work

0028's "Not built yet" list, actionable since 0030:

1. The two tool fixes: the layout guard for `sqlite_stat1`, and the `store_swap` launch path.
2. The read-only groundwork:
   - [the key formula](key-formula.md);
   - [the on-disk format](store-format.md).
3. [The saved-asset writer](writer.md), with the S-10 / S-11 / S-24 and plan 10.x changes.
4. A real-machine test of a texture replacement, then a mesh replacement. When they pass, M2
   (0.1.0) is complete.

The user notice of 0029 (spec S-29) goes with this work.
