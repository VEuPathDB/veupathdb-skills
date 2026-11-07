# tabular-to-stf Regex Transforms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in regex matching (with `$n` capture references) to three curation-spec transforms, a `stf.py preview` sub-command that shows what one transform does, semver `specVersion`, and the skill docs that route regex transforms through preview and user approval.

**Architecture:** A new pure module `_match.py` owns replacement templates and a `ValueMatcher` (exact or regex, whole-cell). `_spec.py` validates `match`, patterns and templates, and the new semver version. `_transforms.py` uses `ValueMatcher` for `map-values`, `derive-column` and `blank-placeholders`, fails on ambiguous cells, and gains `upto`/`entity` options so a new `_preview.py` can run the transforms before index `n` and evaluate transform `n`. `stf.py` gets the `preview` sub-command.

**Tech Stack:** Python ≥3.11, stdlib `re`, pytest; run with uv.

**Spec:** `docs/superpowers/specs/2026-11-06-tabular-to-stf-regex-transforms-design.md`

## Global Constraints

- All paths below are relative to `tabular-to-stf/` unless they start with `docs/`.
- Test command (from `tabular-to-stf/`): `uv run --with pytest --with "ruamel.yaml>=0.18,<0.20" python -m pytest tests -q`. The whole suite must pass at the end of every task.
- `SPEC_VERSION = "1.1.0"`, defined once, in `scripts/_spec.py`.
- Version strings match `(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)` (full match).
- `match` is `"exact"` (default) or `"regex"`, allowed only on `map-values`, `derive-column`, `blank-placeholders`.
- Regex syntax is Python `re`; a pattern matches with `fullmatch` (whole cell).
- Replacement templates (regex mode only): `$` + one or more digits is a group reference (all following digits: `$10` is group 10); `$$` is a literal `$`; any other `$` (including a trailing one) is an error; a group that did not take part gives `""`. Substitution is done by our own code from `match.group(n)`; never pass a user string to `re.sub`/`Match.expand` (so backslashes in replacements stay literal).
- In exact mode, map values are literal (`$1` means the two characters `$1`).
- Ambiguous = a cell matched by two or more keys whose results differ. Same results are not ambiguous.
- Regex transforms may never be `approval: "auto"`.
- A spec that uses `match` must say `specVersion` `"1.1.0"` (Task 3 refuses it on `1.0.0`), so tests that validate or render such a spec set that version; the existing helpers stay at `"1.0.0"`.
- No new dependencies.
- Commits: end messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.

## Review Focus

1. **Partial match** — `\d+` against `40?` must not match (whole-cell rule); alternation `a|ab` against `ab` matches as a whole. Test in Task 2.
2. **Backslashes in a replacement** — `"x\\1"` (JSON for `x\1`) yields the literal text `x\1`, not group 1. Test in Task 2.
3. **Exact mode with `$` in a value** — `{"80+": "$80"}` gives `$80`, and the validator accepts it. Tests in Tasks 2 and 3.
4. **Preview after an earlier rename** — previewing a `map-values` on a column renamed by an earlier `user`/`auto` transform works under the new name, and an earlier `proposed` transform is not applied. Test in Task 5.
5. **Empty cells** — in regex mode, empty cells go through matching like any value (`.*` matches them); in the preview, unmatched empties are counted, not listed. Tests in Tasks 4 and 5.

---

### Task 1: Semver `specVersion`

**Files:**
- Modify: `scripts/_spec.py` (constant; `validate_spec` around line 271)
- Modify: `tests/test_spec.py` (`minimal_spec`, replace `test_spec_version_rejects_bool_and_other_values`)
- Modify: `tests/test_render.py:21`, `tests/test_scale.py:75` (`"specVersion": 1` → `"1.0.0"`)
- Modify: `tests/fixtures/tabular/*/spec.json` and `tests/fixtures/tabular/*/expected/curation-spec.json` (three datasets; change only the value, keep formatting byte-identical otherwise)
- Modify: `resources/curation-spec.md` (schema example; new "Spec version" section)
- Test: `tests/test_docs.py`

**Interfaces:**
- Produces: `_spec.SPEC_VERSION: str = "1.1.0"`; `_spec.parse_version(v: Any) -> tuple[int, int, int] | None` (None for anything that is not a version string).

- [ ] **Step 1: Write the failing tests** in `tests/test_spec.py` (set `minimal_spec()`'s version to `"1.0.0"`):

```python
from _spec import SPEC_VERSION, parse_version, validate_spec

def test_spec_version_accepts_any_1x_up_to_the_code_version():
    for v in ("1.0.0", "1.0.5", SPEC_VERSION):
        s = minimal_spec(); s["specVersion"] = v
        assert validate_spec(s) == [], v

@pytest.mark.parametrize("bad", [1, 1.0, True, None, "1", "1.0", "01.0.0", "1.0.0-rc1", " 1.0.0"])
def test_spec_version_must_be_a_version_string(bad):
    s = minimal_spec(); s["specVersion"] = bad
    assert 'specVersion: must be a version string like "1.1.0"' in validate_spec(s)

def test_spec_version_newer_than_the_code_is_refused():
    s = minimal_spec(); s["specVersion"] = "1.2.0"
    assert "specVersion: this spec needs 1.2.0, these scripts support up to 1.1.0" in validate_spec(s)

def test_spec_version_with_another_major_is_refused():
    for v in ("2.0.0", "0.9.0"):
        s = minimal_spec(); s["specVersion"] = v
        assert any_match(validate_spec(s), rf"specVersion: major version {v[0]} is not supported \(these scripts support 1\.x, up to 1\.1\.0\)")

def test_parse_version():
    assert parse_version("1.10.0") == (1, 10, 0)
    assert parse_version(1) is None
```

And in `tests/test_docs.py`:

```python
from _spec import SPEC_VERSION

def test_curation_spec_md_schema_shows_the_current_spec_version():
    assert f'"specVersion": "{SPEC_VERSION}"' in read("resources/curation-spec.md")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --with pytest --with "ruamel.yaml>=0.18,<0.20" python -m pytest tests/test_spec.py tests/test_docs.py -q`
Expected: FAIL (ImportError on `SPEC_VERSION`).

- [ ] **Step 3: Implement** `SPEC_VERSION`, `parse_version` and the new check in `validate_spec`, with exactly the three messages above (comparison is tuple order; newer means `parse_version(v) > parse_version(SPEC_VERSION)`).

- [ ] **Step 4: Update fixtures and test helpers** to `"1.0.0"` (`grep -rln '"specVersion": 1' tests`), and `resources/curation-spec.md`: schema example `"specVersion": "1.1.0"`, plus a short `## Spec version` section stating: semver string; the scripts read any spec with the same major version and a version no newer than theirs; minor adds ops or fields, patch clarifies without changing behaviour, major removes or changes meaning; write new specs with the version the scripts support (the one in the schema above).

- [ ] **Step 5: Run the whole suite** — Expected: all pass (golden tests included).

- [ ] **Step 6: Commit**

```bash
git add tabular-to-stf
git commit -m "tabular-to-stf: semver specVersion (1.1.0); retrofit fixtures to 1.0.0"
```

---

### Task 2: `_match.py` — templates and `ValueMatcher`

**Files:**
- Create: `scripts/_match.py`
- Test: `tests/test_match.py`

**Interfaces:**
- Produces:
  - `class TemplateError(ValueError)`
  - `parse_template(s: str) -> list[str | int]` — literal chunks and group numbers; raises `TemplateError('"$" must be followed by a group number or "$"')`.
  - `template_groups(parts: list[str | int]) -> set[int]`
  - `expand(parts: list[str | int], m: re.Match) -> str`
  - `class ValueMatcher:`
    - `__init__(self, mapping: dict[str, str], regex: bool)` — patterns compiled once, templates parsed once (exact mode: values literal, no parsing). Assumes a validated spec.
    - `hits(self, cell: str) -> list[tuple[str, str]]` — `(key, result)` for every key matching `cell`, in map order.
    - `@staticmethod is_ambiguous(hits) -> bool` — distinct results > 1.

- [ ] **Step 1: Write the failing tests** in `tests/test_match.py`:

```python
import pytest
from _match import TemplateError, ValueMatcher, parse_template, template_groups

def test_parse_template_groups_dollar_dollar_and_multidigit():
    assert parse_template("a$1b$$c$10") == ["a", 1, "b$c", 10]
    assert template_groups(parse_template("$2-$1")) == {1, 2}

@pytest.mark.parametrize("bad", ["$", "x$", "$a", "$-1"])
def test_parse_template_rejects_stray_dollar(bad):
    with pytest.raises(TemplateError):
        parse_template(bad)

def test_regex_is_whole_cell():
    m = ValueMatcher({r"\d+": "n"}, regex=True)
    assert m.hits("40?") == []
    assert m.hits("40") == [(r"\d+", "n")]
    assert ValueMatcher({"a|ab": "x"}, regex=True).hits("ab") == [("a|ab", "x")]

def test_regex_capture_references():
    m = ValueMatcher({r"(\d+)\?": "$1", r"~(\d+)": "$1", r"(a)?b": "[$1]"}, regex=True)
    assert m.hits("40?") == [(r"(\d+)\?", "40")]
    assert m.hits("~35") == [(r"~(\d+)", "35")]
    assert m.hits("b") == [(r"(a)?b", "[]")]

def test_backslashes_in_a_replacement_stay_literal():
    assert ValueMatcher({r"(\d)": "x\\1\\n"}, regex=True).hits("4") == [(r"(\d)", "x\\1\\n")]

def test_exact_mode_values_are_literal():
    assert ValueMatcher({"80+": "$80"}, regex=False).hits("80+") == [("80+", "$80")]
    assert ValueMatcher({"a.": "x"}, regex=False).hits("ab") == []

def test_empty_cell_is_matched_like_any_value():
    assert ValueMatcher({".*": "x"}, regex=True).hits("") == [(".*", "x")]

def test_ambiguity_only_when_results_differ():
    m = ValueMatcher({r"~.*": "Yes", r".*\?": "Yes", r"\d+\?": "No"}, regex=True)
    assert not ValueMatcher.is_ambiguous(m.hits("~3"))          # one hit
    assert not ValueMatcher.is_ambiguous(m.hits("~x?"))         # two hits, both "Yes"
    assert ValueMatcher.is_ambiguous(m.hits("3?"))              # "Yes" and "No"
```

- [ ] **Step 2: Run** `... -m pytest tests/test_match.py -q` — Expected: FAIL (module not found).

- [ ] **Step 3: Implement `scripts/_match.py`** with the interfaces above. Module docstring: whole-cell matching, `$n` rules, and that substitution never goes through `re.sub`/`expand`.

- [ ] **Step 4: Run** `tests/test_match.py` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tabular-to-stf/scripts/_match.py tabular-to-stf/tests/test_match.py
git commit -m "tabular-to-stf: _match module for exact/regex cell matching with \$n references"
```

---

### Task 3: Validate `match` in the spec

**Files:**
- Modify: `scripts/_spec.py` (`_check_transform`, `validate_spec` passes the parsed version in)
- Test: `tests/test_spec.py`

**Interfaces:**
- Consumes: `parse_template`, `template_groups`, `TemplateError` from Task 2; `parse_version` from Task 1.
- Produces: `_spec.MATCH_OPS = ("map-values", "derive-column", "blank-placeholders")`; `_check_transform(t, i, entity_names, errors, version: tuple[int, int, int] | None)`.

Error messages (exact text; `at` is `transforms[i]`; the field is `map`, or `values` for `blank-placeholders`):

| Condition | Message |
|---|---|
| `match` not `"exact"`/`"regex"` | `{at}.match: must be "exact" or "regex"` |
| `match` on another op | `{at}.match: only map-values, derive-column and blank-placeholders take match` |
| `match` present and spec version known and < (1,1,0) | `{at}.match: needs specVersion 1.1.0 or later` |
| regex + `approval: "auto"` | `{at}.approval: "auto" is not allowed with match "regex"; use "user"` (replaces, not adds to, the blank-placeholders auto message) |
| pattern does not compile | `{at}.{field}: invalid pattern {js_json(p)}: {re.error message}` |
| bad template | `{at}.map: replacement {js_json(v)}: {TemplateError message}` |
| group > pattern's groups | `{at}.map: replacement {js_json(v)} refers to group {n}, but pattern {js_json(k)} has {g} group(s)` |

Templates are checked only in regex mode, on `map` values (not `derive-column`'s `default`). Pattern/template checks run only when the field already passed its existing type check.

- [ ] **Step 1: Write the failing tests** — one test per row of the table, each building on `minimal_spec()` with a transform on its entity, asserting the exact message; plus:

- `test_regex_transforms_with_user_approval_are_valid` — one spec at `"1.1.0"` with `map-values` `{"(\\d+)\\?": "$1"}`, `derive-column` `{"~.*": "Yes"}` / `default "No"`, and `blank-placeholders` `values ["n\\.?a\\.?"]`, all `match: "regex"`, `approval: "user"`: `validate_spec(s) == []`.
- `test_exact_map_value_with_dollar_is_valid` — `map-values` without `match`, `map {"80+": "$80"}`, `approval "auto"`: `validate_spec(s) == []`.
- `test_regex_blank_placeholders_of_unambiguous_values_still_cannot_be_auto` — `values ["NA"]`, `match regex`, `approval auto`: the regex `auto` message is present and the blank-placeholders one is not.
- `test_match_on_a_1_0_0_spec_is_refused` — the version row of the table.

- [ ] **Step 2: Run** `tests/test_spec.py` — Expected: new tests FAIL.

- [ ] **Step 3: Implement** in `_check_transform` per the table.

- [ ] **Step 4: Run the whole suite** — Expected: PASS.

- [ ] **Step 5: Commit** — `git commit -m "tabular-to-stf: validate match, patterns and \$n replacements in the spec"`

---

### Task 4: Regex in the transforms, ambiguity, notes, partial runs

**Files:**
- Modify: `scripts/_transforms.py` (`_apply_one` for the three ops; `apply_transforms` signature)
- Modify: `scripts/_notes.py` (`_describe`)
- Test: `tests/test_transforms.py`, `tests/test_render.py`

**Interfaces:**
- Consumes: `ValueMatcher` (Task 2), `MATCH_OPS` (Task 3).
- Produces:
  - `apply_transforms(tables, spec, *, upto: int | None = None, entity: str | None = None) -> tuple[dict[str, Table], list[dict]]` — runs only transforms with index `< upto` (all if None); with `entity`, transforms for other entities are skipped and not logged. Logged `index` stays the spec index.
  - `value_rule(t: dict) -> tuple[ValueMatcher, str | None]` — the matcher for a `MATCH_OPS` transform (`blank-placeholders` → `{v: "" for v in values}`) and its fallback (`derive-column`'s `default`, else None, meaning "leave the cell").
  - `value_columns(t: dict, headers: list[str]) -> list[str]` — the columns a `MATCH_OPS` transform reads: `[column]`, `[from]`, or `columns`/all headers.

Behaviour: each of the three ops computes `hits` per cell; a cell with ambiguous hits is collected; after the scan, if any, raise
`TransformError(f"{where}: values in column {js_json(col)} match more than one key with different results for row IDs: {ids}; tighten the patterns or settle them with replace-cells before this transform")`
where `ids` is `", ".join(...)` of row IDs (fallback `row N`, as in parse-dates), and `col` is the column read. No cell is changed when the transform fails. Otherwise the cell gets the first hit's result, or the fallback, or stays.

Notes: for `match == "regex"`, `_describe` appends ` (regex)` to the text, e.g. `` `p.age`: "(\d+)\?" → "$1" (regex), 3 cells changed ``.

- [ ] **Step 1: Write the failing tests** in `tests/test_transforms.py`:

```python
def test_map_values_regex_with_capture():
    t = {"p": mk(["id", "age"], [["P1", "40?"], ["P2", "~35"], ["P3", "35"]])}
    out, log = run([T("map-values", column="age", match="regex", map={r"(\d+)\?": "$1"}),
                    T("map-values", column="age", match="regex", map={r"~(\d+)": "$1"})], t)
    assert [r[1] for r in out["p"].rows] == ["40", "35", "35"]
    assert log[0]["ids"] == ["P1"] and log[1]["ids"] == ["P2"]

def test_derive_column_regex_flag_before_strip():
    t = {"p": mk(["id", "age"], [["P1", "40?"], ["P2", "~35"], ["P3", "35"]])}
    out, _ = run([T("derive-column", column="age_uncertain", **{"from": "age"}, match="regex",
                    map={r"~.*": "Yes", r".*\?": "Yes"}, default="No")], t)
    assert [r[2] for r in out["p"].rows] == ["Yes", "Yes", "No"]

def test_blank_placeholders_regex():
    t = {"p": mk(["id", "v"], [["A", "n.a."], ["B", "N/A"], ["C", "nan"]])}
    out, _ = run([T("blank-placeholders", match="regex", values=[r"(?i)n\.?/?a\.?"], columns=["v"])], t)
    assert [r[1] for r in out["p"].rows] == ["", "", "nan"]

def test_regex_matches_empty_cells_too():
    out, _ = run([T("map-values", column="age", match="regex", map={".*": "x"})])
    assert [r[1] for r in out["p"].rows] == ["x", "x", "x"]

def test_ambiguous_regex_fails_naming_row_ids_and_changes_nothing():
    t = {"p": mk(["id", "age"], [["P1", "3?"], ["P2", "4"]])}
    with pytest.raises(TransformError, match=r"match more than one key with different results for row IDs: P1;"):
        run([T("map-values", column="age", match="regex", map={r".*\?": "a", r"\d\?": "b"})], t)

def test_overlapping_keys_with_the_same_result_are_fine():
    t = {"p": mk(["id", "age"], [["P1", "~3?"]])}
    out, _ = run([T("derive-column", column="u", **{"from": "age"}, match="regex",
                    map={r"~.*": "Yes", r".*\?": "Yes"}, default="No")], t)
    assert out["p"].rows[0][2] == "Yes"

def test_upto_and_entity_limit_the_run_and_keep_spec_indexes():
    s = {"entities": [{"name": "p", "idColumn": "id"}, {"name": "q", "idColumn": "id"}],
         "transforms": [T("trim"), {**T("trim"), "entity": "q"}, T("drop-column", column="note")]}
    out, log = apply_transforms(tables(), s, upto=2, entity="p")
    assert [e["index"] for e in log] == [0]
    assert "note" in out["p"].headers
```

And in `tests/test_render.py`, a `render_notes` test asserting `(regex)` appears on the regex transform's line.

- [ ] **Step 2: Run** `tests/test_transforms.py tests/test_render.py` — Expected: new tests FAIL.

- [ ] **Step 3: Implement** `value_rule`, `value_columns`, the three ops via `ValueMatcher`, the ambiguity error, the `apply_transforms` options, and the notes suffix. Exact mode must behave exactly as before (the existing tests, including `test_map_values_does_not_match_inherited_names`, must still pass).

- [ ] **Step 4: Run the whole suite** — Expected: PASS.

- [ ] **Step 5: Commit** — `git commit -m "tabular-to-stf: regex map-values, derive-column and blank-placeholders; ambiguity fails the render"`

---

### Task 5: `stf.py preview`

**Files:**
- Create: `scripts/_preview.py`
- Modify: `scripts/_render.py` (extract `load_spec`)
- Modify: `scripts/stf.py` (docstring, `PREVIEW_USAGE`, `cmd_preview`, parser)
- Modify: `SKILL.md` (Scripts table row — required by `test_docs`, which checks every sub-command and option is documented)
- Test: `tests/test_preview.py`

**Interfaces:**
- Consumes: `apply_transforms(..., upto=, entity=)`, `value_rule`, `value_columns`, `ValueMatcher.is_ambiguous` (Task 4); `TransformError`.
- Produces:
  - `_render.load_spec(spec_path: Path) -> tuple[dict, str]` — reads and validates the spec (raises `RenderError(errors)`), returns it and the absolute input dir. `render_to_dir` uses it.
  - `_preview.preview_transform(spec: dict, table: Table, index: int, top: int = 10, bottom: int = 10) -> str` — `table` is the input table of `transforms[index]`'s entity. Raises `TransformError` if an earlier transform fails.
  - CLI: `Usage: stf.py preview <spec.json> <n> [--top N] [--bottom N]`; `--top`/`--bottom` positive integers via `_positive_int`, default 10; `<n>` a non-negative integer < number of transforms, else `ValueError` (`<n> must be a transform index from 0 to {k-1}, got "{n}"`, or `the spec has no transforms`). Spec errors print like render (`Error: the spec is not valid:` then `- ` lines) and exit 1; an earlier transform failing prints `Error: an earlier transform fails: {message}` and exits 1.

Algorithm for `preview_transform`: copy `transforms[index]` with `approval` forced to `"user"` into a copy of the spec; `before = apply_transforms({e: table}, spec2, upto=index, entity=e)`. For `MATCH_OPS`: for each column from `value_columns` (one section per column), count distinct values of `before` with `Counter`, classify each distinct value via `value_rule`: ambiguous / matched (result = first hit, or for a key-less derive fallback → unmatched) / unmatched. For other ops: `apply_transforms(..., upto=index + 1, entity=e)`; print `Cells changed: N` and, if headers changed, `Columns: [...] → [...]`; if this transform raises `TransformError`, print `This transform fails: {message}` (still a successful preview).

Output layout (values printed with `js_json`; counts with `{n:,}`; lists sorted by count desc then value asc; bottom excludes values already in top):

```
transforms[3] map-values on entity "participant", match regex, approval proposed
Column "age"
Matched: 2 distinct values, 5 cells
  "40?" → "40"  ×3  (key "(\\d+)\\?")
  "35?" → "35"  ×2  (key "(\\d+)\\?")
Ambiguous: none
Unmatched: 120 distinct values, 4,870 cells; 12 empty cells
  "35"  ×200
  … (top 10)
  … 100 more distinct values (4,000 cells)
  "approx. 12"  ×1
  … (bottom 10)
```

`(key …)` appears only in regex mode. For `derive-column`, unmatched lines read `"35" → "No" (default)  ×200`. Ambiguous lines list all keys and results: `"3?"  ×1  keys "(.*)\\?" → "3", "\\d\\?" → "b"`; never capped. Unmatched empties are counted in the header, never listed; a matched empty is listed as `""`.

- [ ] **Step 1: Write the failing tests** in `tests/test_preview.py` (unit tests call `preview_transform` directly; CLI tests use `run_cli` with a spec + CSV written to `tmp_path`):
  - `test_matched_ambiguous_unmatched_sections` — asserts the `Matched: 2 distinct values, 5 cells`, `"40?" → "40"  ×3`, `Ambiguous: none` lines.
  - `test_proposed_transform_is_previewed_and_earlier_proposed_ones_are_not_applied`
  - `test_earlier_rename_is_applied_before_preview` (Review Focus 4)
  - `test_top_and_bottom_cap_with_totals` — 30 distinct unmatched values, `top=2, bottom=2`: exactly 4 value lines and `… 26 more distinct values (` present.
  - `test_unmatched_empty_cells_are_counted_not_listed` (Review Focus 5)
  - `test_ambiguous_values_are_listed_uncapped` — 15 ambiguous values with `top=1, bottom=1`: all 15 listed.
  - `test_derive_column_shows_default_for_unmatched`
  - `test_blank_placeholders_prints_one_section_per_column`
  - `test_non_value_op_summary_and_own_failure` — `drop-column` prints `Columns:`; a failing `parse-dates` prints `This transform fails:` and returns normally.
  - `test_cli_preview_exit_codes` — 0 on success; 1 for index out of range (message), 1 for invalid spec, 1 when an earlier transform fails (`Error: an earlier transform fails:`).
  - `test_preview_works_on_a_skeleton_spec` — entities with `variables: []` plus one transform.

- [ ] **Step 2: Run** `tests/test_preview.py` — Expected: FAIL (module not found).

- [ ] **Step 3: Implement** `load_spec`, `_preview.py`, the CLI, the `stf.py` module docstring paragraph for `preview`, and the `SKILL.md` Scripts table row: `` `uv run scripts/stf.py preview <spec.json> <n> [--top N] [--bottom N]` `` | Shows what transform `n` (0-based) does to the data: matched, ambiguous and unmatched values with counts. Writes nothing.

- [ ] **Step 4: Run the whole suite** — Expected: PASS (including `test_docs`).

- [ ] **Step 5: Commit** — `git commit -m "tabular-to-stf: stf.py preview shows what one transform does"`

---

### Task 6: Skill documentation

**Files:**
- Modify: `SKILL.md` (steps 2, 3, 7)
- Modify: `resources/cleaning.md`
- Modify: `resources/curation-spec.md`
- Test: `tests/test_docs.py` (existing checks)

No code. Each edit below is required; wording is the implementer's, in the docs' existing plain style.

- [ ] **Step 1: `SKILL.md` step 2** — end with: once the tree is settled, write the first draft to `<work>/curation-spec.json` (`specVersion`, `study`, `inputDir` as the absolute input path, the entities with `variables: []`), following curation-spec.md. Steps 3–6 add to this file.

- [ ] **Step 2: `SKILL.md` step 3** — add: a transform that uses `match: "regex"` is written as `proposed`; run `stf.py preview <work>/curation-spec.json <n>` (use `--bottom N` to look for rare values the pattern missed); show the user the matched and ambiguous values and anything suspicious among the unmatched; set `user` only when they accept, `rejected` with `instead` otherwise. Regex is never `auto`. Previewing other transforms before asking about them is encouraged.

- [ ] **Step 3: `SKILL.md` step 7** — rename to "Finish the spec and render"; the draft already exists; keep the render, `--no-raw-data` and handover text.

- [ ] **Step 4: `resources/cleaning.md`** — (a) "Uncertain values" option 1 uses regex: `derive-column` with `"match": "regex"`, `map: { "~.*": "Yes", ".*\\?": "Yes" }`, `default: "No"` first, then one `map-values` per marker (`{ "(\\d+)\\?": "$1" }`, `{ "~(\\d+)": "$1" }`), all `proposed` until previewed and accepted. (b) A short "Patterns instead of long maps" section: use `match: "regex"` when many keys share a shape; patterns match whole cells; `$1` for groups; overlapping keys with different results fail the render; keep patterns simple. (c) The kinds table and the `auto` paragraph mention that regex transforms are always `user`.

- [ ] **Step 5: `resources/curation-spec.md`** — transforms table: `match?` field on the three ops and the "never `auto` with regex" rule; "How the renderer reads the spec": whole-cell regex, `$n`/`$$` rules (stray `$` is an error, non-participating group gives `""`, exact-mode values are literal), the ambiguity rule; a short `stf.py preview` paragraph; the opening paragraph says the draft is started after the entity tree (SKILL.md step 2).

- [ ] **Step 6: Run the whole suite** — Expected: PASS.

- [ ] **Step 7: Commit** — `git commit -m "tabular-to-stf docs: draft the spec after the entity tree; regex transforms via preview and approval"`
