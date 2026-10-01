# S-01 App shell

**Status:** Agreed
**Milestone:** M0
**Risk badge:** none
**Plan sections:** 4.5, 5.4, 5.6, 6, 7.1, 7.7 to 7.10, 8.4, 12.5

## Purpose

One window, tray and set of dialogs that every feature plugs into.

## Behaviour

### Start and single instance

- Verdra runs as a single instance per user. A second launch hands its arguments to the running
  instance over a local socket (name from `soil/terrain`), which brings its window to the front;
  a `roblox-player:` link among those arguments is passed on to the running instance. The second
  process then exits.
- Startup follows plan 8.4: arguments, single-instance check, settings, logging, Qt application,
  fonts, theme, splash, services, main window. Each step logs a timestamp; the window is visible
  within 1.5 s on a mid-range machine.
- Command-line flags: `--minimised` (start in the tray), `--reset-everything [--quiet]` (runs
  Reset everything and exits; it does nothing until S-16 exists, and says so), and an optional
  `roblox-player:` link.

### Splash

- 480 × 300, centred, frameless, `bg` background, symbol 96 px tall, wordmark with a 32 px cap
  height below it, the version in `caption` at the bottom.
- The leaves grow from the node outward (plan 4.5): each leaf scales from 0 to 1 around
  (32, 55.5), the left leaf first and the right leaf 80 ms later, over 560 ms each with the
  `bloom` easing; then the node pulses once (1 → 1.15 → 1 over 240 ms); then the wordmark fades
  in over 240 ms.
- The splash closes when the main window is ready, but stays at least 900 ms.
- With reduced motion, the lockup fades in over 150 ms and nothing scales.

### Main window

- Minimum 1000 × 640, default 1200 × 760. Size, position, sidebar state, splitter positions and
  the last screen are remembered per screen setup in `state.json` (not in settings).
- **Sidebar** (220 px, collapsible to 64 px icons-only with a chevron at the bottom): the Verdra
  mark at the top; main screens Replacements, Library, Tweaks, Accounts, and Traffic (only while
  Advanced mode is on); footer entries Activity, Settings, About.
- **Header** (56 px): screen title (`title-l`); status pill (Idle, Routing, Degraded, Error; a
  click opens a popover with the reason and at most one fix button); the active profile selector;
  the primary button "Apply now".
- **Content**: padding 24 px. Screens that aren't built yet show their empty state from the
  message catalogue, or a short placeholder naming the milestone that brings them.
- Until routing exists (M1) the status pill shows Idle with M-STATUS-03. Until replacements exist
  (M2) "Apply now" is disabled with a tooltip saying why, and the profile selector is empty and
  disabled with a tooltip saying why.

### Keyboard

Ctrl/Cmd+1 to 5 switch screens (Traffic only in Advanced mode); Ctrl/Cmd+F focuses the current
screen's search; Ctrl/Cmd+N adds a replacement; Ctrl/Cmd+Z and Shift+Ctrl/Cmd+Z undo and redo;
Ctrl/Cmd+Enter runs Apply now; Ctrl/Cmd+, opens Settings; Esc closes drawers and dialogs. A
shortcut whose feature isn't built yet does nothing. A help overlay lists the shortcuts.

### Toasts

Bottom right, 16 px from the edges, at most 3 stacked (the oldest leaves first), auto-dismiss
after 6 s unless the toast holds an action or reports an error. A toast states what happened and
offers at most one action. Every toast is also written to Activity (S-03).

### Theme

- Settings › Appearance › Theme: Match system (default), Light, Dark. With Match system, the theme
  follows the OS colour scheme and switches live when it changes; no restart in any case.
- `canopy/crown/theme.py` turns `tokens.json` into a QPalette (roles as plan 5.6) and one
  stylesheet generated from a template with `{token}` placeholders. Base style is Fusion.
- Text size (90, 100, 115, 130 %) scales every type style; fonts are registered at startup and
  sized in pixels.
- Density: Comfortable (default) or Compact. Compact uses the `row-height-compact` token and
  reduces panel padding from `space-4` to `space-3`.
- Reduce motion: Auto (follows the OS where Qt can read it), On, Off. When on, every movement
  becomes a fade of up to 150 ms.

### Tray

- Tray icon (menu-bar icon on macOS) in the variant for the current routing status (plan 4.6).
- Menu (plan 7.10): "Open Verdra"; a status line that isn't clickable; "Apply now"; "Pause
  routing" / "Resume routing"; "Reset everything…"; separator; "Quit Verdra". Items whose feature
  isn't built yet are disabled.
- Left-click opens the window on Windows and Linux; on macOS the menu-bar icon opens the menu.

### Closing and quitting

- Closing the window hides it to the tray when "Keep running in the tray when the window closes"
  (`general.close_to_tray`, default on) is on; M-SHELL-01 is shown once, the first time. When the
  setting is off, closing the window quits.
- Quit follows plan 8.4: stop accepting work, cancel jobs (S-04), flush logs and settings, exit.

### Dialogs, onboarding, About

- The shared dialogs from plan 7.8 (risk warning, explanation, destructive confirmation) exist as
  reusable widgets; buttons repeat the dialog's verb, and Cancel is the default in risk warnings.
- First run (plan 7.9) shows onboarding while `general.onboarding_done` is false: Welcome, How it
  works, Routing (the choice is saved to `routing.mode` and `routing.handle_roblox_links`; no
  system change is made until S-12 exists), Start. Settings › General › "Run setup again" shows
  it again.
- About dialog: symbol and wordmark, version and short Git commit, the NOTICE text with a
  clickable link, the credit line (M-ABOUT-01), the not-affiliated line (M-ABOUT-02), and buttons
  "Licence", "Third-party notices", "Privacy" that open the texts.

## Rules

1. All colours come from tokens; the stylesheet template contains no colour literals.
2. All user-facing text is translatable (`self.tr()` / `QCoreApplication.translate()`), follows
   plan 4.3, and is in the message catalogue (`assets/i18n/verdra_en.ts`).
3. Every interactive element has an accessible name; icon-only buttons also have a tooltip.
4. Every focusable control shows the 2 px `focus-ring` outline with a 2 px offset.
5. Disabled controls carry a tooltip saying why they're disabled (plan 5.4).
6. The UI thread never blocks longer than 50 ms; long work goes to S-04.
7. One primary button per view.
8. `canopy` never touches the network, the disk or the OS itself; it asks `trunk`.

## Messages

- M-SHELL-01 "Verdra is still running in the tray. Quit it from the tray menu." (Toast, once.)
- M-SHELL-02 (new) "Quit Verdra while Roblox is running? Your replacements stop the next time
  Roblox starts." Buttons "Quit", "Cancel". (Used once S-12 can tell that Roblox is running.)
- M-STATUS-03 (new) "Idle. Routing is off." Button "Start routing" (disabled until S-11).
- M-PLAT-01 (new) "<Feature> isn't available on <system>: <reason>."
- M-ONB-01 (new) "Welcome to Verdra!" / "Change how your game looks, only on your screen."
  Button "Get started".
- M-ONB-02 (new) "Everything stays on this computer." / "Other players see the game as usual." /
  "Every change can be undone."
- M-ONB-03 (new) "How should Roblox reach Verdra?" with "Per app (recommended)" or "Hosts file
  (needs administrator rights)", the list of system changes, and "Allow and continue".
- M-ONB-04 (new) "You're set." Buttons "Import replacement profiles…", "Browse presets", "Launch
  Roblox through Verdra", "Finish".
- M-EMPTY-01 (new), M-EMPTY-02 (new): the Replacements and Library empty states.
- M-RISK-01 (new), M-RISK-02 (new): risk-warning controls and badge labels.
- M-ABOUT-01, M-ABOUT-02: the credit and not-affiliated lines.

## Acceptance tests

1. A second launch focuses the first instance and exits within 1 s.
2. The theme switches without a restart when the OS colour scheme changes (Match system), and when
   the Theme setting changes.
3. Every control is reachable by Tab in a logical order (a UI test walks the focus chain of each
   screen).
4. The splash shows for at least 900 ms and closes when the main window is ready.
5. Ctrl/Cmd+1 to 4 switch screens; Ctrl/Cmd+5 switches to Traffic only in Advanced mode.
6. With reduced motion on, the splash and toasts use fades only (no scale or position animation).
7. A second launch with a `roblox-player:` link delivers the link to the first instance unchanged.
8. Closing the window with "Keep running in the tray" on hides it and shows M-SHELL-01 the first
   time only; with it off, closing quits.
9. Every interactive widget in the main window, tray menu, About and onboarding has an accessible
   name, and every icon-only button has a tooltip.
10. The palette roles match the tokens per plan 5.6 in both themes, and the generated stylesheet
    contains no colour value that isn't a token.
11. Toasts stack at most 3, auto-dismiss after 6 s unless they hold an action or an error, and are
    written to Activity.
12. Window size, position, sidebar state and last screen are restored on the next start.
13. Onboarding shows on first run, saves the routing choice, sets `general.onboarding_done`, and
    shows again after "Run setup again".
14. The tray icon, its menu and left-click behaviour work on Windows, macOS and Linux (manual).
15. The window is visible within 1.5 s of launch on a mid-range machine (manual, from the startup
    timestamps in the log).

## Lives in

`canopy/crown/*`, `canopy/leaves/*`, `canopy/screens/*` (placeholders), `trunk/sapwood/*`.

## Refinements from the plan

- **Ctrl/Cmd+5** maps to Traffic, which only exists in Advanced mode, so test 5 says so.
- **Density row heights**: plan 6.3 gives 36 px (compact 28 px); Reference R2
  (`appearance.density`) says 40 px (compact 32 px). This spec follows 6.3, which matches the
  tokens; R2 needs the matching edit.
- **Features not built yet** (routing, replacements, Reset everything) are shown disabled with a
  reason rather than hidden, so the shell's layout is final from M0.
