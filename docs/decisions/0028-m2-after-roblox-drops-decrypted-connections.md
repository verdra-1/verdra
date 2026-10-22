# 0028. M2 after Roblox stopped asking for assets over Verdra's decrypted connections

- **Status:** Proposed (for the owner's decision; nothing is built until it is accepted)
- **Date:** 2026-10-22
- **Plan sections:** 3.1 (clean room), 10.1 to 10.3 (interception, hosts, local CA), 10.6, 14
  (M2 exit gate), 16.2 (autopilot: the owner decides direction, client changes and legal
  questions)

## Context

Up to 15 October Verdra replaced pictures and meshes by decrypting two of Roblox's servers with
a certificate from its own local authority. That authority is added to the Player's certificate
file (spec S-10). The servers are assetdelivery.roblox.com, which answers "where is asset N",
and fts.rbxcdn.com, which serves the bytes. On 21 October, run from source on the updated
Roblox, every decrypted assetdelivery connection completed its TLS 1.3 handshake. Roblox then
closed it within a millisecond, without a request or a TLS alert. Roblox offered only
HTTP/1.1 and Verdra chose it, so this isn't a protocol mismatch, and the built app fails the same
way. The likely cause is a check Roblox makes after the handshake that a certificate from
Verdra's authority can't pass, such as pinning the server's key. That isn't proven yet: the
pass-through control (guide `docs/guides/m2-pass-through-control.md`) tests it, and logs the
real server's certificate for comparison.

Facts that bear on the options:

- On 11 October the client drew Verdra's own bytes served under Roblox's content address. It
  did not check the content hash (docs/platforms/windows.md).
- Verdra already moves Roblox's saved assets (rbx-storage) aside, by move, recorded in the
  ledger and undone by Reset everything (spec S-24).
- Clean room (plan 3.1): everything here comes from the plan, public documentation and general
  knowledge of TLS and HTTP, not from any other tool.

## Options

**D. Pass assetdelivery through and decrypt only the picture server.** Roblox asks
assetdelivery, untouched, where the asset is. Verdra serves the replacement when Roblox
downloads that address from fts.rbxcdn.com. Verdra can no longer read that answer, so it learns
the address of each replaced original itself, before the game asks: one request of its own to
Roblox's public asset-delivery API per replaced asset (as the editor's type check already asks
Roblox about an asset).

- **Needs:** run 1 of the pass-through control to show that Roblox still accepts Verdra on
  fts.rbxcdn.com; the address to stay the same per asset version (it is content-addressed
  today); a plan change listing that request.
- **Loses:** Asset ID swaps (they rewrite the assetdelivery request) unless done another way.
- **Risk:** if Roblox extends its check to the picture server, D stops working too.
- **Smallest change:** the encoder, the formats and the serving stay as they are.

**A. Put the replacement into Roblox's saved assets instead.** Verdra writes the replacement
bytes into the store Roblox reads before it downloads, under the key Roblox looks up, and
decrypts nothing.

- **Needs:**
  - the store's format: an SQLite database and a folder, undocumented, so a read-only
    investigation comes first;
  - the key for each asset, which likely needs the same request of its own as D;
  - knowing whether Roblox checks what it reads against the key (it didn't check downloads on
    11 October).
- **Changes:** Verdra would write into Roblox's files, not just move them. That needs a ledger
  entry and Reset everything to undo it, and a rule that Verdra never writes while Roblox runs.
- **Gains:** if it works, no TLS at all, so no future check of this kind can break it.
- **Risk:** any Roblox update can change the store's format.

**B. Satisfy the check.** If the check is Certificate Transparency, a certificate needs
timestamps from public logs. A private, local authority can't obtain them, and pinning can't be
satisfied at all without Roblox's key. **Rejected.**

**C. Change the Roblox client so it doesn't check.** Modifying the Player's code or its
behavior while it runs is out of bounds for autopilot. It touches Roblox's security surface, and
it raises questions of law and of Roblox's terms that only the owner can weigh. **Not
proposed; listed so the owner can rule it out explicitly.**

## Recommendation

Wait for the pass-through control:

- **If Roblox still accepts Verdra on fts.rbxcdn.com:** try D first. It is the smallest change
  and keeps everything M2 verified on the real machine. Start A's read-only investigation in
  parallel as the fallback.
- **If not:** A becomes the main direction, starting with the read-only investigation.
- **C** stays out unless the owner decides otherwise, with its own decision record.

## Decision

Open: the owner chooses after the pass-through control. Until then the M2 exit gate stays open,
no option is built, Phase A stays frozen, and nothing is released (decision record 0026).

## Consequences

- M2's exit gate ("a texture swap and a mesh swap are visible in game") is not met on today's
  Roblox, although it was on 11 and 12 October. The plan's M2 design (decrypting
  assetdelivery) needs amending whichever option is chosen.
- D and A each need a plan change: D for Verdra's own request; A for writing into Roblox's
  files.
- The per-connection TLS lines (S-11) stay. They are how the next change of this kind will be
  seen.
