# Contributing to Verdra

Thank you for helping. Verdra is built from written specs, so most changes start in
`docs/specs/`, and every change goes through a pull request.

## Clean-room rule

Verdra is written from scratch. You may use the *ideas* of earlier tools and the feature list in
our specs. You must not open, copy, paste or translate any source file, comment, UI text, test,
icon or other bundled file of another asset-replacement tool, and you must not work on Verdra in a
folder or session where such code is present. Inputs you may use: the specs in `docs/specs/`,
Roblox's observable behaviour captured with Verdra's own tools, public format documentation, and
the libraries listed in the licence allowlist. Record what each new module was built from in
`docs/provenance.md`.

## Developer Certificate of Origin

Every commit must be signed off under the [Developer Certificate of Origin 1.1](https://developercertificate.org/):

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

Sign off by committing with `git commit -s`, which adds a line such as:

```
Signed-off-by: Your Name <you@example.com>
```

## Setting up

You need Python 3.14 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pre-commit install
uv run pytest
```

## Conventions

- **Branches:** `spec/S-11-proxy-core`, `fix/<topic>`, `chore/<topic>`, `docs/<topic>`.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`,
  `docs:`, `test:`, `refactor:`, `build:`, `ci:`, `chore:`) with a `Signed-off-by:` trailer.
- **Code style:** `ruff format` (line length 100, double quotes); type hints on every function;
  Google-style docstrings; English identifiers using the nature vocabulary in
  `docs/glossary.md`.
- **File headers:** every source file starts with

  ```
  # SPDX-FileCopyrightText: 2026 The Verdra Authors
  # SPDX-License-Identifier: Apache-2.0
  ```

- **Colours:** colour values live only in `src/verdra/assets/brand/tokens.json`. Code reads
  tokens by name; a hex colour anywhere else is a defect.
- **Text:** every user-facing string goes through Qt's translation functions and follows the
  voice rules in the Master Build Plan (sentence case, "you", no "please", "oops" or emoji).
- **Decisions:** one short record per architecture decision in `docs/decisions/`.

## Definition of done

A pull request is ready to merge when:

1. It links to its spec, and the spec's acceptance tests are added or updated.
2. All CI gates are green on Windows, macOS and Linux.
3. New modules have a provenance entry.
4. User-facing text follows the voice rules and is in the message catalogue.
5. `CHANGELOG.md` has an entry under "Unreleased".
6. There is no TODO without an issue link.

## Reporting security issues

Don't open a public issue. Follow [SECURITY.md](SECURITY.md).

## Code of conduct

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).
