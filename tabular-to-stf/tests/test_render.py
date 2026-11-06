import json
import re
import shutil

import pytest
from conftest import FIXTURES, run_cli

from _notes import render_notes
from _read_table import Table, read_table
from _render import RenderError, render_stf
from _spec import validate_spec
from _yaml import load_stf_yaml

TABULAR = FIXTURES / "tabular"
DATASETS = ["clinical-epi", "mosquito", "coffee-shops"]


def spec(variables, **extra):
    """Minimal one- or two-entity spec; `variables` are the root entity's."""
    return {
        "specVersion": 1,
        "study": {"name": "Test study"},
        "inputDir": "/in",
        "entities": [{"name": "p", "displayName": "P", "displayNamePlural": "Ps", "file": "p.csv",
                      "idColumn": "id", "variables": variables, **extra}],
        "transforms": [],
    }


def table(headers, *rows):
    return Table("t.csv", ",", list(headers), [list(r) for r in rows])


def one(t):
    return {"p": t}


def lines(text):
    return text.split("\n")


def yaml(text):
    return load_stf_yaml(text)[0]


def load_fixture(ds):
    s = json.loads((TABULAR / ds / "spec.json").read_text(encoding="utf-8"))
    tables = {e["name"]: read_table(TABULAR / ds / s["inputDir"] / e["file"]) for e in s["entities"]}
    return s, tables


def throws_render(fn, pattern):
    with pytest.raises(RenderError) as info:
        fn()
    assert isinstance(info.value.messages, list)
    assert re.search(pattern, "\n".join(info.value.messages))


def test_auto_names_come_from_headers_provider_label_keeps_the_header():
    files, _ = render_stf(spec([{"column": "Age (years)"}, {"column": "Hb (g/dL)"}]),
                         one(table(["id", "Age (years)", "Hb (g/dL)"], ["P1", "34", "12.5"])))
    assert lines(files["entity-p.tsv"])[0] == "id \\\\ Descriptors\tage_years\thb_g_dl"
    y = yaml(files["entity-p.yaml"])
    assert [[v["variable"], v["provider_label"]] for v in y["variables"]] == [
        ["age_years", ["Age (years)"]], ["hb_g_dl", ["Hb (g/dL)"]]]
    assert [[v["data_type"], v["data_shape"]] for v in y["variables"]] == [
        ["integer", "continuous"], ["number", "continuous"]]


def test_explicit_name_and_id_name_are_used():
    files, _ = render_stf(spec([{"column": "Age (years)", "name": "age"}], idName="person_id"),
                         one(table(["id", "Age (years)"], ["P1", "34"])))
    assert lines(files["entity-p.tsv"])[0] == "person_id \\\\ Descriptors\tage"
    assert yaml(files["entity-p.yaml"])["id_columns"][0]["id_column"] == "person_id"


def test_an_explicit_name_of_2nd_fails_validate_spec():
    assert any(re.search(r'invalid column name "2nd"', e) for e in validate_spec(spec([{"column": "x", "name": "2nd"}])))
    throws_render(lambda: render_stf(spec([{"column": "x", "name": "2nd"}]), one(table(["id", "x"], ["P1", "1"]))), r"2nd")


def test_clashing_explicit_names_fail_clashing_auto_names_are_suffixed():
    throws_render(lambda: render_stf(spec([{"column": "a", "name": "z"}, {"column": "b", "name": "z"}]),
                                     one(table(["id", "a", "b"], ["P1", "1", "2"]))),
                  r'p: output column name "z" is used by both "a" and "b"')
    files, _ = render_stf(spec([{"column": "A b"}, {"column": "a_b", "name": "a_b"}, {"column": "a-b"}]),
                         one(table(["id", "A b", "a_b", "a-b"], ["P1", "1", "2", "3"])))
    assert lines(files["entity-p.tsv"])[0] == "id \\\\ Descriptors\ta_b_2\ta_b\ta_b_3"


def test_a_child_lists_the_parent_id_first_under_the_parents_output_id_name():
    s = spec([{"column": "x"}], idName="hh")
    s["entities"].append({"name": "c", "displayName": "C", "displayNamePlural": "Cs", "file": "c.csv", "idColumn": "cid",
                          "parent": "p", "parentColumn": "household", "variables": [{"column": "hh"}]})
    tables = {"p": table(["id", "x"], ["H1", "a"]), "c": table(["cid", "household", "hh"], ["C1", "H1", "y"])}
    files, _ = render_stf(s, tables)
    assert yaml(files["study.yaml"]) == {"name": "Test study", "entities": ["p", "c"]}
    assert lines(files["entity-c.tsv"]) == ["hh\tcid \\\\ Descriptors\thh_2", "H1\tC1\ty", ""]
    y = yaml(files["entity-c.yaml"])
    assert y["id_columns"] == [
        {"id_column": "hh", "entity_name": "p", "entity_level": -1, "provider_label": ["household"]},
        {"id_column": "cid", "entity_name": "c", "provider_label": ["cid"]},
    ]
    assert y["categories"] == []


def test_an_explicit_child_name_or_id_name_equal_to_the_parents_id_name_is_an_error():
    def build(**child):
        s = spec([{"column": "x"}], idName="hh")
        s["entities"].append({"name": "c", "displayName": "C", "displayNamePlural": "Cs", "file": "c.csv", "idColumn": "cid",
                              "parent": "p", "parentColumn": "household", "variables": [{"column": "v"}], **child})
        return s
    tables = {"p": table(["id", "x"], ["H1", "a"]), "c": table(["cid", "household", "v"], ["C1", "H1", "y"])}
    throws_render(lambda: render_stf(build(variables=[{"column": "v", "name": "hh"}]), tables),
                  r'c: output column name "hh" for column "v" is the ID column name of parent entity "p"')
    throws_render(lambda: render_stf(build(idName="hh"), tables),
                  r'c: output column name "hh" for column "cid" is the ID column name of parent entity "p"')


def test_an_unaccounted_column_fails_the_render():
    throws_render(lambda: render_stf(spec([{"column": "a"}]), one(table(["id", "a", "b c"], ["P1", "1", "2"]))),
                  r"unaccounted column p\.b c")


def test_a_declared_type_that_does_not_parse_lists_the_bad_values_with_row_ids():
    throws_render(lambda: render_stf(spec([{"column": "n", "dataType": "integer"}]),
                                     one(table(["id", "n"], ["P1", "1"], ["P2", "abc"], ["P3", "2.5"], ["P4", ""]))),
                  r'p\.n: declared integer but 2 values do not parse: "abc" \(P2\), "2\.5" \(P3\)')
    throws_render(lambda: render_stf(spec([{"column": "d", "dataType": "date"}]), one(table(["id", "d"], ["P1", "2023-02-30"]))),
                  r'"2023-02-30" \(P1\)')


def test_a_date_before_year_100_does_not_parse_as_in_js():
    # JS Date.UTC maps years 0-99 to 1900-1999, so isIsoDate rejects them
    throws_render(lambda: render_stf(spec([{"column": "d", "dataType": "date"}]),
                                     one(table(["id", "d"], ["P1", "0099-01-01"], ["P2", "0100-01-01"]))),
                  r'declared date but 1 value does not parse: "0099-01-01" \(P1\)$')


def test_a_tab_or_line_break_in_a_value_fails_naming_entity_column_and_row_id():
    throws_render(lambda: render_stf(spec([{"column": "a"}]), one(table(["id", "a"], ["P1", "ok"], ["P2", "x\ty"]))),
                  r"p\.a: value in row P2 contains a tab or line break")
    throws_render(lambda: render_stf(spec([{"column": "a"}]), one(table(["id", "a"], ["P1", "x\ny"]))), r"row P1")


def geo_spec(variables):
    return spec(variables, geo={"latitude": "gps_lat", "longitude": "gps_lon"})


def geo_table(extra_headers=(), extra=()):
    return one(table(["id", "gps_lat", "gps_lon", *extra_headers], ["P1", "1.5", "-30.25", *extra]))


def test_geo_columns_are_renamed_when_either_rule_fails_and_get_geo_metadata():
    files, log = render_stf(geo_spec([{"column": "gps_lat"}, {"column": "gps_lon"}]), geo_table())
    assert isinstance(log, list)
    assert lines(files["entity-p.tsv"])[0] == "id \\\\ Descriptors\tlatitude\tlongitude"
    lat, lon = yaml(files["entity-p.yaml"])["variables"]
    assert [lat["stable_id"], lat["data_type"], lat["data_shape"], lat["display_type"]] == ["OBI_0001620", "number", "continuous", "latitude"]
    assert [lon["stable_id"], lon["data_type"], lon["data_shape"], lon["display_type"]] == ["OBI_0001621", "longitude", "continuous", "longitude"]
    assert re.search(r"Before `eda` validation or export, run `map_entities\(study, infer_geo_variables_for_eda\)`", files["curation-notes.md"])
    ok, _ = render_stf(spec([{"column": "Lat"}, {"column": "Long"}], geo={"latitude": "Lat", "longitude": "Long"}),
                       one(table(["id", "Lat", "Long"], ["P1", "1", "2"])))
    assert lines(ok["entity-p.tsv"])[0] == "id \\\\ Descriptors\tlat\tlong"


def test_a_stray_coordinate_like_column_in_a_geo_entity_is_an_error_suggesting_the_fix():
    throws_render(lambda: render_stf(geo_spec([{"column": "gps_lat"}, {"column": "gps_lon"}, {"column": "long_term_resident"}]),
                                     geo_table(["long_term_resident"], ["Yes"])),
                  r'p\.long_term_resident: name "long_term_resident" looks like a longitude.*rename-column')
    throws_render(lambda: render_stf(geo_spec([{"column": "gps_lat"}, {"column": "gps_lon"},
                                               {"column": "Long-term illness", "name": "chronic_illness"}]),
                                     geo_table(["Long-term illness"], ["No"])),
                  r'p\.chronic_illness: provider_label "Long-term illness" looks like a longitude.*providerLabel')


def test_provider_label_overrides_the_header_and_is_logged_under_decisions():
    files, _ = render_stf(geo_spec([{"column": "gps_lat"}, {"column": "gps_lon"},
                                    {"column": "Long-term illness", "name": "chronic_illness", "providerLabel": "Chronic illness"}]),
                          geo_table(["Long-term illness"], ["No"]))
    assert yaml(files["entity-p.yaml"])["variables"][2]["provider_label"] == ["Chronic illness"]
    decisions = files["curation-notes.md"].split("## Decisions and answers")[1].split("## Validation")[0]
    assert re.search(r'`p\.chronic_illness`: provider_label set to "Chronic illness" \(original header "Long-term illness"\)', decisions)


def test_a_non_geo_entity_with_two_coordinate_like_columns_fails_one_is_allowed():
    throws_render(lambda: render_stf(spec([{"column": "lat"}, {"column": "latitude"}]), one(table(["id", "lat", "latitude"], ["P1", "1", "2"]))),
                  r"p: 2 columns look like coordinates \(lat, latitude\)")
    render_stf(spec([{"column": "lat"}]), one(table(["id", "lat"], ["P1", "1"])))


def test_ids_and_codes_with_leading_zeros_stay_as_written_as_strings():
    files, _ = render_stf(spec([{"column": "code"}]), one(table(["id", "code"], ["0123", "0007"], ["0456", "12"])))
    assert lines(files["entity-p.tsv"])[1:] == ["0123\t0007", "0456\t12", ""]
    assert yaml(files["entity-p.yaml"])["variables"][0]["data_type"] == "string"


def test_no_float_reaches_the_yaml_unquoted_values_stay_text():
    v = {"column": "a", "unit": "1.5", "multiValueDelimiter": 2.5, "stableId": 7, "isMultiValued": 1,
         "ordinalLevels": ["1", "2.5"], "displayName": "3.0"}
    files, _ = render_stf(spec([v]), one(table(["id", "a"], ["P1", "1"])))
    got = yaml(files["entity-p.yaml"])["variables"][0]
    assert [got["unit"], got["multi_value_delimiter"], got["stable_id"], got["is_multi_valued"], got["ordinal_levels"], got["display_name"]] == [
        "1.5", "2.5", "7", True, ["1", "2.5"], "3.0"]
    assert "!!" not in files["entity-p.yaml"]


def test_render_notes_lists_sections_in_order_validation_defaults_to_not_run():
    s = spec([{"column": "a"}])
    s["transforms"] = [{"op": "trim", "entity": "p", "approval": "auto", "reason": "spaces"}]
    notes = render_notes(s, [{"index": 0, "op": "trim", "entity": "p", "approval": "auto", "cellsChanged": 3}])
    heads = [l for l in notes.split("\n") if l.startswith("## ")]
    assert heads == ["## Study", "## Entity tree", "## Routine normalisation", "## Data changes",
                     "## Flagged, not changed", "## Decisions and answers", "## Validation"]
    assert re.search(r"## Validation\n\nNot run \(mode 1\)\n", notes)
    assert re.search(r"`p` \(all columns\): trim whitespace, 3 cells changed\. Reason: spaces", notes)


def test_render_notes_states_the_python_re_render_command():
    notes = render_notes(spec([{"column": "a"}]), [])
    assert ("To re-render it, run `uv run <skill>/scripts/stf.py render <this directory>/curation-spec.json <this directory>`, "
            "where `<skill>` is the `tabular-to-stf` skill's folder.") in notes


def test_render_notes_lists_row_ids_for_user_value_changes_capped_at_10_and_not_for_auto_ones():
    s = spec([{"column": "a"}])
    s["transforms"] = [
        {"op": "map-values", "entity": "p", "column": "a", "map": {"x": "y"}, "approval": "user", "reason": "typo"},
        {"op": "map-values", "entity": "p", "column": "a", "map": {"z": "y"}, "approval": "user", "reason": "many"},
        {"op": "trim", "entity": "p", "approval": "auto", "reason": "spaces"},
    ]
    ids = [f"R{i + 1}" for i in range(13)]
    notes = render_notes(s, [
        {"index": 0, "op": "map-values", "entity": "p", "column": "a", "approval": "user", "cellsChanged": 1, "ids": ["P7"]},
        {"index": 1, "op": "map-values", "entity": "p", "column": "a", "approval": "user", "cellsChanged": 13, "ids": ids},
        {"index": 2, "op": "trim", "entity": "p", "approval": "auto", "cellsChanged": 2, "ids": ["Q1", "Q2"]},
    ])
    assert re.search(r'`p\.a`: "x" → "y", 1 cell changed \(row P7\)\. Reason: typo', notes)
    assert re.search(r"13 cells changed \(rows R1, R2, R3, R4, R5, R6, R7, R8, R9, R10 and 3 more\)\. Reason: many", notes)
    assert re.search(r"trim whitespace, 2 cells changed\. Reason: spaces", notes)
    assert "Q1" not in notes


def test_render_notes_names_every_parse_dates_format():
    s = spec([{"column": "a"}])
    s["transforms"] = [
        {"op": "parse-dates", "entity": "p", "column": "a", "format": "DD/MM/YYYY", "approval": "user", "reason": "uk"},
        {"op": "parse-dates", "entity": "p", "column": "a", "formats": ["DD/MM/YYYY", "DD/MM/YY"],
         "approval": "user", "reason": "mixed"},
    ]
    notes = render_notes(s, [
        {"index": 0, "op": "parse-dates", "entity": "p", "column": "a", "approval": "user", "cellsChanged": 0, "ids": []},
        {"index": 1, "op": "parse-dates", "entity": "p", "column": "a", "approval": "user", "cellsChanged": 0, "ids": []},
    ])
    assert "`p.a`: parse dates DD/MM/YYYY → YYYY-MM-DD" in notes
    assert "`p.a`: parse dates DD/MM/YYYY or DD/MM/YY → YYYY-MM-DD" in notes


@pytest.mark.parametrize("ds", DATASETS)
def test_golden_yaml_round_trips_display_names_and_definitions(ds):
    s, tables = load_fixture(ds)
    files, _ = render_stf(s, tables)
    assert sorted(files) == sorted(["curation-notes.md", "study.yaml",
                                    *[f"entity-{e['name']}.{x}" for e in s["entities"] for x in ("tsv", "yaml")]])
    for e in s["entities"]:
        y = yaml(files[f"entity-{e['name']}.yaml"])
        assert y["display_name"] == e["displayName"]
        # Variables are written in spec order
        assert len(y["variables"]) == len(e["variables"])
        for got, v in zip(y["variables"], e["variables"]):
            assert got["display_name"] == v.get("displayName")
            assert got.get("definition") == v.get("definition")
            if "vocabularyOrder" in v:
                assert got["vocabulary_order"] == v["vocabularyOrder"]
            if "ordinalLevels" in v:
                assert got["ordinal_levels"] == v["ordinalLevels"]
        assert [[c["category"], c["display_name"], c.get("definition")] for c in y.get("categories") or []] == [
            [c["category"], c["displayName"], c.get("definition")] for c in e.get("categories") or []]


# ---- CLI ----

def scratch(tmp_path, ds="clinical-epi"):
    """A copy of a fixture's inputs and spec, so tests can mutate them."""
    shutil.copytree(TABULAR / ds / "inputs", tmp_path / "inputs")
    shutil.copy(TABULAR / ds / "spec.json", tmp_path / "spec.json")
    return tmp_path


def stf_files(d):
    return sorted(f.name for f in d.iterdir() if f.name not in ("raw-data", "curation-spec.json"))


def render_ok(*args):
    r = run_cli("render", *map(str, args))
    assert r.returncode == 0, r.stderr
    return r.stdout


def render_fails(*args):
    r = run_cli("render", *map(str, args))
    assert r.returncode == 1
    return r.stdout + r.stderr


def test_cli_renders_with_raw_data_a_saved_spec_that_re_renders_from_the_folder_alone(tmp_path):
    root = scratch(tmp_path)
    out = root / "out"
    printed = render_ok(root / "spec.json", out)
    assert re.search(r"study\.yaml", printed)
    s = json.loads((root / "spec.json").read_text(encoding="utf-8"))
    for f in [*(e["file"] for e in s["entities"]), *s["extraFiles"]]:
        assert (out / "raw-data" / f).read_bytes() == (root / "inputs" / f).read_bytes(), f"raw-data/{f}"
    saved = json.loads((out / "curation-spec.json").read_text(encoding="utf-8"))
    assert saved["inputDir"] == "raw-data"
    assert {**saved, "inputDir": s["inputDir"]} == s
    assert re.search(r"`raw-data/participants\.csv` \(16 rows\)", (out / "curation-notes.md").read_text(encoding="utf-8"))
    # Comparison with expected/ is by content, in test_golden.py
    assert stf_files(out) == stf_files(TABULAR / "clinical-epi" / "expected")

    before = {f: (out / f).read_text(encoding="utf-8") for f in stf_files(out)}
    copy = root / "moved"
    shutil.copytree(out, copy)
    render_ok(copy / "curation-spec.json", copy)
    assert {f: (copy / f).read_text(encoding="utf-8") for f in stf_files(copy)} == before


def test_cli_prints_the_written_paths_in_order(tmp_path):
    root = scratch(tmp_path, "mosquito")
    out = (root / "out").absolute()
    printed = render_ok(root / "spec.json", out).splitlines()
    written = [f"entity-{n}.{x}" for n in ("site", "collection", "sample", "assay") for x in ("tsv", "yaml")]
    written += ["study.yaml", "curation-notes.md", "curation-spec.json"]
    copies = ["collection_sites.tsv", "collections.tsv", "samples.tsv", "assays.tsv"]
    assert printed == [str(out / n) for n in written] + [str(out / "raw-data" / n) for n in copies]


def test_cli_refuses_a_non_empty_out_dir_without_curation_spec_json_re_renders_into_one_with_it(tmp_path):
    root = scratch(tmp_path)
    out = root / "out"
    out.mkdir()
    (out / "keep.txt").write_text("mine", encoding="utf-8")
    assert re.search(r"not empty and has no curation-spec\.json", render_fails(root / "spec.json", out))
    out2 = root / "out2"
    render_ok(root / "spec.json", out2)
    render_ok(root / "spec.json", out2)
    assert (out2 / "study.yaml").exists()


def test_cli_a_changed_source_file_with_the_same_name_as_a_raw_data_copy_is_refused(tmp_path):
    root = scratch(tmp_path)
    out = root / "out"
    render_ok(root / "spec.json", out)
    villages = root / "inputs" / "villages.csv"
    villages.write_bytes(villages.read_bytes().replace(b"Kanyawegi", b"Kanyawegy"))
    assert re.search(r"raw-data/villages\.csv differs from .*villages\.csv", render_fails(root / "spec.json", out))
    assert "Kanyawegi" in (out / "raw-data" / "villages.csv").read_text(encoding="utf-8")


def test_cli_no_raw_data_copies_nothing_and_keeps_an_absolute_input_dir(tmp_path):
    root = scratch(tmp_path, "mosquito")
    out = root / "out"
    render_ok(root / "spec.json", out, "--no-raw-data")
    assert not (out / "raw-data").exists()
    saved = json.loads((out / "curation-spec.json").read_text(encoding="utf-8"))
    assert saved["inputDir"] == str(root / "inputs")
    assert f"`{root / 'inputs'}/samples.tsv` (15 rows)" in (out / "curation-notes.md").read_text(encoding="utf-8")
    render_ok(out / "curation-spec.json", out, "--no-raw-data")


def test_cli_render_errors_exit_1_with_the_messages(tmp_path):
    root = scratch(tmp_path, "mosquito")
    s = json.loads((root / "spec.json").read_text(encoding="utf-8"))
    s["entities"][0]["variables"].pop()
    (root / "spec.json").write_text(json.dumps(s), encoding="utf-8")
    text = render_fails(root / "spec.json", root / "out")
    assert "Error: the spec does not render:\n- " in text
    assert re.search(r"unaccounted column site\.habitat", text)
    assert not (root / "out" / "study.yaml").exists()


def test_rendered_files_are_utf8_with_lf_only(tmp_path):
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "p.csv").write_bytes("id,city\r\nP1,São Paulo\r\nP2,Zürich\r\n".encode("utf-8"))
    s = spec([{"column": "city", "displayName": "Cidade é"}])
    s["inputDir"] = "in"
    (tmp_path / "spec.json").write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "out"
    render_ok(tmp_path / "spec.json", out)
    assert "São Paulo" in (out / "entity-p.tsv").read_text(encoding="utf-8")
    files = list(out.glob("*.*"))
    assert len(files) == 5
    for f in files:
        data = f.read_bytes()
        assert b"\r" not in data
        data.decode("utf-8")
