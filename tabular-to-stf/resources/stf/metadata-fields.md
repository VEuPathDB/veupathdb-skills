# STF Metadata Fields Reference

This is the complete reference for the YAML metadata files in a full STF
directory: `study.yaml` and one `entity-<entity_name>.yaml` per entity. It
lists every key the Study Wrangler loaders (`study_from_stf()` and
`entity_from_stf()`) read, with its type, whether it is required, its default,
its allowed values and when to use it.

For the directory layout, the TSV files and STF-Lite, see
[Study-Transfer-Format-STF.md](./Study-Transfer-Format-STF.md). These sections
of that document go deeper than this reference:

- [Variable categories (the variable tree)](./Study-Transfer-Format-STF.md#variable-categories-the-variable-tree)
- [Collections](./Study-Transfer-Format-STF.md#collections)
- [Geocoordinates for EDA](./Study-Transfer-Format-STF.md#geocoordinates-for-eda)
- [Curation notes (curation-notes.md)](./Study-Transfer-Format-STF.md#curation-notes-curation-notesmd)

A test (`tests/testthat/test-stf-documentation.R`) fails if a metadata field
or an allowed value is added to the code but not to this file.

---

## How the loader reads the YAML

Read this before writing YAML by hand or by program. These rules apply to
every section below.

1. **Unknown keys are mostly errors, but a misspelt section name is silently
   ignored.**
   - Inside an entry of `id_columns`, `variables`, `categories` or
     `collections`, an unknown key stops the load. The error names the bad key
     and lists the allowed ones.
   - At the top level of `study.yaml`, any unknown key stops the load. The
     error is either R's `unused argument (...)` or "not valid Entity
     metadata names".
   - At the top level of an entity file, an unknown key with a **scalar**
     value (a string, number or boolean) stops the load with R's
     `unused argument (...)`.
   - At the top level of an entity file, an unknown key whose value is a
     **list or mapping is silently dropped**. There is no error, warning or
     message. The four section names are the only list-valued top-level keys
     the loader reads, so spell them exactly: `id_columns`, `variables`,
     `categories`, `collections`. A typo such as `variabels:` or
     `categoris:` makes the loader ignore the whole section. The columns then
     fall back to inferred metadata, and the entity may still validate. A
     clean load is therefore no proof that a section was read.
2. **A misspelt allowed value is not an error.** The loader converts the
   values of `data_type`, `data_shape`, `display_type`, `scale` and `hidden`
   to R factors, and a value outside the allowed list silently becomes
   missing. A missing `data_type` or `data_shape` is then re-inferred from
   the data (so `data_type: integr` silently becomes whatever the data
   suggests, for example `integer`), and a missing `display_type` or `scale`
   falls back to no setting. Copy allowed
   values exactly from this reference.
3. **The loader does not convert the data to match `data_type`.** The TSV is
   read as text and each column's R type is guessed (readr's `type_convert`).
   The declared `data_type` must agree with that guess or `validate()` fails.
   For example, a column of ISO dates declared `data_type: string` fails,
   because the column is read as dates. A column such as `001, 002` stays text
   (leading zeros), so it can be `string` but not `number`.
4. **List every TSV column in `variables`, with its `data_type`.** A column
   not listed gets default metadata and an inferred type. A text column whose
   values are all different is inferred as an ID column (`data_type: id`),
   and the entity then fails validation with "multiple ID columns per entity
   level".
5. **Entries for columns that are not in the TSV are dropped** (with an
   informational message, not an error). Check spelling: `variable` must match
   the TSV column heading exactly, including spaces and punctuation.
6. **YAML 1.1 typing applies** (R's `yaml` package). Unquoted `yes`, `no`,
   `true`, `false`, `on`, `off` (any case) are booleans, and unquoted numbers
   are numbers. So:
   - quote string values that look like booleans or numbers, for example in
     `vocabulary_order` and `ordinal_levels` (`- 'Yes'`, `- 'No'`);
   - quote the string-typed fields `bin_width_override`, `display_range_min`
     and `display_range_max` even when they hold numbers (`'0.5'`, `'100'`);
     an unquoted number there stops the load with "Can't combine ...
     <character> and ... <double>";
   - give the boolean fields real booleans (`true`/`false`); a quoted
     `'true'` stops the load.
7. **List-valued fields** (`provider_label`, `ordinal_levels`,
   `vocabulary_order`) take a YAML sequence. A single scalar is also accepted
   as a one-item list. `hidden` is a special case; see its entry.
8. **`study_from_stf()` validates each entity as it loads it.** By default
   (`validate = TRUE`) it runs the entity checks of the default validation
   profile (`baseline`) on every entity and **stops the load** if any check
   fails, with "Can't create valid entity from STF file ...", after printing
   the validation report. So wherever this reference says that `validate()`
   reports or fails on a problem in an entity file (an entity or variable
   field, a category or a collection), `study_from_stf()` refuses to load the
   study. `entity_from_stf()` on its own, or `study_from_stf(dir, validate =
   FALSE)`, returns the invalid entity so that you can inspect it. Study-level
   checks (the study `name`, links between parent and child entities) and the
   `eda` profile are not run at load time; call
   `validate(study, profiles = c("baseline", "eda"))` for those.

---

## Study-level metadata (`study.yaml`)

`study.yaml` names the study and lists its entities. `study_from_stf()` loads
`entity-<name>.tsv` and `entity-<name>.yaml` for each listed name and nothing
else, so other files can sit in the same directory.

Without a `study.yaml`, `study_from_stf()` loads every `entity-*.tsv` file in
the directory, each with its same-stem `.yaml` or, failing that, `.yml` file
if present, and the study has no name. With a `study.yaml`, only
`entity-<name>.yaml` is read: an `entity-<name>.yml` file is ignored and the
entity loads without metadata.

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `name` | string | yes (validation) | none | Human-readable study name. A missing name loads (study-level checks are not run at load time), but `validate()` then reports "Study name is missing." |
| `entities` | list of strings | yes (load) | none | Entity names. Each must have `entity-<name>.tsv` in the directory; `entity-<name>.yaml` is optional. The load stops if the list is missing or empty. Order does not matter: the tree is assembled from the ID columns. |

No other keys are read; any other key stops the load.

### Example

```yaml
name: My Awesome Study
entities:
  - household
  - participant
  - observation
```

---

## Entity-level metadata (`entity-<entity_name>.yaml`)

Each entity YAML file describes one entity: its names, ID columns, variables,
variable categories and variable collections. Every scalar top-level key is
passed to the `entity()` constructor, so an unknown scalar key stops the load.
The only list-valued keys read are the four sections, spelt exactly
`id_columns`, `variables`, `categories` and `collections`. Any other list- or
mapping-valued key, including a misspelt section name, is **silently
ignored** (see rule 1 above).

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `name` | string | yes (validation) | none | Machine name of the entity. Use the same `<entity_name>` as in the file names and in `study.yaml`. Use letters and digits only (this is what `set_entity_name()` allows; the YAML loader does not check). A missing name fails validation, so `study_from_stf()` stops at load time (rule 8). |
| `display_name` | string | no | the value of `name` | Human-readable singular name, e.g. `Household`. |
| `display_name_plural` | string | no | `display_name` + `s` | Plural of `display_name`, e.g. `Households`. Set it when adding `s` is wrong (`Person` → `People`). |
| `description` | string | no | none | Free-text description of the entity. Exported to EDA with the entity. |
| `stable_id` | string | no | generated: `ENT_` + 8 characters hashed from `name` | Stable identifier of the entity in EDA, e.g. an ontology term ID such as `EUPATH_0000096`. Must be unique across the study. Use letters, digits and `_`, starting with a letter (what `set_stable_id()` allows; the YAML loader does not check). Set it only when you have a curated ID. |
| `id_columns` | list of ID column entries | yes | none | See [ID columns](#id-columns-id_columns). |
| `variables` | list of variable entries | no (but list every column) | none | See [Variables](#variables-variables). |
| `categories` | list of category entries | no | none | See [Variable categories](#variable-categories-categories). |
| `collections` | list of collection entries | no | none | See [Variable collections](#variable-collections-collections). |

The Study Wrangler's own exporter writes the entity keys that have values,
followed by `id_columns`, `variables`, `categories: []` and
`collections: []` (empty sections are written as `[]`).

---

### ID columns (`id_columns`)

One entry per ID column in the TSV: the entity's own ID column and,
for a child entity, the ID column of its parent (and optionally of further
ancestors). The loader sets `data_type: id` on these columns itself.

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `id_column` | string | yes | none | The ID column heading in the TSV, without the `\\` separator and `Descriptors` marker. |
| `entity_name` | string | yes | none | The entity this ID belongs to. For the entity's own ID column (level 0) it must equal the entity's `name`; otherwise `validate()` fails. |
| `entity_level` | integer | no | `0` | `0` for this entity's own ID column, `-1` for the parent's ID, `-2` for the grandparent's, and so on. Exactly one ID column per level. |
| `provider_label` | list of strings | no | none | The original column heading(s) from the data provider. |

An ID column entry also accepts the variable fields below (for example
`display_name`), and the loader stores them, but the exporter does not write
them back and the code does not show that EDA uses them. Keep ID column
entries to the four keys above.

```yaml
id_columns:
  - id_column: Household.Id
    entity_name: household
    entity_level: -1
  - id_column: Participant.Id
    entity_name: participant
```

---

### Variables (`variables`)

One entry per data column of the TSV (every column after the entity's own
ID column, the one carrying the `Descriptors` marker). Only `variable` is required by the loader; the other
fields have defaults. For EDA, `display_name` is also required.

#### Quick reference

| Field | Type | Default | Allowed values |
|---|---|---|---|
| `variable` | string | (required) | the TSV column heading |
| `display_name` | string | none | free text, at most 1500 characters |
| `provider_label` | list of strings | none | free text |
| `definition` | string | none | free text, at most 4000 characters |
| `stable_id` | string | generated `VAR_xxxxxxxx` | unique within the entity, at most 255 characters |
| `data_type` | string | inferred from the data | `string`, `number`, `integer`, `date`, `longitude` (`id` and `category` are set by the loader) |
| `data_shape` | string | inferred from the data | `continuous`, `categorical`, `ordinal`, `binary` |
| `ordinal_levels` | list | empty | every value in the column, in order (ordinals only) |
| `vocabulary_order` | list | empty | values present in the column (categorical/binary only) |
| `unit` | string | none | free text, e.g. `cm` |
| `scale` | string | none | `log`, `log2`, `ln` |
| `is_multi_valued` | boolean | `false` | `true`, `false` |
| `multi_value_delimiter` | string | none | the separator string, e.g. `';'` |
| `display_type` | string | `default` | `default`, `multifilter`, `geoaggregator`, `latitude`, `longitude` |
| `display_order` | integer | none | -999 to 999 |
| `hidden` | list | none | `download`, `variableTree`, `map`, `everywhere` |
| `display_range_min` | string | none | a number or ISO date, quoted |
| `display_range_max` | string | none | a number or ISO date, quoted |
| `bin_width_override` | string | none | a number, quoted; for dates `week`, `month` or `year` |
| `is_featured` | boolean | `false` | `true`, `false` |
| `parent_category` | string | none | the name of a category in `categories` |
| `parent_variable` | string | none | alias of `parent_category` |
| `is_merge_key` | boolean | `false` | `true`, `false` |
| `is_repeated` | boolean | `false` | `true`, `false` |
| `is_temporal` | boolean | `false` | `true`, `false` |
| `has_study_dependent_vocabulary` | boolean | none | `true`, `false` |
| `impute_zero` | boolean | none | `true`, `false` |
| `weighting_variable_spec` | string | none | not settled by the code (see entry) |
| `variable_spec_to_impute_zeroes_for` | string | none | not settled by the code (see entry) |
| `entity_level` | integer | `0` | leave unset |
| `entity_name` | string | the entity's `name` | leave unset |

The character limits are the column sizes of EDA's variable metadata table,
which the wrangler's VDI export writes to; the wrangler itself does not check
them.

#### Identity and description

- **`variable`** *(string, required)*
  The column heading in the TSV, exactly as written there. This is the
  variable's internal name.

- **`display_name`** *(string, optional for the loader, required for EDA)*
  The human-readable label shown in EDA. EDA validation fails for any variable
  or category without one. Write it in sentence case with units in
  parentheses where helpful, e.g. `Height (cm)`.

- **`provider_label`** *(list of strings, optional; default none)*
  The original column heading(s) as supplied by the data provider. Use it to
  keep the link between a cleaned-up `variable` name and the source file.
  When a column is not listed in the YAML, the loader sets this to the column
  heading.

  ```yaml
  provider_label:
    - Gender (self-reported)
  ```

- **`definition`** *(string, optional; default none)*
  A one- or two-sentence definition of what the variable measures, shown to
  EDA users. Put curation reasoning in `curation-notes.md` instead (see
  [Curation notes](./Study-Transfer-Format-STF.md#curation-notes-curation-notesmd)).

- **`stable_id`** *(string, optional; default generated)*
  The variable's stable identifier in EDA, typically an ontology term ID such
  as `EUPATH_0000704`. When unset, the wrangler generates `VAR_` followed by 8
  characters hashed from `variable`, so the same column name always gets the
  same ID. Stable IDs must be unique within the entity; `validate()` reports
  duplicates. Set it only for a curated ontology ID, or for the fixed
  geocoordinate IDs described in
  [Geocoordinates for EDA](./Study-Transfer-Format-STF.md#geocoordinates-for-eda).

#### Type and shape

- **`data_type`** *(string, optional; default inferred)*
  The type of the values. Allowed values:
  - `string`: text.
  - `number`: real numbers.
  - `integer`: whole numbers.
  - `date`: ISO-8601 dates (`YYYY-MM-DD`) without a time component.
  - `longitude`: a longitude in decimal degrees. Longitude has its own type
    because it is circular. Latitude is a plain `number` (see
    [Geocoordinates for EDA](./Study-Transfer-Format-STF.md#geocoordinates-for-eda)).

  Two more values exist internally and must not be used in `variables`: `id`
  (set by the loader on `id_columns` entries) and `category` (set by the loader
  on `categories` entries).

  When `data_type` is omitted it is inferred from the data. Always set it
  explicitly, and make sure it agrees with the data (rule 3 above).

- **`data_shape`** *(string, optional; default inferred)*
  How the values are treated in analysis. Allowed values:
  - `continuous`: a numeric or date scale. For `number`, `integer` and `date`
    variables. Not allowed for `string`.
  - `categorical`: unordered categories.
  - `ordinal`: ordered categories. Requires `ordinal_levels`. Only for `string`
    and `integer` variables.
  - `binary`: exactly two distinct values (e.g. `Yes`/`No`). `validate()`
    fails if the column has more than two.

  When omitted it is inferred: `continuous` for `number`, `integer` and
  `date`; `binary` for a single-valued `string` column with exactly two
  distinct values that form a true/false, t/f, yes/no or y/n pair (any case);
  `categorical` otherwise. The loader never infers `ordinal`.

  A numeric or date variable can be `categorical` when its values are codes or
  a small set of discrete values rather than a scale.

- **`ordinal_levels`** *(list, required when `data_shape: ordinal`; default
  empty)*
  The complete list of values, from lowest to highest. Only for `data_shape:
  ordinal`; any other shape with `ordinal_levels` fails validation.
  **Every value that occurs in the column must be listed.** For a
  single-valued ordinal the loader turns the column into an R factor with
  these levels, and a value that is not listed silently becomes missing. (For
  a multi-valued ordinal, `validate()` reports unlisted values instead.)
  Levels may list values that do not occur in the data. Quote values that
  YAML would read as booleans.

  ```yaml
  - variable: Study.phase
    display_name: Study phase
    data_type: string
    data_shape: ordinal
    ordinal_levels:
      - preliminary
      - phase one
      - phase two

  - variable: Severity.score
    display_name: Severity score
    data_type: integer
    data_shape: ordinal
    ordinal_levels: [1, 2, 3, 4]
  ```

- **`vocabulary_order`** *(list, optional; default empty)*
  The order in which a categorical or binary variable's values are shown.
  Only for `data_shape: categorical` or `binary`; any other shape fails
  validation. A partial list is allowed: the listed values come first, then
  the remaining values in sorted order (the default without
  `vocabulary_order`). Every listed value must occur
  in the column (after splitting, for multi-valued variables); `validate()`
  reports values that do not. Quote values that YAML would read as booleans
  or numbers.

  ```yaml
  - variable: Owns.property
    display_name: Owns property
    data_type: string
    data_shape: binary
    vocabulary_order:
      - 'Yes'
      - 'No'
  ```

- **`unit`** *(string, optional; default none)*
  The unit of measurement, e.g. `cm`, `kg`, `days`, `mg/dL`. Only for
  `number` and `integer` variables and for ordinals; `validate()` reports a
  unit on any other variable. Leave the unit out of `display_name` when it is
  set here.

- **`scale`** *(string, optional; default none)*
  The axis scale EDA uses by default for a continuous numeric variable.
  Allowed values: `log`, `log2` (base 2), `ln` (natural log). The code does not
  state the base of `log`. Leave unset for a linear scale. The wrangler passes
  it through to EDA and does not check it against the data.

#### Multi-valued variables

- **`is_multi_valued`** *(boolean, optional; default `false`)*
  Set to `true` when a cell can hold several values separated by a delimiter,
  e.g. `fever;cough`. The data column must be text. `data_type` and
  `data_shape` then describe the individual values after splitting (so a
  multi-valued column of numbers can be `number`). Requires
  `multi_value_delimiter`.

- **`multi_value_delimiter`** *(string, required when `is_multi_valued:
  true`; default none)*
  The exact string that separates values within a cell, e.g. `';'` or `'|'`.
  It is matched literally (not as a regular expression). Quote it. If it is
  missing, the loader accepts the file but treats each whole cell as one
  value.

  ```yaml
  - variable: Symptoms
    display_name: Symptoms
    data_type: string
    data_shape: categorical
    is_multi_valued: true
    multi_value_delimiter: ';'
  ```

#### Display

- **`display_type`** *(string, optional; default `default`)*
  How EDA presents the variable. Allowed values:
  - `default`: normal presentation. Use this for almost every variable.
  - `multifilter`: EDA's multi-filter display, set on a category so that its
    child variables can be filtered together. The wrangler passes it through
    to EDA without checks, and the code does not document it further.
  - `geoaggregator`: for the generated geohash variables (`geohash_1` …
    `geohash_6`).
  - `latitude`: for the latitude variable.
  - `longitude`: for the longitude variable.

  The last three are part of the EDA map setup, and the wrangler validates
  them; see
  [Geocoordinates for EDA](./Study-Transfer-Format-STF.md#geocoordinates-for-eda).

- **`display_order`** *(integer, optional; default none)*
  Sort position among siblings (variables and categories with the same
  parent) in the variable tree, lowest first. Must be an integer from -999 to
  999 (EDA stores it as `NUMBER(3,0)`). The wrangler does not check the range,
  and truncates a decimal to an integer. The code does not settle where EDA
  puts siblings without a `display_order`; the wrangler's own tree printout
  puts them after the ordered ones.

- **`hidden`** *(list, optional; default none)*
  Where EDA should hide the variable. Allowed values:
  - `download`: left out of downloads.
  - `variableTree`: not shown in the variable tree.
  - `map`: not offered on the map.
  - `everywhere`: hidden everywhere.

  For one value, write a one-item list (or a scalar):

  ```yaml
  hidden:
    - everywhere
  ```

  For **more than one value, nest the list one level deeper**. This is the
  form the wrangler's exporter writes and reads back:

  ```yaml
  hidden:
    - - download
      - map
  ```

  Do not write a flat list of two or more values (`hidden: [download, map]`):
  the current loader then duplicates the variable's row, and validation fails
  with duplicate stable IDs.

- **`display_range_min`**, **`display_range_max`** *(string, optional;
  default none)*
  The default lower and upper bounds of the axis EDA shows for a continuous
  variable, when the data range is not what users should see first (e.g. a
  percentage shown from `'0'` to `'100'`). A number for numeric variables, an
  ISO date (`'2020-01-01'`) for date variables. They are strings in the
  metadata, so **quote them**.

- **`bin_width_override`** *(string, optional; default none)*
  The default histogram bin width for a continuous variable, replacing the
  computed one. For numeric variables a number (quoted, e.g. `'5'`); for date
  variables `week`, `month` or `year`. The wrangler does not check the value.

- **`is_featured`** *(boolean, optional; default `false`)*
  Set to `true` to list the variable among the study's featured variables in
  EDA. The wrangler passes it through to EDA.

#### Variable tree

- **`parent_category`** *(string, optional; default none)*
  The name of the category (from the `categories` section of the same file)
  that this variable sits under in the variable tree. Unset variables sit at
  the top level of the entity. Every referenced category must exist and the
  tree must have no cycles; `validate()` checks both. See
  [Variable categories (the variable tree)](./Study-Transfer-Format-STF.md#variable-categories-the-variable-tree).

- **`parent_variable`** *(string, optional; default none)*
  The internal name of the same field, accepted as an alias of
  `parent_category`. If both are given, `parent_category` wins. The wrangler's
  exporter currently writes `parent_variable`. Write `parent_category` by
  hand; both load identically.

#### EDA pass-through fields

The wrangler stores these, exports them to EDA and otherwise does not
interpret them. The code does not define their meaning beyond that, so set
them only when you know the EDA behaviour you want.

- **`is_merge_key`** *(boolean, optional; default `false`)*
  An EDA flag for variables usable as merge keys. Leave unset unless EDA
  needs it.

- **`is_repeated`** *(boolean, optional; default `false`)*
  An EDA flag for repeated measurements. Leave unset unless EDA needs it.

- **`is_temporal`** *(boolean, optional; default `false`)*
  An EDA flag for time variables. Leave unset unless EDA needs it.

- **`has_study_dependent_vocabulary`** *(boolean, optional; default none)*
  An EDA flag for categorical variables whose vocabulary depends on the study.
  Leave unset unless EDA needs it.

- **`impute_zero`** *(boolean, optional; default none)*
  An EDA flag for imputing zero for missing values. On variables in a
  collection, every child variable must have the same value (validated).
  Leave unset unless EDA needs it.

- **`weighting_variable_spec`** *(string, optional; default none)*
  An EDA variable specification naming a weighting variable. The code does not
  define the format of the specification. Leave unset.

- **`variable_spec_to_impute_zeroes_for`** *(string, optional; default none)*
  An EDA variable specification used with zero imputation. The code does not
  define the format of the specification. Leave unset.

#### Fields set by the loader

These are columns of the wrangler's internal metadata table. The loader
accepts them in `variables`, but you should leave them out.

- **`entity_name`**: overwritten with the entity's `name` for every variable.
  (In `id_columns` it is a required key; see above.)
- **`entity_level`**: defaults to `0`; leave unset (a value here is kept). (In `id_columns` it gives the
  ancestor level; see above.)
- `has_values`: `true` for data columns and set to `false` by the loader for
  categories. Setting it in YAML breaks the link between metadata and data
  columns.

#### Example

```yaml
variables:
  - variable: Age
    display_name: Age
    definition: Age of the participant at enrollment.
    data_type: integer
    data_shape: continuous
    unit: years
    parent_category: demographics
    display_order: 1

  - variable: Sex
    display_name: Sex
    provider_label:
      - Gender
    data_type: string
    data_shape: categorical
    parent_category: demographics
    display_order: 2

  - variable: Hemoglobin
    display_name: Hemoglobin
    data_type: number
    data_shape: continuous
    unit: g/dL
    display_range_min: '0'
    display_range_max: '20'
    bin_width_override: '0.5'
```

---

### Variable categories (`categories`)

A category is a node in the variable tree that groups variables (and other
categories) but has no data column. Variables point at a category with
`parent_category`. See
[Variable categories (the variable tree)](./Study-Transfer-Format-STF.md#variable-categories-the-variable-tree)
for how to design the tree.

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `category` | string | yes | none | The category's internal name; the value other entries use in `parent_category`. Must not be the name of a TSV column. Use `category:`, not `variable:`; the loader stops with an explanation if you use `variable:`. |
| `display_name` | string | yes for EDA | none | As for variables. |
| `definition` | string | no | none | As for variables. |
| `stable_id` | string | no | generated `VAR_xxxxxxxx` | As for variables. |
| `parent_category` | string | no | none | Parent category, for nested categories. `parent_variable` is accepted as an alias. |
| `display_order` | integer | no | none | As for variables. |
| `display_type` | string | no | `default` | As for variables; `multifilter` is the value meant for categories. |
| `hidden` | list | no | none | As for variables. |
| `is_featured` | boolean | no | `false` | As for variables. |

A category entry accepts every variable field, but the loader sets
`data_type: category` and `has_values: false` itself, and the data fields
(`data_type`, `data_shape`, `unit`, `ordinal_levels` and so on) have no
meaning for a category.

```yaml
categories:
  - category: demographics
    display_name: Demographics
    display_order: 1
  - category: anthropometry
    display_name: Anthropometry
    definition: Body measurements taken at each visit.
```

---

### Variable collections (`collections`)

A collection presents the variables under one category as a single
multi-variable unit in EDA (for example, a panel of related measurements).
Each collection is tied to a category with the same name. See
[Collections](./Study-Transfer-Format-STF.md#collections) for when to use one.

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `category` | string | yes | none | The name of an existing category in this file. `validate()` reports a collection without a matching category. |
| `display_name` | string | yes (validation) | none | Collection label in EDA. |
| `member` | string | yes (validation) | none | Singular noun for one member variable, e.g. `measurement`. |
| `member_plural` | string | yes (validation) | none | Plural of `member`, e.g. `measurements`. |
| `stable_id` | string | no | generated | Stable ID of the collection. Generated when unset. |
| `is_proportion` | boolean | no | `false` | The member values are proportions. |
| `is_compositional` | boolean | no | `false` | The member values are parts of a whole. |
| `impute_zero` | boolean | no | `false` | On export the value is taken from the child variables' `impute_zero`, which must all be equal (validated). |
| `normalization_method` | string | no | none | Free text naming the normalization, e.g. `none`. The code does not restrict the values. |
| `display_range_min` | string | no | none | Quoted number; as for variables. On export it is combined with the child variables' values. |
| `display_range_max` | string | no | none | Quoted number; as for variables. On export it is combined with the child variables' values. |

All child variables of a collection must share the same `data_type`,
`data_shape`, `unit` and `impute_zero`; `validate()` reports any difference.

```yaml
categories:
  - category: integer.measures
    display_name: Anthropometric measurements

collections:
  - category: integer.measures
    display_name: Anthropometric measurements
    member: measurement
    member_plural: measurements
    is_proportion: false
    is_compositional: false
    normalization_method: none
```

---

## Complete example

`entity-participant.yaml` for a child of `household`:

```yaml
name: participant
display_name: Participant
display_name_plural: Participants
description: People enrolled in the study, one row per person.

id_columns:
  - id_column: Household.Id
    entity_name: household
    entity_level: -1
  - id_column: Participant.Id
    entity_name: participant

variables:
  - variable: Name
    display_name: Full name
    data_type: string
    data_shape: categorical
    hidden:
      - everywhere

  - variable: Age
    display_name: Age
    data_type: integer
    data_shape: continuous
    unit: years
    parent_category: demographics

  - variable: Sex
    display_name: Sex
    provider_label:
      - Gender
    data_type: string
    data_shape: categorical
    vocabulary_order:
      - Female
      - Male
    parent_category: demographics

  - variable: Education
    display_name: Highest education level
    data_type: string
    data_shape: ordinal
    ordinal_levels:
      - none
      - primary
      - secondary
      - tertiary
    parent_category: demographics

  - variable: Symptoms
    display_name: Symptoms reported
    data_type: string
    data_shape: categorical
    is_multi_valued: true
    multi_value_delimiter: ';'

categories:
  - category: demographics
    display_name: Demographics
```
