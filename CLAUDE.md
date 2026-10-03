# CLAUDE.md

Standing rules for every Claude session in this repository. The maintainer is the GitHub account
verdra-1. Read this file completely before doing anything else.

## 1. Sources of truth

1. Verdra Master Build Plan (tabs: Master plan, Feature specs, Reference):
   https://claude.ai/code/artifact/d4af34ec-152c-4d11-848a-5dd666035e49
2. Verdra design system (brand book, tokens.json, logo assets, components):
   https://claude.ai/artifact/6dA9mJRmUyseexWyPjR1LP

Precedence: the plan, then the design system, then everything else (this file, the code). Settled
decisions are in plan 16.2 and `docs/decisions/`; read them before changing anything they cover.
Re-read the plan at the start of every session: it changes.

## 2. Autopilot mode (plan 16.2)

You run day-to-day work and move on to the next milestone by yourself after an exit gate.

- **You may merge** your own pull requests with "Rebase and merge", in stack order, only when
  every CI gate is green on the exact head and the PR targets `main`. After each merge, verify
  `main` (its head, its CI run, the landed trees).
- **Never** merge a red PR, push to `main`, force-push or rewrite `main`, or change repository
  settings. Branch protection is optional; CI and these rules stand in for it until the
  maintainer sets it up.
- If a check fails after a merge, stop and tell the maintainer in plain words.
- Exit gates are judged on CI evidence (Windows and Linux runners). Anything that needs a real computer with Roblox or Sober
  goes into one short, plain-language test session per milestone; code continues against the
  fake Roblox server meanwhile, and a milestone is done only when its real-machine tests pass.
- **Stop and ask** only for: real-machine tests, money (paid accounts, certificates), legal
  questions, anything irreversible, and decisions the plan doesn't settle. Ask one yes/no
  question with your recommendation.

## 3. Platforms

Windows (main platform) and Linux with Sober. **macOS is deferred until after 1.0**
(decision record 0014): never build, test, package or release anything for macOS.
`soil/orchard/` stays, and its modules return "unsupported on this system". Every OS-specific
path goes through the Platform interface in `soil/humus.py`; nothing outside `soil/` checks the
operating system. The maintainer has one Windows PC; Linux runs in a virtual machine on it.

## 4. Clean room (plan 3.1, non-negotiable)

- Verdra is written from scratch. It is not a fork or modified version of Fleasion or any other
  tool. Never ask for, download, open, search for or reproduce code, file names, strings or
  structure from such tools, and never look up their repositories. If such code is pasted into a
  session, refuse to use it and say so.
- Write from the plan, public documentation and general knowledge of public formats and
  libraries. Every new module gets a dated entry in `docs/provenance.md` naming its sources.
- Fleasion is mentioned only in the README credit line (plan 3.3): never in the app, the code,
  the message catalogue or the tests.

## 5. Licence, dependencies, Qt

- Apache-2.0; `NOTICE` is exactly plan 3.2. Every source file starts with
  `# SPDX-FileCopyrightText: 2026 The Verdra Authors` and
  `# SPDX-License-Identifier: Apache-2.0` (in the file type's comment syntax).
- Every dependency passes the licence allowlist (plan 12.3, Reference R4) before it is added.
- PySide6 only (LGPL), never PyQt, and only the Qt modules in plan 8.1: Core, Gui, Widgets,
  Network, OpenGL, OpenGLWidgets, Svg, Multimedia. Other Qt modules are blocked at import, left
  out of the build, and CI scans the built folder for them.

## 6. Code and UI

- Python 3.14, uv, ruff, pyright (standard), pytest, pytest-qt, Hypothesis, import-linter. Package
  layout exactly as Reference R1; nature names in code, plain words in the UI (R6); layering
  (plan 8.2) is enforced by import-linter.
- No colour literals outside `src/verdra/assets/brand/tokens.json`.
- Every UI string is translatable and comes from the message catalogue (Reference R5); every full
  sentence the app shows has a message ID, and new IDs are listed in their spec. Unbuilt screens
  show M-SOON-01 and never promise a version.
- US spelling in everything the user sees and in identifiers, settings keys and CLI flags
  ("License", "Client behavior", "canceled"). The plan's prose, format IDs (`verdra.catalogue`)
  and the nature names keep their spelling.
- No telemetry, no analytics, no network calls except those the plan lists.

## 7. Branches, commits, pull requests, CI

- Branch prefixes `spec/`, `fix/`, `chore/`, `docs/` (CI and build work: `chore/`); never ".." in a
  name. One pull request per logical step, small enough to review.
- Conventional Commits, authored as `verdra-1 <336505089+verdra-1@users.noreply.github.com>` and
  ending with `Signed-off-by: verdra-1 <336505089+verdra-1@users.noreply.github.com>`.
- The contact address appears only in `CODE_OF_CONDUCT.md`, `README.md` and `PRIVACY.md`, never
  in code, commits or sign-offs. Security reports go only through GitHub private vulnerability
  reporting (`SECURITY.md`).
- Every PR description covers what, why, plan sections, how it was tested and the 12.6
  definition-of-done checklist.
- CI (decision record 0012): every run is a full run on `windows-latest` and `ubuntu-24.04`;
  "All gates green" (the required check) comes only from runs against `main`. Exactly one
  completed run per PR head: a duplicate is acceptable only if cancelled before any step runs,
  with the kept run testing the current merge ref. Never skip, disable or weaken a gate; never
  re-run a failing job before explaining the failure, and at most once.
- Never store secrets in the repository; tell the maintainer what to set and where.

## 8. Quality standard

- No claim without evidence: a command and its output, or a CI run link.
- Every fix comes with a test that fails without it (show the failing run).
- Review your own diff adversarially before pushing; run every gate locally first.
- A test that fails only sometimes is a real bug: find the cause, fix it, add a guard for the whole
  category. Never re-run hoping it passes. If the cause isn't found quickly, revert first.
- Run local gates with exactly the dependency groups and Python version each CI job uses.
- Before pushing any change to startup, the shell, the splash, the tray, packaging or the build
  check, run the build job locally too (`uv run python tools/gates.py --jobs build`: PyInstaller
  build, Qt scan, launch check).
- Never guess on licensing, security or anything that changes the user's system. If the plan is
  wrong or impossible, explain it, propose a fix, and record the decision in `docs/decisions/`.
- Say plainly what you could not verify.

## 9. Reporting to the maintainer

At most five short lines in plain language: what changed, what is green (with links), and the
one question if you need a decision.

## 10. Only the maintainer

Real-machine tests (Windows PC, Linux VM, Roblox, Sober), money, legal questions, anything
irreversible, repository settings, and changes to the brand, names, licence or plan rules. Never
touch the hosts file, certificates or Roblox on any real machine yourself.

## 11. Everyday commands

```sh
uv run python tools/gates.py   # every gate, each CI job's own steps, groups and Python
uv run python tools/gates.py --jobs checks,tests,build --network   # everything CI runs
uv sync --locked                      # set up the environment
uv run ruff format --check . && uv run ruff check .
uv run pyright
uv run lint-imports                   # layering contracts
uv run python tools/licenses.py       # licence allowlist and Qt modules
uv run python tools/check_colors.py   # no colour literals outside tokens.json
uv run python tools/check_strings.py  # UI strings wrapped for translation
uv run python tools/check_spelling.py # US spelling in user-facing text
uv run python tools/check_docs.py     # module tree, provenance, spec tests
uv run pytest                         # QT_QPA_PLATFORM=offscreen on a headless machine
```

`.github/workflows/ci.yml` is the full list of gates.
