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
