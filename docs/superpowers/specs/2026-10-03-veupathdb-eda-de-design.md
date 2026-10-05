# VEuPathDB EDA Differential Expression — Design

Date: 2026-10-03
Status: DRAFT for user review (design agreed conversationally, section by section; spec not yet reviewed)
Skill: `veupathdb_database/` in this repo (`veupathdb-skills`)
Next step: user reviews this spec, then `superpowers:writing-plans` in a fresh session.

## Goal

Let an agent do what a user does on the website: open an EDA-backed differential
expression or antibody array search, explore the samples, pick a contrast, run
DESeq2 or limma, and turn the result into a normal WDK step. The step must return
the same genes the website would.

On the website the EDA "notebook" replaces the WDK question form. The user filters
samples, looks at a PCA plot, chooses the contrast, and drags volcano thresholds.
All of that is saved as a JSON string in the WDK param `eda_analysis_spec`. When
the user clicks "Get answer", a WSF process query asks EDA for the same genes. The
skill reproduces the notebook part with scripts and hands the same JSON to the
existing WDK tooling.

**The key design aim is contrast discovery.** Finding the "most appropriate"
contrasts in a study must work from two angles: whole-genome (which contrasts are
worth running) and gene-centric (how gene X behaves across DE-ready datasets).

## Wider context (motivation, NOT in scope)

The long-term aim is to use skills to prototype richer per-gene summaries:

1. Combine DESeq2 contrasts (log2FC and p-values) with the existing per-sample
   expression data (TPM, percentiles, log2ratios) that already feeds VEuPathDB's
   LLM per-experiment summaries and summary-of-summaries.
2. Possibly extend to antibody arrays, then protein features and orthologs, towards
   a holistic gene summary.
3. Possibly move it back into server-side code later, as cached summaries shared
   between users.

This spec does **not** promise expression summaries. Publicly, only EDA support is
promised as the next step for `veupathdb_database`.

**The summaries would live in a separate skill in this repo**,
`veupathdb_gene_summaries`, planned as of 2026-10-03. It would aim wider than
expression (protein features such as signal peptides, orthologs and so on) and
use `veupathdb_database` purely for data access. First-stage summaries stay
**siloed**: each sees only its own input and does not know the gene id, name or
other annotations. Only the final summary-of-summaries sees everything. This
keeps `veupathdb_database` a plain database skill alongside `ensembl_database`
and `interpro_database`, and the two skills can be submitted to science-skills
separately. How the summaries skill calls this skill's scripts (sibling paths or
a documented CLI contract) is for its own design.

Four design choices follow from the motivation:

- **The scripts handle deterministic work; the agent handles judgement.**
  Enumerating contrasts, canonicalising them, building specs and shaping DE tables
  are pure functions with JSON contracts and offline tests, so they can be ported
  to a server. Choosing which contrast makes biological sense stays with the LLM,
  which has the study description and the user's question.
- **Canonical contrasts fill a shared cache.** EDA compute jobs are keyed by a hash
  of the request, with no user identity (see Facts). A canonical contrast always
  produces the same job, so results are reused across agents, sessions, website
  users and any future server pipeline. The job id doubles as a stable
  **contrast id** that summaries can cite.
- **Outputs join to existing data.** They use the same gene ids and `DS_…` dataset
  ids as the existing `wdk.py expression` and `gene-expression` subcommands, and
  JSON throughout.
- **Gene identity is separate from data in JSON outputs.** A blind first-stage
  summariser must not see which gene it is looking at, but it does need the
  experimental context, or the numbers mean nothing. JSON outputs therefore keep
  three kinds of field apart, so a consumer can strip what it needs with a simple
  key filter:
  - **Gene identity** (gene ids): in an `identity` block mapping opaque row keys
    to gene ids. This is the only part a blind consumer strips.
  - **Experimental context** (comparator variable, groupA/groupB labels such as
    `sex=male` vs `sex=female`, which group is the reference, n_A and n_B,
    method, filters, thresholds, study description): in a `context` block, kept.
  - **Provenance** (dataset `DS_…` id, contrast/job id): in a `provenance`
    block. A blind consumer does not need it, but keeps it to attach to its
    output for later stages to cite. This matches the existing server-side
    expression summaries (ApiCommonWebsite `Summarizer.java`): `dataset_id` is
    removed before the per-experiment call and added back, with `assay_type`
    and `experiment_name`, to that call's output for the summary-of-summaries.

  Per-gene numbers (effect sizes, p-values) go in `rows` keyed by the opaque key.
  This skill only provides the separation; it does no summarising. The exact
  shape is settled in the plan.

## Scope

In scope, built in three stages, each independently testable and committed:

1. **Stage 1, core contrast loop:** `eda.py study`, `contrasts`, `de`, `de-spec`,
   `de-datasets`, and the WDK step handoff.
2. **Stage 2, sample filtering:** `--filters` on `study`, `contrasts`, `de`,
   `de-spec` and `pca`. `study --filters` *is* the subset preview; there is no
   separate command.
3. **Stage 3, PCA:** `eda.py pca`.

Out of scope: WGCNA notebook searches (their SQL ignores the spec), phenotype and
other `GenesByEdaSubset*` searches, general EDA exploration, the
`differentialabundance` compute (MicrobiomeDB), batch commands across many
datasets (the agent loops for now), and expression summaries.

## Sources consulted (read-only)

| Repo | Path | Commit / branch |
|---|---|---|
| pathfinder (fork `ahmedOmuharram/pathfinder`) | `~/work/pathfinder-as-a-skill/pathfinder`, `docs/knowledge/eda/*.md` | `8a8d6f25` `pydantic-ai` (machine A) |
| pathfinder (upstream `VEuPathDB/pathfinder`) | `~/work/pathfinder`, `docs/knowledge/eda/*.md` | `39399c2b` `pydantic-ai` (machine B; descends from `8a8d6f25`; `eda-wdk-bridge.md` and `rest-surface.md` have changed since) |
| ApiCommonWebService | `~/work/EDA/ApiCommonWebService/WSFPlugin/src/main/java/org/apidb/apicomplexa/wsfplugin/eda/` | `069d725` master (same on both machines, = origin as of 2026-10-03) |
| ApiCommonModel | `~/work/EDA/ApiCommonModel` (`Model/lib/dst/antibodyArray.dst`, `rnaSeqTemplates.dst`, `geneQueries.xml`) | `88b6dfaa5` master (2026-09-30; same on both machines) |
| service-eda | `~/work/EDA/service-eda` | `b3bb8bac` master (2026-07-28; = origin as of 2026-10-03, so current) |
| veupathUtils (R) | `~/work/EDA/veupathUtils/R/method-differentialExpression.R`, `method-pca.R` | `df5bfa2` v2.12.11 `main` (same on both machines) |
| web-monorepo | `~/work/EDA/web-monorepo/packages/libs/eda/src/lib/notebook/` | `564bc092d3` `main` (2026-10-03) |
| ApiCommonWebsite (server-side AI expression summaries; motivation only) | `~/work/ai-wdk/ApiCommonWebsite/Model/src/main/java/org/apidb/apicommon/model/report/ai/expression/Summarizer.java` | `f7104264d` master (2026-10-01) |

Two machines hold these checkouts at the same paths. Machine A was used to write
this spec. Machine B has upstream pathfinder.

Pathfinder EDA docs worth reading during implementation: `eda-wdk-bridge.md`,
`notebook-presets.md`, `computes-and-jobs.md`, `subsetting-and-tabular.md`,
`data-model.md`, `rest-surface.md`, `visualizations.md`.

**Known error in pathfinder docs:** the binding table in `notebook-presets.md` says
antibody-array notebook searches use the subset query. In current ApiCommonModel,
`GenesByAntibodyArrayEdaSubset_${datasetName}` uses
`queryRef="GeneId.GenesByEdaVizWithCompute"` (`antibodyArray.dst` line 157), the
same bridge as DESeq.

## Facts established (verified in source unless marked)

### The bridge

- Two params, `eda_dataset_id` (hidden, defaulting to `DS_…`) and
  `eda_analysis_spec` (a JSON string; empty means no filters). The spec's
  `studyId` field holds a **dataset** id (`DS_…`) and must equal `eda_dataset_id`.
  The plugin resolves the real `STUDY_…` id via `GET {eda}/permissions` →
  `perDataset[DS].studyId`.
- DESeq searches (`GenesByRNASeq{ds}DESeq`, edaNotebookType
  `differentialExpressionNotebook`) and antibody-array searches
  (`GenesByAntibodyArrayEdaSubset_{ds}`, `antibodyArrayNotebook`) both run
  `GeneEdaVizWithComputePlugin`. VDI user datasets use `GenesByDESeqUserDataset`.
  Identify EDA searches by the `eda_analysis_spec` param or the `edaNotebookType`
  property, never by name.
- The plugin takes the **first computation that has a `volcanoplot`
  visualization** whose configuration includes both `effectSizeThreshold` and
  `significanceThreshold`. It then:
  1. POSTs `{eda}/computes/{type}?autostart=true` with body
     `{studyId: STUDY_…, config: <computeConfig>, filters: <subset descriptor>, derivedVariables: []}`.
     `complete` proceeds, `queued`/`in-progress` → delayed result,
     `failed`/`expired`/`no-such-job` → error.
  2. POSTs `{eda}/apps/{type}/visualizations/volcanoplot` with
     `{studyId, filters, computeConfig, config: {}}` and reads `statistics[]`
     (`pointID`, `effectSize`, `pValue`).
  3. Keeps a row when raw `pValue <= significanceThreshold` AND
     `|effectSize| >= effectSizeThreshold`, then applies `effectDirection`
     (`upOnly` keeps > 0, `downOnly` keeps < 0, anything else is `upAndDown`).
  4. Joins genes to transcripts. The step has dynamic columns `effectSize` and
     `pValue`.
- **Raw p-value, not adjusted**, in both the plugin and the website volcano plot
  (`VolcanoPlotVisualization.tsx` uses `d.pValue`).
- While a job runs, the WDK answer returns **HTTP 202**
  `{"message":"WDK-DELAYED-RESULT","status":"accepted"}`, and the WDK request
  itself starts the job. `_client.py` already detects and retries this
  (`_client.py:110`, `:151`).
- **Auth:** the plugin calls EDA with `Authorization: Bearer <user token>`. WDK
  uses a cookie (`Authorization=<token>`). The skill's existing token works for
  both; only the transport differs.

### Compute cache / job identity

`service-eda/src/main/kotlin/.../compute/util/JobIDs.kt`:
`jobId = MD5([pluginUrlSegment, keySortedJson(requestBody)])`. Null `filters` and
`derivedVariables` become `[]`, and keys are sorted. No user identity is included,
so **jobs are shared across users**.

- Volcano thresholds live in the visualization config and are **not** part of the
  hash. A completed job returns statistics for every gene, so thresholds can be
  applied locally at no cost.
- Any change to filters, `studyId`, the method, or the comparator (including
  swapping groupA and groupB, or the order of labels within a group) is a
  different job.
- **Swapping groupA and groupB changes the job id but not the statistics**, apart
  from sign. The design is a single two-level factor with no shrinkage, so
  DESeq2's Wald test and limma's `coef=2` give the same p and padj with
  effectSize negated (independent filtering uses baseMean, which the swap leaves
  alone). This is from reading veupathUtils; a live gold test confirms it
  numerically. The skill uses it for **mirror reuse** (see `de`).
- `POST /computes/{name}?autostart=false` reports status **without starting** the
  job (pathfinder measured this live). `GET /jobs/{id}` also reports status.
- If the skill sends exactly the body the plugin sends, it gets the same job id
  as the WDK step, so creating the step afterwards returns 200 immediately.

### DE compute semantics

From `service-eda/.../differentialexpression/DifferentialExpressionPlugin.java`
and veupathUtils `R/method-differentialExpression.R`:

- Config: `identifierVariable` (`VEUPATHDB_GENE_ID`), `valueVariable` (one of the
  reserved ids below), `comparator {variable, groupA[], groupB[]}`,
  `differentialExpressionMethod` (`"DESeq"` | `"limma"`), `pValueFloor` (default
  `"1e-200"`). Groups are `LabeledRange` lists: several categorical labels can be
  pooled, or numeric ranges used with `binStart`/`binEnd`.
- **One comparator, no covariates, no paired design.** The design is
  `~comparator` only.
- **Orientation: groupA is the reference.** Values are relabelled to the literal
  strings `"groupA"`/`"groupB"`, so factor levels are alphabetical. DESeq2 uses
  plain `results()`, which gives log2(B/A). limma uses `topTable(coef=2)`, also
  B vs A. **A positive effectSize means higher in groupB.**
- No `lfcShrink`, so log2FCs are unshrunk and noisy for low counts.
- Output is only `effectSize`, `pValue`, `adjustedPValue` and `pointID`. There is
  no `baseMean`.
- `adjustedPValue` is NA where DESeq2's independent filtering removed the gene
  (mostly low counts).
- Genes that are all zero are dropped before fitting, so a gene absent from the
  output was *not tested*; it is not "unchanged".
- P-values are floored at `pValueFloor`. Adjusted p-values are floored to the
  largest padj among the floored rows.
- Size factors use a geometric mean over non-zero counts (poscounts-like).
- DESeq rounds the mean of duplicate gene rows to an integer; limma uses the mean.

### Reserved variable ids

`VEUPATHDB_GENE_ID` (identifier); values `SEQUENCE_READ_COUNT`,
`SEQUENCE_READ_COUNT_SENSE`, `SEQUENCE_READ_COUNT_ANTISENSE`,
`NORMALIZED_EXPRESSION`, `NORMALIZED_INTENSITY`. A study is DE-capable when its
gene entity has the identifier and at least one value id. The comparator must sit
on a parent entity of the expression entity (a notebook constraint).

### Notebook presets (web-monorepo `notebook/notebooks/`)

- `differentialExpressionNotebook`:
  1. subset
  2. shared inputs (`identifierVariable`, `valueVariable`) for `pca_1` and `de_1`
  3. `dimensionalityreduction` `pca_1` with `configOverrides {dataFormat: 'rawCounts'}` and a scatterplot
  4. `differentialexpression` `de_1` (default method `DESeq`, `pValueFloor '1e-200'`) with `volcanoplot` `volcano_1` and a review cell
- `antibodyArrayNotebook`: the same, except PCA uses `dataFormat: 'normalizedValues'`
  and DE uses `configOverrides {differentialExpressionMethod: 'limma'}`.
- Ready when `identifierVariable`, `valueVariable`, `comparator.groupA` and
  `comparator.groupB` are all set.

### PCA compute (what it does and doesn't return)

From `DimensionalityReductionPlugin.java` and veupathUtils `R/method-pca.R`:
`prcomp` over the samples × genes matrix. It returns **only per-sample PC scores**
(id columns plus PC1..nPCs). `nPCs` defaults to **2** in the service (the R
function's default of 10 does not apply). Variance explained appears only inside
computed-variable display names (`"PC 1 (34.2% variance)"`). There are **no**
metadata associations; the notebook's "colour by" is client-side. **Everything
beyond the scores is computed locally by `eda.py`.**

### Metadata and counting endpoints (pathfinder `subsetting-and-tabular.md`, `data-model.md`)

- `GET /studies/{STUDY}` returns the entity tree with variables: `vocabulary`,
  `distinctValuesCount`, `dataShape`, `type` (including `category` nodes),
  `hideFrom` (`everywhere`, `variableTree`), `isFeatured`, `units`,
  `distributionDefaults` (range and binWidth), `definition`, and many fields of
  no use to an agent.
- `POST .../entities/{e}/count {filters}` returns a count.
  `POST .../entities/{e}/tabular {filters, outputVariableIds}` returns TSV/JSON
  with ancestor primary keys prepended (nearest first). Always send `filters`,
  even when empty.
- `POST .../variables/{v}/distribution {filters, valueSpec, binSpec?}` returns
  histogram and statistics. A continuous variable **requires** `binSpec`; a
  categorical one must **not** have it. `valueSpec: proportion` is ignored, so
  compute proportions locally.
- Filters propagate across the whole entity tree.

## Architecture

New CLI `veupathdb_database/scripts/eda.py` (PEP 723, `httpx` only, same
conventions as `wdk.py`), with private modules:

| Module | Responsibility |
|---|---|
| `_client.py` (extend) | EDA transport: base `https://{site}/eda`, `Authorization: Bearer` header, same token source as WDK, retry and backoff, metadata cache (`~/.cache/veupathdb-wdk/eda/`, 7-day TTL like the catalog) |
| `_eda.py` | Endpoint wrappers: permissions (DS → STUDY), study metadata, count, tabular, distribution (fallback), compute status/start, volcano statistics, PCA scores |
| `_samples.py` | Metadata pruning, sample-table assembly (joining entities on ancestor keys), local counts and ranges |
| `_contrasts.py` | Candidate enumeration, replicate checks, confounding and nesting detection, stratification suggestions, canonicalisation, job-id derivation (MD5 identical to `JobIDs.kt`) |
| `_de.py` | Compute body and spec builders (matching the plugin exactly), DE result shaping and thresholding |
| `_stats.py` | All statistics: PCA associations (r, R², eta²), outliers, and any other numerical summaries. Standard library only (see below) |

**Statistics are zero-dependency Python.** `_stats.py` uses only the standard
library (`math`, `statistics`), with no numpy, scipy or pandas, so the skill
stays light to install and the code can be ported later. R is a **development
dependency only**, needed on the machine that runs the tests, where base R
(`cor`, `aov`/`lm` and so on) serves as the gold standard (see Testing). Nothing
the skill runs at use time needs R.

Why a separate CLI rather than more `wdk.py` subcommands: EDA is a different API
with different auth, `wdk.py` is already 959 lines, and a separate CLI keeps each
piece testable on its own. The handoff point is a spec JSON file. It can be
inspected and diffed, and it is exactly what the website would save.

## Agent workflow

1. Find the search: run `eda.py de-datasets SITE` or the existing
   `wdk.py find-searches`/`catalog`. **Change needed:** those currently hide
   `eda_` searches by default (`DEFAULT_EXCLUDED_PARAM_PREFIXES = ("eda_",)` in
   `_client.py:205`). Stop hiding DE and antibody-array notebook searches and tag
   them, e.g. `[EDA notebook: differentialExpression]`. Keep hiding other `eda_`
   searches, or tag those as unsupported.
2. Run `eda.py study SITE DS_…` to see the samples and their annotation.
3. *(stage 3)* Run `eda.py pca SITE DS_…` to check for batch effects and outliers.
   *(stage 2)* Then optionally use `--filters` and re-run `study --filters` to
   confirm.
4. Run `eda.py contrasts SITE DS_…` for canonical candidates. The agent chooses,
   using the study description and the user's question.
5. Run `eda.py de SITE DS_… --contrast N` to compute or reuse the job and see how
   many genes pass and which are top. Re-thresholding costs nothing.
6. Run `eda.py de-spec … --save`, which writes the WDK params to the skill cache
   and prints a ready strategy leaf, then `wdk.py create-strategy` with that leaf
   (needs `@file` support for param values; see Handoff and Files).

## Commands

### `eda.py study SITE DATASET_ID [--filters JSON|FILE] [--json]`

A pruned overview of the study, built for agent context.

- **Data:** one metadata fetch (cached) plus **one `/tabular` call per
  sample-side entity** (every entity except the gene/expression entity), with all
  surviving variables as `outputVariableIds`. Entities are joined locally on
  ancestor keys into one sample table, and counts and ranges are computed
  locally. This costs one request however many variables there are; antibody-array
  studies can have 40+. It also gives the **joint** structure that contrast
  discovery needs. Fall back to per-variable `/distribution` when an entity has
  more than about 5,000 rows.
- **Gene/expression entity:** a single line with the gene count (distinct
  `VEUPATHDB_GENE_ID`) and which reserved value ids are present. This is the
  "DE-ready?" answer. No per-variable listing and no data calls on it.
- **Pruning:**
  - Drop `providerLabel`, `displayOrder`, `isTemporal`, `isMergeKey`,
    `imputeZero`, `hasStudyDependentVocabulary`, `displayType`,
    `distributionDefaults` internals, and empty `definition`. Truncate a
    non-empty `definition` to about 120 characters.
  - Omit variables whose `hideFrom` contains `everywhere` or `variableTree`.
  - Show `category` nodes as indented headings, not entries.
  - **Identifier-like** variables (more than 20 distinct values covering at least
    90% of records) get one line, with no vocabulary.
  - Large vocabularies show the top 10 counts, then "… N more".
  - Star featured variables.
- **Each variable line:** id, display name, shape/type and units, then counts
  (categorical) or min–max, mean and missing (continuous).
- **Example:**

```
STUDY_e973eadd57 (DS_e973eadd57) "Heat shock response in sensitive mutants…"
DE-ready: gene entity ENT_fd574cd6 "pfal3D7 htseq counts" — VEUPATHDB_GENE_ID (5720),
          values: SEQUENCE_READ_COUNT_SENSE, SEQUENCE_READ_COUNT_ANTISENSE
ENT_8151325d "Sample" — 12 records
  VAR_081ab087  temperature condition  [categorical]  febrile 6 · normal 6
  VAR_…         time point (h)         [continuous]   0–48, mean 20, 0 missing
  VAR_…         sample name            [identifier: 12 distinct / 12 records]
```

- With `--filters`, every count reflects the subset, and entity lines read
  "9 of 12 records".
- With `--json`, the output is the pruned structure plus the sample table (rows
  of `{sampleId, var: value}`), and later commands can consume it.
- Include the study or dataset description when available (from study metadata,
  or from the WDK dataset record). The agent needs it to choose contrasts.

### `eda.py contrasts SITE DATASET_ID [--filters JSON|FILE] [--vars V1,V2] [--json]`

Deterministic enumeration; the agent ranks the results.

1. **Comparator candidates:** categorical variables, or continuous ones as binned
   ranges, on the expression entity's parent or higher, with at least 2 levels
   present.
2. **Groups:** levels with sample counts. Exclude levels with fewer than 2
   samples; flag fewer than 3. List pairwise contrasts when there are 6 or fewer
   levels; otherwise summarise and let the agent pool levels (groups can hold
   several labels).
3. **Design structure:** detect confounded pairs (one variable fully determines
   another, e.g. condition = batch) and crossed or nested factors. Because the
   compute has no covariates, crossed designs get **stratified contrast
   suggestions** ("A vs B, filtered to factor2 = x"), each with its own replicate
   counts.
4. **Cache status:** for each candidate, `POST /computes/differentialexpression?autostart=false`
   (status only, does not start a job) reports `complete`, `no-such-job` and so
   on. "Complete" means free to use, and also hints at which contrasts website
   users actually run. Cap at about 30 checks per call.
5. **Bounded list:** each pair of levels appears once (never in both
   orientations), pooled groups are never generated, and the whole list is capped
   (about 50 candidates; crossed designs multiply stratified versions). The output
   says how many were left out and suggests `--vars`.
6. **Output:** for each candidate, an index, comparator `{entityId, variableId}`,
   groupA labels (reference), groupB labels, a `reference` hint (`label match`
   or `arbitrary`), filters, n_A, n_B, notes (low replicates, confounded-with),
   cache status and job id.

**Choosing the reference is the agent's call.** A synonym list (control, WT,
mock, naïve, pre-infection, …) cannot be made failsafe, so the scripts only
suggest an orientation: a control-like label goes in groupA (`label match`),
otherwise groupA is the larger level (`arbitrary`). The agent can flip it with a
contrast file. Some variation between runs is acceptable here because of mirror
reuse: a flipped contrast whose mirror is cached costs nothing.

**Canonical form** (used everywhere a contrast is built):
- groupA is the reference/control, groupB the treatment/condition, as chosen by
  the agent from the suggested orientation.
- Labels sorted within each group; filters sorted by (entityId, variableId).
- `pValueFloor: "1e-200"` and the method implied by the search family (DESeq for
  `…DESeq` and `GenesByDESeqUserDataset`, limma for antibody arrays).
- `valueVariable`: prefer `SEQUENCE_READ_COUNT`. If only the stranded variables
  exist, list both and let the agent choose (sense is the usual one). For arrays,
  use `NORMALIZED_INTENSITY`, or whatever value id is present.
- **The compute body must be byte-for-byte the shape the plugin sends**
  (`{studyId: STUDY_…, config, filters, derivedVariables: []}`). The job ids then
  match those from WDK steps and website notebooks. A unit test computes the MD5
  locally and checks it against a captured live job id.

### `eda.py de SITE DATASET_ID --contrast <idx | JSON | file.json> [--method auto|DESeq|limma] [--thresholds FC,P[,upOnly|downOnly]] [--genes ID,…] [--tsv FILE] [--json] [--no-wait] [--no-mirror]`

- Builds the canonical body, then POSTs `?autostart=true` and polls (backoff,
  progress on stderr, configurable timeout). `--no-wait` returns after starting
  and reports status.
- **Mirror reuse:** before starting anything, `de` checks the job's status. If
  it has never run (`no-such-job`) and the swapped-groups job is `complete`, `de`
  uses the mirror's statistics with effectSize negated and starts nothing.
  Provenance keeps this orientation's job id as the contrast id and adds
  `statisticsFrom` (the mirror job). A note warns that the WDK step for this
  orientation is not cached and will start its own job. Failed or expired jobs
  never fall back to the mirror. `--no-mirror` turns reuse off.
- When complete, fetches the volcano statistics once (`/apps/differentialexpression/visualizations/volcanoplot`)
  and applies thresholds locally, exactly as `isRetainedRow` does (default 1,
  0.05, upAndDown, as on the website).
- **Report:**
  - job id (contrast id), comparator and groups with n_A and n_B, method
  - genes tested, padj-NA count
  - genes passing by raw p (what the WDK step will return) **and** by padj
  - top N up and down by effect size among genes passing padj
- `--genes` prints just those rows, marking genes as absent (not tested) or
  padj NA (filtered).
- `--tsv` writes the full table: gene, effectSize, pValue, adjustedPValue.
- `--json` produces a machine-readable result: contrast id, dataset, comparator,
  groups, counts, thresholds, rows on request. It uses the
  `identity`/`context`/`provenance`/`rows` split described under Wider context.
  This is the contract for later consumers such as `veupathdb_gene_summaries`.

### `eda.py de-spec SITE DATASET_ID --contrast … [--thresholds …] [--filters …] [--format spec|params] [--save]`

Writes the complete `eda_analysis_spec` (or the WDK params) to stdout, or with
`--save` to the skill cache (see Files):
- `studyId` = DS id, `displayName` and `description`, `isPublic: false`, and the
  boilerplate fields the plugin's empty-spec synthesiser uses.
- `descriptor.subset.descriptor` = filters.
- `computations`: `pca_1` (dimensionalityreduction, notebook config) and `de_1`
  (differentialexpression, canonical config), with a `volcanoplot` visualization
  `volcano_1` carrying `effectSizeThreshold`, `significanceThreshold` and
  `effectDirection`.
- `starredVariables: []`, `dataTableConfig: {}`, `derivedVariables: []`.

The DE computation's config must be identical to what `de` hashed. Validate it
against the plugin's rules before printing.

### `eda.py pca SITE DATASET_ID [--filters JSON|FILE] [--value-var V] [--npcs N] [--json]` (stage 3)

- Runs `dimensionalityreduction` with the notebook's config: `dataFormat` is
  `rawCounts` for RNA-Seq and `normalizedValues` for arrays, and shared
  identifier/value variables. **By default it sends the notebook's config
  unchanged** so the job hash matches website PCA runs and gets reused. `--npcs 5`
  sends an explicit `nPCs`, which is a new job, for when batch effects may sit on
  PC3 or PC4.
- Fetches the per-sample scores (job output files or the scatterplot endpoint; to
  be settled in the plan) and parses variance explained from the computed-variable
  display names (fragile, so it gets a test). Reading variance explained from a
  label is tech debt; returning it as data is a candidate server-side change for
  later.
- **Computed locally by `eda.py`:**
  - each PC joined to the sample table
  - for each sample variable, scored against **each PC separately** (PC1 and
    PC2 by default, since that is what the notebook config returns): Pearson r
    and R² for continuous variables, eta² (one-way ANOVA) for categorical ones,
    each with the n used and, for categorical, the number of levels. No combined
    score across PCs; the agent weighs PC1 and PC2 hits itself, using variance
    explained.
  - a ranked list of "variables that track PC k" for each PC, which replaces
    trying colourings one at a time
  - outliers more than 3 SD from the centroid in PC1–PC2 (or the first k PCs),
    suggested as filter candidates
- **Edge cases** (each reported as "not scored: <reason>", never silently
  dropped or turned into a misleading score):
  - a variable with only one distinct value among the samples (constant, which
    is common after `--filters`)
  - fewer than 3 samples with a value, after dropping missing values per
    variable
  - a categorical variable with as many levels as samples, or no level with
    2 or more samples: eta² would be 1 by construction. Identifier-like
    variables fall here.
  - a PC with zero variance (e.g. very few samples)
  - outlier detection when the SD is zero or there are too few samples
  Singleton levels are allowed but visible through the reported n and level
  count, since eta² inflates as levels approach n.
- Output: compact text plus `--json`.

### `eda.py de-datasets SITE [--json]`

Lists DE-ready searches for the gene-centric view: search name, display name,
`DS_…` id, notebook type and method. Built from the cached WDK catalog (searches
whose `edaNotebookType` is `differentialExpressionNotebook` or
`antibodyArrayNotebook`, or searches with `eda_analysis_spec` plus the volcano
query). Running across datasets for one gene is an agent loop in v1:
`contrasts` → `de --genes X`.

## WDK handoff

- `wdk.py create-strategy` (and `count`/`preview`) must accept a param value from
  a file. `--params` is currently an inline JSON string (`wdk.py:817`, `:823`).
  Add `--params @file.json` or a per-param `@file` value, whichever fits existing
  code best (decide in the plan). The spec is a JSON **string** inside the params
  object, so stringify it.
- Pass `eda_dataset_id` explicitly as the DS id. It is hidden but must match the
  spec's `studyId`.
- Since `de` has already completed the job, the answer should return 200 at once.
  The existing 202 handling covers the case where it hasn't.
- Optional result check: the step's `totalCount` should equal the number of genes
  passing raw p at the thresholds from `de`. Transcripts versus genes may differ:
  compare against `displayTotalCount` or gene count, per the pathfinder
  measurement of 1543 genes vs 1571 transcripts.

## Files

The skill will run in users' bioinformatics work directories, so it must not
leave glue files there or let parallel sessions clobber each other's.

- `--contrast` and `--filters` accept **inline JSON** as well as a file path. The
  objects are small, so a normal session needs no files of its own.
- `de-spec --save` writes the WDK params to
  `~/.cache/veupathdb-wdk/eda/params/{sha256 prefix}.json`. The name is a hash of
  the content: identical content gives the same file, and different contrasts or
  thresholds never collide. Writes use a temp file and an atomic rename. Files
  older than the cache TTL (7 days) are pruned. It prints
  `{"paramsFile", "leaf": {"search", "params": "@PATH"}}`, so several DE leaves can
  go in one strategy tree.
- Where results the user wants to keep are saved (`--tsv`, JSON) is for the user
  and their agent to decide; the skill only says so.

## Errors

- Failed or expired job: report the job id and status. `--retry` re-POSTs with
  autostart. Explain that a job which failed quickly usually means a bad config
  (e.g. value and identifier variables on different entities).
- Too few replicates (n < 2 in either group): refuse before submitting. n = 2:
  warn.
- Dataset not visible to the user (missing from `/permissions` `perDataset`):
  clear message, suggest checking login and site.
- Unknown variable or label: error with a `difflib` suggestion, as `wdk.py` does.
- Comparator not on a parent entity of the expression entity: refuse, quoting the
  notebook rule.
- Never print the token.

## Testing

- **Offline unit tests** using fixtures captured from live calls (store them under
  `tests/fixtures/eda/`):
  - metadata pruning and identifier detection
  - joining the sample table across entities
  - contrast enumeration, confounding and nesting detection, stratification
  - canonicalisation (label and filter order invariance)
  - one orientation per level pair with its `reference` hint; the overall
    candidate cap
  - mirror reuse: negated effect sizes, both job ids in provenance, nothing started
  - job-id MD5 matches a captured live job id
  - spec builder output accepted by the plugin's rules (volcano present, both
    thresholds, `studyId` = DS)
  - threshold logic identical to `isRetainedRow`
  - variance-label parsing
  - every edge case listed under `pca`, each giving its "not scored" reason
  - Fixture studies: the heat-shock RNA-Seq study `DS_e973eadd57` /
    `STUDY_e973eadd57` on PlasmoDB (12 samples, `VAR_081ab087` febrile/normal
    6/6, stranded counts) and one PlasmoDB antibody-array study (pick from the 5
    `GenesByAntibodyArrayEdaSubset_*`).
- **R gold-standard tests** for `_stats.py`: run base R (`Rscript`) on the same
  inputs and compare to the Python results within a stated tolerance. Cover
  r, R² and eta² (from `aov`/`lm`) on fixture sample tables and on synthetic
  cases: missing values, singleton levels, ties, and near-constant variables.
  These tests skip with a clear message when `Rscript` is not on PATH, so they
  run on the development machine and not in an R-less environment.
- **Live gold tests** registered in `TESTS.md`, as for the WDK suite:
  - the skill's job id equals the id the WDK step drives
  - the count passing at thresholds equals the WDK step's count (see the
    gene/transcript note)
  - a limma antibody-array run end to end
  - `contrasts` on the heat-shock study proposes febrile vs normal with 6/6
  - swapping groups on the heat-shock contrast negates effectSize and leaves p
    and padj unchanged, row for row (the basis of mirror reuse)

## SKILL.md restructure

SKILL.md is currently 229 lines, over its own 200-line limit.
- Make it a router: scope, auth (one token, cookie for WDK and Bearer for EDA),
  site selection, ID conventions (gene ids, `DS_` vs `STUDY_`), and a routing
  table ("searches/strategies → `references/wdk-*.md`; DE/antibody-array
  notebooks → `references/eda.md`").
- Move the WDK depth into references.
- Remove the "Differential expression (EDA) searches are excluded" rule
  (SKILL.md around line 184) and the "EDA" entry in the out-of-scope list.
- New `references/eda.md`: workflow, pruning, contrasts, canonical form, PCA
  interpretation.
- Add an EDA section to `gotchas.md`: raw-p thresholding, orientation, unshrunk
  LFC, padj NA, all-zero genes absent, single comparator with no covariates, a
  `studyId` that is really a DS id, 202 on first answer, cache sharing, swapped
  groups = new job id but the same statistics sign-flipped (mirror reuse), and
  the reference is the agent's choice.
- Update the frontmatter `description` to cover EDA-backed differential
  expression and antibody-array searches in concrete terms. Keep it crisp for
  triggering.

## Open items to settle in the plan (verify live)

1. Whether a `/tabular` request can output ancestor-entity variables directly, or
   needs one call per entity and a local join. The design assumes one call per
   entity, which is safe either way.
2. How to fetch PCA scores: `GET /jobs/{id}/files` plus the data file, or the
   scatterplot visualization endpoint. Also the exact config key for `nPCs`.
3. The exact pruned-output thresholds (identifier rule, vocabulary top-N, the
   ~30 cache-check cap, the ~50-candidate cap, the ~5,000-row fallback). Tune them on 2–3 real
   antibody-array studies with 40+ variables.
4. Where the study or dataset description comes from (EDA study metadata vs the
   WDK dataset record).
5. How `de-datasets` should detect searches (the `edaNotebookType` property in the
   catalog vs param inspection), and whether the catalog cache already holds
   question properties.

## Working conventions (from the user)

- Commit only; the user does all pushing.
- Publicly promise only EDA support as the next extension. Expression summaries
  are motivation, not a commitment.
- Target: submission of `veupathdb_database` to google-deepmind/science-skills,
  next to `ensembl_database` and `interpro_database`. Keep it one skill with
  routing in SKILL.md and depth in references.
