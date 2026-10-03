import json


def test_strip_html():
    from _shaping import strip_html

    assert (
        strip_html("Find genes <br><br> with  <i>weight</i>\n in a range")
        == "Find genes with weight in a range"
    )


def test_catalog_lines_shape_and_boolean_filter():
    from _shaping import catalog_lines

    cat = {
        "record_types": ["transcript"],
        "searches": {
            "transcript": [
                {
                    "name": "GenesByTaxon",
                    "displayName": "Taxonomy",
                    "description": "<b>Find</b> genes " + "x" * 400,
                    "paramNames": ["organism"],
                    "outputRecordClassName": "transcript",
                },
                {
                    "name": "boolean_question_X",
                    "displayName": "bool",
                    "description": "",
                    "paramNames": [],
                    "outputRecordClassName": "transcript",
                },
            ]
        },
    }
    lines = catalog_lines(cat)
    assert len(lines) == 1
    rt, name, disp, desc = lines[0].split("\t")
    assert (rt, name, disp) == ("transcript", "GenesByTaxon", "Taxonomy")
    assert len(desc) <= 250 and desc.startswith("Find genes")


def test_live_catalog_plasmodb(live_client):
    from _client import fetch_catalog
    from _shaping import all_search_names, catalog_lines

    cat = fetch_catalog(live_client)
    assert "transcript" in cat["record_types"]
    names = all_search_names(cat)
    assert names.get("GenesByGoTerm") == "transcript"
    assert names.get("GenesByMolecularWeight") == "transcript"
    assert len(catalog_lines(cat)) > 400  # 515 searches incl. non-gene types, minus booleans

    # second call must come from disk cache (no HTTP): break the token
    from _client import Client

    broken = Client("plasmodb", token="invalid")
    cached = fetch_catalog(broken)
    assert cached["record_types"] == cat["record_types"]


def test_filter_catalog_searches_offline():
    from _client import filter_catalog_searches

    mock_cat = {
        "record_types": ["transcript"],
        "searches": {
            "transcript": [
                {"name": "EdaSearch", "paramNames": ["eda_dataset", "eda_output"]},
                {"name": "MixedSearch", "paramNames": ["organism", "eda_analysis_spec"]},
                {"name": "SuffixOnly", "paramNames": ["my_eda_param"]},
                {"name": "CleanSearch", "paramNames": ["organism", "min_mw"]},
            ]
        },
    }

    # Default filters out "eda_"
    filtered = filter_catalog_searches(mock_cat, excluded_prefixes=("eda_",))
    names = [s["name"] for s in filtered["searches"]["transcript"]]
    assert names == ["SuffixOnly", "CleanSearch"]

    # Empty excluded_prefixes keeps all
    kept = filter_catalog_searches(mock_cat, excluded_prefixes=())
    assert len(kept["searches"]["transcript"]) == 4

    # Custom prefix
    custom = filter_catalog_searches(mock_cat, excluded_prefixes=("my_",))
    custom_names = [s["name"] for s in custom["searches"]["transcript"]]
    assert custom_names == ["EdaSearch", "MixedSearch", "CleanSearch"]


def test_live_catalog_excludes_eda_searches(token):
    from _client import Client, fetch_catalog

    c = Client("vectorbase", token=token)
    cat_filtered = fetch_catalog(c)
    transcript_searches = cat_filtered["searches"]["transcript"]
    # No search should have an eda_ param
    assert not any(
        any(p.startswith("eda_") for p in s.get("paramNames", []))
        for s in transcript_searches
    )

    # When excluded_param_prefixes=(), eda_ searches are present
    cat_raw = fetch_catalog(c, excluded_param_prefixes=())
    raw_transcript_searches = cat_raw["searches"]["transcript"]
    assert len(raw_transcript_searches) > len(transcript_searches) + 100
    assert any(
        any(p.startswith("eda_") for p in s.get("paramNames", []))
        for s in raw_transcript_searches
    )
