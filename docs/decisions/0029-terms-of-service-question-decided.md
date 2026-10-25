# 0029. Terms of service question, decided

- **Status:** Accepted
- **Date:** 2026-10-23
- **Plan sections:** 3 (legal foundations), 16.2 (legal questions are the owner's); the plan's
  change log, entries of 23 October 2026

## Context

Decision record 0028 paused option A (writing replacements into Roblox's saved assets) on
23 October 2026. The pause waited for the owner's legal review of one question: whether writing
into the Player's local asset cache is allowed under Roblox's terms of service.

## The legal opinion

The owner's summary, as the plan's change log records it ("Legal review returned favourable;
Option A proceeds", 23 October 2026):

> The owner obtained a legal opinion covering German/EU and US/California law. Bottom line:
> building, distributing and using Verdra with Option A is lawful on every statutory theory
> examined — copyright, anti-circumvention, computer misuse, trademark. The 21 October pinning
> does not change the analysis, because Option A avoids rather than circumvents the measure, so
> anti-circumvention law is not engaged. The only soft spot is the end user's contract with
> Roblox: Option A is probably outside the express words of Roblox's Terms, so a user's use is a
> breach whose only remedy is account termination; Verdra and its maker are not parties and are
> in breach of nothing. Recommendation: proceed.

**The lawyer's own paragraph: not to hand.** The opinion itself is not in the repository or the
plan. Only the owner's summary above is. When the owner supplies the lawyer's paragraph, it goes
here verbatim.

The caveat stays as the summary states it: this is not "no risk". The risk that a user's Roblox
account is terminated is real, and it falls on the user.

## Decision

The terms question is decided in favor of proceeding with option A. The opinion is the basis;
option A itself resumes by decision record 0030.

## Reasoning

The opinion finds no statutory obstacle to building, distributing or using Verdra with option A.
It also finds that the certificate check Roblox added (0028) is avoided rather than circumvented,
so anti-circumvention law isn't engaged. The one risk it names lies in the user's own contract
with Roblox. Verdra isn't a party to that contract, so the remedy is to tell the user plainly
before they use Verdra, so their use is an informed choice.

## Consequences

- **A new product requirement:** a prominent, plain-language notice that using Verdra may breach
  Roblox's Terms of Service and could lead to Roblox suspending or terminating the user's account,
  and that the user uses Verdra at their own risk. It appears in the app and in the README and
  docs. Its screens, timing and one-time acknowledgement are set out in spec S-29.
- The lawyer review before the first public release (plan 3, the M8 checklist) still applies.
