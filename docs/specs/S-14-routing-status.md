# S-14 Routing status

**Status:** Built
**Milestone:** M1
**Risk badge:** none
**Plan sections:** 4.6 (tray icons per status), 7.1 (header status pill and popover), 7.10 (tray
status line), 10.4 (verification failure turns Degraded), 15 (R-01), Reference R1 (`roots/gardener`,
`canopy/crown/header`, `canopy/crown/tray`, `canopy/leaves/badge`), R5 (M-STATUS-01 to M-STATUS-05)

## Purpose

Always show whether routing works, and why not.

## Behaviour

- **One status source.** `roots/gardener` owns the routing status: a state (Idle, Routing,
  Degraded, Error) plus a reason. Every change is published once (a Qt signal through trunk);
  the header pill, the popover, the tray icon and the tray status line all render that one value.
- **States and triggers** (plan S-14 table):

  | State | Entered when | Fix offered (popover) |
  |---|---|---|
  | Idle | Routing is off (never started, paused from the tray, or stopped) | "Start routing" (M-STATUS-03) |
  | Routing | Proxy listening; Roblox traffic seen in the last 2 minutes, or no Roblox running | none |
  | Degraded | (a) a Roblox client is running but no Roblox CONNECT reached Verdra within 20 s of a launch; (b) an upstream certificate failure (S-11); (c) the CA block is missing from an installed Roblox version (S-10); (d) an asset batch couldn't be read while a replacement is active (S-21, M-GRAFT-03), for two minutes after the last one; (e) a Roblox Player Verdra didn't start is running (S-12, M-LAUNCH-08) | (a) "Restart Roblox through Verdra"; (b) and (d) none, reason only; (c) "Repair certificate" (M-STATUS-04); (e) "Close Roblox…", after M-LAUNCH-10 |
  | Error | The proxy couldn't start (M-PROXY-01); another routing tool was detected (S-15, M-COEX-01); the keeper is unavailable (Hosts-file mode, M6) | One fix specific to the reason (M-STATUS-05) |

- **Priority.** If several triggers hold, Error wins over Degraded, Degraded over Routing. Within
  Degraded, the most recent reason is shown; the popover lists the others.
- **Leaving Degraded.** (a) clears when Roblox traffic arrives; (b) clears after 2 minutes without
  another certificate failure, or when routing restarts; (c) clears when the block is repaired.
- **Notice.** When (a) happens, Library and the popover show M-STATUS-01 with "Restart Roblox
  through Verdra" (S-12 launch, after M-LAUNCH-03).
- **Tray.** The tray icon is the status variant from plan 4.6; the tray status line reads
  M-STATUS-02 in Routing, and the state word with its reason otherwise. "Pause routing" /
  "Resume routing" in the tray switch between Idle and the running states.
- **Logging.** Every state change is written to Activity at Info (Warning for Degraded, Error for
  Error) with the old state, the new state and the reason.

## Rules

1. The pill, the tray icon and the tray status line always agree: they are drawn from the same
   published value, never computed separately.
2. Each state change is logged with its reason, once per change (no repeated lines while the
   state holds).
3. Status is driven by events (proxy start and stop, connection seen, launch, certificate
   failure, folder watch); the only timers are the 20 s launch window and the 2 minute traffic
   window, in line with S-04's rule against polling loops.
4. Status colours always come with an icon and a word (plan 5); the pill never relies on colour
   alone.
5. The reason text never contains secrets; it passes through `bark/veil` like any log line.

## Messages

- M-STATUS-01 (Notice) "Roblox isn't routed through Verdra yet. Restart it from here."
- M-STATUS-02 (Tray line) "Routing · <n> replacements active"
- M-STATUS-03 (Popover, new in R5) "Idle. Routing is off." Button "Start routing".
- M-STATUS-04 (Popover, new in R5) "Degraded. <reason>." Buttons "Restart Roblox through Verdra"
  or "Repair certificate", as fits.
- M-STATUS-05 (Popover, new in R5) "Error. <reason>." One fix button specific to the reason.
- M-STATUS-06 (Activity, new) "Routing status changed from <old> to <new>." A change to Idle or
  Routing.
- M-STATUS-07 (Activity, new) "Routing status changed from <old> to <new>: <reason>" A change to
  Degraded or Error, with its reason.

## Acceptance tests

1. Each trigger in the table, produced with `tools/fake_roblox.py` and a fake client process,
   moves the status to its state within 2 s: start and stop routing; fake client launched with
   and without the proxy variables (Degraded (a) after 20 s, cleared by its first CONNECT);
   upstream self-signed certificate (Degraded (b)); a fixture Roblox version folder without the
   block (Degraded (c), cleared by "Repair certificate"); port and every-port-taken (Error);
   a fake Roblox client with a foreign proxy (Error, M-COEX-01, S-15).
2. In every state, the pill text and icon, the tray icon variant and the tray status line match
   (UI test over all four states and every reason).
3. Priority: with an Error and a Degraded trigger active together, the status is Error; when the
   Error clears, it falls back to Degraded with that reason.
4. Each state change produces exactly one Activity record naming the reason; holding a state for
   5 minutes adds none (fake clock).
5. Each popover fix button runs its action (fake services) and is reachable by keyboard, with an
   accessible name.
6. With routing on and nothing happening, no timer fires more often than once per second (S-04
   idle rule).

## Lives in

`roots/gardener.py` (state and triggers), `canopy/crown/header.py` (pill and popover),
`canopy/crown/tray.py` (icon and status line), `canopy/leaves/badge.py` (pill drawing).

## Refinements from the plan

- The plan's table names triggers without saying how they clear or which wins; the priority and
  clearing rules above are added so test 1 has a definite expected state. Degraded (b) clearing
  after 2 minutes matches the 2 minute traffic window the plan already uses for Routing.
- Tests 3 to 6 are added for rules the plan states (logging, keyboard reach, no polling) but
  S-14 doesn't test.
- M-STATUS-03 to 05 are taken from R5 ("new" entries).
- **Dependency, not a change:** "keeper unavailable" only exists with Hosts-file routing (S-13,
  M6). At M1 that trigger is defined but can't occur; its test is added at M6.

## Refinements from the plan

- The one fix for every Error reason is "Try again" (S-15 names it for M-COEX-01; a proxy that
  couldn't start and an unavailable keeper are retried the same way). Degraded (b) and (d) have
  no fix.
- **Degraded (d), after the second swap test (2026-10-07).** An asset batch the grafter couldn't
  read while a replacement is active (S-21 rule 4) shows M-GRAFT-03. Like (b), it clears two
  minutes after the last such batch, and when routing stops.
- The tray status line reads "<state>: <reason>" when the status has a reason, and the state word
  alone otherwise; in Routing it reads M-STATUS-02.
- The popover lists the other active reasons under the shown one, most recent first.
- Until the action behind a fix exists (starting routing, launching Roblox, repairing the
  certificate), its button is shown disabled with M-SOON-01; the interface enables a fix only
  when a service handles it.
- **Degraded (e), 2026-10-08.** A Roblox Player Verdra didn't start keeps the game away from
  Verdra (S-12's refinement of that day); the status says so until that Player closes, and its fix
  asks before closing it.

