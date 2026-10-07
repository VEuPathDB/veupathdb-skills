import json

import httpx
import pytest
from eda_helpers import eda_fixture

TEMP = {"comparator": {"variableId": "VAR_081ab087"}, "groupA": [{"label": "normal"}], "groupB": [{"label": "febrile"}]}


@pytest.fixture
def contrast_file(tmp_path):
    def make(obj=TEMP):
        path = tmp_path / "contrast.json"
        path.write_text(json.dumps(obj))
        return str(path)

    return make


def test_de_text_report(run_eda, eda_mock, contrast_file):
    out = run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file())
    assert f"contrast {eda_mock.de_job}" in out
    assert "groupA (reference) normal n=6 → groupB febrile n=6" in out
    assert "the WDK step returns" in out
    assert "eda.py de-spec plasmodb DS_e973eadd57 --contrast" in out and "--save" in out
    assert "params.json" not in out
    starts = [(q, b) for m, p, q, b in eda_mock.requests if p == "/computes/differentialexpression"]
    assert starts[-1] == ({"autostart": "true"}, eda_fixture("jobs.json")["de_heatshock"]["body"])
    assert any(p.endswith("/volcanoplot") for m, p, q, b in eda_mock.requests)


def test_de_json_counts_and_first_row_quirk(run_eda, eda_mock, contrast_file):
    out = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--json", "--thresholds", "0,1"))
    counts = out["context"]["counts"]
    assert counts["tested"] == len(eda_fixture("volcano_heatshock.json")["statistics"])
    assert counts["wdk_step_genes"] == counts["passing_raw_p"] - 1  # row 0 passes at (0, 1)
    assert out["provenance"]["jobId"] == eda_mock.de_job
    assert out["provenance"]["studyId"] == "STUDY_e973eadd57"
    assert out["context"]["groupA"] == {"labels": ["normal"], "n": 6, "role": "reference"}
    assert out["context"]["thresholds"]["pValueType"].startswith("raw")
    assert "wdkDroppedRow" in out["context"]


def test_de_genes_and_tsv(run_eda, contrast_file, tmp_path):
    first = eda_fixture("volcano_heatshock.json")["statistics"][0]["pointID"]
    tsv = tmp_path / "de.tsv"
    out = run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(),
                  "--genes", f"{first},PF3D7_NOPE", "--tsv", str(tsv))
    assert f"{first}: tested" in out
    assert "PF3D7_NOPE: not tested" in out
    lines = tsv.read_text().splitlines()
    assert lines[0] == "gene\teffectSize\tpValue\tadjustedPValue"
    assert len(lines) == 1 + len(eda_fixture("volcano_heatshock.json")["statistics"])


def test_de_tsv_unwritable_fails_before_any_job(run_eda, eda_mock, contrast_file, tmp_path, capsys):
    for bad in (tmp_path / "no-such-dir" / "de.tsv", tmp_path):
        with pytest.raises(SystemExit):
            run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--tsv", str(bad))
        err = capsys.readouterr().err
        assert err.startswith("error: --tsv") and "Traceback" not in err
    assert not any(p.startswith("/computes/") for m, p, q, b in eda_mock.requests)


def test_de_tsv_write_failure_after_job_is_clean(run_eda, contrast_file, tmp_path, capsys, monkeypatch):
    import pathlib

    real = pathlib.Path.write_text

    def boom(self, *a, **k):
        if self.name == "de.tsv":
            raise PermissionError(13, "Permission denied", str(self))
        return real(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "write_text", boom)
    with pytest.raises(SystemExit):
        run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--tsv", str(tmp_path / "de.tsv"))
    err = capsys.readouterr().err
    assert err.startswith("error: --tsv") and "Permission denied" in err


def test_de_no_wait_does_not_fetch_statistics(run_eda, eda_mock, contrast_file):
    out = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--no-wait"))
    assert out["jobId"] == eda_mock.de_job and out["status"] == "complete"
    assert not any(p.endswith("/volcanoplot") for m, p, q, b in eda_mock.requests)


def test_de_failed_job_and_retry(run_eda, eda_mock, contrast_file, capsys):
    calls = {"n": 0}

    def compute(request):
        if request.url.params.get("autostart") == "false":  # de's status lookup
            return httpx.Response(200, json={"jobID": eda_mock.de_job, "status": "failed"})
        calls["n"] += 1
        status = "failed" if calls["n"] == 1 else "complete"
        return httpx.Response(200, json={"jobID": eda_mock.de_job, "status": status})

    eda_mock.routes[("POST", "/computes/differentialexpression")] = compute
    eda_mock.routes[("DELETE", f"/jobs/{eda_mock.de_job}")] = lambda r: httpx.Response(204)
    with pytest.raises(SystemExit):
        run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file())
    err = capsys.readouterr().err
    assert "failed" in err and "--retry" in err
    calls["n"] = 0
    out = run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--retry")
    assert f"contrast {eda_mock.de_job}" in out
    assert ("DELETE", f"/jobs/{eda_mock.de_job}") in [(m, p) for m, p, q, b in eda_mock.requests]


def test_de_refuses_too_few_replicates(run_eda, contrast_file, capsys):
    obj = {
        "comparator": {"variableId": "VAR_64c65374"},
        "groupA": [{"label": "WT 37C"}],
        "groupB": [{"label": "WT 41C"}],
        "filters": [{"entityId": "ENT_8151325d", "variableId": "VAR_081ab087", "type": "stringSet", "stringSet": ["normal"]}],
    }
    with pytest.raises(SystemExit):
        run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(obj))
    assert "too few replicates" in capsys.readouterr().err


def test_de_inline_contrast_equals_file(run_eda, eda_mock, contrast_file):
    a = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--json"))
    b = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", json.dumps(TEMP), "--json"))
    c = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", "@" + contrast_file(), "--json"))
    assert a == b == c


def test_de_bad_inline_contrast(run_eda, capsys):
    with pytest.raises(SystemExit):
        run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", '{"comparator": ')
    assert "inline JSON is not valid" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", "nope.json")
    assert "file not found" in capsys.readouterr().err


def test_de_bad_contrast_number(run_eda, capsys):
    with pytest.raises(SystemExit):
        run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", "999")
    assert "no such candidate" in capsys.readouterr().err


def test_de_method_override_is_noted(run_eda, contrast_file):
    out = run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--method", "limma")
    assert "separate job" in out and "limma on" in out


def _mirror_routes(eda_mock):
    """normal→febrile has never run (but would start fine); febrile→normal is cached."""
    def compute(request):
        body = json.loads(request.content)
        if body["config"]["comparator"]["groupA"] == [{"label": "normal"}]:
            status = "no-such-job" if request.url.params.get("autostart") == "false" else "complete"
            return httpx.Response(200, json={"jobID": "a" * 32, "status": status})
        return httpx.Response(200, json={"jobID": "b" * 32, "status": "complete"})

    eda_mock.routes[("POST", "/computes/differentialexpression")] = compute


def test_de_reuses_cached_mirror_with_negated_effects(run_eda, eda_mock, contrast_file, tmp_path):
    _mirror_routes(eda_mock)
    tsv = tmp_path / "de.tsv"
    out = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--json", "--tsv", str(tsv)))
    assert out["provenance"]["jobId"] == "a" * 32
    assert out["provenance"]["statisticsFrom"] == {"jobId": "b" * 32, "negated": True}
    assert any("mirror" in n and "WDK step" in n for n in out["context"]["notes"])
    assert any("--no-mirror" in n and "1e-3" in n for n in out["context"]["notes"])
    computes = [q for m, p, q, b in eda_mock.requests if p == "/computes/differentialexpression"]
    assert computes and all(q == {"autostart": "false"} for q in computes)  # nothing started
    vol = [b for m, p, q, b in eda_mock.requests if p.endswith("/volcanoplot")]
    assert vol[-1]["computeConfig"]["comparator"]["groupA"] == [{"label": "febrile"}]
    first = eda_fixture("volcano_heatshock.json")["statistics"][0]
    gene, es = tsv.read_text().splitlines()[1].split("\t")[:2]
    assert gene == first["pointID"] and float(es) == -float(first["effectSize"])


def test_de_no_mirror_runs_its_own_job(run_eda, eda_mock, contrast_file):
    _mirror_routes(eda_mock)
    out = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", contrast_file(), "--json", "--no-mirror"))
    assert out["provenance"]["jobId"] == "a" * 32 and out["provenance"]["statisticsFrom"] is None
    bodies = eda_mock.compute_bodies("differentialexpression")
    assert all(b["config"]["comparator"]["groupA"] == [{"label": "normal"}] for b in bodies)
