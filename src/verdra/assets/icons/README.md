# Icons

- `lucide/`: a subset of [Lucide](https://lucide.dev) icons, unmodified, from
  lucide-icons/lucide @ 5a92b9ba, under the ISC licence in `LUCIDE-LICENSE.txt` (shipped with the
  app, Master plan 3.4).
- `custom/`: Verdra's own icons, drawn on the same 24-unit grid with a 2 px round stroke (plan
  6.8): `graft` (Replacements), `seed` (Library), `tweaks` (sprout over a slider, Tweaks). They're
  concepts until the designer refinement before 1.0.

Every icon uses `currentColor`; `canopy/crown/theme.py` recolours it from a token at runtime, so
no icon file carries a colour.
