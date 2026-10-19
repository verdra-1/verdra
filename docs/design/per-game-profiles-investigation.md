# Per-game profiles: the two technical checks (investigation, no code)

Decision record [0027](../decisions/0027-design-direction.md), decision 11, asks two questions
before any spec for per-game profiles and auto-rejoin. This page answers them as far as public
documentation goes (19 October 2026) and says what only a real machine can settle. Nothing here
is built, and nothing reads account data, cookies, login state, auth tickets or network traffic.

## (a) Can Verdra rejoin a game with `roblox://placeId=<id>`?

**What Roblox documents.** Roblox's creator documentation on deep links describes a
direct-to-app link, `roblox://placeId=<id>&launchData=<data>` (place ID required; optional
`userId`, `accessCode`, `linkCode`, `gameInstanceId`; launch data under 200 bytes, never
secret), next to the web form `https://www.roblox.com/games/start?placeId=<id>`. The English
page (updated July 2026) now marks the whole process **deprecated** and points creators to
share links. No removal date was found.

**What it would mean for Verdra.** Verdra would start the Roblox Player with that link as its
argument (as it does with a `roblox-player:` link today, spec S-12) and let the Player sign in
with its own saved session. Verdra would not touch a cookie, a login or an auth ticket: the
`roblox-player:` links the website makes carry a one-time ticket for that join, and Verdra must
never make or reuse one (plan 16.2, never Roblox's security endpoints). So `roblox://placeId=`
is the only rejoin path that fits the rules.

**Not known, and why it matters:**

- Whether the Windows Player (`RobloxPlayerBeta.exe`) accepts a `roblox://` link given as its
  argument and joins the place with its saved session, or only handles `roblox-player:` links.
  A community report says the newer Microsoft Store (UWP) app ignores these links. The source
  is user reports only, not Roblox.
- How long the deprecated link keeps working.

**A five-minute check on the owner's PC, later, when it's time** (no Verdra involved): with
Roblox closed, paste `roblox://placeId=<a place you own>` into the Windows Run box (Win+R). If
Roblox opens and joins that place, (a) works today on that PC. Only "joined / didn't" is
reported, never the place ID or anything from the account.

## (b) For a game started inside the Roblox app, do the Player's logs hold the place ID?

**What is public.** Roblox keeps the Player's log files in `%LOCALAPPDATA%\Roblox\logs`
(recorded on the owner's PC as W-06 in `docs/platforms/windows.md`, where Verdra never changes
them). Roblox doesn't document what the logs contain. One public write-up from 2022 shows a
Player log holding the join data of a game, including its place ID. The format of today's
lines is undocumented and can change with any Roblox update.

**What it would mean for Verdra.** Verdra would read, never write, only the newest log file,
and only the one value it needs (the place ID of the join), and keep nothing else from it.
Because the format is undocumented, the feature must:

- fail quietly, showing "game not recognized";
- never guess;
- have a test against a recorded, anonymized line.

**Not known.** Whether every join (from the home screen, from a friend, a teleport between
places of one game) writes the place ID, and how soon after the join it appears.

**A check on the owner's PC, later:** join two games from inside the Roblox app, close Roblox,
open the newest file in `%LOCALAPPDATA%\Roblox\logs` and search it for "placeid" (any case).
Report only:

- whether each join had such a line;
- the line's shape, with every number replaced by `N`.

Never send the file: it holds the account's user ID and name.

## Recommendation

Both paths are possible but rest on undocumented or deprecated behavior. Spec per-game profiles
on the join link Verdra already handles (it always carries the place ID). Add (a) and (b) only
after the two checks above, each behind its own Settings switch, off when the check fails.
