# Fonts

Bundled under the SIL Open Font License 1.1. Each font's licence text sits next to it and ships
with the app (Master plan 3.4). The fonts are not sold on their own.

| File | Family, weight | Role | Source |
| --- | --- | --- | --- |
| `AtkinsonHyperlegibleNext-Regular.ttf` | Atkinson Hyperlegible Next 400 | `sans` | googlefonts/atkinson-hyperlegible-next @ 7925f50f, `fonts/ttf/` |
| `AtkinsonHyperlegibleNext-SemiBold.ttf` | Atkinson Hyperlegible Next 600 | `sans` | same |
| `JetBrainsMono-Regular.ttf` | JetBrains Mono 400 | `mono` | JetBrains/JetBrainsMono @ 19371302, `fonts/ttf/` |
| `Sora-SemiBold.ttf` | Sora 600 | `display` (stand-in) | sora-xor/sora-font @ 7f9a9c5d, `fonts/ttf/` |

Sora is the stand-in display face until the brand's custom face is licensed (Master plan 4.4).
When it arrives, add its files and licence here, point `type.fonts` and `type.families.display`
in `../brand/tokens.json` at it, and regenerate the wordmark with `tools/icons.py`.
