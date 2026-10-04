# S-12 Per-app routing and launching

**Status:** Agreed
**Milestone:** M1
**Risk badge:** none
**Plan sections:** 7.9 (onboarding routing step), 7.10 (tray), 9.4, 10.1 (per-app routing), 11.1–11.3
(discovery, launching, link handling, Microsoft Store; confirm at M1), 15 (R-04, R-05),
Reference R2 (`routing.mode`, `routing.handle_roblox_links`, `routing.close_roblox_on_quit`),
R3 (URL scheme, handler identifiers), R5 (M-LAUNCH-01 to M-LAUNCH-05, M-SHELL-02)

## Purpose

Start Roblox through Verdra on every platform without administrator rights.

## Behaviour

- **Discovery.** Verdra finds the installed Roblox clients at the locations recorded in
  `docs/platforms/<os>.md` at M1 (plan 11.1 to 11.3: per-user and all-users versions on Windows,
  the Microsoft Store package, `Roblox.app` on macOS, Sober on Linux). If none is found, M-LAUNCH-01.
- **Launching.** "Launch Roblox" (Library empty state, tray, onboarding) and every in-app launch
  start the client with `HTTPS_PROXY` and `HTTP_PROXY` set to Verdra's proxy, added to a copy of
  the user's environment:
  - Windows: start the player executable directly with that environment.
  - macOS: execute the player binary inside the app bundle directly.
  - Linux: `flatpak run --env=HTTPS_PROXY=… --env=HTTP_PROXY=… org.vinegarhq.Sober <link>`.
- **Links from the browser.** If `routing.handle_roblox_links` is on, Verdra registers itself as
  the handler for `roblox-player:` links (Windows `HKCU\Software\Classes\roblox-player`, macOS
  `LSSetDefaultHandlerForURLScheme`, Linux `xdg-mime` with the handler desktop entry). A link that
  arrives (also through the single-instance channel, S-01) is passed on unchanged to the real
  client, launched as above. The previous handler is stored in a `uri_handler` ledger entry
  before the change.
- **Turning handling off** restores the previous handler exactly and marks the ledger entry
  removed.
- **Microsoft Store builds.** If the client can't receive the environment, Verdra shows
  M-LAUNCH-02 and offers Hosts-file routing (S-13, M6).
- **Cache clearing.** On request (Apply now, S-24), Verdra closes the client it launched (after
  M-LAUNCH-03) and deletes only the Roblox cache files recorded in `docs/platforms/<os>.md`.
- **Closing on quit.** If `routing.close_roblox_on_quit` is on, quitting Verdra closes the client
  Verdra launched; if off and Roblox is running, quitting asks M-SHELL-02 first.

## Rules

1. The original link is forwarded byte for byte; Verdra never changes a link's parameters except
   where S-52 (subplaces, M5) explicitly does.
2. Link-handler registration and its restore are ledger entries (`uri_handler`), written before
   the change.
3. No administrator rights are needed for anything in this spec.
4. Only processes Verdra started are ever closed by Verdra (psutil, matched by process ID), never
   other Roblox instances.
5. No path, executable name, cache file or registry location is used before it is recorded in
   `docs/platforms/<os>.md` (plan 16.4).

## Messages

- M-LAUNCH-01 (Notice) "Roblox isn't installed, or Verdra couldn't find it. Install Roblox, then
  try again."
- M-LAUNCH-02 (Notice) "This Roblox version from the Microsoft Store can't be routed per app.
  Switch to Hosts-file routing in Settings › Routing."
- M-LAUNCH-03 (Dialog) "Restart Roblox now? Unsaved progress in your game may be lost." Buttons
  "Restart Roblox", "Cancel".
- M-LAUNCH-04 (Notice, new) "Verdra can't route Sober yet: where Sober reads its certificates hasn't
  been confirmed. Nothing was changed."
- M-LAUNCH-05 (Notice, new) "Verdra can't route a Roblox installed for all users: that needs
  administrator rights, which routing per app never uses. Install Roblox for your account only,
  then try again. Nothing was changed."
- M-SHELL-02 (Dialog, new) "Quit Verdra while Roblox is running? Your replacements stop the next
  time Roblox starts." Buttons "Quit", "Cancel".

## Acceptance tests

1. (manual + log check) On each platform, "Launch Roblox" starts the client and its traffic goes
   through Verdra: Verdra's log shows the client's CONNECT requests within 20 s.
2. (manual) With handling on, a game started from the Roblox website opens through Verdra
   (same check as test 1), and the link Roblox receives equals the original.
3. Turning handling off restores the previous handler exactly (registry value, Launch Services
   default or `xdg-mime` default compared before and after, on a test profile), and turning it on
   again records a new ledger entry.
4. Cache clearing removes only the files listed for the platform, on a fixture folder that also
   contains files with similar names, and closes only the process Verdra started.
5. The launched process's environment contains `HTTPS_PROXY` and `HTTP_PROXY` pointing at the
   current proxy port, and otherwise equals the user's environment (fake launcher).
6. A forwarded link is byte-identical to the incoming one, for links with every documented
   parameter and with unusual characters (property test).
7. No Roblox found → M-LAUNCH-01; a Microsoft Store install detected → M-LAUNCH-02 (fixtures of
   both situations).

## Lives in

`trunk/branches/sprout.py`, `soil/*/launcher.py`, `soil/*/files.py`, `bark/scar.py`.

## Refinements from the plan

- Tests 5, 6 and 7 are added so most of S-12 is automatable; tests 1 and 2 stay manual, as the
  plan marks them.
- M-SHELL-02 is listed here because closing on quit belongs to launching; S-01 already reserves
  it "once S-12 can tell that Roblox is running".
- Rule 4 (close only what Verdra started) makes the plan's "the client Verdra launched" testable.
- Built on the facts confirmed on the maintainer's PC (docs/platforms/windows.md, 2026-10-04;
  maintainer's instructions of that day):
  - A **Player** version folder is one that holds `RobloxPlayerBeta.exe` (W-01). A folder holding
    `RobloxStudioBeta.exe` is never used and never changed, even if it also holds the Player.
  - The current Player folder is the one the per-user handler's `version` value names (W-03);
    if that value is missing or names no Player folder, the newest Player folder (by its
    program's date) is used. The value counts only as a folder name, never as a path.
  - Verdra's CA goes into the trust file of **every** Player folder of the client (W-05), never
    Studio's, each as a `ca_roblox_bundle` entry that restores the read-only flag (S-10).
  - Verdra changes only the handler command's `(default)` value; Roblox's `version` value stays.
    If Roblox's updater has rewritten the handler since, the old entry is closed and a new
    snapshot is recorded, so turning handling off never puts back a stale command.
- **Unconfirmed facts block instead of guessing (plan 16.4):** a client that needs one is
  refused with a plain message. Sober needs L-02 (M-LAUNCH-04). A Roblox installed for all
  users (W-02) needs administrator rights to change its trust files, which rule 3 forbids
  (M-LAUNCH-05). Linux doesn't take over `roblox-player:` links until L-02 is confirmed: they
  would reach Sober unrouted.
- **Waiting for facts:** Microsoft Store detection (M-LAUNCH-02, test 7's second half) waits
  until a Store install is observed (W-04: none on the maintainer's PC); cache clearing (test 4)
  waits for the cache file list (W-06, not settled by a listing).
