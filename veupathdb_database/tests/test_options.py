import json
import pathlib

FX = pathlib.Path(__file__).parent / "fixtures"


def _go():
    return json.loads((FX / "go.json").read_text())


def test_unknown_param_returns_did_you_mean():
    from _shaping import param_options

    out = param_options(_go(), "go_typahead")
    assert out["error"] == "unknown parameter"
    assert "go_typeahead" in out["did_you_mean"]
    assert "organism" in out["valid"]


def test_flat_vocab_query_filter():
    from _shaping import param_options

    out = param_options(_go(), "go_typeahead", query="kinase")
    assert 0 < out["shown"] <= 200
    assert out["total"] > 5000
    assert all("kinase" in o["display"].lower() for o in out["options"][:10])


def test_tree_vocab_options_have_leaf_flag():
    from _shaping import param_options

    out = param_options(_go(), "organism", query="falciparum")
    assert any(o["leaf"] for o in out["options"])
    assert all("falciparum" in o["term"].lower() for o in out["options"])


def test_live_dependent_context_note(live_client):
    from _client import fetch_catalog
    from _shaping import get_search_detail, param_options

    detail = get_search_detail(live_client, "transcript", "GenesByGoTerm")
    parents = [
        p["name"]
        for p in detail["parameters"]
        if "go_typeahead" in p.get("dependentParams", [])
    ]
    assert parents == ["go_term_slim"]
    refreshed = get_search_detail(
        live_client, "transcript", "GenesByGoTerm", context={"go_term_slim": "No"}
    )
    out = param_options(refreshed, "go_typeahead", query="kinase")
    assert out["shown"] > 0
