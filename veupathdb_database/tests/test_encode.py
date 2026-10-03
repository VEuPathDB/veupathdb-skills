import json
import pathlib

import pytest

FX = pathlib.Path(__file__).parent / "fixtures"


def _mw():
    return json.loads((FX / "mw.json").read_text())


def _bool():
    return json.loads((FX / "bool.json").read_text())


def test_defaults_fill_and_stringify():
    from _shaping import encode_params

    wire = encode_params(_mw(), {"organism": ["Plasmodium falciparum 3D7"]})
    assert wire["min_molecular_weight"] == "10000"
    assert wire["max_molecular_weight"] == "50000"
    assert json.loads(wire["organism"]) == ["Plasmodium falciparum 3D7"]


def test_numbers_are_stringified():
    from _shaping import encode_params

    wire = encode_params(
        _mw(),
        {"organism": ["Plasmodium falciparum 3D7"], "min_molecular_weight": 25000},
    )
    assert wire["min_molecular_weight"] == "25000"


def test_tree_parent_expands_to_leaves():
    from _shaping import encode_params

    wire = encode_params(_mw(), {"organism": ["Plasmodium"]})
    leaves = json.loads(wire["organism"])
    assert len(leaves) > 5
    assert "Plasmodium" not in leaves  # the parent itself is never sent


def test_unknown_param_and_unknown_value():
    from _shaping import ParamError, encode_params

    with pytest.raises(ParamError) as e:
        encode_params(_mw(), {"organsim": ["x"]})
    assert "organism" in str(e.value)
    with pytest.raises(ParamError) as e:
        encode_params(_mw(), {"organism": ["Plasmodium falciparum 3D8"]})
    assert "3D7" in str(e.value)  # close match suggested


def test_input_step_params_are_empty_strings():
    from _shaping import encode_params

    wire = encode_params(_bool(), {"bq_operator": "INTERSECT"})
    left = "bq_left_op_TranscriptRecordClasses_TranscriptRecordClass"
    right = "bq_right_op_TranscriptRecordClasses_TranscriptRecordClass"
    assert wire[left] == "" and wire[right] == ""
    assert wire["bq_operator"] == "INTERSECT"


def test_extract_count_precedence_and_unmeasured():
    from _shaping import extract_count

    assert extract_count({"displayViewTotalCount": 5, "totalCount": 9}) == (
        5,
        "displayViewTotalCount",
    )
    assert extract_count({"totalCount": 9}) == (9, "totalCount")
    assert extract_count({}) == (None, None)


def test_missing_required_multipick_raises_param_error():
    from _shaping import ParamError, encode_params

    with pytest.raises(ParamError) as exc_info:
        encode_params(_mw(), {})
    msg = str(exc_info.value)
    assert "required parameter(s) with no value and no default: ['organism']" in msg
    assert "requires at least 1 selection" in msg
    assert "param-options" in msg


def test_empty_required_multipick_raises_param_error():
    from _shaping import ParamError, encode_params

    with pytest.raises(ParamError) as exc_info:
        encode_params(_mw(), {"organism": []})
    msg = str(exc_info.value)
    assert "parameter 'organism' cannot be empty" in msg
    assert "requires at least 1 selection" in msg
    assert "param-options" in msg


def _dataset_search():
    return {
        "urlSegment": "GeneByLocusTag",
        "parameters": [
            {
                "name": "ds_gene_ids",
                "type": "input-dataset",
                "allowEmptyValue": False,
                "isVisible": True,
            }
        ],
    }


def test_input_dataset_numeric_passes_through():
    from _shaping import encode_params

    wire = encode_params(_dataset_search(), {"ds_gene_ids": "123456"})
    assert wire["ds_gene_ids"] == "123456"

    wire_int = encode_params(_dataset_search(), {"ds_gene_ids": 123456})
    assert wire_int["ds_gene_ids"] == "123456"


def test_input_dataset_with_client_auto_uploads():
    from unittest.mock import MagicMock
    from _shaping import encode_params

    mock_client = MagicMock()
    mock_client.create_id_dataset.return_value = 777888

    wire = encode_params(
        _dataset_search(),
        {"ds_gene_ids": "AGAP001234, AGAP001235"},
        client=mock_client,
    )
    assert wire["ds_gene_ids"] == "777888"
    mock_client.create_id_dataset.assert_called_once_with(["AGAP001234", "AGAP001235"])


def test_input_dataset_without_client_raises_helpful_error():
    from _shaping import ParamError, encode_params

    with pytest.raises(ParamError) as exc_info:
        encode_params(_dataset_search(), {"ds_gene_ids": "AGAP001234"})
    msg = str(exc_info.value)
    assert "Parameter 'ds_gene_ids' expects a numeric Dataset ID" in msg
    assert "fetch-record" in msg

