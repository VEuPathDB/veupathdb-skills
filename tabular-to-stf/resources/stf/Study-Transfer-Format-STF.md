# Study Transfer Format (STF) Documentation

The Study Transfer Format (STF) is designed for structured storage and
exchange of study data, supporting hierarchical entity
relationships. STF includes two formats: STF (full) and STF-Lite. The
STF format includes detailed metadata, while STF-Lite is a minimal
version without metadata.

## Studies, Entities, IDs, and Variables

A **study** consists of a dataset composed of linked
**entities**. Each entity is a table representing instances of a
real-world object or event, such as a `household` in a clinical
epidemiology study or a `biosource` in a genomics study. Entities are
arranged hierarchically, meaning that some entities serve as parents
to others:

- A `household` entity may have multiple associated `participant` records.
- A `biosource` entity may have multiple `sample` children, each of
  which might have one or more `assay` instances.

Each entity table must include a unique identifier (ID) column to
distinguish instances. If an entity is a child of another, it must
also include a parent ID column to establish the
relationship. Additional ancestor IDs (e.g., grandparent
relationships) can be included but are optional.

Beyond ID columns, entity tables contain **variables**, which describe
attributes of entity instances. Variables fall into different data
types:

- **Numeric**: e.g., `age`, `BMI`
- **Date**: e.g., `enrollment date`
- **Categorical**: e.g., `hair color`
- **Ordinal** *(full STF only)*: e.g., `study phase` (`preliminary`, `phase one`, `phase two`)
- **Longitude** *(full STF only)*: treated separately due to its circular nature (see also [this issue](https://github.com/VEuPathDB/study-wrangler/issues/31))

Note that **dates must be provided in ISO-8601 format** without a time component.

## STF Directory Structure

The STF directory should contain:

- Tab-delimited entity files (`entity-<entity_name>.tsv`)
- Optional entity metadata YAML files (`entity-<entity_name>.yaml`)
- Optional study-level metadata file (`study.yaml`)
- Optional curation notes (`curation-notes.md`), which the loaders ignore
- An optional `raw-data/` subdirectory holding the original source files,
  which the loaders ignore

All these are described in more detail below.

### Example STF directory structure:
```
my_study/
├── study.yaml
├── curation-notes.md
├── raw-data/
│   ├── households.xlsx
│   ├── participants.csv
│   └── data-dictionary.pdf
├── entity-household.tsv
├── entity-household.yaml
├── entity-participant.tsv
├── entity-participant.yaml
├── entity-observation.tsv
└── entity-observation.yaml
```

## STF (full format)

### Entity TSV files

STF entity files are tab-delimited tables where each row represents an
entity instance. The first column(s) define hierarchical relationships
through **parent ID columns**, linking child entities to their parent
records.

Each entity must have a unique identifier column. Its heading carries the
**`Descriptors` marker**, joined to the ID heading by the separator `\\`
(two backslashes, with a space either side), to show where the ID columns
end and the data attributes (the "descriptors") begin. For child entities,
the first column is the parent ID, followed by the child entity’s own ID
column carrying the marker. For deeper hierarchies, you may provide all
parent IDs or just the immediate parent. See the example below.

**Which side of the ID heading the marker is on gives the file's layout:**

| Layout | Marked cell | Where it is |
|---|---|---|
| Standard (one row per record) | `<ID heading> \\ Descriptors` (marker *after* the heading) | in the header row, on the entity's own ID column |
| Transposed (one row per variable) | `Descriptors \\ <ID heading>` (marker *before* the heading) | in the first column, on the entity's own ID row |

The marker is required in both layouts, even when the entity has a YAML
file. The loader strips the marker and separator to get the ID heading.

**Current loader behaviour (differs from the rule above).** The loader does
not yet use the marker's position. It checks only whether *any* cell of the
first row contains the marker, in either order: if so it reads the file as
standard, if not as transposed. So a standard file whose header row lacks
the marker is silently read as transposed (rows and columns come out wrong),
and a transposed file whose first row is the entity's own marked ID row is
silently read as standard (see
[Transposed entity files](#transposed-entity-files) and
[issue #94](https://github.com/VEuPathDB/study-wrangler/issues/94)).

For example:
- **Parent entity (`household`)**: The first column is `Household.Id \\ Descriptors`, as it has no parent.
- **Child entity (`participant`)**: The first column (`Household.Id`) references the parent, and the second column (`Participant.Id \\ Descriptors`) uniquely identifies each participant.
- **Grandchild entity (`observation`)**: Two options are available:
  - Provide *all* parent IDs in parent-to-child order: `Household.Id`, `Participant.Id`, `Part..Obs..Id \\ Descriptors`
  - Provide just the parent IDs: `Participant.Id`, `Part..Obs..Id \\ Descriptors`

#### Example `entity-household.tsv`:
| Household.Id \\\\ Descriptors | Number.of.animals | Owns.property | Enrollment.date | Construction.material |
|----------------------------|-------------------|---------------|----------------|----------------------|
| H001                       | 4                 | Yes           | 2021-01-09     | Concrete             |
| H002                       | 3                 | No            | 2021-02-28     | Timber               |
| H003                       | 3                 | Yes           | 2021-03-13     | Concrete             |


#### Example `entity-participant.tsv`:

| Household.Id | Participant.Id \\\\ Descriptors | Name    | Nickname | Sex    | Family.Role |
|-------------|--------------------------------|---------|----------|--------|-------------|
| H001        | H001-P1                        | Alice   | Di       | Female | Relative    |
| H001        | H001-P2                        | Bob     | Bobby    | Male   | Child       |
| H001        | H001-P3                        | Diana   | NA       | Female | Parent      |
| H002        | H002-P1                        | Charlie | Chuck    | Male   | Child       |
| H002        | H002-P2                        | Anna    | NA       | Female | Relative    |
| H003        | H003-P1                        | Helen   | Hells    | Female | Parent      |
| H003        | H003-P2                        | Eve     | NA       | Female | Child       |
| H003        | H003-P3                        | Michael | Micky    | Male   | Child       |


#### Example `entity-observation.tsv`:

(This is the all-parents version.)

| Household.Id | Participant.Id | Part..Obs..Id \\\\ Descriptors | Observation.date | Height..cm. | Weight..kg. | MUAC..cm. | Teeth.brushed.today |
|-------------|---------------|--------------------------------|------------------|-------------|-------------|-----------|--------------------|
| H001        | H001-P1       | H001-P1-Obs1                   | 2023-09-29       | 145         | 35          | 15.82     | 1                  |
| H001        | H001-P2       | H001-P2-Obs1                   | 2023-05-04       | 135         | 47          | NA        | 1                  |
| H001        | H001-P2       | H001-P2-Obs2                   | 2023-11-30       | 129         | 80          | 28.81     | 0                  |
| H001        | H001-P3       | H001-P3-Obs1                   | 2023-04-21       | 133         | 51          | NA        | 1                  |
| H002        | H002-P1       | H002-P1-Obs1                   | 2023-08-08       | 175         | 32          | 26.68     | NA                 |
| H002        | H002-P1       | H002-P1-Obs2                   | 2023-10-18       | 172         | 34          | 12.59     | 1                  |
| H002        | H002-P2       | H002-P2-Obs1                   | 2023-02-28       | 160         | 74          | 19.83     | 2                  |
| H003        | H003-P1       | H003-P1-Obs1                   | 2023-05-02       | 150         | 40          | 31.84     | 1                  |
| H003        | H003-P2       | H003-P2-Obs1                   | 2023-01-30       | 140         | 38          | 17.5      | 0                  |
| H003        | H003-P3       | H003-P3-Obs1                   | 2023-01-05       | 130         | 45          | NA        | NA                 |
| H003        | H003-P3       | H003-P3-Obs2                   | 2023-08-07       | 127         | 91          | NA        | 1                  |


### Entity Metadata YAML files
These files define entity properties as well as ID columns, variables,
their types, and metadata.

In the `entity-household.yaml` example below, the `id_columns` section makes the important
link between the ID column `Household.Id` and the entity name `household` but this is trivial
for a parent-less entity.

#### Example `entity-household.yaml`:
```yaml
name: household
display_name: Household
display_name_plural: Households

id_columns:
  - id_column: Household.Id
    entity_name: household

variables:
  - variable: Number.of.animals
    display_name: Number of animals
    data_type: integer
    data_shape: continuous

  - variable: Owns.property
    display_name: Owns property
    data_type: string
    data_shape: categorical

  - variable: Enrollment.date
    display_name: Enrollment date
    data_type: date
    data_shape: continuous
```

When an entity has parent relationships, the `id_columns` section is
crucial. Below is an example for the `observation` entity. The
**grandparent** and **parent** columns are explicitly linked to their
respective entities by name, with their ancestral distances specified
in the `entity_level` field (-1 for the immediate parent, -2 for the
grandparent, and so on).

The default value for `entity_level` is 0, meaning "this entity," so it is not required for "Part..Obs..Id".

#### Example `entity-observation.yaml`

```
name: observation
display_name: observation
display_name_plural: observations

id_columns:
  - id_column: Household.Id
    entity_name: household
    entity_level: -2
  - id_column: Participant.Id
    entity_name: participant
    entity_level: -1
  - id_column: Part..Obs..Id
    entity_name: observation

variables:
  - variable: Observation.date
    provider_label:
      - Observation date
    data_type: date
    data_shape: continuous
# more variables not shown
```

Full reference documentation for all the metadata fields [can be found here](./metadata-fields.md).


### Study YAML file

The `study.yaml` file provides high-level study metadata and lists the
names of the entities in the study. The STF loader will only load the
files `entity-<entity_name>.{tsv,yaml}` as defined in this file. This
means you can keep work-in-progress or other versions of entity files
in the same directory as files that do get loaded.

```yaml
name: My Awesome Study
entities:
  - household
  - participant
  - observation
```

## Variable categories (the variable tree)

EDA shows each entity's variables as a tree. The branches of the tree are
**categories**: named groups that hold variables and other categories. A
category has no data column. It exists only in the entity's YAML file.

Without categories every variable sits at the top level of its entity. Use
categories when an entity has more than a handful of variables, grouping them
the way a user would look for them (for example *Demographics*,
*Anthropometry*, *Laboratory results*).

### Declaring categories

List the categories in the `categories:` section of the entity YAML file, one
entry per category, each keyed by `category:`:

```yaml
categories:
  - category: demographics
    display_name: Demographics
    definition: Who the participant is.
```

- **`category`**: the category's internal name. Variables and other
  categories refer to it by this name. It must not be the name of a TSV
  column.
- **`display_name`**: the label shown in the tree. Required for EDA.
- **`definition`**: optional free-text description.
- **`parent_category`**: the enclosing category, for a nested category. Leave
  it out for a top-level category.
- `display_order`, `display_type`, `hidden`, `is_featured` and `stable_id` are
  also accepted. See
  [metadata-fields.md](./metadata-fields.md#variable-categories-categories)
  for every key.

The key is `category:`, **not** `variable:`. An entry keyed `variable:` stops
the load with:

```
Invalid format in 'categories' section of YAML file 'entity-participant.yaml'.
Categories must use 'category:' as the key, not 'variable:'.
```

Spell the section name exactly `categories`. A misspelt section name such as
`categoris:` is **silently ignored**, and every `parent_category` that refers
to it then points at a missing category (see
[How the loader reads the YAML](./metadata-fields.md#how-the-loader-reads-the-yaml)).

The loader gives every category `data_type: category` itself. Do not set
`data_type`, `data_shape`, `unit` or the other data fields on a category.

### Placing variables and categories in the tree

A variable joins a category by naming it in `parent_category`. A category
nests inside another category the same way, so the tree can be as deep as
needed. Entries without `parent_category` sit at the top level of the entity.
`display_order` sorts siblings, lowest first.

`parent_variable` is accepted as an alias of `parent_category` (the Study
Wrangler's own exporter writes `parent_variable`). Write `parent_category`;
if both are present, `parent_category` wins.

### Validation

- **Every `parent_category` must name an existing category.** Otherwise
  `entity_from_stf()` warns ("STF YAML contains parent_variable references to
  undefined categories") and returns an entity that fails `validate()`, and
  `study_from_stf()`, which validates each entity as it loads it, stops with
  "Can't create valid entity from STF file ...". The checks only look for the
  name among the entity's variables and categories, so make sure it names a
  category, not a variable.
- **No cycles.** A category may not be its own ancestor; `validate()` reports
  "Illegal circular path detected".
- **Unique stable IDs.** Categories share the entity's stable ID space with
  variables. Generated IDs (`VAR_` + hash of the name) are unique as long as
  the category names differ from the variable names.
- **EDA profile:** every category needs a `display_name`
  (`validate(profiles = c("baseline", "eda"))` reports "EDA validation
  requires display_name for all categories").

### Worked example: a two-level tree

A `participant` entity with two top-level categories, *Demographics* and
*Clinical*, and a nested category, *Anthropometry*, inside *Clinical*:

```
participant
├── Demographics
│   ├── Age (years)
│   └── Sex
└── Clinical
    ├── Anthropometry
    │   ├── Height (cm)
    │   └── Weight (kg)
    └── Fever
```

`entity-participant.tsv` (columns separated by tabs):

<!-- example:categories:tsv -->
```
Participant.Id \\ Descriptors	Age	Sex	Height	Weight	Fever
P01	34	Female	162	58.5	Yes
P02	41	Male	175	80.2	No
P03	29	Female	158		No
P04	52	Male	181	92.0	Yes
```

`entity-participant.yaml`:

<!-- example:categories:yaml -->
```yaml
name: participant
display_name: Participant
display_name_plural: Participants

id_columns:
  - id_column: Participant.Id
    entity_name: participant

variables:
  - variable: Age
    display_name: Age
    data_type: integer
    data_shape: continuous
    unit: years
    parent_category: demographics
    display_order: 1

  - variable: Sex
    display_name: Sex
    data_type: string
    data_shape: categorical
    parent_category: demographics
    display_order: 2

  - variable: Height
    display_name: Height
    data_type: number
    data_shape: continuous
    unit: cm
    parent_category: anthropometry
    display_order: 1

  - variable: Weight
    display_name: Weight
    data_type: number
    data_shape: continuous
    unit: kg
    parent_category: anthropometry
    display_order: 2

  - variable: Fever
    display_name: Fever at enrolment
    data_type: string
    data_shape: binary
    parent_category: clinical
    display_order: 2

categories:
  - category: demographics
    display_name: Demographics
    display_order: 1

  - category: clinical
    display_name: Clinical
    definition: Clinical measurements and observations at enrolment.
    display_order: 2

  - category: anthropometry
    display_name: Anthropometry
    definition: Body measurements.
    parent_category: clinical
    display_order: 1
```

## Collections

> **Not produced by the tabular-to-stf skill.** Collections are documented
> here so that the format description is complete.

A **collection** presents the variables directly under one category as a
single multi-variable unit in EDA, for example a panel of related
measurements that should be plotted or compared together. Collections are
listed in the `collections:` section of the entity YAML file.

- Each collection is tied to a category of the same name: its `category` key
  must equal the `category` of an entry in `categories`. The members of the
  collection are the variables whose `parent_category` is that category.
- Required (checked by `validate()`): `category`, `display_name`, `member`
  (singular noun for one member, e.g. `measurement`) and `member_plural`.
- Optional: `stable_id`, `is_proportion`, `is_compositional`, `impute_zero`,
  `normalization_method`, `display_range_min`, `display_range_max`.
- All member variables must share the same `data_type`, `data_shape`, `unit`
  and `impute_zero`; `validate()` reports any difference.

The field-by-field reference, with an example, is in
[metadata-fields.md](./metadata-fields.md#variable-collections-collections).

## Geocoordinates for EDA

EDA's map needs each geolocated entity to have **one latitude variable and one
longitude variable**, with fixed metadata, plus six derived *geohash*
variables used to aggregate points on the map. In STF you supply only the
latitude and longitude columns and their metadata. The Study Wrangler derives
the geohash columns.

### Naming the coordinate columns

The Study Wrangler finds the coordinate columns by name. Matching is
**case-insensitive**. A column name matches if it contains one of the
recognised tokens (`latitude`, `lat`, `longitude`, `long`, `lng`) bounded on
**each side** by either a word boundary (the start or end of the name, or a
character that is not a letter, digit or underscore, such as `.`, `-` or a
space) **or** an underscore (`_`).

Latitude, matched column names (examples):

| Column name | Token matched |
|---|---|
| `lat`, `LAT`, `Lat` | `lat` |
| `lat-dd`, `wgs84_lat`, `sample_lat_value` | `lat` |
| `latitude`, `Latitude` | `latitude` |
| `latitude-wgs84`, `sample_latitude` | `latitude` |

Longitude, matched column names (examples):

| Column name | Token matched |
|---|---|
| `lng`, `LNG` | `lng` |
| `sample-lng`, `lng_dd` | `lng` |
| `long`, `LONG` | `long` |
| `long-dd`, `sample_long` | `long` |
| `longitude`, `Longitude` | `longitude` |
| `longitude_wgs84`, `sample-longitude` | `longitude` |

Column names that do **not** match:

| Column name | Reason |
|---|---|
| `lat1`, `lng2` | digit immediately follows token — no word boundary or underscore |
| `platform` | `lat` embedded mid-word, no boundary or underscore before it |
| `flat`, `slat` | `lat` preceded by a letter — no boundary or underscore |
| `belongs`, `elongated` | `long` embedded mid-word |
| `latlong` | tokens are adjacent with no separator; neither `lat` nor `long` has the required trailing/leading boundary |

The EDA validator (the `eda` profile of `validate()`) finds coordinate
columns with a **narrower** rule: the tokens must be bounded by word
boundaries only, and an underscore does not count. So underscore names from
the tables above, such as `wgs84_lat`, `sample_lat_value` or `lng_dd`, are
found by `infer_geo_variables_for_eda()` but are invisible to the validator,
which then does not check their metadata or values. Separate the token with
`.`, `-` or a space (`sample.lat`, `lat-dd`), or better, name the columns
plain `Latitude` and `Longitude`.

**One latitude and one longitude per entity.** An entity must not have any
other variable whose name matches these rules. The EDA validator also looks
for the tokens in each variable's `provider_label` (with word boundaries only,
so `sample_lat` does not match there). So a non-coordinate variable such as
`Long.term.illness`, or one with the provider label `Long-term illness`,
counts as a second longitude, and the entity fails EDA validation. Rename such
variables (e.g. `Chronic.illness`) or reword the label. If a study has
coordinates for two different things (say, household and workplace), put them
on two different entities.

### Required metadata

| | Latitude | Longitude |
|---|---|---|
| `stable_id` | `OBI_0001620` | `OBI_0001621` |
| `data_type` | `number` | `longitude` |
| `display_type` | `latitude` | `longitude` |
| `data_shape` (recommended; not checked) | `continuous` | `continuous` |

The EDA validator checks the first three rows. Also give both a
`display_name`, as for every variable. Values must be WGS-84
decimal degrees: latitude in [-90, 90] and longitude in [-180, 180]. In each
row both values must be present or both missing. EDA validation treats a
value out of range or a half-missing pair as fatal.

### Geohash columns are optional in STF

The six geohash variables are `geohash_1` … `geohash_6` (precision 1 to 6),
with stable IDs `EUPATH_0043203` … `EUPATH_0043208`, `data_type: string`,
`data_shape: categorical`, `display_type: geoaggregator` and `hidden:
[everywhere]`. EDA validation requires them alongside the coordinates.

**You do not need to put them in STF.** `infer_geo_variables_for_eda()`
derives them from the latitude and longitude. It also sets `stable_id`,
`data_type` and `display_type` on the latitude and longitude variables as in
the table above; it does not set `data_shape`, so declare that in the YAML. It
replaces any geohash columns already
present (data and metadata), so it is safe to run more than once. STF exported
by the Study Wrangler after this step contains the geohash columns; that is
fine, and they are regenerated the next time the step runs.

### Recommended step before EDA validation or export

After loading, run the inference across the whole study, then validate with
the EDA profile:

```r
study <- study_from_stf("my_study") %>%
  map_entities(infer_geo_variables_for_eda)
validate(study, profiles = c("baseline", "eda"))
```

`infer_geo_variables_for_eda()` is silent on entities without coordinate
columns and leaves them unchanged. If an entity has coordinate-like columns
but not exactly one of each, it warns and leaves the entity unchanged. EDA
validation then fails if it finds more than one latitude or more than one
longitude column; a lone coordinate column only gets an advisory, and
validation passes. Run this step before EDA validation and before VDI
export.

### Worked example

A `site` entity with coordinates and no geohash columns.

`entity-site.tsv` (columns separated by tabs):

<!-- example:geo:tsv -->
```
Site.Id \\ Descriptors	Site.name	Latitude	Longitude
S01	Kisumu	-0.0917	34.7680
S02	Accra	5.6037	-0.1870
S03	Iquitos	-3.7437	-73.2516
```

`entity-site.yaml`:

<!-- example:geo:yaml -->
```yaml
name: site
display_name: Site
display_name_plural: Sites

id_columns:
  - id_column: Site.Id
    entity_name: site

variables:
  - variable: Site.name
    display_name: Site name
    data_type: string
    data_shape: categorical

  - variable: Latitude
    display_name: Latitude
    stable_id: OBI_0001620
    data_type: number
    data_shape: continuous
    display_type: latitude

  - variable: Longitude
    display_name: Longitude
    stable_id: OBI_0001621
    data_type: longitude
    data_shape: continuous
    display_type: longitude
```

This loads and passes baseline validation as it stands. After
`map_entities(infer_geo_variables_for_eda)` the entity has the six geohash
columns and passes `validate(profiles = c("baseline", "eda"))`.

## Curation notes (curation-notes.md)

An STF directory may contain a Markdown file, `curation-notes.md`, recording
how the STF was made from the provider's data. It is an optional, documented
member of the directory. The loaders ignore it: `study_from_stf()` reads only
`study.yaml` and the entity files, and `export_to_stf()` neither writes nor
removes it.

Keep curation reasoning here rather than in variable `definition`s, which are
shown to EDA users. Write the notes so that a curator can check every change
and redo the work from the original files. When the original files are kept
in [`raw-data/`](#raw-data-raw-data), refer to them by their path relative to
the STF directory, for example `raw-data/participants.csv`.

Recommended sections:

- **Study**: the study, its source files (names, versions, dates received)
  and who curated it.
- **Entity tree**: the entities, their parent-child relationships and ID
  columns, and how they map to the source tables.
- **Routine normalisation**: mechanical changes applied across the board, for
  example trimming whitespace, turning placeholder values such as `N/A` into
  empty cells, ISO-8601 date conversion and column renaming.
- **Data changes**: every change to data values, each as a replayable
  pseudo-code step, for example
  `Participant.Age: "80+" → 80; add Age_censored = TRUE`. Record rejected
  proposals too, with what was done instead.
- **Flagged, not changed**: oddities noticed in the data but left as they
  are, with the reason.
- **Decisions and answers**: questions put to the data provider or the
  team, and the answers or decisions.
- **Validation**: the validation run (profiles used, for example
  `c("baseline", "eda")`), its result and any issues left open.

## Raw data (raw-data/)

An STF directory may contain a `raw-data/` subdirectory holding the original
source files the STF was made from, **unmodified**, together with any data
dictionary or study description the provider supplied. With these, the STF
can be audited and regenerated from what was actually received.

The loaders ignore it. `study_from_stf()` lists only the top level of the STF
directory (it does not recurse), whether or not there is a `study.yaml`, so
files in `raw-data/` are never loaded, even ones named like `entity-*.tsv` or
`study.yaml`.

`curation-notes.md` should refer to these files by their relative path, for
example `raw-data/participants.csv`.

Caveats:

- **Size:** keeping the raw data roughly doubles the size of the directory.
- **Sensitive data:** `raw-data/` may contain columns deliberately left out of
  the STF, such as names, exact coordinates or free text. Review it, or leave
  it out, before sharing the directory outside the team.

## STF-Lite

STF-Lite is a minimal, metadata-free variant suitable for quick or simple data submissions.

- Filenames must follow the convention: `entity-<ENTITY_NAME>.tsv`
- No separate metadata YAML files are required.
- The ID column headings must match entity names exactly (this is the only place they are defined).
- Parent entity ID columns must be in strict parent-to-child order.

### Example STF-Lite entity TSV file:

| household \\\\ Descriptors | Number.of.animals | Owns.property | Enrollment.date | Construction.material |
|----------------------------|-------------------|---------------|----------------|----------------------|
| H001                       | 4                 | Yes           | 2021-01-09     | Concrete             |
| H002                       | 3                 | No            | 2021-02-28     | Timber               |
| H003                       | 3                 | Yes           | 2021-03-13     | Concrete             |


## Entity relationship checks

An STF study is considered invalid if any child entity row references
a parent ID that does not exist in the corresponding parent entity
file. Every child entity must be linked to a valid parent
instance. While it is acceptable for a parent entity to have no
children, orphaned child records (i.e., records with missing or
non-existent parent IDs) are not allowed.


## Column headings format

There are no strict rules for column heading formats. IDs and variable
headings can contain spaces and other non-alphanumeric characters if
you like.

The STF loaders (`study_from_stf()` and `entity_from_stf()`) **keep the
headings exactly as written** (apart from removing the `\\` separator
and `Descriptors` marker from the entity's own ID heading). The `variable` and `id_column` values in the entity YAML must
therefore match the headings character for character. For example, a column
headed `Height (cm)` must be listed as `variable: Height (cm)`; an entry
`variable: Height..cm.` matches no column, so it is dropped and the column
silently falls back to default metadata (see rule 5 of
[How the loader reads the YAML](./metadata-fields.md#how-the-loader-reads-the-yaml)).

Conversion to R-friendly names (replacing spaces and other non-standard
characters with periods, as in `Height..cm.`) happens only when a table is
read with `entity_from_file()` and its relatives (`entity_from_tsv()`,
`entity_from_csv()`, `entity_from_tibble()`), not when STF is loaded.

## Missing values

Missing values should be represented as **empty cells** (blank/empty strings) in TSV files:
- In TSV format: consecutive tabs with no content between them (i.e., `<tab><tab>`)
- In CSV format: consecutive commas with no content between them (i.e., `,,`)

The literal string `NA` is also accepted for R compatibility, but **empty cells are preferred** for broader tool compatibility with Excel, pandas, and other data analysis platforms.

When Study Wrangler exports to STF format, missing values are written as empty cells. When importing, both empty cells and the literal string `NA` are interpreted as missing values.

### Trailing missing values

**Important**: When missing values occur at the end of a row, you **must include the trailing tabs** (or commas in CSV) to maintain proper column alignment. Without trailing delimiters, parsers cannot determine which columns are missing.

**Correct** (with trailing tabs for missing values at end of row):
```
Household.Id \\ Descriptors<tab>Location<tab>Temperature<tab>Humidity
H001<tab>Boston<tab>72.5<tab>65
H002<tab><tab>68.3<tab>
H003<tab>Seattle<tab><tab>
```

**Incorrect** (missing trailing tabs):
```
Household.Id \\ Descriptors<tab>Location<tab>Temperature<tab>Humidity
H001<tab>Boston<tab>72.5<tab>65
H002<tab><tab>68.3
H003<tab>Seattle
```

### Examples

**Example showing missing values as empty cells:**
```
Household.Id \\ Descriptors<tab>Location<tab>Temperature
H001<tab>Boston<tab>72.5
H002<tab><tab>68.3
H003<tab>Seattle<tab>
```

**Example showing missing values as "NA" (also supported):**
```
Household.Id \\ Descriptors	Location	Temperature
H001	Boston	72.5
H002	NA	68.3
H003	Seattle	NA
```

Both formats will be correctly interpreted on import, with missing values preserved through STF export-import roundtrips.

## Transposed entity files

The examples above show entity TSV files in the **standard** layout: one row
per record (entity instance), with one column per ID and variable. This is
the default.

An entity file may instead be **transposed**: one row per ID or variable, and
one column per record. This is a simple transpose of the standard layout
(rows and columns swapped), not a pivot to a long or key-value format with
one row per record, variable and value. The `Descriptors` marker then comes
*before* the ID heading, `Descriptors \\ <ID heading>`, in the first column
on the entity's own ID row; in the standard layout it comes *after* it,
`<ID heading> \\ Descriptors`, in the header row (see
[Entity TSV files](#entity-tsv-files)).

**Write the standard layout.** The loader does not yet tell the layouts
apart by the marker's position: it reads a file as standard whenever any cell
of the first row contains the marker, in either order. A transposed file is
therefore only read correctly when its first row is a parent ID row (which
has no marker). A transposed file for an entity with no parent starts with
its own `Descriptors \\ <ID heading>` row, so the loader takes it for a
standard file and loads it without transposing it, silently producing the
wrong columns and rows.

Here's a snippet of `entity-observations.tsv` transposed. The right-most
columns have been truncated for space reasons. Tabs have been replaced by
spaces for formatting/alignment reasons.


```
Household.Id                  H001                          H001                          H001                          H001                          H002                          H002           >
Participant.Id                H001-P1                       H001-P2                       H001-P2                       H001-P3                       H002-P1                       H002-P1        >
Descriptors \\ Part..Obs..Id  H001-P1-Obs1                  H001-P2-Obs1                  H001-P2-Obs2                  H001-P3-Obs1                  H002-P1-Obs1                  H002-P1-Obs2   >
Observation.date              2023-09-29                    2023-05-04                    2023-11-30                    2023-04-21                    2023-08-08                    2023-10-18     >
Height..cm.                   145                           135                           129                           133                           175                           172            >
Weight..kg.                   35                            47                            80                            51                            32                            34             >
MUAC..cm.                     15.82                         NA                            28.81                         NA                            26.68                         12.59          >
Teeth.brushed.today           1                             1                             0                             1                             NA                            1              >
```


The Study Wrangler reads both layouts, subject to the limitation above.
`export_to_stf()` writes the standard layout, except for an entity with at
least 200 columns and more columns than rows, which it writes transposed.
Because of the limitation above, an entity with no parent and 200 or more
columns (and fewer rows than columns) currently does **not** round-trip
through `export_to_stf()` and `study_from_stf()`: it is exported transposed
and read back untransposed. See
[issue #94](https://github.com/VEuPathDB/study-wrangler/issues/94).


## Comparison of Full STF vs. STF-Lite

| Feature | Full STF ✅ | STF-Lite ⚠️ |
|------------------------------------------|------------------------------------------------|-------------------------------------------|
| **Custom entity names & display names**  | ✅ Supported via metadata YAML                 | ❌ Not supported, entity names must match ID columns |
| **Data type enforcement**                | ✅ Enforced via metadata definitions           | ❌ No enforcement, at mercy of automatic type detection |
| **Ordinal variable support**             | ✅ Metadata allows explicit ordinal definitions | ❌ Not supported |
| **ID column flexibility**                | ✅ Custom ID column names allowed, column order not important   | ❌ ID column headers must match entity names exactly, ID columns must be in parent-to-child order |
| **Validation**                           | ✅ Ensures entity relationships and data integrity | ⚠️ Entity relationships validated, but limited metadata-based type validation |
| **Geo-coordinates**                      | ✅ Flexible variable naming via metadata definitions | ⚠️ Common patterns (Lat/Latitude/Long/Longitude/lng etc.) supported via post-processing inference |
| **Standard or transposed TSV files** | ✅ | ✅ |

## CSV compatibility

We may decide to offer read-compatibility for CSV data files, but the Study Wrangler will likely
continue to write in TSV format only.
