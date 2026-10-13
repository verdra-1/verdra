# 0026. No public release before 1.0.0; the release workflow is a dry run

- **Status:** Accepted (owner, 13 October 2026; plan 16.2)
- **Date:** 2026-10-13
- **Plan sections:** 13.5, 14 (M2, M7, M8), 16.2; amends decision record 0025

## Context

Decision record 0025 built a workflow that published a tag `vX.Y.Z` to GitHub Releases as a
pre-release, and asked the owner whether 0.1.0 could be tagged and published. On 13 October 2026
the owner answered no: there is no public release before 1.0.0.

## Decision

- **No tags, no releases.** No version tag is pushed and no GitHub release, pre-release or draft
  release is created until the owner approves 1.0.0. On 13 October 2026 the repository had no
  tag and no release (`git ls-remote --tags origin` and the releases API both returned none).
- **The release workflow is a dry run.** `.github/workflows/release.yml` ("Release dry run")
  starts only by hand (`workflow_dispatch`), has one job with `contents: read`, builds the app,
  packs `Verdra-X.Y.Z-windows.zip` exactly as a user would get it, checks that exact ZIP (decision
  record 0025's checks are unchanged), writes its SHA-256 into the run summary and keeps the ZIP
  as a workflow artifact for 5 days. The tag trigger, the publish job, the `release`
  environment and every write permission are gone.
- **A guard in CI.** `tests/test_workflows.py::test_no_workflow_can_publish_before_1_0` fails
  if any workflow has a tag or release trigger, a write permission other than `issues: write`
  (nightly's failure reports), `gh release`, a call to the releases API, `git tag` or
  `git push`, or a release action. Turning publishing on for 1.0.0 needs a change to that test,
  so it can only happen in a reviewed, owner-approved pull request (spec S-80).
- **0.1.0 is an internal milestone label**: "M2 complete". `docs/releases/0.1.0.md` holds the
  internal milestone notes. The version string in `pyproject.toml` may be raised to 0.1.0 when
  M2's real-machine tests pass; no tag goes with it.
- **No outside testers before the beta milestone (M7).** Whether the beta is private is decided
  then. Real-machine tests keep using the source run (`tools/run-latest.ps1`, decision record
  0021) and short-lived CI builds (the test build of decision record 0019, and this dry run).
- **The repository stays public.** Visible code is not a published release. Workflow artifacts
  of a public repository can be downloaded by anyone signed in to GitHub who finds the run; they
  aren't advertised, expire after 5 (dry run) or 30 (test build) days, and say in their READ-ME
  what they are.

## Consequences

- The README, CHANGELOG, docs and the app claim no release and offer no download; the README
  says to build from source.
- The third-party notices stay in every build (decision record 0025). The exact addresses of
  Qt's published sources, which the notices name, were not reachable from the session that wrote
  them; they are checked before 1.0 (see `docs/m2/exit-gate.md`, "Not verified").
- At 1.0.0: a new decision record turns publishing on (with spec S-80: installer, signing, SBOM,
  provenance), and the guard test changes with it.
