# tabular-to-stf: port from Node.js to Python/uv — design

Date: 2026-11-05. Branch: `new-skill-generic-to-stf`.

## Intent

`tabular-to-stf` came from an internal, staff-facing repo where Node.js was a
given. It is now meant for outside users, alongside `veupathdb_database`,
which is Python run through `uv`. Claude Code installs as a standalone binary,
so a typical Mac or Windows user may have neither Node nor Python; `uv` gets
them a Python and the script's packages with no install step. One toolchain
for both skills means one set of install instructions and one way of running
scripts. Nobody has used the skill in the wild yet, so there are no users to
migrate.

## Goals

- Replace every Node.js script with Python, run as `uv run scripts/stf.py
  <subcommand>`, following the `veupathdb_database` pattern.
- Keep the skill's behaviour: the same curation spec format (`specVersion: 1`,
  same fields, same transforms and rules), the same checks, the same STF
  meaning, the same exit codes, the same safety rules (inputs never modified,
  no git changes, container never pulls).
- Ship the skill as a release zip, like `veupathdb_database`.
- (Minor) Make a study-wrangler version bump a one-line change. Today
  `1.0.56` is written out in seven files. After the port it appears in only
  two places:
  1. the version constant in the container module, which is the single
     source of truth;
  2. `resources/stf/SOURCE.md`, which records which tag the bundled docs
     were copied from. A test checks it against the constant, so a bump
     that forgets to re-copy the docs fails.

  Everywhere else gets the version from the script, not the docs:
  - `stf.py validate` prints the image it used in its output, and the agent
    copies that into `notes.validation`.
  - When the image is missing, `stf.py validate` prints the exact
    `docker pull` / `podman pull` commands, built from the constant.
    `SKILL.md` and `mode-2-validation.md` say "the pinned image" and tell
    the agent to pass those commands on to the user.
  - `curation-notes.md` (the resource) says "the study-wrangler version
    shown in the validate output".
  - Code comments say "the pinned study-wrangler version".
  - Tests import the constant rather than repeating the literal.

  Historical records stay as written, because they say which version was
  actually run: validation lines in the fixture specs and notes, and the
  1.0.53/1.0.54 bug-fix remarks in `variable-metadata.md` and the
  coffee-shops fixture.

## Non-goals

- Byte-for-byte identical output to the Node version. YAML formatting, number
  formatting and key order inside a mapping may change, as long as the meaning
  is the same and the container validates it.
- Changes to what the skill does (new transforms, new modes, mode 3).
- Shipping the worked examples to users. `tests/fixtures/tabular/*` are test
  data only, and the skill docs no longer mention them (done in `5d1927b`).

## Anti-goals

- Silent changes to the data. A value that reaches the STF differently from
  the Node version (a `yes` that became `true`, `007` that became `7`, a float
  that gained or lost digits) is a bug, even if the container accepts it.
- A heavier install than needed: no pandas or other data-frame library.

## Decisions taken

**One CLI with subcommands**, `scripts/stf.py`, so users approving tool calls
by hand see one command shape. Subcommands map one-to-one onto the current
scripts and keep their arguments and flags:

| New | Old |
|---|---|
| `stf.py profile <inputDir> --out <path>` | `profile-tables.js <inputDir> --out <path>` |
| `stf.py profile <inputDir> --file <name> [--top N]` | `profile-tables.js <inputDir> --file <name> [--top N]` |
| `stf.py render <spec.json> <outDir> [--no-raw-data]` | `render-stf.js …` |
| `stf.py check <stfDir> [--json]` | `check-stf.js …` |
| `stf.py validate <stfDir> [--engine docker\|podman]` | `validate-stf-in-container.js …` |
| `stf.py validate --detect` | `validate-stf-in-container.js --detect` |

Helpers live beside it as `_`-prefixed modules (e.g. `_profile.py`,
`_render.py`, `_check.py`, `_spec.py`, `_transforms.py`, `_geo.py`,
`_notes.py`, `_read_table.py`, `_container.py`), imported from the script's
own directory as `veupathdb_database` does. The R script
`study-wrangler-validate-study.R` is kept unchanged.

**Libraries.** `stf.py` carries a PEP 723 header (`requires-python >= 3.11`,
`dependencies = ["ruamel.yaml"]`).
- YAML read and write with `ruamel.yaml` (YAML 1.2: `yes`/`no`/`on`/`off`
  stay strings; key order is kept). This replaces the hand-written
  `yaml-lite.js` reader and the hand-written YAML emitter in the renderer.
  The renderer must not depend on readers being YAML 1.2: study-wrangler
  reads YAML with R's `yaml` package (YAML 1.1). Keep today's quoting rules
  from `yamlScalar` in `stf-common.js` exactly — empty, edge whitespace,
  `: `, ` #`, leading indicator characters, anything numeric-looking, and
  `true|false|null|yes|no|on|off|y|n|~` in any case are quoted — by forcing
  quoting in ruamel's emitter rather than relying on its 1.2 defaults.
  *(Designer's call, from the builder check.)*
- CSV/TSV with the standard library `csv` module (opened with
  `encoding="utf-8-sig"`, `newline=""`). TSV keeps today's rule of no quoting
  (`csv.QUOTE_NONE`, or a plain split). Today's reader behaviour is the
  spec: no trimming, BOM stripped, `\r\n` accepted, trailing empty lines
  dropped, earlier empty lines kept as rows, errors naming file and line.

**Reading STF YAML in `check`** (decided by the user after the builder
check). `check` also reads STF that a person wrote or hand-edited (mode 2),
and a pass is meant to promise that study-wrangler, which reads YAML 1.1 via
R's `yaml` package, will load it. So `check` does not take ruamel's YAML 1.2
typing:
- ruamel parses with every scalar as a string (e.g. `typ="base"`).
- A small layer then applies today's `yaml-lite.js` typing (`plainValue`):
  empty, `null` and `~` become null; `true`/`false` (any case) become booleans;
  `-?\d+` and `-?(\d+\.\d+|\.\d+)` become numbers; everything else, including
  `yes`/`no`, `1e3` and `2024-01-01`, stays text. Quoted scalars are always
  text.
- The YAML features `yaml-lite` rejected (anchors, aliases, tags, multiple
  documents, flow mappings with content) are still rejected as errors.
- New: a `WARNING:` for any unquoted scalar that YAML 1.1 would read as
  something other than the text (`yes`/`no`/`on`/`off`/`y`/`n` in any case,
  and other 1.1-only forms such as sexagesimal `1:30`), telling the user to
  quote it.
- The `yaml-lite` tests for typing and for what it rejects are ported to this
  layer. Only the tests about its hand-written parser internals are dropped.

Data cells (CSV/TSV in, TSV out) are text throughout. Type inference only
decides `data_type`, and a cell such as `1e3` is written out exactly as it
came in.

**Container.** `veupathdb/study-wrangler:1.0.56` stays the single pinned
version constant (now in Python). Same `docker`/`podman run --rm
--pull=never` with read-only mounts, same marker-line parsing
(`STF_LOAD_ERROR:`, `STF_VALIDATION_ERROR:`), same statuses and exit codes.
Detection order: docker, then podman.

**Removal.** The JS scripts, `scripts/lib/`, `tests/*.test.js` and
`package.json` are deleted in the same change. No compatibility shims.

**Docs.** Every command in `SKILL.md` and `resources/*.md` is rewritten to
the `uv run scripts/stf.py …` form, and the "Run them with `node`. They need
no packages" line becomes a `uv` equivalent. The README's install and
development sections for this skill are rewritten to match
`veupathdb_database` (install uv; recommended `exclude-newer`; tests with
`uv run --with pytest …`).

**Release.** `.github/workflows/release.yml` also builds
`tabular-to-stf-$TAG.zip`, excluding `tests/`, `__pycache__`, `*.pyc` and
`.pytest_cache`, and attaches it to the release. The README's "no release
zip yet" line goes.

## Testing

- pytest, run as `uv run --with pytest --with ruamel.yaml python -m pytest
  tests -q` from `tabular-to-stf/`, with a `conftest.py` that puts `scripts/`
  on `sys.path`.
- Port the JS tests by behaviour, not line by line: each current `test(...)`
  becomes one or more pytest tests asserting the same behaviour. The
  `yaml-lite.js` tests are handled as described under "Reading STF YAML in
  `check`". Add round-trip tests for the
  values that matter (`yes`, `no`, `NA`, `007`, `1e3`, `2023-01-01`, strings
  with `:` or `#`, empty), checking that the renderer's output reads back as
  the same text under both the `check` reader and a YAML 1.1 reader.
- Golden fixtures (`clinical-epi`, `mosquito`, `coffee-shops`): render each
  `spec.json` and compare with `expected/` by content — YAML files parsed and
  compared as data, TSVs compared cell by cell as strings, `curation-notes.md`
  and `curation-spec.json` compared as text/JSON. The builder may regenerate
  the `expected/` directories from the Python renderer (at least once is
  unavoidable: `curation-notes.md` names the render command, which becomes
  `uv run scripts/stf.py render …`). Before regenerating, the content
  comparison must pass apart from known, explained differences; the commit
  that regenerates them lists those differences in its message, and the
  container tests must pass on the regenerated output. No stop for human
  review. *(Designer's call.)*
- The docs test (`tabular-skill.test.js`) is ported, adapted to check that
  every `stf.py <subcommand> --flag` in the docs exists in the argparse
  definition.
- Opt-in groups keep their switches: `STF_CONTAINER_TESTS=1` (needs the
  pinned image) and `STF_SCALE_TEST=1` (1M child rows). A straight port is
  fine: the only limit is the existing 900-second timeout, there is no
  memory limit and the scale test does not run in CI. Report time and peak
  memory as the Node test does. *(Designer's call.)*
- Done means: full suite green, and the container tests green on 1.0.56,
  including all three goldens passing baseline+eda.

## Constraints

- Python ≥ 3.11 (matches `veupathdb_database`).
- Must work on Linux, macOS and Windows for profile/render/check. Use
  `pathlib`; no shell-outs except the container engine.
- Scale: 1M-row child tables must still profile, render and check (the
  current scale test).

## Left to the builder

- Module boundaries within `scripts/`, and internal function names.
- Whether the port goes module by module behind the golden tests, or all at
  once.
- How `--json` output and error message wording are produced, as long as the
  content and exit codes are the same and the docs stay accurate.
