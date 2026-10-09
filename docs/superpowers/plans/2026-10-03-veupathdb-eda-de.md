# VEuPathDB EDA Differential Expression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an agent do what a website user does with an EDA differential-expression or antibody-array notebook: explore the samples, discover and choose a contrast, run DESeq2/limma on the shared EDA compute cache, and turn the result into a normal WDK step that returns the same genes the website would.

**Architecture:** A new PEP 723 CLI, `veupathdb_database/scripts/eda.py`, sits next to `wdk.py`. It is backed by private modules: `_eda.py` (endpoint wrappers on an EDA-flavoured `_client.Client`), `_samples.py` (metadata pruning, sample-table join, filters), `_contrasts.py` (enumeration, canonical compute bodies, job ids), `_de.py` (threshold logic identical to the WSF plugin, result shaping, `eda_analysis_spec` builder), `_stats.py` (stdlib-only statistics) and `_pca.py` (PCA parsing and reporting). The handoff to WDK is a JSON file: `eda.py de-spec --save` writes the WDK params to a content-addressed file in the skill cache (never the user's working directory) and prints a ready strategy leaf, and `wdk.py` accepts `@file` wherever it takes a params object. Contrasts and filters are passed inline as JSON, so a normal session writes no files of its own.

**Tech Stack:** Python ≥3.11, `uv` (PEP 723 inline metadata), `httpx` (only runtime dependency), `pytest` (tests), base R `Rscript` (test-time gold standard for `_stats.py` only).

**Spec:** `docs/superpowers/specs/2026-10-03-veupathdb-eda-de-design.md`. Read it first. This plan settles the spec's "Open items" (see Verified live facts) and makes these decisions the spec left to the plan:
- WDK handoff: `@file` for whole `--params`/`--spec` arguments, plus `"params": "@file"` inside a strategy leaf (Task 12).
- PCA scores come from `POST /computes/dimensionalityreduction/tabular` and `/meta` (Task 18). The config key is `nPCs`.
- Study and dataset descriptions come from `/eda/permissions` (`displayName`, `description`).
- `de-datasets` reads `properties.edaNotebookType` from the WDK search listing (now kept in the catalog cache) and each search's `eda_dataset_id` default.
- The sample table joins the expression entity's **ancestors** only, because comparators must sit there. Other non-gene entities are listed with their counts and marked as not usable as comparators.
- A sixth private module, `_pca.py`, keeps `_stats.py` purely numerical.
- JSON shape for `de --json`: `context` / `provenance` / `identity` / `rows` (Task 9).

## Global Constraints

- Repo: `/home/maccallr/work/veupathdb-skills`; all paths are relative to it. Skill dir: `veupathdb_database/`.
- Commit only. Never push (the user pushes). End every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Runtime dependency: `httpx` only. `_stats.py` uses only `math`, `statistics`, `collections` (no numpy/scipy/pandas). R is a development dependency only: nothing the skill runs at use time needs R.
- `eda.py` has the same PEP 723 header as `wdk.py` (`requires-python = ">=3.11"`, `dependencies = ["httpx"]`).
- Test command (from `veupathdb_database/`): `uv run --with pytest --with httpx python -m pytest tests -q`. Live tests skip cleanly without a token. R tests skip cleanly without `Rscript` on PATH, with a clear reason.
- Never print, log or commit the token.
- `eda.py` output: compact text by default, `--json` for machine-readable output on stdout; progress on stderr; errors as `error: …` on stderr with exit 1 (same `fail()` convention as `wdk.py`).
- The compute body is exactly `{"studyId": STUDY_…, "filters": [...], "config": {...}, "derivedVariables": []}`. In an analysis spec, `studyId` holds the **DS_** id and must equal `eda_dataset_id`.
- Thresholds use the **raw** p-value. Defaults: `effectSizeThreshold 1`, `significanceThreshold 0.05`, `upAndDown`. `groupA` is the reference: positive effectSize means higher in groupB.
- Canonical contrast: labels sorted within each group; filters sorted by (entityId, variableId) with set values sorted; `pValueFloor "1e-200"`; method DESeq for `differentialExpressionNotebook`, limma for `antibodyArrayNotebook`.
- `SKILL.md` ≤ 200 lines. Depth goes in `references/`.
- Strategies created by tests are named `__skill_test__: …` and deleted in teardown.
- Publicly promise only EDA support. Expression summaries are out of scope (no summarising code).
- Every task that adds a live test appends its case to `veupathdb_database/TESTS.md` with the observed gold value and capture date.

## Verified live facts (probed 2026-10-03 on plasmodb.org: trust these)

- **Job id formula (reproduced exactly):** `md5(json.dumps([plugin, json.dumps(body, sort_keys=True, separators=(",", ":"))], separators=(",", ":")))`. For the heat-shock body below the result is `db04204e5386396e1ca2cb78469ab6fb`, which matches the live `jobID`. Python's default `ensure_ascii=True` would escape non-ASCII labels; Jackson does not, so use `ensure_ascii=False` and UTF-8. Numeric filter values may serialise differently in Java (`37` vs `37.0`), so the server's `jobID` is always authoritative and the local hash is only an offline check.

  ```json
  {"studyId":"STUDY_e973eadd57","filters":[],"derivedVariables":[],"config":{"identifierVariable":{"entityId":"ENT_fd574cd6","variableId":"VEUPATHDB_GENE_ID"},"valueVariable":{"entityId":"ENT_fd574cd6","variableId":"SEQUENCE_READ_COUNT_SENSE"},"comparator":{"variable":{"entityId":"ENT_8151325d","variableId":"VAR_081ab087"},"groupA":[{"label":"normal"}],"groupB":[{"label":"febrile"}]},"differentialExpressionMethod":"DESeq","pValueFloor":"1e-200"}}
  ```
- **The WDK step drops `statistics[0]`.** `GeneEdaVizWithComputePlugin` writes the volcano statistics to a temp file with **no header**, and `AbstractEdaGenesPlugin.execute` then skips the first line "as a header". Live, on `GenesByRNASeqpfal3D7_Pfal3D7_Febrile_temps_RNASeq_ebi_rnaSeq_RSRCDESeq` with the body above:
  - thresholds (1, 0.05): local raw-p count is 1543 and WDK `displayTotalCount` is 1543 (`totalCount` 1571 transcripts), because row 0 (`PF3D7_0100100`, p=0.35) fails the threshold
  - thresholds (0, 1.0): local raw-p count is 5510 and WDK `displayTotalCount` is **5509**
  - so the WDK step returns the retained genes of `statistics[1:]`. `de` reports both numbers. This is an upstream bug worth reporting to the ApiCommonWebService maintainers; the skill reproduces it so its counts match the website.
- The volcano response has 5511 statistics for 5720 genes (209 all-zero genes are not tested). Values are **strings**; one `adjustedPValue` is JSON `null`; one row is not numeric in effectSize/pValue (5511 rows, 5510 numeric). The plugin parses with Java `Double.valueOf` and skips rows it cannot parse.
- `POST /computes/dimensionalityreduction/{tabular|meta}` with the same body as the compute returns `text/plain`. It returns **HTTP 406 when `Accept: application/json`**, so send `Accept: */*`. Tabular header for heat-shock: `ENT_8151325d.sample_stable_id\tPC1\tPC2`. Meta is JSON whose computed variables have `displayName` `"PC 1 (54.35% variance)"` and `"PC 2 (12.79% variance)"`. PCA job for the notebook config `{identifierVariable, valueVariable, dataFormat: "rawCounts"}` (no `nPCs`): `2679abb0e5c81b345a21b8f211db6a9b`.
- Heat-shock PCA truth (from the live scores): temperature (37C vs 41C) has eta² 0.7751 on PC1 and 0.0022 on PC2; strain has eta² 0.1485 on PC1 and 0.4964 on PC2. Max |z| is 1.43 on PC1 and 2.00 on PC2, so there are no outliers.
- `GET /eda/permissions` → `{"perDataset": {DS_…: {"studyId", "displayName", "shortDisplayName"?, "description"?, …}}}`, about 1 MB on PlasmoDB. `DS_e973eadd57` → `STUDY_e973eadd57` "Heat shock response in sensitive mutants (LRR5, DHC)".
- `GET /eda/studies/{STUDY}` → `{"study": {"id", "rootEntity": {id, displayName, idColumnName, variables[], children[]}}}`. Heat-shock: root `ENT_8151325d` "Sample" with 6 variables: `VAR_081ab087` temperature_condition (string, `['febrile','normal']`), `VAR_7033e90f` temperature (integer, 37/41, so it is an alias of temperature_condition), `VAR_26d10fbf` strain (`['NF54','PB31','PB4']`), `VAR_84f17484` genotype (`['delta-DHC mutant','delta-LRR5 mutant','wildtype']`, an alias of strain), `VAR_64c65374` label (6 values, `isFeatured: true`), `VAR_ebaebced` SRA ID(s) (one value per sample). The child is `ENT_fd574cd6` "pfal3D7 htseq counts" with `VEUPATHDB_GENE_ID` (`distinctValuesCount` 5720, with the whole gene list as `vocabulary`), `SEQUENCE_READ_COUNT_SENSE`, `SEQUENCE_READ_COUNT_ANTISENSE`. Samples are named `{PB31|PB4|WT}_{37C|41C}_Rep{1|2}`: 3 strains × 2 temperatures × 2 replicates.
- Antibody array: `GenesByAntibodyArrayEdaSubset_PlasmoDB_Crompton_Mali_AntibodyArray_RSRC` → `eda_dataset_id` default `DS_24d441b301` → `STUDY_24d441b301`. Root `ENT_58fabfa7` "Sample" has 421 records, 17 variables (4 of them `category`), and repeated subjects ("Subject 100"). Child `GENE_ANTIBODY_ARRAY_DATA` has `VEUPATHDB_GENE_ID` and `NORMALIZED_INTENSITY`.
- `POST …/entities/{e}/tabular` with `Accept: application/json` returns a bare `string[][]`: header first, own key column first, then ancestor keys (nearest first), then the requested variable ids. Empty cell = no value. `POST …/count` → `{"count": N}`.
- WDK `GET /record-types/transcript/searches` items carry `properties.edaNotebookType` (e.g. `["differentialExpressionNotebook"]`, `["antibodyArrayNotebook"]`, `["wgcnaCorrelationNotebook"]`) and `queryName` (`GenesByEdaVizWithCompute` for DE and antibody arrays). PlasmoDB has 68 searches with `eda_analysis_spec`.
- Numeric comparator groups are half-open bins: veupathUtils `whichValuesInBin` keeps `values >= binStart & values < binEnd`.
- `encode_params` passes string params through `str(value)`, so a dict becomes a Python repr. Task 12 fixes this.

## Review Focus

1. **A study with more than one expression entity** (e.g. dual RNA-Seq host + parasite): commands must stop and list them with `--entity`, never silently pick the first. Test: Task 3 `test_pick_expression_entity_refuses_ambiguity`.
2. **Stale caches:** an older catalog cache without `edaNotebookType` must be refetched, not used (which would silently hide every DE search); a dataset missing from a cached `/permissions` must trigger one fresh fetch before "not visible". Tests: Task 12 `test_old_schema_catalog_cache_is_refetched`, Task 2 `test_resolve_dataset_refetches_once_before_failing`.
3. **Non-numeric volcano values** (`null` padj, `"NA"`, `"Inf"`, Python-only spellings such as `"nan"`, `"inf"`): thresholding must match Java `Double.valueOf` exactly and never crash; JSON output must never contain `NaN`/`Infinity`. Test: Task 9 `test_java_double_matches_java_parsing` and `test_de_table_is_json_safe`.
4. **`eda_analysis_spec` given as a JSON object** in `--params` instead of a string: it must be sent as compact JSON text, not a Python repr. Test: Task 12 `test_encode_params_serialises_object_values_as_json`.
5. **Missing comparator values** (empty tabular cells): those samples belong to no group, are not a level `""`, and are not counted in n. Test: Task 7 `test_missing_values_are_not_a_level`.
6. **Mirror reuse** (Task 10): reused statistics must be the mirror's with effectSize negated and nothing else changed, provenance must name both jobs, and nothing may be started. It rests on the live symmetry check EDA-9 (Task 14). Tests: Task 9 `test_negate_effects_flips_sign_only`, Task 10 `test_de_reuses_cached_mirror_with_negated_effects`.

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `veupathdb_database/scripts/_sites.py` | modify | `eda_url(site)` |
| `veupathdb_database/scripts/_client.py` | modify | `Client(base_url, timeout)`, per-request `headers`/`params`, `eda_client()`, `cached_json()`, catalog schema 2 with `edaNotebookType`, supported-notebook filter |
| `veupathdb_database/scripts/_shaping.py` | modify | EDA tag in catalog/find output; object → JSON text for string params |
| `veupathdb_database/scripts/_strategy.py` | modify | leaf `"params": "@file"` |
| `veupathdb_database/scripts/wdk.py` | modify | `--params @file`, `--spec @file`, EDA notes in `inspect`/unknown-search errors |
| `veupathdb_database/scripts/_eda.py` | create | `EdaError`, permissions/study/count/tabular/distribution wrappers, compute status/poll/files, volcano, EDA search listing |
| `veupathdb_database/scripts/_samples.py` | create | entity tree, expression entity, pruning, sample-table join, summaries, `study` rendering, filter loading/validation |
| `veupathdb_database/scripts/_contrasts.py` | create | canonical groups/filters, configs, compute body, job id, value-var/method choice, enumeration, contrast files, rendering |
| `veupathdb_database/scripts/_de.py` | create | `java_double`, `is_retained`, WDK-step quirk, summaries, JSON split, spec builder/validator, rendering |
| `veupathdb_database/scripts/_stats.py` | create | Pearson r, eta², per-PC scoring with "not scored" reasons, outliers |
| `veupathdb_database/scripts/_pca.py` | create | parse PCA tabular/meta, report, rendering |
| `veupathdb_database/scripts/eda.py` | create | CLI: `study`, `contrasts`, `de`, `de-spec`, `de-datasets`, `pca` |
| `veupathdb_database/tests/eda_helpers.py` | create | fixture loader, synthetic study, `EdaMock` fake EDA service |
| `veupathdb_database/tests/conftest.py` | modify | `eda_cache`, `eda_mock`, `run_eda` fixtures |
| `veupathdb_database/tests/fixtures/eda/` | create | `capture.py` plus captured JSON/TSV fixtures |
| `veupathdb_database/tests/test_eda_*.py`, `test_samples.py`, `test_contrasts*.py`, `test_de*.py`, `test_stats*.py`, `test_pca.py`, `test_wdk_eda_handoff.py` | create | tests |
| `veupathdb_database/SKILL.md` | modify | router restructure |
| `veupathdb_database/references/eda.md` | create | EDA depth |
| `veupathdb_database/references/wdk-workflow.md` | create | WDK depth moved out of SKILL.md |
| `veupathdb_database/references/gotchas.md` | modify | EDA section |
| `veupathdb_database/TESTS.md` | modify | EDA gold cases |

Stages (each independently testable and committed): **Stage 1** = Tasks 1–15, **Stage 2** (`--filters`) = Task 16, **Stage 3** (PCA) = Tasks 17–18.

---

## Stage 1: core contrast loop

### Task 1: EDA transport

**Files:**
- Modify: `veupathdb_database/scripts/_sites.py` (append after `strategy_url`)
- Modify: `veupathdb_database/scripts/_client.py:12-13`, `:113-166`
- Test: `veupathdb_database/tests/test_eda_transport.py`

**Interfaces:**
- Consumes: `_sites.service_url(site_id) -> str`
- Produces:
  - `_sites.eda_url(site_id: str) -> str`, e.g. `"https://plasmodb.org/eda"`
  - `_client.Client(site_id, token=None, transport=None, backoff=2.0, base_url=None, timeout=None)`
  - `Client.request(method, path, body=None, params=None, retries=3, headers=None)`, `Client.post(path, body, idempotent=True, params=None, headers=None)`
  - `_client.eda_client(site_id, token=None, transport=None, backoff=2.0) -> Client` (base URL `eda_url(site)`, 120 s timeout)
  - `_client.EDA_CACHE_DIR: pathlib.Path` (module global, monkeypatched in tests)
  - `_client.cached_json(name: str, fetch: Callable[[], Any], refresh=False, ttl_s=CACHE_TTL_S) -> Any`: after each fresh fetch it writes atomically and prunes stale `*.json` in `EDA_CACHE_DIR` (not subdirectories)
  - `_client.write_atomic(path, text) -> None` (temp file in the same directory + `os.replace`; parallel sessions never read a partial file)
  - `_client.prune_stale(root, ttl_s=CACHE_TTL_S) -> None` (deletes `root/*.json` older than ttl_s; tolerates files vanishing under a parallel prune). Cleanup happens on cache writes only: no cron, nothing on reads.

- [ ] **Step 1: Write the failing tests**

Create `veupathdb_database/tests/test_eda_transport.py`:

```python
import httpx


def test_eda_url_per_site():
    from _sites import eda_url

    assert eda_url("plasmodb") == "https://plasmodb.org/eda"
    assert eda_url("veupathdb") == "https://veupathdb.org/eda"
    assert eda_url("microsporidiadb") == "https://microsporidiadb.org/eda"


def _eda(handler):
    from _client import eda_client

    return eda_client(
        "plasmodb", token="tok-x", transport=httpx.MockTransport(handler), backoff=0
    )


def test_eda_client_base_url_and_bearer():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["accept"] = request.headers.get("accept")
        return httpx.Response(200, json={"ok": True})

    assert _eda(handler).get("/permissions") == {"ok": True}
    assert seen["url"] == "https://plasmodb.org/eda/permissions"
    assert seen["auth"] == "Bearer tok-x"
    assert seen["accept"] == "application/json"


def test_post_query_params_and_header_override():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["accept"] = request.headers.get("accept")
        return httpx.Response(
            200, text="a\tb\n1\t2\n", headers={"content-type": "text/plain"}
        )

    out = _eda(handler).post(
        "/computes/x/tabular",
        {"k": 1},
        params={"autostart": "false"},
        headers={"Accept": "*/*"},
    )
    assert out == "a\tb\n1\t2\n"
    assert seen["url"].endswith("/computes/x/tabular?autostart=false")
    assert seen["accept"] == "*/*"


def test_cached_json_reuses_until_refresh(tmp_path, monkeypatch):
    import _client

    monkeypatch.setattr(_client, "EDA_CACHE_DIR", tmp_path)
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return {"n": calls["n"]}

    assert _client.cached_json("k", fetch) == {"n": 1}
    assert _client.cached_json("k", fetch) == {"n": 1}
    assert _client.cached_json("k", fetch, refresh=True) == {"n": 2}
    assert (tmp_path / "k.json").is_file()


def test_cached_json_write_prunes_stale_files_only(tmp_path, monkeypatch):
    import os
    import time

    import _client

    monkeypatch.setattr(_client, "EDA_CACHE_DIR", tmp_path)
    old = time.time() - _client.CACHE_TTL_S - 60
    stale, fresh = tmp_path / "plasmodb_study_STUDY_old.json", tmp_path / "plasmodb_permissions.json"
    sub = tmp_path / "params" / "abc.json"
    sub.parent.mkdir()
    for f in (stale, fresh, sub):
        f.write_text("{}")
    os.utime(stale, (old, old))
    os.utime(sub, (old, old))
    assert _client.cached_json("plasmodb_permissions", lambda: {"x": 1}) == {}  # fresh hit: read only
    assert stale.exists()  # reads never prune
    _client.cached_json("plasmodb_study_STUDY_new", lambda: {"x": 2})  # a fetch writes, then prunes
    assert not stale.exists() and fresh.exists()
    assert sub.exists()  # subdirectories (params/) are stash_json's to prune
    assert not [f for f in tmp_path.iterdir() if f.name.startswith(".tmp-")]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_transport.py -q`
Expected: FAIL with `ImportError: cannot import name 'eda_url'`.

- [ ] **Step 3: Implement**

Append to `veupathdb_database/scripts/_sites.py` after `strategy_url`:

```python
def eda_url(site_id: str) -> str:
    """EDA service root, e.g. https://plasmodb.org/eda (host of the WDK service + /eda)."""
    scheme, _, host = service_url(site_id).split("/", 3)[:3]
    return f"{scheme}//{host}/eda"
```

In `veupathdb_database/scripts/_client.py`, replace lines 12–13 with:

```python
CACHE_DIR = pathlib.Path.home() / ".cache" / "veupathdb-wdk"
CACHE_TTL_S = 7 * 24 * 3600
EDA_CACHE_DIR = CACHE_DIR / "eda"
EDA_TIMEOUT_S = 120
```

Replace `Client.__init__`, `Client.request` and `Client.post` (lines 114–160) with:

```python
    def __init__(self, site_id, token=None, transport=None, backoff=2.0, base_url=None, timeout=None):
        self.site_id = site_id
        self.token = token
        self.backoff = backoff
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Cookie"] = f"Authorization={token}"
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(
            base_url=base_url or service_url(site_id),
            headers=headers,
            timeout=timeout or SITES[site_id]["timeout"],
            follow_redirects=True,
            transport=transport,
        )
        self._user_id = None

    def request(self, method, path, body=None, params=None, retries=3, headers=None):
        last = None
        for attempt in range(retries):
            if attempt and self.backoff:
                time.sleep(self.backoff**attempt)
            try:
                r = self._http.request(method, path, json=body, params=params, headers=headers)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last = WDKError(f"{type(e).__name__}: {e}", endpoint=path)
                continue
            if r.status_code >= 500:
                last = WDKError(r.text[:500], status=r.status_code, endpoint=path)
                continue
            if r.status_code >= 400:
                raise WDKError(r.text[:1000], status=r.status_code, endpoint=path)
            if r.status_code == 204 or not r.content:
                return None
            ctype = r.headers.get("content-type", "")
            data = r.json() if "json" in ctype else r.text
            if _is_delayed(data):
                last = WDKError("WDK-DELAYED-RESULT (result not ready)", endpoint=path)
                continue
            return data
        raise last

    def get(self, path, params=None):
        return self.request("GET", path, params=params)

    def post(self, path, body, idempotent=True, params=None, headers=None):
        return self.request(
            "POST", path, body=body, params=params, retries=3 if idempotent else 1, headers=headers
        )
```

Add after the `Client` class (before `DEFAULT_EXCLUDED_PARAM_PREFIXES`):

```python
def eda_client(site_id, token=None, transport=None, backoff=2.0):
    """A Client rooted at the site's EDA service (https://{host}/eda). The same token
    works: the Bearer header is what EDA reads; WDK reads the cookie."""
    from _sites import eda_url

    return Client(
        site_id,
        token=token,
        transport=transport,
        backoff=backoff,
        base_url=eda_url(site_id),
        timeout=EDA_TIMEOUT_S,
    )


def write_atomic(path, text):
    """Write via a temp file in the same directory and os.replace: a parallel session
    sees the old file or the new one, never a partial one. Also refreshes the mtime."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        pathlib.Path(tmp).unlink(missing_ok=True)
        raise


def prune_stale(root, ttl_s=CACHE_TTL_S):
    """Delete root/*.json older than ttl_s. Called after cache writes (no cron job): a
    stale file would be refetched on its next read anyway, so deleting it loses nothing."""
    cutoff = time.time() - ttl_s
    for old in root.glob("*.json"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except FileNotFoundError:  # a parallel session pruned it first
            pass


def cached_json(name, fetch, refresh=False, ttl_s=CACHE_TTL_S):
    """Disk-cache fetch() as EDA_CACHE_DIR/{name}.json for ttl_s seconds."""
    EDA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = EDA_CACHE_DIR / f"{name}.json"
    if not refresh and path.is_file() and time.time() - path.stat().st_mtime < ttl_s:
        return json.loads(path.read_text())
    data = fetch()
    write_atomic(path, json.dumps(data))
    prune_stale(EDA_CACHE_DIR)
    return data
```

Add `import tempfile` to `_client.py`'s imports (`os`, `pathlib`, `time` and `json` are already there).

- [ ] **Step 4: Run the new and existing tests**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_transport.py tests/test_client.py -q`
Expected: PASS. Live tests in `test_client.py` pass with a token and skip without one.

- [ ] **Step 5: Commit**

```bash
git add veupathdb_database/scripts/_sites.py veupathdb_database/scripts/_client.py veupathdb_database/tests/test_eda_transport.py
git commit -m "feat(eda): EDA transport on the shared client, JSON disk cache

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: EDA endpoint wrappers and captured fixtures

**Files:**
- Create: `veupathdb_database/scripts/_eda.py`
- Create: `veupathdb_database/tests/fixtures/eda/capture.py` and the files it writes
- Create: `veupathdb_database/tests/eda_helpers.py`
- Modify: `veupathdb_database/tests/conftest.py`
- Test: `veupathdb_database/tests/test_eda_api.py`

**Interfaces:**
- Consumes: `_client.eda_client`, `_client.cached_json`, `_shaping.strip_html`
- Produces (all take `c`, an EDA `Client`):
  - `class EdaError(Exception)`, the base for all eda.py errors (`SampleError`, `ContrastError`, `SpecError` subclass it)
  - `RUNNING = ("queued", "in-progress")`
  - `resolve_dataset(c, dataset_id, refresh=False) -> {"datasetId", "studyId", "displayName", "shortDisplayName", "description"}`
  - `study_metadata(c, study_id, refresh=False) -> dict` (the `study` object: `{"id", "rootEntity", …}`)
  - `entity_count(c, study_id, entity_id, filters) -> int`
  - `tabular(c, study_id, entity_id, variable_ids, filters) -> list[list[str]]` (header row first)
  - `distribution(c, study_id, entity_id, variable_id, filters, bin_spec=None) -> dict`
  - `compute_status(c, plugin, body, start: bool) -> {"jobID", "status", …}`
  - `job_status(c, job_id) -> dict`, `delete_job(c, job_id) -> None`
  - `wait_for_job(c, plugin, body, timeout_s=900, sleep=time.sleep, log=None) -> dict` (returns the first non-running status)
  - `volcano(c, body) -> {"statistics": [...], …}`
  - `compute_file(c, plugin, body, name) -> str` (`name` in `tabular`, `meta`)
- Test helpers: `eda_helpers.eda_fixture(name)`, `eda_helpers.EdaMock` (fake EDA service with `.handler`, `.requests`, `.routes`, `.compute_bodies(plugin)`), conftest fixtures `eda_cache`, `eda_mock`, `run_eda` (the last two are completed in Task 4, once `eda.py` exists).

- [ ] **Step 1: Write the failing tests**

Create `veupathdb_database/tests/test_eda_api.py`:

```python
import json

import httpx
import pytest


def _client(handler):
    from _client import eda_client

    return eda_client(
        "plasmodb", token="tok-x", transport=httpx.MockTransport(handler), backoff=0
    )


PERMS = {
    "perDataset": {
        "DS_aaa": {
            "studyId": "STUDY_aaa",
            "displayName": "A study",
            "shortDisplayName": "A",
            "description": "<b>Heat</b> shock   study",
        }
    }
}


def test_resolve_dataset_maps_ds_to_study(eda_cache):
    from _eda import resolve_dataset

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        assert request.url.path == "/eda/permissions"
        return httpx.Response(200, json=PERMS)

    c = _client(handler)
    ds = resolve_dataset(c, "DS_aaa")
    assert ds == {
        "datasetId": "DS_aaa",
        "studyId": "STUDY_aaa",
        "displayName": "A study",
        "shortDisplayName": "A",
        "description": "Heat shock study",
    }
    resolve_dataset(c, "DS_aaa")
    assert calls["n"] == 1  # second call served from the disk cache


def test_resolve_dataset_refetches_once_before_failing(eda_cache):
    from _eda import EdaError, resolve_dataset

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=PERMS)

    c = _client(handler)
    resolve_dataset(c, "DS_aaa")  # warms the cache
    with pytest.raises(EdaError) as e:
        resolve_dataset(c, "DS_aab")
    assert calls["n"] == 2  # one fresh fetch before giving up
    msg = str(e.value)
    assert "not visible" in msg and "whoami" in msg and "DS_aaa" in msg


def test_tabular_and_count_always_send_filters():
    from _eda import entity_count, tabular

    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        if request.url.path.endswith("/count"):
            return httpx.Response(200, json={"count": 3})
        return httpx.Response(200, json=[["s_id", "VAR_x"], ["s1", "a"]])

    c = _client(handler)
    assert entity_count(c, "STUDY_aaa", "ENT_s", []) == 3
    assert tabular(c, "STUDY_aaa", "ENT_s", ["VAR_x"], []) == [["s_id", "VAR_x"], ["s1", "a"]]
    assert seen == [
        {"filters": []},
        {"filters": [], "outputVariableIds": ["VAR_x"]},
    ]


def test_tabular_parses_tsv_when_server_ignores_accept():
    from _eda import tabular

    def handler(request):
        return httpx.Response(200, text="s_id\tVAR_x\ns1\ta\n", headers={"content-type": "text/plain"})

    assert tabular(_client(handler), "STUDY_aaa", "ENT_s", ["VAR_x"], []) == [
        ["s_id", "VAR_x"],
        ["s1", "a"],
    ]


def test_compute_status_autostart_flag():
    from _eda import compute_status

    seen = []

    def handler(request):
        seen.append((request.url.path, request.url.params.get("autostart")))
        return httpx.Response(200, json={"jobID": "j1", "status": "no-such-job"})

    c = _client(handler)
    compute_status(c, "differentialexpression", {"studyId": "STUDY_aaa"}, start=False)
    compute_status(c, "differentialexpression", {"studyId": "STUDY_aaa"}, start=True)
    assert seen == [
        ("/eda/computes/differentialexpression", "false"),
        ("/eda/computes/differentialexpression", "true"),
    ]


def test_wait_for_job_polls_until_complete():
    from _eda import wait_for_job

    statuses = iter(["queued", "in-progress", "complete"])

    def handler(request):
        return httpx.Response(200, json={"jobID": "j1", "status": next(statuses)})

    slept, logged = [], []
    st = wait_for_job(
        _client(handler), "differentialexpression", {}, sleep=slept.append, log=logged.append
    )
    assert st["status"] == "complete"
    assert slept == [2.0, 3.0]
    assert any("queued" in m for m in logged)


def test_wait_for_job_times_out_with_job_id():
    from _eda import EdaError, wait_for_job

    def handler(request):
        return httpx.Response(200, json={"jobID": "j1", "status": "in-progress"})

    with pytest.raises(EdaError) as e:
        wait_for_job(_client(handler), "differentialexpression", {}, timeout_s=4, sleep=lambda s: None)
    assert "j1" in str(e.value)


def test_wait_for_job_returns_failed_status():
    from _eda import wait_for_job

    def handler(request):
        return httpx.Response(200, json={"jobID": "j1", "status": "failed"})

    assert wait_for_job(_client(handler), "differentialexpression", {})["status"] == "failed"


def test_volcano_body_matches_plugin():
    from _eda import volcano

    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"statistics": []})

    body = {"studyId": "STUDY_aaa", "filters": [], "config": {"k": 1}, "derivedVariables": []}
    volcano(_client(handler), body)
    assert seen["path"] == "/eda/apps/differentialexpression/visualizations/volcanoplot"
    assert seen["body"] == {
        "studyId": "STUDY_aaa",
        "filters": [],
        "computeConfig": {"k": 1},
        "config": {},
    }


def test_compute_file_sends_accept_any():
    from _eda import compute_file

    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["accept"] = request.headers.get("accept")
        return httpx.Response(200, text="x\tPC1\n", headers={"content-type": "text/plain"})

    out = compute_file(_client(handler), "dimensionalityreduction", {}, "tabular")
    assert out == "x\tPC1\n"
    assert seen == {"path": "/eda/computes/dimensionalityreduction/tabular", "accept": "*/*"}
```

Create `veupathdb_database/tests/eda_helpers.py`:

```python
"""Shared test helpers for eda.py: captured fixtures, a synthetic study, a fake EDA service."""
import json
import pathlib

import httpx

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "eda"


def eda_fixture(name):
    path = FIXTURES / name
    text = path.read_text(encoding="utf-8")
    return text if path.suffix == ".tsv" else json.loads(text)


def _matches(cell, f):
    if f["type"] == "stringSet":
        return cell in f["stringSet"]
    if f["type"] == "numberRange":
        try:
            return f["min"] <= float(cell) <= f["max"]
        except ValueError:
            return False
    return True


class EdaMock:
    """Fake EDA service for the heat-shock study, served from captured fixtures.

    Filters on sample variables are applied to the captured sample tabular, which
    is enough for stringSet/numberRange tests. Override a route with
    mock.routes[(METHOD, path_without_/eda)] = fn(request) -> httpx.Response.
    """

    STUDY = "STUDY_e973eadd57"
    SAMPLE = "ENT_8151325d"

    def __init__(self):
        jobs = eda_fixture("jobs.json")
        self.de_job = jobs["de_heatshock"]["jobID"]
        self.pca_job = jobs["pca_heatshock"]["jobID"]
        self.requests = []
        self.routes = {}

    def sample_rows(self, filters):
        rows = eda_fixture("tabular_heatshock_sample.json")
        header, data = rows[0], rows[1:]
        for f in filters:
            if f.get("variableId") in header:
                col = header.index(f["variableId"])
                data = [r for r in data if _matches(r[col], f)]
        return [header] + data

    def compute_bodies(self, plugin):
        return [b for m, p, q, b in self.requests if p == f"/computes/{plugin}"]

    def handler(self, request):
        path = request.url.path.removeprefix("/eda")
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, path, dict(request.url.params), body))
        custom = self.routes.get((request.method, path))
        if custom:
            return custom(request)
        text = {"content-type": "text/plain"}
        if path == "/permissions":
            return httpx.Response(200, json=eda_fixture("permissions.json"))
        if path == f"/studies/{self.STUDY}":
            return httpx.Response(200, json={"study": eda_fixture("study_heatshock.json")})
        if path == f"/studies/{self.STUDY}/entities/{self.SAMPLE}/tabular":
            return httpx.Response(200, json=self.sample_rows(body["filters"]))
        if path.startswith(f"/studies/{self.STUDY}/entities/") and path.endswith("/count"):
            return httpx.Response(200, json={"count": len(self.sample_rows(body["filters"])) - 1})
        if path == "/computes/differentialexpression":
            return httpx.Response(200, json={"jobID": self.de_job, "status": "complete"})
        if path == "/apps/differentialexpression/visualizations/volcanoplot":
            return httpx.Response(200, json=eda_fixture("volcano_heatshock.json"))
        if path == "/computes/dimensionalityreduction":
            return httpx.Response(200, json={"jobID": self.pca_job, "status": "complete"})
        if path == "/computes/dimensionalityreduction/tabular":
            return httpx.Response(200, text=eda_fixture("pca_heatshock_tabular.tsv"), headers=text)
        if path == "/computes/dimensionalityreduction/meta":
            return httpx.Response(200, text=json.dumps(eda_fixture("pca_heatshock_meta.json")), headers=text)
        return httpx.Response(404, json={"status": "not-found", "path": path})
```

Append to `veupathdb_database/tests/conftest.py`:

```python
@pytest.fixture
def eda_cache(tmp_path, monkeypatch):
    """Point the EDA disk cache at a temp dir so tests never read ~/.cache."""
    import _client

    path = tmp_path / "eda-cache"
    monkeypatch.setattr(_client, "EDA_CACHE_DIR", path)
    return path
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_api.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named '_eda'`.

- [ ] **Step 3: Implement `_eda.py`**

Create `veupathdb_database/scripts/_eda.py`:

```python
"""EDA endpoint wrappers. `c` is a Client from _client.eda_client()."""
import difflib
import sys
import time

from _client import cached_json
from _shaping import strip_html

RUNNING = ("queued", "in-progress")


class EdaError(Exception):
    pass


def _permissions(c, refresh):
    return cached_json(f"{c.site_id}_permissions", lambda: c.get("/permissions"), refresh=refresh)


def resolve_dataset(c, dataset_id, refresh=False):
    """DS_ id -> the STUDY_ id EDA endpoints need, plus display name and description."""
    per = _permissions(c, refresh).get("perDataset") or {}
    if dataset_id not in per and not refresh:
        per = _permissions(c, True).get("perDataset") or {}
    if dataset_id not in per:
        close = difflib.get_close_matches(dataset_id, list(per), n=3, cutoff=0.8)
        raise EdaError(
            f"dataset '{dataset_id}' is not visible to this user on {c.site_id} "
            f"(missing from /eda/permissions). Check the login ('wdk.py whoami {c.site_id}') "
            "and the site."
            + (f" Close ids: {close}" if close else "")
        )
    entry = per[dataset_id]
    return {
        "datasetId": dataset_id,
        "studyId": entry["studyId"],
        "displayName": entry.get("displayName") or "",
        "shortDisplayName": entry.get("shortDisplayName") or "",
        "description": strip_html(entry.get("description") or ""),
    }


def study_metadata(c, study_id, refresh=False):
    return cached_json(
        f"{c.site_id}_study_{study_id}",
        lambda: c.get(f"/studies/{study_id}")["study"],
        refresh=refresh,
    )


def entity_count(c, study_id, entity_id, filters):
    return int(c.post(f"/studies/{study_id}/entities/{entity_id}/count", {"filters": filters})["count"])


def tabular(c, study_id, entity_id, variable_ids, filters):
    """Rows as string lists, header first: own key, ancestor keys (nearest first), variables."""
    data = c.post(
        f"/studies/{study_id}/entities/{entity_id}/tabular",
        {"filters": filters, "outputVariableIds": list(variable_ids)},
    )
    if isinstance(data, str):
        return [line.split("\t") for line in data.splitlines() if line]
    return data


def distribution(c, study_id, entity_id, variable_id, filters, bin_spec=None):
    body = {"filters": filters, "valueSpec": "count"}
    if bin_spec:
        body["binSpec"] = bin_spec
    return c.post(f"/studies/{study_id}/entities/{entity_id}/variables/{variable_id}/distribution", body)


def compute_status(c, plugin, body, start):
    """autostart=false is a pure lookup (never starts work); true starts or reuses the job."""
    return c.post(f"/computes/{plugin}", body, params={"autostart": "true" if start else "false"})


def job_status(c, job_id):
    return c.get(f"/jobs/{job_id}")


def delete_job(c, job_id):
    c.delete(f"/jobs/{job_id}")


def wait_for_job(c, plugin, body, timeout_s=900, sleep=time.sleep, log=None):
    """Start (or reuse) the job and poll until it leaves queued/in-progress."""
    log = log or (lambda msg: print(msg, file=sys.stderr))
    st = compute_status(c, plugin, body, start=True)
    delay, waited = 2.0, 0.0
    while st["status"] in RUNNING:
        if waited >= timeout_s:
            raise EdaError(
                f"job {st['jobID']} still {st['status']} after {int(waited)}s; it keeps running "
                "server-side: re-run later, or raise --timeout"
            )
        log(f"job {st['jobID']}: {st['status']} ({int(waited)}s)")
        sleep(delay)
        waited += delay
        delay = min(delay * 1.5, 30.0)
        st = job_status(c, st["jobID"])
    return st


def volcano(c, body):
    """The request the WSF plugin makes: all genes' statistics for a completed DE job."""
    return c.post(
        "/apps/differentialexpression/visualizations/volcanoplot",
        {"studyId": body["studyId"], "filters": body["filters"], "computeConfig": body["config"], "config": {}},
    )


def compute_file(c, plugin, body, name):
    """Job output as text. These endpoints answer 406 to Accept: application/json."""
    return c.post(f"/computes/{plugin}/{name}", body, headers={"Accept": "*/*"})
```

- [ ] **Step 4: Run the tests**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_api.py -q`
Expected: PASS.

- [ ] **Step 5: Write the fixture capture script**

Create `veupathdb_database/tests/fixtures/eda/capture.py`:

```python
"""Capture live EDA fixtures for the offline tests.

Run from veupathdb_database/ with a registered-user token (wdk.py login):
    uv run --with httpx python tests/fixtures/eda/capture.py
Overwrites the JSON/TSV files next to this script. Starts (or reuses) two shared
compute jobs on the heat-shock study; both are the website notebook's defaults.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "scripts"))

from _client import eda_client, load_token  # noqa: E402
from _eda import compute_file, volcano, wait_for_job  # noqa: E402

HEATSHOCK = "DS_e973eadd57"
ANTIBODY = "DS_24d441b301"  # GenesByAntibodyArrayEdaSubset_PlasmoDB_Crompton_Mali_AntibodyArray_RSRC
GENE = "ENT_fd574cd6"
GENE_ID = "VEUPATHDB_GENE_ID"
KEEP_STATISTICS = 200


def save(name, data):
    path = HERE / name
    text = data if isinstance(data, str) else json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path.name}", file=sys.stderr)


def trim_gene_vocab(entity):
    for v in entity.get("variables", []):
        if v["id"] == GENE_ID and "vocabulary" in v:
            v["vocabulary"] = v["vocabulary"][:5]
    for child in entity.get("children", []):
        trim_gene_vocab(child)


def main():
    c = eda_client("plasmodb", token=load_token())
    per = c.get("/permissions")["perDataset"]
    save("permissions.json", {"perDataset": {ds: per[ds] for ds in (HEATSHOCK, ANTIBODY)}})
    for tag, ds in (("heatshock", HEATSHOCK), ("antibody", ANTIBODY)):
        sid = per[ds]["studyId"]
        study = c.get(f"/studies/{sid}")["study"]
        trim_gene_vocab(study["rootEntity"])
        save(f"study_{tag}.json", study)
        root = study["rootEntity"]  # the sample entity in both fixture studies
        ids = [v["id"] for v in root["variables"] if v.get("type") != "category"]
        rows = c.post(f"/studies/{sid}/entities/{root['id']}/tabular", {"filters": [], "outputVariableIds": ids})
        save(f"tabular_{tag}_sample.json", rows)

    sid = per[HEATSHOCK]["studyId"]
    gene_var = {"entityId": GENE, "variableId": GENE_ID}
    value_var = {"entityId": GENE, "variableId": "SEQUENCE_READ_COUNT_SENSE"}
    de = {
        "studyId": sid,
        "filters": [],
        "derivedVariables": [],
        "config": {
            "identifierVariable": gene_var,
            "valueVariable": value_var,
            "comparator": {
                "variable": {"entityId": "ENT_8151325d", "variableId": "VAR_081ab087"},
                "groupA": [{"label": "normal"}],
                "groupB": [{"label": "febrile"}],
            },
            "differentialExpressionMethod": "DESeq",
            "pValueFloor": "1e-200",
        },
    }
    pca = {
        "studyId": sid,
        "filters": [],
        "derivedVariables": [],
        "config": {"identifierVariable": gene_var, "valueVariable": value_var, "dataFormat": "rawCounts"},
    }
    de_st = wait_for_job(c, "differentialexpression", de)
    pca_st = wait_for_job(c, "dimensionalityreduction", pca)
    vol = volcano(c, de)
    vol["totalStatistics"] = len(vol["statistics"])
    vol["statistics"] = vol["statistics"][:KEEP_STATISTICS]
    save("volcano_heatshock.json", vol)
    save("pca_heatshock_tabular.tsv", compute_file(c, "dimensionalityreduction", pca, "tabular"))
    save("pca_heatshock_meta.json", json.loads(compute_file(c, "dimensionalityreduction", pca, "meta")))
    save(
        "jobs.json",
        {
            "de_heatshock": {"body": de, "jobID": de_st["jobID"], "status": de_st["status"]},
            "pca_heatshock": {"body": pca, "jobID": pca_st["jobID"], "status": pca_st["status"]},
        },
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the capture (live, needs a token)**

Run: `cd veupathdb_database && uv run --with httpx python tests/fixtures/eda/capture.py`
Expected: stderr lists `permissions.json`, `study_heatshock.json`, `tabular_heatshock_sample.json`, `study_antibody.json`, `tabular_antibody_sample.json`, `volcano_heatshock.json`, `pca_heatshock_tabular.tsv`, `pca_heatshock_meta.json`, `jobs.json`. Check by hand:
- `jobs.json` → `de_heatshock.jobID` is `db04204e5386396e1ca2cb78469ab6fb` and `pca_heatshock.jobID` is `2679abb0e5c81b345a21b8f211db6a9b`
- `tabular_heatshock_sample.json` has 13 rows (header + 12)
- `volcano_heatshock.json` has `totalStatistics` 5511 (±release drift)

If a job id differs, stop: the study changed, and the gold values in this plan need re-capturing.

- [ ] **Step 7: Commit**

```bash
git add veupathdb_database/scripts/_eda.py veupathdb_database/tests/test_eda_api.py veupathdb_database/tests/eda_helpers.py veupathdb_database/tests/conftest.py veupathdb_database/tests/fixtures/eda
git commit -m "feat(eda): endpoint wrappers, job polling, captured heat-shock and antibody fixtures

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Study metadata: entity tree, expression entity, pruning

**Files:**
- Create: `veupathdb_database/scripts/_samples.py`
- Modify: `veupathdb_database/tests/eda_helpers.py` (append `synthetic_study`)
- Test: `veupathdb_database/tests/test_samples.py`

**Interfaces:**
- Consumes: `_eda.EdaError`
- Produces (in `_samples`):
  - constants `GENE_ID`, `VALUE_IDS`, `COUNT_VALUE_IDS`, `NUMERIC_TYPES = ("number", "integer")`, `MAX_TABULAR_ROWS = 5000`, `VOCAB_TOP = 10`
  - `class SampleError(EdaError)`
  - `index_entities(root) -> {entity_id: {"entity": raw, "parent": id | None}}`
  - `ancestors(index, entity_id) -> list[str]` (nearest first)
  - `expression_entities(index) -> list[{"entityId", "displayName", "geneCount", "valueIds"}]`
  - `pick_expression_entity(index, entity_id=None) -> dict` (one of the above)
  - `prune_entity(entity) -> list[item]`, where an item is `{"kind": "category", "id", "displayName", "depth"}` or `{"kind": "variable", "id", "entityId", "displayName", "type", "dataShape", "featured", "depth", "units"?, "definition"?, "vocabulary"?, "_binSpec"?}`
  - `variable_meta(index, entity_ids) -> {var_id: variable item}`
  - `all_var_entities(index) -> {var_id: entity_id}`

- [ ] **Step 1: Write the failing tests**

Append to `veupathdb_database/tests/eda_helpers.py`:

```python
def synthetic_study():
    """Participant -> Sample -> counts. Exercises hidden variables, categories,
    ordering, long definitions, and an ancestor join."""
    return {
        "id": "STUDY_x",
        "rootEntity": {
            "id": "ENT_p",
            "displayName": "Participant",
            "variables": [
                {"id": "VAR_sex", "parentId": "ENT_p", "displayName": "sex", "type": "string",
                 "dataShape": "categorical", "vocabulary": ["female", "male"], "displayOrder": 1},
                {"id": "VAR_hide", "parentId": "ENT_p", "displayName": "internal", "type": "string",
                 "dataShape": "categorical", "hideFrom": ["everywhere"]},
            ],
            "children": [
                {
                    "id": "ENT_s",
                    "displayName": "Sample",
                    "variables": [
                        {"id": "VAR_cat", "parentId": "ENT_s", "displayName": "Condition group", "type": "category"},
                        {"id": "VAR_cond", "parentId": "VAR_cat", "displayName": "condition", "type": "string",
                         "dataShape": "categorical", "isFeatured": True, "vocabulary": ["control", "treated"],
                         "displayOrder": 2, "definition": "x" * 200},
                        {"id": "VAR_dose", "parentId": "VAR_cat", "displayName": "dose", "type": "number",
                         "dataShape": "continuous", "units": "mg", "displayOrder": 1, "definition": "",
                         "distributionDefaults": {"rangeMin": 0, "rangeMax": 10, "binWidth": 1}},
                        {"id": "VAR_emptycat", "parentId": "ENT_s", "displayName": "Nothing here", "type": "category"},
                    ],
                    "children": [
                        {
                            "id": "ENT_g",
                            "displayName": "counts",
                            "variables": [
                                {"id": "VEUPATHDB_GENE_ID", "parentId": "ENT_g", "type": "string",
                                 "dataShape": "categorical", "distinctValuesCount": 100},
                                {"id": "SEQUENCE_READ_COUNT", "parentId": "ENT_g", "type": "integer",
                                 "dataShape": "continuous"},
                            ],
                        }
                    ],
                }
            ],
        },
    }
```

Create `veupathdb_database/tests/test_samples.py`:

```python
import copy

import pytest
from eda_helpers import eda_fixture, synthetic_study


def _index(study):
    from _samples import index_entities

    return index_entities(study["rootEntity"])


def test_index_and_ancestors_heatshock():
    from _samples import ancestors

    index = _index(eda_fixture("study_heatshock.json"))
    assert ancestors(index, "ENT_fd574cd6") == ["ENT_8151325d"]
    assert ancestors(index, "ENT_8151325d") == []


def test_ancestors_nearest_first():
    from _samples import ancestors

    assert ancestors(_index(synthetic_study()), "ENT_g") == ["ENT_s", "ENT_p"]


def test_expression_entity_heatshock():
    from _samples import pick_expression_entity

    expr = pick_expression_entity(_index(eda_fixture("study_heatshock.json")))
    assert expr["entityId"] == "ENT_fd574cd6"
    assert expr["geneCount"] == 5720
    assert expr["valueIds"] == ["SEQUENCE_READ_COUNT_SENSE", "SEQUENCE_READ_COUNT_ANTISENSE"]


def test_expression_entity_antibody():
    from _samples import pick_expression_entity

    expr = pick_expression_entity(_index(eda_fixture("study_antibody.json")))
    assert expr["entityId"] == "GENE_ANTIBODY_ARRAY_DATA"
    assert expr["valueIds"] == ["NORMALIZED_INTENSITY"]


def test_pick_expression_entity_refuses_ambiguity():
    from _samples import SampleError, pick_expression_entity

    study = synthetic_study()
    sample = study["rootEntity"]["children"][0]
    twin = copy.deepcopy(sample["children"][0])
    twin["id"], twin["displayName"] = "ENT_g2", "host counts"
    sample["children"].append(twin)
    index = _index(study)
    with pytest.raises(SampleError) as e:
        pick_expression_entity(index)
    assert "ENT_g" in str(e.value) and "ENT_g2" in str(e.value) and "--entity" in str(e.value)
    assert pick_expression_entity(index, "ENT_g2")["displayName"] == "host counts"
    with pytest.raises(SampleError):
        pick_expression_entity(index, "ENT_nope")


def test_not_de_ready():
    from _samples import SampleError, pick_expression_entity

    study = synthetic_study()
    study["rootEntity"]["children"][0]["children"] = []
    with pytest.raises(SampleError) as e:
        pick_expression_entity(_index(study))
    assert "not DE-ready" in str(e.value)


def test_prune_entity_hides_orders_and_truncates():
    from _samples import prune_entity

    sample = synthetic_study()["rootEntity"]["children"][0]
    items = prune_entity(sample)
    assert [(i["kind"], i["id"], i["depth"]) for i in items] == [
        ("category", "VAR_cat", 0),
        ("variable", "VAR_dose", 1),
        ("variable", "VAR_cond", 1),
    ]  # empty category dropped; displayOrder respected
    cond = items[2]
    assert cond["featured"] is True and cond["entityId"] == "ENT_s"
    assert len(cond["definition"]) == 120 and cond["definition"].endswith("…")
    dose = items[1]
    assert "definition" not in dose and dose["units"] == "mg"
    assert dose["_binSpec"] == {"displayRangeMin": 0, "displayRangeMax": 10, "binWidth": 1}


def test_prune_entity_drops_hidden_variables():
    from _samples import prune_entity

    items = prune_entity(synthetic_study()["rootEntity"])
    assert [i["id"] for i in items] == ["VAR_sex"]


def test_variable_meta_and_all_var_entities():
    from _samples import all_var_entities, variable_meta

    index = _index(synthetic_study())
    meta = variable_meta(index, ["ENT_s", "ENT_p"])
    assert set(meta) == {"VAR_dose", "VAR_cond", "VAR_sex"}
    assert meta["VAR_sex"]["entityId"] == "ENT_p"
    owners = all_var_entities(index)
    assert owners["SEQUENCE_READ_COUNT"] == "ENT_g" and owners["VAR_hide"] == "ENT_p"


def test_prune_antibody_root_keeps_categories_with_variables():
    from _samples import prune_entity

    items = prune_entity(eda_fixture("study_antibody.json")["rootEntity"])
    kinds = {i["kind"] for i in items}
    assert kinds == {"category", "variable"}
    assert all(i["depth"] >= 0 for i in items)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_samples.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named '_samples'`.

- [ ] **Step 3: Implement**

Create `veupathdb_database/scripts/_samples.py`:

```python
"""EDA study metadata pruning and sample-table assembly (pure functions; no I/O)."""
from collections import defaultdict

from _eda import EdaError

GENE_ID = "VEUPATHDB_GENE_ID"
VALUE_IDS = (
    "SEQUENCE_READ_COUNT",
    "SEQUENCE_READ_COUNT_SENSE",
    "SEQUENCE_READ_COUNT_ANTISENSE",
    "NORMALIZED_EXPRESSION",
    "NORMALIZED_INTENSITY",
)
COUNT_VALUE_IDS = VALUE_IDS[:3]
NUMERIC_TYPES = ("number", "integer")
HIDDEN = {"everywhere", "variableTree"}
DEF_MAX = 120
IDENT_MIN_DISTINCT = 20
IDENT_COVERAGE = 0.9
VOCAB_TOP = 10
MAX_TABULAR_ROWS = 5000


class SampleError(EdaError):
    pass


def index_entities(root):
    """Entity id -> {"entity": raw entity, "parent": parent id or None}."""
    index = {}

    def walk(entity, parent):
        index[entity["id"]] = {"entity": entity, "parent": parent}
        for child in entity.get("children", []):
            walk(child, entity["id"])

    walk(root, None)
    return index


def ancestors(index, entity_id):
    """Ancestor entity ids, nearest first (the order /tabular prepends their keys)."""
    out = []
    parent = index[entity_id]["parent"]
    while parent is not None:
        out.append(parent)
        parent = index[parent]["parent"]
    return out


def expression_entities(index):
    found = []
    for eid, node in index.items():
        variables = {v["id"]: v for v in node["entity"].get("variables", [])}
        values = [v for v in VALUE_IDS if v in variables]
        if GENE_ID in variables and values:
            found.append(
                {
                    "entityId": eid,
                    "displayName": node["entity"].get("displayName", eid),
                    "geneCount": variables[GENE_ID].get("distinctValuesCount"),
                    "valueIds": values,
                }
            )
    return found


def pick_expression_entity(index, entity_id=None):
    found = expression_entities(index)
    if not found:
        raise SampleError(f"not DE-ready: no entity has {GENE_ID} plus one of {', '.join(VALUE_IDS)}")
    listing = "; ".join(f"{e['entityId']} \"{e['displayName']}\"" for e in found)
    if entity_id:
        for e in found:
            if e["entityId"] == entity_id:
                return e
        raise SampleError(f"--entity {entity_id} is not an expression entity; choose one of: {listing}")
    if len(found) > 1:
        raise SampleError(f"study has {len(found)} expression entities ({listing}); pass --entity ID")
    return found[0]


def _var_item(v, entity_id, depth):
    item = {
        "kind": "variable",
        "id": v["id"],
        "entityId": entity_id,
        "displayName": v.get("displayName", v["id"]),
        "type": v.get("type"),
        "dataShape": v.get("dataShape"),
        "featured": bool(v.get("isFeatured")),
        "depth": depth,
    }
    if v.get("units"):
        item["units"] = v["units"]
    definition = (v.get("definition") or "").strip()
    if definition:
        item["definition"] = definition if len(definition) <= DEF_MAX else definition[: DEF_MAX - 1] + "…"
    if v.get("vocabulary"):
        item["vocabulary"] = v["vocabulary"]
    dd = v.get("distributionDefaults") or {}
    if v.get("type") in NUMERIC_TYPES and "binWidth" in dd:
        item["_binSpec"] = {
            "displayRangeMin": dd.get("rangeMin"),
            "displayRangeMax": dd.get("rangeMax"),
            "binWidth": dd["binWidth"],
        }
    return item


def _drop_empty_categories(items):
    keep = []
    for i, item in enumerate(items):
        if item["kind"] == "variable":
            keep.append(item)
            continue
        j = i + 1
        while j < len(items) and items[j]["depth"] > item["depth"]:
            if items[j]["kind"] == "variable":
                keep.append(item)
                break
            j += 1
    return keep


def prune_entity(entity):
    """Visible variables in tree order (category headings kept only above variables).

    A variable's parentId may name a sibling variable (a category) or something
    else; anything that is not a sibling makes it a root. Hidden variables are
    dropped but their children are still shown at the hidden node's depth.
    """
    variables = entity.get("variables", [])
    by_id = {v["id"]: v for v in variables}
    kids = defaultdict(list)
    for v in variables:
        parent = v.get("parentId")
        kids[parent if parent in by_id else None].append(v)
    out = []

    def order(v):
        return (v.get("displayOrder", 10**6), v.get("displayName", ""))

    def walk(parent_key, depth):
        for v in sorted(kids.get(parent_key, []), key=order):
            hidden = bool(HIDDEN & set(v.get("hideFrom") or []))
            if not hidden:
                if v.get("type") == "category":
                    out.append({"kind": "category", "id": v["id"], "displayName": v.get("displayName", v["id"]), "depth": depth})
                else:
                    out.append(_var_item(v, entity["id"], depth))
            walk(v["id"], depth if hidden else depth + 1)

    walk(None, 0)
    return _drop_empty_categories(out)


def variable_meta(index, entity_ids):
    """Visible variables of the given entities: var id -> variable item."""
    meta = {}
    for eid in entity_ids:
        for item in prune_entity(index[eid]["entity"]):
            if item["kind"] == "variable":
                meta[item["id"]] = item
    return meta


def all_var_entities(index):
    return {
        v["id"]: eid
        for eid, node in index.items()
        for v in node["entity"].get("variables", [])
        if v.get("type") != "category"
    }
```

- [ ] **Step 4: Run the tests**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_samples.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add veupathdb_database/scripts/_samples.py veupathdb_database/tests/test_samples.py veupathdb_database/tests/eda_helpers.py
git commit -m "feat(eda): study metadata pruning and expression-entity detection

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Sample table, summaries, and `eda.py study`

**Files:**
- Modify: `veupathdb_database/scripts/_samples.py` (append)
- Create: `veupathdb_database/scripts/eda.py`
- Modify: `veupathdb_database/tests/conftest.py` (append `eda_mock`, `run_eda`)
- Test: `veupathdb_database/tests/test_samples_table.py`, `veupathdb_database/tests/test_eda_cli_study.py`

**Interfaces:**
- Consumes: Task 2 `_eda.resolve_dataset`, `study_metadata`, `entity_count`, `tabular`; Task 3 `_samples.index_entities`, `ancestors`, `pick_expression_entity`, `prune_entity`, `variable_meta`
- Produces:
  - `_samples.convert_value(meta, raw) -> float | str | None` (`""` → `None`; numeric types → `float`)
  - `_samples.build_sample_table(fetch_tabular, index, expr_entity_id, var_meta) -> {"entityId", "rows": [{"sampleId", var_id: value}], "byEntity": {entity_id: [{var_id: value}]}}`, where `fetch_tabular(entity_id, variable_ids) -> rows`
  - `_samples.summarise_variable(meta, values) -> {"kind": "continuous"|"categorical"|"identifier", "n", "missing", "distinct"?, "min"?, "max"?, "mean"?, "levels"?: [[label, count], …]}`
  - `_samples.render_study(dataset, expr, sections, others) -> list[str]`, `_samples.study_json(dataset, expr, sections, others, table, filters) -> dict`
  - `eda.py` module functions used by later tasks: `emit`, `fail`, `log`, `eda_client_for(site)`, `wdk_client_for(site)`, `resolve_target_arg(site, arg)`, `load_target(args) -> {"client", "site", "dataset", "index", "expr", "notebook", "search"}`, `read_filters(args, t) -> list`, `sample_view(t, filters) -> {"chain", "meta", "totals", "counts", "table" | None, "too_big"}`, `build_parser()`, `main(argv=None)`
  - Section dict: `{"entityId", "displayName", "records", "total", "items": [(item, summary | None)], "note": str | None}`
  - conftest fixtures: `eda_mock` (an `EdaMock` wired into `eda.eda_client_for`), `run_eda(*argv) -> stdout`

- [ ] **Step 1: Write the failing unit tests**

Create `veupathdb_database/tests/test_samples_table.py`:

```python
from eda_helpers import eda_fixture, synthetic_study

TAB = {
    "ENT_s": [
        ["Sample_stable_id", "Participant_stable_id", "VAR_dose", "VAR_cond"],
        ["s1", "p1", "1.5", "control"],
        ["s2", "p1", "", "treated"],
        ["s3", "p2", "2", "treated"],
        ["s4", "p3", "3", "control"],
    ],
    "ENT_p": [["Participant_stable_id", "VAR_sex"], ["p1", "female"], ["p2", "male"], ["p3", ""]],
}


def test_build_sample_table_joins_ancestors():
    from _samples import build_sample_table, index_entities, variable_meta

    index = index_entities(synthetic_study()["rootEntity"])
    meta = variable_meta(index, ["ENT_s", "ENT_p"])
    calls = []

    def fetch(eid, ids):
        calls.append((eid, sorted(ids)))
        return TAB[eid]

    table = build_sample_table(fetch, index, "ENT_g", meta)
    assert calls == [("ENT_s", ["VAR_cond", "VAR_dose"]), ("ENT_p", ["VAR_sex"])]
    assert table["entityId"] == "ENT_s"
    assert table["rows"] == [
        {"sampleId": "s1", "VAR_dose": 1.5, "VAR_cond": "control", "VAR_sex": "female"},
        {"sampleId": "s2", "VAR_dose": None, "VAR_cond": "treated", "VAR_sex": "female"},
        {"sampleId": "s3", "VAR_dose": 2.0, "VAR_cond": "treated", "VAR_sex": "male"},
        {"sampleId": "s4", "VAR_dose": 3.0, "VAR_cond": "control", "VAR_sex": None},
    ]
    assert table["byEntity"]["ENT_p"] == [{"VAR_sex": "female"}, {"VAR_sex": "male"}, {"VAR_sex": None}]


def test_build_sample_table_heatshock_fixture():
    from _samples import ancestors, build_sample_table, index_entities, variable_meta

    index = index_entities(eda_fixture("study_heatshock.json")["rootEntity"])
    meta = variable_meta(index, ancestors(index, "ENT_fd574cd6"))
    table = build_sample_table(
        lambda eid, ids: eda_fixture("tabular_heatshock_sample.json"), index, "ENT_fd574cd6", meta
    )
    rows = table["rows"]
    assert len(rows) == 12
    temps = sorted(r["VAR_081ab087"] for r in rows)
    assert temps == ["febrile"] * 6 + ["normal"] * 6
    for vid, m in meta.items():
        if m["type"] in ("number", "integer"):
            assert all(r.get(vid) is None or isinstance(r[vid], float) for r in rows)


def test_summarise_variable_kinds():
    from _samples import summarise_variable

    cat = summarise_variable({"type": "string"}, ["b", "a", "b", None])
    assert cat == {"n": 3, "missing": 1, "distinct": 2, "kind": "categorical", "levels": [["b", 2], ["a", 1]]}
    ident = summarise_variable({"type": "string"}, [f"s{i}" for i in range(25)])
    assert ident["kind"] == "identifier" and ident["distinct"] == 25
    num = summarise_variable({"type": "number"}, [1.0, 3.0, None])
    assert num == {"n": 2, "missing": 1, "kind": "continuous", "min": 1.0, "max": 3.0, "mean": 2.0, "distinct": 2}
    empty = summarise_variable({"type": "number"}, [None, None])
    assert empty == {"n": 0, "missing": 2, "kind": "continuous"}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_samples_table.py -q`
Expected: FAIL with `ImportError: cannot import name 'build_sample_table'`.

- [ ] **Step 3: Implement the `_samples.py` additions**

Change the first import line of `_samples.py` to `from collections import Counter, defaultdict`, then append:

```python
def convert_value(meta, raw):
    if raw is None or raw == "":
        return None
    if meta.get("type") in NUMERIC_TYPES:
        try:
            return float(raw)
        except ValueError:
            return None
    return raw


def build_sample_table(fetch_tabular, index, expr_entity_id, var_meta):
    """Join the expression entity's ancestors into one row per sample.

    fetch_tabular(entity_id, variable_ids) returns /tabular rows: header first,
    then own key, ancestor keys (nearest first), variable values.
    """
    chain = ancestors(index, expr_entity_id)
    if not chain:
        raise SampleError(f"expression entity {expr_entity_id} has no parent sample entity")
    records, by_entity = {}, {}
    for eid in chain:
        ids = [vid for vid, m in var_meta.items() if m["entityId"] == eid]
        rows = fetch_tabular(eid, ids)
        header, data = rows[0], rows[1:]
        n_anc = len(ancestors(index, eid))
        var_cols = header[1 + n_anc:]
        table = {}
        for row in data:
            vals = {
                vid: convert_value(var_meta[vid], cell)
                for vid, cell in zip(var_cols, row[1 + n_anc:])
                if vid in var_meta
            }
            table[row[0]] = {"anc": row[1:1 + n_anc], "vals": vals}
        records[eid] = table
        by_entity[eid] = [rec["vals"] for rec in table.values()]
    out = []
    for key, rec in records[chain[0]].items():
        row = {"sampleId": key, **rec["vals"]}
        for depth, anc_key in enumerate(rec["anc"]):
            anc = records[chain[depth + 1]].get(anc_key)
            if anc:
                row.update(anc["vals"])
        out.append(row)
    return {"entityId": chain[0], "rows": out, "byEntity": by_entity}


def summarise_variable(meta, values):
    present = [v for v in values if v is not None]
    out = {"n": len(present), "missing": len(values) - len(present)}
    if meta.get("type") in NUMERIC_TYPES:
        out["kind"] = "continuous"
        if present:
            out.update(
                min=min(present),
                max=max(present),
                mean=sum(present) / len(present),
                distinct=len(set(present)),
            )
        return out
    counts = Counter(present)
    out["distinct"] = len(counts)
    if len(counts) > IDENT_MIN_DISTINCT and len(counts) >= IDENT_COVERAGE * len(present):
        out["kind"] = "identifier"
        return out
    out["kind"] = "categorical"
    out["levels"] = [[k, n] for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))]
    return out


def _fmt_num(x):
    return f"{x:g}" if isinstance(x, float) else str(x)


def variable_line(item, summary):
    star = "*" if item.get("featured") else " "
    indent = "  " * (item["depth"] + 1)
    units = f" ({item['units']})" if item.get("units") else ""
    head = f"{indent}{star}{item['id']}  {item['displayName']}{units}"
    kind = summary.get("kind")
    if kind == "identifier":
        return f"{head}  [identifier: {summary['distinct']} distinct / {summary['n']} records]"
    if summary.get("unavailable"):
        return f"{head}  [{item.get('dataShape') or item.get('type')}]  ({summary['unavailable']})"
    shape = item.get("dataShape") or item.get("type")
    if kind == "continuous":
        if summary["n"]:
            detail = (
                f"{_fmt_num(summary['min'])}–{_fmt_num(summary['max'])}, "
                f"mean {_fmt_num(round(summary['mean'], 3))}, {summary['missing']} missing"
            )
        else:
            detail = f"no values, {summary['missing']} missing"
    else:
        levels = summary.get("levels", [])
        detail = " · ".join(f"{label} {n}" for label, n in levels[:VOCAB_TOP])
        if len(levels) > VOCAB_TOP:
            detail += f" … {len(levels) - VOCAB_TOP} more"
        if summary.get("missing"):
            detail += f", {summary['missing']} missing"
    return f"{head}  [{shape}]  {detail}"


def render_study(dataset, expr, sections, others):
    lines = [f"{dataset['studyId']} ({dataset['datasetId']}) \"{dataset['displayName']}\""]
    desc = dataset.get("description")
    if desc:
        lines.append("  " + (desc if len(desc) <= 1000 else desc[:999] + "…"))
    lines.append(
        f"DE-ready: gene entity {expr['entityId']} \"{expr['displayName']}\" — "
        f"{GENE_ID} ({expr['geneCount']}), values: {', '.join(expr['valueIds'])}"
    )
    for s in sections:
        rec = f"{s['records']} of {s['total']} records" if s["records"] != s["total"] else f"{s['total']} records"
        lines.append(f"{s['entityId']} \"{s['displayName']}\" — {rec}")
        if s.get("note"):
            lines.append(f"  ({s['note']})")
        for item, summary in s["items"]:
            if item["kind"] == "category":
                lines.append(f"{'  ' * (item['depth'] + 1)}{item['displayName']}:")
            else:
                lines.append(variable_line(item, summary))
    for o in others:
        lines.append(
            f"{o['entityId']} \"{o['displayName']}\" — {o['records']} records "
            "(not an ancestor of the expression entity: not usable as a comparator)"
        )
    return lines


def study_json(dataset, expr, sections, others, table, filters):
    def clean(item):
        return {k: v for k, v in item.items() if not k.startswith("_") and k != "vocabulary"}

    return {
        "dataset": dataset,
        "expression": expr,
        "filters": filters,
        "entities": [
            {
                "entityId": s["entityId"],
                "displayName": s["displayName"],
                "records": s["records"],
                "total": s["total"],
                "note": s["note"],
                "variables": [{**clean(i), **({"summary": sm} if sm else {})} for i, sm in s["items"]],
            }
            for s in sections
        ],
        "otherEntities": others,
        "samples": table["rows"] if table else None,
    }
```

- [ ] **Step 4: Run the unit tests**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_samples_table.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing CLI tests**

Append to `veupathdb_database/tests/conftest.py` (add `import httpx` at the top of the file):

```python
@pytest.fixture
def eda_mock(eda_cache, monkeypatch):
    """eda.py talks to an EdaMock serving the captured heat-shock fixtures."""
    import eda as eda_cli
    from _client import eda_client
    from eda_helpers import EdaMock

    mock = EdaMock()
    monkeypatch.setattr(
        eda_cli,
        "eda_client_for",
        lambda site: eda_client(site, token="tok-x", transport=httpx.MockTransport(mock.handler), backoff=0),
    )
    return mock


@pytest.fixture
def run_eda(eda_mock, capsys):
    import eda as eda_cli

    def run(*argv):
        """Run eda.py; return stdout and keep stderr as run.err. On SystemExit, read
        stderr with capsys.readouterr().err instead."""
        eda_cli.main(list(argv))
        captured = capsys.readouterr()
        run.err = captured.err
        return captured.out

    return run
```

Create `veupathdb_database/tests/test_eda_cli_study.py`:

```python
import json

import pytest


def test_study_text(run_eda):
    out = run_eda("study", "plasmodb", "DS_e973eadd57")
    assert out.startswith('STUDY_e973eadd57 (DS_e973eadd57) "Heat shock response')
    assert "DE-ready: gene entity ENT_fd574cd6" in out
    assert "VEUPATHDB_GENE_ID (5720)" in out
    assert 'ENT_8151325d "Sample" — 12 records' in out
    assert "temperature_condition" in out and "febrile 6 · normal 6" in out


def test_study_json(run_eda):
    out = json.loads(run_eda("study", "plasmodb", "DS_e973eadd57", "--json"))
    assert out["dataset"]["studyId"] == "STUDY_e973eadd57"
    assert out["expression"]["valueIds"] == ["SEQUENCE_READ_COUNT_SENSE", "SEQUENCE_READ_COUNT_ANTISENSE"]
    assert len(out["samples"]) == 12
    sample = out["entities"][0]
    assert sample["entityId"] == "ENT_8151325d" and sample["records"] == 12
    temp = next(v for v in sample["variables"] if v["id"] == "VAR_081ab087")
    assert temp["summary"]["levels"] == [["febrile", 6], ["normal", 6]]
    assert "vocabulary" not in temp


def test_study_unknown_dataset_fails(run_eda, capsys):
    with pytest.raises(SystemExit):
        run_eda("study", "plasmodb", "DS_nope")
    assert "not visible" in capsys.readouterr().err


def test_study_rejects_non_dataset_argument(run_eda, capsys):
    with pytest.raises(SystemExit):
        run_eda("study", "plasmodb", "STUDY_e973eadd57")
    assert "DS_" in capsys.readouterr().err
```

- [ ] **Step 6: Run them to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_cli_study.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'eda'`.

- [ ] **Step 7: Create `eda.py`**

Create `veupathdb_database/scripts/eda.py`:

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""VEuPathDB EDA differential expression: explore an RNA-Seq or antibody-array
study, discover and choose a contrast, run DESeq2/limma on the shared EDA
compute cache, and hand the result to wdk.py as a search step.

Run `eda.py --help` for subcommands, `eda.py <sub> --help` for details.
"""
import argparse
import json
import pathlib
import sys


def emit(obj) -> None:
    print(json.dumps(obj, indent=1, ensure_ascii=False))


def fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def eda_client_for(site):
    from _client import eda_client, load_token

    return eda_client(site, token=load_token())


def wdk_client_for(site):
    from _client import Client, load_token

    return Client(site, token=load_token())


def resolve_target_arg(site, arg):
    """DS_ id -> (dataset id, notebook type or None, search name or None)."""
    if not arg.startswith("DS_"):
        fail(f"'{arg}' is not a DS_ dataset id (STUDY_ ids are EDA-internal; eda.py takes the DS_ id)")
    return arg, None, None


def load_target(args):
    from _eda import resolve_dataset, study_metadata
    from _samples import index_entities, pick_expression_entity

    ds_id, notebook, search = resolve_target_arg(args.site, args.dataset)
    c = eda_client_for(args.site)
    ds = resolve_dataset(c, ds_id)
    study = study_metadata(c, ds["studyId"], refresh=getattr(args, "refresh", False))
    index = index_entities(study["rootEntity"])
    expr = pick_expression_entity(index, getattr(args, "entity", None))
    return {
        "client": c,
        "site": args.site,
        "dataset": ds,
        "index": index,
        "expr": expr,
        "notebook": notebook,
        "search": search,
    }


def read_filters(args, t):
    """Sample filters for this command (Task 16 adds --filters)."""
    return []


def sample_view(t, filters):
    """Counts for the expression entity's ancestors plus the joined sample table
    (None when an entity is too large for /tabular)."""
    from _eda import entity_count, tabular
    from _samples import MAX_TABULAR_ROWS, ancestors, build_sample_table, variable_meta

    c, sid, index = t["client"], t["dataset"]["studyId"], t["index"]
    chain = ancestors(index, t["expr"]["entityId"])
    meta = variable_meta(index, chain)
    totals = {e: entity_count(c, sid, e, []) for e in chain}
    counts = {e: entity_count(c, sid, e, filters) for e in chain} if filters else dict(totals)
    too_big = [e for e in chain if counts[e] > MAX_TABULAR_ROWS]
    table = None
    if not too_big:
        table = build_sample_table(
            lambda e, ids: tabular(c, sid, e, ids, filters), index, t["expr"]["entityId"], meta
        )
    return {"chain": chain, "meta": meta, "totals": totals, "counts": counts, "table": table, "too_big": too_big}


def study_sections(t, view, filters):
    from _samples import prune_entity, summarise_variable

    sections = []
    for eid in reversed(view["chain"]):
        entity = t["index"][eid]["entity"]
        rows = view["table"]["byEntity"][eid]
        items = []
        for item in prune_entity(entity):
            if item["kind"] == "category":
                items.append((item, None))
            else:
                items.append((item, summarise_variable(item, [r.get(item["id"]) for r in rows])))
        sections.append(
            {
                "entityId": eid,
                "displayName": entity.get("displayName", eid),
                "records": view["counts"][eid],
                "total": view["totals"][eid],
                "items": items,
                "note": None,
            }
        )
    return sections


def other_entities(t, view, filters):
    from _eda import entity_count

    skip = set(view["chain"]) | {t["expr"]["entityId"]}
    return [
        {
            "entityId": eid,
            "displayName": node["entity"].get("displayName", eid),
            "records": entity_count(t["client"], t["dataset"]["studyId"], eid, filters),
        }
        for eid, node in t["index"].items()
        if eid not in skip
    ]


def cmd_study(args) -> None:
    from _samples import render_study, study_json

    t = load_target(args)
    filters = read_filters(args, t)
    view = sample_view(t, filters)
    sections = study_sections(t, view, filters)
    others = other_entities(t, view, filters)
    if args.json:
        emit(study_json(t["dataset"], t["expr"], sections, others, view["table"], filters))
    else:
        print("\n".join(render_study(t["dataset"], t["expr"], sections, others)))


def _target_args(sp):
    sp.add_argument("site")
    sp.add_argument("dataset", help="DS_ dataset id")
    sp.add_argument("--entity", help="expression entity id, when the study has several")
    sp.add_argument("--refresh", action="store_true", help="bypass the 7-day study metadata cache")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eda.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("study", help="pruned overview of a study's samples and annotation")
    _target_args(sp)
    sp.add_argument("--json", action="store_true", help="pruned structure plus the sample table")
    sp.set_defaults(func=cmd_study)

    return p


def main(argv=None) -> None:
    from _client import WDKError
    from _eda import EdaError
    from _sites import UnknownSiteError

    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (UnknownSiteError, WDKError, EdaError) as e:
        fail(str(e))


if __name__ == "__main__":
    main()
```

(`pathlib` is used from Task 10 on, by `resolve_contrast`.)

- [ ] **Step 8: Run the CLI tests and the whole suite**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_cli_study.py -q && uv run --with pytest --with httpx python -m pytest tests -q`
Expected: PASS (live tests pass or skip).

- [ ] **Step 9: Try it live once (needs a token)**

Run: `cd veupathdb_database && uv run scripts/eda.py study plasmodb DS_24d441b301 | head -40`
Expected: the antibody study prints with category headings and variable lines. Note anything unreadable for the pruning thresholds (spec Open item 3). Thresholds change only if output is clearly unusable, and any change goes with a test.

- [ ] **Step 10: Commit**

```bash
git add veupathdb_database/scripts/_samples.py veupathdb_database/scripts/eda.py veupathdb_database/tests/conftest.py veupathdb_database/tests/test_samples_table.py veupathdb_database/tests/test_eda_cli_study.py
git commit -m "feat(eda): sample-table join, variable summaries, eda.py study

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `/distribution` fallback for large sample entities

**Files:**
- Modify: `veupathdb_database/scripts/_samples.py` (append `summarise_from_distribution`)
- Modify: `veupathdb_database/scripts/eda.py` (`study_sections`)
- Modify: `veupathdb_database/tests/eda_helpers.py` (distribution route)
- Test: `veupathdb_database/tests/test_eda_cli_study.py` (append)

**Interfaces:**
- Consumes: `_eda.distribution`, item `_binSpec` (Task 3), `sample_view(...)["table"] is None` when an entity has more than `MAX_TABULAR_ROWS` records (Task 4)
- Produces: `_samples.summarise_from_distribution(meta, dist) -> summary` (same shape as `summarise_variable`, plus `"source": "distribution"`, or `{"kind", "n": 0, "missing": 0, "unavailable": reason}` when a continuous variable has no bin defaults)

- [ ] **Step 1: Write the failing test**

In `veupathdb_database/tests/eda_helpers.py`, add this branch to `EdaMock.handler` just before the final `return httpx.Response(404, …)`:

```python
        if path.endswith("/distribution"):
            if "binSpec" in body:
                return httpx.Response(200, json={"histogram": [], "statistics": {
                    "subsetSize": 12, "subsetMin": 37, "subsetMax": 41, "subsetMean": 39,
                    "numVarValues": 12, "numDistinctValues": 2, "numMissingCases": 0}})
            return httpx.Response(200, json={
                "histogram": [{"binLabel": "febrile", "value": 6}, {"binLabel": "normal", "value": 6}],
                "statistics": {"numVarValues": 12, "numDistinctValues": 2, "numMissingCases": 0}})
```

Append to `veupathdb_database/tests/test_eda_cli_study.py`:

```python
def test_study_falls_back_to_distribution_when_too_many_records(run_eda, eda_mock):
    import httpx

    count_path = f"/studies/{eda_mock.STUDY}/entities/{eda_mock.SAMPLE}/count"
    eda_mock.routes[("POST", count_path)] = lambda r: httpx.Response(200, json={"count": 6000})
    out = run_eda("study", "plasmodb", "DS_e973eadd57")
    assert "6000 records" in out
    assert "/distribution" in out
    paths = [p for m, p, q, b in eda_mock.requests]
    assert not any(p.endswith("/tabular") for p in paths)
    assert any(p.endswith("/distribution") for p in paths)
    assert "febrile 6 · normal 6" in out
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_cli_study.py -q -k distribution`
Expected: FAIL with `TypeError: 'NoneType' object is not subscriptable` (the table is None).

- [ ] **Step 3: Implement**

Append to `_samples.py`:

```python
def summarise_from_distribution(meta, dist):
    """Per-variable summary from /distribution when the joint table is unavailable."""
    stats = dist.get("statistics") or {}
    out = {"n": stats.get("numVarValues", 0), "missing": stats.get("numMissingCases", 0), "source": "distribution"}
    distinct = stats.get("numDistinctValues", 0)
    if meta.get("type") in NUMERIC_TYPES:
        out.update(kind="continuous", distinct=distinct)
        if out["n"]:
            out.update(min=stats.get("subsetMin"), max=stats.get("subsetMax"), mean=stats.get("subsetMean"))
        return out
    out["distinct"] = distinct
    if distinct > IDENT_MIN_DISTINCT and distinct >= IDENT_COVERAGE * out["n"]:
        out["kind"] = "identifier"
        return out
    levels = [[b["binLabel"], b["value"]] for b in dist.get("histogram", []) if b.get("value")]
    out["kind"] = "categorical"
    out["levels"] = sorted(levels, key=lambda kv: (-kv[1], str(kv[0])))
    return out
```

In `eda.py`, replace `study_sections` with:

```python
def study_sections(t, view, filters):
    from _eda import distribution
    from _samples import MAX_TABULAR_ROWS, NUMERIC_TYPES, prune_entity, summarise_from_distribution, summarise_variable

    sections = []
    for eid in reversed(view["chain"]):
        entity = t["index"][eid]["entity"]
        rows = view["table"]["byEntity"][eid] if view["table"] else None
        items = []
        for item in prune_entity(entity):
            if item["kind"] == "category":
                items.append((item, None))
            elif rows is not None:
                items.append((item, summarise_variable(item, [r.get(item["id"]) for r in rows])))
            elif item.get("type") in NUMERIC_TYPES and not item.get("_binSpec"):
                items.append((item, {"kind": "continuous", "n": 0, "missing": 0, "unavailable": "no bin defaults"}))
            else:
                dist = distribution(
                    t["client"], t["dataset"]["studyId"], eid, item["id"], filters,
                    item.get("_binSpec") if item.get("type") in NUMERIC_TYPES else None,
                )
                items.append((item, summarise_from_distribution(item, dist)))
        note = None
        if rows is None:
            note = (
                f"{view['counts'][eid]} records > {MAX_TABULAR_ROWS}: per-variable /distribution "
                "summaries, no joint sample table (contrasts and pca need it: narrow with --filters)"
            )
        sections.append(
            {
                "entityId": eid,
                "displayName": entity.get("displayName", eid),
                "records": view["counts"][eid],
                "total": view["totals"][eid],
                "items": items,
                "note": note,
            }
        )
    return sections
```

The entity line prints `6000 records` because the mocked count is the same with and without filters.

- [ ] **Step 4: Run the study tests**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_cli_study.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add veupathdb_database/scripts/_samples.py veupathdb_database/scripts/eda.py veupathdb_database/tests/eda_helpers.py veupathdb_database/tests/test_eda_cli_study.py
git commit -m "feat(eda): distribution fallback for sample entities over 5000 records

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Canonical contrast form and job ids

**Files:**
- Create: `veupathdb_database/scripts/_contrasts.py`
- Test: `veupathdb_database/tests/test_contrasts_canonical.py`

**Interfaces:**
- Consumes: `_samples.GENE_ID`, `COUNT_VALUE_IDS`, `NUMERIC_TYPES`, `summarise_variable`; `_eda.EdaError`
- Produces (in `_contrasts`):
  - constants `PLUGIN_DE = "differentialexpression"`, `PLUGIN_PCA = "dimensionalityreduction"`, `P_VALUE_FLOOR = "1e-200"`, `METHODS = ("DESeq", "limma")`, `NOTEBOOK_METHODS = {"differentialExpressionNotebook": "DESeq", "antibodyArrayNotebook": "limma"}`, `MIN_REPLICATES = 2`, `LOW_REPLICATES = 3`, `MAX_PAIRWISE_LEVELS = 6`, `MAX_CACHE_CHECKS = 30`, `MAX_CANDIDATES = 50`
  - `class ContrastError(EdaError)`
  - `job_id(plugin, body) -> str` (32 lowercase hex)
  - `canonical_group(group) -> list[{"label", "min"?, "max"?}]` (string values, sorted)
  - `canonical_filters(filters) -> list` (sorted; set values sorted)
  - `merge_filters(*lists) -> list` (canonical; raises on a conflict for the same variable)
  - `de_config(expr_entity_id, value_var, comparator, group_a, group_b, method) -> dict` (`comparator` = `{"entityId", "variableId", …}`)
  - `data_format(value_var) -> "rawCounts" | "normalizedValues"`
  - `pca_config(expr_entity_id, value_var, n_pcs=None) -> dict`
  - `compute_body(study_id, config, filters) -> {"studyId", "filters", "config", "derivedVariables": []}`
  - `choose_value_var(expr, requested=None) -> (value_var, note | None)`
  - `choose_method(notebook, value_var, requested="auto") -> (method, note | None)`

- [ ] **Step 1: Write the failing tests**

Create `veupathdb_database/tests/test_contrasts_canonical.py`:

```python
import hashlib
import json

import pytest

GOLD_BODY = {
    "studyId": "STUDY_e973eadd57",
    "filters": [],
    "derivedVariables": [],
    "config": {
        "identifierVariable": {"entityId": "ENT_fd574cd6", "variableId": "VEUPATHDB_GENE_ID"},
        "valueVariable": {"entityId": "ENT_fd574cd6", "variableId": "SEQUENCE_READ_COUNT_SENSE"},
        "comparator": {
            "variable": {"entityId": "ENT_8151325d", "variableId": "VAR_081ab087"},
            "groupA": [{"label": "normal"}],
            "groupB": [{"label": "febrile"}],
        },
        "differentialExpressionMethod": "DESeq",
        "pValueFloor": "1e-200",
    },
}
GOLD_JOB = "db04204e5386396e1ca2cb78469ab6fb"  # live jobID, plasmodb 2026-10-03
TEMP = {"entityId": "ENT_8151325d", "variableId": "VAR_081ab087"}


def test_job_id_matches_live_gold():
    from _contrasts import job_id

    assert job_id("differentialexpression", GOLD_BODY) == GOLD_JOB


def test_job_id_ignores_key_order():
    from _contrasts import job_id

    shuffled = json.loads(json.dumps(GOLD_BODY, sort_keys=True))
    shuffled = {k: shuffled[k] for k in reversed(list(shuffled))}
    assert job_id("differentialexpression", shuffled) == GOLD_JOB


def test_job_id_hashes_non_ascii_unescaped():
    from _contrasts import job_id

    body = {"studyId": "STUDY_x", "filters": [], "derivedVariables": [], "config": {"l": "naïve"}}
    inner = '{"config":{"l":"naïve"},"derivedVariables":[],"filters":[],"studyId":"STUDY_x"}'
    want = hashlib.md5(json.dumps(["p", inner], separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    assert job_id("p", body) == want


def test_de_config_reproduces_gold_and_compute_body():
    from _contrasts import compute_body, de_config

    cfg = de_config("ENT_fd574cd6", "SEQUENCE_READ_COUNT_SENSE", TEMP, [{"label": "normal"}], [{"label": "febrile"}], "DESeq")
    assert compute_body("STUDY_e973eadd57", cfg, []) == GOLD_BODY


def test_label_order_is_canonical_but_swapping_groups_is_a_new_job():
    from _contrasts import PLUGIN_DE, compute_body, de_config, job_id

    def jid(a, b):
        cfg = de_config("E", "SEQUENCE_READ_COUNT", TEMP, a, b, "DESeq")
        return job_id(PLUGIN_DE, compute_body("STUDY_x", cfg, []))

    ab = [{"label": "b"}, {"label": "a"}]
    assert jid(ab, [{"label": "c"}]) == jid(list(reversed(ab)), [{"label": "c"}])
    assert jid([{"label": "a"}], [{"label": "c"}]) != jid([{"label": "c"}], [{"label": "a"}])


def test_canonical_group_stringifies_and_sorts():
    from _contrasts import ContrastError, canonical_group

    assert canonical_group([{"label": "b"}, {"label": "a", "min": 1, "max": 2.5}]) == [
        {"label": "a", "min": "1", "max": "2.5"},
        {"label": "b"},
    ]
    with pytest.raises(ContrastError):
        canonical_group([{"min": "1", "max": "2"}])


def test_canonical_and_merged_filters():
    from _contrasts import ContrastError, canonical_filters, merge_filters

    f1 = {"entityId": "E2", "variableId": "V1", "type": "stringSet", "stringSet": ["b", "a"]}
    f2 = {"entityId": "E1", "variableId": "V9", "type": "numberRange", "min": 1, "max": 2}
    assert canonical_filters([f1, f2]) == [f2, {**f1, "stringSet": ["a", "b"]}]
    assert merge_filters([f1], [f2], [dict(f1, stringSet=["a", "b"])]) == canonical_filters([f1, f2])
    with pytest.raises(ContrastError):
        merge_filters([f1], [dict(f1, stringSet=["c"])])


def test_compute_body_refuses_dataset_ids():
    from _contrasts import ContrastError, compute_body

    with pytest.raises(ContrastError) as e:
        compute_body("DS_e973eadd57", {}, [])
    assert "STUDY_" in str(e.value)


def test_pca_config():
    from _contrasts import pca_config

    assert pca_config("E", "SEQUENCE_READ_COUNT_SENSE") == {
        "identifierVariable": {"entityId": "E", "variableId": "VEUPATHDB_GENE_ID"},
        "valueVariable": {"entityId": "E", "variableId": "SEQUENCE_READ_COUNT_SENSE"},
        "dataFormat": "rawCounts",
    }
    cfg = pca_config("E", "NORMALIZED_INTENSITY", n_pcs=5)
    assert cfg["dataFormat"] == "normalizedValues" and cfg["nPCs"] == 5


def test_choose_value_var():
    from _contrasts import ContrastError, choose_value_var

    assert choose_value_var({"entityId": "E", "valueIds": ["SEQUENCE_READ_COUNT"]}) == ("SEQUENCE_READ_COUNT", None)
    v, note = choose_value_var({"entityId": "E", "valueIds": ["SEQUENCE_READ_COUNT_SENSE", "SEQUENCE_READ_COUNT_ANTISENSE"]})
    assert v == "SEQUENCE_READ_COUNT_SENSE" and "SEQUENCE_READ_COUNT_ANTISENSE" in note
    assert choose_value_var({"entityId": "E", "valueIds": ["NORMALIZED_INTENSITY"]})[0] == "NORMALIZED_INTENSITY"
    with pytest.raises(ContrastError):
        choose_value_var({"entityId": "E", "valueIds": ["SEQUENCE_READ_COUNT"]}, "NORMALIZED_INTENSITY")


def test_choose_method():
    from _contrasts import ContrastError, choose_method

    assert choose_method("antibodyArrayNotebook", "NORMALIZED_INTENSITY") == ("limma", None)
    assert choose_method("differentialExpressionNotebook", "SEQUENCE_READ_COUNT") == ("DESeq", None)
    assert choose_method(None, "SEQUENCE_READ_COUNT_SENSE") == ("DESeq", None)
    assert choose_method(None, "NORMALIZED_EXPRESSION") == ("limma", None)
    method, note = choose_method("differentialExpressionNotebook", "SEQUENCE_READ_COUNT", "limma")
    assert method == "limma" and "separate job" in note
    with pytest.raises(ContrastError):
        choose_method(None, "SEQUENCE_READ_COUNT", "edgeR")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_contrasts_canonical.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named '_contrasts'`.

- [ ] **Step 3: Implement**

Create `veupathdb_database/scripts/_contrasts.py`:

```python
"""Contrast enumeration and canonical compute bodies (pure functions; no I/O).

Canonical form: labels sorted within each group, filters sorted by
(entityId, variableId) with set values sorted, pValueFloor 1e-200, and the
method implied by the search family. The same canonical contrast always gives
the same EDA job, shared with website users and other agents.
"""
import difflib
import hashlib
import itertools
import json
import re
from collections import Counter, defaultdict

from _eda import EdaError
from _samples import COUNT_VALUE_IDS, GENE_ID, NUMERIC_TYPES, summarise_variable

PLUGIN_DE = "differentialexpression"
PLUGIN_PCA = "dimensionalityreduction"
P_VALUE_FLOOR = "1e-200"
METHODS = ("DESeq", "limma")
NOTEBOOK_METHODS = {"differentialExpressionNotebook": "DESeq", "antibodyArrayNotebook": "limma"}
VALUE_PREFERENCE = ("SEQUENCE_READ_COUNT", "SEQUENCE_READ_COUNT_SENSE", "NORMALIZED_INTENSITY", "NORMALIZED_EXPRESSION")
MIN_REPLICATES = 2
LOW_REPLICATES = 3
MAX_PAIRWISE_LEVELS = 6
MAX_CACHE_CHECKS = 30
MAX_CANDIDATES = 50  # crossed designs multiply strata; past this, narrow with --vars


class ContrastError(EdaError):
    pass


def _compact(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def job_id(plugin, body):
    """EDA job id: MD5 of ["plugin", key-sorted compact JSON of the body] (service-eda
    JobIDs.kt). Matches live ids for label-based configs. The server's jobID is
    authoritative: Java may render numeric filter values differently."""
    payload = json.dumps([plugin, _compact(body)], separators=(",", ":"), ensure_ascii=False)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def canonical_group(group):
    out = []
    for g in group:
        item = {k: str(g[k]) for k in ("label", "min", "max") if g.get(k) is not None}
        if "label" not in item:
            raise ContrastError(f"every group entry needs a label: {g!r}")
        out.append(item)
    return sorted(out, key=lambda g: (g["label"], g.get("min", ""), g.get("max", "")))


def canonical_filters(filters):
    out = []
    for f in filters or []:
        f = dict(f)
        for key in ("stringSet", "numberSet", "dateSet"):
            if key in f:
                f[key] = sorted(f[key], key=str)
        out.append(f)
    return sorted(out, key=lambda f: (f.get("entityId", ""), f.get("variableId", ""), _compact(f)))


def merge_filters(*lists):
    merged = {}
    for f in canonical_filters(list(itertools.chain(*lists))):
        key = (f.get("entityId"), f.get("variableId"))
        if key in merged and _compact(merged[key]) != _compact(f):
            raise ContrastError(f"conflicting filters on {key[1]} ({key[0]}): {merged[key]} vs {f}")
        merged[key] = f
    return canonical_filters(list(merged.values()))


def de_config(expr_entity_id, value_var, comparator, group_a, group_b, method):
    if method not in METHODS:
        raise ContrastError(f"method must be one of {METHODS}, got {method!r}")
    return {
        "identifierVariable": {"entityId": expr_entity_id, "variableId": GENE_ID},
        "valueVariable": {"entityId": expr_entity_id, "variableId": value_var},
        "comparator": {
            "variable": {"entityId": comparator["entityId"], "variableId": comparator["variableId"]},
            "groupA": canonical_group(group_a),
            "groupB": canonical_group(group_b),
        },
        "differentialExpressionMethod": method,
        "pValueFloor": P_VALUE_FLOOR,
    }


def data_format(value_var):
    return "rawCounts" if value_var in COUNT_VALUE_IDS else "normalizedValues"


def pca_config(expr_entity_id, value_var, n_pcs=None):
    """The notebook's PCA config (no nPCs, so the job matches website runs);
    an explicit n_pcs makes a separate job."""
    cfg = {
        "identifierVariable": {"entityId": expr_entity_id, "variableId": GENE_ID},
        "valueVariable": {"entityId": expr_entity_id, "variableId": value_var},
        "dataFormat": data_format(value_var),
    }
    if n_pcs is not None:
        cfg["nPCs"] = int(n_pcs)
    return cfg


def compute_body(study_id, config, filters):
    """Exactly the body the WSF plugin POSTs, so job ids match WDK steps and notebooks."""
    if study_id.startswith("DS_"):
        raise ContrastError(f"compute bodies take the STUDY_ id, not {study_id}; resolve it via /permissions")
    return {"studyId": study_id, "filters": canonical_filters(filters), "config": config, "derivedVariables": []}


def choose_value_var(expr, requested=None):
    available = expr["valueIds"]
    if requested:
        if requested not in available:
            raise ContrastError(
                f"--value-var {requested} is not on {expr['entityId']}; available: {', '.join(available)}"
            )
        return requested, None
    for pref in VALUE_PREFERENCE:
        if pref in available:
            others = [v for v in available if v != pref]
            note = f"using {pref}; also available: {', '.join(others)} (--value-var)" if others else None
            return pref, note
    return available[0], None


def choose_method(notebook, value_var, requested="auto"):
    implied = NOTEBOOK_METHODS.get(notebook) or ("DESeq" if value_var in COUNT_VALUE_IDS else "limma")
    if requested in (None, "auto"):
        return implied, None
    if requested not in METHODS:
        raise ContrastError(f"--method must be auto, DESeq or limma, got {requested!r}")
    if requested == implied:
        return requested, None
    return requested, (
        f"--method {requested} differs from the {implied} the website uses here: "
        "a separate job, not shared with website users"
    )
```

(`difflib`, `re`, `Counter`, `defaultdict` and `summarise_variable` are used by Task 7.)

- [ ] **Step 4: Run the tests**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_contrasts_canonical.py -q`
Expected: PASS, including `test_job_id_matches_live_gold`.

- [ ] **Step 5: Commit**

```bash
git add veupathdb_database/scripts/_contrasts.py veupathdb_database/tests/test_contrasts_canonical.py
git commit -m "feat(eda): canonical DE/PCA configs and EDA job-id derivation (matches live id)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Contrast enumeration, design structure, contrast files

**Files:**
- Modify: `veupathdb_database/scripts/_contrasts.py` (append)
- Test: `veupathdb_database/tests/test_contrasts_enum.py`

**Interfaces:**
- Consumes: Task 6 helpers; sample-table rows `[{"sampleId", var_id: value}]` and `var_meta` items (Tasks 3–4)
- Produces:
  - `is_control_label(label) -> bool`
  - `comparator_levels(rows, meta) -> list[(group_entry, [sampleIds])]` (count desc, then label; numeric values become `[v, next)` bins)
  - `samples_in_group(rows, var_id, group) -> list[sampleId]`
  - `aliased(rows, a, b) -> bool`, `determines(rows, a, b) -> bool`
  - `replicate_check(n_a, n_b) -> note | None` (raises `ContrastError` below 2)
  - `enumerate_contrasts(rows, var_meta, base_filters=(), only_vars=None, max_candidates=MAX_CANDIDATES) -> {"candidates", "skipped", "aliases", "nested", "truncated"}` (`nested` items: `{"variableId", "displayName", "within", "withinName"}`; `truncated` is `None` or `{"shown", "total"}`), where a candidate is `{"index", "comparator": {"entityId", "variableId", "displayName"}, "groupA", "groupB", "reference", "filters", "nA", "nB", "notes", "stratum": None | {"variableId", "displayName", "label"}}`
  - `reference` is `"label match"` (groupA's label looks like a control) or `"arbitrary"` (neither or both do; groupA is the larger level, then the first label). It is a **hint**: choosing the reference is the agent's call, and a swap costs nothing when the mirror job is cached (Task 10). Each level pair is listed **once**, never in both orientations, so the list stays bounded.
  - `load_contrast(obj, var_meta, var_entities, chain, base_filters=()) -> candidate-shaped dict` (no `index`/`nA`/`nB`)

- [ ] **Step 1: Write the failing tests**

Create `veupathdb_database/tests/test_contrasts_enum.py`:

```python
import pytest


def meta(vid, name=None, type_="string", entity="ENT_s", featured=False, vocab=None):
    m = {
        "kind": "variable", "id": vid, "entityId": entity, "displayName": name or vid,
        "type": type_, "dataShape": "continuous" if type_ in ("number", "integer") else "categorical",
        "featured": featured, "depth": 0,
    }
    if vocab:
        m["vocabulary"] = vocab
    return m


def crossed_rows():
    rows = []
    for strain in ("A", "B", "C"):
        for temp, deg in (("normal", 37.0), ("febrile", 41.0)):
            for rep in (1, 2):
                rows.append({
                    "sampleId": f"{strain}_{deg:g}_{rep}", "temp": temp, "deg": deg,
                    "strain": strain, "label": f"{strain}-{temp}", "name": f"{strain}_{deg:g}_{rep}",
                })
    return rows


CROSSED = {
    "temp": meta("temp", "temperature_condition"),
    "deg": meta("deg", "temperature", "number"),
    "strain": meta("strain", "strain"),
    "label": meta("label", "label", featured=True),
    "name": meta("name", "sample name"),
}


def test_is_control_label():
    from _contrasts import is_control_label

    for yes in ("WT 37C", "wild type", "Wild-Type", "Control", "pre-infection", "naïve", "mock-infected", "normal"):
        assert is_control_label(yes), yes
    for no in ("febrile", "treated", "PB31", "delta-LRR5-41C"):
        assert not is_control_label(no), no


def test_crossed_design_first_candidate_and_strata():
    from _contrasts import enumerate_contrasts

    out = enumerate_contrasts(crossed_rows(), CROSSED)
    first = out["candidates"][0]
    assert first["index"] == 1
    assert first["comparator"] == {"entityId": "ENT_s", "variableId": "temp", "displayName": "temperature_condition"}
    assert first["groupA"] == [{"label": "normal"}] and first["groupB"] == [{"label": "febrile"}]
    assert first["reference"] == "label match"
    assert (first["nA"], first["nB"], first["filters"], first["stratum"]) == (6, 6, [], None)
    assert out["truncated"] is None
    assert any("same grouping as temperature" in n for n in first["notes"])
    assert any("strain varies within the groups" in n for n in first["notes"])
    strata = out["candidates"][1:4]
    assert [s["stratum"]["label"] for s in strata] == ["A", "B", "C"]
    assert strata[0]["filters"] == [{"entityId": "ENT_s", "variableId": "strain", "type": "stringSet", "stringSet": ["A"]}]
    assert all((s["nA"], s["nB"]) == (2, 2) for s in strata)
    assert all(any("low replicates" in n for n in s["notes"]) for s in strata)
    assert out["aliases"] == [{"variableId": "deg", "displayName": "temperature", "sameAs": "temp", "sameAsName": "temperature_condition"}]
    assert any(s["variableId"] == "name" for s in out["skipped"])
    assert {"variableId": "label", "displayName": "label", "within": "temp", "withinName": "temperature_condition"} in out["nested"]
    assert not any(n["variableId"] == "strain" and n["within"] == "temp" for n in out["nested"])  # crossed, not nested


def test_indices_are_contiguous_and_deterministic():
    from _contrasts import enumerate_contrasts

    a = enumerate_contrasts(crossed_rows(), CROSSED)
    b = enumerate_contrasts(list(reversed(crossed_rows())), dict(reversed(list(CROSSED.items()))))
    assert [c["index"] for c in a["candidates"]] == list(range(1, len(a["candidates"]) + 1))
    assert a == b


def test_pair_notes_name_other_differences():
    from _contrasts import enumerate_contrasts

    out = enumerate_contrasts(crossed_rows(), CROSSED, only_vars={"label"})
    hit = next(c for c in out["candidates"] if c["groupA"] == [{"label": "A-normal"}] and c["groupB"] == [{"label": "A-febrile"}])
    assert "groups also differ in temperature_condition: normal vs febrile" in hit["notes"]
    assert all(c["comparator"]["variableId"] == "label" for c in out["candidates"])


def test_partial_confounding_is_noted():
    from _contrasts import enumerate_contrasts

    rows = (
        [{"sampleId": f"c{i}", "cond": "control", "batch": "b1"} for i in range(3)]
        + [{"sampleId": f"t{i}", "cond": "treated", "batch": "b2"} for i in range(3)]
        + [{"sampleId": "o1", "cond": "other", "batch": "b1"}, {"sampleId": "o2", "cond": "other", "batch": "b2"}]
    )
    out = enumerate_contrasts(rows, {"cond": meta("cond", "condition"), "batch": meta("batch", "batch")}, only_vars={"cond"})
    hit = next(c for c in out["candidates"] if c["groupB"] == [{"label": "treated"}] and c["groupA"] == [{"label": "control"}])
    assert "groups also differ in batch: b1 vs b2" in hit["notes"]


def test_ambiguous_orientation_lists_one_with_hint():
    from _contrasts import enumerate_contrasts

    rows = [{"sampleId": f"s{i}", "col": c} for i, c in enumerate(["red"] * 3 + ["blue"] * 3)]
    cands = enumerate_contrasts(rows, {"col": meta("col")})["candidates"]
    assert [(c["groupA"][0]["label"], c["groupB"][0]["label"]) for c in cands] == [("blue", "red")]
    assert cands[0]["reference"] == "arbitrary"
    assert any("reference unclear" in n and "swap" in n for n in cands[0]["notes"])


def test_label_matched_reference_is_a_hint_not_a_rule():
    from _contrasts import enumerate_contrasts

    rows = [{"sampleId": f"s{i}", "g": c} for i, c in enumerate(["mutant"] * 3 + ["WT"] * 3)]
    cands = enumerate_contrasts(rows, {"g": meta("g")})["candidates"]
    assert len(cands) == 1
    assert cands[0]["groupA"] == [{"label": "WT"}] and cands[0]["reference"] == "label match"
    assert any("reference guessed from label" in n and "swap" in n for n in cands[0]["notes"])


def test_candidate_list_is_capped():
    from _contrasts import enumerate_contrasts

    # three crossed 6-level factors, 2 replicates per cell: hundreds of pairs and strata
    rows = [
        {"sampleId": f"{a}{b}{c}{r}", "f1": f"a{a}", "f2": f"b{b}", "f3": f"c{c}"}
        for a in range(6) for b in range(6) for c in range(6) for r in range(2)
    ]
    var_meta = {v: meta(v) for v in ("f1", "f2", "f3")}
    out = enumerate_contrasts(rows, var_meta)
    assert [c["index"] for c in out["candidates"]] == list(range(1, 51))
    assert out["truncated"]["shown"] == 50 and out["truncated"]["total"] > 50
    assert enumerate_contrasts(rows, var_meta, max_candidates=None)["truncated"] is None


def test_missing_values_are_not_a_level():
    from _contrasts import enumerate_contrasts

    rows = [{"sampleId": f"s{i}", "cond": c} for i, c in enumerate(["control", "control", "treated", "treated", None, None])]
    out = enumerate_contrasts(rows, {"cond": meta("cond", vocab=["control", "treated"])})
    assert len(out["candidates"]) == 1
    c = out["candidates"][0]
    assert (c["nA"], c["nB"]) == (2, 2)
    assert "" not in [g["label"] for g in c["groupA"] + c["groupB"]]


def test_singleton_levels_left_out_with_note():
    from _contrasts import enumerate_contrasts

    rows = [{"sampleId": f"s{i}", "cond": c} for i, c in enumerate(["control"] * 3 + ["treated"] * 3 + ["odd"])]
    c = enumerate_contrasts(rows, {"cond": meta("cond")})["candidates"][0]
    assert "levels with <2 samples left out: odd (1)" in c["notes"]


def test_many_levels_are_summarised_not_paired():
    from _contrasts import enumerate_contrasts

    rows = [{"sampleId": f"s{i}", "stage": f"st{i // 2}"} for i in range(14)]
    out = enumerate_contrasts(rows, {"stage": meta("stage")})
    assert out["candidates"] == []
    skip = out["skipped"][0]
    assert "pool levels" in skip["reason"] and len(skip["levels"]) == 7


def test_numeric_levels_are_half_open_bins():
    from _contrasts import comparator_levels, samples_in_group

    rows = [{"sampleId": f"s{i}", "dose": d} for i, d in enumerate([0.0, 0.0, 5.0, 5.0, 10.0, 10.0])]
    levels = comparator_levels(rows, meta("dose", type_="number"))
    assert [e for e, ids in levels] == [
        {"label": "0", "min": "0", "max": "5"},
        {"label": "10", "min": "10", "max": "11"},
        {"label": "5", "min": "5", "max": "10"},
    ]
    assert samples_in_group(rows, "dose", [{"label": "5", "min": "5", "max": "10"}]) == ["s2", "s3"]


def test_replicate_check():
    from _contrasts import ContrastError, replicate_check

    with pytest.raises(ContrastError):
        replicate_check(1, 5)
    assert "low replicates" in replicate_check(2, 5)
    assert replicate_check(3, 3) is None


def test_load_contrast_validates_and_merges_filters():
    from _contrasts import ContrastError, load_contrast

    var_meta = {"temp": meta("temp", "temperature_condition", vocab=["febrile", "normal"]), "deg": meta("deg", type_="number")}
    owners = {"temp": "ENT_s", "deg": "ENT_s", "SEQUENCE_READ_COUNT": "ENT_g"}
    base = [{"entityId": "ENT_s", "variableId": "strain", "type": "stringSet", "stringSet": ["A"]}]
    c = load_contrast(
        {"comparator": {"variableId": "temp"}, "groupA": [{"label": "normal"}], "groupB": [{"label": "febrile"}]},
        var_meta, owners, ["ENT_s"], base,
    )
    assert c["comparator"]["entityId"] == "ENT_s" and c["filters"] == base
    with pytest.raises(ContrastError) as e:
        load_contrast({"comparator": {"variableId": "temp"}, "groupA": [{"label": "norml"}], "groupB": [{"label": "febrile"}]}, var_meta, owners, ["ENT_s"])
    assert "normal" in str(e.value)
    with pytest.raises(ContrastError) as e:
        load_contrast({"comparator": {"variableId": "SEQUENCE_READ_COUNT"}, "groupA": [{"label": "x"}], "groupB": [{"label": "y"}]}, var_meta, owners, ["ENT_s"])
    assert "not a parent" in str(e.value)
    with pytest.raises(ContrastError) as e:
        load_contrast({"comparator": {"variableId": "tmp"}, "groupA": [{"label": "x"}], "groupB": [{"label": "y"}]}, var_meta, owners, ["ENT_s"])
    assert "temp" in str(e.value)
    with pytest.raises(ContrastError):
        load_contrast({"comparator": {"variableId": "deg"}, "groupA": [{"label": "37"}], "groupB": [{"label": "41"}]}, var_meta, owners, ["ENT_s"])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_contrasts_enum.py -q`
Expected: FAIL with `ImportError: cannot import name 'is_control_label'`.

- [ ] **Step 3: Implement**

Append to `_contrasts.py`:

```python
CONTROL_TOKENS = {
    "control", "ctrl", "normal", "wt", "wildtype", "untreated", "mock", "baseline", "uninfected",
    "naive", "vehicle", "healthy", "unexposed", "reference", "negative", "pre", "before", "0h", "t0", "d0",
}
CONTROL_PHRASES = ("wild type", "wild-type", "day 0", "time 0")


def is_control_label(label):
    s = str(label).strip().lower().replace("ï", "i")
    if any(p in s for p in CONTROL_PHRASES):
        return True
    return bool(CONTROL_TOKENS & set(re.split(r"[^a-z0-9]+", s)))


def _fmt(v):
    v = float(v)
    return str(int(v)) if v.is_integer() else repr(v)


def comparator_levels(rows, meta):
    """(group entry, sample ids) per level; missing values are no level. Numeric values
    become [v, next value) bins, matching veupathUtils' half-open whichValuesInBin."""
    vid = meta["id"]
    by_value = defaultdict(list)
    for r in rows:
        v = r.get(vid)
        if v is not None:
            by_value[v].append(r["sampleId"])
    if meta.get("type") in NUMERIC_TYPES:
        values = sorted(by_value)
        entries = []
        for i, v in enumerate(values):
            nxt = values[i + 1] if i + 1 < len(values) else v + 1
            entries.append(({"label": _fmt(v), "min": _fmt(v), "max": _fmt(nxt)}, by_value[v]))
    else:
        entries = [({"label": str(v)}, ids) for v, ids in by_value.items()]
    return sorted(entries, key=lambda e: (-len(e[1]), e[0]["label"]))


def samples_in_group(rows, var_id, group):
    out = []
    for r in rows:
        v = r.get(var_id)
        if v is None:
            continue
        for g in group:
            if "min" in g and "max" in g:
                try:
                    x = float(v)
                except (TypeError, ValueError):
                    continue
                if float(g["min"]) <= x < float(g["max"]):
                    out.append(r["sampleId"])
                    break
            elif str(v) == g["label"]:
                out.append(r["sampleId"])
                break
    return out


def aliased(rows, a, b):
    """a and b partition the samples (that have both) identically."""
    pairs = {(r.get(a), r.get(b)) for r in rows if r.get(a) is not None and r.get(b) is not None}
    return len(pairs) >= 2 and len({x for x, _ in pairs}) == len(pairs) == len({y for _, y in pairs})


def determines(rows, a, b):
    """Every level of a maps to one level of b (a is as fine as, or finer than, b)."""
    seen = {}
    for r in rows:
        x, y = r.get(a), r.get(b)
        if x is None or y is None:
            continue
        if seen.setdefault(x, y) != y:
            return False
    return len(seen) >= 2


def _low_note(n_a, n_b):
    n = min(n_a, n_b)
    return f"low replicates (n={n} in the smaller group)" if n < LOW_REPLICATES else None


def replicate_check(n_a, n_b):
    if min(n_a, n_b) < MIN_REPLICATES:
        raise ContrastError(
            f"too few replicates (groupA n={n_a}, groupB n={n_b}); DESeq2/limma need at least "
            f"{MIN_REPLICATES} per group"
        )
    return _low_note(n_a, n_b)


def _counts_by(rows, sample_ids, var_id):
    ids = set(sample_ids)
    return Counter(r.get(var_id) for r in rows if r["sampleId"] in ids and r.get(var_id) is not None)


def _filter_for(meta, value):
    base = {"entityId": meta["entityId"], "variableId": meta["id"]}
    if meta.get("type") in NUMERIC_TYPES:
        return {**base, "type": "numberRange", "min": value, "max": value}
    return {**base, "type": "stringSet", "stringSet": [str(value)]}


def _profile(rows, meta):
    summary = summarise_variable(meta, [r.get(meta["id"]) for r in rows])
    if summary["kind"] == "identifier":
        return {"usable": [], "excluded": [], "identifier": True,
                "reason": "identifier-like (almost every sample has its own value)"}
    levels = comparator_levels(rows, meta)
    prof = {
        "usable": [(e, ids) for e, ids in levels if len(ids) >= MIN_REPLICATES],
        "excluded": [(e["label"], len(ids)) for e, ids in levels if len(ids) < MIN_REPLICATES],
        "identifier": False,
        "reason": None,
    }
    if meta.get("type") in NUMERIC_TYPES and len(levels) > MAX_PAIRWISE_LEVELS:
        prof["reason"] = f"continuous with {len(levels)} distinct values: write a contrast file with numeric ranges"
    elif len(prof["usable"]) < 2:
        prof["reason"] = "fewer than 2 levels with 2+ samples"
    elif len(prof["usable"]) > MAX_PAIRWISE_LEVELS:
        prof["reason"] = f"{len(prof['usable'])} levels (> {MAX_PAIRWISE_LEVELS}): pool levels into groups in a contrast file"
    return prof


def _comparator(meta):
    return {"entityId": meta["entityId"], "variableId": meta["id"], "displayName": meta["displayName"]}


def _pair_candidates(rows, var_meta, prof, vid, base, aliases):
    meta = var_meta[vid]
    p = prof[vid]
    twins = [a["displayName"] for a in aliases if a["sameAs"] == vid]
    alias_ids = {a["variableId"] for a in aliases}
    # sorted: note order must not depend on dict order; aliases are covered by their twin
    others = sorted(z for z in var_meta if z != vid and not prof[z]["identifier"] and z not in alias_ids)
    confounders = [z for z in others if not determines(rows, z, vid)]
    stratifiers = [z for z in others if prof[z]["reason"] is None and not aliased(rows, vid, z) and not determines(rows, z, vid)]
    out = []
    for (ea, ids_a), (eb, ids_b) in itertools.combinations(p["usable"], 2):
        # One orientation per pair. The control-label match is only a hint: the agent
        # decides the reference, and a swap reuses the cached mirror job (Task 10).
        ca, cb = is_control_label(ea["label"]), is_control_label(eb["label"])
        (ga, a_ids), (gb, b_ids) = (ea, ids_a), (eb, ids_b)
        if cb and not ca:
            (ga, a_ids), (gb, b_ids) = (gb, b_ids), (ga, a_ids)
        reference = "label match" if ca != cb else "arbitrary"
        notes = []
        if reference == "label match":
            notes.append(f"reference guessed from label {ga['label']!r}: swap groups in a contrast file if "
                         "groupB is the real baseline (same statistics, sign flipped)")
        else:
            notes.append("reference unclear: groupA chosen arbitrarily; swap groups in a contrast file if "
                         "groupB is the baseline (same statistics, sign flipped)")
        if twins:
            notes.append(f"same grouping as {', '.join(twins)}: effects cannot be separated")
        if p["excluded"]:
            notes.append("levels with <2 samples left out: " + ", ".join(f"{label} ({n})" for label, n in p["excluded"]))
        low = _low_note(len(a_ids), len(b_ids))
        if low:
            notes.append(low)
        for z in confounders:
            za, zb = _counts_by(rows, a_ids, z), _counts_by(rows, b_ids, z)
            if len(za) == 1 and len(zb) == 1 and set(za) != set(zb):
                notes.append(f"groups also differ in {var_meta[z]['displayName']}: {_label(next(iter(za)))} vs {_label(next(iter(zb)))}")
        strata = []
        for z in stratifiers:
            za, zb = _counts_by(rows, a_ids, z), _counts_by(rows, b_ids, z)
            if len(za) < 2 and len(zb) < 2:
                continue
            shared = sorted((v for v in set(za) & set(zb) if za[v] >= MIN_REPLICATES and zb[v] >= MIN_REPLICATES), key=str)
            if not shared:
                continue
            zname = var_meta[z]["displayName"]
            notes.append(f"{zname} varies within the groups (the compute has no covariates): stratified versions follow")
            for v in shared:
                strata.append({
                    "comparator": _comparator(meta),
                    "groupA": canonical_group([ga]),
                    "groupB": canonical_group([gb]),
                    "reference": reference,
                    "filters": merge_filters(base, [_filter_for(var_meta[z], v)]),
                    "nA": za[v],
                    "nB": zb[v],
                    "notes": [n for n in [_low_note(za[v], zb[v])] if n] + [f"stratum of the contrast above: {zname} = {_label(v)}"],
                    "stratum": {"variableId": z, "displayName": zname, "label": _label(v)},
                })
        out.append({
            "comparator": _comparator(meta),
            "groupA": canonical_group([ga]),
            "groupB": canonical_group([gb]),
            "reference": reference,
            "filters": list(base),
            "nA": len(a_ids),
            "nB": len(b_ids),
            "notes": notes,
            "stratum": None,
        })
        out.extend(strata)
    return out


def _label(v):
    return _fmt(v) if isinstance(v, float) else str(v)


def enumerate_contrasts(rows, var_meta, base_filters=(), only_vars=None, max_candidates=MAX_CANDIDATES):
    """Deterministic candidates; the agent ranks them. Order: fewest levels first,
    categorical before numeric, featured first, then display name. At most
    max_candidates are returned (None = no cap); `truncated` says how many exist."""
    base = canonical_filters(base_filters)
    prof = {vid: _profile(rows, m) for vid, m in var_meta.items()}

    def order(vid):
        m = var_meta[vid]
        return (len(prof[vid]["usable"]), m.get("type") in NUMERIC_TYPES, not m.get("featured"), m.get("displayName", ""), vid)

    skipped, aliases, comparators = [], [], []
    for vid in sorted(var_meta, key=order):
        m, p = var_meta[vid], prof[vid]
        if p["reason"]:
            if not only_vars or vid in only_vars:
                entry = {"variableId": vid, "displayName": m["displayName"], "reason": p["reason"]}
                levels = [[e["label"], len(ids)] for e, ids in p["usable"]] + [[label, n] for label, n in p["excluded"]]
                if levels and not p["identifier"]:
                    entry["levels"] = levels
                skipped.append(entry)
            continue
        twin = next((c for c in comparators if aliased(rows, c, vid)), None)
        if twin:
            aliases.append({"variableId": vid, "displayName": m["displayName"], "sameAs": twin, "sameAsName": var_meta[twin]["displayName"]})
            continue
        comparators.append(vid)
    # aliases are found over all variables, so --vars cannot change what counts as an
    # alias; an alias named explicitly in --vars is still offered as a comparator
    alias_ids = {a["variableId"] for a in aliases}
    selected = comparators
    if only_vars:
        selected = [v for v in sorted(var_meta, key=order) if v in only_vars and (v in comparators or v in alias_ids)]
    candidates = []
    for vid in selected:
        for cand in _pair_candidates(rows, var_meta, prof, vid, base, aliases):
            cand["index"] = len(candidates) + 1
            candidates.append(cand)
    # Z nested within X: every Z level sits inside one X level (e.g. sample label within condition)
    nested = [
        {"variableId": z, "displayName": var_meta[z]["displayName"], "within": vid, "withinName": var_meta[vid]["displayName"]}
        for vid in selected
        for z in comparators
        if z != vid and determines(rows, z, vid) and not aliased(rows, z, vid)
    ]
    truncated = None
    if max_candidates is not None and len(candidates) > max_candidates:
        truncated = {"shown": max_candidates, "total": len(candidates)}
        candidates = candidates[:max_candidates]
    return {"candidates": candidates, "skipped": skipped, "aliases": aliases, "nested": nested, "truncated": truncated}


def load_contrast(obj, var_meta, var_entities, chain, base_filters=()):
    """Validate a contrast file: {"comparator": {"variableId", "entityId"?}, "groupA", "groupB", "filters"?}."""
    if not isinstance(obj, dict):
        raise ContrastError("a contrast file holds one JSON object: {comparator, groupA, groupB, filters?}")
    vid = (obj.get("comparator") or {}).get("variableId")
    if vid not in var_meta:
        if vid in var_entities:
            raise ContrastError(
                f"comparator {vid} sits on {var_entities[vid]}, which is not a parent of the expression "
                f"entity; the notebook only offers comparators on {', '.join(chain)}"
            )
        hint = difflib.get_close_matches(str(vid), list(var_meta), n=3, cutoff=0.5)
        raise ContrastError(f"unknown comparator variable {vid!r}; did you mean {hint}?")
    m = var_meta[vid]
    numeric = m.get("type") in NUMERIC_TYPES
    groups = {}
    for key in ("groupA", "groupB"):
        group = canonical_group(obj.get(key) or [])
        if not group:
            raise ContrastError(f"{key} is empty")
        if numeric and any("min" not in g or "max" not in g for g in group):
            raise ContrastError(f"{key}: numeric comparator {vid} needs min and max on every entry (bins are [min, max))")
        vocab = m.get("vocabulary")
        if vocab and not numeric:
            bad = [g["label"] for g in group if g["label"] not in vocab]
            if bad:
                hints = {b: difflib.get_close_matches(b, vocab, n=2, cutoff=0.5) for b in bad}
                raise ContrastError(f"unknown {m['displayName']} label(s) {bad}; did you mean {hints}? vocabulary: {vocab}")
        groups[key] = group
    return {
        "comparator": _comparator(m),
        "groupA": groups["groupA"],
        "groupB": groups["groupB"],
        "filters": merge_filters(base_filters, obj.get("filters") or []),
        "reference": "contrast file",
        "notes": [],
        "stratum": None,
    }
```

- [ ] **Step 4: Run the tests**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_contrasts_enum.py tests/test_contrasts_canonical.py -q`
Expected: PASS. If `test_indices_are_contiguous_and_deterministic` fails, the cause is dict/set iteration order leaking into the output: sort it, don't relax the test.

- [ ] **Step 5: Commit**

```bash
git add veupathdb_database/scripts/_contrasts.py veupathdb_database/tests/test_contrasts_enum.py
git commit -m "feat(eda): contrast enumeration with aliasing, confounding and stratified suggestions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: `eda.py contrasts` with cache status

**Files:**
- Modify: `veupathdb_database/scripts/_contrasts.py` (append `render_contrasts`)
- Modify: `veupathdb_database/scripts/eda.py` (add `contrast_setup`, `cmd_contrasts`, parser entry, `_contrast_args`)
- Test: `veupathdb_database/tests/test_eda_cli_contrasts.py`

**Interfaces:**
- Consumes: `_eda.compute_status`; Task 6–7 `_contrasts` functions; `eda.sample_view`, `load_target`, `read_filters`
- Produces:
  - `eda.contrast_setup(args, t, filters) -> (view, value_var, method, notes)` (raises `EdaError` when there is no joint table)
  - `eda._contrast_args(sp)` adds `--value-var`, `--method {auto,DESeq,limma}`, `--vars`
  - `_contrasts.render_contrasts(out) -> list[str]`
  - `contrasts --json` output: `{"datasetId", "valueVariable", "method", "notes", "candidates": [... + "cache": {"status", "jobId"}], "skipped", "aliases", "nested", "truncated"}`

- [ ] **Step 1: Write the failing tests**

Create `veupathdb_database/tests/test_eda_cli_contrasts.py`:

```python
import json

import httpx
import pytest
from eda_helpers import eda_fixture


def _temp(cands):
    return next(c for c in cands if c["comparator"]["variableId"] == "VAR_081ab087" and c["stratum"] is None)


def test_contrasts_json_proposes_febrile_vs_normal(run_eda, eda_mock):
    out = json.loads(run_eda("contrasts", "plasmodb", "DS_e973eadd57", "--json"))
    assert out["valueVariable"] == "SEQUENCE_READ_COUNT_SENSE"
    assert out["method"] == "DESeq"
    assert any("SEQUENCE_READ_COUNT_ANTISENSE" in n for n in out["notes"])
    temp = _temp(out["candidates"])
    assert temp["groupA"] == [{"label": "normal"}] and temp["groupB"] == [{"label": "febrile"}]
    assert (temp["nA"], temp["nB"]) == (6, 6)
    assert temp["cache"] == {"status": "complete", "jobId": eda_mock.de_job}
    bodies = eda_mock.compute_bodies("differentialexpression")
    assert bodies[temp["index"] - 1] == eda_fixture("jobs.json")["de_heatshock"]["body"]


def test_cache_checks_never_start_jobs_and_are_capped(run_eda, eda_mock):
    out = json.loads(run_eda("contrasts", "plasmodb", "DS_e973eadd57", "--json"))
    checks = [q for m, p, q, b in eda_mock.requests if p == "/computes/differentialexpression"]
    assert checks and all(q == {"autostart": "false"} for q in checks)
    assert len(checks) == min(30, len(out["candidates"]))
    beyond = [c for c in out["candidates"] if c["index"] > 30]
    assert all(c["cache"]["status"] == "not checked" and len(c["cache"]["jobId"]) == 32 for c in beyond)


def test_contrasts_text(run_eda):
    out = run_eda("contrasts", "plasmodb", "DS_e973eadd57")
    assert "temperature_condition: normal (n=6) → febrile (n=6)" in out
    assert "[complete]" in out
    assert "groupA is the reference" in out


def test_value_var_and_vars_options(run_eda):
    out = json.loads(run_eda("contrasts", "plasmodb", "DS_e973eadd57", "--json",
                             "--value-var", "SEQUENCE_READ_COUNT_ANTISENSE", "--vars", "VAR_081ab087"))
    assert out["valueVariable"] == "SEQUENCE_READ_COUNT_ANTISENSE"
    assert {c["comparator"]["variableId"] for c in out["candidates"]} == {"VAR_081ab087"}


def test_contrasts_refuse_without_joint_table(run_eda, eda_mock, capsys):
    path = f"/studies/{eda_mock.STUDY}/entities/{eda_mock.SAMPLE}/count"
    eda_mock.routes[("POST", path)] = lambda r: httpx.Response(200, json={"count": 6000})
    with pytest.raises(SystemExit):
        run_eda("contrasts", "plasmodb", "DS_e973eadd57")
    assert "--filters" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_cli_contrasts.py -q`
Expected: FAIL with `argparse` error `invalid choice: 'contrasts'` (SystemExit 2).

- [ ] **Step 3: Implement**

Append to `_contrasts.py`:

```python
def _labels(group):
    return "+".join(g["label"] for g in group)


def render_contrasts(out):
    lines = [
        f"{out['datasetId']}  value={out['valueVariable']}  method={out['method']}  "
        f"{len(out['candidates'])} candidates (groupA is the reference: positive log2FC = higher in groupB; "
        "the suggested reference is a hint, and you decide)"
    ]
    if out.get("truncated"):
        tr = out["truncated"]
        lines.append(f"note: showing the first {tr['shown']} of {tr['total']} candidates; narrow with --vars")
    lines += [f"note: {n}" for n in out["notes"]]
    for c in out["candidates"]:
        where = f"  | {c['stratum']['displayName']} = {c['stratum']['label']}" if c.get("stratum") else ""
        cache = (c.get("cache") or {}).get("status", "")
        lines.append(
            f"{c['index']:>3}  {c['comparator']['displayName']}: {_labels(c['groupA'])} (n={c['nA']}) → "
            f"{_labels(c['groupB'])} (n={c['nB']}){where}  [{cache}]"
        )
        lines += [f"       - {n}" for n in c["notes"]]
    for a in out["aliases"]:
        lines.append(f"aliased: {a['displayName']} ({a['variableId']}) groups samples exactly like {a['sameAsName']} ({a['sameAs']})")
    for n in out.get("nested", []):
        lines.append(f"nested: each {n['displayName']} ({n['variableId']}) level lies within one {n['withinName']} level")
    for s in out["skipped"]:
        levels = ""
        if s.get("levels"):
            levels = ": " + ", ".join(f"{label} ({n})" for label, n in s["levels"][:12])
        lines.append(f"skipped {s['displayName']} ({s['variableId']}): {s['reason']}{levels}")
    lines.append(
        "[complete] = already computed (free, and a hint that website users ran it). "
        "Next: eda.py de SITE DS --contrast N with the same --filters/--vars/--value-var."
    )
    return lines
```

In `eda.py`, add after `other_entities`:

```python
def contrast_setup(args, t, filters):
    """Shared by contrasts/de/de-spec: sample view, value variable, method, notes."""
    from _contrasts import choose_method, choose_value_var
    from _eda import EdaError
    from _samples import MAX_TABULAR_ROWS

    view = sample_view(t, filters)
    if view["table"] is None:
        raise EdaError(
            f"{', '.join(view['too_big'])} has more than {MAX_TABULAR_ROWS} records; contrasts need "
            "the joint sample table. Narrow it with --filters."
        )
    value_var, vnote = choose_value_var(t["expr"], getattr(args, "value_var", None))
    method, mnote = choose_method(t["notebook"], value_var, getattr(args, "method", "auto"))
    return view, value_var, method, [n for n in (vnote, mnote) if n]


def _only_vars(args):
    return set(args.vars.split(",")) if getattr(args, "vars", None) else None


def cmd_contrasts(args) -> None:
    from _contrasts import (
        MAX_CACHE_CHECKS,
        PLUGIN_DE,
        compute_body,
        de_config,
        enumerate_contrasts,
        job_id,
        render_contrasts,
    )
    from _eda import compute_status

    t = load_target(args)
    filters = read_filters(args, t)
    view, value_var, method, notes = contrast_setup(args, t, filters)
    result = enumerate_contrasts(view["table"]["rows"], view["meta"], filters, _only_vars(args))
    for cand in result["candidates"]:
        cfg = de_config(t["expr"]["entityId"], value_var, cand["comparator"], cand["groupA"], cand["groupB"], method)
        body = compute_body(t["dataset"]["studyId"], cfg, cand["filters"])
        if cand["index"] <= MAX_CACHE_CHECKS:
            st = compute_status(t["client"], PLUGIN_DE, body, start=False)
            cand["cache"] = {"status": st["status"], "jobId": st["jobID"]}
        else:
            cand["cache"] = {"status": "not checked", "jobId": job_id(PLUGIN_DE, body)}
    out = {"datasetId": t["dataset"]["datasetId"], "valueVariable": value_var, "method": method, "notes": notes, **result}
    if args.json:
        emit(out)
    else:
        print("\n".join(render_contrasts(out)))
```

Add after `_target_args`:

```python
def _contrast_args(sp):
    sp.add_argument("--value-var", help="expression value variable (default: unstranded counts, else sense, else intensity)")
    sp.add_argument("--method", default="auto", choices=["auto", "DESeq", "limma"],
                    help="auto = the website's method for this search family")
    sp.add_argument("--vars", help="comma-separated comparator variable ids to consider")
```

In `build_parser`, before `return p`:

```python
    sp = sub.add_parser("contrasts", help="canonical candidate contrasts with replicate counts and cache status")
    _target_args(sp)
    _contrast_args(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_contrasts)
```

- [ ] **Step 4: Run the tests**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_cli_contrasts.py -q`
Expected: PASS.

- [ ] **Step 5: Try it live once (needs a token)**

Run: `cd veupathdb_database && uv run scripts/eda.py contrasts plasmodb DS_e973eadd57 | head -30`
Expected: the `temperature_condition: normal (n=6) → febrile (n=6)` line marked `[complete]`, followed by its three strain strata.

- [ ] **Step 6: Commit**

```bash
git add veupathdb_database/scripts/_contrasts.py veupathdb_database/scripts/eda.py veupathdb_database/tests/test_eda_cli_contrasts.py
git commit -m "feat(eda): eda.py contrasts with shared-cache status checks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Threshold logic and DE result shaping

**Files:**
- Create: `veupathdb_database/scripts/_de.py`
- Test: `veupathdb_database/tests/test_de.py`

**Interfaces:**
- Consumes: `_eda.EdaError`; `_contrasts.METHODS`, `PLUGIN_DE`, `PLUGIN_PCA`, `canonical_filters`
- Produces (in `_de`):
  - `DIRECTIONS`, `DEFAULT_THRESHOLDS = "1,0.05,upAndDown"`, `class SpecError(EdaError)`
  - `java_double(value) -> float | None`
  - `negate_effects(statistics) -> statistics` (mirror contrast: effectSize negated, everything else unchanged)
  - `parse_thresholds(text) -> (fc: float, p: float, direction: str)` (raises `EdaError`)
  - `is_retained(effect_size, p_value, fc, p, direction) -> bool`
  - `wdk_step_genes(statistics, thresholds) -> list[str]`
  - `de_table(statistics) -> list[{"gene", "effectSize", "pValue", "adjustedPValue"}]` (finite floats or None)
  - `summarise(statistics, thresholds, top_n=10) -> {"tested", "padj_na", "passing_raw_p", "wdk_step_genes", "wdk_dropped_gene", "passing_padj", "passing_raw_genes", "top_up", "top_down"}`
  - `gene_rows(table, genes) -> list[row + "status"]`
  - `de_json(context, provenance, summary, table, genes=()) -> {"context", "provenance", "identity", "rows"}`
  - `table_tsv(table) -> str`
  - `render_de(context, provenance, summary, gene_count=None, genes=None, next_hint=None) -> list[str]`

- [ ] **Step 1: Write the failing tests**

Create `veupathdb_database/tests/test_de.py`:

```python
import json
import math

import pytest


def stat(gene, es, p, padj="0.5"):
    return {"pointID": gene, "effectSize": es, "pValue": p, "adjustedPValue": padj}


def test_java_double_matches_java_parsing():
    from _de import java_double

    assert java_double("1.5") == 1.5
    assert java_double(" -2e-3 ") == -0.002
    assert java_double("1e-200") == 1e-200
    assert java_double("1.0d") == 1.0
    assert java_double(3) == 3.0
    assert math.isnan(java_double("NaN"))
    assert java_double("Infinity") == math.inf and java_double("-Infinity") == -math.inf
    for bad in ("NA", "nan", "inf", "Inf", "", "null", None, "1,5", True):
        assert java_double(bad) is None, bad


def test_is_retained_ports_plugin():
    from _de import is_retained

    assert is_retained("1.0", "0.05", 1, 0.05, "upAndDown")  # both bounds inclusive
    assert is_retained("-1.0", "0.05", 1, 0.05, "upAndDown")
    assert not is_retained("0.99", "0.01", 1, 0.05, "upAndDown")
    assert not is_retained("2", "0.051", 1, 0.05, "upAndDown")
    assert is_retained("2", "-0.01", 1, 0.05, "upAndDown")  # the plugin takes |p|
    assert is_retained("2", "0.01", 1, 0.05, "upOnly") and not is_retained("-2", "0.01", 1, 0.05, "upOnly")
    assert is_retained("-2", "0.01", 1, 0.05, "downOnly") and not is_retained("2", "0.01", 1, 0.05, "downOnly")
    assert not is_retained("0", "1", 0, 1, "upOnly")
    for es, p in (("NA", "0.01"), ("NaN", "0.01"), ("2", None), ("2", "NaN")):
        assert not is_retained(es, p, 0, 1, "upAndDown")


def test_parse_thresholds():
    from _de import parse_thresholds
    from _eda import EdaError

    assert parse_thresholds("1,0.05") == (1.0, 0.05, "upAndDown")
    assert parse_thresholds("0.5, 0.01, upOnly") == (0.5, 0.01, "upOnly")
    for bad in ("1", "a,0.05", "1,0", "1,1.5", "-1,0.05", "1,0.05,up"):
        with pytest.raises(EdaError):
            parse_thresholds(bad)


def test_wdk_step_skips_first_statistics_row():
    from _de import summarise, wdk_step_genes

    stats = [stat("G1", "3", "0.001"), stat("G2", "3", "0.001"), stat("G3", "0.1", "0.9")]
    th = (1.0, 0.05, "upAndDown")
    assert wdk_step_genes(stats, th) == ["G2"]
    s = summarise(stats, th)
    assert (s["passing_raw_p"], s["wdk_step_genes"], s["wdk_dropped_gene"]) == (2, 1, "G1")
    s = summarise(list(reversed(stats)), th)
    assert (s["passing_raw_p"], s["wdk_step_genes"], s["wdk_dropped_gene"]) == (2, 2, None)


def test_summarise_counts_and_tops():
    from _de import summarise

    stats = [
        stat("G0", "0.1", "0.9", "0.95"),
        stat("G1", "3", "0.001", "0.01"),
        stat("G2", "-2", "0.001", "0.02"),
        stat("G3", "4", "0.01", "0.2"),
        stat("G4", "5", "0.001", None),
        stat("G5", "NA", "NA", None),
    ]
    s = summarise(stats, (1.0, 0.05, "upAndDown"))
    assert s["tested"] == 6 and s["padj_na"] == 2
    assert s["passing_raw_p"] == 4 and s["passing_raw_genes"] == ["G1", "G2", "G3", "G4"]
    assert s["wdk_step_genes"] == 4 and s["wdk_dropped_gene"] is None
    assert s["passing_padj"] == 2
    assert [r["gene"] for r in s["top_up"]] == ["G1"]
    assert [r["gene"] for r in s["top_down"]] == ["G2"]


def test_de_table_is_json_safe():
    from _de import de_table

    rows = de_table([stat("G1", "Infinity", "NaN", None), stat("G2", "1.5", "0.01", "0.02")])
    assert rows[0] == {"gene": "G1", "effectSize": None, "pValue": None, "adjustedPValue": None}
    assert rows[1] == {"gene": "G2", "effectSize": 1.5, "pValue": 0.01, "adjustedPValue": 0.02}
    json.dumps(rows, allow_nan=False)


def test_gene_rows_statuses_case_insensitive():
    from _de import de_table, gene_rows

    table = de_table([stat("PF3D7_0100100", "1", "0.01", "0.02"), stat("PF3D7_0100200", "1", "0.01", None)])
    rows = gene_rows(table, ["pf3d7_0100100", "PF3D7_0100200", "PF3D7_9999999"])
    assert rows[0]["gene"] == "PF3D7_0100100" and rows[0]["status"] == "tested"
    assert "padj NA" in rows[1]["status"]
    assert rows[2]["status"].startswith("not tested") and rows[2]["pValue"] is None


def test_de_json_separates_identity():
    from _de import de_json, de_table, summarise

    stats = [stat("G0", "0.1", "0.9", "0.95"), stat("G1", "3", "0.001", "0.01"), stat("G2", "-2", "0.0001", "0.02")]
    s = summarise(stats, (1.0, 0.05, "upAndDown"))
    out = de_json({"comparator": "temp"}, {"jobId": "j"}, s, de_table(stats), genes=["G0"])
    assert set(out) == {"context", "provenance", "identity", "rows"}
    assert out["identity"] == {"r1": "G2", "r2": "G1", "r3": "G0"}  # ordered by p
    assert out["rows"]["r1"]["effectSize"] == -2.0 and "gene" not in out["rows"]["r1"]
    assert out["context"]["top"] == {"up": ["r2"], "down": ["r1"]}
    assert out["context"]["counts"]["passing_raw_p"] == 2
    blind = json.dumps({k: v for k, v in out.items() if k != "identity"})
    assert "G1" not in blind and "G2" not in blind
    json.dumps(out, allow_nan=False)


def test_negate_effects_flips_sign_only():
    from _de import negate_effects

    stats = [stat("G1", "1.5", "0.01", "0.02"), stat("G2", "-2e-3", "0.5"), stat("G3", "0", "1"), stat("G4", "NA", "NA", None)]
    out = negate_effects(stats)
    assert [s["effectSize"] for s in out] == ["-1.5", "0.002", "0", "NA"]
    assert [(s["pointID"], s["pValue"], s["adjustedPValue"]) for s in out] == [
        (s["pointID"], s["pValue"], s["adjustedPValue"]) for s in stats
    ]
    assert stats[0]["effectSize"] == "1.5"  # input untouched


def test_table_tsv():
    from _de import de_table, table_tsv

    text = table_tsv(de_table([stat("G1", "1.5", "0.01", None)]))
    assert text == "gene\teffectSize\tpValue\tadjustedPValue\nG1\t1.5\t0.01\tNA\n"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_de.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named '_de'`.

- [ ] **Step 3: Implement**

Create `veupathdb_database/scripts/_de.py`:

```python
"""DE result shaping, the WSF plugin's threshold logic, and the eda_analysis_spec
builder (pure functions; no I/O)."""
import difflib
import json
import math
import re

from _contrasts import METHODS, PLUGIN_DE, PLUGIN_PCA, canonical_filters
from _eda import EdaError

DIRECTIONS = ("upAndDown", "upOnly", "downOnly")
DEFAULT_THRESHOLDS = "1,0.05,upAndDown"
_JAVA_DOUBLE = re.compile(r"[+-]?(NaN|Infinity|(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?[fFdD]?)")


class SpecError(EdaError):
    pass


def java_double(value):
    """Parse like Java Double.valueOf, which the plugin uses; None where Java throws.
    (Python's float() also takes 'nan', 'inf' and 'NA'-free spellings Java rejects.)"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not _JAVA_DOUBLE.fullmatch(s):
        return None
    return float(s.rstrip("fFdD"))


def negate_effects(statistics):
    """Statistics of the mirror contrast (groupA and groupB swapped): with a two-level
    ~comparator design and no shrinkage, DESeq2 results() and limma topTable(coef=2)
    give the same p and padj with effectSize negated. Unparseable values pass through."""
    out = []
    for s in statistics:
        x = java_double(s.get("effectSize"))
        if x is not None and math.isfinite(x):
            s = {**s, "effectSize": repr(-x) if x else s["effectSize"]}
        out.append(s)
    return out


def parse_thresholds(text):
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) not in (2, 3):
        raise EdaError("--thresholds expects FC,P[,upAndDown|upOnly|downOnly], e.g. 1,0.05")
    try:
        fc, p = float(parts[0]), float(parts[1])
    except ValueError:
        raise EdaError(f"--thresholds: FC and P must be numbers, got {text!r}") from None
    direction = parts[2] if len(parts) == 3 else "upAndDown"
    if direction not in DIRECTIONS:
        hint = difflib.get_close_matches(direction, DIRECTIONS, n=1, cutoff=0.3)
        raise EdaError(f"--thresholds direction {direction!r}; did you mean {hint}? one of {list(DIRECTIONS)}")
    if fc < 0 or not 0 < p <= 1:
        raise EdaError("--thresholds: FC must be >= 0 and P in (0, 1]")
    return fc, p, direction


def is_retained(effect_size, p_value, fc, p, direction):
    """Exact port of GeneEdaVizWithComputePlugin.isRetainedRow: raw p, inclusive bounds."""
    raw, pv = java_double(effect_size), java_double(p_value)
    if raw is None or pv is None:
        return False
    if not (abs(pv) <= p and abs(raw) >= fc):
        return False
    if direction == "upOnly":
        return raw > 0
    if direction == "downOnly":
        return raw < 0
    return True


def wdk_step_genes(statistics, thresholds):
    """Genes the WDK step returns. The plugin writes the statistics with no header line,
    then skips the first line as if it were one (AbstractEdaGenesPlugin.execute), so
    statistics[0] never reaches the step. Verified live: 5510 retained -> 5509 returned."""
    fc, p, direction = thresholds
    return [
        s.get("pointID")
        for s in statistics[1:]
        if is_retained(s.get("effectSize"), s.get("pValue"), fc, p, direction)
    ]


def _finite(x):
    return x if x is not None and math.isfinite(x) else None


def de_table(statistics):
    return [
        {
            "gene": s.get("pointID"),
            "effectSize": _finite(java_double(s.get("effectSize"))),
            "pValue": _finite(java_double(s.get("pValue"))),
            "adjustedPValue": _finite(java_double(s.get("adjustedPValue"))),
        }
        for s in statistics
    ]


def summarise(statistics, thresholds, top_n=10):
    fc, p, direction = thresholds
    table = de_table(statistics)
    raw = [
        s.get("pointID")
        for s in statistics
        if is_retained(s.get("effectSize"), s.get("pValue"), fc, p, direction)
    ]
    first = statistics[0] if statistics else None
    dropped = None
    if first and is_retained(first.get("effectSize"), first.get("pValue"), fc, p, direction):
        dropped = first.get("pointID")
    padj = [
        r
        for r in table
        if r["effectSize"] is not None
        and r["adjustedPValue"] is not None
        and is_retained(r["effectSize"], r["adjustedPValue"], fc, p, direction)
    ]
    up = sorted((r for r in padj if r["effectSize"] > 0), key=lambda r: (-r["effectSize"], r["gene"]))[:top_n]
    down = sorted((r for r in padj if r["effectSize"] < 0), key=lambda r: (r["effectSize"], r["gene"]))[:top_n]
    return {
        "tested": len(table),
        "padj_na": sum(1 for r in table if r["adjustedPValue"] is None),
        "passing_raw_p": len(raw),
        "wdk_step_genes": len(raw) - (1 if dropped else 0),
        "wdk_dropped_gene": dropped,
        "passing_padj": len(padj),
        "passing_raw_genes": raw,
        "top_up": up,
        "top_down": down,
    }


def gene_rows(table, genes):
    by_lower = {r["gene"].lower(): r for r in table if r["gene"]}
    out = []
    for g in genes:
        r = by_lower.get(g.lower())
        if r is None:
            out.append({"gene": g, "effectSize": None, "pValue": None, "adjustedPValue": None,
                        "status": "not tested (absent from the output: all-zero counts, or not measured)"})
        elif r["adjustedPValue"] is None:
            out.append({**r, "status": "tested; padj NA (removed by independent filtering, usually low counts)"})
        else:
            out.append({**r, "status": "tested"})
    return out


def de_json(context, provenance, summary, table, genes=()):
    """identity / context / provenance / rows. A blind consumer drops `identity` only;
    row keys are opaque (r1, r2, … in p-value order)."""
    wanted = [r["gene"] for r in summary["top_up"] + summary["top_down"]]
    if summary["wdk_dropped_gene"]:
        wanted.append(summary["wdk_dropped_gene"])
    wanted += list(genes)
    seen, unique = set(), []
    for g in wanted:
        if g.lower() not in seen:
            seen.add(g.lower())
            unique.append(g)
    rows = gene_rows(table, unique)
    rows.sort(key=lambda r: (r["pValue"] if r["pValue"] is not None else 2.0, r["gene"]))
    key_of = {r["gene"]: f"r{i}" for i, r in enumerate(rows, 1)}
    ctx = {
        **context,
        "counts": {k: summary[k] for k in ("tested", "padj_na", "passing_raw_p", "wdk_step_genes", "passing_padj")},
        "top": {
            "up": [key_of[r["gene"]] for r in summary["top_up"]],
            "down": [key_of[r["gene"]] for r in summary["top_down"]],
        },
    }
    if summary["wdk_dropped_gene"]:
        ctx["wdkDroppedRow"] = key_of[summary["wdk_dropped_gene"]]
    return {
        "context": ctx,
        "provenance": provenance,
        "identity": {key_of[r["gene"]]: r["gene"] for r in rows},
        "rows": {key_of[r["gene"]]: {k: v for k, v in r.items() if k != "gene"} for r in rows},
    }


def table_tsv(table):
    lines = ["gene\teffectSize\tpValue\tadjustedPValue"]
    for r in table:
        cells = ["NA" if r[k] is None else repr(r[k]) for k in ("effectSize", "pValue", "adjustedPValue")]
        lines.append("\t".join([r["gene"]] + cells))
    return "\n".join(lines) + "\n"


def _g(x, spec):
    return "NA" if x is None else format(x, spec)


def render_de(context, provenance, summary, gene_count=None, genes=None, next_hint=None):
    a, b, t = context["groupA"], context["groupB"], context["thresholds"]
    lines = [
        f"contrast {provenance['jobId']} (the EDA job id: cite it as the contrast id)",
        f"{provenance['datasetId']} \"{context['study']}\"  {context['method']} on {context['valueVariable']}",
        f"{context['comparator']['variable']}: groupA (reference) {'+'.join(a['labels'])} n={a['n']} → "
        f"groupB {'+'.join(b['labels'])} n={b['n']}; positive log2FC = higher in groupB (unshrunk)",
        f"filters: {json.dumps(context['filters']) if context['filters'] else 'none'}",
    ]
    absent = f" ({gene_count - summary['tested']} genes absent: not tested)" if gene_count else ""
    lines.append(f"tested {summary['tested']} genes{absent}; padj NA: {summary['padj_na']}")
    lines.append(f"thresholds |log2FC| >= {t['effectSize']:g}, raw p <= {t['pValue']:g}, {t['direction']}")
    lines.append(f"passing raw p: {summary['passing_raw_p']}  → the WDK step returns {summary['wdk_step_genes']} genes")
    if summary["wdk_dropped_gene"]:
        lines.append(
            f"  (the WDK plugin drops the first statistics row, {summary['wdk_dropped_gene']}, "
            "which passes: a known upstream quirk)"
        )
    lines.append(f"passing padj: {summary['passing_padj']}")
    for name, rows in (("up", summary["top_up"]), ("down", summary["top_down"])):
        if rows:
            lines.append(
                f"top {name} (passing padj): "
                + ", ".join(f"{r['gene']} {r['effectSize']:+.2f} (padj {r['adjustedPValue']:.2g})" for r in rows)
            )
    lines += [f"note: {n}" for n in context["notes"]]
    if genes:
        lines.append("genes:")
        for r in genes:
            lines.append(
                f"  {r['gene']}: {r['status']}; log2FC {_g(r['effectSize'], '+.3f')} "
                f"p {_g(r['pValue'], '.3g')} padj {_g(r['adjustedPValue'], '.3g')}"
            )
    if next_hint:
        lines.append(next_hint)
    return lines
```

(`METHODS`, `PLUGIN_DE`, `PLUGIN_PCA` and `canonical_filters` are used by Task 11.)

- [ ] **Step 4: Run the tests**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_de.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add veupathdb_database/scripts/_de.py veupathdb_database/tests/test_de.py
git commit -m "feat(eda): plugin-exact threshold logic, WDK first-row quirk, identity-split DE JSON

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: `eda.py de`

**Files:**
- Modify: `veupathdb_database/scripts/eda.py`
- Test: `veupathdb_database/tests/test_eda_cli_de.py`

**Interfaces:**
- Consumes: Tasks 6–9; `_eda.compute_status`, `wait_for_job`, `delete_job`, `volcano`
- Produces (in `eda.py`):
  - `json_arg(raw, flag, expected) -> object` (inline JSON when `raw` starts with `{` or `[`; otherwise a file path, optional leading `@`)
  - `resolve_contrast(args, t, filters, view) -> contrast` (`--contrast N` re-enumerates; otherwise inline JSON or a JSON file)
  - `contrast_counts(t, contrast, base_filters, view) -> (n_a, n_b)`
  - `prepare_de(args) -> {"t", "contrast", "nA", "nB", "valueVar", "method", "config", "body", "notes"}` (Task 11 reuses it)
  - `de_context(p, thresholds) -> dict`
  - `mirror_body(p) -> body` (the same contrast with groupA and groupB swapped)
  - CLI: `de SITE DATASET --contrast N|FILE [--thresholds FC,P[,dir]] [--value-var] [--method] [--vars] [--entity] [--genes IDS] [--rows none|passing|all] [--top N] [--tsv FILE] [--json] [--no-wait] [--retry] [--timeout S] [--no-mirror]`
- **Mirror reuse:** when this orientation's job has never run (`no-such-job`) but the swapped contrast's job is `complete`, `de` reuses the mirror's statistics with `negate_effects` and starts nothing. Provenance keeps this orientation's `jobId` (the contrast id) and adds `statisticsFrom: {"jobId", "negated": true}`; a context note says so and warns that the WDK step for this orientation is not cached. This makes the agent's choice of reference cheap to get "wrong". `--no-mirror` turns it off. A failed or expired job never falls back to the mirror (that is `--retry`'s job).

- [ ] **Step 1: Write the failing tests**

Create `veupathdb_database/tests/test_eda_cli_de.py`:

```python
import json

import httpx
import pytest
from eda_helpers import eda_fixture

TEMP = {"comparator": {"variableId": "VAR_081ab087"}, "groupA": [{"label": "normal"}], "groupB": [{"label": "febrile"}]}


@pytest.fixture
def contrast_file(tmp_path):
    def make(obj=TEMP):
        path = tmp_path / "contrast.json"
        path.write_text(json.dumps(obj))
        return str(path)

    return make


def test_de_text_report(run_eda, eda_mock, contrast_file):
    out = run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file())
    assert f"contrast {eda_mock.de_job}" in out
    assert "groupA (reference) normal n=6 → groupB febrile n=6" in out
    assert "the WDK step returns" in out
    assert "eda.py de-spec plasmodb DS_e973eadd57 --contrast" in out and "--save" in out
    assert "params.json" not in out
    starts = [(q, b) for m, p, q, b in eda_mock.requests if p == "/computes/differentialexpression"]
    assert starts[-1] == ({"autostart": "true"}, eda_fixture("jobs.json")["de_heatshock"]["body"])
    assert any(p.endswith("/volcanoplot") for m, p, q, b in eda_mock.requests)


def test_de_json_counts_and_first_row_quirk(run_eda, eda_mock, contrast_file):
    out = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--json", "--thresholds", "0,1"))
    counts = out["context"]["counts"]
    assert counts["tested"] == len(eda_fixture("volcano_heatshock.json")["statistics"])
    assert counts["wdk_step_genes"] == counts["passing_raw_p"] - 1  # row 0 passes at (0, 1)
    assert out["provenance"]["jobId"] == eda_mock.de_job
    assert out["provenance"]["studyId"] == "STUDY_e973eadd57"
    assert out["context"]["groupA"] == {"labels": ["normal"], "n": 6, "role": "reference"}
    assert out["context"]["thresholds"]["pValueType"].startswith("raw")
    assert "wdkDroppedRow" in out["context"]


def test_de_genes_and_tsv(run_eda, contrast_file, tmp_path):
    first = eda_fixture("volcano_heatshock.json")["statistics"][0]["pointID"]
    tsv = tmp_path / "de.tsv"
    out = run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(),
                  "--genes", f"{first},PF3D7_NOPE", "--tsv", str(tsv))
    assert f"{first}: tested" in out
    assert "PF3D7_NOPE: not tested" in out
    lines = tsv.read_text().splitlines()
    assert lines[0] == "gene\teffectSize\tpValue\tadjustedPValue"
    assert len(lines) == 1 + len(eda_fixture("volcano_heatshock.json")["statistics"])


def test_de_no_wait_does_not_fetch_statistics(run_eda, eda_mock, contrast_file):
    out = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--no-wait"))
    assert out["jobId"] == eda_mock.de_job and out["status"] == "complete"
    assert not any(p.endswith("/volcanoplot") for m, p, q, b in eda_mock.requests)


def test_de_failed_job_and_retry(run_eda, eda_mock, contrast_file, capsys):
    calls = {"n": 0}

    def compute(request):
        if request.url.params.get("autostart") == "false":  # de's status lookup
            return httpx.Response(200, json={"jobID": eda_mock.de_job, "status": "failed"})
        calls["n"] += 1
        status = "failed" if calls["n"] == 1 else "complete"
        return httpx.Response(200, json={"jobID": eda_mock.de_job, "status": status})

    eda_mock.routes[("POST", "/computes/differentialexpression")] = compute
    eda_mock.routes[("DELETE", f"/jobs/{eda_mock.de_job}")] = lambda r: httpx.Response(204)
    with pytest.raises(SystemExit):
        run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file())
    err = capsys.readouterr().err
    assert "failed" in err and "--retry" in err
    calls["n"] = 0
    out = run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--retry")
    assert f"contrast {eda_mock.de_job}" in out
    assert ("DELETE", f"/jobs/{eda_mock.de_job}") in [(m, p) for m, p, q, b in eda_mock.requests]


def test_de_refuses_too_few_replicates(run_eda, contrast_file, capsys):
    obj = {
        "comparator": {"variableId": "VAR_64c65374"},
        "groupA": [{"label": "WT 37C"}],
        "groupB": [{"label": "WT 41C"}],
        "filters": [{"entityId": "ENT_8151325d", "variableId": "VAR_081ab087", "type": "stringSet", "stringSet": ["normal"]}],
    }
    with pytest.raises(SystemExit):
        run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(obj))
    assert "too few replicates" in capsys.readouterr().err


def test_de_inline_contrast_equals_file(run_eda, eda_mock, contrast_file):
    a = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--json"))
    b = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", json.dumps(TEMP), "--json"))
    c = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", "@" + contrast_file(), "--json"))
    assert a == b == c


def test_de_bad_inline_contrast(run_eda, capsys):
    with pytest.raises(SystemExit):
        run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", '{"comparator": ')
    assert "inline JSON is not valid" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", "nope.json")
    assert "file not found" in capsys.readouterr().err


def test_de_bad_contrast_number(run_eda, capsys):
    with pytest.raises(SystemExit):
        run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", "999")
    assert "no such candidate" in capsys.readouterr().err


def test_de_method_override_is_noted(run_eda, contrast_file):
    out = run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--method", "limma")
    assert "separate job" in out and "limma on" in out


def _mirror_routes(eda_mock):
    """normal→febrile has never run (but would start fine); febrile→normal is cached."""
    def compute(request):
        body = json.loads(request.content)
        if body["config"]["comparator"]["groupA"] == [{"label": "normal"}]:
            status = "no-such-job" if request.url.params.get("autostart") == "false" else "complete"
            return httpx.Response(200, json={"jobID": "a" * 32, "status": status})
        return httpx.Response(200, json={"jobID": "b" * 32, "status": "complete"})

    eda_mock.routes[("POST", "/computes/differentialexpression")] = compute


def test_de_reuses_cached_mirror_with_negated_effects(run_eda, eda_mock, contrast_file, tmp_path):
    _mirror_routes(eda_mock)
    tsv = tmp_path / "de.tsv"
    out = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--json", "--tsv", str(tsv)))
    assert out["provenance"]["jobId"] == "a" * 32
    assert out["provenance"]["statisticsFrom"] == {"jobId": "b" * 32, "negated": True}
    assert any("mirror" in n and "WDK step" in n for n in out["context"]["notes"])
    computes = [q for m, p, q, b in eda_mock.requests if p == "/computes/differentialexpression"]
    assert computes and all(q == {"autostart": "false"} for q in computes)  # nothing started
    vol = [b for m, p, q, b in eda_mock.requests if p.endswith("/volcanoplot")]
    assert vol[-1]["computeConfig"]["comparator"]["groupA"] == [{"label": "febrile"}]
    first = eda_fixture("volcano_heatshock.json")["statistics"][0]
    gene, es = tsv.read_text().splitlines()[1].split("\t")[:2]
    assert gene == first["pointID"] and float(es) == -float(first["effectSize"])


def test_de_no_mirror_runs_its_own_job(run_eda, eda_mock, contrast_file):
    _mirror_routes(eda_mock)
    out = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--json", "--no-mirror"))
    assert out["provenance"]["jobId"] == "a" * 32 and out["provenance"]["statisticsFrom"] is None
    bodies = eda_mock.compute_bodies("differentialexpression")
    assert all(b["config"]["comparator"]["groupA"] == [{"label": "normal"}] for b in bodies)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_cli_de.py -q`
Expected: FAIL (`invalid choice: 'de'`).

- [ ] **Step 3: Implement**

Add to `eda.py` after `cmd_contrasts`:

```python
def json_arg(raw, flag, expected):
    """Inline JSON (starts with { or [) or a JSON file path (an optional leading @, as in
    wdk.py). Inline is the default for small objects, so no glue files are needed."""
    from _eda import EdaError

    text = raw.strip()
    if text[:1] in ("{", "["):
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise EdaError(f"{flag}: inline JSON is not valid: {e}") from None
    path = pathlib.Path(text.removeprefix("@")).expanduser()
    if not path.is_file():
        raise EdaError(f"{flag} {raw!r} is not {expected} (file not found: {path})")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise EdaError(f"{flag} file {path} is not valid JSON: {e}") from None


def resolve_contrast(args, t, filters, view):
    from _contrasts import enumerate_contrasts, load_contrast
    from _eda import EdaError
    from _samples import all_var_entities

    spec = args.contrast
    if spec.isdigit():
        out = enumerate_contrasts(view["table"]["rows"], view["meta"], filters, _only_vars(args))
        cands = out["candidates"]
        hit = next((c for c in cands if c["index"] == int(spec)), None)
        if hit is None:
            more = " (the list is capped: narrow it with --vars)" if out["truncated"] else ""
            raise EdaError(
                f"--contrast {spec}: no such candidate (1..{len(cands)}){more}; re-run 'eda.py contrasts' "
                "with the same --filters/--vars/--value-var"
            )
        return hit
    obj = json_arg(spec, "--contrast", "a candidate number, inline JSON or a contrast file")
    return load_contrast(obj, view["meta"], all_var_entities(t["index"]), view["chain"], filters)


def contrast_counts(t, contrast, base_filters, view):
    """Samples per group under the contrast's own filters (strata included)."""
    from _contrasts import canonical_filters, samples_in_group
    from _eda import EdaError

    rows = view["table"]["rows"]
    if contrast["filters"] != canonical_filters(base_filters):
        sub = sample_view(t, contrast["filters"])["table"]
        rows = sub["rows"] if sub else []
    vid = contrast["comparator"]["variableId"]
    a = samples_in_group(rows, vid, contrast["groupA"])
    b = samples_in_group(rows, vid, contrast["groupB"])
    both = sorted(set(a) & set(b))
    if both:
        raise EdaError(f"samples fall in both groups: {both[:5]}")
    return len(a), len(b)


def prepare_de(args):
    """Everything de and de-spec share, so de-spec's config is exactly what de hashed."""
    from _contrasts import compute_body, de_config, replicate_check

    t = load_target(args)
    filters = read_filters(args, t)
    view, value_var, method, notes = contrast_setup(args, t, filters)
    contrast = resolve_contrast(args, t, filters, view)
    n_a, n_b = contrast_counts(t, contrast, filters, view)
    rnote = replicate_check(n_a, n_b)
    if rnote:
        notes.append(rnote)
    cfg = de_config(t["expr"]["entityId"], value_var, contrast["comparator"], contrast["groupA"], contrast["groupB"], method)
    body = compute_body(t["dataset"]["studyId"], cfg, contrast["filters"])
    return {"t": t, "contrast": contrast, "nA": n_a, "nB": n_b, "valueVar": value_var,
            "method": method, "config": cfg, "body": body, "notes": notes}


def de_context(p, thresholds):
    c, ds = p["contrast"], p["t"]["dataset"]
    fc, pv, direction = thresholds
    a = [g["label"] for g in c["groupA"]]
    b = [g["label"] for g in c["groupB"]]
    return {
        "study": ds["displayName"],
        "description": ds["description"],
        "comparator": {"variable": c["comparator"]["displayName"], "variableId": c["comparator"]["variableId"],
                       "entityId": c["comparator"]["entityId"]},
        "groupA": {"labels": a, "n": p["nA"], "role": "reference"},
        "groupB": {"labels": b, "n": p["nB"], "role": "comparison"},
        "orientation": f"positive effectSize = higher in groupB ({'+'.join(b)}) than groupA ({'+'.join(a)}); "
                       "unshrunk log2 fold change",
        "method": p["method"],
        "valueVariable": p["valueVar"],
        "filters": c["filters"],
        "thresholds": {"effectSize": fc, "pValue": pv, "direction": direction,
                       "pValueType": "raw (as the website volcano plot and the WDK step)"},
        "notes": p["notes"] + list(c.get("notes") or []),
    }


def mirror_body(p):
    """The same contrast with groupA and groupB swapped: a different job, same statistics
    with effectSize negated (see _de.negate_effects)."""
    from _contrasts import compute_body, de_config

    c = p["contrast"]
    cfg = de_config(p["t"]["expr"]["entityId"], p["valueVar"], c["comparator"], c["groupB"], c["groupA"], p["method"])
    return compute_body(p["t"]["dataset"]["studyId"], cfg, c["filters"])


def _next_hint(p, args):
    import shlex

    return (
        f"next (same --filters/--vars/--value-var): eda.py de-spec {args.site} {args.dataset} "
        f"--contrast {shlex.quote(args.contrast)} --thresholds {args.thresholds} --save, then use the "
        "printed \"leaf\" in wdk.py create-strategy --spec (no file of your own needed)"
    )


def cmd_de(args) -> None:
    from _client import WDKError
    from _contrasts import PLUGIN_DE
    from _de import de_json, de_table, gene_rows, negate_effects, parse_thresholds, render_de, summarise, table_tsv
    from _eda import EdaError, compute_status, delete_job, volcano, wait_for_job

    thresholds = parse_thresholds(args.thresholds)
    p = prepare_de(args)
    t, body = p["t"], p["body"]
    c = t["client"]
    if args.no_wait:
        st = compute_status(c, PLUGIN_DE, body, start=True)
        emit({"jobId": st["jobID"], "status": st["status"],
              "next": "re-run without --no-wait to fetch results (the job keeps running server-side)"})
        return
    mirror = None
    if not args.no_mirror:
        st = compute_status(c, PLUGIN_DE, body, start=False)
        if st["status"] == "no-such-job":
            mbody = mirror_body(p)
            mst = compute_status(c, PLUGIN_DE, mbody, start=False)
            if mst["status"] == "complete":
                mirror = {"jobId": mst["jobID"], "negated": True}
    if mirror:
        stats = negate_effects(volcano(c, mbody)["statistics"])
        p["notes"].append(
            f"statistics reused from the cached mirror job {mirror['jobId']} (groups swapped), effect sizes "
            "negated; p-values are unchanged by the swap. The WDK step for this orientation is not cached: "
            "creating it starts its own job (the first answer is HTTP 202)"
        )
    else:
        st = wait_for_job(c, PLUGIN_DE, body, timeout_s=args.timeout, log=log)
        if st["status"] in ("failed", "expired") and args.retry:
            if st["status"] == "failed":
                try:
                    delete_job(c, st["jobID"])
                except WDKError as e:
                    log(f"could not delete failed job {st['jobID']}: {e}")
            st = wait_for_job(c, PLUGIN_DE, body, timeout_s=args.timeout, log=log)
        if st["status"] != "complete":
            hint = ""
            if st["status"] == "failed":
                hint = (" A job that fails quickly usually means a bad config (e.g. identifier and value "
                        "variables on different entities).")
            raise EdaError(f"job {st['jobID']} is {st['status']}.{hint} --retry resubmits it.")
        stats = volcano(c, body)["statistics"]
    table = de_table(stats)
    summary = summarise(stats, thresholds, top_n=args.top)
    context = de_context(p, thresholds)
    provenance = {"site": t["site"], "datasetId": t["dataset"]["datasetId"], "studyId": t["dataset"]["studyId"],
                  "plugin": PLUGIN_DE, "jobId": st["jobID"], "statisticsFrom": mirror, "search": t["search"]}
    genes = [g.strip() for g in args.genes.split(",") if g.strip()] if args.genes else []
    if args.tsv:
        pathlib.Path(args.tsv).write_text(table_tsv(table), encoding="utf-8")
        log(f"wrote {len(table)} rows to {args.tsv}")
    if args.json:
        extra = list(genes)
        if args.rows == "passing":
            extra += summary["passing_raw_genes"]
        elif args.rows == "all":
            extra += [r["gene"] for r in table]
        emit(de_json(context, provenance, summary, table, extra))
        return
    lines = render_de(context, provenance, summary, t["expr"]["geneCount"],
                      gene_rows(table, genes) if genes else None, _next_hint(p, args))
    print("\n".join(lines))
```

Add after `_contrast_args`:

```python
def _de_args(sp):
    from _de import DEFAULT_THRESHOLDS

    sp.add_argument("--contrast", required=True,
                    help="candidate number from 'contrasts', inline contrast JSON, or a contrast JSON file")
    sp.add_argument("--thresholds", default=DEFAULT_THRESHOLDS,
                    help="FC,P[,upAndDown|upOnly|downOnly]: |log2FC| >= FC and raw p <= P (website defaults)")
```

In `build_parser`, before `return p`:

```python
    sp = sub.add_parser("de", help="run (or reuse) DESeq2/limma for one contrast and summarise the result")
    _target_args(sp)
    _contrast_args(sp)
    _de_args(sp)
    sp.add_argument("--genes", help="comma-separated gene ids to report (absent = not tested)")
    sp.add_argument("--rows", choices=["none", "passing", "all"], default="none",
                    help="--json: which gene rows to include besides the top lists")
    sp.add_argument("--top", type=int, default=10, help="top up/down genes by effect size among padj passers")
    sp.add_argument("--tsv", help="write the full table (gene, effectSize, pValue, adjustedPValue)")
    sp.add_argument("--json", action="store_true", help="identity/context/provenance/rows JSON")
    sp.add_argument("--no-wait", action="store_true", help="start the job and report its status only")
    sp.add_argument("--retry", action="store_true", help="resubmit a failed or expired job")
    sp.add_argument("--timeout", type=int, default=900, help="seconds to wait for the job (default 900)")
    sp.add_argument("--no-mirror", action="store_true",
                    help="never reuse the cached swapped-groups job; always run this orientation")
    sp.set_defaults(func=cmd_de)
```

- [ ] **Step 4: Run the tests and the suite**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_cli_de.py -q && uv run --with pytest --with httpx python -m pytest tests -q`
Expected: PASS.

- [ ] **Step 5: Try it live (needs a token)**

Run: `cd veupathdb_database && uv run scripts/eda.py de plasmodb DS_e973eadd57 --contrast '{"comparator": {"variableId": "VAR_081ab087"}, "groupA": [{"label": "normal"}], "groupB": [{"label": "febrile"}]}'`
Expected: `contrast db04204e5386396e1ca2cb78469ab6fb`, `passing raw p: 1543  → the WDK step returns 1543 genes`, returned at once because the job is cached.

- [ ] **Step 6: Commit**

```bash
git add veupathdb_database/scripts/eda.py veupathdb_database/tests/test_eda_cli_de.py
git commit -m "feat(eda): eda.py de: run or reuse a contrast, re-threshold locally, report

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Analysis-spec builder and `eda.py de-spec`

**Files:**
- Modify: `veupathdb_database/scripts/_de.py` (append)
- Modify: `veupathdb_database/scripts/_client.py` (append `stash_json`)
- Modify: `veupathdb_database/scripts/eda.py`
- Test: `veupathdb_database/tests/test_de_spec.py`

**Interfaces:**
- Consumes: `eda.prepare_de` (Task 10), `_contrasts.pca_config`, `job_id`
- Produces (in `_de`):
  - `build_spec(dataset_id, display_name, filters, de_cfg, pca_cfg, thresholds) -> dict` (what the website saves in `eda_analysis_spec`)
  - `find_volcano_computation(computations) -> dict | None` (port of the plugin's `findVolcanoComputation`)
  - `validate_spec(spec, dataset_id) -> None` (raises `SpecError`)
  - `wdk_params(spec) -> {"eda_dataset_id": DS, "eda_analysis_spec": compact JSON string}`
  - CLI: `de-spec SITE DATASET --contrast … [--thresholds …] [--format spec|params] [--save]` → JSON on stdout; the DE job id on stderr
- Produces (in `_client`): `stash_json(kind, data) -> pathlib.Path`: writes `EDA_CACHE_DIR/{kind}/{sha256 of the canonical JSON, first 16 hex}.json` by temp file + `os.replace` (atomic; parallel writers of the same content are harmless), refreshes the mtime, and prunes files in that directory older than `CACHE_TTL_S`. Returns the absolute path.
- `--save` writes the WDK params with `stash_json("params", …)` and prints `{"paramsFile": PATH, "leaf": {"search": SEARCH, "params": "@PATH"}}`, ready to drop into a `wdk.py create-strategy --spec` tree. Glue files therefore never land in the user's working directory and never clobber each other. Plain `--format params` (stdout) stays for users who want their own copy.

- [ ] **Step 1: Write the failing tests**

Create `veupathdb_database/tests/test_de_spec.py`:

```python
import copy
import json

import pytest

DE_CFG = {
    "identifierVariable": {"entityId": "G", "variableId": "VEUPATHDB_GENE_ID"},
    "valueVariable": {"entityId": "G", "variableId": "SEQUENCE_READ_COUNT"},
    "comparator": {"variable": {"entityId": "S", "variableId": "V"}, "groupA": [{"label": "a"}], "groupB": [{"label": "b"}]},
    "differentialExpressionMethod": "DESeq",
    "pValueFloor": "1e-200",
}
PCA_CFG = {"identifierVariable": DE_CFG["identifierVariable"], "valueVariable": DE_CFG["valueVariable"], "dataFormat": "rawCounts"}


def _spec():
    from _de import build_spec

    return build_spec("DS_x", "Study: b vs a", [], DE_CFG, PCA_CFG, (1.0, 0.05, "upAndDown"))


def test_build_spec_shape():
    from _de import find_volcano_computation, validate_spec

    spec = _spec()
    assert spec["studyId"] == "DS_x" and spec["isPublic"] is False
    assert spec["descriptor"]["subset"] == {"descriptor": [], "uiSettings": {}}
    assert [c["computationId"] for c in spec["descriptor"]["computations"]] == ["pca_1", "de_1"]
    comp = find_volcano_computation(spec["descriptor"]["computations"])
    assert comp["computationId"] == "de_1" and comp["descriptor"]["configuration"] == DE_CFG
    viz = comp["visualizations"][0]["descriptor"]
    assert viz == {"type": "volcanoplot", "configuration": {"effectSizeThreshold": 1.0, "significanceThreshold": 0.05, "effectDirection": "upAndDown"}}
    for key in ("starredVariables", "derivedVariables"):
        assert spec["descriptor"][key] == []
    assert spec["descriptor"]["dataTableConfig"] == {}
    validate_spec(spec, "DS_x")


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda s: s.update(studyId="STUDY_x"), "DS_"),
        (lambda s: s["descriptor"]["computations"].pop(), "volcanoplot"),
        (lambda s: s["descriptor"]["computations"][1]["visualizations"][0]["descriptor"]["configuration"].pop("significanceThreshold"), "volcanoplot"),
        (lambda s: s["descriptor"]["computations"][1]["visualizations"].insert(0, {"visualizationId": "x", "descriptor": {"type": "scatterplot", "configuration": {}}}), "first visualization"),
        (lambda s: s["descriptor"]["computations"][1]["descriptor"]["configuration"]["comparator"].update(groupB=[]), "groupB"),
        (lambda s: s["descriptor"]["computations"][1]["descriptor"]["configuration"]["valueVariable"].update(entityId="OTHER"), "same entity"),
        (lambda s: s["descriptor"]["computations"][1]["descriptor"]["configuration"].update(differentialExpressionMethod="edgeR"), "differentialExpressionMethod"),
    ],
)
def test_validate_spec_rejects(mutate, needle):
    from _de import SpecError, validate_spec

    spec = copy.deepcopy(_spec())
    mutate(spec)
    with pytest.raises(SpecError) as e:
        validate_spec(spec, "DS_x")
    assert needle in str(e.value)


def test_wdk_params_round_trip():
    from _de import wdk_params

    spec = _spec()
    params = wdk_params(spec)
    assert params["eda_dataset_id"] == "DS_x"
    assert isinstance(params["eda_analysis_spec"], str) and '": ' not in params["eda_analysis_spec"]  # compact
    assert json.loads(params["eda_analysis_spec"]) == spec


def test_de_spec_cli_matches_de_body(run_eda, eda_mock, tmp_path):
    contrast = tmp_path / "c.json"
    contrast.write_text(json.dumps({"comparator": {"variableId": "VAR_081ab087"}, "groupA": [{"label": "normal"}], "groupB": [{"label": "febrile"}]}))
    run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", str(contrast))
    de_body = eda_mock.compute_bodies("differentialexpression")[-1]
    spec = json.loads(run_eda("de-spec", "plasmodb", "DS_e973eadd57", "--contrast", str(contrast), "--thresholds", "2,0.01,upOnly"))
    de_1 = spec["descriptor"]["computations"][1]
    assert de_1["descriptor"]["configuration"] == de_body["config"]
    assert de_1["visualizations"][0]["descriptor"]["configuration"] == {"effectSizeThreshold": 2.0, "significanceThreshold": 0.01, "effectDirection": "upOnly"}
    assert spec["studyId"] == "DS_e973eadd57"
    assert spec["descriptor"]["computations"][0]["descriptor"]["configuration"]["dataFormat"] == "rawCounts"
    params = json.loads(run_eda("de-spec", "plasmodb", "DS_e973eadd57", "--contrast", str(contrast), "--format", "params"))
    assert params["eda_dataset_id"] == "DS_e973eadd57"
    assert eda_mock.de_job in run_eda.err


TEMP = {"comparator": {"variableId": "VAR_081ab087"}, "groupA": [{"label": "normal"}], "groupB": [{"label": "febrile"}]}


def test_de_spec_save_is_content_addressed(run_eda, eda_cache, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # nothing may be written to the working directory
    args = ("de-spec", "plasmodb", "DS_e973eadd57", "--contrast", json.dumps(TEMP), "--save")
    a = json.loads(run_eda(*args))
    b = json.loads(run_eda(*args))
    c = json.loads(run_eda(*args, "--thresholds", "2,0.01"))
    assert a == b and a["paramsFile"] != c["paramsFile"]
    path = a["paramsFile"]
    assert path.startswith(str((eda_cache / "params").resolve())) and path.endswith(".json")
    assert a["leaf"]["params"] == "@" + path and a["leaf"]["search"]
    stdout_params = json.loads(run_eda("de-spec", "plasmodb", "DS_e973eadd57", "--contrast", json.dumps(TEMP), "--format", "params"))
    assert json.loads(open(path, encoding="utf-8").read()) == stdout_params
    assert not [f for f in tmp_path.iterdir() if f.is_file()]  # the working directory stays clean


def test_stash_json_is_atomic_parallel_and_pruned(eda_cache):
    import os
    import time
    from concurrent.futures import ThreadPoolExecutor

    import _client

    stale = eda_cache / "params" / "0123456789abcdef.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")
    old = time.time() - _client.CACHE_TTL_S - 60
    os.utime(stale, (old, old))
    payloads = [{"n": i} for i in range(20)] * 2  # every payload written twice, concurrently
    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(lambda d: _client.stash_json("params", d), payloads))
    assert len(set(paths)) == 20
    for d, p in zip(payloads, paths):
        assert json.loads(p.read_text()) == d
    names = sorted(f.name for f in (eda_cache / "params").iterdir())
    assert len(names) == 20 and all(n.endswith(".json") for n in names)  # no temp leftovers
    assert not stale.exists()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_de_spec.py -q`
Expected: FAIL with `ImportError: cannot import name 'build_spec'`.

- [ ] **Step 3: Implement**

Append to `_de.py`:

```python
def build_spec(dataset_id, display_name, filters, de_cfg, pca_cfg, thresholds):
    """The eda_analysis_spec the website notebook saves: subset filters, pca_1 and de_1
    computations, and a volcano visualization carrying the thresholds."""
    fc, p, direction = thresholds
    return {
        "displayName": display_name,
        "description": "",
        "studyId": dataset_id,
        "studyVersion": "",
        "apiVersion": "",
        "isPublic": False,
        "descriptor": {
            "subset": {"descriptor": canonical_filters(filters), "uiSettings": {}},
            "computations": [
                {
                    "computationId": "pca_1",
                    "descriptor": {"type": PLUGIN_PCA, "configuration": pca_cfg},
                    "visualizations": [
                        {"visualizationId": "pca_1", "displayName": "PCA Plot",
                         "descriptor": {"type": "scatterplot", "configuration": {}}}
                    ],
                },
                {
                    "computationId": "de_1",
                    "descriptor": {"type": PLUGIN_DE, "configuration": de_cfg},
                    "visualizations": [
                        {"visualizationId": "volcano_1", "displayName": "Volcano Plot",
                         "descriptor": {"type": "volcanoplot", "configuration": {
                             "effectSizeThreshold": fc, "significanceThreshold": p, "effectDirection": direction}}}
                    ],
                },
            ],
            "starredVariables": [],
            "dataTableConfig": {},
            "derivedVariables": [],
        },
    }


def find_volcano_computation(computations):
    """Port of the plugin's findVolcanoComputation: first computation with a volcanoplot
    visualization whose configuration has both thresholds."""
    for comp in computations or []:
        for viz in comp.get("visualizations") or []:
            desc = viz.get("descriptor") or {}
            cfg = desc.get("configuration")
            if desc.get("type") == "volcanoplot" and isinstance(cfg, dict) and \
                    "effectSizeThreshold" in cfg and "significanceThreshold" in cfg:
                return comp
    return None


def validate_spec(spec, dataset_id):
    """The rules GeneEdaVizWithComputePlugin and the DE compute apply, checked before printing."""
    if spec.get("studyId") != dataset_id:
        raise SpecError(
            f"spec studyId {spec.get('studyId')!r} must equal eda_dataset_id {dataset_id!r} "
            "(a DS_ dataset id, not a STUDY_ id)"
        )
    try:
        filters = spec["descriptor"]["subset"]["descriptor"]
        computations = spec["descriptor"]["computations"]
    except (KeyError, TypeError):
        raise SpecError("spec needs descriptor.subset.descriptor and descriptor.computations") from None
    if not isinstance(filters, list):
        raise SpecError("descriptor.subset.descriptor must be a list of filters")
    comp = find_volcano_computation(computations)
    if comp is None:
        raise SpecError("no computation has a volcanoplot visualization with effectSizeThreshold and significanceThreshold")
    if comp["visualizations"][0].get("descriptor", {}).get("type") != "volcanoplot":
        raise SpecError("the plugin reads thresholds from the first visualization of the volcano computation; put the volcano plot first")
    if comp["descriptor"].get("type") != PLUGIN_DE:
        raise SpecError(f"the volcano computation must be {PLUGIN_DE}, got {comp['descriptor'].get('type')!r}")
    cfg = comp["descriptor"].get("configuration") or {}
    for key in ("identifierVariable", "valueVariable", "comparator"):
        if not cfg.get(key):
            raise SpecError(f"differentialexpression configuration is missing {key}")
    for key in ("groupA", "groupB"):
        if not cfg["comparator"].get(key):
            raise SpecError(f"comparator {key} is empty")
    if cfg["identifierVariable"].get("entityId") != cfg["valueVariable"].get("entityId"):
        raise SpecError("identifier and value variables must be on the same entity")
    if cfg.get("differentialExpressionMethod") not in METHODS:
        raise SpecError(f"differentialExpressionMethod must be one of {METHODS}")


def wdk_params(spec):
    """WDK params for the DE/antibody-array search; the spec travels as a JSON string."""
    return {"eda_dataset_id": spec["studyId"], "eda_analysis_spec": json.dumps(spec, separators=(",", ":"), ensure_ascii=False)}
```

Add to `eda.py` after `cmd_de`:

```python
def cmd_de_spec(args) -> None:
    from _contrasts import PLUGIN_DE, job_id, pca_config
    from _de import build_spec, parse_thresholds, validate_spec, wdk_params

    thresholds = parse_thresholds(args.thresholds)
    p = prepare_de(args)
    t, c = p["t"], p["contrast"]
    ds = t["dataset"]
    name = (
        f"{ds['shortDisplayName'] or ds['displayName']}: "
        f"{'+'.join(g['label'] for g in c['groupB'])} vs {'+'.join(g['label'] for g in c['groupA'])}"
    )[:200]
    spec = build_spec(ds["datasetId"], name, c["filters"], p["config"],
                      pca_config(t["expr"]["entityId"], p["valueVar"]), thresholds)
    validate_spec(spec, ds["datasetId"])
    log(f"DE job id {job_id(PLUGIN_DE, p['body'])} (same body as 'eda.py de'; run de first so the WDK step answers at once)")
    if args.save:
        from _client import stash_json

        path = str(stash_json("params", wdk_params(spec)))
        out = {"paramsFile": path, "leaf": {"search": t["search"], "params": "@" + path}}
        if not t["search"]:
            out["note"] = "no search name known for this dataset: find it with 'eda.py de-datasets SITE'"
        emit(out)
        return
    emit(wdk_params(spec) if args.format == "params" else spec)
```

Append to `_client.py` (add `import hashlib` to its imports; `write_atomic` and `prune_stale` are from Task 1):

```python
def stash_json(kind, data):
    """Content-addressed glue file in the skill's cache: EDA_CACHE_DIR/{kind}/{hash}.json.
    Same content, same path; temp file + os.replace, so parallel writers never see a
    partial file; files older than CACHE_TTL_S are pruned. Never the user's directory."""
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    root = EDA_CACHE_DIR / kind
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}.json"
    write_atomic(path, text)  # refreshes the mtime, so a re-saved file is not pruned
    prune_stale(root)
    return path.resolve()
```

In `build_parser`, before `return p`:

```python
    sp = sub.add_parser("de-spec", help="print the eda_analysis_spec (or WDK params) for a contrast")
    _target_args(sp)
    _contrast_args(sp)
    _de_args(sp)
    sp.add_argument("--format", choices=["spec", "params"], default="spec",
                    help="spec = the analysis JSON; params = {eda_dataset_id, eda_analysis_spec} for wdk.py --params @file")
    sp.add_argument("--save", action="store_true",
                    help="write the WDK params to the skill cache (content-addressed) and print the path and a "
                         "ready-made strategy leaf; nothing is written to the working directory")
    sp.set_defaults(func=cmd_de_spec)
```

- [ ] **Step 4: Run the tests**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_de_spec.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add veupathdb_database/scripts/_de.py veupathdb_database/scripts/eda.py veupathdb_database/tests/test_de_spec.py
git commit -m "feat(eda): eda_analysis_spec builder, plugin-rule validation, eda.py de-spec

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: WDK handoff (catalog, `@file`, JSON params)

**Files:**
- Modify: `veupathdb_database/scripts/_client.py` (`fetch_catalog`, `filter_catalog_searches`)
- Modify: `veupathdb_database/scripts/_shaping.py` (`catalog_lines`, `score_searches`, `encode_params`)
- Modify: `veupathdb_database/scripts/_strategy.py` (`validate_spec`, `build_strategy`)
- Modify: `veupathdb_database/scripts/wdk.py` (`_load_params`, `cmd_create_strategy`, `_resolve_or_fail`, `cmd_inspect`, help strings)
- Modify: `veupathdb_database/tests/test_catalog.py` (`test_live_catalog_excludes_eda_searches`)
- Modify: `veupathdb_database/tests/eda_helpers.py` (append `FakeWdk`)
- Test: `veupathdb_database/tests/test_wdk_eda_handoff.py`

**Interfaces:**
- Produces:
  - `_client.CATALOG_SCHEMA = 2`, `_client.SUPPORTED_EDA_NOTEBOOKS = ("differentialExpressionNotebook", "antibodyArrayNotebook")`
  - catalog search entries gain `"edaNotebookType": str | None` and `"queryName": str`
  - `_shaping.display_name(search) -> str` (adds `[EDA notebook: … — use eda.py]`)
  - `_strategy.resolve_params(value) -> dict` (`"@path"` → JSON object from the file)
  - `wdk._load_json_arg(raw, flag)`; `--params @file` and `--spec @file` work everywhere
  - `encode_params`: a dict/list value for a non-vocabulary param is sent as compact JSON text
  - test helper `eda_helpers.FakeWdk` (WDK catalog + search details for two DE searches, one antibody-array search, one WGCNA search, the user-dataset search and a plain search)

- [ ] **Step 1: Write the failing tests**

Append to `veupathdb_database/tests/eda_helpers.py`:

```python
def _search(name, notebook, params=("eda_dataset_id", "eda_analysis_spec"), display=None):
    props = {"edaNotebookType": [notebook]} if notebook else {}
    return {"urlSegment": name, "displayName": display or name, "description": "",
            "paramNames": list(params), "properties": props,
            "queryName": "GenesByEdaVizWithCompute", "outputRecordClassName": "transcript"}


class FakeWdk:
    """Just enough WDK for the catalog and search details."""

    site_id = "plasmodb"
    DATASETS = {
        "GenesByRNASeqHS_DESeq": "DS_e973eadd57",
        "GenesByAntibodyArrayEdaSubset_X": "DS_24d441b301",
        "GenesByDESeqUserDataset": "",
        "GenesByRNASeqXWGCNAModules": "DS_w",
    }
    LISTING = [
        _search("GenesByRNASeqHS_DESeq", "differentialExpressionNotebook", display="Heat shock (DESeq2)"),
        _search("GenesByAntibodyArrayEdaSubset_X", "antibodyArrayNotebook", display="Mali antibody array"),
        _search("GenesByRNASeqXWGCNAModules", "wgcnaCorrelationNotebook"),
        _search("GenesByDESeqUserDataset", "differentialExpressionNotebook"),
        _search("GenesByEdaSubset", None),
        _search("GenesByTaxon", None, params=("organism",), display="Organism"),
    ]

    def __init__(self):
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(path)
        if path == "/record-types":
            return ["transcript"]
        if path == "/record-types/transcript/searches":
            return self.LISTING
        name = path.rsplit("/", 1)[1]
        return {"searchData": {"urlSegment": name, "parameters": [
            {"name": "eda_dataset_id", "type": "string", "isVisible": False,
             "initialDisplayValue": self.DATASETS.get(name, "")},
            {"name": "eda_analysis_spec", "type": "string", "allowEmptyValue": True},
        ]}}
```

Create `veupathdb_database/tests/test_wdk_eda_handoff.py`:

```python
import json

import pytest
from eda_helpers import FakeWdk


@pytest.fixture
def wdk_cache(tmp_path, monkeypatch):
    import _client

    monkeypatch.setattr(_client, "CACHE_DIR", tmp_path)
    return tmp_path


def test_catalog_keeps_supported_eda_notebooks_and_tags_them(wdk_cache):
    from _client import fetch_catalog
    from _shaping import catalog_lines, score_searches

    cat = fetch_catalog(FakeWdk())
    names = [s["name"] for s in cat["searches"]["transcript"]]
    assert names == ["GenesByRNASeqHS_DESeq", "GenesByAntibodyArrayEdaSubset_X", "GenesByDESeqUserDataset", "GenesByTaxon"]
    de = cat["searches"]["transcript"][0]
    assert de["edaNotebookType"] == "differentialExpressionNotebook" and de["queryName"] == "GenesByEdaVizWithCompute"
    lines = catalog_lines(cat)
    assert "Heat shock (DESeq2) [EDA notebook: differentialExpression — use eda.py]" in lines[0]
    hits = score_searches(cat, "differential expression")
    assert hits and hits[0]["name"] in {"GenesByRNASeqHS_DESeq", "GenesByDESeqUserDataset"}
    assert "[EDA notebook" in hits[0]["displayName"]


def test_old_schema_catalog_cache_is_refetched(wdk_cache):
    from _client import fetch_catalog

    (wdk_cache / "plasmodb.json").write_text(json.dumps({"record_types": ["transcript"], "searches": {"transcript": []}}))
    fake = FakeWdk()
    cat = fetch_catalog(fake)
    assert "/record-types" in fake.calls
    assert cat["schema"] == 2 and cat["searches"]["transcript"]


def test_encode_params_serialises_object_values_as_json():
    from _shaping import encode_params

    detail = FakeWdk().get("/record-types/transcript/searches/GenesByRNASeqHS_DESeq")["searchData"]
    spec = {"studyId": "DS_e973eadd57", "descriptor": {"computations": []}}
    wire = encode_params(detail, {"eda_dataset_id": "DS_e973eadd57", "eda_analysis_spec": spec})
    assert json.loads(wire["eda_analysis_spec"]) == spec
    assert wire["eda_analysis_spec"].startswith('{"studyId"')


def test_resolve_params_reads_at_file(tmp_path):
    from _strategy import SpecError, resolve_params

    good = tmp_path / "p.json"
    good.write_text('{"eda_dataset_id": "DS_x"}')
    assert resolve_params(f"@{good}") == {"eda_dataset_id": "DS_x"}
    assert resolve_params({"a": 1}) == {"a": 1}
    with pytest.raises(SpecError):
        resolve_params(f"@{tmp_path / 'missing.json'}")
    (tmp_path / "list.json").write_text("[1]")
    with pytest.raises(SpecError):
        resolve_params(f"@{tmp_path / 'list.json'}")


def test_validate_spec_accepts_at_file_leaf(tmp_path):
    from _strategy import validate_spec

    p = tmp_path / "p.json"
    p.write_text("{}")
    assert validate_spec({"leaf": {"search": "S", "params": f"@{p}"}}) == "S"


def test_wdk_load_json_arg(tmp_path):
    import wdk

    p = tmp_path / "p.json"
    p.write_text('{"a": 1}')
    assert wdk._load_params(f"@{p}") == {"a": 1}
    assert wdk._load_params('{"b": 2}') == {"b": 2}
    with pytest.raises(SystemExit):
        wdk._load_params(f"@{tmp_path / 'nope.json'}")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_wdk_eda_handoff.py -q`
Expected: FAIL (the DE searches are filtered out; `resolve_params` does not exist).

- [ ] **Step 3: Implement `_client.py`**

Replace `DEFAULT_EXCLUDED_PARAM_PREFIXES = ("eda_",)` (line 205) with:

```python
DEFAULT_EXCLUDED_PARAM_PREFIXES = ("eda_",)
# EDA notebook searches eda.py supports; other eda_ searches stay hidden
SUPPORTED_EDA_NOTEBOOKS = ("differentialExpressionNotebook", "antibodyArrayNotebook")
CATALOG_SCHEMA = 2  # 2 = entries carry edaNotebookType and queryName


def _notebook_type(search):
    values = (search.get("properties") or {}).get("edaNotebookType") or []
    return values[0] if values else None
```

In `filter_catalog_searches`, replace the list comprehension with:

```python
        filtered_searches[rt] = [
            s
            for s in searches
            if s.get("edaNotebookType") in SUPPORTED_EDA_NOTEBOOKS
            or not any(
                isinstance(p, str)
                and any(p.startswith(prefix) for prefix in excluded_prefixes)
                for p in s.get("paramNames", [])
            )
        ]
```

Replace the body of `fetch_catalog` (lines 245–278) with:

```python
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{client.site_id}.json"
    raw_catalog = None
    if not refresh and cache.is_file() and time.time() - cache.stat().st_mtime < CACHE_TTL_S:
        cached = json.loads(cache.read_text())
        if cached.get("schema") == CATALOG_SCHEMA:  # older caches lack edaNotebookType
            raw_catalog = cached
    if raw_catalog is None:
        record_types = client.get("/record-types")
        searches = {}
        for rt in record_types:
            try:
                listing = client.get(f"/record-types/{rt}/searches")
            except WDKError:
                continue  # some record types have no search listing; skip, don't fail
            searches[rt] = [
                {
                    "name": s["urlSegment"],
                    "displayName": s.get("displayName", ""),
                    "description": s.get("description") or s.get("summary") or "",
                    "paramNames": s.get("paramNames", []),
                    "outputRecordClassName": s.get("outputRecordClassName", ""),
                    "edaNotebookType": _notebook_type(s),
                    "queryName": s.get("queryName", ""),
                }
                for s in listing
            ]
        raw_catalog = {
            "schema": CATALOG_SCHEMA,
            "cached_at": time.time(),
            "record_types": record_types,
            "searches": searches,
        }
        cache.write_text(json.dumps(raw_catalog))

    return filter_catalog_searches(raw_catalog, excluded_prefixes=excluded_param_prefixes)
```

Update its docstring: `Filters out searches with excluded_param_prefixes (default: ('eda_',)) except the EDA notebook searches eda.py supports.`

- [ ] **Step 4: Implement `_shaping.py`**

Add after `_is_boolean`:

```python
def _camel_words(name):
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name).lower()


def display_name(search):
    nb = search.get("edaNotebookType")
    if nb:
        return f"{search['displayName']} [EDA notebook: {nb.removesuffix('Notebook')} — use eda.py]"
    return search["displayName"]
```

In `catalog_lines`, replace the append with `lines.append(f"{rt}\t{s['name']}\t{display_name(s)}\t{desc}")`.

In `score_searches`, replace `desc = strip_html(s["description"]).lower()` with:

```python
            desc = strip_html(s["description"]).lower()
            if s.get("edaNotebookType"):
                desc += " " + _camel_words(s["edaNotebookType"])
```

and in its returned dicts use `"displayName": display_name(s),`.

In `encode_params`, replace `sval = str(value)` with:

```python
            if isinstance(value, (dict, list)) and not isinstance(vocab, (list, dict)):
                # e.g. eda_analysis_spec given as an object: WDK wants the JSON text
                sval = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
            else:
                sval = str(value)
```

- [ ] **Step 5: Implement `_strategy.py`**

Add `import json` and `import pathlib` at the top, then add after `SpecError`:

```python
def resolve_params(value):
    """A node's params: an object, or "@path" naming a JSON file that holds one
    (e.g. the output of eda.py de-spec --format params)."""
    if isinstance(value, str) and value.startswith("@"):
        path = pathlib.Path(value[1:]).expanduser()
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise SpecError(f"params file not found: {path}") from None
        except json.JSONDecodeError as e:
            raise SpecError(f"params file {path} is not valid JSON: {e}") from None
        if not isinstance(loaded, dict):
            raise SpecError(f"params file {path} must hold a JSON object")
        return loaded
    return value
```

In `validate_spec`, replace the leaf check with:

```python
    if kind == "leaf":
        if "search" not in body or not isinstance(resolve_params(body.get("params", {})), dict):
            raise SpecError(f"leaf needs 'search' and object 'params' (or \"@file\"): {body!r:.120}")
        return body["search"]
```

In `build_strategy.create`, replace both `params = body.get("params", {})` lines with `params = resolve_params(body.get("params", {}))`.

- [ ] **Step 6: Implement `wdk.py`**

Replace `_load_params` with:

```python
def _load_json_arg(raw, flag):
    """JSON from an inline string, or from a file when the value is @path."""
    if raw.startswith("@"):
        path = pathlib.Path(raw[1:]).expanduser()
        if not path.is_file():
            fail(f"{flag} file not found: {path}")
        raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"{flag} is not valid JSON: {e}")


def _load_params(raw):
    params = _load_json_arg(raw, "--params")
    if not isinstance(params, dict):
        fail("--params must be a JSON object of {param: value}")
    return params
```

In `cmd_create_strategy`, replace the `try: spec = json.loads(args.spec) …` block with `spec = _load_json_arg(args.spec, "--spec")`.

In `_resolve_or_fail`, replace the inner `fail(...)` message with:

```python
                fail(
                    f"search '{name}' on {site} is an EDA notebook search this skill does not "
                    "support (eda.py supports the differential-expression and antibody-array "
                    "notebooks only)."
                )
```

In `cmd_inspect`, replace the `emit(...)` line with:

```python
    sheet = build_sheet(get_search_detail(c, rt, args.search), query=args.query)
    nb = next((s.get("edaNotebookType") for s in cat["searches"].get(rt, []) if s["name"] == args.search), None)
    if nb:
        sheet["eda_note"] = (
            f"EDA notebook search ({nb}): build eda_analysis_spec with scripts/eda.py "
            "(references/eda.md), then pass it with --params @file"
        )
    emit(sheet)
```

Update the `--params` help strings for `count` and `preview` to `'JSON object or @file, e.g. \'{"organism": ["Plasmodium"]}\''`, the `--spec` help to `"JSON node tree or @file; see references/strategies.md"`, and the three `--exclude-param-prefix` helps to `"exclude searches with params starting with prefix (default: eda_, except supported EDA notebooks; pass '' to disable)"`.

- [ ] **Step 7: Update the live catalog test**

In `veupathdb_database/tests/test_catalog.py`, replace `test_live_catalog_excludes_eda_searches` with:

```python
def test_live_catalog_keeps_only_supported_eda_searches(token):
    from _client import SUPPORTED_EDA_NOTEBOOKS, Client, fetch_catalog

    c = Client("vectorbase", token=token)
    transcript = fetch_catalog(c, refresh=True)["searches"]["transcript"]
    eda = [s for s in transcript if any(p.startswith("eda_") for p in s.get("paramNames", []))]
    assert eda, "DE notebook searches should now be listed"
    assert all(s["edaNotebookType"] in SUPPORTED_EDA_NOTEBOOKS for s in eda)
    raw = fetch_catalog(c, excluded_param_prefixes=())["searches"]["transcript"]
    assert len(raw) > len(transcript)
```

and in `TESTS.md` replace the CAT-5 row with:

```
| CAT-5 | test_catalog.py::test_live_catalog_keeps_only_supported_eda_searches / `wdk.py find-searches vectorbase DESeq` | only DE/antibody-array notebook searches among eda_ searches in the default catalog, tagged [EDA notebook: …] | exact | (capture count) | 2026-10-03 |
```

- [ ] **Step 8: Run the whole suite**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests -q`
Expected: PASS. `test_filter_catalog_searches_offline` still passes because its entries have no `edaNotebookType`. Fill in the CAT-5 gold count from the live run.

- [ ] **Step 9: Commit**

```bash
git add veupathdb_database/scripts/_client.py veupathdb_database/scripts/_shaping.py veupathdb_database/scripts/_strategy.py veupathdb_database/scripts/wdk.py veupathdb_database/tests/test_wdk_eda_handoff.py veupathdb_database/tests/test_catalog.py veupathdb_database/tests/eda_helpers.py veupathdb_database/TESTS.md
git commit -m "feat(wdk): list and tag DE/antibody-array notebook searches; @file params; JSON-object params

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: `eda.py de-datasets` and search-name targets

**Files:**
- Modify: `veupathdb_database/scripts/_eda.py` (append `eda_searches`, `cached_eda_searches`)
- Modify: `veupathdb_database/scripts/eda.py` (`resolve_target_arg`, `cmd_de_datasets`, parser, `dataset` help)
- Test: `veupathdb_database/tests/test_eda_cli_datasets.py`

**Interfaces:**
- Consumes: `_client.fetch_catalog` (schema 2), `_client.SUPPORTED_EDA_NOTEBOOKS`, `_shaping.get_search_detail`, `_contrasts.NOTEBOOK_METHODS`
- Produces:
  - `_eda.eda_searches(wdk_client, refresh=False, log=None) -> list[{"search", "recordType", "displayName", "datasetId" | None, "notebook", "method"}]` (cached as `{site}_eda_searches`)
  - `_eda.cached_eda_searches(site_id) -> list | None` (never touches the network)
  - `eda.resolve_target_arg(site, arg)` accepts a DS_ id or a supported search name
  - CLI: `de-datasets SITE [--json] [--refresh]`

- [ ] **Step 1: Write the failing tests**

Create `veupathdb_database/tests/test_eda_cli_datasets.py`:

```python
import json

import pytest
from eda_helpers import FakeWdk


@pytest.fixture
def fake_wdk(monkeypatch, tmp_path):
    import _client
    import eda as eda_cli

    monkeypatch.setattr(_client, "CACHE_DIR", tmp_path / "wdk-cache")
    fake = FakeWdk()
    monkeypatch.setattr(eda_cli, "wdk_client_for", lambda site: fake)
    return fake


def test_de_datasets_lists_supported_searches(run_eda, fake_wdk):
    rows = json.loads(run_eda("de-datasets", "plasmodb", "--json"))
    assert [(r["search"], r["datasetId"], r["method"]) for r in rows] == [
        ("GenesByAntibodyArrayEdaSubset_X", "DS_24d441b301", "limma"),
        ("GenesByDESeqUserDataset", None, "DESeq"),
        ("GenesByRNASeqHS_DESeq", "DS_e973eadd57", "DESeq"),
    ]
    text = run_eda("de-datasets", "plasmodb")
    assert "DS_e973eadd57\tDESeq\tdifferentialExpressionNotebook\tGenesByRNASeqHS_DESeq" in text
    assert "(user dataset: pass your DS_ id)" in text


def test_search_name_target_and_cached_notebook(run_eda, fake_wdk):
    import eda as eda_cli

    out = json.loads(run_eda("contrasts", "plasmodb", "GenesByRNASeqHS_DESeq", "--json"))
    assert out["datasetId"] == "DS_e973eadd57" and out["method"] == "DESeq"
    assert eda_cli.resolve_target_arg("plasmodb", "DS_e973eadd57") == (
        "DS_e973eadd57", "differentialExpressionNotebook", "GenesByRNASeqHS_DESeq")


def test_user_dataset_search_needs_ds_id(run_eda, fake_wdk, capsys):
    with pytest.raises(SystemExit):
        run_eda("study", "plasmodb", "GenesByDESeqUserDataset")
    assert "DS_" in capsys.readouterr().err


def test_unknown_search_suggests(run_eda, fake_wdk, capsys):
    with pytest.raises(SystemExit):
        run_eda("study", "plasmodb", "GenesByRNASeqHS_DESeqq")
    assert "GenesByRNASeqHS_DESeq" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_cli_datasets.py -q`
Expected: FAIL (`invalid choice: 'de-datasets'`).

- [ ] **Step 3: Implement**

Append to `_eda.py`:

```python
def eda_searches(wdk_client, refresh=False, log=None):
    """DE and antibody-array notebook searches with their DS_ ids (from each search's
    hidden eda_dataset_id default). One search-detail call per search, cached 7 days."""
    import _client
    from _contrasts import NOTEBOOK_METHODS
    from _shaping import get_search_detail

    def fetch():
        cat = _client.fetch_catalog(wdk_client, refresh=refresh, excluded_param_prefixes=())
        out, seen = [], set()
        for rt, searches in cat["searches"].items():
            for s in searches:
                nb = s.get("edaNotebookType")
                if nb not in _client.SUPPORTED_EDA_NOTEBOOKS or s["name"] in seen:
                    continue
                seen.add(s["name"])
                if log:
                    log(f"reading {s['name']}")
                detail = get_search_detail(wdk_client, rt, s["name"])
                ds = next((p.get("initialDisplayValue") for p in detail.get("parameters", [])
                           if p["name"] == "eda_dataset_id"), None)
                out.append({"search": s["name"], "recordType": rt, "displayName": s.get("displayName", ""),
                            "datasetId": ds or None, "notebook": nb, "method": NOTEBOOK_METHODS[nb]})
        return sorted(out, key=lambda r: r["search"])

    return cached_json(f"{wdk_client.site_id}_eda_searches", fetch, refresh=refresh)


def cached_eda_searches(site_id):
    """The cached eda_searches listing, or None; never touches the network."""
    import json

    import _client

    path = _client.EDA_CACHE_DIR / f"{site_id}_eda_searches.json"
    return json.loads(path.read_text()) if path.is_file() else None
```

In `eda.py`, replace `resolve_target_arg` with:

```python
def resolve_target_arg(site, arg):
    """DS_ id or supported search name -> (dataset id, notebook type or None, search or None)."""
    import difflib

    from _eda import cached_eda_searches, eda_searches

    if arg.startswith("DS_"):
        hit = next((s for s in cached_eda_searches(site) or [] if s["datasetId"] == arg), None)
        return arg, (hit or {}).get("notebook"), (hit or {}).get("search")
    if arg.startswith("STUDY_"):
        fail(f"'{arg}' is an EDA-internal study id; eda.py takes the DS_ dataset id")
    searches = eda_searches(wdk_client_for(site), log=log)
    hit = next((s for s in searches if s["search"] == arg), None)
    if hit is None:
        close = difflib.get_close_matches(arg, [s["search"] for s in searches], n=3, cutoff=0.6)
        fail(f"'{arg}' is neither a DS_ id nor a DE/antibody-array search on {site}; did you mean {close}? "
             f"List them with: eda.py de-datasets {site}")
    if not hit["datasetId"]:
        fail(f"{arg} runs on your own uploaded (VDI) datasets: pass that dataset's DS_ id instead")
    return hit["datasetId"], hit["notebook"], hit["search"]


def cmd_de_datasets(args) -> None:
    from _eda import eda_searches

    rows = eda_searches(wdk_client_for(args.site), refresh=args.refresh, log=log)
    if args.json:
        emit(rows)
        return
    print("# datasetId\tmethod\tnotebook\tsearch\tdisplayName")
    for r in rows:
        ds = r["datasetId"] or "(user dataset: pass your DS_ id)"
        print(f"{ds}\t{r['method']}\t{r['notebook']}\t{r['search']}\t{r['displayName']}")
```

In `_target_args`, change the `dataset` help to `"DS_ dataset id, or a DE/antibody-array search name (see de-datasets)"`. In `build_parser`, before `return p`:

```python
    sp = sub.add_parser("de-datasets", help="DE and antibody-array searches with their DS_ ids and methods")
    sp.add_argument("site")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--refresh", action="store_true", help="re-read the WDK catalog and search details")
    sp.set_defaults(func=cmd_de_datasets)
```

`test_study_rejects_non_dataset_argument` (Task 4) keeps passing: a `STUDY_` argument now hits the `STUDY_` branch, whose message also names `DS_`, and it fails before any network call.

- [ ] **Step 4: Run the tests**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_cli_datasets.py tests/test_eda_cli_study.py -q`
Expected: PASS.

- [ ] **Step 5: Try it live (needs a token; first run makes one detail call per search)**

Run: `cd veupathdb_database && uv run scripts/eda.py de-datasets plasmodb | grep -E "e973eadd57|24d441b301"`
Expected: `DS_e973eadd57	DESeq	differentialExpressionNotebook	GenesByRNASeqpfal3D7_Pfal3D7_Febrile_temps_RNASeq_ebi_rnaSeq_RSRCDESeq	…` and `DS_24d441b301	limma	antibodyArrayNotebook	GenesByAntibodyArrayEdaSubset_PlasmoDB_Crompton_Mali_AntibodyArray_RSRC	…`.

- [ ] **Step 6: Commit**

```bash
git add veupathdb_database/scripts/_eda.py veupathdb_database/scripts/eda.py veupathdb_database/tests/test_eda_cli_datasets.py
git commit -m "feat(eda): de-datasets listing; accept DE search names as targets

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Live gold tests for stage 1

**Files:**
- Create: `veupathdb_database/tests/test_eda_live.py`
- Modify: `veupathdb_database/TESTS.md`

**Interfaces:**
- Consumes: the whole stage 1 CLI, `eda.build_parser`, `eda.prepare_de`, `_shaping.encode_params`/`get_search_detail`/`run_report`/`extract_count`, `_strategy.build_strategy`
- Produces: gold cases EDA-2 … EDA-9 in TESTS.md

- [ ] **Step 1: Write the live tests**

Create `veupathdb_database/tests/test_eda_live.py`:

```python
"""Live gold tests for eda.py on plasmodb. They skip without a token; see TESTS.md EDA-*."""
import json

import pytest

HS = "DS_e973eadd57"
HS_SEARCH = "GenesByRNASeqpfal3D7_Pfal3D7_Febrile_temps_RNASeq_ebi_rnaSeq_RSRCDESeq"
AB = "DS_24d441b301"
GOLD_JOB = "db04204e5386396e1ca2cb78469ab6fb"
TEMP = {"comparator": {"variableId": "VAR_081ab087"}, "groupA": [{"label": "normal"}], "groupB": [{"label": "febrile"}]}
# A contrast nobody is likely to have run: the strong job-identity check needs it fresh.
RARE = {
    "comparator": {"variableId": "VAR_84f17484"},
    "groupA": [{"label": "delta-DHC mutant"}],
    "groupB": [{"label": "delta-LRR5 mutant"}],
    "filters": [{"entityId": "ENT_8151325d", "variableId": "VAR_081ab087", "type": "stringSet", "stringSet": ["febrile"]}],
}


@pytest.fixture
def live_eda(token, capsys):
    import eda as eda_cli

    def run(*argv):
        eda_cli.main(list(argv))
        return capsys.readouterr().out

    return run


@pytest.fixture
def contrast_path(tmp_path):
    def make(obj):
        p = tmp_path / f"c{abs(hash(json.dumps(obj)))}.json"
        p.write_text(json.dumps(obj))
        return str(p)

    return make


def _wdk_count(token, params):
    from _client import Client
    from _shaping import encode_params, extract_count, get_search_detail, run_report

    c = Client("plasmodb", token=token)
    wire = encode_params(get_search_detail(c, "transcript", HS_SEARCH), params, client=c)
    return extract_count(run_report(c, "transcript", HS_SEARCH, wire)["meta"])


def test_live_contrasts_heatshock(live_eda):
    out = json.loads(live_eda("contrasts", "plasmodb", HS, "--json"))
    temp = next(c for c in out["candidates"] if c["comparator"]["variableId"] == "VAR_081ab087" and c["stratum"] is None)
    assert temp["index"] == 1
    assert (temp["groupA"], temp["groupB"], temp["nA"], temp["nB"]) == ([{"label": "normal"}], [{"label": "febrile"}], 6, 6)
    assert temp["cache"] == {"status": "complete", "jobId": GOLD_JOB}


def test_live_de_heatshock_gold(live_eda, contrast_path):
    out = json.loads(live_eda("de", "plasmodb", HS, "--contrast", contrast_path(TEMP), "--json"))
    assert out["provenance"]["jobId"] == GOLD_JOB
    counts = out["context"]["counts"]
    assert 1543 * 0.8 <= counts["passing_raw_p"] <= 1543 * 1.2
    assert counts["wdk_step_genes"] in (counts["passing_raw_p"], counts["passing_raw_p"] - 1)


@pytest.mark.parametrize("thresholds", ["1,0.05", "0,1"])
def test_live_wdk_count_matches_de(live_eda, contrast_path, token, thresholds):
    path = contrast_path(TEMP)
    de = json.loads(live_eda("de", "plasmodb", HS, "--contrast", path, "--thresholds", thresholds, "--json"))
    params = json.loads(live_eda("de-spec", "plasmodb", HS, "--contrast", path, "--thresholds", thresholds, "--format", "params"))
    count, field = _wdk_count(token, params)
    assert field in ("displayViewTotalCount", "displayTotalCount")  # genes, not transcripts
    assert count == de["context"]["counts"]["wdk_step_genes"]


def test_live_create_strategy_from_de_spec(live_eda, token):
    from _client import Client, fetch_catalog
    from _strategy import build_strategy

    saved = json.loads(live_eda("de-spec", "plasmodb", HS, "--contrast", json.dumps(TEMP), "--save"))
    assert saved["leaf"]["search"] == HS_SEARCH
    c = Client("plasmodb", token=token)
    out = build_strategy(c, fetch_catalog(c), {"leaf": saved["leaf"]}, "__skill_test__: eda de step")
    try:
        assert out["steps"][0]["valid"] is True
        size = out["estimated_size"]
        assert size == "unmeasured" or size > 1000
    finally:
        c.delete(f"/users/{c.user_id()}/strategies/{out['strategy_id']}")


def test_live_wdk_step_drives_the_same_job(live_eda, contrast_path, token):
    """Strong job-identity check: a never-computed contrast is started by the WDK
    step itself, and EDA then reports our body's job as existing."""
    import eda as eda_cli
    from _client import WDKError
    from _contrasts import PLUGIN_DE
    from _eda import compute_status

    path = contrast_path(RARE)
    argv = ["de-spec", "plasmodb", HS, "--contrast", path, "--value-var", "SEQUENCE_READ_COUNT_ANTISENSE"]
    p = eda_cli.prepare_de(eda_cli.build_parser().parse_args(argv))
    before = compute_status(p["t"]["client"], PLUGIN_DE, p["body"], start=False)
    if before["status"] != "no-such-job":
        pytest.skip(f"RARE contrast already computed ({before['status']}, job {before['jobID']}): "
                    "edit RARE to a fresh contrast to repeat the strong check")
    params = json.loads(live_eda(*argv, "--format", "params"))
    try:
        _wdk_count(token, params)  # the WSF plugin starts the job and answers 202
    except WDKError:
        pass
    after = compute_status(p["t"]["client"], PLUGIN_DE, p["body"], start=False)
    assert after["jobID"] == before["jobID"]
    assert after["status"] in ("queued", "in-progress", "complete")


def test_live_mirror_job_has_negated_effects(live_eda, contrast_path):
    """The basis of mirror reuse: swapping groups negates effectSize and leaves p and
    padj unchanged, row for row. Runs the febrile-reference job once (about 2 min);
    later runs hit the cache."""
    import eda as eda_cli
    from _de import java_double
    from _eda import volcano, wait_for_job
    from _contrasts import PLUGIN_DE

    argv = ["de", "plasmodb", HS, "--contrast", contrast_path(TEMP)]
    p = eda_cli.prepare_de(eda_cli.build_parser().parse_args(argv))
    c, mbody = p["t"]["client"], eda_cli.mirror_body(p)
    assert wait_for_job(c, PLUGIN_DE, mbody, timeout_s=1800)["status"] == "complete"
    fwd, rev = volcano(c, p["body"])["statistics"], volcano(c, mbody)["statistics"]
    assert [s["pointID"] for s in fwd] == [s["pointID"] for s in rev]  # same row order: WDK row-0 drop agrees
    for f, r in zip(fwd, rev):
        for key, sign in (("effectSize", -1), ("pValue", 1), ("adjustedPValue", 1)):
            a, b = java_double(f.get(key)), java_double(r.get(key))
            assert (a is None) == (b is None), (f["pointID"], key)
            if a is not None:
                assert b == pytest.approx(sign * a, rel=1e-6, abs=1e-12), (f["pointID"], key)


def test_live_de_datasets_plasmodb(live_eda):
    rows = json.loads(live_eda("de-datasets", "plasmodb", "--json"))
    by_ds = {r["datasetId"]: r for r in rows}
    assert by_ds[HS]["search"] == HS_SEARCH and by_ds[HS]["method"] == "DESeq"
    assert by_ds[AB]["method"] == "limma"
    assert len(rows) >= 30


def test_live_limma_antibody(live_eda):
    out = json.loads(live_eda("contrasts", "plasmodb", AB, "--json"))
    assert out["method"] == "limma" and out["valueVariable"] == "NORMALIZED_INTENSITY"
    assert out["candidates"], out["skipped"]
    cand = next((c for c in out["candidates"] if c["cache"]["status"] == "complete"), out["candidates"][0])
    de = json.loads(live_eda("de", "plasmodb", AB, "--contrast", str(cand["index"]), "--json", "--timeout", "1800"))
    assert de["context"]["method"] == "limma"
    assert de["context"]["counts"]["tested"] > 0
```

- [ ] **Step 2: Run them live**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_live.py -v`
Expected: PASS (the strong identity test may SKIP if `RARE` was already computed: note it). Without a token: every test SKIPs. Record the observed values for Step 3. If the mirror test fails on values (not on a timeout), stop: mirror reuse in `de` rests on it, so either loosen the tolerance with a reason recorded in TESTS.md or make `--no-mirror` the default.

- [ ] **Step 3: Register the gold cases**

Append to `veupathdb_database/TESTS.md`, filling `Gold (captured)` from Step 2 where marked:

```
| EDA-1 | test_contrasts_canonical.py::test_job_id_matches_live_gold | local MD5 of the canonical body equals the live job id | exact (offline) | db04204e5386396e1ca2cb78469ab6fb | 2026-10-03 |
| EDA-2 | `eda.py contrasts plasmodb DS_e973eadd57` / test_eda_live.py::test_live_contrasts_heatshock | candidate 1 = temperature_condition normal → febrile, 6/6, cache complete | exact | index 1, 6/6, db04204e… | 2026-10-03 |
| EDA-3 | `eda.py de plasmodb DS_e973eadd57 --contrast <normal→febrile file>` / test_live_de_heatshock_gold | job id = gold; passing raw p at 1,0.05 | exact job id; range ±20% count | 1543 | 2026-10-03 |
| EDA-4 | test_live_wdk_count_matches_de[1,0.05 / 0,1] | WDK displayTotalCount = de's "WDK step returns" | exact | 1543; 5509 (= 5510 passing − dropped statistics[0]) | 2026-10-03 |
| EDA-5 | test_live_wdk_step_drives_the_same_job | a fresh contrast's job is started by the WDK step under our job id | exact | (job id, date of the run that did not skip) | |
| EDA-6 | test_live_create_strategy_from_de_spec | strategy from the `de-spec --save` leaf (cache "@file") is valid | fields-present | (estimated_size) | |
| EDA-7 | `eda.py de-datasets plasmodb` / test_live_de_datasets_plasmodb | heat-shock and Crompton antibody searches with DS ids and methods | range ≥30 rows | (row count) | |
| EDA-8 | `eda.py de plasmodb DS_24d441b301 --contrast N` / test_live_limma_antibody | limma end to end on an antibody array | fields-present | (contrast, tested) | |
| EDA-9 | test_live_mirror_job_has_negated_effects | heat-shock febrile→normal job: same rows in the same order, effectSize negated, p and padj equal | rel 1e-6 | (mirror job id) | |
| EDA-WEB-1 | manual: open the EDA-6 strategy URL before teardown (or re-create it), click the step's revise/edit | the notebook opens with the same comparator, groups and thresholds | manual | | |
```

- [ ] **Step 4: Commit**

```bash
git add veupathdb_database/tests/test_eda_live.py veupathdb_database/TESTS.md
git commit -m "test(eda): live gold tests: job identity, WDK count parity, limma end to end

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: SKILL.md router, `references/eda.md`, `references/wdk-workflow.md`, EDA gotchas

**Files:**
- Modify: `veupathdb_database/SKILL.md` (rewrite as a router)
- Create: `veupathdb_database/references/wdk-workflow.md`
- Create: `veupathdb_database/references/eda.md`
- Modify: `veupathdb_database/references/gotchas.md` (append EDA section)
- Modify: `veupathdb_database/references/auth.md` (one line on EDA transport)

**Interfaces:**
- Consumes: the stage 1 CLI surface (Tasks 1–14)
- Produces: docs that later tasks extend: `references/eda.md` gains `## Sample filters` (Task 16) and `## PCA` (Task 18); SKILL.md gains the filters sentence (Task 16) and the PCA step (Task 18).

- [ ] **Step 1: Create `references/wdk-workflow.md` from SKILL.md (moved, not rewritten)**

Create `veupathdb_database/references/wdk-workflow.md` with the heading `# WDK workflow (wdk.py)`. Below it, move these blocks **verbatim** from the current `veupathdb_database/SKILL.md` (commit `fb81b67` line numbers; SKILL.md is untouched by Tasks 1–14):
- lines 93–112 (`## Resolving gene symbols & names …`)
- lines 114–143 (`## The workflow`)
- lines 145–169 (`## Subcommands` table)
- lines 186–216 (the gotcha bullets from `inspect-record-type` and `pan_` through `input-dataset`), under a new heading `## WDK-specific gotchas`

Then make three edits in the moved text:
- In the subcommand table, `count`, `preview` and `create-strategy` take `--params JSON|@file` / `--spec JSON|@file`.
- Add a table row: `| (EDA searches) | DE and antibody-array notebook searches are listed and tagged [EDA notebook: …]; build their params with scripts/eda.py (references/eda.md) |`.
- Delete nothing else. Lines 184–185 (the "EDA searches are excluded" bullet) are **not** moved: the rule no longer holds.

- [ ] **Step 2: Rewrite `SKILL.md`**

Replace the whole of `veupathdb_database/SKILL.md` with:

````markdown
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

Pass the same `--vars`, `--value-var` and `--entity` to every command after
`contrasts`, or `--contrast N` names a different candidate. Give contrasts and filters
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
````

- [ ] **Step 3: Create `references/eda.md`**

Create `veupathdb_database/references/eda.md`:

````markdown
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
   the skill cache and prints `{"paramsFile", "leaf"}`; put the `leaf` in
   `wdk.py create-strategy SITE --spec '{"leaf": …}'` (or combine it with other
   steps), or run `wdk.py count SITE SEARCH --params @PARAMSFILE`.

`--contrast N` re-enumerates the candidates, so give every command after
`contrasts` the same `--vars`, `--value-var` and `--entity`. An explicit contrast
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
- Identifier-like variables (more than 20 distinct values covering at least 90% of
  records) get one line with no levels.
- The `DE-ready:` line names the gene entity, its gene count and its value variables.
  With several expression entities (e.g. host and parasite), pass `--entity`.
- Only the expression entity's parent and higher entities can hold a comparator
  (a notebook rule). Other entities are listed with counts and marked unusable.
- An entity with more than 5000 records is summarised per variable via
  `/distribution`; `contrasts` then refuses until filters narrow it.

## Contrasts

- Candidates: categorical variables, and numeric ones with at most 6 distinct values
  (each value becomes a half-open bin `[v, next value)`), on sample-side entities.
  Levels need at least 2 samples. Up to 6 levels are paired; with more, pool
  levels into groups in a contrast file.
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
(p and padj are identical; verified live, TESTS.md EDA-9). So when this orientation
has never run but its mirror is cached, `de` reuses the mirror, negates the effect
sizes, and records the mirror's job under `provenance.statisticsFrom`. The WDK step
for this orientation still runs its own job. `--no-mirror` disables the reuse.

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
````

- [ ] **Step 4: Append the EDA section to `references/gotchas.md`**

```markdown

## EDA differential expression (eda.py)

1. ★ Thresholds use the **raw** p-value (plugin and website volcano). padj is reported
   by `de` for judgement; the WDK step never uses it.
2. ★ groupA is the reference: positive log2FC = higher in groupB. The agent chooses
   it; the control-label match in `contrasts` is a hint, not a rule. Swapping groups
   makes a different job id with the same statistics sign-flipped (`de` reuses a cached
   mirror). Changing label order outside eda.py also makes a different job.
3. Fold changes are unshrunk log2 ratios: large values for low-count genes are noise.
4. padj NA = removed by independent filtering; absent gene = not tested (all zero).
5. One comparator, no covariates, no paired design: crossed or repeated-measures
   designs (e.g. one subject sampled twice) are analysed as if independent. Use the
   stratified contrasts, and say so when the design is paired.
6. ★ `studyId` in an `eda_analysis_spec` is the **DS_** id; compute bodies use the
   STUDY_ id. eda.py resolves this; hand-built specs get it wrong.
7. ★ The first WDK answer for an uncomputed contrast is HTTP 202 (the request
   starts the job). Run `eda.py de` first so the step answers at once.
8. Jobs are shared across users and never belong to you: `--retry` deletes only a
   failed job.
9. ★ The WDK step drops the first volcano statistics row (plugin header-skip quirk):
   its gene count can be one less than the raw-p count. `de` reports both.
```

- [ ] **Step 5: Note EDA transport in `references/auth.md`**

At the end of the `## How auth actually works` section, add:

```markdown
- EDA (`https://{site host}/eda`, used by eda.py) reads the same token as
  `Authorization: Bearer <token>`. The client sends both the WDK cookie and the
  Bearer header, so one login serves both CLIs.
```

- [ ] **Step 6: Check sizes and links**

Run: `cd veupathdb_database && wc -l SKILL.md references/*.md && grep -n "references/" SKILL.md`
Expected: SKILL.md ≤ 200 lines; every referenced file exists.

- [ ] **Step 7: Commit**

```bash
git add veupathdb_database/SKILL.md veupathdb_database/references
git commit -m "docs(skill): route SKILL.md between WDK and EDA; add references/eda.md and wdk-workflow.md

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Stage 2: sample filtering

### Task 16: `--filters` on study, contrasts, de, de-spec

**Files:**
- Modify: `veupathdb_database/scripts/_samples.py` (append `FILTER_FIELDS`, `validate_filters`)
- Modify: `veupathdb_database/scripts/eda.py` (`read_filters`, `_load_filters`, `resolve_contrast`, `_target_args`)
- Modify: `veupathdb_database/references/eda.md`, `veupathdb_database/SKILL.md`
- Test: `veupathdb_database/tests/test_filters.py`

**Interfaces:**
- Consumes: `_contrasts.canonical_filters`; the `read_filters(args, t)` hook every command already calls (Task 4)
- Produces:
  - `_samples.validate_filters(filters, index) -> filters` (raises `SampleError` with suggestions)
  - `--filters JSON|FILE` on every command that uses `_target_args` (study, contrasts, de, de-spec, and pca in Task 18), parsed with `json_arg` (Task 10): inline JSON or a file. It holds a JSON array of EDA filters, `{"filters": [...]}`, or a whole analysis spec (its `descriptor.subset.descriptor` is used).

- [ ] **Step 1: Write the failing tests**

Create `veupathdb_database/tests/test_filters.py`:

```python
import json

import pytest
from eda_helpers import eda_fixture

FEBRILE = [{"entityId": "ENT_8151325d", "variableId": "VAR_081ab087", "type": "stringSet", "stringSet": ["febrile"]}]


def _index():
    from _samples import index_entities

    return index_entities(eda_fixture("study_heatshock.json")["rootEntity"])


def test_validate_filters_accepts_known_values():
    from _samples import validate_filters

    assert validate_filters(FEBRILE, _index()) == FEBRILE


@pytest.mark.parametrize(
    "bad, needle",
    [
        ([{"entityId": "ENT_8151325", "variableId": "VAR_081ab087", "type": "stringSet", "stringSet": ["febrile"]}], "ENT_8151325d"),
        ([{"entityId": "ENT_8151325d", "variableId": "VAR_081ab08", "type": "stringSet", "stringSet": ["febrile"]}], "VAR_081ab087"),
        ([{"entityId": "ENT_8151325d", "variableId": "VAR_081ab087", "type": "stringSet", "stringSet": ["febril"]}], "febrile"),
        ([{"entityId": "ENT_8151325d", "variableId": "VAR_081ab087", "type": "regex", "stringSet": ["x"]}], "stringSet"),
        ([{"entityId": "ENT_8151325d", "variableId": "VAR_7033e90f", "type": "numberRange", "min": 41}], "max"),
        ([{"entityId": "ENT_8151325d", "variableId": "VAR_7033e90f", "type": "numberRange", "min": 41, "max": 37}], "min > max"),
        (["not an object"], "object"),
    ],
)
def test_validate_filters_rejects_with_hints(bad, needle):
    from _samples import SampleError, validate_filters

    with pytest.raises(SampleError) as e:
        validate_filters(bad, _index())
    assert needle in str(e.value)


@pytest.fixture
def filter_file(tmp_path):
    def make(content):
        p = tmp_path / "filters.json"
        p.write_text(json.dumps(content))
        return str(p)

    return make


def test_study_with_filters_shows_subset(run_eda, filter_file):
    out = run_eda("study", "plasmodb", "DS_e973eadd57", "--filters", filter_file(FEBRILE))
    assert 'ENT_8151325d "Sample" — 6 of 12 records' in out
    assert "febrile 6" in out and "normal" not in out.split("temperature_condition", 1)[1].splitlines()[0]


def test_filter_file_forms_are_equivalent(run_eda, filter_file):
    spec = {"descriptor": {"subset": {"descriptor": FEBRILE}}}
    a = json.loads(run_eda("study", "plasmodb", "DS_e973eadd57", "--json", "--filters", filter_file(FEBRILE)))
    b = json.loads(run_eda("study", "plasmodb", "DS_e973eadd57", "--json", "--filters", filter_file({"filters": FEBRILE})))
    c = json.loads(run_eda("study", "plasmodb", "DS_e973eadd57", "--json", "--filters", filter_file(spec)))
    assert a == b == c and a["filters"] == FEBRILE and len(a["samples"]) == 6


def test_contrasts_and_de_carry_filters(run_eda, eda_mock, filter_file):
    path = filter_file(FEBRILE)
    out = json.loads(run_eda("contrasts", "plasmodb", "DS_e973eadd57", "--json", "--filters", path))
    assert not any(c["comparator"]["variableId"] == "VAR_081ab087" for c in out["candidates"])
    assert any(s["variableId"] == "VAR_081ab087" for s in out["skipped"])
    first = out["candidates"][0]
    assert all(f in first["filters"] for f in FEBRILE)
    de = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", "1", "--filters", path, "--json"))
    assert de["context"]["filters"] == first["filters"]
    assert eda_mock.compute_bodies("differentialexpression")[-1]["filters"] == first["filters"]
    spec = json.loads(run_eda("de-spec", "plasmodb", "DS_e973eadd57", "--contrast", "1", "--filters", path))
    assert spec["descriptor"]["subset"]["descriptor"] == first["filters"]


def test_inline_filters_equal_file(run_eda, filter_file):
    a = json.loads(run_eda("study", "plasmodb", "DS_e973eadd57", "--json", "--filters", filter_file(FEBRILE)))
    b = json.loads(run_eda("study", "plasmodb", "DS_e973eadd57", "--json", "--filters", json.dumps(FEBRILE)))
    c = json.loads(run_eda("study", "plasmodb", "DS_e973eadd57", "--json", "--filters", json.dumps({"filters": FEBRILE})))
    assert a == b == c


def test_bad_filter_file_fails_cleanly(run_eda, filter_file, tmp_path, capsys):
    with pytest.raises(SystemExit):
        run_eda("study", "plasmodb", "DS_e973eadd57", "--filters", str(tmp_path / "missing.json"))
    assert "not found" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        run_eda("study", "plasmodb", "DS_e973eadd57", "--filters", "[{")
    assert "inline JSON is not valid" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        run_eda("study", "plasmodb", "DS_e973eadd57", "--filters", filter_file({"x": 1}))
    assert "JSON array" in capsys.readouterr().err


def test_contrast_file_filters_are_validated(run_eda, tmp_path, capsys):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"comparator": {"variableId": "VAR_84f17484"}, "groupA": [{"label": "wildtype"}],
                             "groupB": [{"label": "delta-DHC mutant"}],
                             "filters": [dict(FEBRILE[0], stringSet=["hot"])]}))
    with pytest.raises(SystemExit):
        run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", str(p))
    assert "hot" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_filters.py -q`
Expected: FAIL (`cannot import name 'validate_filters'`; `unrecognized arguments: --filters`).

- [ ] **Step 3: Implement**

Append to `_samples.py`:

```python
FILTER_FIELDS = {
    "stringSet": ("stringSet",),
    "numberSet": ("numberSet",),
    "dateSet": ("dateSet",),
    "numberRange": ("min", "max"),
    "dateRange": ("min", "max"),
    "longitudeRange": ("left", "right"),
}


def validate_filters(filters, index):
    """Check EDA subset filters against the study metadata, with suggestions."""
    import difflib

    variables = {
        eid: {v["id"]: v for v in node["entity"].get("variables", []) if v.get("type") != "category"}
        for eid, node in index.items()
    }
    for f in filters:
        if not isinstance(f, dict):
            raise SampleError(f"each filter must be an object, got {f!r}")
        eid, vid, ftype = f.get("entityId"), f.get("variableId"), f.get("type")
        if eid not in variables:
            hint = difflib.get_close_matches(str(eid), list(variables), n=3, cutoff=0.5)
            raise SampleError(f"filter entity {eid!r} is not in this study; did you mean {hint}?")
        if vid not in variables[eid]:
            hint = difflib.get_close_matches(str(vid), list(variables[eid]), n=3, cutoff=0.5)
            raise SampleError(f"filter variable {vid!r} is not on {eid}; did you mean {hint}?")
        if ftype not in FILTER_FIELDS:
            raise SampleError(f"filter type {ftype!r} is not supported; use one of {sorted(FILTER_FIELDS)}")
        missing = [k for k in FILTER_FIELDS[ftype] if k not in f]
        if missing:
            raise SampleError(f"{ftype} filter on {vid} needs {missing}")
        vocab = variables[eid][vid].get("vocabulary")
        if ftype == "stringSet" and vocab:
            bad = [s for s in f["stringSet"] if s not in vocab]
            if bad:
                hints = {b: difflib.get_close_matches(str(b), vocab, n=2, cutoff=0.5) for b in bad}
                raise SampleError(f"unknown value(s) {bad} for {vid}; did you mean {hints}? vocabulary: {vocab[:20]}")
        if ftype in ("numberRange", "dateRange") and f["min"] > f["max"]:
            raise SampleError(f"{ftype} filter on {vid} has min > max")
    return filters
```

In `eda.py`, replace `read_filters` with:

```python
def _load_filters(raw):
    from _samples import SampleError

    data = json_arg(raw, "--filters", "inline JSON or a filters file")
    if isinstance(data, dict) and "filters" in data:
        data = data["filters"]
    elif isinstance(data, dict) and "descriptor" in data:
        data = ((data.get("descriptor") or {}).get("subset") or {}).get("descriptor", [])
    if not isinstance(data, list):
        raise SampleError('--filters must hold a JSON array of EDA filters, {"filters": [...]}, or an analysis spec')
    return data


def read_filters(args, t):
    """Validated, canonical sample filters from --filters (empty without it)."""
    from _contrasts import canonical_filters
    from _samples import validate_filters

    raw = getattr(args, "filters", None)
    if not raw:
        return []
    return canonical_filters(validate_filters(_load_filters(raw), t["index"]))
```

In `resolve_contrast`, just before `return load_contrast(...)`, add:

```python
    from _samples import validate_filters

    if isinstance(obj, dict) and obj.get("filters"):
        validate_filters(obj["filters"], t["index"])
```

In `_target_args`, add:

```python
    sp.add_argument("--filters", help="inline JSON or a JSON file restricting the samples: an array of EDA "
                                      'filters, {"filters": [...]}, or a saved analysis spec')
```

- [ ] **Step 4: Run the tests and the suite**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_filters.py -q && uv run --with pytest --with httpx python -m pytest tests -q`
Expected: PASS.

- [ ] **Step 5: Document**

Append to `references/eda.md`, after `## Contrasts`:

````markdown
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
````

In `SKILL.md`, change the sentence after the EDA steps to:

```markdown
Pass the same `--filters`, `--vars`, `--value-var` and `--entity` to every command
after `contrasts`, or `--contrast N` names a different candidate. `study --filters '[…]'`
previews a sample subset.
```

- [ ] **Step 6: Commit**

```bash
git add veupathdb_database/scripts/_samples.py veupathdb_database/scripts/eda.py veupathdb_database/tests/test_filters.py veupathdb_database/references/eda.md veupathdb_database/SKILL.md
git commit -m "feat(eda): --filters with validation on study, contrasts, de and de-spec

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Stage 3: PCA

### Task 17: `_stats.py` with R gold-standard tests

**Files:**
- Create: `veupathdb_database/scripts/_stats.py`
- Test: `veupathdb_database/tests/test_stats.py`, `veupathdb_database/tests/test_stats_r.py`

**Interfaces:**
- Consumes: nothing (standard library only: `math`, `collections`)
- Produces (in `_stats`):
  - `MIN_SCORED_N = 3`, `MIN_OUTLIER_N = 5`, `OUTLIER_Z = 3.0`
  - `pearson(xs, ys) -> float | None` (None for zero variance)
  - `eta_squared(groups, ys) -> float | None`
  - `score_against_pc(kind, values, pc) -> {"stat": "r", "r", "r2", "value", "n"} | {"stat": "eta2", "eta2", "value", "n", "levels"} | {"n", "levels"?, "not_scored": reason}` (`kind` is `"continuous"` or `"categorical"`)
  - `outliers(points, threshold=OUTLIER_Z, min_n=MIN_OUTLIER_N) -> {"threshold", "pcs", "samples": [{"sampleId", "distance"}]} | {"not_scored", "samples": []}`

- [ ] **Step 1: Write the failing unit tests**

Create `veupathdb_database/tests/test_stats.py`:

```python
import math

import pytest


def test_pearson_and_zero_variance():
    from _stats import pearson

    assert pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
    assert pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)
    assert pearson([1, 1, 1], [1, 2, 3]) is None


def test_eta_squared_simple():
    from _stats import eta_squared

    assert eta_squared(["a", "a", "b", "b"], [1.0, 1.0, 3.0, 3.0]) == pytest.approx(1.0)
    assert eta_squared(["a", "b", "a", "b"], [1.0, 1.0, 3.0, 3.0]) == pytest.approx(0.0)
    assert eta_squared(["a", "b"], [2.0, 2.0]) is None


@pytest.mark.parametrize(
    "kind, values, pc, reason",
    [
        ("categorical", ["a", None, None, "b"], [1.0, 2.0, 3.0, 4.0], "fewer than 3"),
        ("categorical", ["a"] * 5, [1.0, 2.0, 3.0, 4.0, 5.0], "constant"),
        ("continuous", [2.0] * 4, [1.0, 2.0, 3.0, 4.0], "constant"),
        ("categorical", ["a", "a", "b", "b"], [1.0, 1.0, 1.0, 1.0], "zero variance"),
        ("categorical", ["a", "b", "c", "d"], [1.0, 2.0, 3.0, 4.0], "eta² would be 1"),
    ],
)
def test_score_edge_cases_are_reported_not_scored(kind, values, pc, reason):
    from _stats import score_against_pc

    out = score_against_pc(kind, values, pc)
    assert reason in out["not_scored"] and "value" not in out


def test_score_categorical_with_a_singleton_level_is_scored():
    from _stats import score_against_pc

    out = score_against_pc("categorical", ["a", "a", "b", "c"], [1.0, 1.2, 3.0, 5.0])
    assert out["stat"] == "eta2" and out["levels"] == 3 and out["n"] == 4
    assert 0 < out["value"] <= 1


def test_score_continuous():
    from _stats import score_against_pc

    out = score_against_pc("continuous", [1.0, 2.0, None, 4.0], [2.0, 4.1, 9.0, 7.9])
    assert out["stat"] == "r" and out["n"] == 3
    assert out["r2"] == pytest.approx(out["r"] ** 2) == out["value"]


def test_outliers_flags_a_far_point():
    from _stats import outliers

    pts = [(0, 0.1), (0.2, -0.1), (-0.1, 0.3), (0.3, 0), (-0.2, -0.2), (0.1, 0.2), (0, -0.3), (-0.3, 0.1), (0.2, 0.2), (100, 100)]
    out = outliers({f"s{i}": list(p) for i, p in enumerate(pts)})
    assert [s["sampleId"] for s in out["samples"]] == ["s9"]
    assert out["samples"][0]["distance"] > 3 and out["pcs"] == 2


def test_outliers_not_scored_cases():
    from _stats import outliers

    assert "fewer than 5" in outliers({"a": [1.0, 2.0], "b": [2.0, 1.0]})["not_scored"]
    flat = {f"s{i}": [1.0, float(i)] for i in range(6)}
    assert "zero SD" in outliers(flat)["not_scored"]
    with_missing = {f"s{i}": [float(i), float(i % 3)] for i in range(6)}
    with_missing["s9"] = [None, 1.0]
    assert outliers(with_missing)["samples"] == []
```

- [ ] **Step 2: Write the R gold-standard tests**

Create `veupathdb_database/tests/test_stats_r.py`:

```python
"""R gold standard for _stats.py: base R's cor() and lm() on the same inputs.
R is a development dependency only; these tests skip without Rscript."""
import csv
import shutil
import subprocess

import pytest
from eda_helpers import eda_fixture

RSCRIPT = shutil.which("Rscript")
pytestmark = pytest.mark.skipif(
    RSCRIPT is None, reason="Rscript not on PATH: the R gold-standard tests need base R (development only)"
)
TOL = 1e-9  # relative; near-constant inputs lose precision in any implementation
NEAR_CONSTANT_TOL = 1e-5


def r_value(tmp_path, rows, expr):
    """Evaluate a numeric R expression over d (columns g, x, y; NA for None)."""
    path = tmp_path / "d.csv"
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["g", "x", "y"])
        for g, x, y in rows:
            w.writerow(["NA" if g is None else g,
                        "NA" if x is None else repr(float(x)),
                        "NA" if y is None else repr(float(y))])
    code = (f'd <- read.csv("{path}", stringsAsFactors=FALSE, na.strings="NA", '
            f'colClasses=c("character","numeric","numeric")); cat(sprintf("%.17g", {expr}))')
    out = subprocess.run([RSCRIPT, "--vanilla", "-e", code], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def close(a, b, tol):
    return abs(a - b) <= tol * max(1.0, abs(b))


def complete(*cols):
    keep = [row for row in zip(*cols) if all(v is not None for v in row)]
    return [list(c) for c in zip(*keep)]


PEARSON = {
    "missing": ([1, 2, None, 4, 5, 6], [2.1, 3.9, 6.2, None, 9.8, 12.5], TOL),
    "ties": ([1, 1, 2, 2, 3, 3], [0.5, 0.7, 0.2, 0.9, 1.5, 1.1], TOL),
    "negative": ([10, 20, 30, 40], [4.0, 3.5, 1.0, 0.2], TOL),
    "near_constant": ([1, 1, 1, 1, 1 + 1e-9], [3.0, 1.0, 4.0, 1.0, 5.0], NEAR_CONSTANT_TOL),
}
ETA = {
    "missing": (["a", "a", None, "b", "b", "c", "c"], [1.0, 1.4, 9.0, 3.0, None, 5.5, 5.1], TOL),
    "singleton_level": (["a", "a", "a", "b", "b", "c"], [1.0, 2.0, 1.5, 4.0, 4.4, 9.0], TOL),
    "ties": (["a", "a", "b", "b", "c", "c"], [1.0, 1.0, 2.0, 2.0, 2.0, 3.0], TOL),
    "near_constant": (["a", "a", "b", "b"], [1.0, 1.0, 1.0, 1.0 + 1e-9], NEAR_CONSTANT_TOL),
}


@pytest.mark.parametrize("case", sorted(PEARSON))
def test_pearson_matches_r(tmp_path, case):
    from _stats import pearson

    xs, ys, tol = PEARSON[case]
    want = r_value(tmp_path, [("a", x, y) for x, y in zip(xs, ys)], 'cor(d$x, d$y, use="complete.obs")')
    got = pearson(*complete(xs, ys))
    assert close(got, want, tol), (got, want)


@pytest.mark.parametrize("case", sorted(ETA))
def test_eta_squared_matches_r(tmp_path, case):
    from _stats import eta_squared

    gs, ys, tol = ETA[case]
    want = r_value(tmp_path, [(g, 0, y) for g, y in zip(gs, ys)], "summary(lm(y ~ factor(g), data=d))$r.squared")
    got = eta_squared(*complete(gs, ys))
    assert close(got, want, tol), (got, want)


def _heatshock():
    pcs = {}
    for line in eda_fixture("pca_heatshock_tabular.tsv").strip().splitlines()[1:]:
        cells = line.split("\t")
        pcs[cells[0]] = (float(cells[1]), float(cells[2]))
    tab = eda_fixture("tabular_heatshock_sample.json")
    rows = [dict(zip(tab[0], r)) for r in tab[1:]]
    return rows, pcs, tab[0][0]


@pytest.mark.parametrize("var, k, expected", [("VAR_081ab087", 0, 0.7751), ("VAR_26d10fbf", 1, 0.4964)])
def test_heatshock_eta_squared_matches_r(tmp_path, var, k, expected):
    from _stats import eta_squared

    rows, pcs, key = _heatshock()
    gs = [r[var] for r in rows]
    ys = [pcs[r[key]][k] for r in rows]
    want = r_value(tmp_path, [(g, 0, y) for g, y in zip(gs, ys)], "summary(lm(y ~ factor(g), data=d))$r.squared")
    got = eta_squared(gs, ys)
    assert close(got, want, TOL)
    assert round(got, 4) == expected  # Verified live facts


def test_heatshock_pearson_temperature_matches_r(tmp_path):
    from _stats import pearson

    rows, pcs, key = _heatshock()
    xs = [float(r["VAR_7033e90f"]) for r in rows]
    ys = [pcs[r[key]][0] for r in rows]
    want = r_value(tmp_path, [("a", x, y) for x, y in zip(xs, ys)], "cor(d$x, d$y)")
    assert close(pearson(xs, ys), want, TOL)
```

- [ ] **Step 3: Run them to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_stats.py tests/test_stats_r.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named '_stats'` (the R tests SKIP instead if `Rscript` is missing).

- [ ] **Step 4: Implement**

Create `veupathdb_database/scripts/_stats.py`:

```python
"""Statistics for eda.py, standard library only. Base R is the test-time gold
standard (tests/test_stats_r.py); nothing here needs R at use time."""
import math
from collections import Counter, defaultdict

MIN_SCORED_N = 3
MIN_OUTLIER_N = 5
OUTLIER_Z = 3.0


def mean(xs):
    return math.fsum(xs) / len(xs)


def sum_sq(xs):
    m = mean(xs)
    return math.fsum((x - m) ** 2 for x in xs)


def pearson(xs, ys):
    """Pearson r, or None when either side has zero variance."""
    mx, my = mean(xs), mean(ys)
    sxx = math.fsum((x - mx) ** 2 for x in xs)
    syy = math.fsum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


def eta_squared(groups, ys):
    """One-way ANOVA eta² = SS_between / SS_total (= R² of lm(y ~ factor(g)))."""
    total = sum_sq(ys)
    if total == 0:
        return None
    by = defaultdict(list)
    for g, y in zip(groups, ys):
        by[g].append(y)
    m = mean(ys)
    between = math.fsum(len(v) * (mean(v) - m) ** 2 for v in by.values())
    return between / total


def score_against_pc(kind, values, pc):
    """Association of one sample variable with one PC, or a 'not scored' reason.
    Samples missing either value are dropped first; n is what remains."""
    pairs = [(x, y) for x, y in zip(values, pc) if x is not None and y is not None]
    n = len(pairs)
    if n < MIN_SCORED_N:
        return {"n": n, "not_scored": f"fewer than {MIN_SCORED_N} samples with a value"}
    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    counts = Counter(xs)
    if len(counts) < 2:
        return {"n": n, "not_scored": "constant: one distinct value among these samples"}
    if sum_sq(ys) == 0:
        return {"n": n, "not_scored": "PC has zero variance"}
    if kind == "continuous":
        r = pearson(xs, ys)
        return {"stat": "r", "r": r, "r2": r * r, "value": r * r, "n": n}
    if max(counts.values()) < 2:
        return {"n": n, "levels": len(counts),
                "not_scored": "no level has 2+ samples: eta² would be 1 by construction"}
    e = eta_squared(xs, ys)
    return {"stat": "eta2", "eta2": e, "value": e, "n": n, "levels": len(counts)}


def outliers(points, threshold=OUTLIER_Z, min_n=MIN_OUTLIER_N):
    """points: {sampleId: [pc1, pc2, …]}. Flags samples whose standardised distance
    sqrt(sum_k z_k²) from the centroid exceeds `threshold` (z per PC, sample SD)."""
    complete = {s: p for s, p in points.items() if p and all(v is not None for v in p)}
    if len(complete) < min_n:
        return {"not_scored": f"fewer than {min_n} samples with scores", "samples": []}
    dims = len(next(iter(complete.values())))
    cols = [[p[k] for p in complete.values()] for k in range(dims)]
    means = [mean(c) for c in cols]
    sds = [math.sqrt(sum_sq(c) / (len(c) - 1)) for c in cols]
    if any(sd == 0 for sd in sds):
        return {"not_scored": "a PC has zero SD", "samples": []}
    flagged = []
    for s, p in complete.items():
        d = math.sqrt(math.fsum(((v - m) / sd) ** 2 for v, m, sd in zip(p, means, sds)))
        if d > threshold:
            flagged.append({"sampleId": s, "distance": round(d, 2)})
    return {"threshold": threshold, "pcs": dims, "samples": sorted(flagged, key=lambda f: -f["distance"])}
```

- [ ] **Step 5: Run the tests**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_stats.py tests/test_stats_r.py -v`
Expected: PASS, with the R tests running (not skipped) on the development machine. A tolerance failure on a non-near-constant case is a bug in `_stats.py`; do not widen `TOL`.

- [ ] **Step 6: Register and commit**

Append to `TESTS.md`:

```
| STATS-R-1 | tests/test_stats_r.py (needs Rscript) | pearson and eta² equal base R cor()/lm() r.squared | relative 1e-9 (1e-5 near-constant) | heat-shock eta² PC1 temperature 0.7751, PC2 strain 0.4964 | 2026-10-03 |
```

```bash
git add veupathdb_database/scripts/_stats.py veupathdb_database/tests/test_stats.py veupathdb_database/tests/test_stats_r.py veupathdb_database/TESTS.md
git commit -m "feat(eda): stdlib statistics for PCA scoring, with base-R gold tests

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 18: `eda.py pca`

**Files:**
- Create: `veupathdb_database/scripts/_pca.py`
- Modify: `veupathdb_database/scripts/eda.py` (`cmd_pca`, parser)
- Modify: `veupathdb_database/tests/test_eda_live.py`, `veupathdb_database/TESTS.md`, `veupathdb_database/references/eda.md`, `veupathdb_database/SKILL.md`
- Test: `veupathdb_database/tests/test_pca.py`

**Interfaces:**
- Consumes: `_stats.score_against_pc`, `outliers`; `_contrasts.PLUGIN_PCA`, `pca_config`, `compute_body`, `choose_value_var`; `_eda.wait_for_job`, `compute_file`; `eda.sample_view`, `read_filters`
- Produces (in `_pca`):
  - `parse_scores(tsv) -> (pcs: list[str], scores: {sampleId: [float | None]})`
  - `parse_variance(meta) -> {pc: percent | None}`
  - `pca_report(pcs, scores, variance, rows, var_meta, outlier_pcs=2) -> {"pcs", "samples", "unmatched", "tracks", "notScored", "outliers", "scores"}`
  - `render_pca(report, top=5) -> list[str]`
  - CLI: `pca SITE DATASET [--filters JSON|FILE] [--value-var V] [--npcs N] [--top N] [--json] [--timeout S]`

- [ ] **Step 1: Write the failing tests**

Create `veupathdb_database/tests/test_pca.py`:

```python
import json

import pytest
from eda_helpers import eda_fixture


def test_parse_variance_and_scores():
    from _pca import parse_scores, parse_variance

    assert parse_variance(eda_fixture("pca_heatshock_meta.json")) == {"PC1": 54.35, "PC2": 12.79}
    assert parse_variance({"variables": [{"variableSpec": {"variableId": "PC1"}, "displayName": "PC 1"}]}) == {"PC1": None}
    pcs, scores = parse_scores(eda_fixture("pca_heatshock_tabular.tsv"))
    assert pcs == ["PC1", "PC2"] and len(scores) == 12
    assert scores["WT_41C_Rep2"][0] == pytest.approx(63.5443711576177)


def test_parse_scores_with_ancestor_columns_and_na():
    from _pca import parse_scores

    tsv = "S.id\tP.id\tPC1\tPC2\ns1\tp1\t1.5\tNA\ns2\tp1\t-2\t0.5\n"
    pcs, scores = parse_scores(tsv)
    assert pcs == ["PC1", "PC2"] and scores == {"s1": [1.5, None], "s2": [-2.0, 0.5]}


def _report():
    from _pca import parse_scores, parse_variance, pca_report
    from _samples import ancestors, build_sample_table, index_entities, variable_meta

    index = index_entities(eda_fixture("study_heatshock.json")["rootEntity"])
    meta = variable_meta(index, ancestors(index, "ENT_fd574cd6"))
    table = build_sample_table(lambda e, ids: eda_fixture("tabular_heatshock_sample.json"), index, "ENT_fd574cd6", meta)
    pcs, scores = parse_scores(eda_fixture("pca_heatshock_tabular.tsv"))
    return pca_report(pcs, scores, parse_variance(eda_fixture("pca_heatshock_meta.json")), table["rows"], meta)


def test_pca_report_heatshock():
    rep = _report()
    assert rep["samples"] == 12 and rep["unmatched"] == []
    temp = next(e for e in rep["tracks"]["PC1"] if e["variableId"] == "VAR_081ab087")
    assert temp["eta2"] == pytest.approx(0.7751, abs=1e-4) and temp["n"] == 12 and temp["levels"] == 2
    strain = next(e for e in rep["tracks"]["PC2"] if e["variableId"] == "VAR_26d10fbf")
    assert strain["eta2"] == pytest.approx(0.4964, abs=1e-4)
    values = [e["value"] for e in rep["tracks"]["PC1"]]
    assert values == sorted(values, reverse=True)
    assert rep["outliers"]["samples"] == []
    sra = [e for e in rep["notScored"] if e["variableId"] == "VAR_ebaebced"]
    assert {e["pc"] for e in sra} == {"PC1", "PC2"} and "eta² would be 1" in sra[0]["not_scored"]
    json.dumps(rep, allow_nan=False)


def test_render_pca_groups_not_scored():
    from _pca import render_pca

    rep = _report()
    rep.update(datasetId="DS_e973eadd57", valueVariable="SEQUENCE_READ_COUNT_SENSE", dataFormat="rawCounts", jobId="j", notes=[])
    lines = render_pca(rep)
    assert lines[1].startswith("PC1 (54.35% variance) tracks:")
    assert any("not scored: SRA ID(s) (VAR_ebaebced) on PC1, PC2" in l for l in lines)
    assert any(l.startswith("outliers") and l.endswith("none") for l in lines)


def test_pca_cli_uses_notebook_config(run_eda, eda_mock):
    out = run_eda("pca", "plasmodb", "DS_e973eadd57")
    assert "PC1 (54.35% variance) tracks:" in out and "temperature_condition" in out
    body = eda_mock.compute_bodies("dimensionalityreduction")[-1]
    assert body == eda_fixture("jobs.json")["pca_heatshock"]["body"]
    paths = [p for m, p, q, b in eda_mock.requests]
    assert "/computes/dimensionalityreduction/tabular" in paths and "/computes/dimensionalityreduction/meta" in paths
    rep = json.loads(run_eda("pca", "plasmodb", "DS_e973eadd57", "--json"))
    assert rep["jobId"] == eda_mock.pca_job and rep["dataFormat"] == "rawCounts"


def test_pca_npcs_is_a_separate_job(run_eda, eda_mock):
    rep = json.loads(run_eda("pca", "plasmodb", "DS_e973eadd57", "--npcs", "5", "--json"))
    assert eda_mock.compute_bodies("dimensionalityreduction")[-1]["config"]["nPCs"] == 5
    assert any("separate job" in n for n in rep["notes"])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_pca.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named '_pca'`.

- [ ] **Step 3: Implement `_pca.py`**

Create `veupathdb_database/scripts/_pca.py`:

```python
"""PCA output parsing and reporting. The EDA compute returns only per-sample scores;
variance explained is parsed from computed-variable display names (fragile: a
candidate server-side change), and every association is computed locally."""
import math
import re

from _eda import EdaError
from _samples import NUMERIC_TYPES
from _stats import outliers, score_against_pc

_VARIANCE = re.compile(r"PC\s*(\d+)\s*\(\s*([0-9.]+)\s*%\s*variance\s*\)", re.IGNORECASE)
_PC = re.compile(r"PC\d+")


def _num(cell):
    try:
        x = float(cell)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def parse_scores(tsv):
    lines = [line for line in tsv.splitlines() if line.strip()]
    if not lines:
        raise EdaError("PCA tabular output is empty")
    header = lines[0].split("\t")
    cols = [i for i, h in enumerate(header) if _PC.fullmatch(h)]
    if not cols:
        raise EdaError(f"no PC columns in the PCA output header: {header}")
    scores = {}
    for line in lines[1:]:
        cells = line.split("\t")
        scores[cells[0]] = [_num(cells[i]) if i < len(cells) else None for i in cols]
    return [header[i] for i in cols], scores


def parse_variance(meta):
    out = {}
    for v in meta.get("variables", []):
        m = _VARIANCE.search(v.get("displayName", ""))
        out[v["variableSpec"]["variableId"]] = float(m.group(2)) if m else None
    return out


def pca_report(pcs, scores, variance, rows, var_meta, outlier_pcs=2):
    by_sample = {r["sampleId"]: r for r in rows}
    sample_ids = [s for s in scores if s in by_sample]
    tracks, not_scored = {}, []
    for k, pc in enumerate(pcs):
        pc_values = [scores[s][k] for s in sample_ids]
        ranked = []
        for vid, meta in var_meta.items():
            kind = "continuous" if meta.get("type") in NUMERIC_TYPES else "categorical"
            res = score_against_pc(kind, [by_sample[s].get(vid) for s in sample_ids], pc_values)
            entry = {"pc": pc, "variableId": vid, "displayName": meta["displayName"], **res}
            (not_scored if "not_scored" in res else ranked).append(entry)
        tracks[pc] = sorted(ranked, key=lambda e: (-e["value"], e["variableId"]))
    return {
        "pcs": [{"pc": pc, "variance": variance.get(pc)} for pc in pcs],
        "samples": len(sample_ids),
        "unmatched": sorted(set(scores) - set(by_sample)),
        "tracks": tracks,
        "notScored": not_scored,
        "outliers": outliers({s: scores[s][:outlier_pcs] for s in sample_ids}),
        "scores": {s: dict(zip(pcs, scores[s])) for s in sample_ids},
    }


def render_pca(report, top=5):
    lines = [
        f"PCA {report['datasetId']}  value={report['valueVariable']}  dataFormat={report['dataFormat']}  "
        f"job {report['jobId']}  {report['samples']} samples"
    ]
    for pc in report["pcs"]:
        var = f"{pc['variance']:g}% variance" if pc["variance"] is not None else "variance unknown"
        lines.append(f"{pc['pc']} ({var}) tracks:")
        ranked = report["tracks"][pc["pc"]][:top]
        if not ranked:
            lines.append("  (no scorable variables)")
        for e in ranked:
            if e["stat"] == "r":
                lines.append(f"  {e['displayName']} ({e['variableId']})  r={e['r']:+.2f} R²={e['r2']:.2f}  n={e['n']}")
            else:
                lines.append(f"  {e['displayName']} ({e['variableId']})  eta²={e['eta2']:.2f}  n={e['n']}, {e['levels']} levels")
    o = report["outliers"]
    if o.get("not_scored"):
        lines.append(f"outliers: not scored ({o['not_scored']})")
    else:
        head = f"outliers (standardised distance > {o['threshold']:g} in PC1–PC{o['pcs']})"
        if o["samples"]:
            found = ", ".join(f"{s['sampleId']} ({s['distance']})" for s in o["samples"])
            lines.append(f"{head}: {found}  → candidates for --filters")
        else:
            lines.append(f"{head}: none")
    grouped = {}
    for e in report["notScored"]:
        grouped.setdefault((e["displayName"], e["variableId"], e["not_scored"]), []).append(e["pc"])
    for (name, vid, reason), pcs in grouped.items():
        lines.append(f"not scored: {name} ({vid}) on {', '.join(pcs)}: {reason}")
    if report["unmatched"]:
        lines.append(f"PCA samples missing from the sample table: {', '.join(report['unmatched'][:10])}")
    lines += [f"note: {n}" for n in report["notes"]]
    return lines
```

- [ ] **Step 4: Implement `cmd_pca`**

Add to `eda.py` after `cmd_de_datasets`:

```python
def cmd_pca(args) -> None:
    from _contrasts import PLUGIN_PCA, choose_value_var, compute_body, pca_config
    from _eda import EdaError, compute_file, wait_for_job
    from _pca import parse_scores, parse_variance, pca_report, render_pca

    t = load_target(args)
    filters = read_filters(args, t)
    view = sample_view(t, filters)
    if view["table"] is None:
        raise EdaError(f"{', '.join(view['too_big'])} has too many records for the joint sample table; narrow it with --filters")
    value_var, vnote = choose_value_var(t["expr"], args.value_var)
    body = compute_body(t["dataset"]["studyId"], pca_config(t["expr"]["entityId"], value_var, args.npcs), filters)
    c = t["client"]
    st = wait_for_job(c, PLUGIN_PCA, body, timeout_s=args.timeout, log=log)
    if st["status"] != "complete":
        raise EdaError(f"PCA job {st['jobID']} is {st['status']}")
    pcs, scores = parse_scores(compute_file(c, PLUGIN_PCA, body, "tabular"))
    variance = parse_variance(json.loads(compute_file(c, PLUGIN_PCA, body, "meta")))
    report = pca_report(pcs, scores, variance, view["table"]["rows"], view["meta"])
    notes = [n for n in (vnote,) if n]
    if args.npcs:
        notes.append(f"--npcs {args.npcs}: an explicit nPCs is a separate job from the website's PCA")
    if any(v is None for v in variance.values()):
        notes.append("variance explained could not be parsed from the PC labels")
    report.update(jobId=st["jobID"], datasetId=t["dataset"]["datasetId"], valueVariable=value_var,
                  dataFormat=body["config"]["dataFormat"], filters=filters, notes=notes)
    if args.json:
        emit(report)
    else:
        print("\n".join(render_pca(report, top=args.top)))
```

In `build_parser`, before `return p`:

```python
    sp = sub.add_parser("pca", help="PCA (website notebook config): variables that track each PC, outliers")
    _target_args(sp)
    sp.add_argument("--value-var", help="expression value variable (default as for contrasts)")
    sp.add_argument("--npcs", type=int, help="ask for N PCs (a separate job; default = the notebook's 2)")
    sp.add_argument("--top", type=int, default=5, help="variables listed per PC")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--timeout", type=int, default=900)
    sp.set_defaults(func=cmd_pca)
```

- [ ] **Step 5: Run the tests and the suite**

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_pca.py -q && uv run --with pytest --with httpx python -m pytest tests -q`
Expected: PASS.

- [ ] **Step 6: Add the live PCA gold test**

Append to `veupathdb_database/tests/test_eda_live.py`:

```python
def test_live_pca_heatshock(live_eda):
    rep = json.loads(live_eda("pca", "plasmodb", HS, "--json"))
    assert rep["jobId"] == "2679abb0e5c81b345a21b8f211db6a9b"
    assert [p["variance"] for p in rep["pcs"]] == pytest.approx([54.35, 12.79], abs=0.05)
    temp = next(e for e in rep["tracks"]["PC1"] if e["variableId"] == "VAR_081ab087")
    assert temp["eta2"] == pytest.approx(0.7751, abs=0.05)
    assert rep["outliers"]["samples"] == []
```

Run: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests/test_eda_live.py -q -k pca`
Expected: PASS with a token.

Append to `TESTS.md`:

```
| EDA-9 | `eda.py pca plasmodb DS_e973eadd57` / test_eda_live.py::test_live_pca_heatshock | notebook-config PCA reused; PC1/PC2 variance; temperature tracks PC1; no outliers | exact job id; range ±0.05 | 2679abb0…; 54.35%, 12.79%; eta² 0.7751 | 2026-10-03 |
```

- [ ] **Step 7: Document**

Append to `references/eda.md`:

````markdown
## PCA (`eda.py pca`)

Runs the notebook's PCA (`dimensionalityreduction`, `rawCounts` for RNA-Seq,
`normalizedValues` for arrays, no explicit nPCs), so the job is the one website users
share; `--npcs N` is a separate job, for when batch effects may sit on PC3 or PC4.
EDA returns only per-sample scores. Everything else is computed locally:

- **tracks**: for each PC separately, each sample variable is scored: Pearson r and R²
  for numeric variables, eta² (one-way ANOVA) for categorical ones, with the n used and
  the number of levels. There is no combined score: weigh PC1 hits above PC2 hits using
  the variance explained.
- eta² inflates as the number of levels approaches n (a 6-level label in 12 samples
  scores high by construction). Check `levels` and `n` before reading it as an effect.
- **not scored** (never silently dropped): fewer than 3 samples with a value; a
  constant variable (common after `--filters`); no level with 2+ samples
  (identifier-like); a PC with zero variance.
- **outliers**: samples whose standardised distance from the centroid in PC1–PC2
  exceeds 3 (z per PC). With few samples this rarely triggers. Exclude a confirmed
  outlier with `--filters` and re-run `study`.
- Variance explained is parsed from labels like `PC 1 (54.35% variance)`; if that format
  changes the report says "variance unknown".

Interpretation: a variable that tracks PC1 strongly and is **not** your comparator is a
batch effect or confounder candidate. Prefer contrasts stratified on it, or filter.
````

In `SKILL.md`, insert this step between the `study` and `contrasts` steps of "EDA differential expression in brief", renumbering the steps after it:

```markdown
3. `eda.py pca SITE DS_…`: which sample variables track PC1/PC2 (batch effects), and outliers.
```

Run: `cd veupathdb_database && wc -l SKILL.md`
Expected: ≤ 200.

- [ ] **Step 8: Commit**

```bash
git add veupathdb_database/scripts/_pca.py veupathdb_database/scripts/eda.py veupathdb_database/tests/test_pca.py veupathdb_database/tests/test_eda_live.py veupathdb_database/TESTS.md veupathdb_database/references/eda.md veupathdb_database/SKILL.md
git commit -m "feat(eda): eda.py pca with per-PC variable scoring, outliers and not-scored reasons

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Final check (after Task 18)

- [ ] Run the full suite with a token and `Rscript`: `cd veupathdb_database && uv run --with pytest --with httpx python -m pytest tests -q`. Expect everything to pass, with only the strong job-identity test allowed to skip (with its reason).
- [ ] Run the full suite with no token (`env -u VEUPATHDB_BEARER_TOKEN XDG_CONFIG_HOME=/tmp/empty uv run --with pytest --with httpx python -m pytest tests -q`). Expect offline tests to pass and live tests to skip, never fail.
- [ ] Do EDA-WEB-1 by hand and record the result in TESTS.md.
- [ ] `git log --oneline` shows one commit per task. Do not push.

