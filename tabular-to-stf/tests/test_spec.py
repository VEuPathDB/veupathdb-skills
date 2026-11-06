import copy

import pytest

from _spec import SPEC_VERSION, parse_version, validate_spec


def minimal_spec():
    return {
        "specVersion": "1.0.0",
        "study": {"name": "Demo"},
        "inputDir": "raw-data",
        "entities": [
            {
                "name": "household", "displayName": "Household", "displayNamePlural": "Households",
                "file": "household.csv", "idColumn": "household_id",
                "variables": [{"column": "size", "displayName": "Size"}],
            },
            {
                "name": "participant", "displayName": "Participant", "displayNamePlural": "Participants",
                "file": "participants.csv", "idColumn": "participant_id",
                "parent": "household", "parentColumn": "household_id",
                "variables": [{"column": "age", "name": "age_years", "displayName": "Age",
                               "dataType": "integer", "dataShape": "continuous"}],
                "categories": [{"category": "demo", "displayName": "Demo"}],
            },
        ],
        "transforms": [],
    }


def any_match(errors, text):
    return any(text in e for e in errors)


def test_valid_minimal_spec_gives_no_errors():
    assert validate_spec(minimal_spec()) == []


def test_two_roots_are_reported():
    s = minimal_spec()
    del s["entities"][1]["parent"]
    del s["entities"][1]["parentColumn"]
    assert any_match(validate_spec(s), "root")


def test_parent_cycle_is_reported():
    s = minimal_spec()
    s["entities"][0]["parent"] = "participant"
    s["entities"][0]["parentColumn"] = "participant_id"
    assert any_match(validate_spec(s), "cycle")


def test_unknown_parent_entity_is_reported():
    s = minimal_spec()
    s["entities"][1]["parent"] = "nowhere"
    assert any_match(validate_spec(s), "entities[1].parent")


def test_unknown_parent_category_is_reported():
    s = minimal_spec()
    s["entities"][1]["variables"][0]["parentCategory"] = "missing"
    assert any_match(validate_spec(s), "entities[1].variables[0].parentCategory")


def test_category_cycle_is_reported():
    s = minimal_spec()
    s["entities"][1]["categories"] = [
        {"category": "a", "displayName": "A", "parentCategory": "b"},
        {"category": "b", "displayName": "B", "parentCategory": "a"},
    ]
    assert any_match(validate_spec(s), "category cycle")


def test_replace_cells_cannot_be_auto():
    s = minimal_spec()
    s["transforms"] = [{"op": "replace-cells", "entity": "participant", "column": "age", "cells": [],
                        "reason": "r", "approval": "auto"}]
    assert any_match(validate_spec(s), "transforms[0].approval")


def test_blank_placeholders_auto_only_for_unambiguous_values():
    s = minimal_spec()
    s["transforms"] = [{"op": "blank-placeholders", "entity": "participant", "values": ["unknown"],
                        "reason": "r", "approval": "auto"}]
    assert validate_spec(s) == [
        'transforms[0].approval: "auto" is not allowed for blank-placeholders unless values are all unambiguous placeholders; use "user"'
    ]
    s["transforms"][0]["values"] = ["NA"]
    assert validate_spec(s) == []
    s["transforms"][0]["values"] = ["unknown"]
    s["transforms"][0]["approval"] = "user"
    assert validate_spec(s) == []


@pytest.mark.parametrize("fields, error", [
    ({"format": "DD/MM/YYYY"}, None),
    ({"formats": ["DD/MM/YYYY", "DD/MM/YY"]}, None),
    ({}, "transforms[0].formats: give either format (a string) or formats (a non-empty array of strings)"),
    ({"format": "DD/MM/YYYY", "formats": ["DD/MM/YY"]},
     "transforms[0].formats: give either format (a string) or formats (a non-empty array of strings)"),
    ({"formats": []}, "transforms[0].formats: required non-empty array of strings"),
    ({"formats": ["DD/MM/YYYY", ""]}, "transforms[0].formats: required non-empty array of strings"),
    ({"format": ""}, "transforms[0].format: required string"),
])
def test_parse_dates_takes_format_or_formats(fields, error):
    s = minimal_spec()
    s["transforms"] = [{"op": "parse-dates", "entity": "participant", "column": "dob", "reason": "r",
                        "approval": "user", **fields}]
    assert validate_spec(s) == ([] if error is None else [error])


def test_bad_data_type_name_approval_missing_instead_unknown_entity():
    s = minimal_spec()
    s["entities"][1]["variables"][0]["dataType"] = "float"
    s["entities"][1]["variables"][0]["name"] = "1bad"
    s["entities"][0]["idName"] = "bad name"
    s["transforms"] = [
        {"op": "trim", "entity": "ghost", "reason": "r", "approval": "auto"},
        {"op": "trim", "entity": "participant", "reason": "r", "approval": "maybe"},
        {"op": "trim", "entity": "participant", "reason": "r", "approval": "rejected"},
    ]
    errs = validate_spec(s)
    for want in ["entities[1].variables[0].dataType", "entities[1].variables[0].name", "entities[0].idName",
                 "transforms[0].entity", "transforms[1].approval", "transforms[2].instead"]:
        assert any_match(errs, want), want


def test_non_object_spec_does_not_throw():
    assert validate_spec(None) == ["spec: must be an object"]
    assert len(validate_spec({})) > 0


def test_rename_column_with_from_equal_to_is_rejected():
    s = minimal_spec()
    s["transforms"] = [{"op": "rename-column", "entity": "participant", "from": "age", "to": "age",
                        "reason": "r", "approval": "auto"}]
    assert any_match(validate_spec(s), "transforms[0].to: same as from")
    s["transforms"][0]["to"] = "age_years"
    assert validate_spec(s) == []


@pytest.mark.parametrize("bad", ["/etc/passwd", "../x.csv", "a/../../x.csv", "a\\..\\x.csv", "C:\\x.csv"])
def test_entity_file_and_extra_files_must_stay_inside_input_dir(bad):
    s = minimal_spec()
    s["entities"][0]["file"] = bad
    s["extraFiles"] = ["ok.md", bad]
    errs = validate_spec(s)
    assert any(e.startswith("entities[0].file: must be relative to inputDir") for e in errs), errs
    assert any(e.startswith("extraFiles[1]: must be relative") for e in errs), errs
    assert not any_match(errs, "extraFiles[0]")


def test_paths_with_dots_in_names_are_fine():
    s = minimal_spec()
    s["entities"][0]["file"] = "sub/dir/household.csv"
    s["extraFiles"] = ["docs/dict..v2.xlsx"]
    assert validate_spec(s) == []


def test_notes_lists_value_lists_and_text_fields_are_type_checked_with_paths():
    s = minimal_spec()
    s["notes"] = {"flagged": ["ok"], "decisions": "one string", "pii": [1], "validation": ["ok"]}
    v = s["entities"][1]["variables"][0]
    v.update({"unit": 5, "definition": ["x"], "displayName": None, "providerLabel": {},
              "ordinalLevels": ["a", 2], "vocabularyOrder": "a,b"})
    s["entities"][1]["categories"][0]["definition"] = 3
    errs = validate_spec(s)
    for want in ["notes.decisions: must be an array of strings", "notes.pii: must be an array of strings",
                 "entities[1].variables[0].unit: must be a string",
                 "entities[1].variables[0].definition: must be a string",
                 "entities[1].variables[0].displayName: must be a string",
                 "entities[1].variables[0].providerLabel: must be a string",
                 "entities[1].variables[0].ordinalLevels: must be an array of strings",
                 "entities[1].variables[0].vocabularyOrder: must be an array of strings",
                 "entities[1].categories[0].definition: must be a string"]:
        assert want in errs, want
    assert not any(e.startswith(("notes.flagged", "notes.validation")) for e in errs)
    assert validate_spec({**minimal_spec(), "notes": []}) == ["notes: must be an object"]


def test_null_parent_is_a_present_value_not_a_root():
    spec = minimal_spec()
    spec["entities"][0]["parent"] = None
    errors = validate_spec(spec)
    assert any(e.startswith("entities[0].parent: unknown entity null") for e in errors)
    assert any("need exactly one root" in e for e in errors)


def test_entity_name_message_keeps_js_regex_text():
    s = minimal_spec()
    s["entities"][0]["name"] = "Bad"
    assert "entities[0].name: must match /^[a-z][a-z0-9_]*$/" in validate_spec(s)


def test_spec_version_accepts_any_1x_up_to_the_code_version():
    for v in ("1.0.0", "1.0.5", SPEC_VERSION):
        s = minimal_spec()
        s["specVersion"] = v
        assert validate_spec(s) == [], v


@pytest.mark.parametrize("bad", [1, 1.0, True, None, "1", "1.0", "01.0.0", "1.0.0-rc1", " 1.0.0"])
def test_spec_version_must_be_a_version_string(bad):
    s = minimal_spec()
    s["specVersion"] = bad
    assert 'specVersion: must be a version string like "1.1.0"' in validate_spec(s)


def test_spec_version_newer_than_the_code_is_refused():
    s = minimal_spec()
    s["specVersion"] = "1.2.0"
    assert "specVersion: this spec needs 1.2.0, these scripts support up to 1.1.0" in validate_spec(s)


@pytest.mark.parametrize("v", ["2.0.0", "0.9.0"])
def test_spec_version_with_another_major_is_refused(v):
    s = minimal_spec()
    s["specVersion"] = v
    assert (f"specVersion: major version {v[0]} is not supported "
            f"(these scripts support 1.x, up to 1.1.0)") in validate_spec(s)


def test_parse_version():
    assert parse_version("1.10.0") == (1, 10, 0)
    assert parse_version(1) is None
    assert parse_version("1.0") is None


def test_missing_op_and_entity_print_undefined_like_js():
    s = minimal_spec()
    s["transforms"] = [{"reason": "r", "approval": "user"}]
    assert validate_spec(s) == ["transforms[0].op: unknown op undefined",
                                "transforms[0].entity: unknown entity undefined"]


def test_json_messages_are_compact_and_unescaped():
    s = minimal_spec()
    s["entities"][0]["parent"] = {"a": [1, "é"]}
    assert 'entities[0].parent: unknown entity {"a":[1,"é"]}' in validate_spec(s)


def test_unhashable_values_do_not_crash():
    s = minimal_spec()
    s["entities"][1]["parent"] = ["household"]
    s["transforms"] = [{"op": ["trim"], "entity": {}, "reason": "r", "approval": ["auto"]}]
    s["entities"][1]["variables"][0]["parentCategory"] = []
    errs = validate_spec(s)
    assert any_match(errs, "entities[1].parent: unknown entity")
    assert any_match(errs, "transforms[0].op: unknown op")


def test_validation_does_not_mutate_the_spec():
    s = minimal_spec()
    before = copy.deepcopy(s)
    validate_spec(s)
    assert s == before
