import pathlib
import sys

import httpx
import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture(scope="session")
def token():
    from _client import load_token

    tok = load_token()
    if not tok:
        pytest.skip("VEUPATHDB_BEARER_TOKEN not set (env or ~/.config/veupathdb/token)")
    return tok


@pytest.fixture(scope="session")
def live_client(token):
    from _client import Client

    return Client("plasmodb", token=token)


@pytest.fixture
def eda_cache(tmp_path, monkeypatch):
    """Point the EDA disk cache at a temp dir so tests never read ~/.cache."""
    import _client

    path = tmp_path / "eda-cache"
    monkeypatch.setattr(_client, "EDA_CACHE_DIR", path)
    return path


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
