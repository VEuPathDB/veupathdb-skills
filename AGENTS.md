# Guidance for agents working in this repo

This repo holds standalone agent skills (`veupathdb_database/`, `tabular-to-stf/`). See
`README.md` for what each does and how it is released.

## Relationship to Pathfinder

`veupathdb_database` was ported from Pathfinder, VEuPathDB's tool-calling agent for building
search strategies. It is now a self-contained skill (Python scripts plus reference docs) with no
runtime dependency on Pathfinder. Pathfinder's source is still the best place to check how WDK
and EDA behave, and the skill's reference docs (`veupathdb_database/references/`) summarise
rules that are documented there.

The four Pathfinder repos, all under the `VEuPathDB` GitHub org:

| repo | what it holds |
| --- | --- |
| `ai-veupathdb-client` | typed Python client for WDK and EDA; `docs/knowledge/wdk/rules/` and `docs/knowledge/eda/` are the authoritative rule and surface docs |
| `ai-wdk-mcp` | MCP servers exposing WDK catalog, strategy and research tools |
| `ai-assistant-platform` | assistant runtime and wire protocol (no VEuPathDB science) |
| `pathfinder-app` | the Pathfinder application itself |

Refer to these repos by name in docs. Don't write historical narratives about the port.

## Setup: make the Pathfinder repos visible

Clone the four repos as siblings of this one (`../ai-veupathdb-client`, `../ai-wdk-mcp`,
`../ai-assistant-platform`, `../pathfinder-app`), then the **human user** must give the agent
access to those directories. This is a per-machine step, so repeat it on every new development
machine.

**Agents: you probably can't do this yourself.** Commands like `/add-dir` are typed by the user
in the harness, not run by the agent. If the sibling repos aren't in your accessible
directories, don't search around or guess. Tell the user which are missing and ask them to add
them.

- Claude Code: the user runs `/add-dir ../ai-veupathdb-client`, and likewise for the other three
  (saved in `.claude/settings.local.json`, which is per-machine; don't commit it).
- Other harnesses: the user uses their equivalent for extra working or readable directories.

Without this, the agent cannot check the skill's claims against Pathfinder source. When citing
Pathfinder docs in this repo, name the repo and path (e.g. `ai-veupathdb-client`
`docs/knowledge/wdk/rules/auth-and-transport.md`), not a local filesystem path.

## Development notes

- Tests: see "Development" in `README.md` and `veupathdb_database/TESTS.md`. Scripts run through
  `uv run`.
- GitHub CLI: if `GITHUB_TOKEN` is set in the environment and is not suitable for this org,
  `gh` calls may fail. Run them as `env -u GITHUB_TOKEN gh ...`.
- Design specs and plans live on the `docs` branch, not on `master`.
- Releases are built by publishing a GitHub release; each skill is zipped separately.
- Known limitation: the release tagging/zipping process increments the version for all skills,
  even if only one has been updated.
