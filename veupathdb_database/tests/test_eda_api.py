import json

import httpx
import pytest


def _client(handler):
    from _client import eda_client

    return eda_client(
        "plasmodb", token="tok-x", transport=httpx.MockTransport(handler), backoff=0
    )


PERMS = {
    "perDataset": {
        "DS_aaa": {
            "studyId": "STUDY_aaa",
            "displayName": "A study",
            "shortDisplayName": "A",
            "description": "<b>Heat</b> shock   study",
        }
    }
}


def test_resolve_dataset_maps_ds_to_study(eda_cache):
    from _eda import resolve_dataset

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        assert request.url.path == "/eda/permissions"
        return httpx.Response(200, json=PERMS)

    c = _client(handler)
    ds = resolve_dataset(c, "DS_aaa")
    assert ds == {
        "datasetId": "DS_aaa",
        "studyId": "STUDY_aaa",
        "displayName": "A study",
        "shortDisplayName": "A",
        "description": "Heat shock study",
    }
    resolve_dataset(c, "DS_aaa")
    assert calls["n"] == 1  # second call served from the disk cache


def test_resolve_dataset_refetches_once_before_failing(eda_cache):
    from _eda import EdaError, resolve_dataset

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=PERMS)

    c = _client(handler)
    resolve_dataset(c, "DS_aaa")  # warms the cache
    with pytest.raises(EdaError) as e:
        resolve_dataset(c, "DS_aab")
    assert calls["n"] == 2  # one fresh fetch before giving up
    msg = str(e.value)
    assert "not visible" in msg and "whoami" in msg and "DS_aaa" in msg


def test_tabular_and_count_always_send_filters():
    from _eda import entity_count, tabular

    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        if request.url.path.endswith("/count"):
            return httpx.Response(200, json={"count": 3})
        return httpx.Response(200, json=[["s_id", "VAR_x"], ["s1", "a"]])

    c = _client(handler)
    assert entity_count(c, "STUDY_aaa", "ENT_s", []) == 3
    assert tabular(c, "STUDY_aaa", "ENT_s", ["VAR_x"], []) == [["s_id", "VAR_x"], ["s1", "a"]]
    assert seen == [
        {"filters": []},
        {"filters": [], "outputVariableIds": ["VAR_x"]},
    ]


def test_tabular_parses_tsv_when_server_ignores_accept():
    from _eda import tabular

    def handler(request):
        return httpx.Response(200, text="s_id\tVAR_x\ns1\ta\n", headers={"content-type": "text/plain"})

    assert tabular(_client(handler), "STUDY_aaa", "ENT_s", ["VAR_x"], []) == [
        ["s_id", "VAR_x"],
        ["s1", "a"],
    ]


def test_compute_status_autostart_flag():
    from _eda import compute_status

    seen = []

    def handler(request):
        seen.append((request.url.path, request.url.params.get("autostart")))
        return httpx.Response(200, json={"jobID": "j1", "status": "no-such-job"})

    c = _client(handler)
    compute_status(c, "differentialexpression", {"studyId": "STUDY_aaa"}, start=False)
    compute_status(c, "differentialexpression", {"studyId": "STUDY_aaa"}, start=True)
    assert seen == [
        ("/eda/computes/differentialexpression", "false"),
        ("/eda/computes/differentialexpression", "true"),
    ]


def test_wait_for_job_polls_until_complete():
    from _eda import wait_for_job

    statuses = iter(["queued", "in-progress", "complete"])

    def handler(request):
        return httpx.Response(200, json={"jobID": "j1", "status": next(statuses)})

    slept, logged = [], []
    st = wait_for_job(
        _client(handler), "differentialexpression", {}, sleep=slept.append, log=logged.append
    )
    assert st["status"] == "complete"
    assert slept == [2.0, 3.0]
    assert any("queued" in m for m in logged)


def test_wait_for_job_times_out_with_job_id():
    from _eda import EdaError, wait_for_job

    def handler(request):
        return httpx.Response(200, json={"jobID": "j1", "status": "in-progress"})

    with pytest.raises(EdaError) as e:
        wait_for_job(_client(handler), "differentialexpression", {}, timeout_s=4, sleep=lambda s: None)
    assert "j1" in str(e.value)


def test_wait_for_job_returns_failed_status():
    from _eda import wait_for_job

    def handler(request):
        return httpx.Response(200, json={"jobID": "j1", "status": "failed"})

    assert wait_for_job(_client(handler), "differentialexpression", {})["status"] == "failed"


def test_volcano_body_matches_plugin():
    from _eda import volcano

    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"statistics": []})

    body = {"studyId": "STUDY_aaa", "filters": [], "config": {"k": 1}, "derivedVariables": []}
    volcano(_client(handler), body)
    assert seen["path"] == "/eda/apps/differentialexpression/visualizations/volcanoplot"
    assert seen["body"] == {
        "studyId": "STUDY_aaa",
        "filters": [],
        "computeConfig": {"k": 1},
        "config": {},
    }


def test_compute_file_sends_accept_any():
    from _eda import compute_file

    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["accept"] = request.headers.get("accept")
        return httpx.Response(200, text="x\tPC1\n", headers={"content-type": "text/plain"})

    out = compute_file(_client(handler), "dimensionalityreduction", {}, "tabular")
    assert out == "x\tPC1\n"
    assert seen == {"path": "/eda/computes/dimensionalityreduction/tabular", "accept": "*/*"}
