# 0020. A Roblox Player Verdra didn't start is shown, and closed only on the user's yes

- **Status:** Accepted
- **Date:** 2026-10-08
- **Plan sections:** 16.2; specs S-12 (rule 4), S-14 (Degraded), S-15 (rule 2), S-24 (rule 4)

## Context

Guide B on the maintainer's PC (2026-10-07) couldn't test any swap in game. A Roblox Player
started before Verdra was still running, hidden. Roblox handed the join from the browser to it,
and it never used Verdra. Verdra only wrote an Activity line ("A Roblox Player that Verdra
didn't start is running…") at each Apply now. Windows also refused to show that Player's
environment ("AccessDenied"), so the coexistence check couldn't tell whose it was. S-12 rule 4
forbade closing any Roblox Verdra didn't start, even when the user wants it closed.

## Decision

- Such a Player is shown plainly: a banner on every screen and the routing status Degraded (e),
  both with M-LAUNCH-08, until it closes. The banner has "How to close it" and "Close Roblox…".
- A launch (a join from the browser too) waits while it runs and asks: close it and continue,
  continue anyway, or cancel (M-LAUNCH-17).
- S-12 rule 4 gains one exception (the maintainer's instruction of 2026-10-08): a Player Verdra
  didn't start is closed when the user confirms M-LAUNCH-10 right before. It is never closed
  silently, and never by any other path.
- Verdra keeps a record of the Players it started (`players.json`: process ID and creation
  time), so a restarted Verdra still knows them. A Player whose environment Windows shows with
  Verdra's proxy in it joins the record. When Windows refuses ("AccessDenied"), the record
  alone decides. Verdra never tries another way into a Roblox process: only psutil's ordinary
  process listing and the environment Windows offers (S-15 rule 2, plan 3.1).
- Every launch says how it went in Activity (started with its process ID, failed with the
  reason, closed right away, or handed to the Player already running).

## Consequences

- Guide steps start with no Roblox running; when one is, Verdra now says so before the user
  joins.
- The coexistence check (S-15) is unchanged: it still goes ahead when an environment can't be
  read.
