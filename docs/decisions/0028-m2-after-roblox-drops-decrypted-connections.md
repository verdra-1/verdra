# 0028. M2 after Roblox stopped asking for assets over Verdra's decrypted connections

- **Status:** Proposed. Direction A, pending the read-only investigation and the owner's explicit
  approval to write into Roblox's files; nothing that writes to Roblox is built until then.
- **Date:** 2026-10-22 (options scoped); updated 2026-10-22 with the pass-through control
- **Plan sections:** 3.1 (clean room), 10.1 to 10.3 (interception, hosts, local CA), 10.6, 14
  (M2 exit gate), 16.2 (autopilot: the owner decides direction, client changes and legal
  questions)

## Context

Up to 15 October Verdra replaced pictures and meshes by decrypting two of Roblox's servers with
a certificate from its own local authority. That authority is added to the Player's certificate
file (spec S-10). The servers are assetdelivery.roblox.com, which answers "where is asset N",
and fts.rbxcdn.com, which serves the bytes.

On 21 October, run from source on the updated Roblox, every decrypted assetdelivery connection
completed its TLS 1.3 handshake. Roblox then closed it within a millisecond, without a request
or a TLS alert. HTTP/2 and the build were ruled out (`docs/m2/exit-gate.md`).

### The pass-through control, 22 October 2026 (source, main 8012450)

The owner's three runs (logs checked; none committed):

1. **`--no-intercept assetdelivery.roblox.com`, 19:53:53 to 19:57:48:**
   - assetdelivery passed through (19:56:03.316, 19:56:04.947).
   - Verdra decrypted fts.rbxcdn.com 77 times, from 19:56:03.513 to 19:56:24.811. All 77
     completed TLS 1.3 and ended "before its first request (… a plain TCP close)", with no
     request and nothing served.
   - On fts Roblox offered ALPN `h2, http/1.1`, and Verdra chose `http/1.1`.
   - Degraded at 19:56:58.233.
   - Apply now found nothing to move this time (no "Moved…" line).
2. **`--no-intercept assetdelivery.roblox.com,fts.rbxcdn.com`, 19:58:35 to 19:59:45:**
   Verdra decrypted nothing, and logged the real servers' chains (19:58:37):
   - **assetdelivery.roblox.com:** CN=roblox.com, issued by Sectigo Public Server Authentication
     CA OV R36, RSA 2048, 2026-10-12 to 2027-04-28, 3 signed certificate timestamps, then two CA
     certificates.
   - **fts.rbxcdn.com:** CN=\*.rbxcdn.com, issued by Amazon RSA 2048 M01, RSA 2048, 2026-09-09
     to 2027-03-25, 3 timestamps, then two CA certificates.
   - Roblox joined at 19:59:08. It needed one connection to fts (19:59:15.287) and two to
     assetdelivery, instead of dozens of retries.
   - The run lasted 37 s in the game. The wall wasn't reported.
3. **`--send-ca`, 20:01:28 to 20:02:48:**
   - Verdra decrypted assetdelivery 30 times between 20:01:59.048 and 20:02:35, presenting
     "this certificate, then Verdra's CA".
   - All 30 ended before their first request: 29 plain TCP closes and one reset (20:02:24.242).

What the runs show:

- **The check covers both servers.** Roblox accepts Verdra's certificate during the handshake
  (it is trusted through the Player's certificate file), then drops the connection on both
  servers.
- **It isn't about the chain.** Sending Verdra's CA along changes nothing.
- **The real certificates** come from public authorities and carry Certificate Transparency
  timestamps. Verdra's (ECDSA, from its own authority) has none.
- **Pinning fits best:** of the key, or of an issuing authority, possibly with a timestamp
  requirement. Both points are inferences: the client's code isn't read (clean room), and
  nothing in the logs names the check.
- **One alternative isn't excluded for fts alone:** Roblox offered HTTP/2 first there and got
  HTTP/1.1. assetdelivery offered only HTTP/1.1 and fails the same way, so one cause explains
  both.

## Options

**D. Pass assetdelivery through and decrypt only the picture server. Rejected by test.**
Run 1: fts.rbxcdn.com drops Verdra's connections exactly like assetdelivery.

**B. Satisfy the check. Rejected.** Run 3: the full chain is refused too. The real certificates
carry timestamps from public Certificate Transparency logs, which a private local authority
can't obtain, and a pinned key can't be matched without Roblox's own key.

**C. Change the Roblox client so it doesn't check.** Unchanged: modifying the Player's code or
its behavior while it runs is out of bounds for autopilot. It touches Roblox's security surface,
and it raises questions of law and of Roblox's terms that only the owner can weigh. Not
proposed.

**A. Put the replacement into Roblox's saved assets: the direction.** Verdra would write the
replacement into the store the Player reads before it downloads (`rbx-storage.db` and the
`rbx-storage` folder in `%LOCALAPPDATA%\Roblox`), with no TLS at all.

- **Builds on:** Verdra already moves that store aside, recorded in the ledger and undone by
  Reset everything (S-24).
- **Gains:** no decryption means no certificate in Roblox's files, so this kind of check can't
  break it.
- **Needs, in order:**
  1. The read-only investigation below.
  2. The owner's explicit approval to write into Roblox's files.
  3. The plan and spec changes below.

### A, step 1: the read-only investigation (now)

`tools/inspect_store.py` reads a **copy** the owner makes after one plain join. It refuses
Roblox's own folder and opens the database from a private temporary copy, so not even the copy
changes. It reports structure only (guide `docs/guides/m2-store-inspection.md`):

- tables, schema, row counts and the shapes of values;
- where asset 15553230204 appears;
- the folder's layout, name shapes, sizes and formats by first bytes;
- whether file names are hashes of their own bytes (MD5, SHA-1, SHA-256), and which columns
  name the files.

It answers three questions:

1. **Format:** what Verdra would have to write. On 11 October the CDN sent pictures as KTX2 with
   zstd (decision record 0022), and Verdra already writes that format.
2. **Key derivation:** how the Player finds a saved asset. Either a table links asset IDs to
   files, and Verdra can find the original after Roblox has saved it once, with no network
   request. Or files are found only by a content hash that Roblox's batch answer gives. Then
   Verdra must learn that hash first: after a join (the store holds it), or by a request of its
   own to Roblox's public asset-delivery API.
   - Whether that API answers without a login isn't known. Verdra never sends a login or cookie
     (plan 16.2), so if it needs one, this path is closed.
3. **Content addressing:** whether a file's name is a hash of its bytes. If it is, Roblox
   *could* check what it reads. Only the test below shows whether it does. Over the network it
   did not on 11 October (Verdra's own bytes, served under Roblox's content address, were
   drawn), but reading from disk is a different code path.

### A, step 2: the verification test (designed, not run; needs the owner's approval)

The question that decides A: does the Player check what it reads from its store against the
key? The test uses only Roblox's own bytes:

1. Apply now moves the real store aside, into Verdra's backup, as today.
2. Join 1, with nothing decrypted: the Player builds a fresh store holding pictures X (the
   wall, 15553230204) and Y (a second picture in the same place).
3. With Player and Studio closed, a source-only diagnostic swaps the stored bytes of X and Y in
   that fresh store. That store is disposable, and Reset everything still restores the real one.
4. Join 2, with nothing decrypted:
   - **The wall shows Y:** the Player doesn't check, and A works.
   - **The wall shows X and the log shows a new download from fts:** it checks, and A is
     blocked.

This writes into Roblox's folder (only the disposable store), so it waits for the owner's yes.

## Proposed plan and spec changes if A is approved (drafts, not applied)

- **Plan 10.1 to 10.3, specs S-10 and S-11:**
  - Replacements stop depending on decryption.
  - The local authority and the Player's certificate file are left alone unless a diagnostic
    needs them, so fewer changes to the user's system.
  - S-11's proxy stays for the diagnostics and for features that only read.
- **New spec "saved-asset writer" (S-24's sibling):**
  - It writes only while no Player or Studio runs, as the move does today.
  - Before each write, the bytes it replaces go into Verdra's backup, and the write is in the
    ledger. Reset everything restores them.
  - It writes only a store format it recognizes (a schema check). An unknown format stops it
    with a plain message, never a guess.
  - It checks each write by reading it back.
  - Roblox may later replace or drop an entry. Verdra then writes it again at the next Apply
    now, and says so.
- **S-24 (Apply now):** the flow may need two steps: join once so Roblox saves the original,
  then Apply now writes the replacement. Whether that is needed depends on step 1's answer to
  key derivation. The interface text for it needs new message IDs.
- **Plan 16.2 / legal:** writing into Roblox's cache files is a change to the user's local files,
  not to the client's code. Whether Roblox's terms allow it is a question for the owner and the
  M8 legal review.

## Decision

Open. Recommended:

- Approve A's read-only investigation now (no approval needed: nothing is written).
- After the report, decide on the verification test, which writes only into a disposable store.
- Then decide on building A.

D and B are rejected by test. C stays the owner's call, with its own record if ever wanted.
Until A is approved and built, the M2 exit gate stays open, Phase A stays frozen, and nothing is
released (decision record 0026).

## Consequences

- M2's exit gate ("a texture swap and a mesh swap are visible in game") isn't met on today's
  Roblox, though it was on 11 and 12 October.
- What M2 already built carries over to A: the encoders, the formats, the profiles and the
  editor. The interception path becomes diagnostics.
- A depends on an undocumented store that any Roblox update can change. The schema check and a
  plain message keep that from failing silently.
- The per-connection TLS lines (S-11) and the pass-through control stay: they are how the next
  change of this kind will be seen.
