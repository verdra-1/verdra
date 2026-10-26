# 0027. Design direction: Herbarium and Night garden, status words, the leaf as status light, design laws

- **Status:** Accepted (owner, 19 October 2026; plan 16.2 "Design decisions complete")
- **Date:** 2026-10-19
- **Plan sections:** 4 (brand), 6 (interface), 7.1 (header and status), 12.5 (accessibility),
  16.2; the owner's design rule of 16 October 2026

## Context

The M2 final test (15 October 2026) asked for a design pass that "must look excellent, never
AI-made", in stages: D1 a screenshot gallery and an audit of today's app, D2 a design proposal
for the owner's review, D3 building it screen by screen. On 16 October the owner added a rule:
no text is ever cut off. On 19 October the owner and the design review settled the direction in
the Design Studio, and asked for the decisions to be recorded before D1 starts. Nothing in this
record changes the app's code yet; D3 builds it, screen by screen, after D2 is approved.

## Decision

1. **Direction.** "Herbarium" for light: a warm paper ground (#F3EFE6) with a very faint grain,
   flat sheets with hairlines, specimen-style asset cards. "Night garden" for dark: a deep
   green-black ground (#0B1411) with two very soft brand glows. The theme follows Windows by
   default; Settings can force light or dark. The two grounds become tokens in
   `src/verdra/assets/brand/tokens.json` when D3 builds them (no color literal anywhere else).
2. **Title bar.** The native Windows title bar stays, tinted to the ground color on Windows 11
   (the DWM caption and title color attributes); Windows 10 keeps the plain bar. No frameless
   window and no extra window library.
3. **Status words in the window:** Working · Waiting for the game · Needs you · Stopped · Off.
   The words Idle, Routing, Degraded and Error stay in the log only (spec S-14 keeps its states;
   the interface maps them to these words).
4. **The leaf is the status light.** The whole Verdra leaf mark takes the state's color, and
   every state also has its own shape, so it reads in grayscale and in Windows contrast themes:
   - Working: solid, success teal; it breathes slowly, inside the window only.
   - Waiting for the game: outline with the lower half filled.
   - Needs you: solid amber with a "!" badge at the bottom right.
   - Stopped: solid red with a "×" badge.
   - Off: an empty outline.

   The tray icon never animates. It comes at 16, 20 and 24 px, a light set on a light taskbar
   and a dark set on a dark taskbar, with the tooltip "Verdra – Working" (the state's word).
5. **A state change shows only after the new condition has lasted 5 seconds.** Every change is
   still logged at once.
6. **No sounds.** The replacement editor opens as a full page. Apply now stays clickable when
   nothing waits (spec S-27, unchanged).
7. **Notifications.** A problem gets one Windows notification, with its fix as the button. Good
   news ("Your picture is now in game") always shows inside Verdra; a Windows notification for
   it is offered once and is off by default. Routine events go to Activity only.
8. **Wordmark.** The node dot over the final "a" is removed everywhere: `wordmark.svg`, the
   lockups, About and the splash. The brand README's "one flourish" rule is changed to match
   (in the design system, when D3 changes the files).
9. **Feel to aim for:** calm and trustworthy, precise and fast, native to Windows. Not media-rich.
10. **Approved extras and ideas**, each to become a spec later, not now: the first-graft
    moment, the living status leaf, a before/after slider, drop anywhere, specimen labels,
    drawn empty states, a Ctrl+K palette, a session summary, copy with a tick, path chips, the
    evening ground, a credits wall; a transparency checkerboard, Undo instead of a confirmation
    for reversible actions, one-button "Check what's wrong", per-game profiles, a keyboard-only
    first start, the status in the window title, a "what changed" note after a Roblox update, a
    7-day "seen" sparkline, a priority rank between profiles, screenshot mode, a color-blind
    preview, a profile accent color, paste anything, quiet hours, locale-aware times and
    decimals.
11. **Per-game profiles** identify the game only by the place ID in the join link Verdra
    already handles. The owner's idea: after a profile change restarts Roblox, Verdra rejoins
    the same game by itself, with a Settings switch to turn that off. Before any spec, two
    questions are investigated and reported, with no code: whether Roblox's documented
    `roblox://placeId=<id>` link (marked deprecated by Roblox) launches and joins on Windows
    without Verdra touching cookies, logins or auth tickets; and whether, for a game started
    from inside the Roblox app (no join link reaches Verdra), the Player's own local log files
    under `%LOCALAPPDATA%\Roblox\logs` reliably hold the place ID. Account data and network
    traffic are never read for this, and no log line with the owner's name or IDs is
    committed.
12. **The design laws** in [docs/design/laws.md](../design/laws.md) bind every screen, from D1's
    audit on. Law 1 (nothing is cut off) gets a CI check in D1, which may start as "report only"
    if today's interface fails it.

## Consequences

- D1 (one pull request) adds the screenshot gallery, the audit `docs/design/d1-audit.md` and the
  law 1 check; it redesigns nothing.
- D2's mock-ups come from the owner and the design review; D3 builds them screen by screen, each
  with before and after screenshots, and changes the tokens, the brand files (decision 8) and the
  status rendering (decisions 3 to 5) then, not before.
- Spec S-14 keeps its four states and their triggers; a later spec change maps them to the five
  status words (Working, Waiting for the game, Needs you, Stopped, Off) and adds the 5-second
  rule. Until then the window keeps today's words.
- The extras in decision 10 add no work until each has its own spec.
- The law 1 check (decision 12) starts report-only because today's app fails it (D1 left ~334
  findings). A.7 makes it strict per screen: `tools/gallery.py --strict` (the CI gate) fails only
  on a law 1 finding in a screen listed in `gallery.CLEAN_SCREENS`, which is empty until a
  redesign lands. Each D3 pull request adds its screen's scene name(s) to that set, so from then
  on CI holds that screen to law 1 while the un-redesigned screens stay report-only.
