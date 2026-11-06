import _constants
from _common import infer_type, is_valid_column_name, is_valid_iso_date, to_column_name, unique_column_names


def test_is_valid_iso_date_is_shared_by_check_and_render():
    import _check
    import _render
    for s in ["2020-02-29", "0100-01-01", "9999-12-31"]:
        assert is_valid_iso_date(s), s
    for s in ["2023-02-30", "2021-02-29", "0050-01-01", "2020-1-01", "2020-01-01 ", "２０２０-01-01", ""]:
        assert not is_valid_iso_date(s), s
    assert _render.PARSES["date"] is is_valid_iso_date
    assert _check.is_valid_iso_date is is_valid_iso_date


def test_to_column_name_gives_snake_case_names_that_need_no_quoting():
    assert to_column_name("Age (years)") == "age_years"
    assert to_column_name("1st visit") == "x1st_visit"
    assert to_column_name("_id") == "id"
    assert to_column_name("Hb (g/dL)") == "hb_g_dl"
    assert to_column_name("°C") == "c"
    assert to_column_name("%%") == "x"
    assert to_column_name("participant_id") == "participant_id"


def test_unique_column_names_suffixes_later_duplicates():
    assert unique_column_names(["a_b", "a_b", "c", "a_b"]) == ["a_b", "a_b_2", "c", "a_b_3"]


def test_is_valid_column_name():
    for ok in ["age", "Age_2", "x1"]:
        assert is_valid_column_name(ok)
    for bad in ["1age", "_age", "a.b", "a b", "", "ä", "age\n"]:
        assert not is_valid_column_name(bad)


def test_infer_type_keeps_leading_zero_codes_as_strings():
    assert infer_type(["007", "012"]) == {"data_type": "string", "data_shape": "categorical"}


def test_infer_type_integer_number_date_and_empty():
    assert infer_type(["1", "-2", ""]) == {"data_type": "integer", "data_shape": "continuous"}
    assert infer_type(["1.5", "2e3"]) == {"data_type": "number", "data_shape": "continuous"}
    assert infer_type(["2020-01-31"]) == {"data_type": "date", "data_shape": "continuous"}
    assert infer_type(["1\n"]) == {"data_type": "string", "data_shape": "categorical"}
    assert infer_type([]) == {"data_type": "string", "data_shape": "categorical"}


def test_to_column_name_is_ascii_only():
    assert to_column_name("Âge (années)") == "ge_ann_es"


def test_constants_are_frozen_with_the_expected_values():
    assert _constants.DATA_TYPES == ("string", "number", "integer", "date", "longitude")
    assert _constants.HIDDEN == ("download", "variableTree", "map", "everywhere")
    assert isinstance(_constants.DATA_SHAPES, tuple)
    assert _constants.MAX_VALUE_LENGTH == 80
    assert _constants.SAVED_SPEC == "curation-spec.json"
    assert _constants.RAW_DIR == "raw-data"
    assert "not done" in _constants.PLACEHOLDERS
    assert _constants.UNAMBIGUOUS_PLACEHOLDERS[-1] == "NULL"
