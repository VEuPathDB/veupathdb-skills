# Category tree

EDA shows each entity's variables as a tree. Categories are the branches:
named groups with no data column of their own. Without categories, every
variable sits at the top level of its entity. That is fine for a handful of
variables, but hard to browse for many. See "Variable categories" in
[Study-Transfer-Format-STF.md](stf/Study-Transfer-Format-STF.md#variable-categories-the-variable-tree).

## When

Draft a tree for each entity with **about 10 or more variables**. Below that,
skip it unless the variables fall into obvious groups that the dictionary
already uses. Entities with only a few variables, such as a site with
coordinates and a habitat, need none. Use your judgement near the threshold,
and do not invent categories with one variable each.

## How to draft it

- Group variables the way a researcher would look for them, for example
  *Demographics*, *Household*, *Behaviour*, *Clinical*, *Anthropometry*,
  *Laboratory results*, *Bioassay* and *Molecular markers*.
- Follow the dictionary's sections or the questionnaire's modules when they
  exist.
- Nest a category inside another only when it helps. For example,
  *Anthropometry* fits under *Clinical*. Two levels are usually enough.
- Give every category a `displayName`, which EDA requires, and a one-line
  `definition` where it adds something.
- A variable may stay at the top level, with no `parentCategory`, when it
  fits nowhere. An example is an enrolment date.

## Show it to the user first

Show the draft as an indented outline before you write it into the spec.
Categories are in bold with their internal names, and variables are listed by
display name:

```
Participant
├── **Demographics** (demographics): who the participant is
│   ├── Sex
│   ├── Age
│   ├── Age 80 or over
│   ├── Education level
│   └── Occupation
├── **Behaviour** (behaviour)
│   └── Slept under a bednet
├── **Clinical** (clinical): clinical history and measurements at enrolment
│   ├── Fever in the last 14 days
│   └── **Anthropometry** (anthropometry): body measurements
│       ├── Weight
│       └── Height
└── Enrolment date
```

Ask whether to rename, merge, split or move anything. Apply the user's edits,
then write the tree, and record any choices they made in `notes.decisions`.

## Writing it into the spec

- Add `categories` to the entity: `{ "category", "displayName",
  "definition"?, "parentCategory"? }`.
- Set `parentCategory` on each variable that belongs to a category.
- `category` is an internal name in snake case (`demographics`). It must not
  equal a variable's output name or a column name.
- Every `parentCategory` must name a category in the **same** entity, and the
  categories must not form a cycle. The spec validator and `check-stf.js`
  both check this.

The `participant` entity in `tests/fixtures/tabular/clinical-epi/spec.json`
holds the tree above.
