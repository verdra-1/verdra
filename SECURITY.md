# Security policy

Verdra runs a local proxy, holds a certificate authority key and can store Roblox login tokens,
so security reports matter to us.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting: open
<https://github.com/verdra-1/verdra/security/advisories/new> and describe the issue, the
affected version and how to reproduce it. Do not open a public issue for a vulnerability.

## What to expect

| Step | Target |
| --- | --- |
| Acknowledgement of your report | Within 3 days |
| Fix or mitigation of a critical issue | Within 14 days |
| Advisory | Published once the fix is released, with credit to you unless you ask otherwise |

## Supported versions

Until 1.0, only the latest release receives security fixes.

## Scope

In scope: the Verdra app, its privileged helper (Verdra Keeper), its installers and release
artefacts, and the signed preset catalogue client. Out of scope: Roblox itself, and
third-party presets or packs (report those to their authors).
