# The curation spec

The curation spec is one JSON file. Start the draft once the entity tree is
settled (SKILL.md step 2), outside the output directory (for example
`<work>/curation-spec.json`), and add to it until the first render, which saves
it as `<out>/curation-spec.json`. From then on, that saved copy is the spec:
edit it and re-render from it.
`stf.py render` reads it with the input tables and writes the STF directory.
The spec is the only place where you decide anything: entities, IDs, variable
metadata, the category tree, and every change to the data, as an ordered list
of transforms. Loaders ignore the saved copy, and `study.yaml` does not refer
to it.

## Schema

```jsonc
{
  "specVersion": "1.1.0",                  // see "Spec version" below
  "study": { "name": "string", "description": "string?" },
  "inputDir": "path, relative to the spec file or absolute",   // the saved copy in <out> always says "raw-data" unless --no-raw-data
  "extraFiles": ["dictionary.xlsx", "description.md"],        // optional; other supplied files (data dictionary, study description), relative to inputDir, copied into raw-data/ too
  "entities": [{
    "name": "participant",                 // /^[a-z][a-z0-9_]*$/, unique
    "displayName": "Participant", "displayNamePlural": "Participants",
    "file": "participants.csv",
    "idColumn": "participant_id",          // header after renames
    "idName": "participant_id",            // optional output name for the ID column; same rules as variable "name"
    "parent": "household",                 // omitted for the root; exactly one root
    "parentColumn": "household_id",
    "geo": { "latitude": "lat", "longitude": "lon" },   // optional
    "variables": [{
      "column": "age",                     // header after renames
      "name": "age_years",                 // optional output name; default toColumnName(column); must pass isValidColumnName
      "displayName": "Age",
      "dataType": "integer", "dataShape": "continuous",  // optional: inferred if absent
      "unit": "years", "definition": "…",
      "ordinalLevels": ["low","mid","high"], "vocabularyOrder": ["No","Yes"],
      "isMultiValued": false, "multiValueDelimiter": ",",
      "parentCategory": "demographics", "stableId": "…", "displayType": "…",
      "providerLabel": "…"                 // optional; overrides the original header as provider_label (see Geo below)
    }],
    "categories": [{ "category": "demographics", "displayName": "Demographics", "definition": "…", "parentCategory": "…?" }]
  }],
  "transforms": [ /* ordered; see below */ ],
  "notes": { "flagged": ["…"], "decisions": ["…"], "pii": ["…"], "validation": ["…"] }
}
```

## Spec version

`specVersion` is a version string, `MAJOR.MINOR.PATCH`. Write new specs with
the version in the schema above, which is the one these scripts support. The
scripts read any spec with the same major version and a version no newer than
theirs, and refuse others with a message naming both versions. A minor
version adds ops or fields, a patch only clarifies without changing
behaviour, and a major version removes something or changes what it means.
Version 1.1.0 added `match` (see Transforms).

## Allowed values

Allowed values, which are the same ones `stf.py check` enforces:

- `dataType`: `string`, `number`, `integer`, `date`, `longitude`
- `dataShape`: `continuous`, `categorical`, `ordinal`, `binary`
- `displayType`: `default`, `multifilter`, `geoaggregator`, `latitude`, `longitude`

## Transforms

Every transform has `op`, `entity`, `reason` and `approval` (`"auto"` | `"user"` | `"proposed"` | `"rejected"`), plus `instead` (string) when `rejected`. `proposed` and `rejected` are not applied.

| op | fields | `auto` allowed |
|---|---|---|
| `trim` | `columns?` (default all) | yes |
| `blank-placeholders` | `columns?`, `values`, `match?` | only if `values ⊆ UNAMBIGUOUS_PLACEHOLDERS` and not regex |
| `map-values` | `column`, `map` `{from: to}`, `match?` | yes, unless regex (the skill docs restrict it to the same value written differently: case, whitespace, conventional abbreviations, dictionary-defined codes; typos and similarity matches are `user`) |
| `rename-column` | `from`, `to` | yes |
| `replace-cells` | `column`, `cells: [{ id, from, to }]` | no |
| `parse-dates` | `column`, and either `format` or `formats` (a list) (tokens `DD`, `D`, `MM`, `M`, `YYYY`, `YY`, any separators) | no |
| `derive-column` | `column` (new), `from`, `map`, `default`, `match?` | no |
| `drop-column` | `column` | no |

`UNAMBIGUOUS_PLACEHOLDERS` are `NA`, `N/A`, `n/a`, `na`, `-`, `--`, `.`,
`null` and `NULL`.

`match` (spec version 1.1.0 or later) is `"exact"`, the default, or
`"regex"`. With `"regex"`, the `map` keys (or `values`) are Python regular
expressions, and the transform's `approval` may not be `auto`. See below for
how they match.

What the approvals mean:

- `auto`: routine normalisation. It is applied, and listed under
  "Routine normalisation" in the notes.
- `user`: the user approved it. It is applied, and listed under
  "Data changes".
- `proposed`: waiting for an answer. It is not applied, and is listed as
  "Proposed, not applied".
- `rejected`: the user said no. It is not applied, and is listed with its
  `instead`.

## Previewing a transform

`uv run scripts/stf.py preview <spec.json> <n> [--top N] [--bottom N]` shows
what `transforms[n]` does, whatever its `approval`, and writes nothing. It
first runs that entity's earlier `auto` and `user` transforms, so it sees the
cells the transform will see. For `map-values`, `derive-column` and
`blank-placeholders` it lists, per column, the values it changes (with the
result and, for regex, the key), every ambiguous value, and the values it
leaves alone (with `derive-column`'s default). Lists are cut to the `--top`
most and `--bottom` least common values (10 each by default), with a line
counting the rest. For other ops it gives the number of cells changed, the
columns before and after, or why the transform fails.

## How the renderer reads the spec

These rules are what `stf.py render` actually does. They are not all
visible in the schema.

**Transforms run in order, one entity table at a time, on copies of the
input.** A transform names a column as it is at that point in the list:
before a `rename-column`, use the old header, and after it, the new one.
`variables[].column`, `idColumn` and `parentColumn` use headers after all
transforms.

- `trim` and `blank-placeholders` match whole cells exactly, so put `trim`
  first when a placeholder has stray spaces (`"NA "`).
- `map-values` replaces whole cells that equal a key. Other cells are left
  alone.
- With `"match": "regex"`, a key matches a cell when the pattern matches the
  **whole** cell (`\d+` does not match `40?`). Empty cells are matched like
  any other. In a `map` value, `$1`, `$2`, … insert what that group captured
  (`$10` is group 10), a group that took no part gives an empty string, and
  `$$` is a literal `$`. Any other `$` is a spec error, as is a group the
  pattern does not have. Backslashes in a value are literal. Without regex,
  `map` values are literal text, `$` included. `derive-column`'s `default`
  is always literal.
- A cell that two keys match with **different** results fails the render,
  listing the row IDs and values (the first ten of each, then how many
  more). Keys that agree are fine. Tighten the patterns, or settle those
  cells with `replace-cells` first. `stf.py preview` lists every ambiguous
  value, with counts.
- `replace-cells` finds rows by the value in the entity's `idColumn`. It
  fails if a row ID is missing or a cell no longer holds `from`, which means
  the spec is stale. Re-profile and fix the spec, do not force it.
- `parse-dates` turns every non-empty cell into `YYYY-MM-DD`. Cells that
  are already valid `YYYY-MM-DD` dates are left as they are, so a column
  that is only partly ISO needs just the other formats. `YY` always means
  20YY. It fails, listing the row IDs (the first ten, then how many more),
  if a cell matches none of the formats
  (and is not ISO) or is not a real date (`31/02/2023`). It also fails if two
  formats, or a format and ISO, read a cell as different dates (`03/04/23`
  under both `DD/MM/YY` and `MM/DD/YY`). Settle those cells with
  `replace-cells` first.
- `derive-column` adds a column, using `map[value]` for each value of `from`
  and `default` for everything else. It reads `from` as it is at that point,
  so put it **before** any transform that changes those values. For example,
  derive `age_censored` from `80+` before replacing `80+` with `80`.
- `drop-column` removes the column from the output. `raw-data/` still has
  it.

**Every column must be accounted for.** Each column left after the
transforms, apart from the ID and parent ID columns, must be listed in
`variables` or removed with `drop-column`. Otherwise the render fails with
`unaccounted column`.

**Output names.**

- A variable's output name is `name` if given, otherwise the header in
  snake case: `Age (years)` becomes `age_years`, and a name starting with a
  digit gets an `x` prefix.
- Automatic names that clash get `_2`, `_3` suffixes. Explicit names that
  clash are an error.
- An explicit `name` or `idName` must be letters, digits and `_`, starting
  with a letter.
- In each child file, the parent ID column is written under the parent's
  own output ID name.

**`provider_label`** is the original input header of the column, followed
through any renames. A derived column has none. Set `providerLabel` to
override it. That is only needed for the geo case in
[variable-metadata.md](variable-metadata.md#geocoordinates).

**Defaults.**

- `dataType` is inferred from the values after the transforms:
  - integer if every value is a whole number;
  - number if every value is numeric;
  - date if every value is `YYYY-MM-DD`;
  - otherwise string.
  - A value with a leading zero (`007`) makes the column a string.
- A declared `dataType` is checked: every non-empty value must parse as
  that type. Otherwise the render fails, listing the rows.
- `dataShape` is `ordinal` if `ordinalLevels` is set, `categorical` for
  strings, and otherwise `continuous`. `binary` is never inferred, so set
  it.
- `displayName` defaults to the provider label, and then to the output name.

**Geo.** For the two columns named in `geo`:

- The renderer sets `data_type`, `data_shape`, `stable_id` and
  `display_type`. Do not set them yourself.
- It names the column `latitude` or `longitude` when its name would not be
  recognised by both EDA rules, and records that in the notes.
- Both columns must be listed in `variables`.

**Notes.**

- `notes.flagged` and `notes.pii` (prefixed `PII:`) go under "Flagged, not
  changed".
- `notes.decisions` go under "Decisions and answers", followed by the lines
  the renderer adds itself (geo renames and `providerLabel` overrides).
- `notes.validation` goes under "Validation". When it is empty, that section
  says "Not run (mode 1)".

## Rendering

```bash
uv run scripts/stf.py render <work>/curation-spec.json <out>                # first render, into a new or empty <out>
uv run scripts/stf.py render <out>/curation-spec.json <out>                # every later render
uv run scripts/stf.py render <out>/curation-spec.json <out> --no-raw-data
```

- `stf.py render` validates the spec, applies the transforms and checks the
  result before it writes anything. On failure it prints every problem as a
  `- ` line and exits 1.
- It refuses an output directory that is not empty unless that directory
  already holds a `curation-spec.json`. It also refuses if a file in
  `raw-data/` differs from the input of the same name.
- It overwrites `study.yaml`, the entity files and `curation-notes.md` on
  every run. It does not delete the files of an entity you removed from the
  spec, so delete those yourself.
- The saved `curation-spec.json` is the spec you gave, with `inputDir`
  rewritten to `raw-data`, or to the absolute input path with
  `--no-raw-data`.
- `extraFiles` must be inside `inputDir`.
