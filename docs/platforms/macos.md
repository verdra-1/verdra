# macOS platform facts

> **Deferred until after 1.0** (Master plan 16.2, decision record 0014). Nothing on this page is
> run, built or tested before the deferral is lifted; risk R-03 is inactive. The page keeps the
> facts table, the R-03 trust-file test and the former protocol steps as reference, so macOS can
> return without starting over. Lifting the deferral needs a Mac with Apple silicon, the Apple
> Developer Program and a new decision record; Intel Macs are then dropped, so the Intel notes
> below no longer apply.

States are defined in [README.md](README.md). Until a row is `Confirmed`, no code may depend on
it (plan 16.4).

## Machine

| Field | Value |
|---|---|
| OS, version, build | |
| Architecture | |
| Roblox CFBundleVersion; Apple silicon or Intel build | |
| Checked by, date | |
| Evidence folder | `evidence/macos/` |

## Facts

| ID | Plan says | Recorded value | State | Date | Evidence |
|---|---|---|---|---|---|
| M-01 | `/Applications/Roblox.app` or `~/Applications/Roblox.app`; binary `Contents/MacOS/RobloxPlayer` | | Unconfirmed | | |
| M-02 | Trust file `Contents/Resources/ssl/cacert.pem` | | Unconfirmed | | |
| M-03 | `CFBundleURLTypes` entry for `roblox-player` | | Unconfirmed | | |
| M-04 | Cache and settings under `~/Library/Roblox`, `~/Library/Caches` (exact list) | | Unconfirmed | | |
| M-05 | Client settings file inside the app bundle | | Unconfirmed | | |
| V0 | Client honors `HTTPS_PROXY` / `HTTP_PROXY` when the binary is run directly | | Unconfirmed | | |
| M-06 | A running Roblox's proxy variables can be read (S-15) | | Unconfirmed | | |
| M-07 | `/etc/hosts` is readable without administrator rights (S-15) | | Unconfirmed | | |
| R-03 | Editing the trust file keeps Roblox working (procedure below) | | Not run | | |

## Differences from the plan

None recorded.

## R-03 trust-file test

Plan 11.2 and risk R-03: Verdra adds its CA to the trust file inside the signed `Roblox.app`.
That may break the app's code signature or be blocked by macOS. When macOS returns, this test
MUST run before any macOS trust-file code is written. Its result goes into a decision record
(`docs/decisions/00xx-macos-trust-file.md`).

### Preconditions

- Test Mac on the M0 list (Apple silicon, current macOS). If an Intel Mac or macOS 12 to 14 is
  available, repeat there; record each run separately.
- Roblox installed normally and up to date; launched once and signed in with a **test account**.
- The M1 development build with S-10 and S-11, run from source with
  `uv run python -m verdra --diagnose-interception` (stage 2, see `protocol.md`), for step 8
  only. Steps 1 to 7 use only macOS's own tools and `openssl`; they can run first.
- Terminal has **no** extra privacy permissions (System Settings › Privacy & Security: not in
  Full Disk Access or App Management). Record that.

### Steps

Run these in Terminal, in this order. Save each step's output as
`docs/platforms/evidence/macos/R-03-<step>.txt`.

```sh
APP=/Applications/Roblox.app; [ -d "$APP" ] || APP=~/Applications/Roblox.app
PEM="$APP/Contents/Resources/ssl/cacert.pem"
```

1. **Baseline signature.**
   `codesign --verify --deep --strict --verbose=2 "$APP"; echo "exit $?"`;
   `codesign -dv --verbose=4 "$APP" 2>&1 | grep -E 'Identifier|TeamIdentifier|Authority|Sealed'`;
   `spctl --assess --type execute -vv "$APP"; echo "exit $?"`.
   You should see "valid on disk", "satisfies its Designated Requirement", `exit 0`, and spctl
   "accepted, source=Notarized Developer ID".
2. **Baseline file.** `shasum -a 256 "$PEM"; ls -lO "$PEM"; xattr -l "$PEM"`, then
   `cp -p "$PEM" ~/verdra-r03-backup.pem`. Record the hash.
3. **Throwaway test CA** (two days, the same Name Constraints as Verdra's, trusted nowhere):
   ```sh
   openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 2 \
     -keyout /tmp/r03-key.pem -out /tmp/r03-ca.pem -subj "/CN=Verdra R-03 test CA" \
     -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
     -addext "keyUsage=critical,keyCertSign,cRLSign" \
     -addext "nameConstraints=critical,permitted;DNS:roblox.com,permitted;DNS:rbxcdn.com"
   ```
   You should see two new files and no error. (If this `openssl` rejects `-addext`, drop the
   three `-addext` lines; steps 4 to 7 test the file edit, not the certificate.)
4. **Edit as a normal user.**
   `{ echo '# BEGIN Verdra Local CA'; cat /tmp/r03-ca.pem; echo '# END Verdra Local CA'; } >> "$PEM"; echo "exit $?"`
   Record: `exit 0`, or the error text, and whether macOS showed any prompt (for example
   "Terminal would like to modify apps on your Mac"). Don't click Allow on any prompt: choose
   Don't Allow and record it.
5. **Signature after the edit.** Repeat step 1's three commands; save the output.
6. **Normal launch.** Quit Roblox completely. Open Roblox from Finder; then from a
   `roblox-player:` link on the Roblox website; then with `"$APP/Contents/MacOS/RobloxPlayer"`.
   For each, record whether it reaches the home screen, any dialog ("damaged", "can't be
   opened", "unidentified developer"), and the output of
   `find ~/Library/Logs/DiagnosticReports -newer ~/verdra-r03-backup.pem -iname '*roblox*'`
   (it should print nothing).
7. **After a restart.** Restart the Mac and repeat step 6 once (Gatekeeper can cache its
   result until then).
8. **Effect (stage 2).** First restore the original (step 10's `cp` line), so only Verdra's own
   block goes in. Start Verdra from source with
   `uv run python -m verdra --diagnose-interception`; it adds its block (S-10). Choose "Launch
   Roblox through Verdra" and join a game. Activity must show the intercepted 10.2 hosts with
   "upstream verified" and the leaf key type, and Roblox must work normally. Activity › Copy into
   the evidence file. Then Settings › System changes › Reset everything… removes the block.
9. **Roblox update.** If Roblox updates during the test (its `CFBundleVersion` changes), record
   `grep -c 'BEGIN Verdra Local CA' "$PEM"`.
10. **Restore.** `cp -p ~/verdra-r03-backup.pem "$PEM"; shasum -a 256 "$PEM"` (must equal step
    2), repeat step 1 (output must equal the baseline), `rm /tmp/r03-key.pem /tmp/r03-ca.pem`,
    and launch Roblox once from Finder.

### Pass or fail

**PASS** only if all of these hold on every macOS version tested:

- Step 4: the write succeeds from a normal user process **with no system prompt**.
- Step 6 and 7: all three launch paths reach the home screen, with no dialog and no new crash
  report, before and after restart.
- Step 8: the intercepted request succeeds (Roblox trusts the CA from that file).
- Step 10: after restoring, the signature check output equals the baseline.

**FAIL** if any of these doesn't hold. Record which one. A failed step 5 alone (signature reported
invalid) is **not** a fail if steps 6 to 8 pass; it is recorded, because macOS may still enforce
it later.

### What follows

- **PASS:** the decision record states per-app routing on macOS uses the trust file; M-02 becomes
  `Confirmed`; S-10's macOS trust-file support can ship (until then it runs only from source,
  for this test).
- **FAIL:** stop. The plan's first fallback is a trust-bundle path passed through the
  environment; testing it needs a documented environment variable that Roblox reads, and none is
  documented publicly. The maintainer decides whether to test candidate variables or go straight
  to the second fallback (Hosts-file routing with the keeper patching the file, which moves macOS
  per-app routing to M6). This is a plan decision, not one made in code.
- **A prompt in step 4 (App Management):** recorded as FAIL under the rule above; the maintainer
  may decide in the decision record that one approval prompt is acceptable, which changes plan
  11.2.

## Former protocol steps (reference only)

These were the macOS steps of [protocol.md](protocol.md) until the deferral.

Set `APP` first: `APP=/Applications/Roblox.app; [ -d "$APP" ] || APP=~/Applications/Roblox.app`.

### M-01 The app and the player binary

| | |
|---|---|
| Command | `ls -ld /Applications/Roblox.app ~/Applications/Roblox.app; ls -l "$APP/Contents/MacOS"; defaults read "$APP/Contents/Info.plist" CFBundleExecutable; defaults read "$APP/Contents/Info.plist" CFBundleVersion` |
| You should see | One of the two app paths; `RobloxPlayer` in `Contents/MacOS`; the executable name and the version. |
| Record | Row M-01: the app path and binary path; Observed, then Confirmed after V0. Evidence `M-01.txt`. |
| Fail | No `Roblox.app` in either place, or no `RobloxPlayer` binary. |

### M-02 Trust file in the app

| | |
|---|---|
| Command | `find "$APP/Contents" -name '*.pem'; shasum -a 256 "$APP/Contents/Resources/ssl/cacert.pem"; ls -lO "$APP/Contents/Resources/ssl/cacert.pem"` |
| You should see | `Contents/Resources/ssl/cacert.pem`, its hash and flags. |
| Record | Row M-02: the path, hash and flags; Observed. Evidence `M-02.txt`. |
| Stage 2 | The R-03 procedure in `macos.md`. Its result decides Confirmed or Differs. |
| Fail | No `cacert.pem` in the app, or R-03 fails. |

### M-03 URL handler entry

| | |
|---|---|
| Command | `defaults read "$APP/Contents/Info.plist" CFBundleURLTypes` |
| You should see | An entry whose `CFBundleURLSchemes` contains `roblox-player`. |
| Record | Row M-03; Observed. Evidence `M-03.txt`. |
| Fail | No `roblox-player` scheme. |

### M-04 Cache and settings files

| | |
|---|---|
| Command | `touch /tmp/verdra-marker`; launch Roblox, join a game, quit; then `find ~/Library/Roblox ~/Library/Caches ~/Library/Preferences -iname '*roblox*' -newer /tmp/verdra-marker -ls` |
| You should see | The files Roblox wrote during the session. |
| Record | Row M-04: folders and name patterns; Observed. Evidence `M-04.txt`. Stage 2 as W-06 (move them aside, Roblox must start and recreate them, put them back): Confirmed. |
| Fail | As W-06. |

### M-05 Client settings file in the app

| | |
|---|---|
| Command | `find "$APP/Contents" -iname '*ClientSettings*'` |
| You should see | A folder or nothing (it may not exist until something creates it). |
| Record | Row M-05; Observed (FastFlags are M4). Evidence `M-05.txt`. |
| Fail | None at M1. |

### M-06 Reading a running Roblox's proxy variables (S-15)

| | |
|---|---|
| Command | Stage 2: start Roblox through Verdra, then `uv run python -c "import psutil; print([(p.pid, p.info['name'], p.environ().get('HTTPS_PROXY')) for p in psutil.process_iter(['name']) if p.info['name'] and 'Roblox' in p.info['name']])"` |
| You should see | The `RobloxPlayer` process with `HTTPS_PROXY` pointing at `http://127.0.0.1:<port>` (Verdra's port, as Activity shows it). |
| Record | Row M-06: "readable" and the process name, or the exact error; Confirmed. Evidence `M-06.txt`. |
| Fail | An empty list while Roblox runs, or `psutil.AccessDenied` / `PermissionError`: S-15's per-app check can't see a foreign proxy on macOS. Set Differs and tell me. |


### M-07 `/etc/hosts` is readable as a normal user (S-15)

| | |
|---|---|
| Command | `wc -l /etc/hosts; ls -l /etc/hosts` |
| You should see | A line count, and permissions that allow reading for everyone (`-rw-r--r--`). |
| Record | Row M-07: "readable" and the permissions; Confirmed. Evidence `M-07.txt` (not the file's contents). |
| Fail | `Permission denied`: tell me. |
