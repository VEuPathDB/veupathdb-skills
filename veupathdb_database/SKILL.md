---
name: veupathdb_database
description: Query VEuPathDB genomics sites (PlasmoDB, VectorBase, ToxoDB, FungiDB, TriTrypDB, CryptoDB, HostDB and others) through their WDK and EDA REST APIs. Use to find genes or other records by biological criteria, combine searches into strategies, count, preview or download results, fetch gene records and expression tables, and run differential expression (DESeq2) or antibody-array (limma) contrasts on EDA-backed RNA-Seq and protein-array datasets, turning a chosen contrast into a website search step.
---

# VEuPathDB database

Two CLIs, run from this skill's directory:

- `uv run scripts/wdk.py …`: searches, strategies, records, per-gene expression tables (WDK API).
- `uv run scripts/eda.py …`: differential-expression and antibody-array notebooks (EDA API).

stdout is JSON (wdk.py) or compact text with a `--json` option (eda.py); errors go
to stderr with exit 1; `--help` works on every subcommand. Supply-chain note: uv
installs are expected to be date-pinned via `exclude-newer` in `~/.config/uv/uv.toml`.

## Auth (required for everything)

One registered-user token serves both APIs (WDK reads it as a cookie, EDA as a
Bearer header). It lives in `~/.config/veupathdb/token` (mode 0600) or
`VEUPATHDB_BEARER_TOKEN`. Verify first:

    uv run scripts/wdk.py whoami plasmodb

> [!CRITICAL] **`whoami` is authoritative: DO NOT probe files or environment variables**
> `whoami` checks both token sources itself. If it exits 1 (no token, or a GUEST):
> - **DO NOT** inspect `~/.config/veupathdb/token` (`ls`, `cat`, etc.) or search environment variables.
> - **DO NOT** run other wdk.py/eda.py data commands; they fail with 401.
> Probing triggers alarming permission dialogs in desktop harnesses. **STOP** and run the onboarding below.

**Onboarding: YOU do the work; never tell chat/desktop users to open a terminal.**

1. `uv run scripts/wdk.py detect-site "<question or organism>"` → site id, `profile_url`, `registration_url`.
2. Ask with the harness question tool (Antigravity `ask_question`, Claude Code `AskUserQuestion`), or list the options in chat and wait:
   "VEuPathDB authentication is required to access <Project>. How would you like to proceed?"
   - "(Recommended) I have an account — I'll save my browser API key to a file (e.g. /tmp/<site>-key)"
   - "I have an account — I'll paste my browser API key directly into chat"
   - "I don't have an account yet — I need to register"
3. File: give `[<Project> Service Access Tab](<profile_url>)` (User menu → My Account → Service Access), ask for the file path in their next reply, then run `uv run scripts/wdk.py login <site> --token-file "<PATH>"`.
   Paste: give the same link, then run `printf '%s' "<PASTED_KEY>" | uv run scripts/wdk.py login <site> --token -`.
   Register: give `[Register at <Project>](<registration_url>)` (free, under a minute, single sign-on across all 14 sites), then continue with the file or paste route.
4. Verify with `whoami`, confirm, and **go straight back to the user's original request**.

Logout: `uv run scripts/wdk.py logout`. Details: references/auth.md.

## Sites and identifiers

- Site: `wdk.py detect-site "QUERY"`, or `wdk.py sites` for all 14 (`veupathdb` is the portal).
- Gene ids (`PF3D7_…`, `AGAP…`) are the join key everywhere. Resolve symbols and names
  with `GenesByText` (references/wdk-workflow.md), **never** web search or external
  databases first: VEuPathDB is the authority for these genome annotations.
- Dataset ids: `DS_…` is what WDK params, `wdk.py expression --dataset` and eda.py take.
  `STUDY_…` is EDA's internal id, which eda.py resolves for you. In an
  `eda_analysis_spec`, the `studyId` field holds the **DS_** id.

## Routing

| task | tool | read |
|---|---|---|
| find searches, count, preview, combine into strategies, results, downloads | wdk.py | references/wdk-workflow.md, parameters.md, strategies.md |
| one gene's record, tables, orthologs | `wdk.py fetch-record` | references/wdk-workflow.md |
| one gene's expression across datasets (TPM, percentiles) | `wdk.py expression` | references/wdk-workflow.md |
| differential expression or antibody-array contrasts; which contrasts a study supports; gene X across DE datasets | eda.py | references/eda.md |
| a result is 0 or looks wrong | | references/gotchas.md |

## WDK in brief (full workflow: references/wdk-workflow.md)

1. Discover searches in a SUB-AGENT: "run `uv run scripts/wdk.py catalog SITE`, read every
   line, return 3–8 candidate searches (name, record type, why), tagged seed/filter/transform".
   `find-searches SITE QUERY` is a quick lexical fallback.
2. `inspect-search SITE SEARCH [--query HINT]` → parameter sheet. Copy vocabulary values EXACTLY.
3. Dry-run with `count` and `preview` (`--params JSON` or `--params @file`).
4. `create-strategy SITE --spec JSON|@file --name "…"` → give the user the returned URL.
5. `results`, `download-url`, `fetch-record`, `expression`.

## EDA differential expression in brief (full detail: references/eda.md)

Supported: searches tagged `[EDA notebook: differentialExpression]` (DESeq2 on RNA-Seq
counts) and `[EDA notebook: antibodyArray]` (limma on array intensities). Other `eda_`
searches (WGCNA modules, phenotype subsets) are not supported.

1. `eda.py de-datasets SITE`: DS ids, methods and search names.
2. `eda.py study SITE DS_…`: samples, annotation, DE-readiness, the study description.
3. `eda.py contrasts SITE DS_…`: canonical candidates with n per group, confounding notes,
   stratified versions and cache status. **You** choose the contrast and its reference
   (groupA), using the description and the question; the suggested reference is a hint.
4. `eda.py de SITE DS_… --contrast N`: runs or reuses the shared job (or its cached
   swapped-groups mirror); counts and top genes.
   Re-thresholding (`--thresholds FC,P[,upOnly|downOnly]`) costs nothing.
5. `eda.py de-spec SITE DS_… --contrast N --save` prints a ready strategy `leaf`; use it
   in `wdk.py create-strategy SITE --spec '{"leaf": …}'`.

Pass the same `--filters`, `--vars`, `--value-var` and `--entity` to every command
after `contrasts`, or `--contrast N` names a different candidate. `study --filters '[…]'`
previews a sample subset. Give contrasts and filters
inline (`--contrast '{…}'`); glue files live in the skill cache (`--save`). Write files
to the user's directory only when they ask to keep them.

## Top gotchas (full list: references/gotchas.md)

- **Vocabulary values are exact strings.** Copy them from the sheet or `param-options`.
- **Tree parents are expanded to leaves** on submit: "Plasmodium" means all its genomes.
- **Multi-evidence needs enumeration**: a multi-pick param lists EVERY covered value.
- **Defaults are disclosed**: tell the user which search defaults applied.
- **No ad-hoc wrapper scripts** around the CLIs (they trigger approval dialogs in desktop
  harnesses): read the JSON output and use the built-in flags.
- **`--tables Sequences` dumps raw sequence**: use `GeneTranscripts` unless FASTA is asked for.
- **EDA thresholds use the raw p-value**, as the website does; `de` also reports padj counts.
- **groupA is the reference**: positive log2FC = higher in groupB. You pick it; `de` reuses a
  cached swapped-groups job with the sign flipped.
- **One comparator, no covariates, no pairing**: use the stratified contrasts for crossed designs.
- **A gene absent from DE output was not tested** (all-zero counts); it is not "unchanged".

## Reference files (read on demand)

- references/auth.md: tokens, onboarding detail, cookie vs Bearer transport
- references/wdk-workflow.md: WDK workflow, subcommand table, WDK-specific gotchas
- references/parameters.md: the 11 WDK param types, dependent vocabularies
- references/strategies.md: stepTree semantics, spec format, step kinds
- references/eda.md: EDA notebooks, contrasts, canonical form, results, handoff, JSON output
- references/gotchas.md: every known silent-failure mode

Out of scope: semantic search, site-search, enrichment, step analyses, result filters,
phyletic patterns, basket uploads, EDA searches other than the DE and antibody-array
notebooks, general EDA exploration, and the web UI's `ai_expression` summaries.
Tests and gold standards: TESTS.md.
