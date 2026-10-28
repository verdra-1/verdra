# D2: the mock-ups

The design pass runs D1 (audit of today's app) → **D2 (these mock-ups)** → D3 (build them, screen
by screen). D2 proposes how each screen should look once redesigned, in the direction decision
record [0027](../../decisions/0027-design-direction.md) settled (Herbarium for light, Night garden
for dark; the status words and the status leaf; drawn empty states; specimen cards and hairlines).

Nothing here is built into the app. D3 builds each screen after you approve these.

## What's here

- `screens/*.html` — one mock-up per screen, plus `base.css`, the shared shell and components.
  They carry **no colour literals**: every colour, type size, space and radius is a CSS custom
  property the renderer injects from `src/verdra/assets/brand/tokens.json` (the real Part-B
  tokens), so the mock-ups always match the token system.
- `render.mjs` — renders every screen with Playwright, in **both themes** at **100 % and 200 %**
  text scale, into `renders/`. Run `node docs/design/d2/render.mjs` (or pass a name, e.g.
  `… render.mjs 05-activity`).
- `renders/*.png` — the committed renders (`<screen>-<theme>-<scale>.png`), the default 1200×760
  window. Law 1 (nothing cut off) is meant to hold at 200 % here too.

The grounds and every colour come straight from the current tokens. 0027's warm-paper Herbarium
ground (`#F3EFE6`) and the deeper Night-garden ground are a **proposed token change for D3**, not
yet in `tokens.json`; the mock-ups use today's `bg`/`surface` so they stay honest to Part B.

## The ten screens

1. **Window frame / sidebar** — native title bar tinted to the ground (no frameless window), the
   220px botanical sidebar with the active screen marked, the profile as a card (D1 #17), the
   header carrying the status leaf and its word.
2. **Replacements** — before→after specimen rows, drop-anywhere, the row action "Delete" apart
   from the "Remove" kind (D1 #22), the toolbar grouped into labelled sections (D1 #16). The
   before/after thumbnails are **placeholders**: Verdra has no rendered preview of an asset yet,
   so a row shows an empty frame rather than imply a preview it can't draw. Real previews are
   Editor 2.0 Part B; nothing here means they already exist.
3. **Status / popover** — the five leaves (Working · Waiting for the game · Needs you · Stopped ·
   Off), each its own shape so it reads in grayscale; the word always beside the leaf; a change
   shows only after 5 seconds, every change logged (0027 §3–5).
4. **Dialogs** — one layout for every dialog: title, risk badge, two sentences, optional checkbox,
   two buttons that name the action; nothing clips at 200 % (D1 blocker 1).
5. **Activity** — a timeline grouped by session, a segmented filter, and a detail pane that shows
   the selected entry in full (D1 Major 8, law 2).
6. **First start** — calm and truthful: what Verdra does and does not do, no version promised.
7. **Library** — a drawn "coming later" empty state (M-SOON-01), not a disabled button (D1 #23).
8. **Settings** — standard switches, not the leaf glyph (D1 #21); "Reset to defaults" a quiet
   button (D1 #19); no "Check for updates" (Part E, honest interface).
9. **About / licences** — the lockup without the node dot (0027 §8), a readable NOTICE pane, and
   un-squeezed buttons including an enabled "Third-party notices" (Part E).
10. **Tray / notifications** — the tray leaf (never animated, tooltip is the state word), the tray
    menu, and one Windows notification for good news.

## Next

This is a **hard stop**: D3 waits on your approval of these mock-ups. Tell me what to change, or
approve, and D3 builds them screen by screen (each adding its screen to the gallery's strict law-1
set and folding in the accessibility gate).
