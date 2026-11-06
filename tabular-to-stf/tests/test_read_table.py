import time

import pytest

from _read_table import Table, TableError, parse_delimited, read_table


def tmp_file(tmp_path, name, content):
    p = tmp_path / name
    p.write_bytes(content.encode("utf-8"))
    return p


def test_csv_quoting_commas_and_doubled_quotes():
    headers, rows = parse_delimited('h1,h2,h3\na,"b,c","d ""e"""\n', ",")
    assert headers == ["h1", "h2", "h3"]
    assert rows == [["a", "b,c", 'd "e"']]


def test_csv_quoted_field_with_embedded_newline_is_one_cell():
    _, rows = parse_delimited('a,b\n"x\ny",z\n', ",")
    assert rows == [["x\ny", "z"]]


def test_bom_and_crlf_no_cr_in_values_bom_not_in_first_header():
    headers, rows = parse_delimited("﻿id,v\r\n1,a\r\n2,b\r\n", ",")
    assert headers == ["id", "v"]
    assert rows == [["1", "a"], ["2", "b"]]
    h, r = parse_delimited("﻿id\tv\r\n1\ta\r\n", "\t")
    assert h == ["id", "v"]
    assert r == [["1", "a"]]


def test_ragged_csv_row_error_names_file_and_the_line_where_the_record_starts(tmp_path):
    p = tmp_file(tmp_path, "r.csv", 'a,b\n"x\ny",z\n1,2,3\n')
    with pytest.raises(TableError) as e:
        read_table(p)
    assert "r.csv" in str(e.value)
    assert "line 4:" in str(e.value)
    assert str(e.value) == "r.csv: line 4: expected 2 cells but found 3"


def test_ragged_tsv_row_error_has_line_number():
    with pytest.raises(TableError, match=r"line 2\b"):
        parse_delimited("a\tb\n1\n", "\t")


def test_tsv_keeps_literal_quotes_and_does_not_trim():
    _, rows = parse_delimited('a\tb\n"x\t y \n', "\t")
    assert rows == [['"x', " y "]]


def test_empty_cells_and_missing_trailing_newline():
    _, rows = parse_delimited("a,b,c\n1,,\n,2,3", ",")
    assert rows == [["1", "", ""], ["", "2", "3"]]


def test_all_empty_lines_at_eof_are_dropped_an_empty_line_mid_file_is_still_a_row():
    cases = [
        ("a,b\n1,2\n\n", ","), ("a,b\n1,2\n\n\n\n", ","), ("a,b\r\n1,2\r\n\r\n\r\n", ","),
        ("a\tb\n1\t2\n\n", "\t"), ("a\tb\n1\t2\n\n\n", "\t"), ("a\tb\r\n1\t2\r\n\r\n", "\t"),
    ]
    for text, d in cases:
        assert parse_delimited(text, d) == (["a", "b"], [["1", "2"]]), repr(text)
    with pytest.raises(TableError, match=r"line 2: expected 2 cells but found 1"):
        parse_delimited("a,b\n\n1,2\n", ",")
    with pytest.raises(TableError, match=r"line 2: expected 2 cells but found 1"):
        parse_delimited("a\tb\n\n1\t2\n", "\t")
    assert parse_delimited("a\n\nx\n\n", ",")[1] == [[""], ["x"]]
    assert parse_delimited('a,b\n1,"x\n\n"\n\n', ",")[1] == [["1", "x\n\n"]]


def test_delimiter_from_extension_else_sniffed_from_line_1(tmp_path):
    assert read_table(tmp_file(tmp_path, "a.csv", "a,b\n1,2\n")).delimiter == ","
    assert read_table(tmp_file(tmp_path, "a.tsv", "a\tb\n1\t2\n")).delimiter == "\t"
    assert read_table(tmp_file(tmp_path, "a.txt", "a\tb\n1\t2\n")).delimiter == "\t"
    assert read_table(tmp_file(tmp_path, "a.dat", "a,b,c\n1,2,3\n")).delimiter == ","
    assert read_table(tmp_file(tmp_path, "b.dat", "a\tb\tc,d\n1\t2\t3\n")).delimiter == "\t"
    t = read_table(tmp_file(tmp_path, "c.csv", "a,b\n1,2\n"))
    assert isinstance(t, Table)
    assert str(t.file).endswith("c.csv")


def test_read_table_strips_bom_and_keeps_crlf_out_of_values(tmp_path):
    p = tmp_path / "bom.csv"
    p.write_bytes("﻿id,v\r\n1,a\r\n".encode("utf-8"))
    t = read_table(p)
    assert t.headers == ["id", "v"]
    assert t.rows == [["1", "a"]]


def test_non_utf8_input_is_a_table_error_naming_the_file_and_line(tmp_path):
    p = tmp_path / "cp.csv"
    p.write_bytes("id,city\r\nS1,Paris\r\nS2,São Paulo\r\n".encode("cp1252"))
    with pytest.raises(TableError) as e:
        read_table(p)
    assert str(e.value) == ("cp.csv: line 3: not valid UTF-8; "
                            "re-save the file as UTF-8 (e.g. Excel's 'CSV UTF-8')")


def test_non_utf8_after_a_bom_counts_lines_from_the_start(tmp_path):
    p = tmp_path / "b.tsv"
    p.write_bytes(b"\xef\xbb\xbfid\n\xe3\n")
    with pytest.raises(TableError, match=r"^b\.tsv: line 2: not valid UTF-8"):
        read_table(p)


def test_unterminated_quote_throws():
    with pytest.raises(TableError, match=r"(?i)unterminated"):
        parse_delimited('a,b\n"x,y\n', ",")


def test_quote_followed_by_text_is_kept_literally():
    assert parse_delimited('a\n"a"b\n', ",")[1] == [["ab"]]


def test_large_input_parses_linearly():
    n = 300000
    lines = ["a,b,c"] + [f'{i},"v {i}",z' for i in range(n)]
    t0 = time.time()
    _, rows = parse_delimited("\n".join(lines), ",")
    assert len(rows) == n
    assert time.time() - t0 < 5
