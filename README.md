# veupathdb-skills

Agent skills for [VEuPathDB](https://veupathdb.org) genomics sites (PlasmoDB, VectorBase,
ToxoDB, FungiDB, TriTrypDB and others).

## veupathdb_database

Lets an agent query the VEuPathDB WDK and EDA REST APIs: find genes by biological
criteria, combine searches into strategies, count, preview and download results, fetch
gene records and expression tables, and run differential expression (DESeq2) and
antibody-array (limma) contrasts on EDA-backed datasets.

### Install

1. Download `veupathdb_database-<version>.zip` from the
   [latest release](../../releases/latest) (the named asset, not "Source code").
2. Unzip it into your agent's skills directory, e.g. `~/.claude/skills/` for Claude Code.
   The skill is the `veupathdb_database/` folder containing `SKILL.md`.
3. Install [uv](https://docs.astral.sh/uv/); the scripts run through `uv run`.
4. Recommended supply-chain protection: make uv ignore package versions published in
   the last week, so a freshly compromised release is never installed. Put this in
   `~/.config/uv/uv.toml`:

   ```toml
   exclude-newer = "1 week"
   ```

### Use

Ask your agent a VEuPathDB question. A free VEuPathDB account is required, and the
agent walks you through saving your API key on first use.

## tabular-to-stf

Turns a folder of related CSV/TSV tables (one file per entity, e.g. village, household,
participant, sample) into a Study Transfer Format (STF) directory that study-wrangler
loads and VEuPathDB EDA accepts. The agent profiles your data, asks you about it, and
writes a curation spec; scripts render and check the STF. Optionally it validates the
result in the pinned study-wrangler container.

### Install

1. Copy or symlink the `tabular-to-stf/` folder (the one containing `SKILL.md`) from a
   checkout of this repository into your agent's skills directory, e.g.
   `~/.claude/skills/` for Claude Code. There is no release zip for this skill yet.
2. Install [Node.js](https://nodejs.org) 18 or later. The scripts need no npm packages.
3. Optional: install Docker or Podman for container validation.

### Use

Ask your agent to convert your tables to STF and give it the input folder, an output
folder, and optionally a study description or data dictionary.

## Development

### veupathdb_database

Tests and gold standards are in `veupathdb_database/TESTS.md`; run them with
`uv run --with pytest --with httpx python -m pytest tests -q` from `veupathdb_database/`.

### tabular-to-stf

From `tabular-to-stf/`, run `npm test` (or `node --test tests/*.test.js`). Node 18 or
later, no install step. The golden tests render the fixtures in `tests/fixtures/tabular/`
and compare them with each `expected/` directory. Two groups are skipped by default:
the container tests (set `STF_CONTAINER_TESTS=1`; needs Docker or Podman and the pinned
study-wrangler image) and the 1M-row scale test (set `STF_SCALE_TEST=1`).

### Releases

Design specs and plans are archived on the `docs` branch. Publishing a GitHub release
builds and attaches the `veupathdb_database` zip; `tabular-to-stf` is not packaged yet.
