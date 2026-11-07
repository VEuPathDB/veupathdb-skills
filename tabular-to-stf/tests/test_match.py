import pytest

from _match import TemplateError, ValueMatcher, parse_template, template_groups


def test_parse_template_groups_dollar_dollar_and_multidigit():
    assert parse_template("a$1b$$c$10") == ["a", 1, "b$c", 10]
    assert template_groups(parse_template("$2-$1")) == {1, 2}


@pytest.mark.parametrize("bad", ["$", "x$", "$a", "$-1"])
def test_parse_template_rejects_stray_dollar(bad):
    with pytest.raises(TemplateError):
        parse_template(bad)


def test_regex_is_whole_cell():
    m = ValueMatcher({r"\d+": "n"}, regex=True)
    assert m.hits("40?") == []
    assert m.hits("40") == [(r"\d+", "n")]
    assert ValueMatcher({"a|ab": "x"}, regex=True).hits("ab") == [("a|ab", "x")]


def test_regex_capture_references():
    m = ValueMatcher({r"(\d+)\?": "$1", r"~(\d+)": "$1", r"(a)?b": "[$1]"}, regex=True)
    assert m.hits("40?") == [(r"(\d+)\?", "40")]
    assert m.hits("~35") == [(r"~(\d+)", "35")]
    assert m.hits("b") == [(r"(a)?b", "[]")]


def test_backslashes_in_a_replacement_stay_literal():
    assert ValueMatcher({r"(\d)": "x\\1\\n"}, regex=True).hits("4") == [(r"(\d)", "x\\1\\n")]


def test_exact_mode_values_are_literal():
    assert ValueMatcher({"80+": "$80"}, regex=False).hits("80+") == [("80+", "$80")]
    assert ValueMatcher({"a.": "x"}, regex=False).hits("ab") == []


def test_empty_cell_is_matched_like_any_value():
    assert ValueMatcher({".*": "x"}, regex=True).hits("") == [(".*", "x")]


def test_ambiguity_only_when_results_differ():
    m = ValueMatcher({r"~.*": "Yes", r".*\?": "Yes", r"\d+\?": "No"}, regex=True)
    assert not ValueMatcher.is_ambiguous(m.hits("~3"))
    assert not ValueMatcher.is_ambiguous(m.hits("~x?"))
    assert ValueMatcher.is_ambiguous(m.hits("3?"))
