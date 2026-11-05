# Variable metadata

Every column except the ID and parent ID columns becomes a variable in the
spec (`entities[].variables[]`, see [curation-spec.md](curation-spec.md)). The
full field reference is in [metadata-fields.md](stf/metadata-fields.md). This
page says, for each field, when to infer it, when to ask, and when to leave it
blank.

Sources, in order of trust:

1. What the user tells you.
2. The data dictionary.
3. The study description.
4. The data, as seen in the profile.
5. Your own knowledge of the field.

Never contradict a dictionary silently. If the data disagrees with it, for
example a unit of `mg/dL` but values in the range of `g/dL`, ask.

## Asking questions

Collect the open questions for one entity and ask them **in one message**, as
a numbered list. Give your best guess for each, so the user can answer "yes
to all but 3". Never ask one prompt per column. Ask only about what matters:

- a unit missing on a number;
- the order of ordinal levels;
- the meaning of a code;
- a definition the dictionary does not give, for a variable whose name does
  not explain it.

## Fields

| Spec field | Infer when | Ask when | Leave blank when |
|---|---|---|---|
| `displayName` | always: a short, plain-English label without the unit, e.g. `Weight` for `Weight (kg)` | the header is a code (`q17b`) and nothing explains it | never: it defaults to the original header, which is often fine |
| `name` | the snake-case default (`Age (years)` → `age_years`) is clumsy, misleading or clashes, e.g. `age` | never | the default is fine |
| `dataType` | the data is clear. Set it explicitly when the inferred type is wrong, e.g. identifiers and codes made of digits (phone extensions, PubMed IDs, site codes `1`/`2`/`3`) are `string` with `dataShape` `categorical`, or a number column that should be `number` although the current values are whole | a column could be a code or a quantity | the default inference is right |
| `dataShape` | `binary` for a two-valued column (`Yes`/`No`, `Positive`/`Negative`). It is never inferred, so set it. `ordinal` when `ordinalLevels` is set | a number could be a scale or a set of codes | the default is right: `categorical` for strings, `continuous` for numbers and dates |
| `ordinalLevels` | the dictionary gives the order, or it is obvious (`none` < `primary` < `secondary` < `tertiary`) | the order is not obvious | not ordinal |
| `vocabularyOrder` | a natural order exists: `Yes` before `No`, `Positive` before `Negative`, `Female`/`Male` as in the dictionary | rarely | there is no natural order |
| `unit` | the header or dictionary gives it (`Weight (kg)` → `kg`) | a number has no unit anywhere and plainly needs one | not `number`, `integer` or ordinal; or unitless (counts, scores, ratios) |
| `definition` | the dictionary or description says what it is | the variable is important and unclear | nothing reliable is known: it is optional |
| `isMultiValued`, `multiValueDelimiter` | cells hold several values (`fever;cough`) | the delimiter is unclear | single-valued |
| `parentCategory` | see [category-tree.md](category-tree.md) | | the entity has no category tree |
| `stableId` | you know the right ontology term | | almost always: the loader makes one |
| `displayType` | | | almost always: `default` is implied. The renderer sets geo columns itself |
| `providerLabel` | only for the geo case below | | almost always: the original header is used |

Rules that are enforced locally, by `render-stf.js` or `check-stf.js`:

- **A declared `dataType` must fit every value.** The renderer checks every
  whole cell, so a multi-valued column must stay `string`. `check-stf.js`
  checks values against the YAML type as well.
- **`dataShape` `ordinal` needs `ordinalLevels`.** For a **string** ordinal,
  `check-stf.js` also reports any value missing from the levels. For an
  integer ordinal it only checks that the values are integers.
- **Allowed values.** `dataType`, `dataShape` and `displayType` must be
  among the allowed values.
- **Geo values.** Latitudes must be in −90…90 and longitudes in −180…180.

Rules that only study-wrangler's `validate()` catches, in mode 2. Get these
right in the spec, because mode 1 will not warn you:

- `ordinalLevels` must list **every** value in the column, after the
  transforms. The loader silently turns an unlisted value into a missing
  value. Check against the profile's `top` and `distinctCount`. This matters
  most for integer ordinals, which `check-stf.js` does not check against the
  levels.
- `vocabularyOrder` is only for `categorical` or `binary` variables, and
  every value it lists must occur in the column.
- `binary` means exactly two distinct non-empty values.
- `unit` only on `number` and `integer` variables and on ordinals. Keep the
  unit out of `displayName`.
- In each row, a latitude and its longitude must both be present or both
  missing.
- Avoid `integer` with `dataShape` `categorical`. EDA may not handle it
  (study-wrangler issue #82, unresolved). A code made of digits is `string`
  `categorical`. study-wrangler 1.0.53 and earlier rejected an all-digit
  `string` column (#95); 1.0.54 accepts it.

Also:

- Definitions are shown to EDA users. Write them for a researcher. Keep
  curation reasoning (what you changed and why) out of them. That belongs in
  the notes.

## Reading a free-form data dictionary

Dictionaries arrive as spreadsheets, Word or PDF tables, Markdown, or a
paragraph in an email. Read it like a person would, and map what you find:

- A column or variable name. Match it to the input header, allowing for
  case, spaces and underscores. List every dictionary entry with no column,
  and every column with no entry. Ask about either if it matters.
- Label or description: `displayName` (short) and `definition` (longer).
- Unit: `unit`.
- Allowed values or a codebook (`1 = Yes, 2 = No`). The codes in the data
  might need a `map-values`, which is a routine change when the dictionary
  defines it. They also give you `vocabularyOrder` or `ordinalLevels`.
- Type or format, such as "date (DD/MM/YYYY)". This feeds `dataType` and
  any `parse-dates` format.
- A missing-value code (`-99`, `999`). Blanking it is a data-altering fix,
  so propose `blank-placeholders` with `"approval": "user"`, citing the
  dictionary.

Put the dictionary file in the spec's `extraFiles` if it is in the input
folder, so it is copied into `raw-data/`.

## Geocoordinates

EDA's map needs **one latitude and one longitude variable per entity**, with
fixed metadata. Collection sites, villages and households usually have them.
See "Geocoordinates for EDA" in
[Study-Transfer-Format-STF.md](stf/Study-Transfer-Format-STF.md#geocoordinates-for-eda).

**What to do.**

1. Set `"geo": { "latitude": "<column>", "longitude": "<column>" }` on the
   entity.
2. List both columns in `variables`, with a `displayName` (and a
   `definition` if you know the datum or what point it is).

The renderer does the rest:

- It writes `data_type` (`number` and `longitude`), `data_shape`
  `continuous`, `stable_id` (`OBI_0001620` and `OBI_0001621`) and
  `display_type` (`latitude` and `longitude`).
- It names the columns `latitude` and `longitude` when their names would
  not be recognised, and logs that in the notes.

Do not write geohash columns. study-wrangler's
`infer_geo_variables_for_eda()` derives them, and `check-stf.js` warns if
any are present. The notes record that the study needs
`map_entities(study, infer_geo_variables_for_eda)` before `eda` validation,
which mode 2 does.

**How EDA finds coordinate columns: two rules.** EDA looks for the tokens
`lat`, `latitude`, `long`, `longitude` and `lng`, in any case, in two places
with two different rules:

- **Inference** (`infer_geo_variables_for_eda()`) looks at the variable
  name. It accepts a token bounded by a word boundary **or an underscore**.
  So `wgs84_lat` and `long_term_resident` both match.
- **The validator** (the `eda` profile of `validate()`) looks at the
  variable name **and its `provider_label`**. It accepts a token bounded by
  a word boundary only. An underscore does not count as a boundary, but a
  space, hyphen or dot does. So `long_term_resident` does not match, but a
  provider label of `Long-standing market` does.

`provider_label` is the column's **original** input header. A
`rename-column`, or a variable `name`, changes the output name but not the
label.

**Stray look-alikes.** A non-coordinate column whose name or original header
looks like a latitude or longitude makes EDA see two longitudes (or
latitudes), and validation fails. Examples are `Long-standing market` and
`long_term_resident`, but not `Latrine type`, where `lat` runs on into a word.
It may need **two** fixes, and you
should make both in the same spec edit, so one render pass fixes it:

1. **The output name.** If the snake-case name matches (`long_standing_market`
   and `long_term_resident` both do, by the underscore rule), give it
   another name, with the variable's `name` (`established_market`) or a
   `rename-column`.
2. **The provider label.** If the original header itself matches by the
   validator rule (`Long-standing market` does; `long_term_resident` does
   not), also set `providerLabel` to a wording without the token
   (`Established market`). Renaming alone leaves the old header as the
   label.

The `village` entity of `tests/fixtures/tabular/clinical-epi/spec.json` shows
both. The renderer refuses a stray look-alike on an entity with `geo`, naming
the fix. The renderer also refuses two or more look-alikes on an entity
without `geo`. `check-stf.js` warns about a lone look-alike, and about a name
that only the inference rule matches. Record each such decision in
`notes.decisions`. The renderer logs `providerLabel` overrides itself.

**Checks on the values.** From the profile's `min` and `max`:

- Latitude must be in −90…90, and longitude in −180…180. EDA validation
  fails on any value out of range.
- In each row, both values must be present, or both missing.
- **An apparent swap.** For example, a "latitude" column whose values only
  fit as longitudes (outside ±90), or coordinates that land in the wrong
  country for the study description (Kenya is near latitude 0, longitude
  34–35; a "lat" of 34 is suspicious). Do not fix a swap yourself. Ask the
  user.
  - If the whole columns are swapped, point `geo.latitude` and
    `geo.longitude` at each other's columns. Then set `providerLabel` on
    both, so that neither keeps a label naming the other axis. The
    validator reads labels too.
  - If only some rows are swapped, use `replace-cells` on both columns, with
    `"approval": "user"`.
- Coordinates as degrees-minutes-seconds (`0°5'12"S`), or with a hemisphere
  letter, are a data-altering fix. Propose the conversion to decimal degrees
  and wait for approval. There is no transform for it, so it would be a
  `replace-cells` per row. Discuss that with the user if there are many
  rows.
