# mega — Marx-Engels-Gesamtausgabe

One register, the persons: profile `mega`.

`extract_mega_person()`; schema override in `projects/mega/__init__.py`. Alternate
`<persName type="alt">` names are sorted by `@subtype` into `alt_names` /
`birth_names` / `pseudonyms` (shared with `schleiermacher` via `_alt_names()`).
`mega_id` collects the register's own (non-unique, occasionally repeated)
`idno[@type='mega']` numbers; `gnd` / `viaf` / `idno_other` come from
`idno[@type='uri']` only — the register number above is not a URI. `old_id`
carries the pre-migration id (`pdrPo.…` / `ed_…`). `role` flags non-historical
persons (`mythological`/`fictional`); `sex` adds `intersex` to the usual
`female`/`male`/`unknown`.
