import copy
import json

import pytest

DE_CFG = {
    "identifierVariable": {"entityId": "G", "variableId": "VEUPATHDB_GENE_ID"},
    "valueVariable": {"entityId": "G", "variableId": "SEQUENCE_READ_COUNT"},
    "comparator": {"variable": {"entityId": "S", "variableId": "V"}, "groupA": [{"label": "a"}], "groupB": [{"label": "b"}]},
    "differentialExpressionMethod": "DESeq",
    "pValueFloor": "1e-200",
}
PCA_CFG = {"identifierVariable": DE_CFG["identifierVariable"], "valueVariable": DE_CFG["valueVariable"], "dataFormat": "rawCounts"}


def _spec():
    from _de import build_spec

    return build_spec("DS_x", "Study: b vs a", [], DE_CFG, PCA_CFG, (1.0, 0.05, "upAndDown"))


def test_build_spec_shape():
    from _de import find_volcano_computation, validate_spec

    spec = _spec()
    assert spec["studyId"] == "DS_x" and spec["isPublic"] is False
    assert spec["descriptor"]["subset"] == {"descriptor": [], "uiSettings": {}}
    assert [c["computationId"] for c in spec["descriptor"]["computations"]] == ["pca_1", "de_1"]
    comp = find_volcano_computation(spec["descriptor"]["computations"])
    assert comp["computationId"] == "de_1" and comp["descriptor"]["configuration"] == DE_CFG
    viz = comp["visualizations"][0]["descriptor"]
    assert viz == {"type": "volcanoplot", "configuration": {"effectSizeThreshold": 1.0, "significanceThreshold": 0.05, "effectDirection": "upAndDown"}}
    for key in ("starredVariables", "derivedVariables"):
        assert spec["descriptor"][key] == []
    assert spec["descriptor"]["dataTableConfig"] == {}
    validate_spec(spec, "DS_x")


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda s: s.update(studyId="STUDY_x"), "DS_"),
        (lambda s: s["descriptor"]["computations"].pop(), "volcanoplot"),
        (lambda s: s["descriptor"]["computations"][1]["visualizations"][0]["descriptor"]["configuration"].pop("significanceThreshold"), "volcanoplot"),
        (lambda s: s["descriptor"]["computations"][1]["visualizations"].insert(0, {"visualizationId": "x", "descriptor": {"type": "scatterplot", "configuration": {}}}), "first visualization"),
        (lambda s: s["descriptor"]["computations"][1]["descriptor"]["configuration"]["comparator"].update(groupB=[]), "groupB"),
        (lambda s: s["descriptor"]["computations"][1]["descriptor"]["configuration"]["valueVariable"].update(entityId="OTHER"), "same entity"),
        (lambda s: s["descriptor"]["computations"][1]["descriptor"]["configuration"].update(differentialExpressionMethod="edgeR"), "differentialExpressionMethod"),
    ],
)
def test_validate_spec_rejects(mutate, needle):
    from _de import SpecError, validate_spec

    spec = copy.deepcopy(_spec())
    mutate(spec)
    with pytest.raises(SpecError) as e:
        validate_spec(spec, "DS_x")
    assert needle in str(e.value)


def test_wdk_params_round_trip():
    from _de import wdk_params

    spec = _spec()
    params = wdk_params(spec)
    assert params["eda_dataset_id"] == "DS_x"
    assert isinstance(params["eda_analysis_spec"], str) and '": ' not in params["eda_analysis_spec"]  # compact
    assert json.loads(params["eda_analysis_spec"]) == spec


def test_de_spec_cli_matches_de_body(run_eda, eda_mock, tmp_path):
    contrast = tmp_path / "c.json"
    contrast.write_text(json.dumps({"comparator": {"variableId": "VAR_081ab087"}, "groupA": [{"label": "normal"}], "groupB": [{"label": "febrile"}]}))
    run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", str(contrast))
    de_body = eda_mock.compute_bodies("differentialexpression")[-1]
    spec = json.loads(run_eda("de-spec", "plasmodb", "DS_e973eadd57", "--contrast", str(contrast), "--thresholds", "2,0.01,upOnly"))
    de_1 = spec["descriptor"]["computations"][1]
    assert de_1["descriptor"]["configuration"] == de_body["config"]
    assert de_1["visualizations"][0]["descriptor"]["configuration"] == {"effectSizeThreshold": 2.0, "significanceThreshold": 0.01, "effectDirection": "upOnly"}
    assert spec["studyId"] == "DS_e973eadd57"
    assert spec["descriptor"]["computations"][0]["descriptor"]["configuration"]["dataFormat"] == "rawCounts"
    params = json.loads(run_eda("de-spec", "plasmodb", "DS_e973eadd57", "--contrast", str(contrast), "--format", "params"))
    assert params["eda_dataset_id"] == "DS_e973eadd57"
    assert eda_mock.de_job in run_eda.err


TEMP = {"comparator": {"variableId": "VAR_081ab087"}, "groupA": [{"label": "normal"}], "groupB": [{"label": "febrile"}]}


def test_de_spec_save_is_content_addressed(run_eda, eda_cache, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # nothing may be written to the working directory
    args = ("de-spec", "plasmodb", "DS_e973eadd57", "--contrast", json.dumps(TEMP), "--save")
    a = json.loads(run_eda(*args))
    b = json.loads(run_eda(*args))
    c = json.loads(run_eda(*args, "--thresholds", "2,0.01"))
    assert a == b and a["paramsFile"] != c["paramsFile"]
    path = a["paramsFile"]
    assert path.startswith(str((eda_cache / "params").resolve())) and path.endswith(".json")
    # resolve_target_arg does not look the search up yet (Task 13 adds the positive case)
    assert a["leaf"]["params"] == "@" + path and a["leaf"]["search"] is None
    assert "search" in a["note"]
    stdout_params = json.loads(run_eda("de-spec", "plasmodb", "DS_e973eadd57", "--contrast", json.dumps(TEMP), "--format", "params"))
    assert json.loads(open(path, encoding="utf-8").read()) == stdout_params
    assert not [f for f in tmp_path.iterdir() if f.is_file()]  # the working directory stays clean


def test_stash_json_is_atomic_parallel_and_pruned(eda_cache):
    import os
    import time
    from concurrent.futures import ThreadPoolExecutor

    import _client

    stale = eda_cache / "params" / "0123456789abcdef.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")
    old = time.time() - _client.CACHE_TTL_S - 60
    os.utime(stale, (old, old))
    payloads = [{"n": i} for i in range(20)] * 2  # every payload written twice, concurrently
    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(lambda d: _client.stash_json("params", d), payloads))
    assert len(set(paths)) == 20
    for d, p in zip(payloads, paths):
        assert json.loads(p.read_text()) == d
    names = sorted(f.name for f in (eda_cache / "params").iterdir())
    assert len(names) == 20 and all(n.endswith(".json") for n in names)  # no temp leftovers
    assert not stale.exists()
