import copy
import re

import pytest

from _read_table import Table
from _transforms import TransformError, apply_transforms


def T(op, **extra):
    return {"op": op, "entity": "p", "reason": "r", "approval": "user", **extra}


def spec(transforms, id_column="id"):
    return {"entities": [{"name": "p", "idColumn": id_column}], "transforms": transforms}


def mk(headers, rows):
    return Table(file="/data/p.csv", delimiter=",", headers=headers, rows=rows)


def tables():
    return {"p": mk(["id", "age", "note"], [["P1", "80+", " NA "], ["P2", "5", "ok "], ["P3", "", "NA"]])}


def run(transforms, t=None, id_column="id"):
    return apply_transforms(t if t is not None else tables(), spec(transforms, id_column))


def test_trim_defaults_to_all_columns_and_counts_changed_cells():
    out, log = run([T("trim")])
    assert out["p"].rows[0] == ["P1", "80+", "NA"]
    assert log[0]["cellsChanged"] == 2
    assert log[0]["index"] == 0


def test_trim_uses_js_whitespace_set():
    t = {"p": mk(["id", "v"], [["A", "﻿ x "], ["B", "\x1cy\x1c"]])}
    out, _ = run([T("trim")], t)
    assert out["p"].rows == [["A", "x"], ["B", "\x1cy\x1c"]]


def test_trim_with_columns():
    out, log = run([T("trim", columns=["note"])])
    assert out["p"].rows[1][2] == "ok"
    assert log[0]["cellsChanged"] == 2


def test_blank_placeholders():
    out, log = run([T("blank-placeholders", values=["NA"], columns=["note"])])
    assert out["p"].rows[2][2] == ""
    assert out["p"].rows[0][2] == " NA "
    assert log[0]["cellsChanged"] == 1


def uncertain():
    return {"p": mk(["id", "age"], [["P1", "40?"], ["P2", "~35"], ["P3", "35"]])}


def test_map_values_regex_with_capture():
    out, log = run([T("map-values", column="age", match="regex", map={r"(\d+)\?": "$1"}),
                    T("map-values", column="age", match="regex", map={r"~(\d+)": "$1"})], uncertain())
    assert [r[1] for r in out["p"].rows] == ["40", "35", "35"]
    assert log[0]["ids"] == ["P1"] and log[1]["ids"] == ["P2"]
    assert log[0]["cellsChanged"] == 1


def test_derive_column_regex_flag_before_strip():
    out, _ = run([T("derive-column", column="age_uncertain", match="regex",
                    map={r"~.*": "Yes", r".*\?": "Yes"}, default="No", **{"from": "age"})], uncertain())
    assert [r[2] for r in out["p"].rows] == ["Yes", "Yes", "No"]


def test_blank_placeholders_regex():
    t = {"p": mk(["id", "v"], [["A", "n.a."], ["B", "N/A"], ["C", "nan"]])}
    out, _ = run([T("blank-placeholders", match="regex", values=[r"(?i)n\.?/?a\.?"], columns=["v"])], t)
    assert [r[1] for r in out["p"].rows] == ["", "", "nan"]


def test_regex_matches_empty_cells_too():
    out, _ = run([T("map-values", column="age", match="regex", map={".*": "x"})])
    assert [r[1] for r in out["p"].rows] == ["x", "x", "x"]


def test_ambiguous_regex_fails_naming_row_ids():
    t = {"p": mk(["id", "age"], [["P1", "3?"], ["P2", "4"]])}
    with pytest.raises(TransformError, match=re.escape(
            'values in column "age" match more than one key with different results for row IDs: P1; '
            "tighten the patterns or settle them with replace-cells before this transform")):
        run([T("map-values", column="age", match="regex", map={r".*\?": "a", r"\d\?": "b"})], t)


def test_ambiguous_derive_column_names_the_source_column():
    t = {"p": mk(["id", "age"], [["P1", "3?"]])}
    with pytest.raises(TransformError, match='values in column "age" match more than one key'):
        run([T("derive-column", column="u", match="regex", map={r".*\?": "a", r"\d\?": "b"},
               default="n", **{"from": "age"})], t)


def test_overlapping_keys_with_the_same_result_are_fine():
    t = {"p": mk(["id", "age"], [["P1", "~3?"]])}
    out, _ = run([T("derive-column", column="u", match="regex", map={r"~.*": "Yes", r".*\?": "Yes"},
                    default="No", **{"from": "age"})], t)
    assert out["p"].rows[0][2] == "Yes"


def test_exact_mode_value_with_dollar_is_literal():
    out, _ = run([T("map-values", column="age", map={"80+": "$1"})])
    assert out["p"].rows[0][1] == "$1"


def test_upto_and_entity_limit_the_run_and_keep_spec_indexes():
    s = {"entities": [{"name": "p", "idColumn": "id"}, {"name": "q", "idColumn": "id"}],
         "transforms": [T("trim"), {**T("trim"), "entity": "q"}, T("drop-column", column="note")]}
    out, log = apply_transforms(tables(), s, upto=2, entity="p")
    assert [e["index"] for e in log] == [0]
    assert "note" in out["p"].headers


def test_map_values_exact_match_only():
    out, log = run([T("map-values", column="age", map={"80+": "80", "5": "5"})])
    assert [r[1] for r in out["p"].rows] == ["80", "5", ""]
    assert log[0]["cellsChanged"] == 1
    assert log[0]["column"] == "age"


def test_rename_column_and_drop_column():
    out, _ = run([T("rename-column", **{"from": "age", "to": "years"}), T("drop-column", column="note")])
    assert out["p"].headers == ["id", "years"]
    assert out["p"].rows[0] == ["P1", "80+"]


def test_missing_column_error_names_entity_index_and_column():
    with pytest.raises(TransformError, match=r"zzz"):
        run([T("trim"), T("drop-column", column="zzz")])
    with pytest.raises(TransformError) as e:
        run([T("drop-column", column="zzz")])
    msg = str(e.value)
    assert 'entity "p"' in msg and "transforms[0]" in msg and "zzz" in msg
    assert msg == 'entity "p", transforms[0] (drop-column): column "zzz" not found'


def test_proposed_and_rejected_are_skipped_but_logged():
    out, log = run([
        T("drop-column", column="note", approval="proposed"),
        T("drop-column", column="age", approval="rejected", instead="x"),
    ])
    assert out["p"].headers == ["id", "age", "note"]
    assert [[l["index"], l["approval"], l["cellsChanged"]] for l in log] == [[0, "proposed", 0], [1, "rejected", 0]]
    assert log[0]["column"] == "note"
    assert list(log[0].keys()) == ["index", "op", "entity", "approval", "cellsChanged", "column"]


def test_log_key_order():
    _, log = run([T("map-values", column="note", map={"NA": ""}), T("rename-column", **{"from": "age", "to": "y"})])
    assert list(log[0].keys()) == ["index", "op", "entity", "approval", "cellsChanged", "column", "ids"]
    assert list(log[1].keys()) == ["index", "op", "entity", "approval", "cellsChanged", "column"]
    assert log[1]["column"] == "y"


def test_no_table_for_entity():
    with pytest.raises(TransformError, match=r'entity "q", transforms\[0\] \(trim\): no table for entity'):
        run([T("trim", entity="q")])


def test_unknown_op():
    with pytest.raises(TransformError, match=r"\(bogus\): unknown op"):
        run([T("bogus")])


def test_replace_cells_applies_by_row_id():
    out, log = run([T("replace-cells", column="age", cells=[{"id": "P1", "from": "80+", "to": "80"}])])
    assert out["p"].rows[0][1] == "80"
    assert log[0]["ids"] == ["P1"]
    assert log[0]["cellsChanged"] == 1


def test_stale_replace_cells_throws_naming_the_row_id():
    with pytest.raises(TransformError, match="P2") as e:
        run([T("replace-cells", column="age", cells=[{"id": "P2", "from": "99", "to": "1"}])])
    assert 'is "5", spec expects "99" (stale spec?)' in str(e.value)
    with pytest.raises(TransformError, match="P9"):
        run([T("replace-cells", column="age", cells=[{"id": "P9", "from": "1", "to": "2"}])])


def test_parse_dates_dd_mm_yyyy():
    t = {"p": mk(["id", "d"], [["A", "03/04/2023"], ["B", ""]])}
    out, log = run([T("parse-dates", column="d", format="DD/MM/YYYY")], t)
    assert [r[1] for r in out["p"].rows] == ["2023-04-03", ""]
    assert log[0]["cellsChanged"] == 1


def test_parse_dates_single_digit_tokens_and_bad_rows():
    t = {"p": mk(["id", "d"], [["A", "3.4.2023"], ["B", "12.11.2023"]])}
    out, _ = run([T("parse-dates", column="d", format="D.M.YYYY")], t)
    assert [r[1] for r in out["p"].rows] == ["2023-04-03", "2023-11-12"]
    bad = {"p": mk(["id", "d"], [["A", "31/02/2023"], ["B", "1/2/2023"], ["C", "01/02/2023"]])}
    with pytest.raises(TransformError) as e:
        run([T("parse-dates", column="d", format="DD/MM/YYYY")], bad)
    msg = str(e.value)
    assert "A" in msg and "B" in msg and not re.search(r"\bC\b", msg)
    assert msg.endswith("do not match format DD/MM/YYYY and are not YYYY-MM-DD dates for row IDs: A, B")


@pytest.mark.parametrize("value", [
    "2023-02-29",  # not a leap year
    "2023-00-10",
    "2023-13-01",
    "2023-04-31",
    "2023-04-00",
    "0050-01-01",  # JS Date.UTC maps years 0-99 to 19xx, so the JS rejects these
    "0000-01-01",
    "٢023-01-01",  # non-ASCII digit
    "2023-01-01\n",
])
def test_parse_dates_rejects_impossible_or_unmatched(value):
    t = {"p": mk(["id", "d"], [["A", value]])}
    with pytest.raises(TransformError, match="row IDs: A"):
        run([T("parse-dates", column="d", format="YYYY-MM-DD")], t)


def test_parse_dates_accepts_leap_day_and_escapes_format_literals():
    t = {"p": mk(["id", "d"], [["A", "2024-02-29"], ["B", "29.02.2024"]])}
    out, _ = run([T("parse-dates", column="d", format="YYYY-MM-DD")], {"p": mk(["id", "d"], [t["p"].rows[0]])})
    assert out["p"].rows[0][1] == "2024-02-29"
    out, _ = run([T("parse-dates", column="d", format="DD.MM.YYYY")], {"p": mk(["id", "d"], [t["p"].rows[1]])})
    assert out["p"].rows[0][1] == "2024-02-29"
    # "." is literal, not a wildcard
    with pytest.raises(TransformError):
        run([T("parse-dates", column="d", format="DD.MM.YYYY")], {"p": mk(["id", "d"], [["A", "29x02x2024"]])})


def test_parse_dates_format_missing_a_component_never_matches():
    t = {"p": mk(["id", "d"], [["A", "2023-04"]])}
    with pytest.raises(TransformError, match="row IDs: A"):
        run([T("parse-dates", column="d", format="YYYY-MM")], t)


def dates(*values):
    return {"p": mk(["id", "d"], [[f"R{i}", v] for i, v in enumerate(values, 1)])}


def parse(t, **kw):
    out, log = run([T("parse-dates", column="d", **kw)], t)
    return [r[1] for r in out["p"].rows], log[0]


def test_parse_dates_formats_list_converts_mixed_columns_and_passes_iso_through():
    t = dates("2024-07-07", "15/03/2024", "15/03/24", "2024/07-15", "")
    values, log = parse(t, formats=["DD/MM/YYYY", "DD/MM/YY", "YYYY/MM-DD"])
    assert values == ["2024-07-07", "2024-03-15", "2024-03-15", "2024-07-15", ""]
    assert log["cellsChanged"] == 3


def test_parse_dates_single_format_passes_valid_iso_through():
    values, log = parse(dates("2023-04-03", "05/06/2023"), format="DD/MM/YYYY")
    assert values == ["2023-04-03", "2023-06-05"]
    assert log["cellsChanged"] == 1


def test_parse_dates_yy_is_always_20yy():
    assert parse(dates("01/02/99", "01/02/00"), format="DD/MM/YY")[0] == ["2099-02-01", "2000-02-01"]


def test_parse_dates_unmatched_cells_name_every_format():
    with pytest.raises(TransformError) as e:
        parse(dates("15/03/2024", "March 2024", "2023-02-29"), formats=["DD/MM/YYYY", "DD/MM/YY"])
    assert str(e.value).endswith(
        'values in column "d" do not match any of the formats DD/MM/YYYY, DD/MM/YY '
        "and are not YYYY-MM-DD dates for row IDs: R2, R3"
    )


def test_parse_dates_cells_read_two_ways_are_ambiguous():
    # 03/04/23 is 3 April or 4 March; 13/04/23 fits only day-first; 04/04/23 reads the same either way
    with pytest.raises(TransformError) as e:
        parse(dates("03/04/23", "13/04/23", "04/04/23"), formats=["DD/MM/YY", "MM/DD/YY"])
    msg = str(e.value)
    assert "read as different dates under more than one format (counting YYYY-MM-DD) for row IDs: R1;" in msg
    assert "replace-cells" in msg and "R2" not in msg and "R3" not in msg


def test_parse_dates_iso_cell_another_format_reads_differently_is_ambiguous():
    with pytest.raises(TransformError, match=r"different dates .* row IDs: R1;"):
        parse(dates("2023-04-05", "2023-31-12"), format="YYYY-DD-MM")
    assert parse(dates("2023-05-05", "2023-31-12"), format="YYYY-DD-MM")[0] == ["2023-05-05", "2023-12-31"]


def test_parse_dates_reports_unmatched_and_ambiguous_together():
    with pytest.raises(TransformError) as e:
        parse(dates("03/04/23", "nope"), formats=["DD/MM/YY", "MM/DD/YY"])
    msg = str(e.value)
    assert "row IDs: R2" in msg and "row IDs: R1" in msg


def test_derive_column_then_replace_cells():
    out, _ = run([
        T("derive-column", column="age_80plus", **{"from": "age"}, map={"80+": "TRUE"}, default="FALSE"),
        T("replace-cells", column="age", cells=[{"id": "P1", "from": "80+", "to": "80"}]),
    ])
    assert out["p"].headers == ["id", "age", "note", "age_80plus"]
    assert [[r[1], r[3]] for r in out["p"].rows] == [["80", "TRUE"], ["5", "FALSE"], ["", "FALSE"]]
    with pytest.raises(TransformError, match="age"):
        run([T("derive-column", column="age", **{"from": "age"}, map={}, default="")])


def test_id_column_resolved_across_a_later_rename():
    t = {"p": mk(["pid", "age"], [["P1", "80+"]])}
    out, _ = run([
        T("replace-cells", column="age", cells=[{"id": "P1", "from": "80+", "to": "80"}]),
        T("rename-column", **{"from": "pid", "to": "id"}),
    ], t)
    assert out["p"].rows[0][1] == "80"
    assert out["p"].headers == ["id", "age"]


def test_missing_id_column_with_a_later_rename_cycle():
    t = {"p": mk(["age"], [["age1"]])}
    with pytest.raises(TransformError, match=r'ID column "pid" not found'):
        run([
            T("replace-cells", column="age", cells=[{"id": "P1", "from": "age1", "to": "80"}]),
            T("rename-column", **{"from": "x", "to": "pid"}),
            T("rename-column", **{"from": "pid", "to": "x"}),
        ], t, "pid")


def test_missing_id_column_with_a_later_noop_rename():
    t = {"p": mk(["age"], [["age1"]])}
    with pytest.raises(TransformError, match=r'ID column "pid" not found'):
        run([
            T("replace-cells", column="age", cells=[{"id": "P1", "from": "age1", "to": "80"}]),
            T("rename-column", **{"from": "pid", "to": "pid"}),
        ], t, "pid")
    t = {"p": mk([" age"], [["age1"]])}
    with pytest.raises(TransformError, match=r'transforms\[1\] \(rename-column\): column "pid" not found'):
        run([T("trim"), T("rename-column", **{"from": "pid", "to": "pid"})], t, "pid")


def test_inputs_are_not_mutated():
    t = tables()
    before = copy.deepcopy(t)
    out, _ = run([T("trim"), T("rename-column", **{"from": "age", "to": "y"}), T("drop-column", column="note")], t)
    assert t == before
    assert out["p"] is not t["p"]
    assert out["p"].file == "/data/p.csv" and out["p"].delimiter == ","


def test_user_value_changes_log_ids_auto_ones_log_only_counts():
    m = {"column": "note", "map": {"NA": ""}}
    user = run([T("map-values", **m)])[1][0]
    assert user["ids"] == ["P3"]
    assert user["cellsChanged"] == 1
    auto = run([T("map-values", **m, approval="auto")])[1][0]
    assert "ids" not in auto
    assert auto["cellsChanged"] == 1


def test_each_value_changing_op_logs_changed_row_ids_once_per_row_when_user_approved():
    assert run([T("trim")])[1][0]["ids"] == ["P1", "P2"]
    assert run([T("blank-placeholders", values=["NA"])])[1][0]["ids"] == ["P3"]
    dates = {"p": mk(["id", "d"], [["A", "2023-4-3"], ["B", ""], ["C", "2023-01-02"]])}
    assert run([T("parse-dates", column="d", format="YYYY-M-D")], dates)[1][0]["ids"] == ["A"]
    cells = [{"id": "P1", "from": "80+", "to": "80"}, {"id": "P2", "from": "5", "to": "5"}]
    assert run([T("replace-cells", column="age", cells=cells)])[1][0]["ids"] == ["P1"]


def test_ids_fall_back_to_row_numbers_without_id_column():
    log = run([T("trim")], None, "nope")[1][0]
    assert log["ids"] == ["row 1", "row 2"]


def test_empty_columns_list_means_no_columns():
    # JS treats [] as truthy: zero columns, so nothing changes
    out, log = run([T("trim", columns=[])])
    assert log[0]["cellsChanged"] == 0
    assert out["p"].rows[0][2] == " NA "


def test_map_values_does_not_match_inherited_names():
    t = {"p": mk(["id", "v"], [["A", "toString"], ["B", "__proto__"]])}
    out, log = run([T("map-values", column="v", map={})], t)
    assert log[0]["cellsChanged"] == 0
