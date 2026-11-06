# tabular-to-stf Python Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Node.js scripts of the `tabular-to-stf` skill with one Python CLI, `uv run scripts/stf.py <subcommand>`. Behaviour, the curation spec format and the meaning of the output all stay the same.

**Architecture:** `scripts/stf.py` is a thin argparse CLI with a PEP 723 header. It imports `_`-prefixed sibling modules, one per responsibility, each a port of a JS module under `scripts/lib/`. The JS stays in the tree as reference material until the last task deletes it. **Do not run or fix the JS suite during the port.**

**Tech Stack:** Python ≥ 3.11, `ruamel.yaml` (the only dependency), stdlib `csv`, `argparse`, `subprocess`, `pathlib`; pytest; docker/podman + the R script for opt-in container tests.

**Spec:** `docs/superpowers/specs/2026-11-05-tabular-to-stf-python-port-design.md` (read it first; this plan argues from it).

## Global Constraints

- Python `>=3.11`; PEP 723 header on `stf.py`: `requires-python = ">=3.11"`, `dependencies = ["ruamel.yaml>=0.18"]`. No other third-party packages (no pandas).
- Run as `uv run scripts/stf.py …`. Tests run from `tabular-to-stf/` with `uv run --with pytest --with "ruamel.yaml>=0.18" python -m pytest tests -q`.
- Inputs are never modified, no git changes, and the container is never pulled (`--pull=never`).
- `STUDY_WRANGLER_VERSION = "1.0.56"` is written out once, in `scripts/_container.py`. Everything else imports it. The only other place that names it is `resources/stf/SOURCE.md`, which a test checks against the constant.
- Every file the scripts write uses UTF-8 and `\n` line endings on every platform (`open(..., "w", encoding="utf-8", newline="\n")`).
- `stf.py` reconfigures stdout and stderr to UTF-8 at startup.
- Error, warning and log message texts are ported verbatim from the JS. Where the JS uses `JSON.stringify(x)` inside a message, use `json.dumps(x, ensure_ascii=False)`.
- JS `x !== undefined` on a spec or YAML field means *the key is present*: test it with `"key" in d`. A JSON `null` is a present value and fails string checks. JS `a ?? b` means `a if a is not None else b`.
- Port tests by behaviour. Each JS `test('…')` becomes a pytest `test_…` with a snake_case version of the same name and the same assertions, unless a task says otherwise.
- Use `pathlib`. Do not shell out to anything except the container engine.
- Each commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Commit only; never push.

## Review Focus

1. **Writing files on Windows.** A default `open(..., "w")` writes CRLF and cp1252, so an entity TSV would gain `\r` and non-ASCII values would be mangled. Expected: the bytes are UTF-8 with LF only. The test is in Task 7.
2. **Non-ASCII on a Windows console.** Profiling data with `São Paulo` and printing the JSON to a cp1252 console would crash with `UnicodeEncodeError`. Expected: exit 0 and correct output. The test is in Task 4.
3. **JSON `null` versus a missing key in the spec.** `"parent": null` is a present value in the JS and is reported, not treated as a root. Expected: the same errors as the JS. The test is in Task 5.
4. **Non-ASCII word boundaries in the geo matchers.** Python's `\b` is Unicode-aware but the JS one is ASCII-only, so names like `élat` or `lat_é` would be matched differently. Expected: identical results, using `re.ASCII`. The test is in Task 1.
5. **Numbers read from hand-edited YAML in `check`.** `ordinal_levels: [1.0, 2.0]` must still match TSV cells `1` and `2`, and `entity_level: -1.0` is still an integer, as in the JS. Expected: no error. The test is in Task 3.

---

## File structure

All paths are under `tabular-to-stf/`.

| File | Responsibility | Ported from |
|---|---|---|
| `scripts/stf.py` | CLI: `build_parser()`, `main(argv)`, one `cmd_*` per subcommand | `scripts/*.js` |
| `scripts/_constants.py` | STF value sets, placeholders, `MAX_VALUE_LENGTH`, `SAVED_SPEC`, `RAW_DIR` | `stf-constants.js`, parts of `profile.js`, `notes.js`, `render-stf.js` |
| `scripts/_common.py` | `infer_type`, `is_valid_column_name`, `to_column_name`, `unique_column_names` | `stf-common.js` (minus YAML) |
| `scripts/_geo.py` | lat/long name matchers, `GEO` | `geo.js` |
| `scripts/_yaml.py` | R-safe YAML writer; STF YAML reader with yaml-lite typing; YAML 1.1 ambiguity predicate | `yaml-lite.js`, `yamlScalar` |
| `scripts/_read_table.py` | `Table`, `parse_delimited`, `read_table` | `read-table.js` |
| `scripts/_profile.py` | `profile_tables`, `truncate_value` | `profile.js` |
| `scripts/_spec.py` | `validate_spec` | `spec.js` |
| `scripts/_transforms.py` | `apply_transforms` | `transforms.js` |
| `scripts/_notes.py` | `render_notes` | `notes.js` |
| `scripts/_render.py` | `render_stf` (pure), `render_to_dir` (I/O, raw-data copies) | `render.js`, `render-stf.js` |
| `scripts/_check.py` | `check_stf`, `geohash_warning` | `check.js` |
| `scripts/_container.py` | version constant, engine detection, container args, validation | `study-wrangler-container.js`, `exec.js` |
| `scripts/study-wrangler-validate-study.R` | unchanged R validator (moved with `git mv`) | `scripts/lib/tools/…R` |
| `tests/conftest.py` | `sys.path` setup, `run_cli`, fixture paths | — |
| `tests/test_*.py` | one per module, plus `test_golden.py`, `test_docs.py`, `test_scale.py`, `test_container.py` | `tests/*.test.js` |

---

### Task 1: Scaffold, constants, naming helpers, geo matchers

**Files:**
- Create: `scripts/_constants.py`, `scripts/_common.py`, `scripts/_geo.py`, `tests/conftest.py`, `tests/test_common.py`, `tests/test_geo.py`

**Interfaces:**
- Produces:
  - `_constants`: `DATA_TYPES`, `DATA_SHAPES`, `DISPLAY_TYPES`, `HIDDEN` (tuples, with the values from `stf-constants.js`); `PLACEHOLDERS`, `UNAMBIGUOUS_PLACEHOLDERS` (tuples, values from `profile.js`); `MAX_VALUE_LENGTH = 80`; `SAVED_SPEC = "curation-spec.json"`; `RAW_DIR = "raw-data"`.
  - `_common`: `infer_type(values: Iterable[str]) -> dict[str, str]` (keys `data_type`, `data_shape`); `is_valid_column_name(name: str) -> bool`; `to_column_name(header: str) -> str`; `unique_column_names(names: list[str]) -> list[str]`.
  - `_geo`: `is_latitude_name`, `is_longitude_name`, `validator_sees_latitude`, `validator_sees_longitude` (each `(text: str) -> bool`); `GEO = {"latitude": {"stable_id": "OBI_0001620", "data_type": "number", "display_type": "latitude"}, "longitude": {"stable_id": "OBI_0001621", "data_type": "longitude", "display_type": "longitude"}, "geohash_columns": ("geohash_1", …, "geohash_6")}`.
  - `tests/conftest.py`: puts `scripts/` on `sys.path`. Defines `SKILL = Path(__file__).resolve().parents[1]` and `FIXTURES = SKILL / "tests/fixtures"`, plus `run_cli(*args, env=None) -> subprocess.CompletedProcess`, which runs `[sys.executable, SKILL/"scripts/stf.py", *args]` with `capture_output=True, text=True, encoding="utf-8"`.

- [ ] **Step 1: Write the failing tests.** Port `tests/tabular-stf-common.test.js` into `tests/test_common.py`, except the `yamlScalar` test, which moves to Task 3. Port `tests/tabular-geo.test.js` and the "constants are frozen with the expected values" test from `tabular-spec.test.js` into `tests/test_geo.py` and `tests/test_common.py`. Add:

```python
def test_geo_word_boundaries_are_ascii_like_js():
    # JS \b treats non-ASCII letters as non-word characters
    assert is_latitude_name("élat")
    assert validator_sees_latitude("élat")   # False under Unicode \b
    assert to_column_name("Âge (années)") == "ge_ann_es"
```

- [ ] **Step 2: Run them and check they fail.** `uv run --with pytest --with "ruamel.yaml>=0.18" python -m pytest tests -q` should FAIL with `ModuleNotFoundError: _common`.

- [ ] **Step 3: Implement the three modules.** The regexes are ported character for character. The geo matchers use `re.IGNORECASE | re.ASCII`. `to_column_name` uses `[^a-z0-9]+` on `.lower()`.

- [ ] **Step 4: Run the tests and check they pass.** Same command as Step 2. Expected: PASS.

- [ ] **Step 5: Commit.** `git add scripts/_constants.py scripts/_common.py scripts/_geo.py tests/conftest.py tests/test_common.py tests/test_geo.py`. Message: "tabular-to-stf: Python scaffold, naming helpers and geo matchers".

---

### Task 2: Table reader

**Files:**
- Create: `scripts/_read_table.py`, `tests/test_read_table.py`

**Interfaces:**
- Produces: `@dataclass class Table: file: str; delimiter: str; headers: list[str]; rows: list[list[str]]`. `class TableError(ValueError)`, with the message `"{label}: line {n}: {message}"`. `parse_delimited(text: str, delimiter: str, label: str = "input") -> tuple[list[str], list[list[str]]]`. `read_table(path: Path) -> Table`.

- [ ] **Step 1: Write the failing tests.** Port every test in `tests/tabular-read-table.test.js`, keeping the same inputs and expected cells, line numbers and messages.

- [ ] **Step 2: Run them and check they fail.** `… pytest tests/test_read_table.py -q` should FAIL on import.

- [ ] **Step 3: Implement `_read_table.py`.**
  - Strip a leading `﻿`.
  - TSV: split on `\n`, drop one trailing `\r` per line, no quoting.
  - CSV: use `csv.reader(io.StringIO(text, newline=""))` with `strict=False`, so `"a"b` reads as `ab` as in the JS.
  - Treat a record that `csv` returns as `[]` (a blank line) as `[""]`.
  - Report the line where a record *starts*, which is the previous record's `reader.line_num + 1`.
  - Detect an unterminated quote and raise `TableError(label, line, "unterminated quoted field")`.
  - Drop trailing blank records only.
  - The cell-count mismatch message is `expected {n} cells but found {m}`.
  - The delimiter comes from the extension (`.csv` `,`; `.tsv`/`.txt` tab), otherwise it is sniffed from line 1 as in `sniffDelimiter`.
  - `read_table` reads the file with `encoding="utf-8-sig"` and `newline=""`.

- [ ] **Step 4: Run the tests and check they pass.** Including "large input parses linearly".

- [ ] **Step 5: Commit.** "tabular-to-stf: Python table reader".

---

### Task 3: YAML writer and STF YAML reader

**Files:**
- Create: `scripts/_yaml.py`, `tests/test_yaml.py`

**Interfaces:**
- Produces:
  - `needs_quoting(s: str) -> bool`: the `yamlScalar` rule from `stf-common.js` (`looksNumeric` included), ported exactly.
  - `yaml11_resolves(s: str) -> bool`: True if a YAML 1.1 reader (R's `yaml`) would read the plain scalar `s` as something other than that text. That means `^(y|yes|n|no|on|off|true|false|null|~)$` in any case, or `looksNumeric(s)`.
  - `dump_yaml(data: Any) -> str`: block style, key order kept, `width=4096` (no folding), sequences indented as `  - ` under their key, `[]` for an empty list. Every `str` is written plain unless `needs_quoting`, in which case single-quoted (double-quoted with `\n \r \t` escapes if it contains a control character). bools are written `true`/`false`. ints are written plain.
  - `class YamlError(ValueError)` with `.line` and the message `"line {n}: {message}"`.
  - `load_stf_yaml(text: str) -> tuple[Any, list[str]]`: returns the data and a list of warnings.

- [ ] **Step 1: Write the failing tests.**
  - Port all of `tests/tabular-yaml-lite.test.js` against `load_stf_yaml(...)[0]`, keeping the same inputs and expected values, including "unsupported constructs throw … with the line" (now `YamlError`).
  - Port the "yamlScalar quotes YAML 1.1 booleans…" test as a test of `needs_quoting`.
  - Add these new tests:

```python
TRICKY = ["yes", "No", "on", "OFF", "y", "NA", "007", "1e3", "1_000", "0x1F", "1:30",
          ".inf", "2023-01-01", "a: b", "a #b", "#x", "", " pad", "it's", "line\nbreak", "true", "null", "~"]

def test_dump_round_trips_as_text_under_yaml_1_2_and_1_1():
    text = dump_yaml({"values": TRICKY})
    assert load_stf_yaml(text)[0]["values"] == TRICKY
    from ruamel.yaml import YAML
    as_11 = YAML(typ="safe", pure=True).load("%YAML 1.1\n---\n" + text)["values"]
    # R's yaml keeps timestamps as text; ruamel's 1.1 resolver makes a date, so skip that one
    assert [v for v, t in zip(as_11, TRICKY) if t != "2023-01-01"] == [t for t in TRICKY if t != "2023-01-01"]

def test_reader_types_like_yaml_lite():
    data, _ = load_stf_yaml("a: [1.0, 2.0, 1e3, 2024-01-01, yes, 'true', true, ~, -1.0]\n")
    assert data["a"] == [1, 2, "1e3", "2024-01-01", "yes", "true", True, None, -1]
    assert type(data["a"][0]) is int and type(data["a"][8]) is int

def test_unquoted_yaml11_values_warn_quoted_do_not():
    _, warnings = load_stf_yaml("levels: [yes, 'no', on]\n")
    assert len(warnings) == 2
    assert all("quote it" in w for w in warnings)
```

- [ ] **Step 2: Run them and check they fail.** On import.

- [ ] **Step 3: Implement `dump_yaml`** with `ruamel.yaml.YAML(typ="rt")`. Register a `str` representer that applies `needs_quoting`, and set the indentation with `yaml.indent(mapping=2, sequence=4, offset=2)` and `yaml.width = 4096`.

- [ ] **Step 4: Implement `load_stf_yaml`** as a small builder over `ruamel.yaml.YAML(typ="safe", pure=True).parse(text)` events, so each scalar's style, tag and anchor are visible.
  - **Raise `YamlError` with the event's line** on any of these: an anchor; an `AliasEvent`; an explicit tag; a second document; a flow mapping that has content. `{}` is allowed. A flow sequence may contain only scalars.
  - **Quoted and block scalars** are text.
  - **Plain scalars are typed as in `plainValue`:**
    - empty, `null` or `~` (any case) become `None`;
    - `true`/`false` (any case) become `bool`;
    - `-?\d+` and `-?(\d+\.\d+|\.\d+)` become numbers: `int` when the value is integral, otherwise `float`;
    - everything else stays text.
  - **Warnings:** a plain scalar left as text for which `yaml11_resolves` is True adds a warning: ``line {n}: unquoted value {json} would be read as a non-text value by study-wrangler's YAML 1.1 reader; quote it``.

- [ ] **Step 5: Run the tests and check they pass.**

- [ ] **Step 6: Commit.** "tabular-to-stf: R-safe YAML writer and STF YAML reader".

---

### Task 4: Profiler and `stf.py profile`

**Files:**
- Create: `scripts/_profile.py`, `scripts/stf.py`, `tests/test_profile.py`

**Interfaces:**
- Consumes: `Table`, `read_table` (Task 2); `infer_type` (Task 1); `PLACEHOLDERS`, `MAX_VALUE_LENGTH` (Task 1).
- Produces:
  - `truncate_value(v: str, max_len: int = MAX_VALUE_LENGTH) -> str`.
  - `profile_tables(tables: list[Table], top_n: int = 20, sample_rows: int = 5) -> dict`, with the same keys and order as the JS output.
  - `stf.py`:
    - a PEP 723 header (see Global Constraints) and `#!/usr/bin/env python3`;
    - `build_parser() -> argparse.ArgumentParser` with subparsers (`dest="command"`, required);
    - `main(argv: list[str] | None = None) -> int`;
    - `cmd_profile(args) -> int`.
    - `main` reconfigures stdout and stderr to UTF-8. Every exception except `SystemExit` becomes `Error: {message}` on stderr and exit 1.
- CLI: `stf.py profile <inputDir> [--top N] [--file NAME] [--out PATH]`, with the same validation, messages and summary lines as `profile-tables.js`. JSON is compact (`separators=(",", ":"), ensure_ascii=False`). Sizes in KB are measured on UTF-8 bytes. `min`/`max` are `int` for integer columns.

- [ ] **Step 1: Write the failing tests.** Port every test in `tests/tabular-profile.test.js`, running the CLI tests through `run_cli("profile", …)`. Add:

```python
def test_profile_prints_non_ascii_on_a_cp1252_console(tmp_path):
    (tmp_path / "sites.csv").write_text("site_id,city\nS1,São Paulo\n", encoding="utf-8")
    r = run_cli("profile", str(tmp_path), env={**os.environ, "PYTHONIOENCODING": "cp1252"})
    assert r.returncode == 0 and "São Paulo" in r.stdout
```

- [ ] **Step 2: Run them and check they fail.**

- [ ] **Step 3: Implement `_profile.py`** using `collections.Counter`. Sort by count descending, then by value ascending. Use the same Levenshtein limits (`5`, `2`, `200` distinct) and the same order of near-duplicate pairs.

- [ ] **Step 4: Implement `stf.py`** with only the `profile` subcommand.

- [ ] **Step 5: Run the tests and check they pass.**

- [ ] **Step 6: Commit.** "tabular-to-stf: Python profiler and stf.py profile".

---

### Task 5: Spec validator

**Files:**
- Create: `scripts/_spec.py`, `tests/test_spec.py`

**Interfaces:**
- Consumes: `is_valid_column_name`; `UNAMBIGUOUS_PLACEHOLDERS`, `DATA_TYPES`, `DATA_SHAPES`, `DISPLAY_TYPES`.
- Produces: `validate_spec(spec: Any) -> list[str]`, which returns every error with its path, in the same order and with the same text as `spec.js`. The entity-name message keeps the literal text `must match /^[a-z][a-z0-9_]*$/`.

- [ ] **Step 1: Write the failing tests.** Port every test in `tests/tabular-spec.test.js` except the constants test, which was done in Task 1. Add:

```python
def test_null_parent_is_a_present_value_not_a_root():
    spec = minimal_spec()  # the same minimal valid spec as the JS test helper
    spec["entities"][0]["parent"] = None
    errors = validate_spec(spec)
    assert any(e.startswith("entities[0].parent: unknown entity null") for e in errors)
    assert any("need exactly one root" in e for e in errors)
```

- [ ] **Step 2: Run them and check they fail.**

- [ ] **Step 3: Implement `_spec.py`.** Follow the key-presence rule in Global Constraints. `isStr` means a `str` that is not empty. `isInsidePath` uses the same regex and `..` segment check.

- [ ] **Step 4: Run the tests and check they pass.**

- [ ] **Step 5: Commit.** "tabular-to-stf: Python spec validator".

---

### Task 6: Transforms

**Files:**
- Create: `scripts/_transforms.py`, `tests/test_transforms.py`

**Interfaces:**
- Consumes: `Table` (Task 2).
- Produces: `class TransformError(ValueError)`. `apply_transforms(tables: dict[str, Table], spec: dict) -> tuple[dict[str, Table], list[dict]]` returns copies of the tables and the log. Each log entry has the keys `index`, `op`, `entity`, `approval`, `cellsChanged`, plus `column` when the transform has one and `ids` for `user` value changes. The keys and their meaning are as in `transforms.js`.

- [ ] **Step 1: Write the failing tests.** Port every test in `tests/tabular-transforms.test.js`.
- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement `_transforms.py`.** `dateParser` validates the date with `datetime.date(y, m, d)`, catching `ValueError`. `map-values` and `derive-column` look values up with `in` on the map dict.
- [ ] **Step 4: Run the tests and check they pass.**
- [ ] **Step 5: Commit.** "tabular-to-stf: Python transforms".

---

### Task 7: Notes, renderer and `stf.py render`

**Files:**
- Create: `scripts/_notes.py`, `scripts/_render.py`, `tests/test_render.py`
- Modify: `scripts/stf.py` (add `render`)

**Interfaces:**
- Consumes: `validate_spec`, `apply_transforms`, `read_table`, `dump_yaml`, `infer_type`, `to_column_name`, `unique_column_names`, the `_geo` matchers, `GEO`, `SAVED_SPEC`, `RAW_DIR`.
- Produces:
  - `render_notes(spec: dict, log: list[dict], sources: list[dict] | None = None, decisions: list[str] = ()) -> str`.
  - `class RenderError(Exception)` with `.messages: list[str]`.
  - `render_stf(spec: dict, tables: dict[str, Table], source_dir: str = "raw-data") -> tuple[dict[str, str], list[dict]]`, which returns the file texts by name and the log.
  - `render_to_dir(spec_path: Path, out_dir: Path, copy_raw: bool = True) -> list[Path]`, which applies the CLI rules of `render-stf.js` (non-empty guard, raw-data byte check, saved spec with rewritten `inputDir`, written as `json.dumps(saved, indent=2, ensure_ascii=False) + "\n"`) and returns the paths written, in the order the JS prints them.
  - `stf.py render <spec.json> <outDir> [--no-raw-data]`. A `RenderError` prints `Error: the spec does not render:` followed by `- {m}` lines on stderr, exit 1.
- The entity YAML is built as a dict and passed to `dump_yaml`. Its key order and omission rules come from `variableYaml`, `categoryYaml` and `entityYaml`. `provider_label` is a one-item list. `study.yaml` is `{"name": …, "entities": [...]}` in tree order. The TSV is built by hand: tab-joined, own ID header suffixed with ` \\ Descriptors` (a space, two backslashes, a space, `Descriptors`), and a trailing `\n`.
- The re-render sentence in the notes now reads exactly: ``To re-render it, run `uv run <skill>/scripts/stf.py render <this directory>/curation-spec.json <this directory>`, where `<skill>` is the `tabular-to-stf` skill's folder.``

- [ ] **Step 1: Write the failing tests.** Port every test in `tests/tabular-render.test.js`, using `run_cli("render", …)` for the CLI tests. Drop the test "CLI is executable", because it is replaced by running through `sys.executable`. Add:

```python
def test_rendered_files_are_utf8_with_lf_only(tmp_path):
    # a minimal one-entity input whose values include "São Paulo"
    ...
    for f in out.glob("*.*"):
        data = f.read_bytes()
        assert b"\r" not in data
        data.decode("utf-8")
```

- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement `_notes.py`.** `q()` is `json.dumps(s, ensure_ascii=False)`.
- [ ] **Step 4: Implement `_render.py`.** `PARSES` and `isIsoDate` are ported, and dates are validated with `datetime.date`.
- [ ] **Step 5: Add `render` to `stf.py`.**
- [ ] **Step 6: Run the tests and check they pass.**
- [ ] **Step 7: Commit.** "tabular-to-stf: Python renderer and stf.py render".

---

### Task 8: Golden fixtures

**Files:**
- Create: `tests/test_golden.py`
- Modify: `tests/fixtures/tabular/*/expected/**` (regenerated)

**Interfaces:**
- Consumes: `render_to_dir` (Task 7), `load_stf_yaml` (Task 3), `parse_delimited` (Task 2).

- [ ] **Step 1: Write the test.** For each of `clinical-epi`, `mosquito` and `coffee-shops`:
  - copy `inputs/` and `spec.json` to `tmp_path` as the JS golden test does;
  - render with `render_to_dir`;
  - assert that the set of rendered files, including `raw-data/`, equals the set in `expected/`;
  - compare by content: `*.yaml` with `load_stf_yaml(...)[0]`, `*.tsv` with `parse_delimited` on both sides as string cells, `curation-spec.json` with `json.loads`, and `curation-notes.md` and `raw-data/*` as exact text or bytes.
- [ ] **Step 2: Run it.** Expected: the only failure is the re-render sentence in each `curation-notes.md`. Any other difference is a porting bug: fix it in the owning module and re-run.
- [ ] **Step 3: Regenerate `expected/`** from `uv run scripts/stf.py render`, for all three fixtures.
- [ ] **Step 4: Review the diff.** Run `git diff --stat tests/fixtures/tabular` and `git diff tests/fixtures/tabular`. Expected: only YAML layout (blank lines, quoting style) and the notes sentence. If the diff changes any value, revert and fix the module first.
- [ ] **Step 5: Run the full suite.** Expected: PASS.
- [ ] **Step 6: Commit.** The commit message lists the kinds of differences the regeneration introduced. Message: "tabular-to-stf: golden fixtures compared by content; regenerate expected/ from Python".

---

### Task 9: Checker and `stf.py check`

**Files:**
- Create: `scripts/_check.py`, `tests/test_check.py`
- Modify: `scripts/stf.py` (add `check`)

**Interfaces:**
- Consumes: `load_stf_yaml`, `parse_delimited`, `is_valid_column_name`, the value sets, the `_geo` matchers, `GEO`, and `STUDY_WRANGLER_VERSION`. To keep this task independent of Task 10, create `scripts/_container.py` here containing only `STUDY_WRANGLER_VERSION = "1.0.56"` and `STUDY_WRANGLER_IMAGE = f"veupathdb/study-wrangler:{STUDY_WRANGLER_VERSION}"`; Task 10 fills in the rest.
- Produces: `check_stf(path: Path) -> dict` with the keys `errors` and `warnings`, both lists of strings. `geohash_warning(version: str = STUDY_WRANGLER_VERSION) -> str`. `stf.py check <stfDir> [--json]` prints `ERROR: …`/`WARNING: …` lines, or `json.dumps(result, indent=2, ensure_ascii=False)` with `--json`, and exits 1 if there are errors.
- Warnings from `load_stf_yaml` are added to `warnings` as `{file}: {warning}`.
- `asList(v).map(String)` and messages that print YAML values use `js_str(v)`: `True`/`False` become `"true"`/`"false"`, `None` becomes `"null"`, other values use `str(v)`. Integral numbers are already `int` (Task 3).

- [ ] **Step 1: Write the failing tests.** Port every test in `tests/tabular-check.test.js`, using `run_cli("check", …)` for the CLI test. Add:

```python
def test_float_ordinal_levels_match_integer_cells(good_stf):
    # good_stf: the JS helper's minimal valid STF, written to tmp_path
    set_yaml(good_stf, "sample", variable="grade", ordinal_levels="[1.0, 2.0]", data_shape="ordinal")
    write_column(good_stf, "sample", "grade", ["1", "2"])
    assert check_stf(good_stf)["errors"] == []

def test_unquoted_yes_in_entity_yaml_is_a_warning(good_stf):
    set_yaml(good_stf, "sample", variable="flag", vocabulary_order="[yes, no]")
    warnings = check_stf(good_stf)["warnings"]
    assert any(w.startswith("entity-sample.yaml: line") and "quote it" in w for w in warnings)
```

`set_yaml` and `write_column` are small test helpers. Write them in the test file.

- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement `_check.py`.** A YAML parse error becomes `{name}: cannot parse YAML: {message}`.
- [ ] **Step 4: Add `check` to `stf.py`.**
- [ ] **Step 5: Run the tests and check they pass.** Then run `check` on each regenerated `expected/` directory. Expected: no `ERROR:` lines and no new warnings.
- [ ] **Step 6: Commit.** "tabular-to-stf: Python checker and stf.py check".

---

### Task 10: Container validation and `stf.py validate`

**Files:**
- Modify: `scripts/_container.py`, `scripts/stf.py` (add `validate`)
- Move: `git mv scripts/lib/tools/study-wrangler-validate-study.R scripts/study-wrangler-validate-study.R` (unchanged)
- Create: `tests/test_container.py`

**Interfaces:**
- Produces, in `_container.py`:
  - `Exec = Callable[[list[str]], str]`, which raises `subprocess.CalledProcessError` on failure. `default_exec(cmd)` uses `subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)` and returns stdout.
  - `failure_output(e) -> str`.
  - `detect_engine(exec=default_exec, preferred: str | None = None) -> str | None`.
  - `container_args(engine: str, stf_dir: Path, script_path: Path) -> list[str]`: the same arguments as the JS (`--mount …,readonly` for docker; `-v …:ro,Z` for podman; `--pull=never`).
  - `pull_commands() -> list[str]`, which returns `[f"docker pull {STUDY_WRANGLER_IMAGE}", f"podman pull docker.io/{STUDY_WRANGLER_IMAGE}"]`.
  - `image_present(engine, exec=default_exec) -> bool`, which runs `<engine> image inspect <image>`.
  - `validate_study_in_container(stf_dir: Path, engine: str, exec=default_exec) -> tuple[str, str]`, which returns `(status, output)` with the status rules from the JS.
- **New behaviour, needed by the version goal in the spec.** The first output line is always `Image: {STUDY_WRANGLER_IMAGE}`. If `image_present` is False, the container is not run, the status is `load-error`, and the output after the `Image:` line is:

```
The image is not present, and this script never downloads it. Ask the user before pulling it (about 6 GB), with one of:
  docker pull veupathdb/study-wrangler:1.0.56
  podman pull docker.io/veupathdb/study-wrangler:1.0.56
```

  The two command lines are built from `pull_commands()`; the version shown is just an example.
- CLI: `stf.py validate <stfDir> [--engine docker|podman]` and `stf.py validate --detect`. The exit codes are as in the JS: 0 pass, 1 fail, 2 error or load-error, 3 no engine. The output is printed, then `Result: {status}`.

- [ ] **Step 1: Write the failing tests.**
  - Port every test in `tests/tabular-container.test.js`. "the image is pinned to one version constant" becomes `STUDY_WRANGLER_IMAGE == f"veupathdb/study-wrangler:{STUDY_WRANGLER_VERSION}"`, with no literal.
  - Mark the fake-docker-on-PATH test `skipif(sys.platform == "win32")`.
  - Keep the integration tests behind `STF_CONTAINER_TESTS=1`. They render the goldens from `spec.json` into `tmp_path` and validate them.
  - Add:

```python
def test_missing_image_prints_pull_commands_and_is_a_load_error(tmp_path):
    def fake(cmd):
        if cmd[1:3] == ["image", "inspect"]:
            raise subprocess.CalledProcessError(1, cmd, "", "No such image")
        raise AssertionError("container must not run")
    status, output = validate_study_in_container(tmp_path, "docker", exec=fake)
    assert status == "load-error"
    assert output.splitlines()[0] == f"Image: {STUDY_WRANGLER_IMAGE}"
    for c in pull_commands():
        assert c in output
```

- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement `_container.py`** and add `validate` to `stf.py`.
- [ ] **Step 4: Run the offline tests.** Expected: PASS.
- [ ] **Step 5: Run the container tests.** `STF_CONTAINER_TESTS=1 uv run --with pytest --with "ruamel.yaml>=0.18" python -m pytest tests/test_container.py -q` should pass, including all three goldens passing baseline and eda on 1.0.56. If the image is missing, stop and report; never pull it.
- [ ] **Step 6: Commit.** "tabular-to-stf: Python container validation and stf.py validate".

---

### Task 11: Scale test

**Files:**
- Create: `tests/test_scale.py`

- [ ] **Step 1: Port `tests/tabular-scale.test.js`.** Keep the same generated data (1M child rows), the same CLI sequence (now `stf.py profile`, `render`, `check`), the `STF_SCALE_TEST=1` switch and a 900 s budget. Print elapsed time and peak memory for each step, using `resource.getrusage(RUSAGE_CHILDREN)` where it is available. There is no memory assertion.
- [ ] **Step 2: Run it.** `STF_SCALE_TEST=1 … pytest tests/test_scale.py -q -s` should PASS within 900 s. Record the timings in the commit message. If it fails on time, profile the slow step and fix that module.
- [ ] **Step 3: Commit.** "tabular-to-stf: Python scale test".

---

### Task 12: Docs

**Files:**
- Modify: `SKILL.md`, `resources/*.md` (not `resources/stf/Study-Transfer-Format-STF.md` or `metadata-fields.md`), `resources/stf/SOURCE.md`, `../README.md`
- Create: `tests/test_docs.py`

**Interfaces:**
- Consumes: `stf.build_parser()`, `STUDY_WRANGLER_VERSION`, the `_constants` value sets.

- [ ] **Step 1: Write the failing tests.** Port `tests/tabular-skill.test.js` to `tests/test_docs.py`, with these changes:
  - The script-mention test finds every `stf.py <subcommand>` in `SKILL.md` and `resources/*.md` (excluding `resources/stf/`). It asserts that the subcommand exists in `build_parser()` and that every `--flag` on the same line is an option of that subcommand. It also asserts that no doc mentions `node `, `.js` or `scripts/lib/`.
  - "SOURCE.md names the pinned study-wrangler version and no other" now imports the constant.
  - Add:

```python
def test_version_number_appears_only_in_source_md():
    hits = [p for p in docs() if STUDY_WRANGLER_VERSION in (SKILL / p).read_text(encoding="utf-8")]
    assert hits == ["resources/stf/SOURCE.md"]
```

- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Rewrite the commands in the docs.**
  - Every command becomes `uv run scripts/stf.py <subcommand> …`.
  - SKILL.md's "Run them with `node`. They need no packages…" becomes "Run them with `uv run`; uv installs the one dependency on first use. They never modify the input files and make no git changes." The script table lists the `stf.py` subcommands.
- [ ] **Step 4: Remove the version numbers from the docs.**
  - SKILL.md and `mode-2-validation.md` say "the pinned study-wrangler image". When `validate` reports that the image is missing, the agent passes the printed pull commands on to the user and says it is about 6 GB.
  - `mode-2-validation.md` describes the new missing-image output instead of the engine's own error text.
  - `curation-notes.md`'s `notes.validation` bullet says "the image shown on the `Image:` line of the validate output".
  - The historical 1.0.53/1.0.54 remark in `variable-metadata.md` stays.
- [ ] **Step 5: Update `SOURCE.md`.** It names `_container.py`'s `STUDY_WRANGLER_VERSION` instead of the JS file, and `tests/test_docs.py` instead of the JS test.
- [ ] **Step 6: Update the README.** In the `tabular-to-stf` Install section: download the release zip, unzip it into the skills directory, install uv, and the recommended `exclude-newer` note, mirroring `veupathdb_database`. In its Development section, give the pytest command and the two opt-in switches. In Releases, both skills are packaged.
- [ ] **Step 7: Run the full suite.** Expected: PASS.
- [ ] **Step 8: Commit.** "tabular-to-stf: docs use stf.py; version only in code and SOURCE.md".

---

### Task 13: Remove the JS and package the skill

**Files:**
- Delete: `package.json`, `scripts/*.js`, `scripts/lib/` (the R script already moved), `tests/*.test.js`
- Modify: `../.github/workflows/release.yml`

- [ ] **Step 1: Delete the JS.** `git rm -r package.json scripts/*.js scripts/lib tests/*.test.js`.
- [ ] **Step 2: Check nothing still refers to the JS.** `git grep -nE "\.js\b|node |npm |scripts/lib" -- tabular-to-stf ../README.md` should return no hits, apart from fixture text that quotes history (if any, leave it).
- [ ] **Step 3: Extend the release workflow.** Add a second zip step to `release.yml`:

```yaml
      - name: Build tabular-to-stf zip
        env:
          TAG: ${{ github.event.release.tag_name }}
        run: zip -r "tabular-to-stf-$TAG.zip" tabular-to-stf -x '*/__pycache__/*' '*.pyc' '*/.pytest_cache/*' 'tabular-to-stf/tests/*'
```

  Add `"tabular-to-stf-$TAG.zip"` to the `gh release upload` line.
- [ ] **Step 4: Verify the zip locally.** Run `cd .. && zip -r /tmp/claude-check.zip tabular-to-stf -x '*/__pycache__/*' '*.pyc' '*/.pytest_cache/*' 'tabular-to-stf/tests/*' && unzip -l /tmp/claude-check.zip`. Expected: `SKILL.md`, `resources/`, `scripts/stf.py`, `scripts/_*.py` and the R script; no `tests/`; no `.js`. Then delete the zip.
- [ ] **Step 5: Smoke-test from the unzipped copy.** Unzip it into a scratch dir and run `uv run <dir>/tabular-to-stf/scripts/stf.py profile tests/fixtures/tabular/mosquito/inputs`. Expected: JSON, exit 0.
- [ ] **Step 6: Run the full verification.** Run the full offline suite, then `STF_CONTAINER_TESTS=1` on the container tests. Expected: all PASS.
- [ ] **Step 7: Commit.** "tabular-to-stf: remove Node.js implementation; release zip".
