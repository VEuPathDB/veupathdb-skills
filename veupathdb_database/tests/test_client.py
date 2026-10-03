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
    assert seen["auth_header"] == "Bearer tok-x"


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


def test_load_token_env_then_config(tmp_path, monkeypatch):
    from _client import delete_token, load_token, save_token

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("VEUPATHDB_BEARER_TOKEN", "from-env")
    assert load_token() == "from-env"

    monkeypatch.delenv("VEUPATHDB_BEARER_TOKEN")
    assert load_token() is None

    p = save_token("from-config-file")
    assert p == tmp_path / "veupathdb" / "token"
    assert p.is_file()
    assert (p.stat().st_mode & 0o777) == 0o600
    assert load_token() == "from-config-file"

    assert delete_token() is True
    assert load_token() is None
    assert delete_token() is False


def test_verify_token_valid(monkeypatch):
    from _client import Client, verify_token

    def handler(request):
        assert request.url.path.endswith("/users/current")
        assert "Authorization=test-token" in request.headers.get("cookie", "")
        return httpx.Response(200, json={"id": 12345, "email": "test@uni.edu", "isGuest": False})

    real_init = Client.__init__

    def mock_init(self, site_id, token=None, transport=None, backoff=0):
        real_init(self, site_id, token=token, transport=httpx.MockTransport(handler), backoff=0)

    monkeypatch.setattr(Client, "__init__", mock_init)

    user = verify_token("plasmodb", "test-token")
    assert user["id"] == 12345
    assert user["email"] == "test@uni.edu"


def test_verify_token_guest_refused(monkeypatch):
    from _client import Client, GuestTokenError, verify_token

    def handler(request):
        return httpx.Response(200, json={"id": 999, "isGuest": True})

    real_init = Client.__init__

    def mock_init(self, site_id, token=None, transport=None, backoff=0):
        real_init(self, site_id, token=token, transport=httpx.MockTransport(handler), backoff=0)

    monkeypatch.setattr(Client, "__init__", mock_init)

    with pytest.raises(GuestTokenError):
        verify_token("plasmodb", "guest-token")


def test_cli_detect_site(capsys):
    import wdk

    p = wdk.build_parser()
    args = p.parse_args(["detect-site", "Toxoplasma gondii kinase"])
    args.func(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["site"] == "toxodb"
    assert data["project"] == "ToxoDB"
    assert "profile#serviceAccess" in data["profile_url"]
    assert "registration" in data["registration_url"]


def test_cli_whoami_unauthenticated(tmp_path, monkeypatch, capsys):
    import wdk

    monkeypatch.delenv("VEUPATHDB_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    p = wdk.build_parser()
    args = p.parse_args(["whoami", "toxodb"])
    with pytest.raises(SystemExit) as exc:
        args.func(args)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "not logged in. VEuPathDB authentication is required." in err
    assert "uv run scripts/wdk.py login toxodb" in err
    assert "https://toxodb.org/toxo/app/user/profile#serviceAccess" in err
    assert "https://toxodb.org/toxo/app/user/registration" in err


def test_cli_login_token_and_logout(tmp_path, monkeypatch, capsys):
    import wdk

    monkeypatch.delenv("VEUPATHDB_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(
        "_client.verify_token",
        lambda site_id, tok: {"id": 1234, "email": "alice@test.org", "isGuest": False},
    )

    p = wdk.build_parser()
    args = p.parse_args(["login", "plasmodb", "--token", "my-secret-key"])
    args.func(args)
    out = capsys.readouterr().out
    assert "Authenticated: alice@test.org" in out
    token_file = tmp_path / "veupathdb" / "token"
    assert token_file.is_file()
    assert token_file.read_text().strip() == "my-secret-key"
    assert (token_file.stat().st_mode & 0o777) == 0o600

    args_logout = p.parse_args(["logout"])
    args_logout.func(args_logout)
    out_logout = capsys.readouterr().out
    assert "Logged out" in out_logout
    assert not token_file.exists()


def test_cli_login_token_from_stdin(tmp_path, monkeypatch, capsys):
    import io
    import sys
    import wdk

    monkeypatch.delenv("VEUPATHDB_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(
        "_client.verify_token",
        lambda site_id, tok: {"id": 1234, "email": "alice@test.org", "isGuest": False},
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("stdin-token-val\n"))

    p = wdk.build_parser()
    args = p.parse_args(["login", "plasmodb", "--token", "-"])
    args.func(args)
    out = capsys.readouterr().out
    assert "Authenticated: alice@test.org" in out
    token_file = tmp_path / "veupathdb" / "token"
    assert token_file.is_file()
    assert token_file.read_text().strip() == "stdin-token-val"


def test_cli_login_token_from_file(tmp_path, monkeypatch, capsys):
    import wdk

    monkeypatch.delenv("VEUPATHDB_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(
        "_client.verify_token",
        lambda site_id, tok: {"id": 1234, "email": "alice@test.org", "isGuest": False},
    )

    key_file = tmp_path / "plasmodb-key"
    key_file.write_text("file-secret-token\n")

    p = wdk.build_parser()
    args = p.parse_args(["login", "plasmodb", "--token-file", str(key_file)])
    args.func(args)
    out = capsys.readouterr().out
    assert "Authenticated: alice@test.org" in out
    token_file = tmp_path / "veupathdb" / "token"
    assert token_file.is_file()
    assert token_file.read_text().strip() == "file-secret-token"
    assert (token_file.stat().st_mode & 0o777) == 0o600


def test_cli_login_token_from_file_at_syntax(tmp_path, monkeypatch, capsys):
    import wdk

    monkeypatch.delenv("VEUPATHDB_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(
        "_client.verify_token",
        lambda site_id, tok: {"id": 1234, "email": "alice@test.org", "isGuest": False},
    )

    key_file = tmp_path / "plasmodb-key"
    key_file.write_text("at-file-secret-token\n")

    p = wdk.build_parser()
    args = p.parse_args(["login", "plasmodb", "--token", f"@{key_file}"])
    args.func(args)
    out = capsys.readouterr().out
    assert "Authenticated: alice@test.org" in out
    token_file = tmp_path / "veupathdb" / "token"
    assert token_file.is_file()
    assert token_file.read_text().strip() == "at-file-secret-token"




def test_live_whoami(live_client):
    me = live_client.get("/users/current")
    assert me["isGuest"] is False
    assert isinstance(me["id"], int)


@pytest.mark.parametrize("site", ["plasmodb", "vectorbase", "toxodb"])
def test_live_whoami_all_test_sites(site, token):
    from _client import Client

    me = Client(site, token=token).get("/users/current")
    assert me["isGuest"] is False


def test_create_id_dataset_unit(monkeypatch):
    from _client import Client

    c = Client("vectorbase", token="dummy-token")
    captured = {}

    def mock_post(path, body):
        captured["path"] = path
        captured["body"] = body
        return {"id": 12345678}

    monkeypatch.setattr(c, "post", mock_post)

    ds_id = c.create_id_dataset([" AGAP001234 ", "AGAP001235"])
    assert ds_id == 12345678
    assert captured["path"] == "/users/current/datasets"
    assert captured["body"] == {
        "sourceType": "idList",
        "sourceContent": {"ids": ["AGAP001234", "AGAP001235"]},
    }

    with pytest.raises(ValueError):
        c.create_id_dataset([])


def test_live_create_id_dataset(live_client):
    ds_id = live_client.create_id_dataset(["AGAP001234"])
    assert isinstance(ds_id, int)
    assert ds_id > 0







