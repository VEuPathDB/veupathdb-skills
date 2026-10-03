import pytest

MW = "GenesByMolecularWeight"


@pytest.fixture
def live_step(live_client):
    """A real step inside a real strategy (WDK refuses to run orphan steps)."""
    from _client import fetch_catalog
    from _strategy import build_strategy

    spec = {
        "leaf": {
            "search": MW,
            "params": {"organism": ["Plasmodium falciparum 3D7"]},
        }
    }
    out = build_strategy(
        live_client, fetch_catalog(live_client), spec, "__skill_test__: results"
    )
    yield out["root_step_id"]
    uid = live_client.user_id()
    try:
        live_client.delete(f"/users/{uid}/strategies/{out['strategy_id']}")
    except Exception:
        pass


def test_live_step_records(live_client, live_step):
    from _shaping import shape_records

    uid = live_client.user_id()
    resp = live_client.post(
        f"/users/{uid}/steps/{live_step}/reports/standard",
        {"reportConfig": {"pagination": {"offset": 0, "numRecords": 2}}},
    )
    shaped = shape_records(resp)
    assert len(shaped["records"]) == 2
    assert "gene_source_id" in shaped["records"][0]["id"]


def test_live_download_url(live_client, live_step):
    resp = live_client.post(
        "/temporary-results",
        {
            "stepId": live_step,
            "reportName": "attributesTabular",
            "reportConfig": {
                "attributes": ["primary_key"],
                "includeHeader": True,
                "attachmentType": "plain",
            },
        },
        idempotent=False,
    )
    assert resp.get("id"), f"unexpected temporary-results response: {resp!r}"


def test_live_step_records_with_default_attributes(live_client, live_step):
    from _shaping import get_search_detail, shape_records

    uid = live_client.user_id()
    step = live_client.get(f"/users/{uid}/steps/{live_step}")
    rt = step.get("recordClassName")
    search_name = step.get("searchName")
    detail = get_search_detail(live_client, rt, search_name)
    da = detail.get("defaultAttributes")
    assert da is not None
    assert "primary_key" in da
    assert "gene_product" in da

    resp = live_client.post(
        f"/users/{uid}/steps/{live_step}/reports/standard",
        {"reportConfig": {"pagination": {"offset": 0, "numRecords": 2}, "attributes": da}},
    )
    shaped = shape_records(resp)
    assert len(shaped["records"]) == 2
    assert "gene_product" in shaped["records"][0]["attributes"]
    assert "primary_key" in shaped["records"][0]["attributes"]

