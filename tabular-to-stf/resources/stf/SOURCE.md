# Source of the bundled STF documentation

`Study-Transfer-Format-STF.md` and `metadata-fields.md` are unmodified copies
of `STF_documentation/` in the study-wrangler repository
(https://github.com/VEuPathDB/study-wrangler) at tag `v1.0.56`, bundled on
2026-11-05:

```bash
git -C <study-wrangler checkout> show v1.0.56:STF_documentation/Study-Transfer-Format-STF.md
git -C <study-wrangler checkout> show v1.0.56:STF_documentation/metadata-fields.md
```

The tag matches the pinned container image, `STUDY_WRANGLER_VERSION` in
`scripts/_container.py`. Whenever that
constant moves, re-bundle both files from the new tag and update this file.
`tests/test_docs.py` fails until they agree.

Do not edit the copies here. Fix the documentation upstream and re-bundle.
