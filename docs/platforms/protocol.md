# Verification protocol for "(confirm at M1)" facts

**Who runs it:** the maintainer, in the first real-machine test session, on the Windows 11 PC and
on Ubuntu 24.04 (a virtual machine on that PC), signed in as a normal user. Nothing here needs
administrator rights. macOS is deferred until after 1.0 (decision record 0014): there are no
macOS steps, and the former ones are kept as reference in [`macos.md`](macos.md).

**What it changes:** nothing on the system, except stage 2 (which runs the M1 development
build). Every step
that changes a file first makes a byte copy, and checks afterwards that the copy was restored.

**What it never does:** read or patch Roblox's or Sober's program code, or use any third-party
Roblox tool. Facts come only from what the operating system shows (file listings, hashes,
registry and package queries, process lists) and from the public documentation of Sober and the
operating system (clean room, plan 3.1).

## How to record

Each step below says which row of `docs/platforms/<os>.md` it fills. For every step:

1. **Evidence.** Save the command's full output as `docs/platforms/evidence/<os>/<ID>.txt`, with
   the command itself as the first line. Before committing, replace your user name in paths with
   `<user>` and remove anything that identifies the machine or an account (serial numbers, e-mail
   addresses, Roblox user IDs, cookies). Never include the contents of Roblox's or Sober's files:
   names, sizes, hashes and dates only.
2. **Row.** In the facts table: the value copied from the output (not retyped), the state
   (Observed, Confirmed or Differs, see `README.md`), the date (YYYY-MM-DD) and the evidence file.
3. **Versions.** Fill the Machine table once per machine: OS version and build, and the Roblox
   version (Windows: the `version-…` folder name; Linux: Sober's version and commit from
   `flatpak info`).
4. **A fail stops that line of work.** If a step fails, set the row to Differs, write what the
   plan says and what you saw under "Differences from the plan", and tell me. Code that needs the
   fact waits for your decision.

## Stages

- **Stage 1 (observation)** needs no Verdra code. It records paths and names. Run it first; it
  unblocks code that only reads or lists (discovery, version watching).
- **Stage 2 (effect)** needs the M1 development build, run from source with the diagnostic flag
  (plan 16.2, S-11):

  ```sh
  git clone https://github.com/verdra-1/verdra && cd verdra   # a checkout at the M1 branch
  uv sync --locked
  uv run python -m verdra --diagnose-interception
  ```

  While the flag is on, Verdra shows the notice M-DIAG-01, intercepts only the 10.2 hosts, passes
  everything through unchanged, and writes two Activity lines per intercepted connection (M-DIAG-02,
  spec S-11), one for each side:

  ```text
  Diagnostic interception, <host> (Roblox to Verdra): <TLS version>, <cipher>, Verdra's certificate, key ECDSA P-256.
  Diagnostic interception, <host> (Verdra to the server): <TLS version>, <cipher>, the server's certificate verified.
  ```

  A "not verified" in the second line, or no lines at all for a host Roblox uses, is a fail.
  To stop: quit Verdra (tray › Quit Verdra) and start it again without the flag.

  Stage 2 can only run once routing starts from the window (adding Verdra's certificate to the
  trust files and launching Roblox with the proxy settings, specs S-10 and S-12), and that needs
  the trust-file and launcher paths Stage 1 records. So Stage 1 comes first; Stage 2 follows in a
  second session once that code is merged, and this protocol will name the build to use.

## Step 0: the machine (each OS)

| | |
|---|---|
| Command | Windows (PowerShell): `Get-ComputerInfo -Property OsName,OsVersion,OsBuildNumber,OsArchitecture`; Linux: `cat /etc/os-release; uname -m; echo $XDG_SESSION_TYPE; flatpak --version` |
| You should see | The OS name, version, build and architecture (Linux: also `wayland` or `x11`, and the Flatpak version). |
| Record | Machine table; evidence `env.txt`. |
| Fail | Not one of the M0 test systems: say so in the Machine table and continue. |

## Step V0: Roblox uses the proxy variables (each OS, stage 2)

Plan 11 doesn't mark this "(confirm at M1)", but every per-app feature depends on it (S-12 test 1).

| | |
|---|---|
| Command | Start Verdra from source with `--diagnose-interception`, choose "Launch Roblox through Verdra", join any game, wait 30 s, then Activity › Copy (the whole list). |
| You should see | Within 20 s of the launch, Activity lines for connections to `*.roblox.com` or `*.rbxcdn.com` hosts that came through Verdra's proxy. |
| Record | Row V0: Confirmed; evidence `V0.txt` (the copied Activity text; Verdra redacts secrets). |
| Fail | No Roblox connection in Activity after 20 s, or Roblox shows a connection error. |

## Windows (fact IDs W-…)

**Stage 1 on Windows is one script:** `tools/platforms/stage1-windows.ps1` runs Step 0 and the
stage 1 parts of W-01 to W-05, W-07 and W-10 in one go and writes one report file (the user
folder written as `%USERPROFILE%`). It only reads, needs no administrator rights, sends nothing
anywhere and never opens Roblox's login, cookie or settings files (Windows PowerShell itself, not
the script, refreshes its own small startup cache in its own folder whenever it runs); `tests/tools/test_stage1_windows.py`
checks that on every pull request (the commands it may use, and a run on the Windows runner
that must write nothing but its report). For W-06 it lists only the names directly in the Roblox
folder; the before-and-after comparison around a game session moves to stage 2 with W-09, because
it needs a signed-in Roblox and a game.

### W-01 Per-user Roblox install

| | |
|---|---|
| Command | `Get-ChildItem "$env:LOCALAPPDATA\Roblox\Versions" -Directory \| ForEach-Object { Get-ChildItem $_.FullName -Filter RobloxPlayerBeta.exe \| Select-Object FullName, Length, LastWriteTime }` |
| You should see | At least one `...\Roblox\Versions\version-<hex>\RobloxPlayerBeta.exe`. |
| Record | Row W-01: the path pattern with the version folder; Observed. After V0 passes with it: Confirmed. Evidence `W-01.txt`. |
| Fail | No `Versions` folder, or no `RobloxPlayerBeta.exe` in any version folder, with Roblox installed and launched once. |

### W-02 All-users install

| | |
|---|---|
| Command | `Test-Path "${env:ProgramFiles(x86)}\Roblox\Versions"`, and if `True`, the W-01 listing for that folder. |
| You should see | `False` on a normal per-user install. `True` only if Roblox was installed for all users. |
| Record | Row W-02: "not present" or the path; Observed. Evidence `W-02.txt`. |
| Fail | None: either answer is a fact. If `True`, also run W-05 on that folder. |

### W-03 The `roblox-player` link handler

| | |
|---|---|
| Command | `reg query HKCU\Software\Classes\roblox-player /s` then `reg query HKCR\roblox-player /s` |
| You should see | A `shell\open\command` default value naming `RobloxPlayerBeta.exe` (or the Roblox launcher) with `%1`. |
| Record | Row W-03: the key that holds it (HKCU or HKLM via HKCR) and the command; Observed. Evidence `W-03.txt`. |
| Fail | No `roblox-player` key with Roblox installed. |

### W-04 Microsoft Store Roblox (only if a test machine has it)

| | |
|---|---|
| Command | `Get-AppxPackage *Roblox* \| Select-Object Name, PackageFamilyName, InstallLocation, Version`; then stage 2: start that version from Verdra (V0). |
| You should see | A package entry. In stage 2, either Roblox connections in Activity (proxy variables reach it) or none (risk R-05). |
| Record | Row W-04: the PackageFamilyName and whether V0 passed for it; Observed or Confirmed. Evidence `W-04.txt`. |
| Fail | None for detection. If V0 fails for it, that is the expected R-05 case: record "proxy variables don't reach the Store version"; M-LAUNCH-02 covers it. |

### W-05 Trust file in each version folder

| | |
|---|---|
| Command | `Get-ChildItem -Recurse -Filter *.pem "$env:LOCALAPPDATA\Roblox\Versions" \| ForEach-Object { $_.FullName; (Get-FileHash $_.FullName -Algorithm SHA256).Hash; $_.IsReadOnly }` |
| You should see | `...\version-<hex>\ssl\cacert.pem`, its SHA-256 and `False` (or `True` if read-only). |
| Record | Row W-05: the relative path `ssl\cacert.pem`, the hash, the read-only flag; Observed. Evidence `W-05.txt`. |
| Stage 2 | Run Verdra from source with `--diagnose-interception`; it adds its block to that file (S-10). Launch Roblox through Verdra and join a game. Activity shows the intercepted hosts with "upstream verified" and the leaf key type (ECDSA P-256). Quit Verdra, choose Settings › System changes › Reset everything…, then hash the file again: it must equal the hash recorded above. Row W-05: Confirmed. |
| Fail | No `cacert.pem`; or in stage 2 Roblox shows a connection or certificate error with the block in place; or the hash after Reset everything differs. |

### W-06 Cache files to clear

| | |
|---|---|
| Command | Before: `Get-ChildItem -Recurse "$env:LOCALAPPDATA\Roblox","$env:TEMP\Roblox" -File \| Select-Object FullName, Length, LastWriteTime > before.txt`. Launch Roblox, join a game, quit it. After: the same command into `after.txt`. Then `Compare-Object (Get-Content before.txt) (Get-Content after.txt)`. |
| You should see | Files that appear or change during a session (cache databases, HTTP cache entries), outside the `Versions` folder. |
| Record | Row W-06: the list of folders and file name patterns; Observed. Evidence `W-06.txt` (both listings and the comparison). |
| Stage 2 | Close Roblox, move those files to a backup folder, start Roblox normally: it must start and recreate them. Put the originals back. Row W-06: Confirmed. |
| Fail | Roblox doesn't start, or reports damage, with the files moved away. |

### W-07 Client settings file and global settings

| | |
|---|---|
| Command | `Get-ChildItem "$env:LOCALAPPDATA\Roblox\Versions\*\ClientSettings" -ErrorAction SilentlyContinue`; `Get-ChildItem "$env:LOCALAPPDATA\Roblox" -Filter *.xml` |
| You should see | Either a `ClientSettings` folder (it may not exist until something creates it) and the global settings XML file name. |
| Record | Row W-07: what exists; Observed (FastFlags are M4, so stage 1 only). Evidence `W-07.txt`. |
| Fail | None at M1. |

### W-08 Single-instance object name

Settled in plan 16.2: confirmed at M5 with multi-instance. Not run at M1.

### W-09 Reading a running Roblox's proxy variables (S-15)

| | |
|---|---|
| Command | Stage 2: start Roblox through Verdra, then `uv run python -c "import psutil; print([(p.pid, p.environ().get('HTTPS_PROXY')) for p in psutil.process_iter(['name']) if p.info['name'] and 'Roblox' in p.info['name']])"` |
| You should see | The Roblox process with `HTTPS_PROXY` pointing at `http://127.0.0.1:<port>` (Verdra's port). |
| Record | Row W-09: "readable" or the error; Confirmed. Evidence `W-09.txt`. |
| Fail | An access error: then S-15's per-app check can't see a foreign proxy on Windows; tell me. |


### W-10 The hosts file is readable as a normal user (S-15)

| | |
|---|---|
| Command | In a normal (not elevated) PowerShell: `Get-Content "$env:SystemRoot\System32\drivers\etc\hosts" \| Measure-Object -Line` |
| You should see | A line count, and no access error. |
| Record | Row W-10: "readable" and the line count; Confirmed. Evidence `W-10.txt` (the count only, not the file). |
| Fail | An access error: S-15's hosts-file sign can't be checked per app on Windows; tell me. |
## Linux (fact IDs L-…)

### L-01 Sober is installed and launches with the proxy variables

| | |
|---|---|
| Command | `flatpak info org.vinegarhq.Sober; flatpak info --show-permissions org.vinegarhq.Sober` |
| You should see | Sober's ID, version, commit and runtime; its permissions (network among them). |
| Record | Row L-01; Observed, then Confirmed after V0. Evidence `L-01.txt`. |
| Fail | Sober not installed under `org.vinegarhq.Sober`. |

### L-02 Where Sober reads its CA bundle

| | |
|---|---|
| Command | `find ~/.var/app/org.vinegarhq.Sober \( -name '*.pem' -o -name '*.crt' \) -ls; flatpak info -m org.vinegarhq.Sober \| grep -i runtime`. Also read Sober's public documentation for a certificate or trust setting and note the link. |
| You should see | Either a bundle file in Sober's own data folder, or none (Sober then uses its runtime's CA store, which the user can't edit). |
| Record | Row L-02: the candidate path(s) and the documentation link; Observed. Evidence `L-02.txt`. |
| Stage 2 | For each candidate: Verdra from source with `--diagnose-interception` adds its block there (or passes the bundle path with `--env=SSL_CERT_FILE=<path>` if Sober documents it); launch Sober through Verdra; Activity must show the intercepted hosts with "upstream verified". Record which candidate worked: Confirmed. |
| Fail | No candidate makes Sober accept Verdra's leaf: per-app routing on Linux needs a different trust path; tell me. |

### L-03 Asset overlay folder

| | |
|---|---|
| Command | `ls -la ~/.var/app/org.vinegarhq.Sober/data/sober/` |
| You should see | Sober's data folder; note whether an asset overlay folder exists and its name, with Sober's documentation link. |
| Record | Row L-03; Observed (file tweaks are M4). Evidence `L-03.txt`. |
| Fail | None at M1. |

### L-04 `config.json` and the FastFlags key

| | |
|---|---|
| Command | `ls -la ~/.var/app/org.vinegarhq.Sober/config/sober/`; `python3 -c "import json,sys; print(sorted(json.load(open(sys.argv[1]))))" ~/.var/app/org.vinegarhq.Sober/config/sober/config.json` |
| You should see | `config.json` and its top-level key names (names only, no values). |
| Record | Row L-04: the file and the key that holds FastFlags, from Sober's documentation; Observed (FastFlags are M4). Evidence `L-04.txt`. |
| Fail | None at M1. |

### L-05 Link handler

| | |
|---|---|
| Command | `xdg-mime query default x-scheme-handler/roblox-player` |
| You should see | Sober's desktop entry (or nothing if no handler is set). |
| Record | Row L-05; Observed. Evidence `L-05.txt`. |
| Fail | None: either answer is a fact for S-12 test 3. |

### L-06 Reading a running Sober's proxy variables (S-15)

| | |
|---|---|
| Command | Stage 2: start Sober through Verdra, then `pgrep -a -i sober` (to see the process names Flatpak shows), then `uv run python -c "import psutil; print([(p.pid, p.info['name'], p.environ().get('HTTPS_PROXY')) for p in psutil.process_iter(['name']) if p.info['name'] and 'sober' in p.info['name'].lower()])"` |
| You should see | Sober's process (and possibly a `bwrap` parent from Flatpak's sandbox) with `HTTPS_PROXY` pointing at `http://127.0.0.1:<port>` (Verdra's port, as Activity shows it). |
| Record | Row L-06: "readable", the process name that carries the variable, or the exact error; Confirmed. Evidence `L-06.txt` (both commands). |
| Fail | `pgrep` shows Sober but the Python list is empty or the variable is missing (the sandbox hides it), or `psutil.AccessDenied`: S-15's per-app check can't see a foreign proxy on Linux. Set Differs and tell me. |


### L-07 `/etc/hosts` from the host and from inside the Flatpak (S-15)

| | |
|---|---|
| Command | `sha256sum /etc/hosts; flatpak run --command=sha256sum org.vinegarhq.Sober /etc/hosts` |
| You should see | Two identical hashes: the sandbox sees the host's file. Sober's sandbox stands in for Verdra's own Flatpak, which doesn't exist yet; the Flatpak build re-checks it when it is made. |
| Record | Row L-07: both hashes and "same" or "different"; Confirmed if the same, Differs if not. Evidence `L-07.txt` (hashes only). |
| Fail | Different hashes or an error: Verdra's Flatpak build can't see foreign hosts lines, so S-15's hosts-file sign needs another way on Linux; tell me. |
## After the protocol

1. Update `docs/platforms/<os>.md` and the evidence files in one `docs/` pull request per OS.
2. Any Differs goes to the maintainer before that pull request is merged.
3. Code that uses a fact cites its ID (W-05, L-02, …) in a comment; `tools/check_docs.py` can then
   check that each cited ID is Confirmed (proposed for M1).
