# Upstream decisions tracker

Pathfinder's `ai-wdk-mcp` repo records design decisions in `docs/knowledge/decisions/`
(index: `docs/knowledge/decisions/index.md`). Some bear on the `veupathdb_database` skill's
user experience. This file records, for each upstream decision, what we decided locally.
See "Tracking upstream decisions" in `AGENTS.md` for how to keep it current.

**Scope: the `veupathdb_database` skill only.** `tabular-to-stf` has no Pathfinder
counterpart and is not tracked here. This file lives at the repo root, outside both skill
directories, so it is not packaged in either release zip.

**Last reviewed against `ai-wdk-mcp` commit `17a56c5` (2026-11-11).**

## Status labels

| status | meaning |
| --- | --- |
| `to-do` | relevant and not yet applied; has a GitHub issue (link it) |
| `done` | applied here; link the PR |
| `undecided` | possibly relevant; needs a closer read or a scope decision |
| `not-relevant` | server internals or out of this skill's scope; add the reason |

## Decisions

Upstream file names are relative to `docs/knowledge/decisions/` in `ai-wdk-mcp`.

| upstream decision | status | link | note |
| --- | --- | --- | --- |
| `a-compare-past-one-expression-is-computed-from-group-clouds` | not-relevant | | OrthoMCL phyletic compare; phyletic patterns are out of scope |
| `a-control-test-files-every-id-it-was-given` | undecided | | control-gene workflow; no equivalent here. Copy the design if one is added |
| `a-curated-search-runs-on-its-datasets-assay` | undecided | | could annotate catalog lines with assay |
| `a-dataset-search-runs-on-its-datasets-organism` | undecided | | could annotate catalog lines with organisms |
| `a-decisions-choice-widens-the-candidates-and-doubts-a-vocabulary-pick` | not-relevant | | server-side LLM Decisions API |
| `a-frozen-step-is-keyed-by-the-account-it-lands-in` | not-relevant | | server cache |
| `a-keyed-engine-answers-first-and-prices-the-call` | not-relevant | | deprecated upstream; web search engine |
| `a-listing-page-never-outranks-a-paper` | not-relevant | | web-search ranking |
| `a-metasearch-the-deployment-runs-answers-first` | not-relevant | | web-search backend |
| `a-named-gene-is-read-by-its-record` | undecided | | `Orthologs` table for a whole group, transcript record for protein fields; possible note in `wdk-workflow.md` |
| `a-radio-pair-offers-a-term-as-two-readings` | to-do | [#11](https://github.com/VEuPathDB/veupathdb-skills/issues/11) | count both readings; accession-label caveat |
| `a-record-that-is-not-a-gene-is-read-as-a-table` | to-do | [#7](https://github.com/VEuPathDB/veupathdb-skills/issues/7) | organism/record-level facts (BUSCO, gene counts); site links |
| `a-search-note-fills-only-an-empty-description` | undecided | | OrthoMCL phyletic guidance; revisit if phyletic patterns enter scope |
| `a-separation-is-measured-on-the-site` | undecided | | control-set separation; no equivalent here |
| `a-served-result-validates-its-own-dump` | not-relevant | | server model validation |
| `a-short-model-names-the-frameshift-that-cut-it` | not-relevant | | gene-model audit |
| `a-step-read-is-bounded-by-its-caller` | to-do | [#8](https://github.com/VEuPathDB/veupathdb-skills/issues/8) | bounded `results`; loud site refusals |
| `a-strategy-holds-one-line-on-the-database` | not-relevant | | server DB locking |
| `a-vocabulary-lookup-reads-the-phrasings-of-a-term` | to-do | [#10](https://github.com/VEuPathDB/veupathdb-skills/issues/10) | phrase-aware `param-options --filter` |
| `an-audit-check-reads-its-genome-from-the-site` | not-relevant | | gene-model audit |
| `an-expensive-search-holds-one-line-on-the-database` | not-relevant | | server DB locking |
| `an-experiment-is-indexed-per-site` | undecided | | dataset cards ranked per site; not yet read in full |
| `an-input-step-search-is-listed-whatever-its-question-set` | to-do | [#9](https://github.com/VEuPathDB/veupathdb-skills/issues/9) | verify transforms such as `GenesByOrthologs` are still listed after #6 |
| `both-servers-prove-admission-here` | not-relevant | | upstream CI |
| `each-image-is-the-last-stage-of-its-own-dockerfile` | not-relevant | | upstream Docker build |
| `tests-run-against-qa-and-a-deployment-names-its-sites` | not-relevant | | upstream tests |
| `the-agent-finds-only-the-searches-the-ontology-offers` | done | [#6](https://github.com/VEuPathDB/veupathdb-skills/pull/6) | listings and find-searches offer only ontology-named searches |
| `the-catalog-shares-a-search-definition-across-logins` | not-relevant | | server catalog cache |
| `the-root-package-holds-what-both-servers-share` | not-relevant | | upstream packaging |
| `what-the-wire-serves-and-what-a-host-imports` | not-relevant | | upstream server architecture |
