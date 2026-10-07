# WDK workflow (wdk.py)

## Resolving gene symbols & names (don't web-search or use external APIs first!)

When asked about a gene by symbol, name, or product (e.g. `SRPN2`, `K13`):
- **Do NOT reach for WebSearch or external APIs (NCBI, Ensembl, etc.)** to look
  up accession IDs (`AGAP...`, `PF3D7_...`) or to "cross-check" annotations.
  VEuPathDB is the primary authority for these genomes; external resources
  frequently use different gene models, ortholog mappings, or obsolete builds.
- **Resolve with `GenesByText` preview first**:
  ```bash
  uv run scripts/wdk.py preview SITE GenesByText \
    --params '{"text_expression": "SYMBOL", "text_search_organism": ["Organism"], "text_fields": ["name", "Alias"]}' \
    --attributes primary_key,gene_name,gene_product
  ```
  - **`text_search_organism` is MANDATORY**: WDK has no default organism for `GenesByText` and rejects empty selections. Always specify the organism or species complex (e.g. `["Anopheles gambiae"]`, `["Plasmodium falciparum 3D7"]`). Tree parents auto-expand to all member strains.
  - To look up the exact organism name: `uv run scripts/wdk.py param-options SITE GenesByText text_search_organism --filter "organism"`
  - Matching symbols specifically: use `"text_fields": ["name", "Alias"]` (as shown above).
- **When is WebSearch acceptable?** ONLY as a fallback if VEuPathDB text search
  returns 0 hits, specifically to discover published nomenclature/hyphenation
  variants (e.g. `SRPN-2` vs `SRPN2`) or synonym aliases. Once a synonym is
  found, return to `GenesByText` or `fetch-record` inside VEuPathDB.

## The workflow

1. **Check auth & pick the site**: Verify with `whoami`. If unauthenticated or GUEST, do NOT probe `~/.config` or `env`; immediately follow the onboarding questionnaire in SKILL.md (`detect-site`, conduct questionnaire, run login for the user). Otherwise resolve the site with `detect-site "QUERY"` or list all 14 with `sites`.
2. **Discover searches** — dispatch a SUB-AGENT (keeps your context clean):
   its prompt = the research goal + "run `uv run scripts/wdk.py catalog SITE`,
   read every line, return 3–8 candidate searches (name, record type, why),
   tagged seed/filter/transform". The dump is ~25–75k tokens. No sub-agents
   available? Read the dump yourself. `find-searches SITE QUERY` is a quick
   lexical fallback when you already know roughly the name.
3. **Inspect each candidate**: `inspect-search SITE SEARCH [--query HINT]` returns the
   parameter sheet: required/optional params, defaults, vocabularies
   (truncated over 200 — fetch more with `param-options`), dependency notes,
   and `params_template` (copy it, fill values, null = use default).
   Copy vocabulary values EXACTLY. A tree parent term selects all its children.
4. **Dry-run cheaply** (no writes, parallelizable): `count SITE SEARCH --params
   JSON`, then `preview` to sanity-check actual records. A count of 0 usually
   means a wrong vocabulary value or an over-narrow AND — see
   references/gotchas.md before blaming the site.
5. **Create the strategy**: `create-strategy SITE --spec JSON --name "..."`.
   Spec nodes: {"leaf": {search, params}}, {"combine": {operator, left,
   right}} (UNION|INTERSECT|MINUS|RMINUS|LONLY|RONLY), {"transform": {search,
   params, input}}. Returns strategy id, per-step counts, and the website URL —
   give that URL to the user. Combine semantics: alternative evidence for the
   SAME property → UNION; distinct required properties → INTERSECT; nest
   multi-evidence branches (A ∩ (B ∪ C) ≠ (A ∩ B) ∪ C).
6. **Fetch results & records**: `results SITE --step ID`, `download-url SITE --step ID`.
   Discover schema: `inspect-record-type SITE RT [--filter Q]` (PK, attributes, tables).
   Inspect record/tables: `fetch-record SITE ID [--tables TBLS] [--filter TEXT]`.
   Transcriptomics & expression: `expression SITE GENE [--type T] [--filter Q] [--dataset DS]`.
   Manage: `strategy`, `list-strategies`, `delete-strategy ... --yes`.

## Subcommands

| cmd | purpose |
|---|---|
| sites | list site ids and service URLs |
| whoami SITE | verify token, print numeric user id |
| login [SITE] [--token K] [--email E --password P] | authenticate and store token in ~/.config/veupathdb/token |
| logout | remove stored token from ~/.config/veupathdb/token |
| detect-site QUERY | detect VEuPathDB site and URLs from query text |
| record-types SITE | list record type segments |
| inspect-record-type SITE RT [--filter Q] [--name-only] [--exclude P] | record schema: PK, attributes, tables |
| searches SITE RT | searches for one record type (TSV) |
| catalog SITE [--record-type RT] [--refresh] | full compact catalog (TSV) — discovery input |
| find-searches SITE QUERY | lexical convenience lookup |
| inspect-search SITE SEARCH [--filter HINT] | parameter sheet (alias: inspect) |
| param-options SITE SEARCH PARAM [--filter Q] [--context P=V] | browse a vocabulary |
| count SITE SEARCH --params JSON\|@file | count without creating anything |
| preview SITE SEARCH --params JSON\|@file [--limit N] [--attributes A] | sample records with search's default attributes (or custom) |
| create-strategy SITE --spec JSON\|@file [--name S] | steps + strategy, returns URL |
| strategy SITE ID / list-strategies SITE | read back |
| delete-strategy SITE ID --yes | destructive |
| results SITE --step ID [--limit N] [--attributes A] | records for a step (defaults to search's standard attributes) |
| download-url SITE --step ID | temporary download URL |
| fetch-record SITE [ID] [--tables T] [--filter F] | record details/tables with row filtering |
| expression SITE GENE [--type T] [--filter Q] [--dataset DS] | transcriptomics & 'omics expression (joined datasets + ranked samples) |
| (EDA searches) | DE and antibody-array notebook searches are listed and tagged [EDA notebook: …]; build their params with scripts/eda.py (references/eda.md) |

## WDK-specific gotchas

- **`inspect-record-type` and Protocol Application Nodes (`pan_`)**: Transcript records
  contain thousands of legacy GUS Protocol Application Node columns (`pan_<id>_ns_<id>`)
  and web graph widgets (`_expr_graph`). When querying schema, use `--name-only` to filter
  specifically on attribute names (avoiding false positives from long descriptions) or
  `--exclude pan_` / `--exclude "pan_,graph"` to suppress them.
- **Automatic default attributes for `preview` and `results`**: When `--attributes` is
  omitted, both `preview` and `results` dynamically look up and return the search's
  standard default columns (`defaultAttributes`, e.g. `gene_product`, `organism`,
  `primary_key`), exactly matching the website results table. Specify `--attributes` only
  when requesting custom non-default attributes.
- **Gene expression summaries and `ai_expression`**: To summarize transcript expression,
  run `wdk.py expression <site> <gene>`. The CLI outputs datasets ranked by peak percentile
  with their `top_sample` (e.g. 95th+ percentile) — summarize directly from this output.
  Do NOT write custom scripts in `scratch/` to dump all raw samples across dozens of
  datasets. The `ai_expression` attribute is an external web UI flag and is strictly
  **out of scope** (do not query, scrape, or automate it).
- **`fetch-record` attributes and `--tables Sequences` vs `GeneTranscripts`**:
  `fetch-record <site> <gene_id>` returns `transcript_count`, `exon_count`, `product`,
  and `location_text` directly in its default attributes without truncation.
  To list transcripts, use `--tables GeneTranscripts`. **Never use `--tables Sequences`**
  unless raw FASTA/DNA sequences are explicitly requested by the user: `Sequences` dumps
  multi-kilobase nucleotide sequences that trigger tool output truncation.
- **Never write ad-hoc Python subprocess wrapper scripts to parse CLI output**:
  In desktop agent environments (e.g. Antigravity Desktop), invoking inline Python commands
  (`python -c "import subprocess..."` or scripts in `scratch/`) triggers interactive
  security approval modals and interrupts the user. Always consume structured JSON output
  directly from `wdk.py` or use built-in CLI flags (`--attributes`, `--tables`, `--filter`).
- **ID-list searches (`GeneByLocusTag`) and `input-dataset` parameters**:
  Searches accepting gene ID lists (e.g. `GeneByLocusTag`) use parameter type `input-dataset`.
  The CLI automatically creates and uploads the dataset to WDK and substitutes the resulting
  numeric dataset ID. For a single gene lookup, `fetch-record <site> <gene_id>` is direct and preferred.
