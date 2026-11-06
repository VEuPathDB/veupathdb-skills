import json
import os

from conftest import FIXTURES, run_cli
from _constants import PLACEHOLDERS, UNAMBIGUOUS_PLACEHOLDERS
from _profile import profile_tables, truncate_value
from _read_table import Table, parse_delimited
from stf import build_parser


def table(file, csv):
    headers, rows = parse_delimited(csv, ",", file)
    return Table(file=f"/data/{file}", delimiter=",", headers=headers, rows=rows)


village = table("village.csv", "village_id,name\nV1,Alpha\nV2,Beta\n")
household = table("household.csv", "household_id,village_id\nH1,V1\nH2,V1\nH3,V2\n")
participant = table("participant.csv", "\n".join([
    "participant_id,household_id,age,code,consent,note",
    "P1,H1,34,007,y,NA",
    "P2,H1,80+,012,Yes,ok",
    "P3,H2,5,345,yes ,NA",
    "P4,H3,61,678,y,",
]) + "\n")

profile = profile_tables([village, household, participant])


def col(file, header):
    f = next(f for f in profile["files"] if f["file"] == file)
    return next(c for c in f["columns"] if c["header"] == header)


def test_file_entries_carry_basename_delimiter_row_count_headers_and_sample_rows():
    p = next(f for f in profile["files"] if f["file"] == "participant.csv")
    assert p["delimiter"] == ","
    assert p["rowCount"] == 4
    assert p["headers"][0] == "participant_id"
    assert len(p["sampleRows"]) == 4
    assert len(profile_tables([participant], sample_rows=2)["files"][0]["sampleRows"]) == 2


def test_key_order_matches_the_js_output():
    assert list(profile) == ["files", "parentLinks"]
    f = profile["files"][0]
    assert list(f) == ["file", "delimiter", "rowCount", "headers", "sampleRows", "columns"]
    assert list(col("participant.csv", "age")) == [
        "header", "distinctCount", "top", "inferred", "isCandidateId", "leadingZeros",
        "whitespaceCells", "placeholderCells", "nearDuplicates", "nearDuplicateCount"]
    assert list(col("village.csv", "village_id")) == [
        "header", "distinctCount", "top", "inferred", "isCandidateId", "leadingZeros",
        "whitespaceCells", "placeholderCells", "nearDuplicates", "nearDuplicateCount"]


def test_parent_link_household_village_id_to_village_village_id():
    links = profile["parentLinks"]
    assert {"file": "household.csv", "column": "village_id", "refFile": "village.csv", "refColumn": "village_id"} in links
    assert {"file": "participant.csv", "column": "household_id", "refFile": "household.csv", "refColumn": "household_id"} in links
    # a file's only candidate ID is not a link
    assert not any(l["file"] == "village.csv" and l["column"] == "village_id" for l in links)


def test_ids_are_flagged_as_candidates():
    assert col("village.csv", "village_id")["isCandidateId"] is True
    assert col("participant.csv", "participant_id")["isCandidateId"] is True
    assert col("household.csv", "village_id")["isCandidateId"] is False
    assert col("participant.csv", "note")["isCandidateId"] is False


def test_y_yes_yes_space_give_a_near_duplicate_pair_and_a_whitespace_count():
    c = col("participant.csv", "consent")
    assert c["nearDuplicates"] == [["Yes", "yes "]]
    assert c["nearDuplicateCount"] == 1
    assert c["whitespaceCells"] == 1


def test_80plus_makes_age_a_string_and_appears_in_top():
    c = col("participant.csv", "age")
    assert c["inferred"]["data_type"] == "string"
    assert any(t["value"] == "80+" for t in c["top"])
    assert "min" not in c


def test_leading_zero_codes_are_flagged():
    assert col("participant.csv", "code")["leadingZeros"] is True
    assert col("participant.csv", "age")["leadingZeros"] is False


def test_placeholders_are_counted():
    assert col("participant.csv", "note")["placeholderCells"] == {"NA": 2}


def test_top_is_capped_at_top_n_while_distinct_count_stays_exact():
    rows = ["v"]
    for i in range(30):
        rows += [f"x{i}", f"x{i}"]
    rows.append("x0")
    p = profile_tables([table("t.csv", "\n".join(rows) + "\n")], top_n=5)
    c = p["files"][0]["columns"][0]
    assert len(c["top"]) == 5
    assert c["distinctCount"] == 30
    assert c["top"][0] == {"value": "x0", "count": 3}
    assert c["top"][1] == {"value": "x1", "count": 2}


def test_min_max_for_numbers_and_iso_dates_only():
    t = table("t.csv", "n,d,s\n3,2020-05-01,a\n-1.5,2019-01-02,b\n10,2021-12-31,c\n")
    n, d, s = profile_tables([t])["files"][0]["columns"]
    assert n["inferred"]["data_type"] == "number"
    assert n["min"] == -1.5
    assert n["max"] == 10
    assert d["min"] == "2019-01-02"
    assert d["max"] == "2021-12-31"
    assert "min" not in s


def test_min_max_serialise_like_js_numbers():
    t = table("t.csv", "i,n,big,huge\n3,3.0,1e20,1e21\n-7,2.50,2,2\n")
    i, n, big, huge = profile_tables([t])["files"][0]["columns"]
    text = json.dumps([i["min"], i["max"], n["min"], n["max"], big["max"], huge["max"]])
    # JS prints 1e20 in full and 1e21 in exponent form
    assert text == "[-7, 3, 2.5, 3, 100000000000000000000, 1e+21]"
    assert isinstance(i["min"], int) and isinstance(n["max"], int)


def test_levenshtein_near_duplicates_need_both_values_of_5_plus_chars():
    t = table("t.csv", "v\nmalaria\nmalarla\ncat\ncot\ncat\n")
    assert profile_tables([t])["files"][0]["columns"][0]["nearDuplicates"] == [["malaria", "malarla"]]


def test_empty_cells_block_candidate_ids_short_rows_read_as_empty():
    t = table("t.csv", "a,b\n1,x\n2,\n")
    a, b = profile_tables([t])["files"][0]["columns"]
    assert a["isCandidateId"] is True
    assert b["isCandidateId"] is False


def test_placeholder_lists():
    assert all(p in PLACEHOLDERS for p in UNAMBIGUOUS_PLACEHOLDERS)
    assert "not done" in PLACEHOLDERS
    assert "unknown" not in UNAMBIGUOUS_PLACEHOLDERS


def test_profile_tables_cli_prints_json_for_a_directory(tmp_path):
    (tmp_path / "a.csv").write_text("id,x\n1,a\n2,b\n")
    (tmp_path / "ignore.md").write_text("nope")
    r = run_cli("profile", str(tmp_path), "--top", "1")
    assert r.returncode == 0
    p = json.loads(r.stdout)
    assert len(p["files"]) == 1
    assert p["files"][0]["file"] == "a.csv"
    assert len(p["files"][0]["columns"][1]["top"]) == 1


def test_profile_tables_cli_errors_on_a_missing_directory():
    r = run_cli("profile", "/no/such/dir")
    assert r.returncode == 1
    assert "Error: Not a directory: /no/such/dir" in r.stderr


def test_one_stray_non_numeric_value_late_in_a_column_makes_it_a_string():
    rows = ["v"] + [str(i + 1) for i in range(2000)] + ["80+"]
    c = profile_tables([table("t.csv", "\n".join(rows) + "\n")])["files"][0]["columns"][0]
    assert c["inferred"]["data_type"] == "string"


def test_near_duplicates_is_capped_at_top_n_and_count_stays_true():
    rows = ["v"]
    for i in range(200):
        rows += [f"sample{i:03d}", f"sample{i:03d}"]
    c = profile_tables([table("t.csv", "\n".join(rows) + "\n")], top_n=20)["files"][0]["columns"][0]
    assert len(c["nearDuplicates"]) == 20
    assert c["nearDuplicateCount"] > 20
    assert c["nearDuplicates"][0] == ["sample000", "sample001"]


def test_normalised_equal_pairs_come_before_levenshtein_pairs():
    t = table("t.csv", "v\nmalaria\nmalarla\nYes\nyes\nYes\n")
    c = profile_tables([t])["files"][0]["columns"][0]
    assert c["nearDuplicates"] == [["Yes", "yes"], ["malaria", "malarla"]]


def test_candidate_id_columns_get_no_near_duplicates():
    rows = ["id"] + [f"sample{i:03d}" for i in range(50)]
    c = profile_tables([table("t.csv", "\n".join(rows) + "\n")])["files"][0]["columns"][0]
    assert c["isCandidateId"] is True
    assert c["nearDuplicates"] == []
    assert c["nearDuplicateCount"] == 0


def test_no_parent_link_when_a_value_is_missing_from_the_target_id():
    g = table("g.csv", "id\nA\nB\nC\n")
    f = table("f.csv", "fid,gid\n1,A\n2,B\n3,Z\n")
    assert profile_tables([g, f])["parentLinks"] == []


def test_a_non_id_column_whose_values_fit_another_id_column_still_links_after_pruning():
    g = table("g.csv", "id\nA\nB\n")
    f = table("f.csv", "fid,gid\n1,A\n2,B\n3,A\n")
    assert profile_tables([g, f])["parentLinks"] == [
        {"file": "f.csv", "column": "gid", "refFile": "g.csv", "refColumn": "id"}]


def test_a_column_with_blank_cells_still_links_when_its_non_empty_values_fit_the_target_id():
    g = table("g.csv", "id\nA\nB\n")
    f = table("f.csv", "fid,gid\n1,A\n2,B\n3,\n")
    assert profile_tables([g, f])["parentLinks"] == [
        {"file": "f.csv", "column": "gid", "refFile": "g.csv", "refColumn": "id"}]


def test_values_over_80_chars_are_cut_in_top_sample_rows_and_near_duplicates():
    long = "x" * 100
    cut = "x" * 80 + "…[+20 chars]"
    cut_upper = "X" * 80 + "…[+20 chars]"
    assert truncate_value(long) == cut
    assert truncate_value("x" * 80) == "x" * 80
    t = table("long.csv", f"id,text\n1,{long}\n2,{long.upper()}\n3,{long}\n")
    f = profile_tables([t])["files"][0]
    c = f["columns"][1]
    assert [x["value"] for x in c["top"]] == [cut, cut_upper]
    assert f["sampleRows"][0][1] == cut
    assert c["nearDuplicates"] == [[cut_upper, cut]]
    assert c["distinctCount"] == 2


def linked_dir(tmp_path):
    (tmp_path / "village.csv").write_text("village_id,name\nV1,Alpha\nV2,Beta\nV3,Gamma\n")
    (tmp_path / "household.csv").write_text("household_id,village_id\nH1,V1\nH2,V2\nH3,V2\n")
    (tmp_path / "person.csv").write_text("person_id,household_id\nP1,H1\nP2,H2\n")
    return tmp_path


def test_profile_tables_cli_prints_compact_json(tmp_path):
    r = run_cli("profile", str(linked_dir(tmp_path)))
    assert len(r.stdout.strip().split("\n")) == 1
    assert r.stdout.startswith('{"files":[{"file":')
    assert len(json.loads(r.stdout)["files"]) == 3


def test_profile_tables_cli_file_keeps_one_file_and_the_links_involving_it(tmp_path):
    d = str(linked_dir(tmp_path))
    p = json.loads(run_cli("profile", d, "--file", "household.csv").stdout)
    assert [f["file"] for f in p["files"]] == ["household.csv"]
    assert sorted(f"{l['file']}.{l['column']}->{l['refFile']}" for l in p["parentLinks"]) == [
        "household.csv.village_id->village.csv", "person.csv.household_id->household.csv"]
    v = json.loads(run_cli("profile", d, "--file", "village.csv").stdout)
    assert [l["file"] for l in v["parentLinks"]] == ["household.csv"]
    r = run_cli("profile", d, "--file", "nope.csv")
    assert r.returncode == 1
    assert "--file nope.csv: no such table" in r.stderr


def test_profile_tables_cli_out_writes_full_profile_and_prints_a_summary_per_file(tmp_path):
    import re
    (tmp_path / "in").mkdir()
    d = linked_dir(tmp_path / "in")
    before = {f.name: f.read_text() for f in d.iterdir()}
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out_path = out_dir / "profile.json"
    r = run_cli("profile", str(d), "--out", str(out_path))
    assert r.returncode == 0
    text = out_path.read_text(encoding="utf-8")
    assert len(text.strip().split("\n")) == 1
    assert json.loads(text) == json.loads(run_cli("profile", str(d)).stdout)
    assert re.search(r"^household\.csv: 3 rows, 2 columns, \d+\.\d KB$", r.stdout, re.M)
    assert re.search(r"^person\.csv: 2 rows, 2 columns, ", r.stdout, re.M)
    assert re.search(r"^parentLinks: 2$", r.stdout, re.M)
    assert re.search(r"^Wrote .*profile\.json \(\d+\.\d KB\); read one file at a time with --file <name>$", r.stdout, re.M)
    assert '"columns"' not in r.stdout
    assert {f.name: f.read_text() for f in d.iterdir()} == before
    bad = run_cli("profile", str(d), "--out", str(d / "p.json"))
    assert bad.returncode == 1
    assert "must not be in the input directory" in bad.stderr


def test_profile_rejects_bad_top_and_empty_directories(tmp_path):
    r = run_cli("profile", str(tmp_path), "--top", "0")
    assert r.returncode == 1 and '--top must be a positive integer, got "0"' in r.stderr
    r = run_cli("profile", str(tmp_path))
    assert r.returncode == 1 and "No .csv/.tsv/.txt files in" in r.stderr
    r = run_cli("profile")
    assert r.returncode == 1 and "Error: Usage: stf.py profile <inputDir>" in r.stderr


def test_profile_of_a_non_utf8_file_exits_1_naming_the_file(tmp_path):
    (tmp_path / "sites.csv").write_bytes("site_id,city\nS1,São Paulo\n".encode("cp1252"))
    r = run_cli("profile", str(tmp_path))
    assert r.returncode == 1
    assert r.stderr.startswith("Error: sites.csv: line 2: not valid UTF-8;"), r.stderr
    assert "Traceback" not in r.stderr


def test_clinical_epi_compact_file_participants_is_well_under_20_kb():
    r = run_cli("profile", str(FIXTURES / "tabular/clinical-epi/inputs"), "--file", "participants.csv")
    assert r.returncode == 0, r.stderr
    assert len(r.stdout.encode("utf-8")) < 20 * 1024


def test_profile_prints_non_ascii_on_a_cp1252_console(tmp_path):
    (tmp_path / "sites.csv").write_text("site_id,city\nS1,São Paulo\n", encoding="utf-8")
    r = run_cli("profile", str(tmp_path), env={**os.environ, "PYTHONIOENCODING": "cp1252"})
    assert r.returncode == 0 and "São Paulo" in r.stdout


def test_build_parser_has_a_required_profile_subcommand():
    parser = build_parser()
    args = parser.parse_args(["profile", "d", "--top", "3", "--file", "a.csv", "--out", "o.json"])
    assert args.command == "profile"
    assert (args.top, args.file, args.out) == ("3", "a.csv", "o.json")
