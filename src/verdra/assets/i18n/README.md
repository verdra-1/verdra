# Message catalogue

`verdra_en.ts` holds every sentence Verdra shows (Reference R5), each under its context: a message
ID such as `M-SET-01`, or the screen it belongs to. It is generated from the source with
`uv run python tools/i18n.py` and CI fails when it's out of date. The same command compiles
`verdra_en.qm`, which is committed (Reference R1) and loaded at startup; it carries the English
plural forms ("1 replacement", "2 replacements"), which the catalogue gives for each message
with a count. 1.0 ships English only (Master plan 6.7).
