# 0012. What CI runs, and on which events

- **Status:** Accepted (revised in the third M0 review round, when the repository became public;
  the wording on skipped runs corrected on 3 October 2026)
- **Date:** 2026-10-02
- **Plan sections:** 12.1, 12.3, 13.2, 13.5, 16.2 ("CI runs on pull requests and on pushes to
  main only"; "M0 review round 3 decisions")

## Context

The first version of this record saved Actions minutes while the repository was private: only
pull requests into `main`, pushes to `main` and a stacked pull request labeled `ci:full` ran the
four-runner matrix and the build; every other pull request ran the static gates and Linux tests.
The free minutes ran out anyway, and the maintainer made the repository public (decision record
0013). Standard GitHub-hosted runners are free for public repositories, so the minutes are no
longer the limit; the queue is.

Two more things came up:

- **Two runs per pull request per push.** A push of the stack moves each pull request's branch
  and its base branch, and GitHub can send a `synchronize` event for each move, about a second
  apart. Measured on both pushes of 2 October 2026 (14:28 and 14:46 UTC), with run titles: nine
  of the eleven pull requests got two `synchronize` runs (for example #26: 37020067074 and
  37020067563); the concurrency group cancelled one of each pair before any step ran (checked
  job by job), and the run that was kept checked out the current merge ref (run 37020067312:
  `Merge 8e95c6a into 52ea15b`, the new base, the same commit as `refs/pull/19/merge`). Which of
  the two runs is kept was not consistent with their run IDs, so this record doesn't say which
  one GitHub keeps. The same pattern is reported for other stacked-PR workflows (git-spice issue
  966). An earlier reading blamed the `edited` trigger; the run titles showed it wasn't the
  cause.
- **The label step.** `ci:full` on the top pull request was a manual step that could be
  forgotten, and it only covered one pull request of the stack.

Queue estimate for one push of the M0 stack (eleven pull requests run CI; #13 to #15 come before
`ci.yml`) with every run full, from the job durations of run 36921511421 (1 October 2026): the
macOS jobs are the bottleneck, about 3.8 minutes per pull request (Tests on `macos-15` 0:53 and
`macos-15-intel` 2:54) and 7.3 on the top one, which adds the two macOS builds; about 45 macOS
job-minutes in all, 57 with the three M1 documentation pull requests. GitHub's documented limit
for the Free plan is 20 concurrent jobs, 5 of them on macOS, so a whole push should take about
10 to 15 minutes. The first push measures it.

## Decision

- **Every run is full**: the static gates with gitleaks, every test (slow ones included) on
  `windows-latest`, `macos-15`, `macos-15-intel` and `ubuntu-24.04`, the per-system, combined and
  changed-lines coverage floors, and (from the build pull request on) the PyInstaller build with
  the Qt-module scan and one start of the built app on all four runners. The `ci:full` label and
  the fast mode are gone.
- **Events**: pushes to `main`, and pull requests `opened`, `synchronize`, `reopened` and
  `edited`. An `edited` event starts a run only when the base branch changed to another branch
  (`changes.base.ref.from` differs from the current base); a moved base branch or an edited title
  or description goes to its own concurrency group, where the `Plan` job finds nothing to do and
  every other job is skipped. Each run's title names its event (`CI: synchronize on …`,
  `CI: edited (retarget) on …`).
- **One completed run per pull request head** (plan 16.2, "CI run rule for stacked pull
  requests"): one concurrency group per branch with `cancel-in-progress`. A duplicate
  `synchronize` run is acceptable only if the concurrency group cancels it before any step
  runs, and the kept run tests the current merge ref. The final job runs unless the run was
  cancelled (`!canceled()`), so a superseded run leaves no red check behind and a failed or
  skipped gate still turns it red. Its first step lists, in the job summary, any other
  completed and not cancelled run of this workflow for the same head commit (a retarget is
  marked as one); it reports and never fails.

**Checks.** The final job is named for what the run proves, from the event alone (never from
another job's output). GitHub evaluates a job's name only when the job runs: the check of a
skipped job shows the raw name expression from `ci.yml` (seen on the no-op runs for `fd36abf`,
2 October 2026). An earlier version of this record said no check shows a raw expression; that
was wrong.

| Run | Final check |
|---|---|
| A push to `main`, or a pull request into `main` (including a retarget to `main`) | **All gates green** (required by branch protection) |
| A stacked pull request | **Full gates green (stacked)** |
| An edit that isn't a retarget | The final job is skipped; its check shows the raw name expression |

A stacked run checks the commit against its own base, not against `main`, so it doesn't report
the required check (review finding F9). A no-op run must not report the required check either:
GitHub counts a skipped required check as passed, so a skipped "All gates green" after a failed
real run would let the pull request merge. Because a no-op run's check carries the raw
expression, never "All gates green", the real run's "All gates green" (passed or failed) stays the only check of that name on the
head commit: a no-op run can neither pass nor block it. `tests/test_ci_plan.py` runs the
`Plan` job's script and evaluates the final job's name, the run title and the concurrency group
for each case, and checks that the final job is skipped for exactly the events its name calls
"No-op (edited)" (what the name would read if GitHub ever evaluated it for a skipped job).

**Public repository.** `permissions: {}` at the top of every workflow, and each job asks for
what it needs (read access only, except the nightly benchmark job, which may open an issue and
never runs pull request code). No `pull_request_target` or `workflow_run` trigger, secrets only
in the release environment, every action pinned to a commit SHA, no checkout that keeps the
token. `tests/test_workflows.py` checks all of this.

No gate is removed or weakened.

## Consequences

- Before anything merges into `main`, the full matrix has passed on the exact commit: only a run
  against `main` reports the required check. When a lower pull request merges and the next one
  is retargeted to `main`, the retarget starts a new full run against `main`; until it is
  green, the pull request can't merge.
- Every pull request in a stack shows the full matrix, so a failure on one runner is found on
  the pull request that causes it.
- If the queue turns out too slow, the simplest fallback that keeps the guarantee above is to run
  the matrix only on runs against `main` and on the top of the stack; that would need a new
  revision of this record.
