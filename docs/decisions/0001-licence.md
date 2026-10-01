# 0001. Apache License 2.0 with a NOTICE file

- **Status:** Accepted
- **Date:** 2026-10-01
- **Plan sections:** 3.2, 3.3

## Context

Verdra is an independent, clean-room project. We want anyone to be able to use, study and modify
it, while making sure that every redistributed or modified copy points back to the original
project and keeps our copyright notices. We also want an explicit patent grant and no claim on
the name or logo.

## Decision

Verdra is licensed under the Apache License 2.0. The repository carries:

- `LICENSE`: the unmodified Apache-2.0 text from apache.org;
- `NOTICE`, with the original project's address, exactly as plan section 3.2 gives it;
- an SPDX header on every source file:
  `SPDX-FileCopyrightText: 2026 The Verdra Authors` and `SPDX-License-Identifier: Apache-2.0`.

The README footer and the About dialog show the NOTICE text with a clickable link. The courtesy
credit to Fleasion (3.3) is a courtesy, not a licence requirement.

## Consequences

- Section 4(d) makes the NOTICE travel with every fork, so the link to the original does too.
- Section 4(b) requires modified files to say they were changed; section 4(c) keeps our notices.
- Section 6 grants no right to the name "Verdra" or the logo beyond describing where a fork came
  from.
- Dependencies must be compatible with Apache-2.0 distribution; the licence allowlist (plan 12.3)
  enforces this in CI.
