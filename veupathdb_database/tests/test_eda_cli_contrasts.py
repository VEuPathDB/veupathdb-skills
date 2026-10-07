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


def test_cache_checks_never_start_jobs_and_are_capped(run_eda, eda_mock, monkeypatch):
    import _contrasts
    from _contrasts import PLUGIN_DE, compute_body, de_config, job_id

    monkeypatch.setattr(_contrasts, "MAX_CACHE_CHECKS", 5)
    out = json.loads(run_eda("contrasts", "plasmodb", "DS_e973eadd57", "--json"))
    checks = [q for m, p, q, b in eda_mock.requests if p == "/computes/differentialexpression"]
    assert len(checks) == 5 and all(q == {"autostart": "false"} for q in checks)
    bodies = eda_mock.compute_bodies("differentialexpression")
    beyond = [c for c in out["candidates"] if c["index"] > 5]
    assert beyond
    expr = bodies[0]["config"]["identifierVariable"]["entityId"]
    for c in beyond:
        cfg = de_config(expr, out["valueVariable"], c["comparator"], c["groupA"], c["groupB"], out["method"])
        body = compute_body(eda_mock.STUDY, cfg, c["filters"])
        assert c["cache"]["status"] == "not checked"
        assert len(c["cache"]["jobId"]) == 32
        assert c["cache"]["jobId"] == job_id(PLUGIN_DE, body)


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
