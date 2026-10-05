# S-15 Coexistence

**Status:** Built
**Milestone:** M1 (per-app part); M6 (Hosts-file part, marked below)
**Risk badge:** none
**Plan sections:** 10.1 (Coexistence), 14 (M1: "coexistence check"), 16.2 (M0 review round 2:
"S-15's per-app coexistence check is M1 work; its Hosts-file part stays at M6"; M0 review round
3: the per-app signs), Feature specs S-15, Reference R5 (M-COEX-01)

## Purpose

Never fight with another routing tool, and say so clearly.

## Behaviour

- **When.** Before routing starts (routing start, "Start routing", Launch Roblox through Verdra),
  `roots/gardener` checks for signs of another routing tool. If it finds one, routing doesn't
  start, the status is Error with that reason (S-14), and M-COEX-01 is shown with "Try again" and
  "Cancel". "Try again" runs the check again.
- **Per-app mode (M1).** Two signs:
  1. **A running Roblox client whose proxy isn't Verdra's.** Verdra lists the user's own
     processes that are a Roblox client found by S-12 discovery (paths from
     `docs/platforms/<os>.md`) and reads their `HTTPS_PROXY` and `HTTP_PROXY` environment values;
     a value that is set and doesn't point at Verdra's own listener is a sign. A client with no
     proxy variables isn't a sign (it was started normally; S-14 shows "Restart Roblox through
     Verdra" instead).
  2. **Roblox hostnames mapped in the hosts file without Verdra's marker.** Verdra reads the
     system hosts file (read-only; `%SystemRoot%\System32\drivers\etc\hosts`) and looks for
     any line that maps a hostname from 10.2 to
     an address and doesn't carry Verdra's marker `# verdra:route`. This breaks per-app routing
     too: Verdra's upstream lookup for that host would reach the other tool instead of Roblox.
- **Not a sign:** Verdra's own port (`routing.proxy_port`, default 49443) being taken. S-11
  moves to another free loopback port and writes M-PROXY-03 to Activity (plan 10.1).
- **Hosts-file mode (M6, not built at M1).** One more sign: port 443 already in use on loopback.
  The hosts-file sign above applies in both modes.
- **Where the environment can't be read** (an OS refuses to show another process's environment,
  confirm at M1 per platform), that client isn't treated as a sign, and Activity records that the
  check was incomplete and why.

## Rules

1. Verdra never changes or removes another tool's entries, files or settings. It only reads the
   generic signs listed here: the hosts file, read-only and line by line, and its own user's
   Roblox processes.
2. Only the user's own processes are inspected, read-only; nothing is written to them.
3. Detection never blocks the UI thread (it runs as a background job, S-04).
4. Each sign found is logged with what was seen (process name and ID, the proxy host and port,
   redacted by `bark/veil`), once per check.

## Messages

- M-COEX-01 (Dialog) "Another tool is already routing Roblox traffic. Close it, then try again."
  Buttons "Try again", "Cancel".
- M-COEX-02 (Activity, new) "Another routing tool: <name> (process <pid>) uses the proxy <proxy>."
  The proxy is shown as its address only, never with a user name or password.
- M-COEX-03 (Activity, new) "Another routing tool: line <line> of the hosts file maps <host>."
- M-COEX-04 (Activity, new) "Verdra couldn't check everything for other routing tools (<parts>),
  so it went ahead."

## Acceptance tests

1. A fake Roblox client process (a test executable at a discovered path) started with
   `HTTPS_PROXY` pointing at another loopback port blocks routing start with M-COEX-01 and status
   Error; started with Verdra's own proxy, or with no proxy variables, it doesn't.
2. "Try again" after the fake client exits starts routing.
3. A hosts file (a test copy at a temporary path) with `127.0.0.1 assetdelivery.roblox.com`, or
   the same host mapped to any other address, without Verdra's marker blocks start with
   M-COEX-01; the same line with `# verdra:route`, lines for other hosts, and comment lines
   don't. The test hosts file is byte-identical afterwards.
4. Verdra's own port taken by another listener doesn't block start: routing starts on another
   port and Activity shows M-PROXY-03.
5. Processes that aren't Roblox clients, whatever their proxy variables, are never signs.
6. When the environment of a client can't be read (simulated), routing starts and Activity
   records the incomplete check.
7. The check runs off the UI thread and finishes within 2 s with 200 processes running (fake
   process list) and a 2,000-line hosts file.
8. (M6) Port 443 in use on loopback blocks start with M-COEX-01 in Hosts-file mode only.
9. (M6) Foreign hosts lines are byte-identical after Verdra starts, stops and resets in
   Hosts-file mode (plan S-15 test 2).

## Lives in

`roots/gardener.py` (the check), `soil/*/launcher.py` (Roblox client discovery and process
lookup), `canopy/leaves/dialogs.py` (the dialog).

## Refinements from the plan

- Settled (plan 16.2, M0 review round 3, ruling F17): in per-app mode a taken port 49443 is not
  a coexistence sign (the 10.1 fallback handles it, M-PROXY-03); the per-app signs are a running
  Roblox whose proxy isn't Verdra's and Roblox hostnames in the hosts file without Verdra's
  marker. Port 443 on loopback is checked only in Hosts-file mode (M6).
- Tests 3 to 7 are added for the signs and rules; tests 8 and 9 carry the Hosts-file part to M6,
  where they become Built with S-13.
- Verdra never writes the hosts file in per-app mode. That a normal user can read it is
  confirmed at M1 (fact W-10 in `docs/platforms/`; the Linux fact L-07 is kept as reference
  while Linux is paused).
- Reading another process's environment is OS-dependent; the protocol in `docs/platforms/`
  records whether it works (fact W-09; L-06 for Linux, paused).
- Built for per-app mode (2026-10-04):
  - The check runs before routing starts and before each launch through Verdra, as a background
    job (rule 3). Signs go to Activity one line each (M-COEX-02, M-COEX-03, rule 4); the
    status is Error with M-COEX-01, and "Try again" repeats the request that was stopped.
  - Windows: a running Player is a `RobloxPlayerBeta.exe` inside a version folder of the
    discovered install, run by the same user (W-01). Its environment is read with psutil;
    whether that works on a real machine is W-09 (stage 2). When it can't be read, the client
    isn't a sign and M-COEX-04 records it (test 6).
  - Linux is paused (decision record 0018): nothing is listed there, and Verdra doesn't run on
    Linux.
  - The hosts file is read from `%SystemRoot%\System32\drivers\etc\hosts` (W-10) and
    `/etc/hosts` (L-07), as text, never written.
  - Plan 10.2's hosts live in `roots/rules`: the exact list confirmed by capture on Windows at
    M1 (plan 16.2).
