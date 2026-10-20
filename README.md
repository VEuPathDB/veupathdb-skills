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

### Use

Ask your agent a VEuPathDB question. A free VEuPathDB account is required, and the
agent walks you through saving your API key on first use.

## Development

Tests and gold standards are in `veupathdb_database/TESTS.md`; run them with
`uv run --with pytest --with httpx python -m pytest tests -q` from `veupathdb_database/`.
Design specs and plans are archived on the `docs` branch. Publishing a GitHub release
builds and attaches the skill zip.
