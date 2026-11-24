# veupathdb-skills

Agent skills for [VEuPathDB](https://veupathdb.org) genomics sites (PlasmoDB, VectorBase,
ToxoDB, FungiDB, TriTrypDB and others).

Skills:

- [veupathdb_database](#veupathdb_database)
- [tabular-to-stf](#tabular-to-stf)

## veupathdb_database

Lets an agent query the VEuPathDB WDK and EDA REST APIs: find genes by biological
criteria, combine searches into strategies, count, preview and download results, fetch
gene records and expression tables, and run differential expression (DESeq2) and
antibody-array (limma) contrasts on EDA-backed datasets.

### Install in Claude Code (or another local agent)

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

### Install in claude.ai (web chat)

Any claude.ai plan can use the skill, including Free. It runs scripts in Claude's
sandbox, and those scripts must reach the VEuPathDB sites, so the sandbox needs network
access to the hosts below. Anthropic's menus change from time to time; if a label
differs, see Anthropic's help article
[Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude).

**Hosts the skill needs**

```
veupathdb.org
orthomcl.org
amoebadb.org
cryptodb.org
fungidb.org
giardiadb.org
hostdb.org
microsporidiadb.org
piroplasmadb.org
plasmodb.org
toxodb.org
trichdb.org
tritrypdb.org
vectorbase.org
```

The scripts also install their Python packages with `uv`, so package-manager access
must stay allowed (`pypi.org` and similar). Each of the options below includes it.

**1. Upload the skill** (everyone, including VEuPathDB staff)

1. Download `veupathdb_database-<version>.zip` from the
   [latest release](../../releases/latest) (the named asset, not "Source code"). Don't unzip it.
2. In claude.ai, open the **Skills** tab and use **Add** to upload the zip. Where to find
   it depends on your account (these names change from time to time):
   - Personal account: **Plugins** in the left navigation → **Skills** tab → **Add** →
     **Upload plugin**.
   - Team account: **Customize** in the left navigation → **Skills** tab → **Add** →
     **Upload skill**.
3. Check the skill is switched on.

**2. Allow network access.** Pick the case that matches your account.

*Personal account (Free, Pro, Max)*

1. Click your user icon (bottom left) → **Settings** → **Capabilities**.
2. Turn on **Use the internet while making files**.
3. Next to **Allowed websites**, click **Manage**.
4. Under "Which sites to allow", choose **Standard download sites only**.
5. Under **Add a website**, type each host and click **Add**. Everyone should add
   `veupathdb.org` and `orthomcl.org` first, then the sites for the communities
   you work with (for example `plasmodb.org`). Add any others you expect to use.

*VEuPathDB Team account*

The organization already allows package managers plus the VEuPathDB hosts, so no setup
is needed beyond uploading the skill.

*Team or Enterprise account from another organization*

Only an organization owner can change network settings. Send your owner this request:

> Please set Organization settings → Capabilities → **Allow network egress** to
> "package managers and specific domains", and add these domains: *(paste the host list
> above, or just the ones we need)*. If members can't upload skills, please also turn on
> "User-created skills" under Organization settings → Plugins & skills (Policy tab).

Once your owner has done that, upload the skill as in step 1.

### Use

Ask your agent a VEuPathDB question. A free VEuPathDB account is required, and the
agent walks you through saving your API key on first use. On claude.ai, the key is
pasted into (or attached to) the chat, so treat it like a password and don't share the
conversation. The sandbox may not remember it in a new chat, so you may be asked again.

If the agent reports that a VEuPathDB site is blocked or can't be reached, the host is
missing from your allow-list: add it and ask again.

## tabular-to-stf

Turns a folder of related CSV/TSV tables (one file per entity, e.g. village, household,
participant, sample) into a Study Transfer Format (STF) directory that study-wrangler
loads and VEuPathDB EDA accepts. The agent profiles your data, asks you about it, and
writes a curation spec; scripts render and check the STF. Optionally it validates the
result in the pinned study-wrangler container.

### Install in Claude Code (or another local agent)

1. Download `tabular-to-stf-<version>.zip` from the
   [latest release](../../releases/latest) (the named asset, not "Source code").
2. Unzip it into your agent's skills directory, e.g. `~/.claude/skills/` for Claude Code.
   The skill is the `tabular-to-stf/` folder containing `SKILL.md`.
3. Install [uv](https://docs.astral.sh/uv/); the scripts run through `uv run`.
4. Recommended supply-chain protection: make uv ignore package versions published in
   the last week, so a freshly compromised release is never installed. Put this in
   `~/.config/uv/uv.toml`:

   ```toml
   exclude-newer = "1 week"
   ```

5. Optional: install Docker or Podman for container validation.

### Install in claude.ai (web chat)

Any claude.ai plan can use the skill, including Free. See
[Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
if a menu label differs from the steps below.

1. Download `tabular-to-stf-<version>.zip` from the
   [latest release](../../releases/latest) (the named asset, not "Source code"). Don't unzip it.
2. In claude.ai, open the **Skills** tab and use **Add** to upload the zip. Where to find
   it depends on your account (these names change from time to time):
   - Personal account: **Plugins** in the left navigation → **Skills** tab → **Add** →
     **Upload plugin**.
   - Team account: **Customize** in the left navigation → **Skills** tab → **Add** →
     **Upload skill**.
3. Check the skill is switched on.
4. Check network access allows package managers:
   - Personal account: Settings → Capabilities → **Use the internet while making
     files** on, with **Allowed websites** set to "Standard download sites only".
   - Team or Enterprise account: the default, "package managers only", is enough. If
     your organization has network access switched off, ask your owner to change
     Organization settings → Capabilities → **Allow network egress** to "package
     managers only" or wider.

### Use

Ask your agent to convert your tables to STF and give it the input folder, an output
folder, and optionally a study description or data dictionary. On claude.ai, attach your
tables to the chat, and download the STF files it produces.

## Development

### veupathdb_database

Tests and gold standards are in `veupathdb_database/TESTS.md`; run them with
`uv run --with pytest --with httpx python -m pytest tests -q` from `veupathdb_database/`.

### tabular-to-stf

From `tabular-to-stf/`, run
`uv run --with pytest --with "ruamel.yaml>=0.18,<0.20" python -m pytest tests -q`. The golden
tests render the fixtures in `tests/fixtures/tabular/` and compare them with each
`expected/` directory. Two groups are skipped by default:
the container tests (set `STF_CONTAINER_TESTS=1`; needs Docker or Podman and the pinned
study-wrangler image) and the 1M-row scale test (set `STF_SCALE_TEST=1`).

### Releases

Design specs and plans are archived on the `docs` branch. Publishing a GitHub release
builds and attaches a zip for each skill, `veupathdb_database` and `tabular-to-stf`.
