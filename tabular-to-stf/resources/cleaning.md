# Cleaning

Every change to the data is a transform in the spec (see
[curation-spec.md](curation-spec.md)). The input files are never touched.
Changes fall into three kinds, and they are handled differently.

| Kind | Examples | Transform | `approval` |
|---|---|---|---|
| Routine normalisation | stray spaces; `NA`, `N/A`, `-`; the same value written differently: `y`/`yes`/`YES` → `Yes`, `pos` → `Positive`; codes the dictionary defines (`1` → `Yes`) | `trim`, `blank-placeholders`, `map-values`, `rename-column` | `auto`: apply, and the notes log it |
| Likely typo | a judgement about what was meant, found only by similarity: `Feamle` next to `Female`; `Anopheles gambie` next to `Anopheles gambiae` | `map-values`, once the user confirms | `user` |
| Data-altering fix | `80+` in an age column, `12..5`, `2023-13-01`, text in a numeric column, ambiguous placeholders | `replace-cells`, `parse-dates`, `derive-column`, `drop-column`, `blank-placeholders` | `user`, only after the user approves |

`render-stf.js` refuses `auto` for `replace-cells`, `parse-dates`,
`derive-column` and `drop-column`. It also refuses `auto` for
`blank-placeholders` whose values are not all unambiguous placeholders.

## What the profile tells you

For each column, `profile-tables.js` reports:

- `whitespaceCells`: cells with leading or trailing spaces. Use `trim` with
  `auto`. List the affected columns, or omit `columns` to trim the whole
  table.
- `placeholderCells`: counts of known placeholder values. Split them in
  two:
  - **Unambiguous** (`UNAMBIGUOUS_PLACEHOLDERS`: `NA`, `N/A`, `n/a`, `na`,
    `-`, `--`, `.`, `null`, `NULL`). These only mean "missing". Use
    `blank-placeholders` with `auto`.
  - **Ambiguous**: `none`, `None`, `unknown`, `Unknown`, `not done`, and
    `0` in a count or measurement column. These may carry meaning. `none`
    can be an answer ("no bednet"), and `unknown` can be a category a
    researcher wants to filter on. Ask the user. If they agree that these
    mean "missing", use `blank-placeholders` with `user`. Otherwise keep
    them.
- `nearDuplicates` and `nearDuplicateCount`: pairs of values in a
  categorical column that look alike. The count is the total, and the list
  is capped. Pairs that differ only by case or spaces come first, followed
  by pairs of values with 5 or more characters that are 1 or 2 edits apart.
- `leadingZeros`: values such as `007`. These are codes, so keep them as
  strings. Never strip the zeros.
- `inferred`, `top`, `min`, `max`: a column inferred as `string` whose top
  values are mostly numbers, or a `min`/`max` outside a plausible range,
  points to a data-altering fix.

Use `--top N` with `--file <name>` to see more values of a column. Values
longer than 80 characters are cut and end in `…[+N chars]`. Never copy a cut
value into the spec: find the full value in the input file first. The profile
only shows the first five rows of each file. If you need more, for example to find the row IDs of
the bad values, search the input file with a script or `grep`. Do not read the
whole file.

## Routine normalisation (automatic)

Apply these without asking. The notes log each rule once per column with a
cell count.

- `trim` for stray spaces. Put it before any transform that matches whole
  cells.
- `blank-placeholders` for unambiguous placeholders.
- `map-values` that **only** unifies *the same value written differently*.
  That covers three cases:
  - Case or surrounding whitespace, for example
    `{ "yes": "Yes", "YES": "Yes", " Yes": "Yes" }`.
  - Conventional, unambiguous abbreviations of that value in that column,
    for example:
    - `y`/`n` for `Yes`/`No`;
    - `pos`/`neg` for `Positive`/`Negative`;
    - `M`/`F` for `Male`/`Female` in a sex column.
  - Codes that the data dictionary defines, for example
    `{ "1": "Yes", "2": "No" }` when the dictionary gives that codebook. Cite
    the dictionary in the `reason`.

  Pick the form most of the column already uses, or the dictionary's form.

  Anything that is a judgement about what was **meant** is not routine. That
  includes a likely typo, or a value you match to another **only by
  similarity or edit distance**, such as the profile's `nearDuplicates`
  beyond case and whitespace pairs. Do not apply it as `auto`. Propose it to
  the user, as below. An abbreviation that could stand for more than one
  value, such as `M` in a column that also has `Married`, is a judgement
  too.
- `rename-column` for a header that is unhelpful or misleading, for example
  a bare `date` when the table has several dates. Usually the variable's
  `name` and `displayName` are enough, and you do not need a rename.

## Likely typos (flag, never fix silently)

A near-duplicate pair that differs by an edit or two, such as `Feamle` and
`Female`, is usually a typo, but not always. `Block 1` and `Block 2` are
distinct values, and `Musoma` and `Mosoma` may be two different villages. It
takes a person who knows the study to tell. Show every
such pair to the user, with the counts of each value, and say which one you
think is right. If the user confirms, add a `map-values` with `"approval":
"user"`. If they say the values are distinct, or don't know, leave them, and
write a line in `notes.flagged`.

## Data-altering fixes (approval required)

These are values that would force a type change or break a format. Collect
them for one entity, then show them to the user **in one message**. For each,
give the column, the row IDs, the values, and the fix you propose, as a
numbered list the user can answer item by item.

Common cases and the fix to propose:

- **Right-censored (top-coded) values**, such as `80+` in an age column.
  Propose to keep the column numeric:
  1. Add a flag column named `<variable>_censored` with `derive-column`, for
     example `{ "op": "derive-column", "column": "age_censored", "from": "Age (years)", "map": { "80+": "Yes" }, "default": "No" }`.
  2. Then set the value to the cap with `replace-cells` (`80+` → `80`).

  The derive must come first, because it reads the original values. Give the
  flag column `dataShape` `binary`, and say in the age variable's definition
  that values at the cap are lower bounds. The alternative, which the user
  may prefer, is to keep the column as a string or ordinal variable with
  `80+` as a level. That gives up numeric filtering and ranges. Present
  this as a proposal and wait for approval. Do not apply it. Left-censored
  values (`<0.1`, below a detection limit) work the same way, with the
  value set to the limit.
- **Malformed numbers**, such as `12..5` or `1,5`. Propose `replace-cells`
  to the likely value (`12.5`, `1.5`) and say why you think so.
- **Dates not in ISO format**, such as `03/04/2023`. Propose `parse-dates`
  with the format (`DD/MM/YYYY`). Ask about the format if the data does not
  settle it, for example if no day is above 12. Impossible dates, such as
  `2023-13-01`, need the user. The month and day may be swapped, or it may
  be a slip, so propose a `replace-cells` and ask.
- **Stray text in a numeric column**, such as `see notes` or `>5`. Propose
  blanking it (`replace-cells` to `""`) or a censored treatment, as above.
- **Implausible values**, such as a weight of 250 kg next to a height of
  163 cm. These do not break a type. Flag them, and propose a fix only if
  the right value is obvious.
- **Tabs or line breaks inside a value.** The render fails on these, naming
  the entity, column and row ID. Propose `replace-cells` to the same text
  with spaces.
- **Identifying columns** (see "Personal data" in SKILL.md). Propose
  `drop-column`.

While you wait for an answer, you may write a fix into the spec as
`"approval": "proposed"`, so that it is visible in the notes as "Proposed, not
applied". When the user answers:

- If they approve, change it to `"user"`.
- If they reject it, change it to `"rejected"`, and add `instead` saying what
  was done instead. For example: "Kept 250 and flagged it for the provider to
  confirm", or "Column kept categorical".
- If they want something else, write that instead, with `"user"`.

Keep rejected and still-proposed transforms in the spec. They are not applied,
but they are part of the record.

## Order of transforms

A sensible order within an entity:

1. `rename-column`.
2. `trim`.
3. `blank-placeholders`.
4. `map-values`.
5. `derive-column`.
6. `replace-cells`.
7. `parse-dates`.
8. `drop-column`.

Remember that later transforms see the results of earlier ones. For example,
a `replace-cells` after a `map-values` must use the mapped value as `from`.
