---
name: tabular-to-stf
description: Convert multi-entity relational tabular data (CSV/TSV, one file per entity, e.g. village/household/participant/sample or collection site/collection/sample/assay) into STF for study-wrangler and VEuPathDB EDA; optionally validate and fix it in a study-wrangler container
---

# Tabular data to STF

This skill turns a folder of related tables into a Study Transfer Format (STF)
directory that study-wrangler loads and VEuPathDB EDA accepts. You read capped
profiles of the data, talk to the user, and write one JSON **curation spec**.
A script renders the STF from the spec. You never write STF files by hand.

The STF format is documented in
[Study-Transfer-Format-STF.md](resources/stf/Study-Transfer-Format-STF.md) and
[metadata-fields.md](resources/stf/metadata-fields.md), bundled from
study-wrangler (see [SOURCE.md](resources/stf/SOURCE.md)).

## Scripts

All scripts are in this skill's `scripts/` directory (next to this file).
Run them with `uv run`; uv installs the one dependency on first use. They
never modify the input files and make no git changes.

| Command | What it does |
|---|---|
| `uv run scripts/stf.py profile <inputDir> --out <path>` | Profiles every `.csv`/`.tsv`/`.txt` file in `<inputDir>`, writes the full JSON to `<path>` and prints one summary line per file |
| `uv run scripts/stf.py profile <inputDir> --file <name> [--top N]` | Prints the compact JSON profile of one file, with the parent links that involve it |
| `uv run scripts/stf.py render <spec.json> <outDir> [--no-raw-data]` | Renders the spec to an STF directory |
| `uv run scripts/stf.py check <stfDir> [--json]` | Checks an STF directory; exit 1 on errors |
| `uv run scripts/stf.py validate <stfDir> [--engine docker\|podman]` | Mode 2: validates in the pinned study-wrangler container |
| `uv run scripts/stf.py validate --detect` | Prints `docker`, `podman` or `none` |

## Inputs

Ask for whatever is missing:

- **An input folder** of CSV or TSV tables, UTF-8, one header row, one file
  per entity. Each file has its own ID column and, except the root, a column
  holding its parent's ID.
- **A study description** (optional): a paragraph of free text, pasted or in
  a file.
- **A data dictionary** (optional), in any format. Read it yourself. There is
  no parser for it.
- **An output directory** (`<out>`). It must be new or empty, or an earlier
  output of this skill.

You also need a working area, `<work>`, for `profile.json` and the first
draft of the spec. Use the current directory unless the user names another.
It must not be the input folder or `<out>`.

## Choosing a mode

Run `uv run scripts/stf.py validate --detect` first.

- **Mode 1, tables to STF**, is the default. Follow the steps below.
- **Mode 2, validate and fix in a container.** Offer it after mode 1 when the
  detect step found `docker` or `podman`. Run mode 2 alone when the user
  gives you an existing STF directory. See
  [mode-2-validation.md](resources/mode-2-validation.md).
- **Mode 3, write a study-wrangler R script**, is not yet available. It will
  have the model write and run an R script that builds the study with
  study-wrangler's own functions, as a parallel route to the curation spec
  for data the spec cannot express. If the user asks for it, say it is not
  available yet. See [mode-3-wrangler-script.md](resources/mode-3-wrangler-script.md).

**Containers.** Always validate through `stf.py validate`. Never run
`docker` or `podman` yourself, and never pull an image without asking.
The script uses the pinned study-wrangler image and never downloads it. If
the image is missing, `validate` prints `Result: load-error` and the two pull
commands. Pass those commands on to the user, say it is about a 6 GB
download, and let them decide.

## The rule

Never hand-edit rendered STF files. Every change that reaches the output is
in the curation spec: change the spec, re-render, re-check. The rendered files
are overwritten on each render, so hand edits are lost, and the spec is the
replayable record of what was done. You may explore the data any way you like
while investigating. The only exception is mode 2 on an STF directory that
has no curation spec, where nothing can re-render it.

## Mode 1: tables to STF

### 1. Profile

Profile in two steps, so that no single output is too long to read:

1. `uv run scripts/stf.py profile <inputDir> --out <work>/profile.json`.
   `<work>` is your working area, such as the current directory. It must not
   be the input folder or `<out>`. This prints one line per file: its name,
   rows, columns and the size of its profile.
2. For each file, `uv run scripts/stf.py profile <inputDir> --file <name>`,
   and read that JSON. Do one file at a time.

Do not read whole input files, or the whole `profile.json`. They can be
large. A file's profile gives its delimiter, row count, headers and first
five rows. For each column it gives the top values with counts,
`distinctCount`, the `inferred` type, `min`/`max`, and quirk flags. Those
flags are `isCandidateId`, `leadingZeros`, `whitespaceCells`,
`placeholderCells`, `nearDuplicates` and `nearDuplicateCount`. It also lists
`parentLinks` that involve the file: columns whose values all occur in
another file's candidate ID column. Values longer than 80 characters are cut
and end in `…[+N chars]`. Use `--top N` for more values of a column. A `.txt`
data dictionary in the folder is profiled as a table. Ignore it. Read the
description and dictionary now too.

### 2. Entity tree

Propose the entities, from the profile, the file and column names, and the
description. Each one needs a `name` (lower case), display name and plural,
ID column, and parent with its parent column. Each entity has exactly one
parent, and one entity, the root, has none. A parent may have several kinds
of child. State the parts that are unambiguous, for example a clear
`parentLinks` entry and a matching column name, and move on. Ask before
continuing about anything you would be guessing at. Examples are two
plausible parents, no clear ID column, or an entity name the data does not
suggest. Ask these in one message.

### 3. Cleaning

Look for whitespace, placeholders, the same value written differently
(`y`/`yes`/`YES`), near-duplicate values, and values that break a column's
type or format, such as `80+` in an age column, `12..5` or `2023-13-01`.
Routine normalisation is applied automatically and logged: trimming,
unambiguous placeholders, and the same value written differently. Likely
typos and anything else that is a judgement about what was meant are shown
to the user, never fixed silently. Data-altering fixes are batched per entity, shown with a proposed
fix, and applied only when the user approves. Record a rejected fix, and what
was done instead. See [cleaning.md](resources/cleaning.md).

### 4. Variable metadata

For each variable: display name, `data_type`, `data_shape`, unit, definition,
ordinal levels and value order. Infer what the data shows, and take what the
description and dictionary say. Ask about what remains and matters, such as
the unit of a bare number or the order of ordinal levels. A missing
definition may stay blank. Batch your questions per entity, never one prompt
per column. See [variable-metadata.md](resources/variable-metadata.md).

### 5. Geocoordinates

For each entity with latitude and longitude, set `geo` in the spec. The
renderer then writes the metadata EDA needs. Do not add geohash columns,
because study-wrangler derives them. Make sure EDA will find exactly one
latitude and one longitude per entity, and rename or relabel any other column
that looks like one. Check the value ranges, and ask the user about an
apparent lat/long swap. See the geocoordinates section of
[variable-metadata.md](resources/variable-metadata.md#geocoordinates).

### 6. Category tree

For each entity with about 10 or more variables, draft a variable tree. That
is named categories with short definitions, nested if that helps. Show it to
the user as an indented outline, apply their edits, then put it in the spec.
See [category-tree.md](resources/category-tree.md).

### 7. Write the spec and render

Write the first draft of the spec to `<work>/curation-spec.json`, beside
`profile.json` and outside `<out>`, following
[curation-spec.md](resources/curation-spec.md). Set `inputDir` to the input
folder's absolute path. Then run
`uv run scripts/stf.py render <work>/curation-spec.json <out>`. Writing the
draft into `<out>` instead would defeat the renderer's guard against
rendering into a directory that holds other files.

The render writes `study.yaml`, the entity files, `curation-notes.md` and
`<out>/curation-spec.json`. By default it also copies the inputs and any
`extraFiles` unmodified into `<out>/raw-data/`, and rewrites the saved spec's
`inputDir` to `raw-data`, so the directory can be re-rendered on its own.
Use `--no-raw-data` only if the user asks, or if the inputs are very large or
hold sensitive columns that must not travel with the STF. If you skip the
copy, say so in `notes.decisions`.

After the first successful render, `<out>/curation-spec.json` is the spec.
Delete the draft in `<work>`, so there is only one. Make every later change
in `<out>/curation-spec.json` and re-render with
`uv run scripts/stf.py render <out>/curation-spec.json <out>`. A render error
lists every problem in the spec. Fix the spec and render again.

### 8. Check

Run `uv run scripts/stf.py check <out>`. It checks ID integrity, the variable
tree, that the files load, allowed values, data types and the EDA geo rules.
Each `ERROR:` line is fixed in the spec, followed by a re-render and a
re-check, until there are none. Read every `WARNING:` line and act on it or
record it in `notes.flagged`. Then offer mode 2 if a container engine was
found.

### 9. Notes

The renderer writes `curation-notes.md` from the spec and its transform log.
Make sure the spec's `notes` hold everything a later curator needs: flagged
issues, the user's answers and decisions, PII, and, after mode 2, the
validation runs. Then re-render. See
[curation-notes.md](resources/curation-notes.md).

## Personal data

If a column looks like it identifies people, such as names, phone numbers,
exact home coordinates or free-text addresses, mention it once, gently, and
ask whether to keep it, drop it with `drop-column` (approved by the user) or
leave it to the provider. Record it in `notes.pii` either way. If it is
dropped, note that `raw-data/` still holds it.
