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
    assert cat["searches"]["transcript"]
    assert json.loads((wdk_cache / "plasmodb.json").read_text())["schema"] == 2


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


@pytest.fixture
def bad_json_files(tmp_path):
    """A directory, a non-UTF-8 file and (unless running as root) an unreadable file."""
    import os

    d = tmp_path / "adir"
    d.mkdir()
    latin = tmp_path / "latin1.json"
    latin.write_bytes(b'{"a": "caf\xe9"}')
    out = {"directory": d, "not UTF-8": latin}
    if os.geteuid() != 0:
        locked = tmp_path / "locked.json"
        locked.write_text("{}")
        locked.chmod(0)
        out["unreadable"] = locked
    return out


def test_at_file_errors_are_clean(bad_json_files, capsys):
    import wdk
    from _eda import EdaError
    from _strategy import SpecError, resolve_params
    from eda import json_arg

    for kind, path in bad_json_files.items():
        with pytest.raises(SpecError) as e:
            resolve_params(f"@{path}")
        assert str(path) in str(e.value), kind
        with pytest.raises(SystemExit):
            wdk._load_params(f"@{path}")
        err = capsys.readouterr().err
        assert err.startswith("error: --params") and str(path) in err, kind
        with pytest.raises(EdaError) as e:
            json_arg(f"@{path}", "--contrast", "a contrast file")
        assert "--contrast" in str(e.value) and str(path) in str(e.value), kind
