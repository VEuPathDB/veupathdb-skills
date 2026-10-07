import pathlib
import sys

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
