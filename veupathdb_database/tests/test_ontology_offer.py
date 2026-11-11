"""The agent finds only the searches the site's Categories ontology offers.

Ported from the Pathfinder decision (ai-wdk-mcp docs/knowledge/decisions/
the-agent-finds-only-the-searches-the-ontology-offers.md).
"""
import httpx


def node(name, scope=None, target="search"):
    props = {"name": [name], "targetType": [target]}
    if scope is not None:
        props["scope"] = scope
    return {"children": [], "properties": props}


def tree(*nodes):
    return {"tree": {"children": list(nodes), "properties": {}}}


def test_offered_search_names_follow_target_type_and_scope():
    from _client import offered_search_names

    onto = tree(
        node("GeneQuestions.NoScope"),
        node("GeneQuestions.Web", ["webservice"]),
        node("OrganismQuestions.GenomeDataTypes", ["menu"]),
        node("GeneQuestions.Both", ["menu", "webservice"]),
        node("InternalQuestions.Only", ["internal"]),
        node("GeneQuestions.Results", ["results"]),
        node("someAttribute", None, target="attribute"),
    )
    assert offered_search_names(onto) == {
        "GeneQuestions.NoScope",
        "GeneQuestions.Web",
        "OrganismQuestions.GenomeDataTypes",
        "GeneQuestions.Both",
    }


def test_offered_search_names_walks_nested_children():
    from _client import offered_search_names

    inner = node("GeneQuestions.Deep")
    onto = tree({"children": [{"children": [inner], "properties": {}}], "properties": {}})
    assert offered_search_names(onto) == {"GeneQuestions.Deep"}


def _s(name, full, takes_input=False):
    return {
        "name": name,
        "fullName": full,
        "displayName": name,
        "description": "genes " + name,
        "paramNames": [],
        "outputRecordClassName": "transcript",
        "takesInputStep": takes_input,
    }


def _cat(offered):
    return {
        "record_types": ["transcript"],
        "offered_searches": offered,
        "searches": {
            "transcript": [
                _s("GenesByTaxon", "GeneQuestions.GenesByTaxon"),
                _s("AllGenes", "GeneQuestions.AllGenes"),
                _s("TranscriptsFromGenes", "GeneQuestions.TranscriptsFromGenes", True),
            ]
        },
    }


def test_listings_drop_unoffered_but_keep_transforms():
    from _shaping import catalog_lines, score_searches

    cat = _cat(["GeneQuestions.GenesByTaxon"])
    names = [ln.split("\t")[1] for ln in catalog_lines(cat)]
    assert names == ["GenesByTaxon", "TranscriptsFromGenes"]
    hits = [h["name"] for h in score_searches(cat, "genes")]
    assert "AllGenes" not in hits and "GenesByTaxon" in hits and "TranscriptsFromGenes" in hits


def test_empty_ontology_offers_everything():
    from _shaping import catalog_lines

    assert len(catalog_lines(_cat([]))) == 3


def test_reads_by_name_are_not_filtered():
    from _shaping import resolve_search

    rt, _ = resolve_search(_cat(["GeneQuestions.GenesByTaxon"]), "AllGenes")
    assert rt == "transcript"


def test_fetch_catalog_reads_ontology_and_caches_it(tmp_path, monkeypatch):
    import _client

    monkeypatch.setattr(_client, "CACHE_DIR", tmp_path)
    calls = []

    def handler(request):
        calls.append(request.url.path)
        p = request.url.path
        if p.endswith("/record-types"):
            return httpx.Response(200, json=["transcript"])
        if p.endswith("/record-types/transcript/searches"):
            return httpx.Response(200, json=[
                {"urlSegment": "GenesByTaxon", "fullName": "GeneQuestions.GenesByTaxon"},
                {"urlSegment": "AllGenes", "fullName": "GeneQuestions.AllGenes"},
                {"urlSegment": "TranscriptsFromGenes", "fullName": "X.T",
                 "allowedPrimaryInputRecordClassNames": ["transcript"]},
            ])
        if p.endswith("/ontologies/Categories"):
            return httpx.Response(200, json=tree(node("GeneQuestions.GenesByTaxon")))
        return httpx.Response(404, json={})

    c = _client.Client("plasmodb", token="t", transport=httpx.MockTransport(handler), backoff=0)
    cat = _client.fetch_catalog(c)
    assert cat["offered_searches"] == ["GeneQuestions.GenesByTaxon"]
    by = {s["name"]: s for s in cat["searches"]["transcript"]}
    assert by["TranscriptsFromGenes"]["takesInputStep"] is True
    assert by["GenesByTaxon"]["takesInputStep"] is False
    assert len(by) == 3  # the catalog still holds unoffered searches
    n = len(calls)
    _client.fetch_catalog(c)
    assert len(calls) == n  # second call from cache


def test_fetch_catalog_survives_ontology_failure(tmp_path, monkeypatch):
    import _client

    monkeypatch.setattr(_client, "CACHE_DIR", tmp_path)

    def handler(request):
        p = request.url.path
        if p.endswith("/record-types"):
            return httpx.Response(200, json=["transcript"])
        if p.endswith("/searches"):
            return httpx.Response(200, json=[{"urlSegment": "A", "fullName": "Q.A"}])
        return httpx.Response(500, json={})

    c = _client.Client("plasmodb", token="t", transport=httpx.MockTransport(handler), backoff=0)
    assert _client.fetch_catalog(c)["offered_searches"] == []
