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
