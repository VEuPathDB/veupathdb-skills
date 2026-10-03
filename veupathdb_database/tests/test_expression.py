import pytest

from _client import Client, load_token
from _shaping import shape_expression_data


@pytest.fixture(scope="module")
def token():
    tok = load_token()
    if not tok:
        pytest.skip("VEUPATHDB_BEARER_TOKEN not set")
    return tok


def _mock_record():
    return {
        "id": "AGAP009221",
        "attributes": {
            "primary_key": "AGAP009221",
            "name": "SRPN5",
            "product": "serine protease inhibitor 5",
            "organism": "<i>A. gambiae PEST</i>",
        },
        "tables": {
            "ExpressionGraphs": [
                {
                    "dataset_id": "DS_ATLAS",
                    "display_name": "Tissue Atlas of Adult Mosquito",
                    "summary": "Expression in various adult tissues.",
                    "assay_type": "array",
                    "y_axis": "RMA",
                    "short_attribution": "Baker et al.",
                },
                {
                    "dataset_id": "DS_BLOOD",
                    "display_name": "Response to Bloodmeal in Whole Body",
                    "summary": "Blood feeding time course.",
                    "assay_type": "RNA-Seq",
                    "y_axis": "TPM",
                    "short_attribution": "Marinotti et al.",
                },
            ],
            "ExpressionGraphsDataTable": [
                {
                    "dataset_id": "DS_ATLAS",
                    "sample_name": "carcass: male",
                    "value": "9.23",
                    "percentile_channel1": "97.10",
                    "standard_error": "0.03",
                },
                {
                    "dataset_id": "DS_ATLAS",
                    "sample_name": "salivary gland: male",
                    "value": "7.34",
                    "percentile_channel1": "92.50",
                    "standard_error": "0.71",
                },
                {
                    "dataset_id": "DS_ATLAS",
                    "sample_name": "midgut: female",
                    "value": "3.49",
                    "percentile_channel1": "44.99",
                    "standard_error": "0.09",
                },
                {
                    "dataset_id": "DS_BLOOD",
                    "sample_name": "whole body: non-fed",
                    "value": "47.01",
                    "percentile_channel1": "82.69",
                    "standard_error": "2.99",
                },
                {
                    "dataset_id": "DS_BLOOD",
                    "sample_name": "whole body: 3h post blood meal",
                    "value": "40.15",
                    "percentile_channel1": "78.38",
                    "standard_error": "2.79",
                },
            ],
        },
    }


def test_shape_expression_bare_summary_offline():
    res = shape_expression_data(_mock_record(), site="vectorbase")
    assert res["gene"] == "AGAP009221"
    assert res["organism"] == "A. gambiae PEST"  # HTML stripped
    assert res["total_datasets"] == 2
    assert res["matching_datasets"] == 2
    assert "note" in res
    # Samples omitted in bare summary
    for d in res["datasets"]:
        assert "samples" not in d
        assert d["sample_count"] > 0
        assert d["max_percentile"] is not None
        assert "top_sample" in d


def test_shape_expression_dataset_id_drilldown_offline():
    res = shape_expression_data(_mock_record(), site="vectorbase", dataset_id="DS_ATLAS")
    assert res["matching_datasets"] == 1
    ds = res["datasets"][0]
    assert ds["dataset_id"] == "DS_ATLAS"
    assert len(ds["samples"]) == 3
    # Sorted by percentile descending
    assert ds["samples"][0]["sample_name"] == "carcass: male"
    assert ds["samples"][0]["percentile"] == 97.10
    assert ds["samples"][1]["sample_name"] == "salivary gland: male"
    assert ds["samples"][2]["sample_name"] == "midgut: female"


def test_shape_expression_filter_metadata_offline():
    res = shape_expression_data(_mock_record(), site="vectorbase", filter_query="blood")
    assert res["matching_datasets"] == 1
    ds = res["datasets"][0]
    assert ds["dataset_id"] == "DS_BLOOD"
    assert len(ds["samples"]) == 2


def test_shape_expression_filter_sample_name_narrowing_offline():
    # "salivary" only appears in sample_name of DS_ATLAS, not in its title/summary
    res = shape_expression_data(_mock_record(), site="vectorbase", filter_query="salivary")
    assert res["matching_datasets"] == 1
    ds = res["datasets"][0]
    assert ds["dataset_id"] == "DS_ATLAS"
    # Samples narrowed specifically to salivary
    assert len(ds["samples"]) == 1
    assert ds["samples"][0]["sample_name"] == "salivary gland: male"


def test_shape_expression_min_percentile_offline():
    res = shape_expression_data(
        _mock_record(), site="vectorbase", dataset_id="DS_ATLAS", min_percentile=90.0
    )
    ds = res["datasets"][0]
    assert len(ds["samples"]) == 2
    assert all(s["percentile"] >= 90.0 for s in ds["samples"])


def test_shape_expression_empty_datasets_offline():
    empty_record = {
        "id": "XYZ123",
        "attributes": {"primary_key": "XYZ123", "name": "UNK"},
        "tables": {"ExpressionGraphs": [], "ExpressionGraphsDataTable": []},
    }
    res = shape_expression_data(empty_record, site="vectorbase", omics_type="expression")
    assert res["total_datasets"] == 0
    assert res["matching_datasets"] == 0
    assert "message" in res


def test_live_expression_vectorbase_summary(token):
    from _sites import project_id

    c = Client("vectorbase", token=token)
    payload = {
        "primaryKey": [
            {"name": "source_id", "value": "AGAP009221"},
            {"name": "project_id", "value": project_id("vectorbase")},
        ],
        "attributes": ["primary_key", "name", "product", "organism"],
        "tables": ["ExpressionGraphs", "ExpressionGraphsDataTable"],
    }
    raw = c.post("/record-types/gene/records", payload, idempotent=True)
    res = shape_expression_data(raw, site="vectorbase")
    assert res["gene"] == "AGAP009221"
    assert res["name"] == "SRPN5"
    assert res["total_datasets"] >= 30
    assert "A. gambiae" in res["organism"]


def test_live_expression_vectorbase_filter(token):
    from _sites import project_id

    c = Client("vectorbase", token=token)
    payload = {
        "primaryKey": [
            {"name": "source_id", "value": "AGAP009221"},
            {"name": "project_id", "value": project_id("vectorbase")},
        ],
        "attributes": ["primary_key", "name", "product", "organism"],
        "tables": ["ExpressionGraphs", "ExpressionGraphsDataTable"],
    }
    raw = c.post("/record-types/gene/records", payload, idempotent=True)
    res = shape_expression_data(raw, site="vectorbase", filter_query="body")
    assert res["matching_datasets"] >= 1
    assert any("samples" in d for d in res["datasets"])


def test_shape_expression_max_datasets_offline():
    res = shape_expression_data(_mock_record(), site="vectorbase", max_datasets=1)
    assert res["matching_datasets"] == 2
    assert len(res["datasets"]) == 1
    assert "Showing top 1 of 2 datasets" in res["note"]

    # all_datasets overrides max_datasets
    res_all = shape_expression_data(
        _mock_record(), site="vectorbase", max_datasets=1, all_datasets=True
    )
    assert len(res_all["datasets"]) == 2

