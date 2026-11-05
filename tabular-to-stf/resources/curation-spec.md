# The curation spec

The curation spec is one JSON file. Draft it outside the output directory
(for example `<work>/curation-spec.json`) for the first render, which saves
it as `<out>/curation-spec.json`. From then on, that saved copy is the spec:
edit it and re-render from it.
`render-stf.js` reads it with the input tables and writes the STF directory.
The spec is the only place where you decide anything: entities, IDs, variable
metadata, the category tree, and every change to the data, as an ordered list
of transforms. Loaders ignore the saved copy, and `study.yaml` does not refer
to it.

For complete examples, see `clinical-epi/spec.json`, `mosquito/spec.json` and
`coffee-shops/spec.json` in the worked examples (see SKILL.md).

## Schema

```jsonc
{
  "specVersion": 1,
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

Allowed values, which are the same ones `check-stf.js` enforces:

- `dataType`: `string`, `number`, `integer`, `date`, `longitude`
- `dataShape`: `continuous`, `categorical`, `ordinal`, `binary`
- `displayType`: `default`, `multifilter`, `geoaggregator`, `latitude`, `longitude`

## Transforms

Every transform has `op`, `entity`, `reason` and `approval` (`"auto"` | `"user"` | `"proposed"` | `"rejected"`), plus `instead` (string) when `rejected`. `proposed` and `rejected` are not applied.

| op | fields | `auto` allowed |
|---|---|---|
| `trim` | `columns?` (default all) | yes |
| `blank-placeholders` | `columns?`, `values` | only if `values ⊆ UNAMBIGUOUS_PLACEHOLDERS` |
| `map-values` | `column`, `map` `{from: to}` | yes (the skill docs restrict it to the same value written differently: case, whitespace, conventional abbreviations, dictionary-defined codes; typos and similarity matches are `user`) |
| `rename-column` | `from`, `to` | yes |
| `replace-cells` | `column`, `cells: [{ id, from, to }]` | no |
| `parse-dates` | `column`, `format` (tokens `DD`, `D`, `MM`, `M`, `YYYY`, any separators) | no |
| `derive-column` | `column` (new), `from`, `map`, `default` | no |
| `drop-column` | `column` | no |

`UNAMBIGUOUS_PLACEHOLDERS` are `NA`, `N/A`, `n/a`, `na`, `-`, `--`, `.`,
`null` and `NULL`.

What the approvals mean:

- `auto`: routine normalisation. It is applied, and listed under
  "Routine normalisation" in the notes.
- `user`: the user approved it. It is applied, and listed under
  "Data changes".
- `proposed`: waiting for an answer. It is not applied, and is listed as
  "Proposed, not applied".
- `rejected`: the user said no. It is not applied, and is listed with its
  `instead`.

## How the renderer reads the spec

These rules are what `render-stf.js` actually does. They are not all
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
- `replace-cells` finds rows by the value in the entity's `idColumn`. It
  fails if a row ID is missing or a cell no longer holds `from`, which means
  the spec is stale. Re-profile and fix the spec, do not force it.
- `parse-dates` turns every non-empty cell into `YYYY-MM-DD`. It fails,
  listing the row IDs, if any cell does not match `format` or is not a real
  date (`31/02/2023`).
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
node scripts/render-stf.js <work>/curation-spec.json <out>                # first render, into a new or empty <out>
node scripts/render-stf.js <out>/curation-spec.json <out>                # every later render
node scripts/render-stf.js <out>/curation-spec.json <out> --no-raw-data
```

- `render-stf.js` validates the spec, applies the transforms and checks the
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
