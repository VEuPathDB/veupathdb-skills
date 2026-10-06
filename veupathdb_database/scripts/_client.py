"""WDK transport. Auth is a COOKIE (Authorization=<token>), exactly one pair."""
import difflib
import json
import os
import pathlib
import tempfile
import time

import httpx

from _sites import SITES, service_url

CACHE_DIR = pathlib.Path.home() / ".cache" / "veupathdb-wdk"
CACHE_TTL_S = 7 * 24 * 3600
EDA_CACHE_DIR = CACHE_DIR / "eda"
EDA_TIMEOUT_S = 120


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


def config_dir() -> pathlib.Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = pathlib.Path(xdg) if xdg else (pathlib.Path.home() / ".config")
    return base / "veupathdb"


def token_path() -> pathlib.Path:
    return config_dir() / "token"


def save_token(token: str) -> pathlib.Path:
    tok = token.strip()
    if not tok:
        raise ValueError("Cannot save empty token")
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    p = token_path()
    p.write_text(tok + "\n", encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return p


def delete_token() -> bool:
    p = token_path()
    if p.is_file():
        p.unlink()
        return True
    return False


def load_token(root=None) -> str | None:
    tok = os.environ.get("VEUPATHDB_BEARER_TOKEN")
    if tok:
        return tok.strip()
    p = token_path()
    if p.is_file():
        try:
            val = p.read_text(encoding="utf-8").strip()
            if val:
                return val
        except OSError:
            pass
    return None


def verify_token(site_id: str, token: str) -> dict:
    """Verify that a token belongs to a registered VEuPathDB user.

    Returns the user dict from /users/current.
    Raises GuestTokenError or WDKError on failure.
    """
    tok = token.strip()
    if not tok:
        raise ValueError("Token cannot be empty")
    c = Client(site_id, token=tok)
    user = c.get("/users/current")
    if not isinstance(user, dict):
        raise WDKError(f"Unexpected response from /users/current: {user}", endpoint="/users/current")
    if user.get("isGuest"):
        raise GuestTokenError(
            "Token identifies a GUEST user; register at the site to obtain a registered-user token.",
            endpoint="/users/current",
        )
    return user


def _is_delayed(body):
    return isinstance(body, dict) and body.get("message") == "WDK-DELAYED-RESULT"


class Client:
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
                    "no token: run 'wdk.py login' or set VEUPATHDB_BEARER_TOKEN. "
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

    def create_id_dataset(self, ids: list[str]) -> int:
        """Upload a list of IDs as a temporary user dataset.

        Returns the integer dataset ID assigned by WDK.
        """
        clean_ids = [str(i).strip() for i in ids if str(i).strip()]
        if not clean_ids:
            raise ValueError("Cannot create ID dataset from empty list of IDs")
        payload = {
            "sourceType": "idList",
            "sourceContent": {"ids": clean_ids},
        }
        res = self.post("/users/current/datasets", body=payload)
        return int(res["id"])


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


DEFAULT_EXCLUDED_PARAM_PREFIXES = ("eda_",)


def get_excluded_param_prefixes() -> tuple[str, ...]:
    env_val = os.environ.get("WDK_EXCLUDED_PARAM_PREFIXES")
    if env_val is not None:
        if not env_val.strip():
            return ()
        return tuple(p.strip() for p in env_val.split(",") if p.strip())
    return DEFAULT_EXCLUDED_PARAM_PREFIXES


def filter_catalog_searches(catalog: dict, excluded_prefixes: tuple[str, ...] | None = None) -> dict:
    """Return catalog with searches filtered out if any param matches an excluded prefix."""
    if excluded_prefixes is None:
        excluded_prefixes = get_excluded_param_prefixes()
    if not excluded_prefixes:
        return catalog

    filtered_searches = {}
    for rt, searches in catalog.get("searches", {}).items():
        filtered_searches[rt] = [
            s
            for s in searches
            if not any(
                isinstance(p, str)
                and any(p.startswith(prefix) for prefix in excluded_prefixes)
                for p in s.get("paramNames", [])
            )
        ]
    return {
        **catalog,
        "searches": filtered_searches,
    }


def fetch_catalog(client, refresh=False, excluded_param_prefixes=None):
    """Record types + compact search listings. Disk-cached 7 days per site.
    Filters out searches with excluded_param_prefixes (default: ('eda_',)).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{client.site_id}.json"
    if (
        not refresh
        and cache.is_file()
        and time.time() - cache.stat().st_mtime < CACHE_TTL_S
    ):
        raw_catalog = json.loads(cache.read_text())
    else:
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
        raw_catalog = {
            "cached_at": time.time(),
            "record_types": record_types,
            "searches": searches,
        }
        cache.write_text(json.dumps(raw_catalog))

    return filter_catalog_searches(raw_catalog, excluded_prefixes=excluded_param_prefixes)


def fetch_record_type(client, record_type, refresh=False):
    """Fetch expanded record-type definition. Disk-cached 7 days per site/rt."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{client.site_id}_rt_{record_type}.json"
    if (
        not refresh
        and cache.is_file()
        and time.time() - cache.stat().st_mtime < CACHE_TTL_S
    ):
        return json.loads(cache.read_text())
    try:
        raw = client.get(f"/record-types/{record_type}", params={"format": "expanded"})
    except WDKError as err:
        try:
            all_rts = client.get("/record-types")
        except Exception:
            all_rts = []
        hint = difflib.get_close_matches(record_type, all_rts, n=3, cutoff=0.5)
        if hint:
            raise WDKError(
                f"unknown record type '{record_type}'; did you mean {hint}? Valid: {sorted(all_rts)}",
                status=404,
                endpoint=f"/record-types/{record_type}",
            ) from None
        raise err
    cache.write_text(json.dumps(raw))
    return raw
