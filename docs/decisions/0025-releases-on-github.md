# 0025. Releases: built by CI from a tag, published to GitHub Releases in this repository

- **Status:** Accepted (owner, 12 October 2026), amended by [0026](0026-no-public-release-before-1-0.md):
  no public release before 1.0.0; the workflow is a dry run, its tag trigger and publish job are
  gone, and the build, ZIP and check steps and the third-party notices below stay as they are
- **Date:** 2026-10-12
- **Plan sections:** 3.2, 13.5, 13.6, 14 (M2 exit gate), 16.2; decision records 0002, 0015,
  0019, 0021

## Context

Decision record 0021 left open how releases are distributed, to be settled before 0.1.0. The M2
exit gate asks for 0.1.0 tagged for the owner and invited testers. The owner chose, on
12 October 2026, CI builds from a tag and publishes to GitHub Releases in this repository, with
the third-party licence texts and NOTICE, and the frozen build checked to exclude the diagnostic
flags (decision record 0015). Until now `release.yml` was a stub that only ran `uv build`, and
the build carried LICENSE, NOTICE and PRIVACY.md but no third-party notices: the About dialog's
"Third-party notices" button was disabled (M-ABOUT-03).

## Decision

- **Trigger.** A tag `vX.Y.Z` runs `.github/workflows/release.yml` on `windows-latest`. The tag
  must match the version in `pyproject.toml`, and `docs/releases/X.Y.Z.md` (the release notes)
  must exist, or nothing is built. Started by hand (`workflow_dispatch`), the same workflow
  builds and checks the ZIP and keeps it as an artifact for 30 days, without publishing: a dry
  run of the exact release steps.
- **Build and check.** The same PyInstaller setup as CI's build job and the test build
  (`packaging/verdra.spec`). `tools/pack_test_build.py --release X.Y.Z` packs
  `Verdra-X.Y.Z-windows.zip`: one `Verdra` folder with `verdra.exe` and a READ-ME for that
  version (unsigned and SmartScreen, start, update, undo, privacy, where to ask). That exact ZIP
  is unpacked into an empty folder and `tools/check_build.py --launch` runs on it: only the
  allowed Qt modules, LICENSE, NOTICE and PRIVACY.md byte for byte, the third-party notices
  present, the native modules present, `roots/litmus` absent, `--diagnose-interception` refused
  by the built app (decision record 0015), and one start of the app. `SHA256SUMS` is written
  for the ZIP.
- **Publish.** A second job, in the `release` environment and the only one with
  `contents: write`, runs only for a tag. It creates the GitHub release for the existing tag
  (`gh release create --verify-tag`), marked as a pre-release (versions before 1.0 are previews,
  plan 14), titled "Verdra X.Y.Z", with the notes file as its text and the ZIP and `SHA256SUMS`
  attached. Nothing is pushed to the repository.
- **Third-party notices.** `tools/third_party.py` writes `THIRD_PARTY_NOTICES.md` during every
  PyInstaller build (so CI's build job checks it on every pull request, not only at release
  time) into `assets/legal/`, where the About dialog shows it. It lists every runtime package of
  the lockfile for Windows with its licence expression and the full text of every licence file
  its installed metadata carries. Qt for Python's wheels carry no licence file; as decision
  record 0002 requires, their entries say Qt is used under LGPL-3.0, that the Qt libraries are
  separate replaceable files, and where the Qt and Qt for Python sources are published, and the
  file ends with the full LGPL-3.0 and GPL-3.0 texts (`packaging/licenses/`, the Free Software
  Foundation's texts of 29 June 2007, checked by SHA-256 in `tests/tools/test_third_party.py`).
  Any other package without a licence text stops the build. The build check fails a build
  without the file or without the LGPL-3.0 text.
- **Version.** The version in `pyproject.toml` is raised to the release's version, with its
  CHANGELOG section, in a pull request just before the tag; the tag is pushed only after the
  owner says yes.

## Consequences

- One yes from the owner and one tag make a release; no release step runs on a computer.
- The repository is public, so a GitHub release is visible to anyone with the link, although
  0.1.0 is meant for the owner and invited testers (plan 14). It is marked as a pre-release and
  isn't advertised; the README says Verdra is in early development.
- The ZIP isn't signed until SignPath (M7), so Windows SmartScreen warns on first start; the
  READ-ME and the release notes say how to continue.
- Not yet in a release (spec S-80, M8): installer, signing, CycloneDX SBOM, provenance
  attestations, update notice.
- Not verified by this record: the notices name where Qt's sources are published
  (download.qt.io); those addresses weren't reachable from the session that wrote this record.
  Qt's own bundled third-party components (listed in Qt's documentation, not in the wheels) are
  not listed separately; whether the release needs them is a licensing question for the owner
  and the lawyer review of plan section 3 (M8).
