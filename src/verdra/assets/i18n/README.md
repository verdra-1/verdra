# Message catalogue

`verdra_en.ts` holds every sentence Verdra shows (Reference R5), each under its context: a message
ID such as `M-SET-01`, or the screen it belongs to. It is generated from the source with
`uv run python tools/i18n.py` and CI fails when it's out of date. Compiled `.qm` files are built
at release time and aren't committed. 1.0 ships English only (Master plan 6.7).
