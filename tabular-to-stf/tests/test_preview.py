import json

import pytest
from conftest import run_cli

from _preview import preview_transform
from _read_table import Table
from _transforms import TransformError


def T(op, approval="user", **extra):
    return {"op": op, "entity": "p", "reason": "r", "approval": approval, **extra}


def spec(*transforms):
    return {
        "specVersion": "1.1.0",
        "study": {"name": "S"},
        "inputDir": "in",
        "entities": [{"name": "p", "displayName": "P", "displayNamePlural": "Ps", "file": "p.csv",
                      "idColumn": "id", "variables": []}],
        "transforms": list(transforms),
    }


def mk(headers, rows):
    return Table(file="p.csv", delimiter=",", headers=headers, rows=[list(r) for r in rows])


def ages(*values):
    return mk(["id", "age"], [[f"P{i + 1}", v] for i, v in enumerate(values)])


STRIP = T("map-values", approval="proposed", column="age", match="regex", map={r"(\d+)\?": "$1"})


def test_matched_ambiguous_unmatched_sections():
    text = preview_transform(spec(STRIP), ages("40?", "40?", "40?", "35?", "35?", "35", "35", "x", ""), 0)
    lines = text.split("\n")
    assert lines[0] == 'transforms[0] map-values on entity "p", match regex, approval proposed'
    assert 'Column "age"' in lines
    assert "Matched: 2 distinct values, 5 cells" in lines
    assert '  "40?" → "40"  ×3  (key "(\\\\d+)\\\\?")' in lines
    assert "Ambiguous: none" in lines
    assert "Unmatched: 2 distinct values, 3 cells; 1 empty cell" in lines
    assert '  "35"  ×2' in lines


def test_proposed_transform_is_previewed_and_earlier_proposed_ones_are_not_applied():
    s = spec(T("map-values", approval="proposed", column="age", map={"40?": "zzz"}), STRIP)
    text = preview_transform(s, ages("40?"), 1)
    assert '  "40?" → "40"  ×1  (key "(\\\\d+)\\\\?")' in text


def test_earlier_rename_is_applied_before_preview():
    s = spec(T("rename-column", **{"from": "age", "to": "years"}),
             T("map-values", column="years", match="regex", map={r"~(\d+)": "$1"}))
    text = preview_transform(s, ages("~3"), 1)
    assert 'Column "years"' in text
    assert '  "~3" → "3"  ×1  (key "~(\\\\d+)")' in text


def test_earlier_transform_failure_raises():
    s = spec(T("drop-column", column="nope"), STRIP)
    with pytest.raises(TransformError, match='column "nope" not found'):
        preview_transform(s, ages("1"), 1)


def test_top_and_bottom_cap_with_totals():
    values = [f"v{i:02d}" for i in range(30) for _ in range(30 - i)]  # v00 ×30 … v29 ×1
    text = preview_transform(spec(STRIP), ages(*values), 0, top=2, bottom=2)
    lines = text.split("\n")
    shown = [l for l in lines if l.startswith('  "v')]
    assert shown == ['  "v00"  ×30', '  "v01"  ×29', '  "v28"  ×2', '  "v29"  ×1']
    assert "  … 26 more distinct values (" in text
    hidden_cells = sum(30 - i for i in range(2, 28))
    assert f"  … 26 more distinct values ({hidden_cells:,} cells)" in lines


def test_top_and_bottom_do_not_repeat_values():
    text = preview_transform(spec(STRIP), ages("a", "b", "b"), 0, top=2, bottom=2)
    assert [l for l in text.split("\n") if l.startswith('  "')] == ['  "b"  ×2', '  "a"  ×1']
    assert "more distinct" not in text


def test_unmatched_empty_cells_are_counted_not_listed():
    text = preview_transform(spec(STRIP), ages("", "", "1?"), 0)
    assert "Unmatched: 0 distinct values, 0 cells; 2 empty cells" in text
    assert '  ""' not in text


def test_matched_empty_cells_are_listed():
    s = spec(T("map-values", column="age", match="regex", map={".*": "x"}))
    assert '  "" → "x"  ×2  (key ".*")' in preview_transform(s, ages("", ""), 0)


def test_ambiguous_values_are_listed_uncapped():
    s = spec(T("map-values", column="age", match="regex", map={r"(.*)\?": "$1", r"\d+\?": "b"}))
    text = preview_transform(s, ages(*[f"{i}?" for i in range(15)]), 0, top=1, bottom=1)
    assert "Ambiguous: 15 distinct values, 15 cells" in text
    assert '  "3?"  ×1  keys "(.*)\\\\?" → "3", "\\\\d+\\\\?" → "b"' in text
    assert sum(1 for l in text.split("\n") if "  keys " in l) == 15


def test_exact_mode_has_no_key_column():
    s = spec(T("map-values", column="age", map={"y": "Yes"}))
    text = preview_transform(s, ages("y"), 0)
    assert text.split("\n")[0] == 'transforms[0] map-values on entity "p", match exact, approval user'
    assert '  "y" → "Yes"  ×1' in text.split("\n")


def test_derive_column_shows_default_for_unmatched():
    s = spec(T("derive-column", column="u", match="regex", map={r"~.*": "Yes"}, default="No", **{"from": "age"}))
    text = preview_transform(s, ages("~3", "35", "35"), 0)
    assert '  "35" → "No" (default)  ×2' in text.split("\n")


def test_blank_placeholders_prints_one_section_per_column():
    t = mk(["id", "a", "b"], [["1", "NA", "x"], ["2", "n/a", "NA"]])
    s = spec(T("blank-placeholders", match="regex", values=["(?i)n/?a"], columns=["a", "b"]))
    text = preview_transform(s, t, 0)
    assert 'Column "a"' in text and 'Column "b"' in text
    assert text.index('Column "a"') < text.index('Column "b"')


def test_non_value_op_summary():
    text = preview_transform(spec(T("drop-column", column="age")), ages("1"), 0)
    assert text.split("\n")[0] == 'transforms[0] drop-column on entity "p", approval user'
    assert "Cells changed: 0" in text
    assert "Columns: id, age → id" in text


def test_non_value_op_own_failure_is_shown_not_raised():
    s = spec(T("parse-dates", column="age", format="DD/MM/YYYY"))
    text = preview_transform(s, ages("nope"), 0)
    assert "This transform fails: " in text
    assert "P1" in text


# ---- CLI ----

def write(tmp_path, s, rows=(("P1", "40?"), ("P2", "35"))):
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "p.csv").write_text("id,age\n" + "".join(f"{a},{b}\n" for a, b in rows), encoding="utf-8")
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(s), encoding="utf-8")
    return path


def test_cli_preview_prints_the_preview(tmp_path):
    r = run_cli("preview", str(write(tmp_path, spec(STRIP))), "0", "--top", "5", "--bottom", "5")
    assert r.returncode == 0, r.stderr
    assert '  "40?" → "40"  ×1  (key "(\\\\d+)\\\\?")' in r.stdout


def test_preview_works_on_a_skeleton_spec(tmp_path):
    r = run_cli("preview", str(write(tmp_path, spec(STRIP))), "0")
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("n, message", [
    ("1", 'Error: <n> must be a transform index from 0 to 0, got "1"'),
    ("-1", 'Error: <n> must be a transform index from 0 to 0, got "-1"'),
    ("x", 'Error: <n> must be a transform index from 0 to 0, got "x"'),
])
def test_cli_preview_bad_index(tmp_path, n, message):
    r = run_cli("preview", str(write(tmp_path, spec(STRIP))), n)
    assert r.returncode == 1
    assert message in r.stderr


def test_cli_preview_spec_without_transforms(tmp_path):
    r = run_cli("preview", str(write(tmp_path, spec())), "0")
    assert r.returncode == 1
    assert "Error: the spec has no transforms" in r.stderr


def test_cli_preview_invalid_spec(tmp_path):
    s = spec(STRIP)
    s["specVersion"] = 1
    r = run_cli("preview", str(write(tmp_path, s)), "0")
    assert r.returncode == 1
    assert "Error: the spec is not valid:" in r.stderr
    assert '- specVersion: must be a version string like "1.1.0"' in r.stderr


def test_cli_preview_earlier_transform_fails(tmp_path):
    r = run_cli("preview", str(write(tmp_path, spec(T("drop-column", column="nope"), STRIP))), "1")
    assert r.returncode == 1
    assert "Error: an earlier transform fails: " in r.stderr


def test_cli_preview_shows_ambiguity_with_exit_0(tmp_path):
    s = spec(T("map-values", column="age", match="regex", map={r"(.*)\?": "$1", r"\d+\?": "b"}))
    r = run_cli("preview", str(write(tmp_path, s)), "0")
    assert r.returncode == 0, r.stderr
    assert "Ambiguous: 1 distinct value, 1 cell" in r.stdout
