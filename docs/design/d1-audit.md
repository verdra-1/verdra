# D1 audit: today's app against the design laws (19 October 2026)

Made with `tools/gallery.py` (D1): every screen, dialog and status of today's app on main
(d45e08f), offscreen, at text scale 100, 115, 150 and 200 %, light and dark, the smallest window
(1000 × 640) and the default (1200 × 760), and the pseudo-language of law 1 at 115 %. That is
440 screenshots. The law 1 check measured every visible widget in them: **532 findings break law
1** (226 buttons, 88 table headers, 70 combo boxes, 64 wrapped labels, 42 labels, 42
placeholders), and 1,137 table cells are shortened, which law 2 allows only for paths, links,
asset names and log messages.

Screenshot names below are `<configuration>/<number>-<scene>.png`, as in the CI artifact
"design-gallery-windows-latest" (the gallery step of the Tests job). The numbers in this audit
come from a local run on Linux. Windows uses its own font rendering, so a few pixels differ; the
CI artifact is the reference.

Nothing here is redesigned. D2's mock-ups answer these points; D3 builds them.

## Severity

- **Blocker:** the user can't read or use something.
- **Major:** law 1 or 2 is broken where a user will see it, or the wording is wrong.
- **Minor:** inconsistent, untidy, or technical.

## Blockers

1. **Dialogs of fixed width break at larger text.** The "Roblox is already running without
   Verdra" choice cuts its title, its body and all three buttons ("tinue any", "blox and") from
   115 %. Every dialog built on the shared dialog has a fixed width (460 px), so the same happens
   with "How to close Roblox completely", the Moderation-risk warning and the explanation
   dialogs at 200 %. *light-200/41-choice-roblox-running.png, light-115/42-information-close-roblox.png,
   light-200/43-risk-warning.png.*
2. **The status popover cuts its own message.** The popover is 300 px wide with a fixed height
   for the text. At every scale the Degraded (f) message loses its first and last lines;
   "Roblox is already running…" and the Error message too, from 115 %. *light-100/32-status-no-asset-requests.png,
   light-150/31-status-other-roblox.png, light-150/33-status-error.png.*
3. **Paths lose their file names.** In Replacements, "Replace with" shows `C:…` for a local
   file, and the end of a link is cut ("https://example.com/…"). That is the part a user needs,
   and it breaks law 2 (shorten in the middle, keep the file name). The note column does the
   same to "The file for this replacement is missing: …". *light-115/15-replacements-default.png.*
4. **At 200 % the window can't show its own title or navigation.** "Replacements" becomes
   "Replaceme" in the header and "Repl…ents" in the sidebar, the profile list cuts "My
   replacements", the profile box shows "My replacei", and the editor's buttons squeeze.
   Settings only offers 90 to 130 % today, so 150 % and 200 % are reached by Windows scaling and
   by law 1's test, not by a choice in Verdra. *dark-200/01-replacements-minimum.png, dark-200/02-replacements-editor-minimum.png.*

## Major

5. **Table headers are narrower than their titles.** "Replace with" at every scale, and
   "Original", "Kind" and "Note" from 150 %. *light-100/02-replacements-editor-minimum.png.*
6. **Placeholder "New profile name" is cut at every scale** in the smallest window
   ("New profile n…"). *light-100/01-replacements-minimum.png.*
7. **Asset IDs are cut** ("155532…") from 150 % in the smallest window. An ID is not free-length
   data and must never shorten. *dark-200/01-replacements-minimum.png.*
8. **Activity cuts every long message at the right** and has no detail pane. Law 2 asks for
   wrapping or a pane with the full message. *dark-115/21-activity-default.png.*
9. **Technical words in the window:** the status says "Idle", "Routing", "Degraded" and "Error"
   (decision 3: Working · Waiting for the game · Needs you · Stopped · Off); Settings says "How
   Roblox is routed", "Local port" and "Per app". *light-115/22-settings-default.png, light-100/29-status-idle.png.*
10. **The About dialog:** the wordmark still has its node dot (decision 8). The NOTICE text sits
    in a heavy outlined box with hard line breaks. "Third-party notices" is disabled in a source
    run with no explanation (it has a file only in the built app). At 150 % and above its
    buttons squeeze. *light-115/34-about.png, light-200/34-about.png.*
11. **Settings offers things that aren't built:** "Check for updates" and "Update channel" are
    switches and choices with no feature behind them (PRIVACY.md describes them too, see the M2
    final test). *light-115/22-settings-default.png.*
12. **Onboarding:** the wordmark with its dot, a large empty area under the welcome text, and
    only one "Get started" button at the bottom right. *light-115/37-onboarding.png.*
13. **Pseudo-language:** almost every button, tab, header and label is cut, including the
    sidebar ("Répláçé…çéméñts"), the toolbar and the Settings group titles. Translations into
    longer languages would break the window today. *dark-115-pseudo/15-replacements-default.png.*
14. **No contrast-theme support.** Verdra draws its own colors and ignores Windows contrast
    themes; CI can't switch one on without changing the runner's settings, so the gallery has no
    contrast screenshots. Design law: map to Window, WindowText, Hotlight, Highlight and
    GrayText.

15. **Library promises what isn't built.** Its empty state says "Your library is empty. Launch
    Roblox through Verdra and assets will appear here as they load." with a disabled "Launch
    Roblox" button. Library isn't built (M3), so no asset ever appears there. An unbuilt screen
    shows M-SOON-01 (CLAUDE.md, section 6). *light-115/18-library-default.png.*

## Minor

16. **Two rows of toolbar buttons** in Replacements (Add replacement, Remove / Undo, Redo,
    Preview changes) with no grouping. Remove sits next to Add and looks the same as the others.
    *light-115/15-replacements-default.png.*
17. **"Profile options" menu:** its arrow sits under the text, away from it, and it looks unlike
    any other control. *light-115/15-replacements-default.png.*
18. **Activity writes a dialog as title and body run together** with no separator ("Roblox is
    already running without Verdra If Verdra starts this game…"). *dark-115/21-activity-default.png.*
19. **"Reset to defaults" in Settings is a link at the right**, while every other action is a
    button. *light-115/22-settings-default.png.*
20. **The status pill and the profile box in the header look disabled** (gray) in light mode
    while they work. *light-115/15-replacements-default.png.*
21. **Settings' switches carry a leaf glyph** that is hard to see at 100 % and reads as a
    checkmark. *light-115/22-settings-default.png.*
22. **The editor drawer's buttons for the kind of replacement** (Asset ID, Local file, URL,
    Remove) look like actions, not a choice of one; "Remove" there means "make it disappear",
    while the toolbar's "Remove" deletes a row. Same word, two jobs. *light-100/02-replacements-editor-minimum.png.*
23. **The empty screens sit inside a heavy green outline** that looks like a focus ring
    (Library, Tweaks, Accounts), with a small icon and one sentence in a large blank page. The
    design laws ask for drawn empty states. *light-115/19-tweaks-default.png, light-115/20-accounts-default.png.*
## What the gallery doesn't cover yet

- The tray menu and Windows notifications: they are not app windows and offscreen rendering
  can't show them.
- The first-run flow beyond its first page, the editor with each kind of target filled in, and
  the Preview changes dialog (it needs a running proxy).
- Phase A's screens (the new table, review dialog), which live on their branches until M2 passes.
- Contrast themes (point 14).

## The law 1 check

`tools/gallery.py` runs in CI's Tests job on Windows, **report only**: today's app fails it (the
532 findings above), so failing the build now would block every pull request until D3. Its
report is `law1.md` and `law1.json` in the artifact, next to the screenshots. When D3 has fixed
the findings, the step gets `--strict` and fails on any new one. The check itself is tested in
`tests/tools/test_gallery.py`.
