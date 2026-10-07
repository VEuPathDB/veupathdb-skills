"""Live gold tests for eda.py on plasmodb. They skip without a token; see TESTS.md EDA-*."""
import json

import pytest

HS = "DS_e973eadd57"
HS_SEARCH = "GenesByRNASeqpfal3D7_Pfal3D7_Febrile_temps_RNASeq_ebi_rnaSeq_RSRCDESeq"
AB = "DS_24d441b301"
GOLD_JOB = "db04204e5386396e1ca2cb78469ab6fb"
TEMP = {"comparator": {"variableId": "VAR_081ab087"}, "groupA": [{"label": "normal"}], "groupB": [{"label": "febrile"}]}
# A contrast nobody is likely to have run: the strong job-identity check needs it fresh.
RARE = {
    "comparator": {"variableId": "VAR_84f17484"},
    "groupA": [{"label": "delta-DHC mutant"}],
    "groupB": [{"label": "delta-LRR5 mutant"}],
    "filters": [{"entityId": "ENT_8151325d", "variableId": "VAR_081ab087", "type": "stringSet", "stringSet": ["normal"]}],
}


@pytest.fixture
def live_eda(token, capsys):
    import eda as eda_cli

    def run(*argv):
        eda_cli.main(list(argv))
        return capsys.readouterr().out

    return run


@pytest.fixture
def contrast_path(tmp_path):
    def make(obj):
        p = tmp_path / f"c{abs(hash(json.dumps(obj)))}.json"
        p.write_text(json.dumps(obj))
        return str(p)

    return make


def _wdk_count(token, params):
    from _client import Client
    from _shaping import encode_params, extract_count, get_search_detail, run_report

    c = Client("plasmodb", token=token)
    wire = encode_params(get_search_detail(c, "transcript", HS_SEARCH), params, client=c)
    return extract_count(run_report(c, "transcript", HS_SEARCH, wire)["meta"])


def test_live_contrasts_heatshock(live_eda):
    out = json.loads(live_eda("contrasts", "plasmodb", HS, "--json"))
    temp = next(c for c in out["candidates"] if c["comparator"]["variableId"] == "VAR_081ab087" and c["stratum"] is None)
    assert temp["index"] == 1
    assert (temp["groupA"], temp["groupB"], temp["nA"], temp["nB"]) == ([{"label": "normal"}], [{"label": "febrile"}], 6, 6)
    assert temp["cache"] == {"status": "complete", "jobId": GOLD_JOB}


def test_live_de_heatshock_gold(live_eda, contrast_path):
    out = json.loads(live_eda("de", "plasmodb", HS, "--contrast", contrast_path(TEMP), "--json"))
    assert out["provenance"]["jobId"] == GOLD_JOB
    counts = out["context"]["counts"]
    assert 1543 * 0.8 <= counts["passing_raw_p"] <= 1543 * 1.2
    assert counts["wdk_step_genes"] in (counts["passing_raw_p"], counts["passing_raw_p"] - 1)


@pytest.mark.parametrize("thresholds", ["1,0.05", "0,1"])
def test_live_wdk_count_matches_de(live_eda, contrast_path, token, thresholds):
    path = contrast_path(TEMP)
    de = json.loads(live_eda("de", "plasmodb", HS, "--contrast", path, "--thresholds", thresholds, "--json"))
    params = json.loads(live_eda("de-spec", "plasmodb", HS, "--contrast", path, "--thresholds", thresholds, "--format", "params"))
    count, field = _wdk_count(token, params)
    assert field in ("displayViewTotalCount", "displayTotalCount")  # genes, not transcripts
    assert count == de["context"]["counts"]["wdk_step_genes"]


def test_live_create_strategy_from_de_spec(live_eda, token):
    from _client import Client, fetch_catalog
    from _strategy import build_strategy

    saved = json.loads(live_eda("de-spec", "plasmodb", HS, "--contrast", json.dumps(TEMP), "--save"))
    assert saved["leaf"]["search"] == HS_SEARCH
    c = Client("plasmodb", token=token)
    out = build_strategy(c, fetch_catalog(c), {"leaf": saved["leaf"]}, "__skill_test__: eda de step")
    try:
        assert out["steps"][0]["valid"] is True
        size = out["estimated_size"]
        assert size == "unmeasured" or size > 1000
    finally:
        c.delete(f"/users/{c.user_id()}/strategies/{out['strategy_id']}")


def test_live_wdk_step_drives_the_same_job(live_eda, contrast_path, token):
    """Strong job-identity check: a never-computed contrast is started by the WDK
    step itself, and EDA then reports our body's job as existing."""
    import eda as eda_cli
    from _client import WDKError
    from _contrasts import PLUGIN_DE
    from _eda import compute_status

    path = contrast_path(RARE)
    argv = ["de-spec", "plasmodb", HS, "--contrast", path, "--value-var", "SEQUENCE_READ_COUNT_ANTISENSE"]
    p = eda_cli.prepare_de(eda_cli.build_parser().parse_args(argv))
    before = compute_status(p["t"]["client"], PLUGIN_DE, p["body"], start=False)
    if before["status"] != "no-such-job":
        pytest.skip(f"RARE contrast already computed ({before['status']}, job {before['jobID']}): "
                    "edit RARE to a fresh contrast to repeat the strong check")
    params = json.loads(live_eda(*argv, "--format", "params"))
    try:
        _wdk_count(token, params)  # the WSF plugin starts the job and answers 202
    except WDKError:  # 202, no JSON body: the job is started
        pass
    after = compute_status(p["t"]["client"], PLUGIN_DE, p["body"], start=False)
    assert after["jobID"] == before["jobID"]
    assert after["status"] in ("queued", "in-progress", "complete")


def test_live_mirror_job_has_negated_effects(live_eda, contrast_path):
    """The basis of mirror reuse: swapping groups negates effectSize and leaves p and
    padj unchanged, row for row. Runs the febrile-reference job once (about 2 min);
    later runs hit the cache."""
    import eda as eda_cli
    from _de import java_double
    from _eda import volcano, wait_for_job
    from _contrasts import PLUGIN_DE

    argv = ["de", "plasmodb", HS, "--contrast", contrast_path(TEMP)]
    p = eda_cli.prepare_de(eda_cli.build_parser().parse_args(argv))
    c, mbody = p["t"]["client"], eda_cli.mirror_body(p)
    assert wait_for_job(c, PLUGIN_DE, mbody, timeout_s=1800)["status"] == "complete"
    fwd, rev = volcano(c, p["body"])["statistics"], volcano(c, mbody)["statistics"]
    assert [s["pointID"] for s in fwd] == [s["pointID"] for s in rev]  # same row order: WDK row-0 drop agrees
    # observed max deviations: effectSize 7.4e-4 rel / 2.9e-5 abs; p and padj 3.6e-5 rel (DESeq2 fitting is iterative)
    for f, r in zip(fwd, rev):
        for key, sign in (("effectSize", -1), ("pValue", 1), ("adjustedPValue", 1)):
            a, b = java_double(f.get(key)), java_double(r.get(key))
            assert (a is None) == (b is None), (f["pointID"], key)
            if a is not None:
                assert b == pytest.approx(sign * a, rel=1e-3, abs=1e-4), (f["pointID"], key)


def test_live_de_datasets_plasmodb(live_eda):
    rows = json.loads(live_eda("de-datasets", "plasmodb", "--json"))
    by_ds = {r["datasetId"]: r for r in rows}
    assert by_ds[HS]["search"] == HS_SEARCH and by_ds[HS]["method"] == "DESeq"
    assert by_ds[AB]["method"] == "limma"
    assert len(rows) >= 30


def test_live_limma_antibody(live_eda):
    out = json.loads(live_eda("contrasts", "plasmodb", AB, "--json"))
    assert out["method"] == "limma" and out["valueVariable"] == "NORMALIZED_INTENSITY"
    assert out["candidates"], out["skipped"]
    cand = next((c for c in out["candidates"] if c["cache"]["status"] == "complete"), out["candidates"][0])
    de = json.loads(live_eda("de", "plasmodb", AB, "--contrast", str(cand["index"]), "--json", "--timeout", "1800"))
    assert de["context"]["method"] == "limma"
    assert de["context"]["counts"]["tested"] > 0


def test_live_pca_heatshock(live_eda):
    rep = json.loads(live_eda("pca", "plasmodb", HS, "--json"))
    assert rep["jobId"] == "2679abb0e5c81b345a21b8f211db6a9b"
    assert [p["variance"] for p in rep["pcs"]] == pytest.approx([54.35, 12.79], abs=0.05)
    temp = next(e for e in rep["tracks"]["PC1"] if e["variableId"] == "VAR_081ab087")
    assert temp["eta2"] == pytest.approx(0.7751, abs=0.05)
    assert rep["outliers"]["samples"] == []
