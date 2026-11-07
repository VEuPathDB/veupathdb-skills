# tabular-to-stf: regex transforms, transform preview, semver spec

Date: 2026-11-06. Branch: `improvements-round-1`. Skill: `tabular-to-stf/`.

## Why

Every value-matching transform in the curation spec matches whole cells by
exact string equality. That is fine for `y`/`yes`/`YES`, but the
"Uncertain values" pattern added on this branch (`40?`, `~35` → keep the
number, add `<variable>_uncertain`) needs one `map` entry per distinct value.
With many values the agent either writes a long hand-computed map or gives
up (the coffee-shops run kept the uncertainty only in the notes).

Regex keys with capture groups solve this, but a regex can match more than
intended. So regex transforms always need the user's approval, and the user
is shown exactly what a regex matches before approving. The preview is a
new `stf.py` sub-command, and the skill docs make running it part of the
approval step.

The spec version is a bare integer `1` checked by equality. Adding regex is
a spec change, so the version moves to semver now, while no specs exist
outside this repo.

## Goals

- Optional regex matching on `map-values`, `derive-column` and
  `blank-placeholders`.
- `$1`-style capture-group references in replacement values.
- A `stf.py preview` sub-command that shows what one transform does to the
  data, for any transform, regex or not.
- Semantic versioning for `specVersion`, with a clear compatibility rule.
- Skill docs that route regex transforms through `proposed` → preview →
  user approval, and use regex for uncertain values.

## Non-goals

- Regex on `replace-cells` (matches by row ID), `trim`, `rename-column`,
  `drop-column` or `parse-dates` (has its own format tokens).
- Substring search-and-replace. Patterns still match whole cells.
- Detecting "strange" values in the tool. The agent judges that from the
  preview output.
- Migrating old specs. There are none in the wild.

## Anti-goals

- A regex transform applied without the user seeing its preview.
- Key order in a map silently deciding which replacement a cell gets.

## Design

### Spec version (semver)

- `specVersion` becomes a semver string, `"MAJOR.MINOR.PATCH"`. The integer
  `1` is no longer valid.
- The current format (including `parse-dates` `formats`, added earlier on
  this branch) is retroactively `1.0.0`. This change makes it `1.1.0`.
- `_spec.py` gets one constant, `SPEC_VERSION = "1.1.0"`. A spec is accepted
  when its major version equals the code's and its version is not newer than
  the code's. Errors name both versions, e.g. `specVersion: this spec needs
  1.2.0, these scripts support up to 1.1.0` or `specVersion: major version 2
  is not supported (these scripts support 1.x, up to 1.1.0)`. A non-semver
  value is `specVersion: must be a version string like "1.1.0"`.
- Compatibility rule (document in `curation-spec.md`): within a major
  version, newer code reads every older spec. Minor adds ops or fields;
  patch is for clarifications that change no behaviour; major removes or
  changes the meaning of something.
- The skill writes new specs with the current `SPEC_VERSION`. Update the
  schema example, test fixtures (`tests/fixtures/tabular/*/spec.json` and
  `expected/curation-spec.json`) and tests that set `specVersion`.
- Specs that use no 1.1.0 feature may still say `1.0.0`; nothing requires
  the lowest sufficient version. (Builder's call whether validation warns
  when a 1.0.0 spec uses `match` — see below.)

### `match: "regex"`

- `map-values`, `derive-column` and `blank-placeholders` take an optional
  `match`: `"exact"` (default) or `"regex"`. With `"regex"`, the `map` keys
  (or `values` entries) are patterns.
- Syntax is Python `re`. A pattern must match the **whole cell**
  (`re.fullmatch`), the same rule as exact matching, so `^`/`$` are not
  needed.
- Replacement values (`map` values in `map-values` and `derive-column`) may
  use `$1`, `$2`, … for capture groups, and `$$` for a literal `$`. With
  `match: "exact"`, `$` has no special meaning (values are unchanged from
  1.0.0 behaviour). `default` in `derive-column` is literal.
- **`$` edge cases** (Claude's call): `$` followed by digits takes all the
  digits (`$10` is group 10); a group that did not take part in the match
  gives `""`; `$` followed by anything other than a digit or `$`, or a
  trailing `$`, is a validation error.
- **Ambiguity:** if a cell fully matches more than one key **and those keys
  give different results** (after `$n` substitution), the render fails and
  lists the row IDs (and values), as `parse-dates` does for cells two
  formats read differently. Keys that agree are fine (e.g. several flag
  patterns all mapping to `"1"`), so `blank-placeholders` is never
  ambiguous. (Claude's call, matching the anti-goal: order only matters when
  results differ.) Settle real ambiguity by tightening the patterns or with
  `replace-cells` first.
- **Validation errors** (in `validate_spec`): `match` not `"exact"`/`"regex"`;
  a pattern that does not compile (include the `re.error` message); a `$n`
  reference to a group the pattern does not have; `match` used on any other
  op; `approval: "auto"` with `match: "regex"` (use `"user"`).
- Notes: regex transforms appear under "Data changes" like any `user`
  transform; the existing row-ID listing applies.

Uncertain values then look like this (in this order):

```json
{ "op": "derive-column", "entity": "participant", "column": "age_uncertain",
  "from": "age", "match": "regex", "map": { "~.*|.*\\?": "1" }, "default": "0",
  "reason": "...", "approval": "user" },
{ "op": "map-values", "entity": "participant", "column": "age",
  "match": "regex", "map": { "(\\d+)\\?": "$1" }, "reason": "...", "approval": "user" },
{ "op": "map-values", "entity": "participant", "column": "age",
  "match": "regex", "map": { "~(\\d+)": "$1" }, "reason": "...", "approval": "user" }
```

(One op per marker is the recommended style: simpler patterns, simpler
previews.)

### `stf.py preview`

```
Usage: stf.py preview <spec.json> <n> [--top N] [--bottom N]
```

- `<n>` is the transform's 0-based index in `transforms`, matching the
  `transforms[n]` paths in spec errors.
- Validates the spec, reads that transform's entity table from `inputDir`,
  applies the earlier `auto`/`user` transforms for that entity in order (as
  `render` would), then evaluates transform `n` **whatever its approval**.
  It writes nothing.
- Output for value-matching ops (`map-values`, `derive-column`,
  `blank-placeholders`), grouped by distinct cell value with cell counts,
  **per column** (`blank-placeholders` over several columns prints one
  section per column; Claude's call, so `--bottom` stays useful):
  - **Matched:** `value → result  ×count` (and which key matched, for regex).
  - **Ambiguous:** values matching more than one key, with the keys. Never
    capped.
  - **Unmatched:** values left as they are (for `derive-column`, given
    `default`). Empty cells are counted on one line, not listed as a value.
  - Matched and unmatched lists show the `--top N` most common and the
    `--bottom N` least common distinct values (defaults are the builder's
    call; 10 each is a reasonable start), without repeating a value that
    falls in both. Each list ends with a totals line, e.g.
    `… 1,212 more distinct values (4,870 cells)`; when nothing is hidden,
    the totals still say how many distinct values and cells the list has.
- For other ops, preview prints a short, useful summary (e.g. cells changed,
  columns added/removed, `parse-dates` failures). Exact format is the
  builder's call; it must not crash on any valid op.
- Exit code: 0 when the preview ran (ambiguity is shown, not an error);
  non-zero for an invalid spec, bad index, or a failure in an earlier
  transform (report it like `render` would).
- Human-readable text output. A `--json` flag is optional, builder's call.

### Skill documentation

- **Spec drafted earlier (user's decision).** Today `SKILL.md` writes the
  first draft of the spec at step 7, but preview needs a spec during step 3.
  Move the first draft to the end of step 2: once the entity tree is
  settled, write `<work>/curation-spec.json` with `specVersion`, `study`,
  `inputDir`, and the entities (name, display names, `file`, `idColumn`,
  `parent`/`parentColumn`, `variables: []`). Such a skeleton already passes
  `validate_spec`. Step 3 adds transforms to it; steps 4–6 fill variables,
  geo and categories into it (or are collected and written in — builder's
  call on wording, but the spec file exists from step 2 on); step 7 becomes
  "finish the spec and render". The `<work>` draft → `<out>` saved-copy
  handover after the first render is unchanged. Check the step 2 text,
  step 7 text, the opening workflow summary and any references in
  `resources/` (e.g. `curation-spec.md`'s opening paragraph) for wording
  that assumes the spec is written last.
- `SKILL.md` step 3 (Cleaning): regex transforms are drafted as
  `proposed`, previewed with `stf.py preview`, shown to the user (the
  preview table, or the relevant part of it), and set to `user` only when
  they accept; `rejected` with `instead` otherwise. Using `--bottom` to look
  for rare values the pattern missed is part of reading the preview.
  Previewing exact-match transforms before asking is encouraged.
- `cleaning.md`: "Uncertain values" uses the regex recipe above (derive the
  flag first, then one `map-values` per marker). Mention regex as the tool
  when a map would need many keys that share a shape.
- `curation-spec.md`: `specVersion` semver and compatibility rule; `match`
  in the transforms table; `$n`/`$$`; whole-cell matching; the ambiguity
  rule; the "never `auto`" rule; the `preview` sub-command.
- The `stf.py` usage text and any doc listing sub-commands include
  `preview`. `tests/test_docs.py` may need updating if it checks these.

## Testing

TDD, in the existing `tests/` style:

- `test_spec.py`: semver acceptance and each rejection; `match` validation
  (bad value, wrong op, bad pattern, bad group reference, regex + `auto`).
- `test_transforms.py`: regex `map-values` with `$1` and `$$`;
  `derive-column` regex with default; `blank-placeholders` regex; whole-cell
  semantics (`\\d+` does not match `40?`); ambiguity failure with row IDs;
  exact mode unchanged, including a literal `$1` value.
- Preview: matched/ambiguous/unmatched grouping, top/bottom capping and
  totals, earlier transforms applied, `proposed` transform previewed,
  non-value ops don't crash, bad index.
- Fixtures and golden outputs updated for `"specVersion": "1.1.0"`.

## Left to the builder

- Module layout (e.g. a `_preview.py`), shared code between render and
  preview for running the earlier transforms.
- Default `--top`/`--bottom` values and exact output layout.
- Whether to warn when a spec declares an older minor than the features it
  uses.
