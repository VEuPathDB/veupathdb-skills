def _cat():
    def s(name, disp, desc):
        return {
            "name": name,
            "displayName": disp,
            "description": desc,
            "paramNames": [],
            "outputRecordClassName": "transcript",
        }

    return {
        "record_types": ["transcript"],
        "searches": {
            "transcript": [
                s("GenesByGoTerm", "GO Term", "genes by gene ontology term"),
                s("GenesByTaxon", "Taxonomy", "genes from selected organisms"),
                s("boolean_question_X", "bool", "go term"),
            ]
        },
    }


def test_scoring_ranks_name_hits_first():
    from _shaping import score_searches

    hits = score_searches(_cat(), "go term")
    assert hits[0]["name"] == "GenesByGoTerm"
    assert hits[0]["relevance"] == 1.0
    assert all(h["name"] != "boolean_question_X" for h in hits)


def test_no_hits_is_empty():
    from _shaping import score_searches

    assert score_searches(_cat(), "zzzznothing") == []


def test_live_find(live_client):
    from _client import fetch_catalog
    from _shaping import score_searches

    hits = score_searches(fetch_catalog(live_client), "GO term")
    assert "GenesByGoTerm" in [h["name"] for h in hits[:5]]
