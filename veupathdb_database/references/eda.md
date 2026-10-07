# EDA differential expression and antibody-array notebooks

On the website, an EDA "notebook" replaces the WDK question form for two search
families. `scripts/eda.py` does what the user does there (look at the samples,
pick a contrast, run the compute, set volcano thresholds) and hands the result to
`wdk.py` as an ordinary search step that returns the same genes.

| notebook (`edaNotebookType`) | WDK searches | method | expression values |
|---|---|---|---|
| `differentialExpressionNotebook` | `GenesByRNASeq…DESeq`, `GenesByDESeqUserDataset` | DESeq2 | `SEQUENCE_READ_COUNT` (or `_SENSE` / `_ANTISENSE`) |
| `antibodyArrayNotebook` | `GenesByAntibodyArrayEdaSubset_…` | limma | `NORMALIZED_INTENSITY` |

The notebook state is a JSON string in the WDK param `eda_analysis_spec`. The hidden
param `eda_dataset_id` must equal the spec's `studyId`, which is a **DS_** id.
When the step runs, a WSF plugin asks EDA for the volcano statistics of the first
computation that has a thresholded volcano plot, and keeps the rows that pass.

## Workflow

1. Find the dataset: `eda.py de-datasets SITE` (DS id, method, search name), or
   `wdk.py find-searches SITE "differential expression"` (tagged `[EDA notebook: …]`).
   `DATASET` arguments accept a DS id or one of these search names.
2. `eda.py study SITE DATASET`: the samples and their annotation.
3. `eda.py contrasts SITE DATASET`: canonical candidate contrasts. Choose one.
4. `eda.py de SITE DATASET --contrast N`: compute (or reuse), then summarise.
5. `eda.py de-spec SITE DATASET --contrast N --save`. It writes the WDK params to
   the skill cache and prints `{"paramsFile", "leaf"}`. It resolves the WDK search name
   itself, so the leaf is ready to paste (it notes when no search exists for a dataset,
   e.g. user datasets). Put the `leaf` in
   `wdk.py create-strategy SITE --spec '{"leaf": …}'` (or combine it with other
   steps), or run `wdk.py count SITE SEARCH --params @PARAMSFILE`.

`--contrast N` re-enumerates the candidates, so give every command after
`contrasts` the same `--filters`, `--vars`, `--value-var` and `--entity`. An explicit contrast
(below) avoids that dependency.

## Files

Nothing needs a file in the user's working directory:
- `--contrast` and `--filters` take inline JSON (`'{…}'` / `'[…]'`), or a file path
  when the user wants to keep one.
- `de-spec --save` writes the WDK params to
  `~/.cache/veupathdb-wdk/eda/params/{content hash}.json`: the same content gives the
  same file, different contrasts or thresholds never collide, writes are atomic, and
  files are pruned after 7 days. Each `--save` prints its own path, so parallel
  sessions are safe.
- Save results (`--tsv`, JSON) where the user and their project want them; ask if
  unsure.

## Reading `study`

- One line per variable: id, name, `[shape]`, then level counts (categorical) or
  min–max, mean and missing count (continuous). `*` marks featured variables.
- Hidden variables are dropped; category nodes are headings; a definition is cut
  at 120 characters; a large vocabulary shows its top 10 levels and "… N more".
- Identifier-like variables get one line with no levels: more than 20 distinct values
  covering at least 90% of records, or present values that are all distinct (at least 3).
- The `DE-ready:` line names the gene entity, its gene count and its value variables.
  With several expression entities (e.g. host and parasite), pass `--entity`.
- Only the expression entity's parent and higher entities can hold a comparator
  (a notebook rule). Other entities are listed with counts and marked unusable.
- An entity with more than 5000 records is summarised per variable via
  `/distribution`; `contrasts` then refuses until filters narrow it.

## Contrasts

- Candidates (sample-side entities): categorical variables, and numeric ones.
  - Numeric with at most 6 distinct values: one level per value.
  - Numeric with more: binned into half-open ranges `[start, end)` using the variable's
    default bin width (EDA `distributionDefaults`), then treated like categorical levels.
    Binned numerics are not offered as stratifiers. A numeric variable with no default
    bins gets the reason "write a contrast file with numeric ranges".
  - Levels (or bins) need at least 2 samples. Up to 6 usable levels are paired; with
    more, pool them into groups in a contrast file.
- Orientation: each pair of levels is listed once. **Choosing the reference is your
  call**; the listed orientation is only a hint, shown in `reference`:
  - `label match`: groupA's label looks like a control (control, normal, WT, wild
    type, untreated, mock, baseline, uninfected, naive, vehicle, healthy, pre,
    day 0, …). Usually right, but check it against the study description.
  - `arbitrary`: neither or both labels look like controls; groupA is just the
    larger level.
  To flip, write a contrast file with groupA and groupB swapped. If the listed
  orientation is cached, `de` reuses it with effect sizes negated, so a flip costs
  nothing (see "Canonical form and the shared cache").
- At most 50 candidates are listed (crossed designs multiply the stratified
  versions); a note gives the total. Narrow with `--vars`.
- Notes to weigh:
  - `same grouping as X`: X splits the samples identically (aliased). The effects
    cannot be separated. The alias is listed once, not as its own candidate.
  - `groups also differ in Z: a vs b`: a confounder for this pair.
  - `Z varies within the groups … stratified versions follow`: the compute has no
    covariates, so each following candidate repeats the contrast within one level
    of Z (it carries a filter). Prefer these when Z matters biologically.
  - `low replicates (n=2 …)`: allowed but noisy. n < 2 is refused.
- `[complete]`: the job already exists in the shared cache, so `de` is instant
  (and someone, maybe a website user, ran it). Only the first 30 candidates are
  checked, with `autostart=false`, which never starts work.
- Explicit contrast, inline or as a file (for pooled or custom groups, or a flipped
  reference; `filters` optional):

  ```json
  {"comparator": {"variableId": "VAR_…"},
   "groupA": [{"label": "control"}],
   "groupB": [{"label": "drug A"}, {"label": "drug B"}],
   "filters": []}
  ```

  Numeric comparators need `{"label": "0-10", "min": "0", "max": "10"}`
  (half-open `[min, max)`).

## Sample filters (`--filters JSON|FILE`)

`study`, `contrasts`, `de`, `de-spec` and `pca` take `--filters`, which restricts
the samples exactly as the notebook's subset step does. Pass it inline (preferred:
no file to manage) or as a file. It holds an array of EDA filters,
`{"filters": [...]}`, or a saved analysis spec (its subset is used):

```json
[{"entityId": "ENT_…", "variableId": "VAR_…", "type": "stringSet", "stringSet": ["febrile"]},
 {"entityId": "ENT_…", "variableId": "VAR_…", "type": "numberRange", "min": 0, "max": 48}]
```

`study --filters` is the subset preview: entity lines read "6 of 12 records". Filters
are part of the job (a different subset is a different job) and travel into the
spec's subset. Typical uses: drop PCA outliers, or restrict to one level of a
crossed factor by hand.

## Canonical form and the shared cache

EDA names a compute job by the MD5 of the plugin name and the key-sorted request
body; no user identity is included. So a contrast computed by anyone (website user,
other agent) is free for everyone, and the job id is a stable **contrast id** to cite.
eda.py builds every contrast in one canonical form: labels sorted within each group,
filters sorted, `pValueFloor` `1e-200`, the website's method for the search family,
and exactly the body the WSF plugin sends. Changing a filter, the value variable or
the method makes a new job. Thresholds are not part of the job.

Swapping groupA and groupB also makes a new job id, but not new statistics: with a
single two-level comparator and no shrinkage, the swap only negates `effectSize`
(p and padj agree to ~4e-5; verified live, TESTS.md EDA-9). So when this orientation
has never run but its mirror is cached, `de` reuses the mirror, negates the effect
sizes, and records the mirror's job under `provenance.statisticsFrom`. The WDK step
for this orientation still runs its own job. `--no-mirror` disables the reuse.

The symmetry is numeric, not exact: swapped-group DESeq2 results agree to about 1e-3
relative on effect sizes and ~4e-5 on p/padj. With a reused mirror, the passing-gene
counts near the thresholds can differ by a gene or two from the WDK step for this
orientation; `--no-mirror` gives exact parity.

## Reading `de`

- `effectSize` is log2(groupB/groupA), **unshrunk** (no lfcShrink), so it is noisy for
  low-count genes. There is no baseMean.
- Thresholds apply to the **raw** p-value, as the website's volcano plot and the WDK
  step do: `|log2FC| >= FC` and `p <= P`, then the direction. `de` also reports how many
  genes pass using padj, and the top genes are taken among those.
- `padj NA`: DESeq2's independent filtering removed the gene (usually low counts).
- A gene absent from the output was **not tested** (all-zero counts, or not on the
  array). It is not "unchanged".
- "the WDK step returns N genes": the plugin drops the first statistics row (a
  header-skip quirk, verified live), so N is one less than the raw-p count when that
  row passes. The step's `totalCount` counts transcripts and is larger.
- `--genes A,B` reports single genes; `--tsv FILE` writes the whole table;
  `--thresholds` re-filters locally without recomputing.

## JSON output (`de --json`)

```
{"context":    comparator, groups (labels, n, which is the reference), orientation,
                method, value variable, filters, thresholds, notes, counts,
                top lists as row keys,
 "provenance": site, datasetId, studyId, plugin, jobId (the contrast id),
                statisticsFrom (null, or the mirror job reused with negated effects), search,
 "identity":   {"r1": "PF3D7_…", …},
 "rows":       {"r1": {"effectSize", "pValue", "adjustedPValue", "status"}, …}}
```

A consumer that must not see gene identity drops `identity` and keeps the rest.
Row keys are opaque (ordered by p-value). Rows hold the top genes, any `--genes`, and
`--rows passing|all`.

## Errors

- `job … is failed`: a job that fails quickly usually means a bad configuration.
  `--retry` deletes the failed job and resubmits; an expired job is resubmitted.
- `still in-progress after …s`: the job keeps running; re-run later or raise `--timeout`.
  `--no-wait` starts it and returns.
- `dataset … is not visible`: check the login (`wdk.py whoami SITE`) and the site.
- `comparator … is not a parent of the expression entity`: the notebook rule.
- `wdk.py count` or a report on a DE search whose EDA job is not computed yet returns a
  clean error saying the job has been started or is running: retry in a few minutes
  (or run `eda.py de` first).
