# VEuPathDB WDK Strategy Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A self-contained `veupathdb-wdk-strategies` skill (markdown + uv-run Python CLI) that lets any agentic client build search strategies on VEuPathDB sites.

**Architecture:** One CLI (`scripts/wdk.py`, PEP 723) with subcommands, backed by three private modules: `_sites.py` (site registry), `_client.py` (httpx transport with WDK auth/retry quirks + catalog cache), `_shaping.py` (parameter sheets, vocab handling, param encoding, result shaping), plus `_strategy.py` (step-tree construction). SKILL.md + references/ provide progressive discovery. Live pytest suite with gold standards registered in TESTS.md.

**Tech Stack:** Python ≥3.11, `uv` (PEP 723 inline metadata), `httpx` (only runtime dep), `pytest` (tests only).

**Spec:** `docs/superpowers/specs/2026-08-27-veupathdb-wdk-skill-design.md` (read it first — the Shaping and Transport sections are normative).

## Global Constraints

- Repo: `/home/maccallr/work/veupathdb-skills` (all paths below relative to it). Commit here, never in `../pathfinder-as-a-skill/pathfinder`.
- `SKILL.md` ≤ 200 lines. Reference docs hold the depth.
- Runtime dependency: `httpx` only. Tests may add `pytest`. Nothing else.
- Supply chain: rely on the user's global `~/.config/uv/uv.toml` `exclude-newer`; document this in SKILL.md. Do not add per-script exclude-newer.
- The bearer token (`VEUPATHDB_BEARER_TOKEN`, from env or repo-root `.env`) must NEVER be printed, logged, or committed. `.env` is already gitignored.
- Auth is a **cookie**: `Cookie: Authorization=<token>` — exactly one pair, never an `Authorization:` header.
- Non-idempotent POSTs (step/strategy/dataset/temporary-result creation) get exactly ONE attempt.
- All WDK parameter values are strings on the wire; multi-pick values are JSON arrays serialized to a string.
- Strategies created by tests are named with prefix `__skill_test__:` and deleted in teardown (404-tolerant).
- Live tests skip cleanly (not fail) when no token is available.
- Test command (from `veupathdb-wdk-strategies/`): `uv run --with pytest --with httpx python -m pytest tests -q`
- Every task that adds a live test also appends its case to `veupathdb-wdk-strategies/TESTS.md` with the observed gold value and capture date (2026-08-27 format).

## Verified live facts (probed 2026-08-27 against plasmodb.org — trust these)

- `GET /record-types` → flat JSON list of url segments (`["transcript","gene","organism",…]`). **Requires auth cookie** — anonymous gets HTTP 401 `"Valid API Key required"`.
- `GET /record-types/{rt}/searches` → list of search objects; keys include `urlSegment`, `displayName`, `shortDisplayName`, `fullName`, `description`, `summary`, `paramNames`, `outputRecordClassName`, `queryName`.
- `GET /record-types/{rt}/searches/{name}?expandParams=true` → `{"searchData": {...,"parameters":[...]}, "validation": {"level":"DISPLAYABLE","isValid":true}}`.
- Parameter objects: `name`, `type` (seen: `string`, `multi-pick-vocabulary`, `single-pick-vocabulary`, `input-step`; also exist: `number`, `date`, `date-range`, `number-range`, `timestamp`, `input-dataset`, `filter`), `displayName`, `help`, `isVisible`, `allowEmptyValue`, `initialDisplayValue`, `dependentParams` (list of param names whose vocab THIS param controls), and for vocab params `vocabulary`, `displayType` (`treeBox` for trees), `countOnlyLeaves`, `maxSelectedCount`, `multiPick`.
- Flat vocabulary: list of `[term, display, parent-or-null]` triples. Tree vocabulary: `{"data": {"term": …, "display": …}, "children": [...]}` with synthetic root term `@@fake@@`.
- Example: `GenesByMolecularWeight` (transcript) params = `organism` (multi-pick treeBox, countOnlyLeaves=true, default `"[]"`), `min_molecular_weight` (string, default `"10000"`), `max_molecular_weight` (string, default `"50000"`). `GenesByGoTerm` has `go_typeahead` (flat vocab, 5992 entries) and `go_term_slim` with `dependentParams: ["go_typeahead"]`.
- `POST /record-types/transcript/searches/GenesByMolecularWeight/reports/standard` with body `{"searchConfig":{"parameters":{"organism":"[\"Plasmodium falciparum 3D7\"]","min_molecular_weight":"10000","max_molecular_weight":"50000"}},"reportConfig":{"pagination":{"offset":0,"numRecords":1}}}` → HTTP 200, `{"meta": {...}, "records": [...]}`. Meta counts observed: `displayViewTotalCount: 2365` (genes), `viewTotalCount: 2403`, `displayTotalCount: 2365`, `totalCount: 2403` (transcripts). Records: `{"id": [{"name":"gene_source_id","value":"PF3D7_0100200"},{"name":"source_id",…},{"name":"project_id",…}], "displayName": …, "attributes": {…}, "tables": {…}, "recordClassName": "transcript"}`.
- `GET /users/current` → `{"id": <int>, "isGuest": <bool>, "email": …, "properties": {…}}`.
- The transcript boolean search is `boolean_question_TranscriptRecordClasses_TranscriptRecordClass`; params: `bq_left_op_TranscriptRecordClasses_TranscriptRecordClass` (input-step, hidden), `bq_right_op_TranscriptRecordClasses_TranscriptRecordClass` (input-step, hidden), `bq_operator` (single-pick, values `UNION | INTERSECT | MINUS | RMINUS | LONLY | RONLY`, default INTERSECT).

## File structure (final)

```
veupathdb-wdk-strategies/
├── SKILL.md
├── TESTS.md
├── references/
│   ├── auth.md
│   ├── parameters.md
│   ├── strategies.md
│   └── gotchas.md
├── scripts/
│   ├── wdk.py          CLI: argparse subcommands, JSON/TSV output, error handling
│   ├── _sites.py       14-site registry + URL builders
│   ├── _client.py      token loading, Client (cookie auth, retries, delayed-result), catalog fetch+cache
│   ├── _shaping.py     html stripping, catalog lines, lexical scoring, sheet building, vocab tools, encode_params, count/record shaping
│   └── _strategy.py    spec parsing, step creation order, boolean discovery, strategy shaping
└── tests/
    ├── conftest.py
    ├── fixtures/       captured live JSON (mw.json, go.json, bool.json)
    ├── test_sites.py
    ├── test_client.py      offline (httpx.MockTransport) + live whoami
    ├── test_catalog.py     live
    ├── test_find.py        offline scoring + live
    ├── test_sheet.py       offline (fixtures) + live inspect
    ├── test_options.py     live param-options
    ├── test_encode.py      offline (fixtures)
    ├── test_reports.py     live count/preview
    ├── test_strategy.py    live create/read/delete (cleanup!)
    └── test_results.py     live results/download-url
```

---

### Task 1: Scaffold, site registry, `sites` subcommand

**Files:**
- Create: `veupathdb-wdk-strategies/scripts/_sites.py`
- Create: `veupathdb-wdk-strategies/scripts/wdk.py`
- Create: `veupathdb-wdk-strategies/tests/conftest.py`
- Test: `veupathdb-wdk-strategies/tests/test_sites.py`

**Interfaces:**
- Produces: `_sites.SITES: dict[str, dict]` (keys `base_url`, `project_id`, `timeout`), `_sites.service_url(site_id) -> str` (raises `KeyError`-derived `UnknownSiteError` listing valid ids), `_sites.web_base_url(site_id) -> str`, `_sites.strategy_url(site_id, strategy_id, step_id=None) -> str`. `wdk.py` argparse skeleton with `emit(obj)` (JSON to stdout, `indent=1`) and `fail(msg)` (stderr + exit 1) helpers and a `cmd_sites` handler.

- [ ] **Step 1: Write the failing tests**

`tests/conftest.py`:
```python
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
```

`tests/test_sites.py`:
```python
import pytest


def test_all_14_sites_present():
    from _sites import SITES
    assert len(SITES) == 14
    for sid in ("plasmodb", "vectorbase", "toxodb", "veupathdb", "orthomcl"):
        assert sid in SITES


def test_service_and_web_urls():
    from _sites import service_url, strategy_url, web_base_url
    assert service_url("plasmodb") == "https://plasmodb.org/plasmo/service"
    assert web_base_url("plasmodb") == "https://plasmodb.org/plasmo"
    assert (strategy_url("plasmodb", 123)
            == "https://plasmodb.org/plasmo/app/workspace/strategies/123")
    assert (strategy_url("plasmodb", 123, 456)
            == "https://plasmodb.org/plasmo/app/workspace/strategies/123/456")


def test_unknown_site_lists_valid_ids():
    from _sites import UnknownSiteError, service_url
    with pytest.raises(UnknownSiteError) as e:
        service_url("nope")
    assert "plasmodb" in str(e.value)


def test_portal_timeout_is_120():
    from _sites import SITES
    assert SITES["veupathdb"]["timeout"] == 120
    assert SITES["plasmodb"]["timeout"] == 30
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `veupathdb-wdk-strategies/`): `uv run --with pytest --with httpx python -m pytest tests/test_sites.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named '_sites'`

- [ ] **Step 3: Write `scripts/_sites.py`**

```python
"""VEuPathDB site registry. base_url IS the WDK REST service root."""


class UnknownSiteError(KeyError):
    pass


def _s(base_url: str, project_id: str, timeout: int = 30) -> dict:
    return {"base_url": base_url, "project_id": project_id, "timeout": timeout}


SITES: dict[str, dict] = {
    "veupathdb": _s("https://veupathdb.org/veupathdb/service", "EuPathDB", 120),
    "amoebadb": _s("https://amoebadb.org/amoeba/service", "AmoebaDB"),
    "cryptodb": _s("https://cryptodb.org/cryptodb/service", "CryptoDB"),
    "fungidb": _s("https://fungidb.org/fungidb/service", "FungiDB"),
    "giardiadb": _s("https://giardiadb.org/giardiadb/service", "GiardiaDB"),
    "hostdb": _s("https://hostdb.org/hostdb/service", "HostDB"),
    "microsporidiadb": _s("https://microsporidiadb.org/micro/service", "MicrosporidiaDB"),
    "orthomcl": _s("https://orthomcl.org/orthomcl/service", "OrthoMCL"),
    "piroplasmadb": _s("https://piroplasmadb.org/piro/service", "PiroplasmaDB"),
    "plasmodb": _s("https://plasmodb.org/plasmo/service", "PlasmoDB"),
    "toxodb": _s("https://toxodb.org/toxo/service", "ToxoDB"),
    "trichdb": _s("https://trichdb.org/trichdb/service", "TrichDB"),
    "tritrypdb": _s("https://tritrypdb.org/tritrypdb/service", "TriTrypDB"),
    "vectorbase": _s("https://vectorbase.org/vectorbase/service", "VectorBase"),
}


def _site(site_id: str) -> dict:
    try:
        return SITES[site_id]
    except KeyError:
        raise UnknownSiteError(
            f"unknown site '{site_id}'; valid: {', '.join(sorted(SITES))}"
        ) from None


def service_url(site_id: str) -> str:
    return _site(site_id)["base_url"]


def web_base_url(site_id: str) -> str:
    return _site(site_id)["base_url"].removesuffix("/service")


def strategy_url(site_id: str, strategy_id, step_id=None) -> str:
    url = f"{web_base_url(site_id)}/app/workspace/strategies/{strategy_id}"
    return f"{url}/{step_id}" if step_id is not None else url
```

- [ ] **Step 4: Write `scripts/wdk.py` skeleton with `sites`**

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""VEuPathDB WDK CLI — build search strategies from the command line.

Run `wdk.py --help` for subcommands, `wdk.py <sub> --help` for details.
"""
import argparse
import json
import sys

from _sites import SITES, UnknownSiteError, strategy_url


def emit(obj) -> None:
    print(json.dumps(obj, indent=1, ensure_ascii=False))


def fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def cmd_sites(args) -> None:
    emit(
        {
            sid: {"service": cfg["base_url"], "project": cfg["project_id"]}
            for sid, cfg in sorted(SITES.items())
        }
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wdk.py", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("sites", help="list site ids, service URLs, project ids")
    sp.set_defaults(func=cmd_sites)
    return p


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except UnknownSiteError as e:
        fail(str(e))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests + CLI smoke**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_sites.py -q` — Expected: 4 passed.
Run: `uv run scripts/wdk.py sites | head -5` — Expected: JSON starting with `"amoebadb"`.

- [ ] **Step 6: Commit**

```bash
git add veupathdb-wdk-strategies
git commit -m "feat: skill scaffold, site registry, sites subcommand"
```

---

### Task 2: Transport (`_client.py`) + `whoami`

**Files:**
- Create: `veupathdb-wdk-strategies/scripts/_client.py`
- Modify: `veupathdb-wdk-strategies/scripts/wdk.py` (add `whoami`)
- Test: `veupathdb-wdk-strategies/tests/test_client.py`
- Create: `veupathdb-wdk-strategies/TESTS.md` (first two cases)

**Interfaces:**
- Produces: `_client.load_token(root=None) -> str | None`; `_client.WDKError(msg, status=None, endpoint=None)`; `_client.GuestTokenError(WDKError)`; `_client.Client(site_id, token=None, transport=None, backoff=2.0)` with `.get(path, params=None)`, `.post(path, body, idempotent=True)`, `.put(path, body)`, `.patch(path, body)`, `.delete(path)` (all return parsed JSON or `None` on 204/empty), `.user_id() -> int` (cached; raises `GuestTokenError` on guest/missing token), `.site_id`, `.token`.
- Consumes: `_sites.SITES`, `_sites.service_url`.

- [ ] **Step 1: Write the failing tests**

`tests/test_client.py`:
```python
import json

import httpx
import pytest


def _client(handler, **kw):
    from _client import Client

    kw.setdefault("token", "tok-x")
    kw.setdefault("backoff", 0)
    return Client("plasmodb", transport=httpx.MockTransport(handler), **kw)


def test_auth_is_a_single_cookie_pair():
    seen = {}

    def handler(request):
        seen["cookie"] = request.headers.get("cookie")
        seen["auth_header"] = request.headers.get("authorization")
        return httpx.Response(200, json={"ok": True})

    assert _client(handler).get("/x") == {"ok": True}
    assert seen["cookie"] == "Authorization=tok-x"
    assert seen["auth_header"] is None


def test_retries_5xx_then_succeeds():
    n = {"v": 0}

    def handler(request):
        n["v"] += 1
        if n["v"] < 3:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, json={"ok": True})

    assert _client(handler).get("/x") == {"ok": True}
    assert n["v"] == 3


def test_delayed_result_body_is_retried():
    n = {"v": 0}

    def handler(request):
        n["v"] += 1
        if n["v"] == 1:
            return httpx.Response(
                200, json={"status": "accepted", "message": "WDK-DELAYED-RESULT"}
            )
        return httpx.Response(200, json={"ok": True})

    assert _client(handler).get("/x") == {"ok": True}
    assert n["v"] == 2


def test_non_idempotent_post_gets_one_attempt():
    from _client import WDKError

    n = {"v": 0}

    def handler(request):
        n["v"] += 1
        return httpx.Response(502, text="proxy hiccup")

    with pytest.raises(WDKError):
        _client(handler).post("/users/1/steps", {"a": 1}, idempotent=False)
    assert n["v"] == 1


def test_4xx_raises_with_body_and_no_retry():
    from _client import WDKError

    n = {"v": 0}

    def handler(request):
        n["v"] += 1
        return httpx.Response(422, text="value 'x' is not in vocabulary")

    with pytest.raises(WDKError) as e:
        _client(handler).get("/x")
    assert n["v"] == 1
    assert e.value.status == 422
    assert "vocabulary" in str(e.value)


def test_user_id_resolves_and_caches():
    n = {"v": 0}

    def handler(request):
        n["v"] += 1
        assert request.url.path.endswith("/users/current")
        return httpx.Response(200, json={"id": 12345, "isGuest": False, "email": "x@y"})

    c = _client(handler)
    assert c.user_id() == 12345
    assert c.user_id() == 12345
    assert n["v"] == 1


def test_guest_token_is_refused():
    from _client import GuestTokenError

    def handler(request):
        return httpx.Response(200, json={"id": 99, "isGuest": True})

    with pytest.raises(GuestTokenError) as e:
        _client(handler).user_id()
    assert "register" in str(e.value).lower()


def test_load_token_env_then_dotenv(tmp_path, monkeypatch):
    from _client import load_token

    monkeypatch.setenv("VEUPATHDB_BEARER_TOKEN", "from-env")
    assert load_token(root=tmp_path) == "from-env"
    monkeypatch.delenv("VEUPATHDB_BEARER_TOKEN")
    (tmp_path / ".env").write_text('VEUPATHDB_BEARER_TOKEN="from-file"\n')
    assert load_token(root=tmp_path) == "from-file"
    assert load_token(root=tmp_path / "nowhere") is None


def test_live_whoami(live_client):
    me = live_client.get("/users/current")
    assert me["isGuest"] is False
    assert isinstance(me["id"], int)


@pytest.mark.parametrize("site", ["plasmodb", "vectorbase", "toxodb"])
def test_live_whoami_all_test_sites(site, token):
    from _client import Client

    me = Client(site, token=token).get("/users/current")
    assert me["isGuest"] is False
```

Append to `tests/conftest.py`:
```python
import pytest


@pytest.fixture(scope="session")
def token():
    from _client import load_token

    tok = load_token()
    if not tok:
        pytest.skip("VEUPATHDB_BEARER_TOKEN not set (env or repo-root .env)")
    return tok


@pytest.fixture(scope="session")
def live_client(token):
    from _client import Client

    return Client("plasmodb", token=token)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named '_client'`

- [ ] **Step 3: Write `scripts/_client.py`**

```python
"""WDK transport. Auth is a COOKIE (Authorization=<token>), exactly one pair."""
import json
import os
import pathlib
import time

import httpx

from _sites import SITES, service_url

# scripts/ -> veupathdb-wdk-strategies/ -> pathfinder-skills/
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE_DIR = pathlib.Path.home() / ".cache" / "veupathdb-wdk"
CACHE_TTL_S = 7 * 24 * 3600


class WDKError(Exception):
    def __init__(self, message, status=None, endpoint=None):
        self.status = status
        self.endpoint = endpoint
        super().__init__(message)

    def __str__(self):
        bits = []
        if self.status:
            bits.append(f"HTTP {self.status}")
        if self.endpoint:
            bits.append(self.endpoint)
        bits.append(super().__str__())
        return " | ".join(bits)


class GuestTokenError(WDKError):
    pass


def load_token(root=None):
    tok = os.environ.get("VEUPATHDB_BEARER_TOKEN")
    if tok:
        return tok.strip()
    env = pathlib.Path(root or REPO_ROOT) / ".env"
    if env.is_file():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("VEUPATHDB_BEARER_TOKEN="):
                return line.split("=", 1)[1].strip().strip("\"'") or None
    return None


def _is_delayed(body):
    return isinstance(body, dict) and body.get("message") == "WDK-DELAYED-RESULT"


class Client:
    def __init__(self, site_id, token=None, transport=None, backoff=2.0):
        self.site_id = site_id
        self.token = token
        self.backoff = backoff
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Cookie"] = f"Authorization={token}"
        self._http = httpx.Client(
            base_url=service_url(site_id),
            headers=headers,
            timeout=SITES[site_id]["timeout"],
            follow_redirects=True,
            transport=transport,
        )
        self._user_id = None

    def request(self, method, path, body=None, params=None, retries=3):
        last = None
        for attempt in range(retries):
            if attempt and self.backoff:
                time.sleep(self.backoff**attempt)
            try:
                r = self._http.request(method, path, json=body, params=params)
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

    def post(self, path, body, idempotent=True):
        return self.request("POST", path, body=body, retries=3 if idempotent else 1)

    def put(self, path, body):
        return self.request("PUT", path, body=body)

    def patch(self, path, body):
        return self.request("PATCH", path, body=body)

    def delete(self, path):
        return self.request("DELETE", path)

    def user_id(self):
        if self._user_id is None:
            if not self.token:
                raise GuestTokenError(
                    "no token: set VEUPATHDB_BEARER_TOKEN (env or repo-root .env). "
                    "Register at the site to obtain a registered-user token.",
                    endpoint="/users/current",
                )
            me = self.get("/users/current")
            if me.get("isGuest"):
                raise GuestTokenError(
                    "token identifies a GUEST user; WDK refuses programmatic guest "
                    "access. Register at the site and supply a registered-user token.",
                    endpoint="/users/current",
                )
            self._user_id = int(me["id"])
        return self._user_id
```

- [ ] **Step 4: Add `whoami` to `wdk.py`**

Add handler + subparser (site is a positional arg; the `client()` helper is reused by every later command):

```python
def client(site_id):
    from _client import Client, load_token

    return Client(site_id, token=load_token())


def cmd_whoami(args) -> None:
    c = client(args.site)
    me = c.get("/users/current")
    if me.get("isGuest"):
        fail(
            "token identifies a GUEST user; register at the site and supply a "
            "registered-user bearer token"
        )
    emit({"site": args.site, "user_id": me["id"], "email": me.get("email")})
```

In `build_parser()`:
```python
    sp = sub.add_parser("whoami", help="verify token; print numeric user id")
    sp.add_argument("site")
    sp.set_defaults(func=cmd_whoami)
```

And widen `main()`'s except clause:
```python
    except (UnknownSiteError, Exception) as e:  # noqa: BLE001 — replace below
```
Actually use this exact `main()`:
```python
def main() -> None:
    from _client import WDKError

    args = build_parser().parse_args()
    try:
        args.func(args)
    except (UnknownSiteError, WDKError) as e:
        fail(str(e))
```

- [ ] **Step 5: Run tests, then live smoke**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_client.py -q`
Expected: 12 passed (the live whoami runs on plasmodb, vectorbase, and toxodb; live tests skip only if the token is missing — it must not be).
Run: `uv run scripts/wdk.py whoami plasmodb` — Expected: JSON with your numeric `user_id`. Record the id in TESTS.md.

- [ ] **Step 6: Create `TESTS.md` with the first cases**

```markdown
# Gold-standard test registry

Live services drift with data releases; each case states its tolerance:
`exact` | `range` (± stated) | `fields-present`.
Run all: `uv run --with pytest --with httpx python -m pytest tests -q`

| ID | Command / pytest node | Expectation | Tolerance | Gold (captured) | Date |
|---|---|---|---|---|---|
| AUTH-1 | `wdk.py whoami plasmodb` / test_client.py::test_live_whoami | numeric user_id, not guest | fields-present | user_id=<fill from live run> | 2026-08-27 |
| AUTH-2 | test_client.py::test_guest_token_is_refused | guest refusal names registration | exact (offline) | message contains "register" | 2026-08-27 |
```

- [ ] **Step 7: Commit**

```bash
git add veupathdb-wdk-strategies
git commit -m "feat: WDK transport with cookie auth, retries, whoami"
```

---

### Task 3: Catalog fetch + cache; `record-types`, `searches`, `catalog` subcommands

**Files:**
- Modify: `veupathdb-wdk-strategies/scripts/_client.py` (add `fetch_catalog`)
- Create: `veupathdb-wdk-strategies/scripts/_shaping.py` (strip_html, catalog_lines)
- Modify: `veupathdb-wdk-strategies/scripts/wdk.py`
- Test: `veupathdb-wdk-strategies/tests/test_catalog.py`

**Interfaces:**
- Produces: `_client.fetch_catalog(client, refresh=False) -> dict` with keys `cached_at: float`, `record_types: list[str]`, `searches: dict[rt, list[{name, displayName, description, paramNames, outputRecordClassName}]]`; `_shaping.strip_html(text) -> str`; `_shaping.catalog_lines(catalog, record_type=None) -> list[str]` (TSV `record_type\tname\tdisplayName\tdescription≤250`, excluding searches whose name starts with `boolean_question_`); `_shaping.all_search_names(catalog) -> dict[name, rt]` (first record type wins, preferring non-`gene` rt for duplicates).
- Consumes: `Client.get`, `CACHE_DIR`, `CACHE_TTL_S`.

- [ ] **Step 1: Write the failing tests**

`tests/test_catalog.py`:
```python
import json


def test_strip_html():
    from _shaping import strip_html

    assert (
        strip_html("Find genes <br><br> with  <i>weight</i>\n in a range")
        == "Find genes with weight in a range"
    )


def test_catalog_lines_shape_and_boolean_filter():
    from _shaping import catalog_lines

    cat = {
        "record_types": ["transcript"],
        "searches": {
            "transcript": [
                {
                    "name": "GenesByTaxon",
                    "displayName": "Taxonomy",
                    "description": "<b>Find</b> genes " + "x" * 400,
                    "paramNames": ["organism"],
                    "outputRecordClassName": "transcript",
                },
                {
                    "name": "boolean_question_X",
                    "displayName": "bool",
                    "description": "",
                    "paramNames": [],
                    "outputRecordClassName": "transcript",
                },
            ]
        },
    }
    lines = catalog_lines(cat)
    assert len(lines) == 1
    rt, name, disp, desc = lines[0].split("\t")
    assert (rt, name, disp) == ("transcript", "GenesByTaxon", "Taxonomy")
    assert len(desc) <= 250 and desc.startswith("Find genes")


def test_live_catalog_plasmodb(live_client):
    from _client import fetch_catalog
    from _shaping import all_search_names, catalog_lines

    cat = fetch_catalog(live_client)
    assert "transcript" in cat["record_types"]
    names = all_search_names(cat)
    assert names.get("GenesByGoTerm") == "transcript"
    assert names.get("GenesByMolecularWeight") == "transcript"
    assert len(catalog_lines(cat)) > 400  # 515 searches incl. non-gene types, minus booleans

    # second call must come from disk cache (no HTTP): break the token
    from _client import Client

    broken = Client("plasmodb", token="invalid")
    cached = fetch_catalog(broken)
    assert cached["record_types"] == cat["record_types"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_catalog.py -q`
Expected: FAIL — `No module named '_shaping'` / missing `fetch_catalog`.

- [ ] **Step 3: Implement**

Append to `scripts/_client.py`:
```python
def fetch_catalog(client, refresh=False):
    """Record types + compact search listings. Disk-cached 7 days per site."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{client.site_id}.json"
    if (
        not refresh
        and cache.is_file()
        and time.time() - cache.stat().st_mtime < CACHE_TTL_S
    ):
        return json.loads(cache.read_text())
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
            }
            for s in listing
        ]
    catalog = {
        "cached_at": time.time(),
        "record_types": record_types,
        "searches": searches,
    }
    cache.write_text(json.dumps(catalog))
    return catalog
```

Create `scripts/_shaping.py`:
```python
"""Response shaping: compact, context-friendly views of WDK payloads."""
import html
import json
import re

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def strip_html(text):
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", text or ""))).strip()


def _is_boolean(name):
    return name.startswith("boolean_question_")


def catalog_lines(catalog, record_type=None):
    lines = []
    for rt, searches in catalog["searches"].items():
        if record_type and rt != record_type:
            continue
        for s in searches:
            if _is_boolean(s["name"]):
                continue
            desc = strip_html(s["description"])[:250]
            lines.append(f"{rt}\t{s['name']}\t{s['displayName']}\t{desc}")
    return lines


def all_search_names(catalog):
    """Map search name -> record type. Prefer non-'gene' rt for duplicates
    (gene searches live under 'transcript' in WDK)."""
    names = {}
    for rt, searches in catalog["searches"].items():
        for s in searches:
            if s["name"] not in names or names[s["name"]] == "gene":
                names[s["name"]] = rt
    return names
```

- [ ] **Step 4: Wire subcommands into `wdk.py`**

```python
def cmd_record_types(args) -> None:
    emit(client(args.site).get("/record-types"))


def cmd_searches(args) -> None:
    from _client import fetch_catalog
    from _shaping import catalog_lines

    cat = fetch_catalog(client(args.site), refresh=args.refresh)
    print("\n".join(catalog_lines(cat, record_type=args.record_type)))


def cmd_catalog(args) -> None:
    from _client import fetch_catalog
    from _shaping import catalog_lines

    cat = fetch_catalog(client(args.site), refresh=args.refresh)
    lines = catalog_lines(cat, record_type=args.record_type)
    print(f"# {args.site}: {len(lines)} searches (record_type\tname\tdisplayName\tdescription)")
    print("\n".join(lines))
```

Subparsers:
```python
    sp = sub.add_parser("record-types", help="list record type url segments")
    sp.add_argument("site")
    sp.set_defaults(func=cmd_record_types)

    sp = sub.add_parser("searches", help="list searches for one record type")
    sp.add_argument("site")
    sp.add_argument("record_type")
    sp.add_argument("--refresh", action="store_true", help="bypass 7-day disk cache")
    sp.set_defaults(func=cmd_searches)

    sp = sub.add_parser(
        "catalog",
        help="full compact search catalog (primary discovery input; ~25-75k tokens)",
    )
    sp.add_argument("site")
    sp.add_argument("--record-type")
    sp.add_argument("--refresh", action="store_true")
    sp.set_defaults(func=cmd_catalog)
```

- [ ] **Step 5: Run tests + live smoke on all three sites**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_catalog.py -q` — Expected: 3 passed.
Run: `uv run scripts/wdk.py catalog plasmodb | head -3`, same for `vectorbase` and `toxodb`. Record line counts in TESTS.md (expected ≈505/905/415, tolerance ±20%):

| ID | Command | Expectation | Tolerance | Gold | Date |
|---|---|---|---|---|---|
| CAT-1 | `wdk.py record-types plasmodb` | contains transcript, organism, dataset | fields-present | 23 record types | 2026-08-27 |
| CAT-2 | `wdk.py catalog plasmodb` | header + one TSV line per non-boolean search | range ±20% | <fill observed line count> | 2026-08-27 |
| CAT-3 | `wdk.py catalog vectorbase` | as CAT-2 | range ±20% | <fill> | 2026-08-27 |
| CAT-4 | `wdk.py catalog toxodb` | as CAT-2 | range ±20% | <fill> | 2026-08-27 |

- [ ] **Step 6: Commit**

```bash
git add veupathdb-wdk-strategies
git commit -m "feat: catalog fetch with disk cache; record-types/searches/catalog subcommands"
```

---

### Task 4: `find-searches` (lexical convenience)

**Files:**
- Modify: `veupathdb-wdk-strategies/scripts/_shaping.py` (add `score_searches`)
- Modify: `veupathdb-wdk-strategies/scripts/wdk.py`
- Test: `veupathdb-wdk-strategies/tests/test_find.py`

**Interfaces:**
- Produces: `_shaping.score_searches(catalog, query, limit=20) -> list[dict]` — each `{"record_type", "name", "displayName", "relevance"}` sorted by relevance desc; relevance = score/max_score rounded to 2dp. Scoring: per query word (lowercased, len ≥ 2): +3 if substring of name, +2 if of displayName, +1 if of description. Zero-score entries dropped; boolean searches excluded.

- [ ] **Step 1: Write the failing tests**

`tests/test_find.py`:
```python
def _cat():
    def s(name, disp, desc):
        return {
            "name": name,
            "displayName": disp,
            "description": desc,
            "paramNames": [],
            "outputRecordClassName": "transcript",
        }

    return {
        "record_types": ["transcript"],
        "searches": {
            "transcript": [
                s("GenesByGoTerm", "GO Term", "genes by gene ontology term"),
                s("GenesByTaxon", "Taxonomy", "genes from selected organisms"),
                s("boolean_question_X", "bool", "go term"),
            ]
        },
    }


def test_scoring_ranks_name_hits_first():
    from _shaping import score_searches

    hits = score_searches(_cat(), "go term")
    assert hits[0]["name"] == "GenesByGoTerm"
    assert hits[0]["relevance"] == 1.0
    assert all(h["name"] != "boolean_question_X" for h in hits)


def test_no_hits_is_empty():
    from _shaping import score_searches

    assert score_searches(_cat(), "zzzznothing") == []


def test_live_find(live_client):
    from _client import fetch_catalog
    from _shaping import score_searches

    hits = score_searches(fetch_catalog(live_client), "GO term")
    assert "GenesByGoTerm" in [h["name"] for h in hits[:5]]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_find.py -q` — Expected: FAIL (`score_searches` missing).

- [ ] **Step 3: Implement in `_shaping.py`**

```python
def score_searches(catalog, query, limit=20):
    words = [w for w in re.split(r"\W+", query.lower()) if len(w) >= 2]
    scored = []
    for rt, searches in catalog["searches"].items():
        for s in searches:
            if _is_boolean(s["name"]):
                continue
            name = s["name"].lower()
            disp = s["displayName"].lower()
            desc = strip_html(s["description"]).lower()
            score = sum(
                (3 if w in name else 0)
                + (2 if w in disp else 0)
                + (1 if w in desc else 0)
                for w in words
            )
            if score:
                scored.append((score, rt, s))
    if not scored:
        return []
    scored.sort(key=lambda t: (-t[0], t[2]["name"]))
    top = scored[0][0]
    return [
        {
            "record_type": rt,
            "name": s["name"],
            "displayName": s["displayName"],
            "relevance": round(score / top, 2),
        }
        for score, rt, s in scored[:limit]
    ]
```

- [ ] **Step 4: Wire `find-searches` into `wdk.py`**

```python
def cmd_find_searches(args) -> None:
    from _client import fetch_catalog
    from _shaping import score_searches

    hits = score_searches(fetch_catalog(client(args.site)), args.query, limit=args.limit)
    if not hits:
        fail(
            f"no searches match '{args.query}'. Broaden the query, or run "
            f"'wdk.py catalog {args.site}' and reason over the full listing "
            "(recommended: in a sub-agent)"
        )
    emit(hits)
```

Subparser:
```python
    sp = sub.add_parser("find-searches", help="lexical search-name lookup (convenience)")
    sp.add_argument("site")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_find_searches)
```

- [ ] **Step 5: Run tests; add TESTS.md case**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_find.py -q` — Expected: 3 passed.

| FIND-1 | `wdk.py find-searches plasmodb "GO term"` | GenesByGoTerm in top 5 | fields-present | rank=<fill> | 2026-08-27 |

- [ ] **Step 6: Commit**

```bash
git add veupathdb-wdk-strategies
git commit -m "feat: find-searches lexical scoring"
```

---

### Task 5: Search detail, parameter sheet, `inspect`

**Files:**
- Modify: `veupathdb-wdk-strategies/scripts/_shaping.py` (vocab tools + `build_sheet` + `resolve_search`)
- Modify: `veupathdb-wdk-strategies/scripts/wdk.py`
- Create: `veupathdb-wdk-strategies/tests/fixtures/mw.json`, `go.json`, `bool.json`
- Test: `veupathdb-wdk-strategies/tests/test_sheet.py`

**Interfaces:**
- Produces:
  - `_shaping.FAKE = "@@fake@@"`; `_shaping.is_tree(vocab) -> bool`
  - `_shaping.tree_entries(node) -> list[{"term","display","parent","leaf"}]` (skips `@@fake@@`)
  - `_shaping.expand_to_leaves(tree, selected: list[str]) -> (leaves: list[str], unknown: list[str])`
  - `_shaping.flat_terms(vocab_list) -> list[str]` (first element of each `[term, display, parent]` triple)
  - `_shaping.resolve_search(catalog, name) -> (rt, None)` or `(None, suggestions: list[str])` via `difflib.get_close_matches(n=5)`
  - `_shaping.get_search_detail(client, rt, name, context=None) -> dict` (searchData; POST `{"contextParamValues": context}` when context given, else GET; both with `expandParams=true`)
  - `_shaping.build_sheet(search_data, query=None) -> dict` with keys `search`, `displayName`, `recordType`, `description` (stripped, ≤500), `required` (list of param entries), `optional`, `dependencies` (list of sentences naming only visible dependents), `params_template` (`{visible name: default}`), `hidden_params_submitted_automatically` (names only). Param entry keys: `name`, `type`, `displayName`, `required` (`not allowEmptyValue`), `default`, optional `help` (stripped ≤300), and for vocab params either `allowed_values` (flat, ≤200 terms, `"term"` or `"term — display"` when they differ) or `vocabulary_tree` (list of indented lines, ≤80, parents suffixed `/<n descendants>`) plus `note` when truncated: `"<N> values total; showing <M>. Use: wdk.py param-options <search> <param> --query <keyword>"`, and for trees always the note `"selecting a parent term selects all of its children"`. `input-step` params get `note: "wired via stepTree; submitted as empty string"`.
- Consumes: `fetch_catalog`, `all_search_names`, `Client`.

- [ ] **Step 1: Capture live fixtures**

Run from `veupathdb-wdk-strategies/`:
```bash
uv run --with httpx python - <<'EOF'
import json, pathlib, sys
sys.path.insert(0, "scripts")
from _client import Client, load_token
c = Client("plasmodb", token=load_token())
fx = pathlib.Path("tests/fixtures"); fx.mkdir(parents=True, exist_ok=True)
for name, out in [
    ("GenesByMolecularWeight", "mw.json"),
    ("GenesByGoTerm", "go.json"),
    ("boolean_question_TranscriptRecordClasses_TranscriptRecordClass", "bool.json"),
]:
    d = c.get(f"/record-types/transcript/searches/{name}", params={"expandParams": "true"})
    (fx / out).write_text(json.dumps(d["searchData"], indent=1))
    print(out, "ok")
EOF
```
Expected: `mw.json ok`, `go.json ok`, `bool.json ok`. These are committed — they are the offline regression baseline.

- [ ] **Step 2: Write the failing tests**

`tests/test_sheet.py`:
```python
import json
import pathlib

FX = pathlib.Path(__file__).parent / "fixtures"


def _mw():
    return json.loads((FX / "mw.json").read_text())


def _go():
    return json.loads((FX / "go.json").read_text())


def test_tree_entries_skips_fake_root():
    from _shaping import tree_entries

    organism = next(p for p in _mw()["parameters"] if p["name"] == "organism")
    entries = tree_entries(organism["vocabulary"])
    terms = [e["term"] for e in entries]
    assert "@@fake@@" not in terms
    assert "Plasmodium falciparum 3D7" in terms
    leaf = next(e for e in entries if e["term"] == "Plasmodium falciparum 3D7")
    assert leaf["leaf"] is True


def test_expand_to_leaves_parent_and_leaf_and_unknown():
    from _shaping import expand_to_leaves

    organism = next(p for p in _mw()["parameters"] if p["name"] == "organism")
    tree = organism["vocabulary"]
    leaves, unknown = expand_to_leaves(tree, ["Plasmodium falciparum 3D7"])
    assert leaves == ["Plasmodium falciparum 3D7"] and unknown == []
    leaves, unknown = expand_to_leaves(tree, ["Plasmodium"])
    assert len(leaves) > 5 and all("Plasmodium" in x for x in leaves[:3])
    _, unknown = expand_to_leaves(tree, ["Plasmodium falciparum 3D8"])
    assert unknown == ["Plasmodium falciparum 3D8"]


def test_sheet_mw():
    from _shaping import build_sheet

    sheet = build_sheet(_mw())
    assert sheet["search"] == "GenesByMolecularWeight"
    names = [e["name"] for e in sheet["required"] + sheet["optional"]]
    assert set(names) == {"organism", "min_molecular_weight", "max_molecular_weight"}
    org = next(e for e in sheet["required"] if e["name"] == "organism")
    assert "vocabulary_tree" in org
    assert len(org["vocabulary_tree"]) <= 80
    assert "children" in org["note"]
    assert sheet["params_template"]["min_molecular_weight"] == "10000"


def test_sheet_shortlists_huge_flat_vocab():
    from _shaping import build_sheet

    sheet = build_sheet(_go(), query="kinase")
    ta = next(
        e for e in sheet["required"] + sheet["optional"] if e["name"] == "go_typeahead"
    )
    assert len(ta["allowed_values"]) <= 200
    assert "values total" in ta["note"]
    assert "param-options" in ta["note"]


def test_sheet_dependencies_name_visible_dependents():
    from _shaping import build_sheet

    deps = build_sheet(_go())["dependencies"]
    assert any("go_term_slim" in d and "go_typeahead" in d for d in deps)


def test_resolve_search_did_you_mean(live_client):
    from _client import fetch_catalog
    from _shaping import resolve_search

    cat = fetch_catalog(live_client)
    rt, _ = resolve_search(cat, "GenesByMolecularWeight")
    assert rt == "transcript"
    rt, sugg = resolve_search(cat, "GenesByMolecularWieght")
    assert rt is None and "GenesByMolecularWeight" in sugg
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_sheet.py -q` — Expected: FAIL (missing functions).

- [ ] **Step 4: Implement in `_shaping.py`**

```python
import difflib

FAKE = "@@fake@@"
DIRECT_MAX = 200
TREE_MAX_LINES = 80


def is_tree(vocab):
    return isinstance(vocab, dict)


def tree_entries(node, parent=None, out=None):
    out = [] if out is None else out
    term = node["data"]["term"]
    kids = node.get("children", [])
    if term != FAKE:
        out.append(
            {
                "term": term,
                "display": node["data"].get("display", term),
                "parent": parent,
                "leaf": not kids,
            }
        )
    for c in kids:
        tree_entries(c, None if term == FAKE else term, out)
    return out


def expand_to_leaves(tree, selected):
    """Selected node terms (parents or leaves) -> the leaf terms they cover."""
    sel = set(selected)
    leaves, seen = [], set()

    def walk(node, under):
        term = node["data"]["term"]
        kids = node.get("children", [])
        hit = under or term in sel
        if hit and not kids and term != FAKE and term not in seen:
            seen.add(term)
            leaves.append(term)
        for c in kids:
            walk(c, hit)

    walk(tree, False)
    known = {e["term"] for e in tree_entries(tree)}
    unknown = [s for s in selected if s not in known]
    return leaves, unknown


def flat_terms(vocab_list):
    return [row[0] for row in vocab_list]


def resolve_search(catalog, name):
    names = all_search_names(catalog)
    if name in names:
        return names[name], None
    return None, difflib.get_close_matches(name, list(names), n=5, cutoff=0.5)


def get_search_detail(client, rt, name, context=None):
    path = f"/record-types/{rt}/searches/{name}"
    if context:
        data = client.post(
            f"{path}?expandParams=true", {"contextParamValues": context}
        )
    else:
        data = client.get(path, params={"expandParams": "true"})
    return data["searchData"]


def _render_tree(tree):
    lines, more = [], []

    def walk(node, depth):
        term = node["data"]["term"]
        kids = node.get("children", [])
        if term != FAKE:
            n_desc = len([e for e in tree_entries(node)]) - 1
            label = f"{'  ' * depth}{term}" + (f" /{n_desc}" if kids else "")
            if len(lines) < TREE_MAX_LINES:
                lines.append(label)
            elif depth <= 1:
                more.append(f"{term} /{n_desc}")
        for c in kids:
            walk(c, depth + (0 if term == FAKE else 1))

    walk(tree, 0)
    return lines, more


def _shortlist(terms, query, k):
    if not query:
        return terms[:k]
    words = [w for w in re.split(r"\W+", query.lower()) if len(w) >= 2]
    scored = sorted(
        terms, key=lambda t: -sum(1 for w in words if w in t.lower())
    )
    return scored[:k]


def _vocab_entry(p, query):
    v = p["vocabulary"]
    out = {}
    if is_tree(v):
        lines, more = _render_tree(v)
        out["vocabulary_tree"] = lines
        note = "selecting a parent term selects all of its children"
        if more:
            note += (
                f"; tree truncated at {TREE_MAX_LINES} lines, remaining top-level: "
                + ", ".join(more[:15])
            )
        out["note"] = note
    else:
        rows = [
            row[0] if row[0] == row[1] else f"{row[0]} — {row[1]}" for row in v
        ]
        if len(rows) <= DIRECT_MAX:
            out["allowed_values"] = rows
        else:
            out["allowed_values"] = _shortlist(rows, query, DIRECT_MAX)
            out["note"] = (
                f"{len(rows)} values total; showing {DIRECT_MAX}. Use: wdk.py "
                f"param-options <site> <search> {p['name']} --query <keyword>"
            )
    return out


def build_sheet(search_data, query=None):
    params = search_data.get("parameters", [])
    visible = [p for p in params if p.get("isVisible", True)]
    hidden = [p["name"] for p in params if not p.get("isVisible", True)]
    visible_names = {p["name"] for p in visible}
    entries, deps, template = [], [], {}
    for p in visible:
        e = {
            "name": p["name"],
            "type": p["type"],
            "displayName": p.get("displayName", ""),
            "required": not p.get("allowEmptyValue", False),
            "default": p.get("initialDisplayValue"),
        }
        help_text = strip_html(p.get("help") or "")
        if help_text:
            e["help"] = help_text[:300]
        if p.get("vocabulary") is not None:
            e.update(_vocab_entry(p, query))
        if p["type"] == "input-step":
            e["note"] = "wired via stepTree; submitted as empty string"
        entries.append(e)
        template[p["name"]] = p.get("initialDisplayValue")
        for dep in p.get("dependentParams", []):
            if dep in visible_names:
                deps.append(
                    f"'{p['name']}' controls the vocabulary of '{dep}'; re-read "
                    f"options for '{dep}' after choosing '{p['name']}'"
                )
    return {
        "search": search_data["urlSegment"],
        "displayName": search_data.get("displayName", ""),
        "recordType": search_data.get("outputRecordClassName", ""),
        "description": strip_html(search_data.get("description") or "")[:500],
        "required": [e for e in entries if e["required"]],
        "optional": [e for e in entries if not e["required"]],
        "dependencies": deps,
        "params_template": template,
        "hidden_params_submitted_automatically": hidden,
    }
```

- [ ] **Step 5: Wire `inspect` into `wdk.py`**

```python
def _resolve_or_fail(cat, name, site):
    from _shaping import resolve_search

    rt, suggestions = resolve_search(cat, name)
    if rt is None:
        fail(
            f"unknown search '{name}' on {site}. Did you mean: "
            f"{', '.join(suggestions) or '(no close match)'}? "
            f"Run 'wdk.py catalog {site}' for the full list."
        )
    return rt


def cmd_inspect(args) -> None:
    from _client import fetch_catalog
    from _shaping import build_sheet, get_search_detail

    c = client(args.site)
    cat = fetch_catalog(c)
    rt = _resolve_or_fail(cat, args.search, args.site)
    emit(build_sheet(get_search_detail(c, rt, args.search), query=args.query))
```

Subparser:
```python
    sp = sub.add_parser("inspect", help="shaped parameter sheet for one search")
    sp.add_argument("site")
    sp.add_argument("search")
    sp.add_argument("--query", help="hint used to shortlist huge vocabularies")
    sp.set_defaults(func=cmd_inspect)
```

- [ ] **Step 6: Run tests + live smoke; add TESTS.md cases**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_sheet.py -q` — Expected: 6 passed.
Run: `uv run scripts/wdk.py inspect plasmodb GenesByMolecularWeight | head -40`

| INS-1 | `wdk.py inspect plasmodb GenesByMolecularWeight` | 3 visible params; organism tree; min default 10000 | exact (offline fixture) | see tests/fixtures/mw.json | 2026-08-27 |
| INS-2 | `wdk.py inspect plasmodb GenesByGoTerm --query kinase` | go_typeahead shortlisted with note (5992 total) | range: total >5000 | 5992 | 2026-08-27 |
| INS-3 | `wdk.py inspect plasmodb GenesByMolecularWieght` | did-you-mean GenesByMolecularWeight, exit 1 | exact | — | 2026-08-27 |

- [ ] **Step 7: Commit**

```bash
git add veupathdb-wdk-strategies
git commit -m "feat: parameter sheet shaping and inspect subcommand"
```

---

### Task 6: `param-options`

**Files:**
- Modify: `veupathdb-wdk-strategies/scripts/_shaping.py` (add `param_options`)
- Modify: `veupathdb-wdk-strategies/scripts/wdk.py`
- Test: `veupathdb-wdk-strategies/tests/test_options.py`

**Interfaces:**
- Produces: `_shaping.param_options(search_data, param_name, query=None, limit=200) -> dict`. Unknown param → `{"error": "unknown parameter", "did_you_mean": [...], "valid": [all names]}` (a normal value, not an exception). Known param → `{"param", "type", "total", "shown", "options": [{"term","display"} or {"term","display","parent","leaf"}], "context_note"?}`. `--context` handling lives in the CLI: parents = every param whose `dependentParams` contains this param; when parents exist, the CLI re-fetches the detail with `context` = given `--context` pairs merged over parent defaults, and the output carries `context_note` naming the parent values used (e.g. `"vocabulary read under go_term_slim=No (default — pass --context go_term_slim=... to change)"`).
- Consumes: `get_search_detail(context=…)`, `tree_entries`, `flat_terms`, `_shortlist`.

- [ ] **Step 1: Write the failing tests**

`tests/test_options.py`:
```python
import json
import pathlib

FX = pathlib.Path(__file__).parent / "fixtures"


def _go():
    return json.loads((FX / "go.json").read_text())


def test_unknown_param_returns_did_you_mean():
    from _shaping import param_options

    out = param_options(_go(), "go_typahead")
    assert out["error"] == "unknown parameter"
    assert "go_typeahead" in out["did_you_mean"]
    assert "organism" in out["valid"]


def test_flat_vocab_query_filter():
    from _shaping import param_options

    out = param_options(_go(), "go_typeahead", query="kinase")
    assert 0 < out["shown"] <= 200
    assert out["total"] > 5000
    assert all("kinase" in o["display"].lower() for o in out["options"][:10])


def test_tree_vocab_options_have_leaf_flag():
    from _shaping import param_options

    out = param_options(_go(), "organism", query="falciparum")
    assert any(o["leaf"] for o in out["options"])
    assert all("falciparum" in o["term"].lower() for o in out["options"])


def test_live_dependent_context_note(live_client):
    from _client import fetch_catalog
    from _shaping import get_search_detail, param_options

    detail = get_search_detail(live_client, "transcript", "GenesByGoTerm")
    parents = [
        p["name"]
        for p in detail["parameters"]
        if "go_typeahead" in p.get("dependentParams", [])
    ]
    assert parents == ["go_term_slim"]
    refreshed = get_search_detail(
        live_client, "transcript", "GenesByGoTerm", context={"go_term_slim": "No"}
    )
    out = param_options(refreshed, "go_typeahead", query="kinase")
    assert out["shown"] > 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_options.py -q` — Expected: FAIL (`param_options` missing).

- [ ] **Step 3: Implement `param_options` in `_shaping.py`**

```python
def param_options(search_data, param_name, query=None, limit=200):
    by_name = {p["name"]: p for p in search_data.get("parameters", [])}
    if param_name not in by_name:
        return {
            "error": "unknown parameter",
            "did_you_mean": difflib.get_close_matches(
                param_name, list(by_name), n=5, cutoff=0.5
            ),
            "valid": sorted(by_name),
        }
    p = by_name[param_name]
    v = p.get("vocabulary")
    if v is None:
        return {"param": param_name, "type": p["type"], "total": 0, "shown": 0,
                "options": [], "note": "parameter has no vocabulary (free-text)"}
    if is_tree(v):
        entries = tree_entries(v)
    else:
        entries = [
            {"term": row[0], "display": row[1], "parent": row[2], "leaf": True}
            for row in v
        ]
    if query:
        q = query.lower()
        entries = [
            e
            for e in entries
            if q in e["term"].lower() or q in (e["display"] or "").lower()
        ]
    total_all = len(tree_entries(v)) if is_tree(v) else len(v)
    return {
        "param": param_name,
        "type": p["type"],
        "total": total_all,
        "shown": min(len(entries), limit),
        "options": entries[:limit],
    }
```

- [ ] **Step 4: Wire `param-options` into `wdk.py`**

```python
def _parse_kv(pairs):
    out = {}
    for pair in pairs or []:
        if "=" not in pair:
            fail(f"--context expects key=value, got '{pair}'")
        k, val = pair.split("=", 1)
        out[k] = val
    return out


def cmd_param_options(args) -> None:
    from _client import fetch_catalog
    from _shaping import get_search_detail, param_options

    c = client(args.site)
    cat = fetch_catalog(c)
    rt = _resolve_or_fail(cat, args.search, args.site)
    detail = get_search_detail(c, rt, args.search)
    parents = [
        p["name"]
        for p in detail["parameters"]
        if args.param in p.get("dependentParams", [])
    ]
    note = None
    if parents:
        given = _parse_kv(args.context)
        context = {
            name: given.get(
                name,
                next(
                    q.get("initialDisplayValue")
                    for q in detail["parameters"]
                    if q["name"] == name
                ),
            )
            for name in parents
        }
        detail = get_search_detail(c, rt, args.search, context=context)
        used = ", ".join(f"{k}={v}" for k, v in context.items())
        defaulted = [k for k in parents if k not in given]
        note = f"vocabulary read under {used}"
        if defaulted:
            note += (
                f" ({'/'.join(defaulted)} defaulted — pass --context "
                f"{defaulted[0]}=... to change)"
            )
    out = param_options(detail, args.param, query=args.query, limit=args.limit)
    if note and "error" not in out:
        out["context_note"] = note
    emit(out)
```

Subparser:
```python
    sp = sub.add_parser("param-options", help="browse/filter a parameter's vocabulary")
    sp.add_argument("site")
    sp.add_argument("search")
    sp.add_argument("param")
    sp.add_argument("--query", help="case-insensitive substring filter")
    sp.add_argument("--context", nargs="*", metavar="PARENT=VALUE",
                    help="values for params this vocabulary depends on")
    sp.add_argument("--limit", type=int, default=200)
    sp.set_defaults(func=cmd_param_options)
```

- [ ] **Step 5: Run tests + live smoke; add TESTS.md cases**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_options.py -q` — Expected: 4 passed.
Run: `uv run scripts/wdk.py param-options plasmodb GenesByGoTerm go_typeahead --query kinase | head -20`

| OPT-1 | `wdk.py param-options plasmodb GenesByGoTerm go_typeahead --query kinase` | filtered options + context_note naming go_term_slim | fields-present | <fill shown count> | 2026-08-27 |
| OPT-2 | `wdk.py param-options plasmodb GenesByGoTerm go_typahead` | did_you_mean includes go_typeahead | exact | — | 2026-08-27 |

- [ ] **Step 6: Commit**

```bash
git add veupathdb-wdk-strategies
git commit -m "feat: param-options with dependent-parameter context"
```

---

### Task 7: Parameter encoding; `count` and `preview`

**Files:**
- Modify: `veupathdb-wdk-strategies/scripts/_shaping.py` (add `ParamError`, `encode_params`, `extract_count`, `shape_records`, `run_report`)
- Modify: `veupathdb-wdk-strategies/scripts/wdk.py`
- Test: `veupathdb-wdk-strategies/tests/test_encode.py`, `veupathdb-wdk-strategies/tests/test_reports.py`

**Interfaces:**
- Produces:
  - `_shaping.ParamError(Exception)` — message carries did-you-mean / missing-required details.
  - `_shaping.encode_params(search_data, user_params: dict) -> dict[str, str]`: unknown names → `ParamError` with close matches; `input-step` params always `""`; absent/None values → param default (`initialDisplayValue`), hidden params included; visible required param with no default and no value → `ParamError` listing missing names; multi-pick accepts list or JSON-array string or scalar, validates membership (tree: `expand_to_leaves`, unknown terms → `ParamError` with close matches over all tree terms; flat: membership of `flat_terms`), tree+`countOnlyLeaves` selections expanded to leaves, result `json.dumps(list)`; single-pick validates membership; everything else `str(value)`.
  - `_shaping.extract_count(meta) -> (int | None, str | None)` — precedence `displayViewTotalCount, viewTotalCount, displayTotalCount, totalCount`; `(None, None)` if all absent.
  - `_shaping.shape_records(response) -> dict` — `{"count", "count_field", "counts": {<all four fields present>}, "records": [{"id": {name: value…}, "displayName", "attributes"}]}`; `count=None` → `"count": "unmeasured"`.
  - `_shaping.run_report(client, rt, search, wire_params, num_records=1, attributes=None) -> dict` — POSTs `/record-types/{rt}/searches/{search}/reports/standard` with `{"searchConfig": {"parameters": wire_params}, "reportConfig": {"pagination": {"offset": 0, "numRecords": num_records}}}` (+`"attributes"` when given), `idempotent=True`.
- Consumes: fixtures, `Client.post`.

- [ ] **Step 1: Write the failing tests**

`tests/test_encode.py`:
```python
import json
import pathlib

import pytest

FX = pathlib.Path(__file__).parent / "fixtures"


def _mw():
    return json.loads((FX / "mw.json").read_text())


def _bool():
    return json.loads((FX / "bool.json").read_text())


def test_defaults_fill_and_stringify():
    from _shaping import encode_params

    wire = encode_params(_mw(), {"organism": ["Plasmodium falciparum 3D7"]})
    assert wire["min_molecular_weight"] == "10000"
    assert wire["max_molecular_weight"] == "50000"
    assert json.loads(wire["organism"]) == ["Plasmodium falciparum 3D7"]


def test_numbers_are_stringified():
    from _shaping import encode_params

    wire = encode_params(
        _mw(),
        {"organism": ["Plasmodium falciparum 3D7"], "min_molecular_weight": 25000},
    )
    assert wire["min_molecular_weight"] == "25000"


def test_tree_parent_expands_to_leaves():
    from _shaping import encode_params

    wire = encode_params(_mw(), {"organism": ["Plasmodium"]})
    leaves = json.loads(wire["organism"])
    assert len(leaves) > 5
    assert "Plasmodium" not in leaves  # the parent itself is never sent


def test_unknown_param_and_unknown_value():
    from _shaping import ParamError, encode_params

    with pytest.raises(ParamError) as e:
        encode_params(_mw(), {"organsim": ["x"]})
    assert "organism" in str(e.value)
    with pytest.raises(ParamError) as e:
        encode_params(_mw(), {"organism": ["Plasmodium falciparum 3D8"]})
    assert "3D7" in str(e.value)  # close match suggested


def test_input_step_params_are_empty_strings():
    from _shaping import encode_params

    wire = encode_params(_bool(), {"bq_operator": "INTERSECT"})
    left = "bq_left_op_TranscriptRecordClasses_TranscriptRecordClass"
    right = "bq_right_op_TranscriptRecordClasses_TranscriptRecordClass"
    assert wire[left] == "" and wire[right] == ""
    assert wire["bq_operator"] == "INTERSECT"


def test_extract_count_precedence_and_unmeasured():
    from _shaping import extract_count

    assert extract_count({"displayViewTotalCount": 5, "totalCount": 9}) == (
        5,
        "displayViewTotalCount",
    )
    assert extract_count({"totalCount": 9}) == (9, "totalCount")
    assert extract_count({}) == (None, None)
```

`tests/test_reports.py`:
```python
import json


def test_live_count_mw_pfalciparum(live_client):
    from _shaping import encode_params, extract_count, get_search_detail, run_report

    detail = get_search_detail(live_client, "transcript", "GenesByMolecularWeight")
    wire = encode_params(detail, {"organism": ["Plasmodium falciparum 3D7"]})
    resp = run_report(live_client, "transcript", "GenesByMolecularWeight", wire)
    count, field = extract_count(resp["meta"])
    assert field == "displayViewTotalCount"
    assert 1800 <= count <= 3000  # gold 2365 on 2026-08-27; ±~20% for data drift


def test_live_preview_records(live_client):
    from _shaping import encode_params, get_search_detail, run_report, shape_records

    detail = get_search_detail(live_client, "transcript", "GenesByMolecularWeight")
    wire = encode_params(detail, {"organism": ["Plasmodium falciparum 3D7"]})
    resp = run_report(
        live_client, "transcript", "GenesByMolecularWeight", wire, num_records=3
    )
    shaped = shape_records(resp)
    assert len(shaped["records"]) == 3
    assert "gene_source_id" in shaped["records"][0]["id"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_encode.py tests/test_reports.py -q` — Expected: FAIL (missing names).

- [ ] **Step 3: Implement in `_shaping.py`**

```python
class ParamError(Exception):
    pass


COUNT_FIELDS = (
    "displayViewTotalCount",
    "viewTotalCount",
    "displayTotalCount",
    "totalCount",
)


def _as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip().startswith("["):
        return json.loads(value)
    return [value]


def encode_params(search_data, user_params):
    params = search_data.get("parameters", [])
    by_name = {p["name"]: p for p in params}
    unknown = sorted(set(user_params) - set(by_name))
    if unknown:
        hints = {
            u: difflib.get_close_matches(u, list(by_name), n=3, cutoff=0.5)
            for u in unknown
        }
        raise ParamError(
            f"unknown parameter(s) {unknown}; did you mean: {hints}? "
            f"valid: {sorted(by_name)}"
        )
    wire, missing = {}, []
    for p in params:
        name, ptype = p["name"], p["type"]
        if ptype == "input-step":
            wire[name] = ""
            continue
        supplied = name in user_params and user_params[name] is not None
        value = user_params[name] if supplied else p.get("initialDisplayValue")
        if value is None:
            if not p.get("allowEmptyValue", False) and p.get("isVisible", True):
                missing.append(name)
            wire[name] = ""
            continue
        vocab = p.get("vocabulary")
        if ptype == "multi-pick-vocabulary":
            items = [str(i) for i in _as_list(value)]
            if is_tree(vocab):
                leaves, bad = expand_to_leaves(vocab, items)
                if bad:
                    all_terms = [e["term"] for e in tree_entries(vocab)]
                    hints = {
                        b: difflib.get_close_matches(b, all_terms, n=3, cutoff=0.5)
                        for b in bad
                    }
                    raise ParamError(f"unknown value(s) for '{name}': {hints}")
                items = leaves
            elif isinstance(vocab, list):
                valid = set(flat_terms(vocab))
                bad = [i for i in items if i not in valid]
                if bad:
                    hints = {
                        b: difflib.get_close_matches(b, sorted(valid), n=3, cutoff=0.5)
                        for b in bad
                    }
                    raise ParamError(f"unknown value(s) for '{name}': {hints}")
            wire[name] = json.dumps(items)
        else:
            sval = str(value)
            if (
                ptype == "single-pick-vocabulary"
                and isinstance(vocab, list)
                and sval not in set(flat_terms(vocab))
            ):
                hint = difflib.get_close_matches(
                    sval, flat_terms(vocab), n=3, cutoff=0.5
                )
                raise ParamError(
                    f"'{sval}' is not in the vocabulary of '{name}'; "
                    f"did you mean {hint}?"
                )
            wire[name] = sval
    if missing:
        raise ParamError(
            f"required parameter(s) with no value and no default: {missing}"
        )
    return wire


def extract_count(meta):
    for field in COUNT_FIELDS:
        if meta.get(field) is not None:
            return meta[field], field
    return None, None


def shape_records(response):
    meta = response.get("meta", {})
    count, field = extract_count(meta)
    return {
        "count": count if count is not None else "unmeasured",
        "count_field": field,
        "counts": {f: meta.get(f) for f in COUNT_FIELDS},
        "records": [
            {
                "id": {part["name"]: part["value"] for part in r.get("id", [])},
                "displayName": r.get("displayName"),
                "attributes": r.get("attributes", {}),
            }
            for r in response.get("records", [])
        ],
    }


def run_report(client, rt, search, wire_params, num_records=1, attributes=None):
    body = {
        "searchConfig": {"parameters": wire_params},
        "reportConfig": {"pagination": {"offset": 0, "numRecords": num_records}},
    }
    if attributes:
        body["reportConfig"]["attributes"] = attributes
    return client.post(f"/record-types/{rt}/searches/{search}/reports/standard", body)
```

Note the `input-dataset` clause: only `input-step` is forced to `""`; an `input-dataset` param falls through to normal handling (v1 has no dataset upload — a search requiring one will fail with WDK's own message, which is acceptable and documented in gotchas.md).

- [ ] **Step 4: Wire `count` and `preview` into `wdk.py`**

```python
def _load_params(raw):
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"--params is not valid JSON: {e}")
    if not isinstance(params, dict):
        fail("--params must be a JSON object of {param: value}")
    return params


def _prepared(args):
    from _client import fetch_catalog
    from _shaping import ParamError, encode_params, get_search_detail

    c = client(args.site)
    cat = fetch_catalog(c)
    rt = _resolve_or_fail(cat, args.search, args.site)
    detail = get_search_detail(c, rt, args.search)
    try:
        wire = encode_params(detail, _load_params(args.params))
    except ParamError as e:
        fail(str(e))
    return c, rt, wire


def cmd_count(args) -> None:
    from _shaping import extract_count, run_report

    c, rt, wire = _prepared(args)
    resp = run_report(c, rt, args.search, wire, num_records=1)
    count, field = extract_count(resp.get("meta", {}))
    emit(
        {
            "search": args.search,
            "count": count if count is not None else "unmeasured",
            "count_field": field,
            "counts": {
                k: resp.get("meta", {}).get(k)
                for k in (
                    "displayViewTotalCount",
                    "viewTotalCount",
                    "displayTotalCount",
                    "totalCount",
                )
            },
        }
    )


def cmd_preview(args) -> None:
    from _shaping import run_report, shape_records

    c, rt, wire = _prepared(args)
    attrs = args.attributes.split(",") if args.attributes else None
    emit(
        shape_records(
            run_report(c, rt, args.search, wire, num_records=args.limit, attributes=attrs)
        )
    )
```

Subparsers:
```python
    sp = sub.add_parser("count", help="result count without creating anything (anonymous report)")
    sp.add_argument("site")
    sp.add_argument("search")
    sp.add_argument("--params", required=True, help='JSON object, e.g. \'{"organism": ["Plasmodium"]}\'')
    sp.set_defaults(func=cmd_count)

    sp = sub.add_parser("preview", help="sample records without creating anything")
    sp.add_argument("site")
    sp.add_argument("search")
    sp.add_argument("--params", required=True)
    sp.add_argument("--limit", type=int, default=5)
    sp.add_argument("--attributes", help="comma-separated attribute names")
    sp.set_defaults(func=cmd_preview)
```

- [ ] **Step 5: Run tests + CLI smoke; add TESTS.md cases**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_encode.py tests/test_reports.py -q` — Expected: 8 passed.
Run: `uv run scripts/wdk.py count plasmodb GenesByMolecularWeight --params '{"organism": ["Plasmodium falciparum 3D7"]}'` — Expected: count ≈ 2365.
Also run a parent-expansion count: `--params '{"organism": ["Plasmodium"]}'` — must be **larger** than the 3D7-only count.

| CNT-1 | count MW, organism=[P. falciparum 3D7], 10000–50000 defaults | 2365 genes | range 1800–3000 | 2365 | 2026-08-27 |
| CNT-2 | count MW, organism=["Plasmodium"] (parent expansion) | > CNT-1 count | range | <fill> | 2026-08-27 |
| PRV-1 | preview MW --limit 3 | 3 records with gene_source_id ids | fields-present | first id PF3D7_0100200 (sorting-dependent) | 2026-08-27 |

- [ ] **Step 6: Commit**

```bash
git add veupathdb-wdk-strategies
git commit -m "feat: param encoding with tree expansion; count and preview subcommands"
```

---

### Task 8: Strategy creation (`_strategy.py`); `create-strategy`, `strategy`, `list-strategies`, `delete-strategy`

**Files:**
- Create: `veupathdb-wdk-strategies/scripts/_strategy.py`
- Modify: `veupathdb-wdk-strategies/scripts/wdk.py`
- Test: `veupathdb-wdk-strategies/tests/test_strategy.py`

**Interfaces:**
- Produces:
  - `_strategy.SpecError(Exception)`
  - `_strategy.validate_spec(node) -> str` — returns the first leaf's search name; raises `SpecError` on malformed nodes. Node forms (exactly one key each): `{"leaf": {"search", "params"}}`, `{"combine": {"operator", "left", "right"}}` (operator in `UNION|INTERSECT|MINUS|RMINUS|LONLY|RONLY`), `{"transform": {"search", "params", "input"}}`.
  - `_strategy.build_strategy(client, catalog, spec, name) -> dict` — creates all steps bottom-up then the strategy; returns `shape_strategy` output. Every creating POST uses `idempotent=False`.
  - `_strategy.shape_strategy(site_id, detail) -> dict` — `{"strategy_id", "name", "url" (via strategy_url), "root_step_id", "estimated_size", "steps": [{"step_id", "search", "displayName", "count", "valid"}]}`. Tolerant to WDK field naming: strategy id from `strategyId` or `id`; root step from `rootStepId` or the stepTree root; steps map from `steps` dict. `count`: `estimatedSize` when present and ≥ 0 else `"unmeasured"`.
  - `_strategy.find_boolean_search(catalog, client, rt) -> (search_name, left_param, right_param)` — search whose name starts `boolean_question_` in `catalog["searches"][rt]`; operand names read from its expanded detail (params starting `bq_left_op` / `bq_right_op`). Raises `SpecError` if the record type has no boolean search.
- Consumes: `encode_params`, `get_search_detail`, `resolve_search`, `all_search_names`, `Client`, `strategy_url`.

- [ ] **Step 1: Write the failing tests**

`tests/test_strategy.py`:
```python
import pytest

MW = "GenesByMolecularWeight"
PF = ["Plasmodium falciparum 3D7"]


def _leaf(minw, maxw):
    return {
        "leaf": {
            "search": MW,
            "params": {
                "organism": PF,
                "min_molecular_weight": str(minw),
                "max_molecular_weight": str(maxw),
            },
        }
    }


def test_validate_spec_shapes():
    from _strategy import SpecError, validate_spec

    assert validate_spec(_leaf(1, 2)) == MW
    combined = {"combine": {"operator": "INTERSECT", "left": _leaf(1, 2), "right": _leaf(2, 3)}}
    assert validate_spec(combined) == MW
    with pytest.raises(SpecError):
        validate_spec({"combine": {"operator": "XOR", "left": _leaf(1, 2), "right": _leaf(2, 3)}})
    with pytest.raises(SpecError):
        validate_spec({"leaf": {"params": {}}})
    with pytest.raises(SpecError):
        validate_spec({"leaf": {}, "combine": {}})


@pytest.fixture
def strategy_tracker(live_client):
    created = []
    yield created
    uid = live_client.user_id()
    for sid in created:
        try:
            live_client.delete(f"/users/{uid}/strategies/{sid}")
        except Exception:
            pass  # 404 etc.: already gone


def test_live_two_leaf_intersect(live_client, strategy_tracker):
    from _client import fetch_catalog
    from _strategy import build_strategy

    spec = {
        "combine": {
            "operator": "INTERSECT",
            "left": _leaf(10000, 50000),
            "right": _leaf(40000, 100000),
        }
    }
    cat = fetch_catalog(live_client)
    out = build_strategy(live_client, cat, spec, "__skill_test__: intersect mw")
    strategy_tracker.append(out["strategy_id"])
    assert out["url"].endswith(f"/app/workspace/strategies/{out['strategy_id']}")
    assert len(out["steps"]) == 3
    root = out["estimated_size"]
    leaf_counts = [s["count"] for s in out["steps"] if s["search"] == MW]
    assert all(isinstance(c, int) for c in leaf_counts)
    assert isinstance(root, int)
    assert root <= min(leaf_counts)  # intersect can't exceed either input
    assert root > 0  # 40k-50k overlap is non-empty
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_strategy.py -q` — Expected: FAIL (`No module named '_strategy'`).

- [ ] **Step 3: Write `scripts/_strategy.py`**

```python
"""Declarative step-tree spec -> WDK steps + strategy.

Spec nodes (exactly one key each):
  {"leaf":      {"search": name, "params": {...}}}
  {"combine":   {"operator": OP, "left": node, "right": node}}
  {"transform": {"search": name, "params": {...}, "input": node}}
OP: UNION | INTERSECT | MINUS | RMINUS | LONLY | RONLY
"""
from _shaping import all_search_names, encode_params, get_search_detail
from _sites import strategy_url

OPERATORS = {"UNION", "INTERSECT", "MINUS", "RMINUS", "LONLY", "RONLY"}


class SpecError(Exception):
    pass


def _kind(node):
    if not isinstance(node, dict) or len(node) != 1:
        raise SpecError(
            f"a spec node must have exactly one of leaf/combine/transform: {node!r:.120}"
        )
    kind = next(iter(node))
    if kind not in ("leaf", "combine", "transform"):
        raise SpecError(f"unknown node kind '{kind}'")
    return kind, node[kind]


def validate_spec(node):
    """Returns the search name of the leftmost leaf (used to resolve record type)."""
    kind, body = _kind(node)
    if kind == "leaf":
        if "search" not in body or not isinstance(body.get("params", {}), dict):
            raise SpecError(f"leaf needs 'search' and object 'params': {body!r:.120}")
        return body["search"]
    if kind == "combine":
        if body.get("operator") not in OPERATORS:
            raise SpecError(
                f"combine operator must be one of {sorted(OPERATORS)}, "
                f"got {body.get('operator')!r}"
            )
        first = validate_spec(body["left"])
        validate_spec(body["right"])
        return first
    # transform
    if "search" not in body or "input" not in body:
        raise SpecError(f"transform needs 'search' and 'input': {body!r:.120}")
    return validate_spec(body["input"])


def find_boolean_search(catalog, client, rt):
    listing = catalog["searches"].get(rt, [])
    name = next(
        (s["name"] for s in listing if s["name"].startswith("boolean_question_")), None
    )
    if name is None:
        raise SpecError(f"record type '{rt}' has no boolean (combine) search")
    detail = get_search_detail(client, rt, name)
    left = next(p["name"] for p in detail["parameters"] if p["name"].startswith("bq_left_op"))
    right = next(p["name"] for p in detail["parameters"] if p["name"].startswith("bq_right_op"))
    return name, left, right


def build_strategy(client, catalog, spec, name):
    first_search = validate_spec(spec)
    names = all_search_names(catalog)
    if first_search not in names:
        raise SpecError(f"unknown search '{first_search}'")
    rt = names[first_search]
    uid = client.user_id()
    bool_cache = {}

    def create(node):
        kind, body = _kind(node)
        if kind == "leaf":
            detail = get_search_detail(client, rt, body["search"])
            wire = encode_params(detail, body.get("params", {}))
            step = client.post(
                f"/users/{uid}/steps",
                {"searchName": body["search"], "searchConfig": {"parameters": wire}},
                idempotent=False,
            )
            return {"stepId": step["id"]}
        if kind == "transform":
            child = create(body["input"])
            detail = get_search_detail(client, rt, body["search"])
            wire = encode_params(detail, body.get("params", {}))  # input-step -> ""
            step = client.post(
                f"/users/{uid}/steps",
                {"searchName": body["search"], "searchConfig": {"parameters": wire}},
                idempotent=False,
            )
            return {"stepId": step["id"], "primaryInput": child}
        # combine
        left_tree = create(body["left"])
        right_tree = create(body["right"])
        if rt not in bool_cache:
            bool_cache[rt] = find_boolean_search(catalog, client, rt)
        bname, lparam, rparam = bool_cache[rt]
        step = client.post(
            f"/users/{uid}/steps",
            {
                "searchName": bname,
                "searchConfig": {
                    "parameters": {
                        lparam: "",
                        rparam: "",
                        "bq_operator": body["operator"],
                    }
                },
            },
            idempotent=False,
        )
        return {
            "stepId": step["id"],
            "primaryInput": left_tree,
            "secondaryInput": right_tree,
        }

    tree = create(spec)
    strat = client.post(
        f"/users/{uid}/strategies",
        {"name": name, "isPublic": False, "isSaved": False, "stepTree": tree},
        idempotent=False,
    )
    sid = strat.get("strategyId", strat.get("id"))
    detail = client.get(f"/users/{uid}/strategies/{sid}")
    return shape_strategy(client.site_id, detail)


def _count(value):
    return value if isinstance(value, int) and value >= 0 else "unmeasured"


def shape_strategy(site_id, detail):
    sid = detail.get("strategyId", detail.get("id"))
    tree = detail.get("stepTree", {})
    root = detail.get("rootStepId") or tree.get("stepId")
    steps = []
    for step_id, s in (detail.get("steps") or {}).items():
        steps.append(
            {
                "step_id": int(step_id),
                "search": s.get("searchName"),
                "displayName": s.get("customName") or s.get("displayName"),
                "count": _count(s.get("estimatedSize")),
                "valid": (s.get("validation") or {}).get("isValid"),
            }
        )
    root_count = next(
        (s["count"] for s in steps if s["step_id"] == root), "unmeasured"
    )
    return {
        "strategy_id": sid,
        "name": detail.get("name"),
        "url": strategy_url(site_id, sid),
        "root_step_id": root,
        "estimated_size": root_count,
        "steps": steps,
    }
```

**Live-shape caveat for the implementer:** `shape_strategy`'s field fallbacks (`strategyId`/`id`, `rootStepId`/stepTree root, `steps` as a dict keyed by step id, `estimatedSize`) follow pathfinder's models but MUST be confirmed against the real GET response during the live test. If the test fails on shaping, print the raw `detail` keys, adjust `shape_strategy` to the observed names, and record the observed shape in `references/strategies.md`. Do not weaken the test's semantic assertions (root ≤ min(leaf counts), root > 0).

- [ ] **Step 4: Wire the four subcommands into `wdk.py`**

```python
def cmd_create_strategy(args) -> None:
    from _client import fetch_catalog
    from _shaping import ParamError
    from _strategy import SpecError, build_strategy

    c = client(args.site)
    try:
        spec = json.loads(args.spec)
    except json.JSONDecodeError as e:
        fail(f"--spec is not valid JSON: {e}")
    try:
        emit(build_strategy(c, fetch_catalog(c), spec, args.name))
    except (SpecError, ParamError) as e:
        fail(str(e))


def cmd_strategy(args) -> None:
    from _strategy import shape_strategy

    c = client(args.site)
    uid = c.user_id()
    emit(shape_strategy(args.site, c.get(f"/users/{uid}/strategies/{args.id}")))


def cmd_list_strategies(args) -> None:
    from _sites import strategy_url

    c = client(args.site)
    uid = c.user_id()
    strategies = c.get(f"/users/{uid}/strategies")
    emit(
        [
            {
                "strategy_id": s.get("strategyId", s.get("id")),
                "name": s.get("name"),
                "url": strategy_url(args.site, s.get("strategyId", s.get("id"))),
            }
            for s in strategies
        ]
    )


def cmd_delete_strategy(args) -> None:
    if not args.yes:
        fail("refusing to delete without --yes")
    c = client(args.site)
    uid = c.user_id()
    c.delete(f"/users/{uid}/strategies/{args.id}")
    emit({"deleted": args.id})
```

Subparsers:
```python
    sp = sub.add_parser("create-strategy", help="create steps + strategy from a declarative JSON spec")
    sp.add_argument("site")
    sp.add_argument("--spec", required=True, help="JSON node tree; see references/strategies.md")
    sp.add_argument("--name", default="wdk.py strategy")
    sp.set_defaults(func=cmd_create_strategy)

    sp = sub.add_parser("strategy", help="strategy detail: tree, counts, url")
    sp.add_argument("site")
    sp.add_argument("id", type=int)
    sp.set_defaults(func=cmd_strategy)

    sp = sub.add_parser("list-strategies", help="list your strategies on a site")
    sp.add_argument("site")
    sp.set_defaults(func=cmd_list_strategies)

    sp = sub.add_parser("delete-strategy", help="delete a strategy (destructive)")
    sp.add_argument("site")
    sp.add_argument("id", type=int)
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=cmd_delete_strategy)
```

- [ ] **Step 5: Run tests; capture VectorBase variant; add TESTS.md cases**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_strategy.py -q` — Expected: 2 passed (live test creates then deletes its strategy — verify with `uv run scripts/wdk.py list-strategies plasmodb` that no `__skill_test__` strategies remain).

Then capture a VectorBase gold standard by hand (VectorBase organism values differ):
1. `uv run scripts/wdk.py param-options vectorbase GenesByMolecularWeight organism --query gambiae` — pick a leaf term (expect `Anopheles gambiae PEST` or similar).
2. `uv run scripts/wdk.py count vectorbase GenesByMolecularWeight --params '{"organism": ["<leaf term>"]}'` — record the count.
3. Add to `tests/test_reports.py`:
```python
def test_live_count_vectorbase(token):
    from _client import Client
    from _shaping import encode_params, extract_count, get_search_detail, run_report

    c = Client("vectorbase", token=token)
    detail = get_search_detail(c, "transcript", "GenesByMolecularWeight")
    wire = encode_params(detail, {"organism": ["<the leaf term you found>"]})
    resp = run_report(c, "transcript", "GenesByMolecularWeight", wire)
    count, _ = extract_count(resp["meta"])
    assert count > 0  # tighten to ±20% of the captured gold in TESTS.md
```
Replace the placeholder organism with the real term and tighten the assertion to the captured range before committing.

| STR-1 | create-strategy plasmodb, MW(10–50k) ∩ MW(40–100k) | 3 steps; root ≤ min(leaves); root > 0; url valid | range | root=<fill>, leaves=<fill> | 2026-08-27 |
| STR-2 | `wdk.py strategy plasmodb <id>` | same shape as create output | fields-present | — | 2026-08-27 |
| STR-3 | `wdk.py delete-strategy plasmodb <id>` (no --yes) | refuses, exit 1 | exact | — | 2026-08-27 |
| CNT-3 | count vectorbase MW, organism=[<captured leaf>] | >0 | range ±20% of gold | <fill> | 2026-08-27 |

- [ ] **Step 6: Commit**

```bash
git add veupathdb-wdk-strategies
git commit -m "feat: declarative strategy creation with combine/transform support"
```

---

### Task 9: `results` and `download-url`

**Files:**
- Modify: `veupathdb-wdk-strategies/scripts/wdk.py`
- Test: `veupathdb-wdk-strategies/tests/test_results.py`

**Interfaces:**
- Consumes: `shape_records`, `Client`, a step id from a freshly created strategy (the test creates and cleans up its own).
- Produces (CLI only): `results SITE --step ID [--limit N] [--attributes a,b]` → shaped records via POST `/users/{uid}/steps/{id}/reports/standard` with `{"reportConfig": {"pagination": {"offset": 0, "numRecords": N}}}` (+attributes). `download-url SITE --step ID [--report NAME] [--config JSON]` → POST `/temporary-results` with `{"stepId": ID, "reportName": NAME, "reportConfig": CONFIG}`; default `NAME="attributesTabular"`, default `CONFIG={"attributes": ["primary_key"], "includeHeader": true, "attachmentType": "plain"}`. Output `{"download_url": f"{service_url(site)}/temporary-results/{id}"}`.

- [ ] **Step 1: Write the failing test**

`tests/test_results.py`:
```python
import pytest

MW = "GenesByMolecularWeight"


@pytest.fixture
def live_step(live_client):
    """A real step inside a real strategy (WDK refuses to run orphan steps)."""
    from _client import fetch_catalog
    from _strategy import build_strategy

    spec = {
        "leaf": {
            "search": MW,
            "params": {"organism": ["Plasmodium falciparum 3D7"]},
        }
    }
    out = build_strategy(
        live_client, fetch_catalog(live_client), spec, "__skill_test__: results"
    )
    yield out["root_step_id"]
    uid = live_client.user_id()
    try:
        live_client.delete(f"/users/{uid}/strategies/{out['strategy_id']}")
    except Exception:
        pass


def test_live_step_records(live_client, live_step):
    from _shaping import shape_records

    uid = live_client.user_id()
    resp = live_client.post(
        f"/users/{uid}/steps/{live_step}/reports/standard",
        {"reportConfig": {"pagination": {"offset": 0, "numRecords": 2}}},
    )
    shaped = shape_records(resp)
    assert len(shaped["records"]) == 2
    assert "gene_source_id" in shaped["records"][0]["id"]


def test_live_download_url(live_client, live_step):
    resp = live_client.post(
        "/temporary-results",
        {
            "stepId": live_step,
            "reportName": "attributesTabular",
            "reportConfig": {
                "attributes": ["primary_key"],
                "includeHeader": True,
                "attachmentType": "plain",
            },
        },
        idempotent=False,
    )
    assert resp.get("id"), f"unexpected temporary-results response: {resp!r}"
```

**Live-shape caveat:** if `attributesTabular`/`primary_key` is rejected (422), probe the step's report names via the WDK error message, try `{"reportName": "standard", "reportConfig": {}}`, and record what actually works in TESTS.md and `references/strategies.md`; update the CLI defaults to the working combination.

- [ ] **Step 2: Run to verify failure**

Run: `uv run --with pytest --with httpx python -m pytest tests/test_results.py -q` — the first test should PASS already (it uses existing plumbing); `test_live_download_url` exercises the new endpoint. If both pass, proceed (this task's new code is CLI wiring).

- [ ] **Step 3: Wire subcommands**

```python
def cmd_results(args) -> None:
    from _shaping import shape_records

    c = client(args.site)
    uid = c.user_id()
    body = {"reportConfig": {"pagination": {"offset": 0, "numRecords": args.limit}}}
    if args.attributes:
        body["reportConfig"]["attributes"] = args.attributes.split(",")
    emit(shape_records(c.post(f"/users/{uid}/steps/{args.step}/reports/standard", body)))


def cmd_download_url(args) -> None:
    from _sites import service_url

    c = client(args.site)
    if args.config:
        try:
            config = json.loads(args.config)
        except json.JSONDecodeError as e:
            fail(f"--config is not valid JSON: {e}")
    else:
        config = {
            "attributes": ["primary_key"],
            "includeHeader": True,
            "attachmentType": "plain",
        }
    resp = c.post(
        "/temporary-results",
        {"stepId": args.step, "reportName": args.report, "reportConfig": config},
        idempotent=False,
    )
    emit({"download_url": f"{service_url(args.site)}/temporary-results/{resp['id']}"})
```

Subparsers:
```python
    sp = sub.add_parser("results", help="records for an existing step")
    sp.add_argument("site")
    sp.add_argument("--step", type=int, required=True)
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--attributes")
    sp.set_defaults(func=cmd_results)

    sp = sub.add_parser("download-url", help="temporary download URL for a step's results")
    sp.add_argument("site")
    sp.add_argument("--step", type=int, required=True)
    sp.add_argument("--report", default="attributesTabular")
    sp.add_argument("--config", help="JSON reportConfig override")
    sp.set_defaults(func=cmd_download_url)
```

- [ ] **Step 4: Run full suite; add TESTS.md cases**

Run: `uv run --with pytest --with httpx python -m pytest tests -q` — Expected: all green, no `__skill_test__` strategies left behind on plasmodb.

| RES-1 | `wdk.py results plasmodb --step <id> --limit 2` | 2 records with gene ids | fields-present | — | 2026-08-27 |
| DL-1 | `wdk.py download-url plasmodb --step <id>` | URL containing /temporary-results/ | fields-present | report=<fill working reportName> | 2026-08-27 |

- [ ] **Step 5: Commit**

```bash
git add veupathdb-wdk-strategies
git commit -m "feat: step results and temporary-result download URLs"
```

---

### Task 10: SKILL.md, references, TESTS.md polish

**Files:**
- Create: `veupathdb-wdk-strategies/SKILL.md`
- Create: `veupathdb-wdk-strategies/references/auth.md`, `references/parameters.md`, `references/strategies.md`, `references/gotchas.md`
- Modify: `veupathdb-wdk-strategies/TESTS.md` (intro, fill any `<fill>` gaps)

**Interfaces:** none (documentation). SKILL.md MUST be ≤200 lines (`wc -l` check is a step).

- [ ] **Step 1: Write `SKILL.md`**

```markdown
---
name: veupathdb-wdk-strategies
description: Build, run, and manage search strategies on VEuPathDB sites (PlasmoDB, VectorBase, ToxoDB, FungiDB, TriTrypDB, etc.) via the WDK REST API. Use when the user wants to find genes/records by biological criteria on a VEuPathDB site, combine searches (intersect/union/minus), count or preview results, or fetch/download result records.
---

# VEuPathDB WDK search strategies

All commands: `uv run scripts/wdk.py <subcommand> ...` (run from this skill's
directory). Machine-readable JSON on stdout; errors on stderr with exit 1.
`--help` on any subcommand. Supply-chain note: uv installs are expected to be
date-pinned via `exclude-newer` in `~/.config/uv/uv.toml`.

## Auth (required for nearly everything)

`VEUPATHDB_BEARER_TOKEN` env var, or `.env` at the repo root. Must be a
REGISTERED user's token — WDK silently mints guests otherwise. Verify first:

    uv run scripts/wdk.py whoami plasmodb

Details and how to obtain a token: references/auth.md

## The workflow

1. **Pick the site**: `sites` lists all 14 (plasmodb, vectorbase, toxodb, …).
2. **Discover searches** — dispatch a SUB-AGENT (keeps your context clean):
   its prompt = the research goal + "run `uv run scripts/wdk.py catalog SITE`,
   read every line, return 3–8 candidate searches (name, record type, why),
   tagged seed/filter/transform". The dump is ~25–75k tokens. No sub-agents
   available? Read the dump yourself. `find-searches SITE QUERY` is a quick
   lexical fallback when you already know roughly the name.
3. **Inspect each candidate**: `inspect SITE SEARCH [--query HINT]` returns the
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
6. **Fetch results**: `results SITE --step ID`, `download-url SITE --step ID`.
   Manage: `strategy`, `list-strategies`, `delete-strategy ... --yes`.

## Subcommands

| cmd | purpose |
|---|---|
| sites | list site ids and service URLs |
| whoami SITE | verify token, print numeric user id |
| record-types SITE | list record type segments |
| searches SITE RT | searches for one record type (TSV) |
| catalog SITE [--record-type RT] [--refresh] | full compact catalog (TSV) — discovery input |
| find-searches SITE QUERY | lexical convenience lookup |
| inspect SITE SEARCH [--query HINT] | shaped parameter sheet |
| param-options SITE SEARCH PARAM [--query Q] [--context P=V] | browse a vocabulary |
| count SITE SEARCH --params JSON | count without creating anything |
| preview SITE SEARCH --params JSON [--limit N] | sample records, no writes |
| create-strategy SITE --spec JSON [--name S] | steps + strategy, returns URL |
| strategy SITE ID / list-strategies SITE | read back |
| delete-strategy SITE ID --yes | destructive |
| results SITE --step ID | records for a step |
| download-url SITE --step ID | temporary download URL |

## Top gotchas (full list: references/gotchas.md)

- **Vocabulary values are exact strings.** Never paraphrase; copy from the
  sheet or `param-options`. Wrong values are caught locally with suggestions.
- **Tree parents are auto-expanded to leaves** on submit (WDK would silently
  return 0 rows otherwise). Selecting "Plasmodium" means all its leaf genomes.
- **Multi-evidence needs enumeration**: a multi-pick param must list EVERY
  covered value, never one representative.
- **Defaults are disclosed**: params you leave null use the search default
  (shown in the sheet) — tell the user which defaults applied.

## Deeper reference (read on demand)

- references/auth.md — token acquisition, cookie transport, guest refusal
- references/parameters.md — the 11 param types, dependent vocabularies
- references/strategies.md — stepTree semantics, spec format, step kinds
- references/gotchas.md — every known silent-failure mode

Out of scope (v1): semantic search, site-search, control tests, enrichment,
step analyses, filters, phyletic profile patterns, dataset/basket uploads, EDA.
Tests + gold standards: TESTS.md.
```

- [ ] **Step 2: Verify the 200-line limit**

Run: `wc -l veupathdb-wdk-strategies/SKILL.md` — Expected: ≤ 200.

- [ ] **Step 3: Write `references/auth.md`**

```markdown
# Authentication and transport

## Getting a token

Register at the target site (e.g. plasmodb.org → Register). A logged-in
browser holds the token in the `Authorization` cookie; the profile page's
"Service Access" section describes API-key access. Put it in the environment
as `VEUPATHDB_BEARER_TOKEN` or in `.env` at the repo root (gitignored).

## How auth actually works (distilled from pathfinder's WDK rules)

- The token travels as a COOKIE: `Cookie: Authorization=<token>`. Never as an
  `Authorization:` header. Tomcat honors the FIRST cookie pair if duplicates
  are sent — the client here sends exactly one.
- An uncredentialed request is NOT rejected: WDK mints a fresh guest user per
  request. Guests get 401s on `/users/…` programmatic paths (VEuPathDB policy
  since 2026-08-19) and results that silently belong to nobody. Always verify
  with `whoami` first; the client refuses guest tokens for user-scoped calls.
- `GET /users/current` → `{"id": <int>, "isGuest": bool, "email": …}`. The
  client resolves the numeric id ONCE and uses it in every `/users/{uid}/…`
  path (the `current` alias is only ever used for that one resolution call —
  concrete ids make ownership errors loud 403s instead of silent misfires).
- Logout does NOT invalidate a bearer token; treat tokens as long-lived
  secrets. Never print or commit them.

## Transport quirks the client handles for you

- Retries ×3 (exponential backoff) on timeouts, connect errors, 5xx.
- A 2xx body of `{"status": "accepted", "message": "WDK-DELAYED-RESULT"}` means
  "result not ready" and is retried like a failure.
- Step/strategy/temporary-result CREATION is never retried (a proxy 502 after
  a committed create would otherwise duplicate objects).
- 422 = well-formed request, semantically invalid values; the WDK message is
  surfaced verbatim — read it, it names the offending parameter.
- Timeouts: 30 s per site; 120 s for the veupathdb.org portal.
```

- [ ] **Step 4: Write `references/parameters.md`**

```markdown
# WDK parameters and vocabularies

Every parameter value is a STRING on the wire. `encode_params` handles the
conversions below; this doc explains what it does and why.

## Parameter types

string, number, date, timestamp, number-range, date-range,
single-pick-vocabulary, multi-pick-vocabulary, input-step, input-dataset,
filter. Numeric bounds (e.g. min_molecular_weight) are usually `string`
params — WDK rejects thousands separators; send `"10000"` not `"10,000"`.

## Semantics the sheet encodes

- `required` = NOT allowEmptyValue. `default` = initialDisplayValue (a real
  default, but not a promise the value is still valid — the count will tell).
- Hidden params (`isVisible: false`) are presentation-only: STILL required,
  STILL validated. The sheet omits them; encode_params submits their defaults.
- Multi-pick values are JSON arrays serialized to a string:
  `"[\"a\",\"b\"]"`. A single-pick given a 2-element array is a 500.
- `input-step` params are ALWAYS submitted as "" — the actual input step is
  wired via the strategy's stepTree, never via parameters.
- `input-dataset` params need an uploaded dataset (out of scope v1); searches
  requiring one will fail with WDK's own message.

## Vocabularies

- Flat vocab: rows of [term, display, parent]. Term is what you submit.
- Tree vocab (displayType treeBox): nodes {data: {term, display}, children}.
  The synthetic root term `@@fake@@` is never a value.
- `countOnlyLeaves: true` + a PARENT term submitted directly = WDK silently
  selects NOTHING (0 rows). encode_params expands parents to their leaf
  descendants, mirroring the website's checkbox tree.
- Dependent vocabularies: a param listing others in `dependentParams` controls
  their vocabulary. Read the dependent's options only under bound parents —
  `param-options` uses parent defaults and says so in `context_note`; pass
  `--context parent=value` to change. After changing a parent value, re-read
  the dependent's options; previously valid values may be gone.
- Huge vocabularies (>200) are shortlisted in the sheet with a note; use
  `param-options SEARCH PARAM --query <keyword>` to find exact terms.
```

- [ ] **Step 5: Write `references/strategies.md`**

```markdown
# Strategies, steps, and the spec format

## WDK model (upstream truth)

- A STEP = searchName + searchConfig{parameters}. Step kind is determined by
  how many input-step params its search declares: 0 = leaf, 1 = transform,
  2 = combine (boolean).
- A STRATEGY = name + stepTree. Tree nodes carry ONLY {stepId, primaryInput?,
  secondaryInput?}. Parameters live on steps; wiring lives in the tree.
- A step outside a strategy cannot be run; deleting a step inside one is a
  409. This CLI always creates steps and immediately places them in a
  strategy.
- Boolean searches are per record type, named `boolean_question_*` (e.g.
  boolean_question_TranscriptRecordClasses_TranscriptRecordClass for
  transcript). Operand params bq_left_op*/bq_right_op* are input-step (sent
  ""); bq_operator ∈ UNION, INTERSECT, MINUS (left minus right), RMINUS,
  LONLY, RONLY.

## The create-strategy --spec format

    {"leaf":      {"search": "GenesByMolecularWeight",
                   "params": {"organism": ["Plasmodium falciparum 3D7"],
                              "min_molecular_weight": "100000"}}}
    {"combine":   {"operator": "INTERSECT", "left": <node>, "right": <node>}}
    {"transform": {"search": "GenesByOrthologs", "params": {...},
                   "input": <node>}}

Params omitted or null take the search's defaults (they're in the sheet's
params_template — disclose applied defaults to the user). Steps are created
bottom-up; the strategy is created last with the assembled stepTree; each
create is single-attempt (no retry-duplication).

## Structure semantics (from pathfinder's FRAME rules)

- Alternative evidence for the same property → UNION those searches.
- Distinct required properties → INTERSECT.
- A property with multiple evidence sources gets its OWN nested branch:
  A ∩ (B ∪ C) is not (A ∩ B) ∪ C.
- Few, broad criteria beat many narrow ones — ANDing many filters returns 0.
- Any search with an input-step param MUST be a transform node; standalone it
  makes WDK reject the whole strategy.

## Reading results

- Counts: displayViewTotalCount (genes) → viewTotalCount → displayTotalCount →
  totalCount (transcripts) — first present wins; all absent = "unmeasured",
  NEVER zero. estimatedSize -1 or absent likewise means unmeasured.
- The returned `url` opens the strategy on the website — always hand it to the
  user.
- Record ids are composite: gene_source_id + source_id + project_id.
```

- [ ] **Step 6: Write `references/gotchas.md`**

```markdown
# Silent-failure modes (WDK accepts your request; the science is wrong)

Each of these was learned the hard way in pathfinder and is machine-checked
there (docs/knowledge/wdk/rules). The CLI guards the starred ones.

1. ★ Tree parent submitted directly under countOnlyLeaves → 0 rows, no error.
   Guard: encode_params expands parents to leaves.
2. ★ Guest tokens: uncredentialed requests mint a fresh guest per request —
   results belong to nobody and /users paths 401. Guard: whoami / user_id()
   refuse guests.
3. ★ Duplicate Authorization cookie pairs: Tomcat honors the first. Guard: the
   client sends exactly one.
4. ★ Retrying a committed create after a proxy 502 duplicates objects. Guard:
   creates are single-attempt.
5. ★ estimatedSize/count 0 vs absent vs -1: absent/-1 means "nobody measured",
   not "empty". Guard: shaping reports "unmeasured", never fabricates 0.
6. ★ input-step params given real values are rejected or mis-wired. Guard:
   always "".
7. Hidden params are still validated (isVisible is presentation-only) — they
   are auto-submitted with defaults; if a hidden default is invalid the WDK
   422 names it.
8. Multi-pick enumeration: one representative value ≠ the covered set. List
   every value you mean. A vocabulary + free-text pair covering the same
   concept is ORed by the search — pass "N/A" to the half you don't use (the
   sheet default usually does this).
9. initialDisplayValue is not a promise: a default may be stale; a 0 count
   with defaults means check the params, not the biology.
10. `isValid: true` at validation level NONE means "nobody checked", not
    "valid". Only the level the response names was checked.
11. Single-pick param + JSON array value = HTTP 500 (not 422). Send a scalar.
12. Number-ish params reject thousands separators ("10,000" → 422).
13. One-sided ranges are invalid; supply both bounds (defaults cover the
    other side if you only care about one).
14. A count of 0 after AND-ing many criteria usually means over-narrowing —
    prefer few broad criteria, verify each leaf's count > 0 before combining
    (use `count` per leaf; they're anonymous and parallelizable).
```

- [ ] **Step 7: Polish TESTS.md**

Confirm every `<fill>` placeholder from Tasks 2–9 now holds an observed value; add this intro paragraph if missing: "Gold standards captured live on 2026-08-27. Counts drift with VEuPathDB data releases (~4/year): a `range` failure within ~20% of gold means re-capture, not code bug. Any other failure is a regression."

- [ ] **Step 8: Full suite + line-count checks**

Run: `uv run --with pytest --with httpx python -m pytest tests -q` — Expected: all pass.
Run: `wc -l veupathdb-wdk-strategies/SKILL.md veupathdb-wdk-strategies/references/*.md` — SKILL.md ≤ 200.
Run: `uv run scripts/wdk.py --help` — all 15 subcommands listed.
Run: `git -C . status --short` — confirm `.env` never appears.

- [ ] **Step 9: Commit**

```bash
git add veupathdb-wdk-strategies
git commit -m "docs: SKILL.md, reference docs, TESTS.md gold-standard registry"
```

---

## Final acceptance (whole plan)

- [ ] `uv run --with pytest --with httpx python -m pytest tests -q` fully green with the real token.
- [ ] End-to-end manual run of the SKILL.md workflow on **vectorbase**: catalog → inspect → count → create-strategy (two-leaf INTERSECT) → results → delete-strategy --yes. Paste the strategy URL into TESTS.md as E2E-1 before deleting.
- [ ] `list-strategies` on plasmodb and vectorbase shows no leftover `__skill_test__` strategies.
- [ ] No file contains the token: `git grep -I "$(head -c 12 <<<"$VEUPATHDB_BEARER_TOKEN")"` returns nothing (run with token loaded; checks the prefix only).
