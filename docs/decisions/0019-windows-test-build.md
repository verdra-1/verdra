# 0019. A Windows test build the owner can download, as a workflow artifact

- **Status:** Accepted
- **Date:** 2026-10-07
- **Plan sections:** 13.5, 13.6, 16.2 ("Next steps", item 2, 7 October 2026), Reference R3

## Context

Until now the owner ran Verdra from source: download the repository as a ZIP, then PowerShell
and uv. After the first texture swap worked (7 October 2026), the plan asks for a portable test
build the owner can unzip and double-click, built by CI and downloaded from the workflow run,
with no public release and no installer.

## Decision

- `.github/workflows/test-build.yml` runs on every push to `main` and by hand
  (`workflow_dispatch`), never on pull requests, with read access only.
- It builds with the same PyInstaller setup as CI's build job (`packaging/verdra.spec`), packs
  `Verdra-windows-test.zip` with `tools/pack_test_build.py` (one `Verdra` folder holding
  `verdra.exe` (Reference R3), what PyInstaller put next to it, and `READ-ME.txt`), then unpacks
  that exact ZIP into an empty folder and runs `tools/check_build.py --launch` on it (Qt
  allowlist, legal texts, no diagnostic interception, one start of the app).
- The ZIP is uploaded as the run's only artifact, not zipped again (`archive: false` in
  upload-artifact v7), and kept for 30 days. There is no release, tag, installer or package.
- The build isn't signed (signing waits for SignPath at M7, plan 16.3), so Windows SmartScreen
  shows "Windows protected your PC" the first time; `READ-ME.txt` and the owner's guide say
  so and how to continue.

## Consequences

- The owner's test guides use the test build instead of PowerShell and uv.
- The repository is public, so anyone signed in to GitHub can download a workflow artifact. It
  isn't advertised anywhere; it is a test build, says so, and expires after 30 days.
- Settings and profiles live in `%LOCALAPPDATA%\Verdra`, outside the unzipped folder, so a newer
  test build replaces an older one by deleting the folder and unzipping the new ZIP.
- The CI build job keeps checking every pull request; this workflow adds the check of the ZIP
  the owner actually downloads.
