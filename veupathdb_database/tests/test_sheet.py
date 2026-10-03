import json
import pathlib

FX = pathlib.Path(__file__).parent / "fixtures"


def _mw():
    return json.loads((FX / "mw.json").read_text())


def _go():
    return json.loads((FX / "go.json").read_text())


def test_tree_entries_skips_fake_root():
    from _shaping import tree_entries

    organism = next(p for p in _mw()["parameters"] if p["name"] == "organism")
    entries = tree_entries(organism["vocabulary"])
    terms = [e["term"] for e in entries]
    assert "@@fake@@" not in terms
    assert "Plasmodium falciparum 3D7" in terms
    leaf = next(e for e in entries if e["term"] == "Plasmodium falciparum 3D7")
    assert leaf["leaf"] is True


def test_expand_to_leaves_parent_and_leaf_and_unknown():
    from _shaping import expand_to_leaves

    organism = next(p for p in _mw()["parameters"] if p["name"] == "organism")
    tree = organism["vocabulary"]
    leaves, unknown = expand_to_leaves(tree, ["Plasmodium falciparum 3D7"])
    assert leaves == ["Plasmodium falciparum 3D7"] and unknown == []
    leaves, unknown = expand_to_leaves(tree, ["Plasmodium"])
    assert len(leaves) > 5 and all("Plasmodium" in x for x in leaves[:3])
    _, unknown = expand_to_leaves(tree, ["Plasmodium falciparum 3D8"])
    assert unknown == ["Plasmodium falciparum 3D8"]


def test_sheet_mw():
    from _shaping import build_sheet

    sheet = build_sheet(_mw())
    assert sheet["search"] == "GenesByMolecularWeight"
    names = [e["name"] for e in sheet["required"] + sheet["optional"]]
    assert set(names) == {"organism", "min_molecular_weight", "max_molecular_weight"}
    org = next(e for e in sheet["required"] if e["name"] == "organism")
    assert "vocabulary_tree" in org
    assert len(org["vocabulary_tree"]) <= 80
    assert "children" in org["note"]
    assert org["default"] is None
    assert sheet["params_template"]["organism"] is None
    assert sheet["params_template"]["min_molecular_weight"] == "10000"


def test_sheet_shortlists_huge_flat_vocab():
    from _shaping import build_sheet

    sheet = build_sheet(_go(), query="kinase")
    ta = next(
        e for e in sheet["required"] + sheet["optional"] if e["name"] == "go_typeahead"
    )
    assert len(ta["allowed_values"]) <= 200
    assert "values total" in ta["note"]
    assert "param-options" in ta["note"]


def test_sheet_dependencies_name_visible_dependents():
    from _shaping import build_sheet

    deps = build_sheet(_go())["dependencies"]
    assert any("go_term_slim" in d and "go_typeahead" in d for d in deps)


def test_resolve_search_did_you_mean(live_client):
    from _client import fetch_catalog
    from _shaping import resolve_search

    cat = fetch_catalog(live_client)
    rt, _ = resolve_search(cat, "GenesByMolecularWeight")
    assert rt == "transcript"
    rt, sugg = resolve_search(cat, "GenesByMolecularWieght")
    assert rt is None and "GenesByMolecularWeight" in sugg


def test_shape_record_type_offline():
    from _shaping import shape_record_type

    mock_raw = {
        "urlSegment": "gene",
        "displayName": "Gene",
        "primaryKeyColumnRefs": ["source_id", "project_id"],
        "attributes": [
            {"name": "primary_key", "displayName": "Gene ID", "columnDataType": "STRING"},
            {"name": "exon_count", "displayName": "# Exons in Gene", "columnDataType": "NUMBER"},
            {"name": "name", "displayName": "Gene Name", "columnDataType": "STRING"},
        ],
        "tables": [
            {
                "name": "GeneTranscripts",
                "displayName": "Transcripts",
                "attributes": [
                    {"name": "transcript_id"},
                    {"name": "exon_count"},
                ],
            },
            {
                "name": "GeneModelDump",
                "displayName": "Gene Model",
                "attributes": [{"name": "sequence_id"}],
            },
        ],
    }

    # Without query
    shaped = shape_record_type(mock_raw)
    assert shaped["record_type"] == "gene"
    assert shaped["primary_key"] == ["source_id", "project_id"]
    assert len(shaped["attributes"]) == 3
    assert len(shaped["tables"]) == 2
    assert shaped["tables"][0]["columns"] == ["transcript_id", "exon_count"]

    # With query "exon"
    q_shaped = shape_record_type(mock_raw, query="exon")
    assert q_shaped["matching_attributes"] == 1
    assert q_shaped["attributes"][0]["name"] == "exon_count"
    assert q_shaped["matching_tables"] == 1
    assert q_shaped["tables"][0]["name"] == "GeneTranscripts"


def test_shape_record_offline():
    from _shaping import clean_table_row, shape_record

    raw_row = {
        "organism": "Anopheles albimanus STECLA",
        "ortho_gene_source_id": "AALB005865",
        "clustalInput": "<input type=\"checkbox\" name=\"gene_ids\">",
        "sort_key": "some_padding_key_123",
        "gene": {"displayText": "AALB005865-RA", "url": "/app/record/gene"},
    }
    cleaned = clean_table_row(raw_row)
    assert "clustalInput" not in cleaned
    assert "sort_key" not in cleaned
    assert cleaned["ortho_gene_source_id"] == "AALB005865"

    mock_record = {
        "id": [{"name": "source_id", "value": "AGAP006348"}],
        "displayName": "AGAP006348",
        "recordClassName": "GeneRecordClass",
        "attributes": {"primary_key": "AGAP006348", "name": "LRIM1"},
        "tables": {
            "Orthologs": [
                raw_row,
                {
                    "organism": "Culex pipiens",
                    "ortho_gene_source_id": "CPIP001",
                    "sort_key": "key2",
                },
            ]
        },
    }

    # Filtered by "albimanus"
    shaped = shape_record(mock_record, filter_query="albimanus")
    assert shaped["filter"] == "albimanus"
    assert len(shaped["tables"]["Orthologs"]) == 1
    assert shaped["tables"]["Orthologs"][0]["organism"] == "Anopheles albimanus STECLA"
    assert shaped["attributes"]["name"] == "LRIM1"


def test_get_search_detail_for_params_offline():
    from _shaping import get_search_detail_for_params

    class MockClient:
        def __init__(self):
            self.post_called_with = None

        def get(self, path, params=None):
            return {
                "searchData": {
                    "name": "ExpSearch",
                    "parameters": [
                        {
                            "name": "experiment",
                            "dependentParams": ["samples"],
                            "vocabulary": [["exp1", "exp1"], ["exp2", "exp2"]],
                        },
                        {
                            "name": "samples",
                            "vocabulary": [["s1", "s1"]],
                        },
                    ],
                }
            }

        def post(self, path, body, idempotent=True):
            self.post_called_with = body
            return {
                "searchData": {
                    "name": "ExpSearch",
                    "parameters": [
                        {
                            "name": "experiment",
                            "dependentParams": ["samples"],
                            "vocabulary": [["exp1", "exp1"], ["exp2", "exp2"]],
                        },
                        {
                            "name": "samples",
                            "vocabulary": [["s2", "s2"], ["s3", "s3"]],
                        },
                    ],
                }
            }

    c = MockClient()
    # Case 1: no parent param supplied in user_params
    d1 = get_search_detail_for_params(c, "transcript", "ExpSearch", {"other": "val"})
    assert c.post_called_with is None
    samples_p = next(p for p in d1["parameters"] if p["name"] == "samples")
    assert samples_p["vocabulary"] == [["s1", "s1"]]

    # Case 2: parent param supplied
    d2 = get_search_detail_for_params(
        c, "transcript", "ExpSearch", {"experiment": "exp2", "samples": ["s2"]}
    )
    assert c.post_called_with == {"contextParamValues": {"experiment": "exp2"}}
    samples_p2 = next(p for p in d2["parameters"] if p["name"] == "samples")
    assert samples_p2["vocabulary"] == [["s2", "s2"], ["s3", "s3"]]

