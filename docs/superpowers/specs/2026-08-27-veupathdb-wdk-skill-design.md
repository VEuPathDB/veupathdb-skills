# VEuPathDB WDK Strategy Skill — Design

Date: 2026-08-27
Status: APPROVED (design), implementation not started
Repos: `veupathdb-skills` (this repo, the deliverable; formerly `pathfinder-skills`); `../pathfinder-as-a-skill/pathfinder` (source of distilled knowledge, read-only; fork `ahmedOmuharram/pathfinder`, branch `pydantic-ai`)

## Goal

Distil the VEuPathDB WDK service calls and response parsing from the pathfinder
agentic-loop UI into a single Claude-Code-style **skill** so that any agentic
coding client (Claude Code, Google Antigravity, …) can build search strategies
on VEuPathDB sites (PlasmoDB, VectorBase, ToxoDB, …) without the pathfinder app.

The skill replaces pathfinder's conversation-loop UI; the agent host provides
the loop, the skill provides the business logic: transport quirks, endpoint
knowledge, parameter/vocabulary rules, response shaping, and runnable scripts.

## Scope (v1): the core strategy loop

1. Authenticate (bearer token) and verify identity.
2. Discover searches — **reasoning over the full compact catalog, delegated to a
   sub-agent**: the orchestrator (main thread) dispatches a sub-agent that runs
   `catalog SITE`, reads all search descriptions in isolated context, and
   returns a shortlist (3–8 candidates with rationale, tagged seed / filter /
   transform). No embeddings. Measured dump sizes: PlasmoDB ~32k tokens (515
   searches), VectorBase ~74k (923), ToxoDB ~23k (423). Clients without
   sub-agents read the dump directly; `find-searches` (lexical) remains as a
   cheap convenience when the target is already roughly known.
3. Inspect a search: shaped parameter sheet, vocabulary browsing, dependent params.
4. Count / preview results anonymously (no user session) before committing.
5. Create steps and strategies (leaf / combine / transform), get counts and the web URL.
6. Fetch results: sample records, download URLs.

Explicitly **out of scope for v1** (documented as such in SKILL.md): semantic /
embedding search, the site-search microservice, control tests, enrichment,
step analyses, step filters, phyletic `profile_pattern` expansion, EDA,
basket/dataset uploads beyond what strategy creation needs.

## Decisions (made with the user, 2026-08-27)

| Decision | Choice |
|---|---|
| Scope | Core strategy loop (above) |
| Code reuse | Standalone scripts; **no** dependency on the pathfinder package |
| Response parsing | Scripts shape output (param sheets, vocab shortlists, count extraction) — not raw JSON dumps |
| Granularity | One skill + on-demand reference docs (progressive discovery) |
| Tests | TESTS.md as human-readable gold-standard registry + live pytest suite |
| Test sites | PlasmoDB, VectorBase, ToxoDB |
| Language/tooling | Python via `uv` (PEP 723 inline metadata); supply-chain: `exclude-newer` assumed from `~/.config/uv/uv.toml` and documented |
| Script architecture | Single CLI (`wdk.py`) with subcommands + private helper modules beside it |

## Repository layout

```
veupathdb-skills/
├── .gitignore                     (.env)
├── .env                           (VEUPATHDB_BEARER_TOKEN=…, never committed)
├── docs/superpowers/specs/        (this file)
└── veupathdb-wdk-strategies/
    ├── SKILL.md                   ≤200 lines; frontmatter, workflow, script index, pointers
    ├── references/
    │   ├── auth.md                cookie auth, guest detection, user-id resolution
    │   ├── parameters.md          the 11 parameter types, vocabulary + dependent-param rules
    │   ├── strategies.md          stepTree semantics, step kinds, combine operators, URLs
    │   └── gotchas.md             SILENT-failure rules distilled from pathfinder docs/knowledge/wdk/rules/
    ├── scripts/
    │   ├── wdk.py                 CLI entry point (PEP 723 header, deps: httpx only)
    │   ├── _client.py             transport layer
    │   ├── _shaping.py            response shaping
    │   └── _sites.py              site registry
    ├── TESTS.md                   test registry with gold-standard expectations
    └── tests/
        ├── conftest.py            token loading, site fixtures, strategy cleanup
        └── test_*.py              live pytest suite (auth, discovery, inspect, counts, strategies, results)
```

## CLI surface (`uv run scripts/wdk.py <subcommand>`)

| Subcommand | WDK endpoint(s) | Notes |
|---|---|---|
| `sites` | — | list site_id → base URL / project id |
| `whoami SITE` | `GET /users/current` | verifies token; **refuses guest identities**; prints numeric user id |
| `record-types SITE` | `GET /record-types?format=expanded` | compact listing |
| `searches SITE RECORD_TYPE` | `GET /record-types/{rt}/searches` | name, displayName, one-line description |
| `catalog SITE [--record-type RT]` | `GET /record-types?format=expanded` + per-type searches | **primary discovery primitive**: compact one-line-per-search dump (record type, name, displayName, description trimmed to ~250 chars). ~25–75k tokens per site — sized for a sub-agent's isolated context. Catalog cached on disk (`~/.cache/veupathdb-wdk/{site}.json`, 7-day TTL) since a cold fetch is slow |
| `find-searches SITE QUERY` | catalog (cached, as above) | convenience lexical word/substring scoring over names+descriptions; relevance-sorted, truncated. Secondary to `catalog` + reasoning |
| `inspect SITE SEARCH` | `GET/POST /record-types/{rt}/searches/{name}?expandParams=true` | shaped parameter sheet (see Shaping) |
| `param-options SITE SEARCH PARAM [--query Q] [--context k=v…]` | search detail / `refreshed-dependent-params` | vocabulary browsing; dependent vocabularies require `--context` for parents |
| `count SITE SEARCH --params JSON` | `POST /record-types/{rt}/searches/{name}/reports/standard` | anonymous; no step/strategy/user session |
| `preview SITE SEARCH --params JSON [--limit N]` | same | sample records, compact attributes |
| `create-strategy SITE --spec JSON [--name …]` | `POST /users/{uid}/steps`, `POST /users/{uid}/strategies` | declarative step-tree spec; creates steps in dependency order, then the strategy; returns strategy id, web URL, per-step counts/validation |
| `strategy SITE ID` | `GET /users/{uid}/strategies/{id}` | shaped tree + counts |
| `list-strategies SITE` | `GET /users/{uid}/strategies` | |
| `delete-strategy SITE ID` | `DELETE /users/{uid}/strategies/{id}` | destructive; requires `--yes` |
| `results SITE --step ID [--attributes …]` | `POST /users/{uid}/steps/{id}/reports/standard` | records + count |
| `download-url SITE --step ID [--report …]` | `POST /temporary-results` | note: body field is `reportName` (not `reporterName`), `reportConfig` required even if `{}` |

The `--spec` format for `create-strategy` is a small declarative JSON tree:
nodes are `{"leaf": {"search": …, "params": {…}}}`,
`{"combine": {"operator": "UNION|INTERSECT|MINUS", "left": …, "right": …}}`, or
`{"transform": {"search": …, "params": {…}, "input": …}}`.

## Transport rules (`_client.py`, `references/auth.md`)

Distilled from pathfinder `integrations/veupathdb/_http.py` and
`docs/knowledge/wdk/rules/auth-and-transport.md`:

- Auth is a **cookie, not a header**: `Cookie: Authorization=<token>`, exactly
  one pair (Tomcat honors the first of duplicates).
- Token source: `VEUPATHDB_BEARER_TOKEN` env var, falling back to `.env` at the
  repo root (parsed manually — no dotenv dependency).
- An uncredentialed request is **not rejected** — WDK mints a fresh guest each
  time. `whoami` (via `GET /users/current`, `isGuest`) is the correctness check,
  and user-scoped commands resolve the concrete numeric user id once and use it
  in all `/users/{uid}/…` paths (never the `current` alias after resolution).
- Registered (non-guest) login is required for programmatic `/users/…` calls
  (VEuPathDB policy since 2026-08-19).
- Retries: up to 3 attempts, exponential backoff, on timeouts, connect errors,
  5xx, and the delayed-result body — a 2xx of
  `{"status": "accepted", "message": "WDK-DELAYED-RESULT"}` means retry.
- **Non-idempotent POSTs (step/strategy creation) get exactly one attempt** so
  a proxy 502 after a committed create cannot duplicate the object.
- 422 means well-formed but semantically wrong (bad param value); surface the
  WDK message verbatim.
- Timeouts: 30 s per site, 120 s for the portal (veupathdb.org).
- Site registry (14 sites) copied from pathfinder `integrations/veupathdb/sites.yaml`
  into `_sites.py`; strategy web URL is
  `{base minus /service}/app/workspace/strategies/{id}`.

## Shaping rules (`_shaping.py`, `references/parameters.md`, `references/gotchas.md`)

Distilled from pathfinder `services/catalog/{param_sheet,param_formatting,vocab_rendering}.py`
and `docs/knowledge/wdk/rules/parameters-and-vocabularies.md`:

- **Parameter sheet** (`inspect`): per param — name, type, required, help,
  default, allowed values. Hidden (`isVisible: false`) params are omitted from
  the sheet **but their defaults are still submitted** on create (WDK validates
  them regardless — visibility is presentation only).
- Vocabularies ≤ 200 entries: shown whole. Larger: shortlisted with an explicit
  disclosure note naming the total and pointing at
  `param-options … --query`. Tree vocabularies rendered with a line cap;
  truncation lists remaining top-level categories with descendant counts.
- Dependent vocabularies are only meaningful under bound parents: `param-options`
  refuses to answer without `--context` for unbound parents, and says so.
- On submit (`count`, `preview`, `create-strategy`):
  - every value is stringified (WDK params are all strings on the wire);
    multi-pick values are JSON arrays serialized to strings;
  - tree-vocabulary **parents are expanded to leaf descendants** when the vocab
    counts only leaves — otherwise WDK silently returns 0 rows;
  - every `input-step` param is sent as `""`; real inputs are wired via the
    `stepTree`;
  - unspecified params get their defaults filled in (including hidden ones);
  - the synthetic `@@fake@@` vocabulary root is never sent.
- Boolean (combine) steps: operand param names embed the record-class name and
  are **discovered at runtime** (`bq_left_op*`, `bq_right_op*`, `bq_operator*`),
  never hardcoded.
- Step kind is determined by the number of `input-step` params its search
  declares: 0 = leaf, 1 = transform, 2 = combine.
- Counts: prefer `displayViewTotalCount → viewTotalCount → displayTotalCount →
  totalCount`; if all absent, report "unmeasured", never 0.
- Gene searches live under the `transcript` record type (record type `gene`
  auto-resolves there).
- Unknown search/param names come back as did-you-mean suggestions with the
  valid list (difflib), as normal output — not stack traces.

## SKILL.md (progressive discovery)

- Frontmatter: name + a trigger-rich description (VEuPathDB, PlasmoDB,
  VectorBase, WDK, search strategy, gene search…).
- Body ≤ 200 lines: the 6-step workflow, the subcommand index (one line each),
  the 3 highest-value gotchas inline, and pointers into `references/` for depth.
- Explicit sub-agent guidance for discovery: dispatch a sub-agent to run
  `catalog SITE` and shortlist candidate searches in isolated context, keeping
  the orchestrator thread clean; fall back to reading the dump directly on
  hosts without sub-agents.
- `wdk.py --help` / `wdk.py <sub> --help` are the second discovery layer.
- References are the third layer, read only when the agent needs them.

## Testing (TDD)

- **TESTS.md** is the registry: one section per test case with the exact
  command, the gold-standard expectation (retrieved live during implementation;
  reviewable/tweakable later), and the tolerance class:
  `exact` | `range` (counts drift with data releases) | `fields-present`.
- **pytest** (`uv run --with pytest,httpx pytest tests/ …` or a PEP 723
  runner script) implements every TESTS.md case, live against the real
  services. Site-generic cases are parameterised over
  `plasmodb, vectorbase, toxodb`; search-specific cases pin one site.
- TDD order: auth → discovery → inspection → counts/preview → strategy
  creation → results. Each phase: write the failing test with a live-retrieved
  gold answer, then implement until green.
- Write-path hygiene: strategies created by tests are named with a
  `__skill_test__:` prefix and deleted in teardown (best-effort, 404-tolerant).
- Tests require `VEUPATHDB_BEARER_TOKEN`; skip (with a clear reason) when it
  is absent so the suite is safe to run anywhere.

## Error handling

- HTTP/WDK errors → single-line structured messages (status, WDK message,
  endpoint) on stderr, non-zero exit; never a traceback for expected failures.
- Guest token → explicit "register at the site and supply a registered-user
  token" message.
- Vague `find-searches` queries and empty results give actionable guidance
  (try record-type listing, broaden the query).

## Sources of truth consulted in pathfinder (read-only)

- `integrations/veupathdb/` — transport, endpoints, models
- `services/catalog/` — discovery scoring, param sheets, vocab rendering
- `services/strategies/` — step push order, sync, counts
- `docs/knowledge/wdk/rules/` — the machine-checked WDK rules bundle
- `docs/knowledge/wdk/rest/endpoint-surface.md` — endpoint inventory
