# 0013. Decisions from the third M0 review round

- **Status:** Accepted
- **Date:** 2026-10-02
- **Plan sections:** 10.1, 13.2, 16.2 ("M0 review round 3 decisions"), Feature specs S-15,
  Reference R5 (M-SHELL-01)

## Context

The maintainer ruled on the three findings of the round-2 self-review that needed a decision
(F12, F13, F17) and made the repository public, because the private repository's free Actions
minutes ran out (plan 13.2 and 16.2, 2 October 2026). This record lists what that means for the
code and the M1 specs.

## Decision

### M-SHELL-01 (F12)

M-SHELL-01 "Verdra is still running in the tray. Quit it from the tray menu." is shown once, as an
OS tray notification: the window is already hidden when it fires, so an in-app toast would be
invisible. It is also written to Activity. S-01 acceptance test 8 checks both.

### Activity lines (F13)

Every Activity line written for the user (Info, Warning and Error records that describe
something that happened) comes from the message catalogue and has a message ID. Technical detail
has none: Debug lines (such as the startup steps and their timings), exception text and
tracebacks, and values inside a message's placeholders. New IDs: M-SHELL-03 to M-SHELL-08,
M-SET-15 to M-SET-19, M-LOG-04 and M-JOB-03, listed word for word in S-01 to S-04.
`tests/test_activity_lines.py` fails on any Info-or-above log call whose format string holds
words of its own. Because the startup steps are Debug lines now, the build's launch check
(`tools/check_build.py --launch`) turns detailed logging on in its throwaway data folder.

### Coexistence in per-app mode (F17)

In per-app mode a taken port 49443 is not a coexistence sign: S-11 moves to a free port and
writes M-PROXY-03 (plan 10.1). The per-app signs are a running Roblox whose proxy isn't
Verdra's, and Roblox hostnames mapped in the hosts file without Verdra's marker (these break
per-app routing too, because Verdra's upstream lookup would reach the other tool). Port 443 on
loopback is checked only in Hosts-file mode (M6). The M1 spec S-15 and the platform protocol
(facts W-10, M-07, L-07: the hosts file is readable) follow this.

### Public repository

The repository is public from M0, after a pre-publication audit of the full history (secrets,
personal data, clean room, private files, workflow safety). Standard GitHub-hosted runners are
free for public repositories; decision record 0012 says what CI runs where.

## Consequences

- A new user-facing log line needs a catalogue entry and a spec listing before its test passes.
- Technical detail that used to be at Info level (startup timings, the shutdown duration) is in
  the log only while detailed logging is on.
- Anyone can read the repository, its history and its pull requests from now on, so nothing
  private may be committed or written in a pull request.
