# Curation notes

`curation-notes.md` sits in the STF directory and records how the STF was made
from the provider's files, so that another curator can check every change and
redo the work. Loaders ignore it. The recommended sections are documented in
"Curation notes" in
[Study-Transfer-Format-STF.md](stf/Study-Transfer-Format-STF.md#curation-notes-curation-notesmd).

In mode 1 and in mode 2 with a spec, `stf.py render` writes the whole file
from the spec on every render. **Do not edit it by hand**, because the next
render would overwrite your edits. Put what it needs into the spec instead.
The file opens with a link to the saved spec, `curation-spec.json`, in the
same directory, and says how to re-render from it.

## Sections and where they come from

| Section | Written from |
|---|---|
| **Study** | `study.name`, `study.description`, and each entity file and `extraFiles` entry, by its path under `raw-data/` with row counts. It also says when the study needs `map_entities(study, infer_geo_variables_for_eda)` |
| **Entity tree** | `entities`: name, plural, source file, ID column, parent and parent column |
| **Routine normalisation** | transforms with `"approval": "auto"`, one line each, with the count of cells changed (no row IDs) |
| **Data changes** | transforms with `"approval": "user"`, as replayable steps, with the IDs of the rows changed (the first 10, then `and N more`). Then "Proposed, not applied" (`proposed`) and "Rejected" (`rejected`, with `instead`) |
| **Flagged, not changed** | `notes.flagged`, then `notes.pii`, each prefixed `PII:` |
| **Decisions and answers** | `notes.decisions`, then lines the renderer adds: geo columns it renamed and `providerLabel` overrides |
| **Validation** | `notes.validation`. When this is empty, it says "Not run (mode 1)" |

Each transform line names the entity and column, says what changed, and ends
with the transform's `reason`. So write each `reason` as a full sentence a
reviewer will understand on its own, for example "Ages of 80 and over were
recorded as 80+; record them as 80 so age is an integer, flagged by
age_censored." A typical data change line reads:

```
- `participant.Age (years)`: "80+" → "80" (row P012). Reason: …
```

## What to put in `notes`

Each entry is one Markdown string, a sentence or two. Name things as
`` `entity.variable` ``, and use row IDs where they help.

- **`notes.flagged`**: oddities you noticed and left alone, with the reason
  and whether the provider was asked. Examples:
  - near-duplicates the user said are distinct, or could not judge;
  - implausible values that were kept;
  - `stf.py check` warnings you chose not to act on.
- **`notes.pii`**: columns that may identify people, and what was done with
  them. If a column was dropped, say that `raw-data/` still holds it.
- **`notes.decisions`**: answers to your questions that shaped the STF. A
  later curator would otherwise have to guess at these. Examples:
  - the entity tree, where it was ambiguous;
  - units, ordinal orders and code meanings the user confirmed;
  - the category tree choices;
  - stray lat/long look-alikes you renamed or relabelled;
  - that `raw-data/` was not copied, and why, when you used `--no-raw-data`.

  Do not repeat what the transforms already say.
- **`notes.validation`** (mode 2): one entry per container run, giving:
  - the image shown on the `Image:` line of the validate output;
  - what was run: `validate(study, profiles = c("baseline", "eda"))` after
    `map_entities(study, infer_geo_variables_for_eda)`;
  - the result (`pass`, `fail`, `error` or `load-error`);
  - for a failure, the issues and what was done about them, or that they
    were left open and why.

Keep curation reasoning out of variable `definition`s. EDA shows those to
users.

## Without a spec

In mode 2 on an STF directory that has no `curation-spec.json`, nothing
renders the notes. Edit `curation-notes.md` directly. Create it with the
sections above if it is missing, or append to the existing sections. See
[mode-2-validation.md](mode-2-validation.md).
