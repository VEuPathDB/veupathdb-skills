import json


def test_live_count_mw_pfalciparum(live_client):
    from _shaping import encode_params, extract_count, get_search_detail, run_report

    detail = get_search_detail(live_client, "transcript", "GenesByMolecularWeight")
    wire = encode_params(detail, {"organism": ["Plasmodium falciparum 3D7"]})
    resp = run_report(live_client, "transcript", "GenesByMolecularWeight", wire)
    count, field = extract_count(resp["meta"])
    assert field == "displayViewTotalCount"
    assert 1800 <= count <= 3000  # gold 2365 on 2026-08-27; ±~20% for data drift


def test_live_preview_records(live_client):
    from _shaping import encode_params, get_search_detail, run_report, shape_records

    detail = get_search_detail(live_client, "transcript", "GenesByMolecularWeight")
    wire = encode_params(detail, {"organism": ["Plasmodium falciparum 3D7"]})
    resp = run_report(
        live_client, "transcript", "GenesByMolecularWeight", wire, num_records=3
    )
    shaped = shape_records(resp)
    assert len(shaped["records"]) == 3
    assert "gene_source_id" in shaped["records"][0]["id"]


def test_live_count_vectorbase(token):
    from _client import Client
    from _shaping import encode_params, extract_count, get_search_detail, run_report

    c = Client("vectorbase", token=token)
    detail = get_search_detail(c, "transcript", "GenesByMolecularWeight")
    wire = encode_params(detail, {"organism": ["Anopheles gambiae PEST"]})
    resp = run_report(c, "transcript", "GenesByMolecularWeight", wire)
    count, _ = extract_count(resp["meta"])
    assert 5400 <= count <= 8100  # gold 6755 on 2026-08-27; ±20%


def test_live_count_dependent_params(token):
    from _client import Client
    from _shaping import (
        encode_params,
        extract_count,
        get_search_detail_for_params,
        run_report,
    )

    c = Client("vectorbase", token=token)
    search_name = (
        "GenesByMicroarrayagamPEST_microarrayExpression_GSE8822_bloodmeal_response_RSRC"
    )
    user_params = {
        "profileset_generic": "bloodmeal_time_series",
        "samples_fc_ref_generic": ["non-blood-fed"],
        "samples_fc_comp_generic": ["blood-fed 3h"],
    }
    detail = get_search_detail_for_params(c, "transcript", search_name, user_params)
    wire = encode_params(detail, user_params)
    resp = run_report(c, "transcript", search_name, wire, num_records=1)
    count, field = extract_count(resp["meta"])
    assert field == "displayViewTotalCount"
    assert 1400 <= count <= 2200  # 1753 on 2026-09-10

