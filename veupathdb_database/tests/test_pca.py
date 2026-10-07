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


def test_render_pca_outliers_not_scored():
    from _pca import parse_scores, parse_variance, pca_report, render_pca
    from _samples import ancestors, build_sample_table, index_entities, variable_meta

    index = index_entities(eda_fixture("study_heatshock.json")["rootEntity"])
    meta = variable_meta(index, ancestors(index, "ENT_fd574cd6"))
    table = build_sample_table(lambda e, ids: eda_fixture("tabular_heatshock_sample.json"), index, "ENT_fd574cd6", meta)
    pcs, scores = parse_scores(eda_fixture("pca_heatshock_tabular.tsv"))
    eight = dict(list(scores.items())[:8])
    rep = pca_report(pcs, eight, parse_variance(eda_fixture("pca_heatshock_meta.json")), table["rows"], meta)
    rep.update(datasetId="DS_e973eadd57", valueVariable="SEQUENCE_READ_COUNT_SENSE", dataFormat="rawCounts", jobId="j", notes=[])
    line = next(l for l in render_pca(rep) if l.startswith("outliers"))
    assert line.startswith("outliers: not scored (too few samples") and "n=8" in line and line.endswith(")")


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
