# S-16 Reset everything

**Status:** Agreed
**Milestone:** M1
**Risk badge:** none
**Plan sections:** 1 (principle "Rooted"), 2 (zero entries after reset), 7.7 (Settings › System
changes), 7.8 (Reset everything dialog), 7.10 (tray), 9.2 (`changes.json`), 9.4 (ledger), 9.7
(atomic writes), 11.1–11.3 (uninstallers), 12.2, Reference R1 (`trunk/branches/fallow`,
`bark/scar`, `trunk/sapwood/cli`, `canopy/screens/settings`), R5 (M-RESET-01 to M-RESET-03)

## Purpose

Undo every change Verdra made to the system, in one action, even after a crash.

## Behaviour

- **System changes.** Settings › System changes lists every ledger entry that isn't `removed`:
  kind (plain name), target, created date and state (pending, done, failed with its reason).
- **Reset everything…** (Settings › System changes, tray menu item 5) asks M-RESET-03, then shows
  the list and undoes entries in reverse creation order, with per-item progress, as one
  background job (S-04). It ends with M-RESET-01 or M-RESET-02.
- **Undo per kind.** Each entry kind (plan 9.4) has one undo action using the details stored in
  the entry. The kinds that can exist at M1 are `ca_roblox_bundle` (remove the block, restore
  the read-only flag; S-10) and `uri_handler` (restore the previous handler exactly; S-12).
  Reset also deletes the CA key from the secret store and `trust/ca.crt`. Later kinds add their
  undo action in their own milestone; an entry of an unknown kind is reported as failed, never
  skipped silently.
- **Half-done entries.** An entry left `pending` by a crash is undone the same way: each undo
  action first checks whether the change is present, so it works whether or not the change was
  made.
- **Before undoing.** Reset stops routing and closes the Roblox client Verdra launched (S-12),
  after M-LAUNCH-03 when Roblox is running.
- **Command line.** `verdra --reset-everything` runs the same steps with the same ledger, printing
  each item and the summary; `--quiet` prints nothing and reports through the exit code (0 all
  removed or nothing to remove, 1 some failed). The Windows and Linux uninstallers and macOS
  "Remove Verdra…" run `verdra --reset-everything --quiet` first (plan 11.1–11.3).
- **Option "Also delete my profiles, library and settings"** (off by default): after the ledger
  is empty, deletes Verdra's own config, data and cache folders (plan 9.1), not the log folder
  until the end of the run.

## Rules

1. Idempotent: running reset twice is harmless; the second run removes nothing and says so.
2. A failed item stays listed with its reason and state `failed`, and can be retried; the other
   items still run.
3. Reset works when routing is broken, when the proxy can't start, and without the window
   (command line), because it depends only on the ledger and the undo actions.
4. Every ledger write is atomic with `.bak` (plan 9.7); a damaged ledger is restored from `.bak`.
5. Undo touches only what the entry names; it never removes content Verdra didn't add (for
   example another tool's lines in a trust file).
6. Nothing is deleted from the user's own folders unless the option is ticked.

## Messages

- M-RESET-01 (Dialog) "Removed <n> changes. Verdra left nothing behind."
- M-RESET-02 (Dialog) "<n> changes couldn't be removed. See the list for details."
- M-RESET-03 (Dialog, new in R5) "Remove everything Verdra changed on this computer? Your
  profiles and library stay." Buttons "Reset everything", "Cancel".
- M-RESET-05 (Notice, new) "Verdra can't read its list of system changes in <path>." Shown in
  Settings › System changes, and printed by the command line, when the ledger and its `.bak`
  copy are both damaged; reset then changes nothing.
- M-RESET-06 (reason, new) "Verdra can't undo this kind of change in this version." The reason
  stored with an entry whose kind has no undo action yet.
- M-RESET-07 (Activity and command line, new) "Removed <change> (<target>)." One line per change
  removed.
- M-RESET-08 (Activity and command line, new) "Couldn't remove <change> (<target>): <reason>"
  One line per change that couldn't be removed.
- M-RESET-01 and M-RESET-02 have singular forms ("Removed 1 change.", "1 change couldn't be
  removed.").

## Acceptance tests

1. On a test profile of each OS (CI runner home folder, fixture Roblox install, fake secret
   store), after every M1 feature has been used (routing started, CA added to every trust-file
   fixture, link handling on), reset makes a snapshot of trust files, link handler, secret
   store items and Verdra's ledger equal to the snapshot taken before first start. Extended with
   each later milestone's entry kinds (hosts, tasks, services, autostart, file tweaks).
2. A crash simulated after each ledger write and before the change (and after the change, before
   "done") leaves a state that reset then completes, for each M1 entry kind.
3. A second reset reports nothing to remove (M-RESET-01 with 0, exit code 0) and changes no file.
4. One undo made to fail (read-only fixture) leaves that item `failed` with its reason, the
   others removed, M-RESET-02, exit code 1; retrying after the cause is fixed removes it.
5. Reset with the proxy port taken and routing in Error completes.
6. `verdra --reset-everything --quiet` prints nothing and returns the documented exit codes;
   without `--quiet` it prints one line per item.
7. A trust-file fixture holding a foreign block and Verdra's block keeps the foreign block
   byte for byte after reset.
8. The dialog is keyboard-operable (Cancel is the default), and every item and the summary are
   written to Activity.

## Lives in

`trunk/branches/fallow.py`, `bark/scar.py`, `trunk/sapwood/cli.py`, `canopy/screens/settings.py`,
`canopy/crown/tray.py`.

## Refinements from the plan

- Tests 4 to 8 are added for rules the plan states (retry, works when broken, command-line form,
  never touches others' content) but S-16 doesn't test.
- Test 1's "full use of every feature" is scoped to what exists at each milestone; at M1 that is
  CA blocks and the link handler. The M8 installer smoke test (plan 13.x) is the full check.
- Exit codes for `--quiet` are not in the plan; 0 and 1 above are a proposal so uninstallers
  can tell success from failure.
- The System changes list shows, newest first (the order reset undoes them), each kind by a
  plain name (plan 4.3, R6): `ca_roblox_bundle` "Verdra's certificate in Roblox",
  `hosts_entries` "Hosts file entries", `keeper_install` "Verdra Keeper helper",
  `scheduled_task` "Scheduled task", `launch_agent` "Launch agent", `launch_daemon` "Launch
  daemon", `polkit_policy` "Permission policy", `systemd_unit` "System service", `autostart`
  "Start with the system", `launcher_entry` "Launcher entry", `uri_handler` "Roblox link
  handler", `file_tweak` "File tweak", `client_settings_file` "Client settings file",
  `frame_rate_setting` "Frame-rate cap". Columns: Change, Where, Made (date and time in the
  user's locale), State (Pending, Done, or "Failed: <reason>"). It is read again each time the
  screen is shown. M-RESET-05 is added for a ledger that can't be read, which the plan doesn't
  cover.
- The command line loads the message catalogue for the language in the settings before it
  prints, so its lines and the summary's plural forms match the window's. If the ledger can't
  be read, it prints M-RESET-05, changes nothing (the CA key stays, because trust files may
  still hold its block) and exits with 1.
- Reset deletes the CA key and `trust/ca.crt`, which are in Verdra's own folders and the secret
  store and so aren't ledger entries; plan S-10 says reset deletes the key, so this is stated
  explicitly here.
