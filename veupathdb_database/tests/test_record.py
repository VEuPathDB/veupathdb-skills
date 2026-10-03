import pytest

from _client import Client, load_token
from _sites import project_id


@pytest.fixture(scope="module")
def token():
    tok = load_token()
    if not tok:
        pytest.skip("VEUPATHDB_BEARER_TOKEN not set")
    return tok


def test_live_fetch_gene_record_vectorbase(token):
    c = Client("vectorbase", token=token)
    payload = {
        "primaryKey": [
            {"name": "source_id", "value": "AGAP001212"},
            {"name": "project_id", "value": project_id("vectorbase")},
        ],
        "attributes": ["primary_key", "name", "product", "exon_count"],
        "tables": ["GeneTranscripts"],
    }
    data = c.post("/record-types/gene/records", payload, idempotent=True)
    assert data["attributes"]["name"] == "PGRPLB"
    assert data["attributes"]["exon_count"] == "3"
    transcripts = data["tables"]["GeneTranscripts"]
    assert len(transcripts) >= 1
    assert transcripts[0]["exon_count"] == "3"
    assert transcripts[0]["transcript_id"] == "AGAP001212-RA"


def test_live_fetch_gene_record_plasmodb(token):
    c = Client("plasmodb", token=token)
    payload = {
        "primaryKey": [
            {"name": "source_id", "value": "PF3D7_0100200"},
            {"name": "project_id", "value": project_id("plasmodb")},
        ],
        "attributes": ["primary_key", "name", "product", "exon_count"],
        "tables": ["GeneTranscripts"],
    }
    data = c.post("/record-types/gene/records", payload, idempotent=True)
    assert data["attributes"]["primary_key"] == "PF3D7_0100200"
    assert data["attributes"]["exon_count"] == "2"


def test_live_fetch_transcript_record(token):
    c = Client("vectorbase", token=token)
    payload = {
        "primaryKey": [
            {"name": "gene_source_id", "value": "AGAP001212"},
            {"name": "source_id", "value": "AGAP001212-RA"},
            {"name": "project_id", "value": project_id("vectorbase")},
        ],
        "attributes": ["primary_key", "exon_count"],
        "tables": [],
    }
    data = c.post("/record-types/transcript/records", payload, idempotent=True)
    assert data["attributes"]["exon_count"] == "3"


def test_live_inspect_record_type_gene_vectorbase(token):
    from _client import fetch_record_type
    from _shaping import shape_record_type

    c = Client("vectorbase", token=token)
    raw = fetch_record_type(c, "gene")
    shaped = shape_record_type(raw, query="exon")
    assert shaped["record_type"] == "gene"
    assert shaped["primary_key"] == ["source_id", "project_id"]
    assert any(a["name"] == "exon_count" for a in shaped["attributes"])
    assert any(t["name"] == "GeneTranscripts" for t in shaped["tables"])


def test_live_inspect_record_type_transcript_vectorbase(token):
    from _client import fetch_record_type
    from _shaping import shape_record_type

    c = Client("vectorbase", token=token)
    raw = fetch_record_type(c, "transcript")
    shaped = shape_record_type(raw, query="exon")
    assert shaped["record_type"] == "transcript"
    assert shaped["primary_key"] == ["gene_source_id", "source_id", "project_id"]
    assert shaped["matching_attributes"] >= 1
    assert any(a["name"] == "exon_count" for a in shaped["attributes"])


def test_live_fetch_record_filter_tables(token):
    from _shaping import shape_record

    c = Client("vectorbase", token=token)
    payload = {
        "primaryKey": [
            {"name": "source_id", "value": "AGAP006348"},
            {"name": "project_id", "value": project_id("vectorbase")},
        ],
        "attributes": ["primary_key", "name"],
        "tables": ["Orthologs"],
    }
    raw = c.post("/record-types/gene/records", payload, idempotent=True)
    shaped = shape_record(raw, filter_query="albimanus")
    rows = shaped["tables"]["Orthologs"]
    assert len(rows) == 2
    for r in rows:
        assert "albimanus" in r["organism"].lower()
        assert "clustalInput" not in r
        assert "sort_key" not in r
    assert shaped["attributes"]["name"] == "LRIM1"


def test_live_fetch_record_filter_attributes(token):
    from _shaping import shape_record

    c = Client("vectorbase", token=token)
    payload = {
        "primaryKey": [
            {"name": "source_id", "value": "AGAP001212"},
            {"name": "project_id", "value": project_id("vectorbase")},
        ],
        "attributes": ["primary_key", "name", "exon_count"],
        "tables": [],
    }
    raw = c.post("/record-types/gene/records", payload, idempotent=True)
    shaped = shape_record(raw, filter_query="exon")
    assert shaped["attributes"] == {"exon_count": "3"}


def test_shape_record_type_name_only_offline():
    from _shaping import shape_record_type

    raw = {
        "name": "transcript",
        "displayName": "Transcript",
        "primaryKeyColumnRefs": ["source_id"],
        "attributes": [
            {"name": "gene_product", "displayName": "Product Description"},
            {"name": "pan_123_ns_456", "displayName": "Male reproductive organs expression"},
            {"name": "organism", "displayName": "Organism"},
        ],
        "tables": [],
    }
    # Without name_only, "product" matches both gene_product and the "reproductive" display name
    shaped_broad = shape_record_type(raw, query="product", name_only=False)
    assert shaped_broad["matching_attributes"] == 2

    # With name_only, "product" matches ONLY gene_product
    shaped_strict = shape_record_type(raw, query="product", name_only=True)
    assert shaped_strict["matching_attributes"] == 1
    assert shaped_strict["attributes"][0]["name"] == "gene_product"
    assert shaped_strict["name_only"] is True


def test_shape_record_type_exclude_offline():
    from _shaping import shape_record_type

    raw = {
        "name": "transcript",
        "displayName": "Transcript",
        "primaryKeyColumnRefs": ["source_id"],
        "attributes": [
            {"name": "primary_key", "displayName": "Gene ID"},
            {"name": "gene_product", "displayName": "Product Description"},
            {"name": "pan_123_ns_456", "displayName": "Sample 123"},
            {"name": "aaeg_expr_graph", "displayName": "Expression Graph"},
        ],
        "tables": [
            {"name": "TableA", "displayName": "Table A", "attributes": []},
            {"name": "pan_table", "displayName": "PAN Table", "attributes": []},
        ],
    }
    # Exclude pan_
    shaped = shape_record_type(raw, exclude="pan_")
    assert shaped["matching_attributes"] == 3
    assert not any("pan_" in a["name"] for a in shaped["attributes"])
    assert len(shaped["tables"]) == 1
    assert shaped["tables"][0]["name"] == "TableA"

    # Exclude multiple patterns: "pan_,_graph"
    shaped_multi = shape_record_type(raw, exclude="pan_,_graph")
    assert shaped_multi["matching_attributes"] == 2
    assert [a["name"] for a in shaped_multi["attributes"]] == ["primary_key", "gene_product"]


def test_live_inspect_record_type_name_only_and_exclude(token):
    from _client import fetch_record_type
    from _shaping import shape_record_type

    c = Client("vectorbase", token=token)
    raw = fetch_record_type(c, "transcript")

    # Name-only filter on "product" excluding "graph"
    shaped = shape_record_type(raw, query="product", name_only=True, exclude="graph")
    names = [a["name"] for a in shaped["attributes"]]
    assert "gene_product" in names
    assert "transcript_product" in names
    assert not any("graph" in n for n in names)
    assert shaped["matching_attributes"] <= 5

    # Exclude pan_ attributes
    shaped_no_pan = shape_record_type(raw, exclude="pan_")
    assert shaped_no_pan["matching_attributes"] < shaped_no_pan["total_attributes"]
    assert not any(a["name"].startswith("pan_") for a in shaped_no_pan["attributes"])

