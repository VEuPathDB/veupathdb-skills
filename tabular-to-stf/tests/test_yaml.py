import json

import pytest
from conftest import FIXTURES

from _yaml import YamlError, dump_yaml, load_stf_yaml, needs_quoting, yaml11_resolves


def parse(text):
    return load_stf_yaml(text)[0]


# ---- ported from tests/tabular-yaml-lite.test.js ----

def test_parses_the_sample_annotations_to_stf_golden_entity_yaml():
    doc = parse((FIXTURES / "stf/entity-sample.yaml").read_text(encoding="utf-8"))
    assert doc["name"] == "sample"
    assert doc["display_name_plural"] == "Samples"
    assert doc["id_columns"] == [{"id_column": "sample.ID", "entity_name": "sample", "provider_label": ["sample ID"]}]
    assert len(doc["variables"]) == 3
    assert doc["variables"][0]["variable"] == "SRA.ID.s."
    assert doc["variables"][0]["is_multi_valued"] == "yes"  # yes stays a string
    assert doc["variables"][0]["multi_value_delimiter"] == ","
    assert doc["variables"][2]["definition"] == "Growth condition before RNA extraction"
    assert doc["categories"] == []
    assert doc["collections"] == []


# Examples copied from study-wrangler v1.0.53 STF_documentation
def test_parses_stf_docs_household_entity_and_observation_entity():
    hh = parse("""name: household
display_name: Household
display_name_plural: Households

id_columns:
  - id_column: Household.Id
    entity_name: household

variables:
  - variable: Number.of.animals
    display_name: Number of animals
    data_type: integer
    data_shape: continuous

  - variable: Enrollment.date
    display_name: Enrollment date
    data_type: date
    data_shape: continuous
""")
    assert hh["variables"][1]["variable"] == "Enrollment.date"
    assert hh["id_columns"] == [{"id_column": "Household.Id", "entity_name": "household"}]

    obs = parse("""name: observation
display_name: observation
display_name_plural: observations

id_columns:
  - id_column: Household.Id
    entity_name: household
    entity_level: -2
  - id_column: Participant.Id
    entity_name: participant
    entity_level: -1
  - id_column: Part..Obs..Id
    entity_name: observation

variables:
  - variable: Observation.date
    provider_label:
      - Observation date
    data_type: date
    data_shape: continuous
# more variables not shown
""")
    assert obs["id_columns"][0]["entity_level"] == -2
    assert obs["variables"][0]["provider_label"] == ["Observation date"]


def test_parses_stf_docs_study_yaml_and_categories_collections():
    assert parse("""name: My Awesome Study
entities:
  - household
  - participant
  - observation
""") == {"name": "My Awesome Study", "entities": ["household", "participant", "observation"]}

    c = parse("""categories:
  - category: integer.measures
    display_name: Anthropometric measurements

collections:
  - category: integer.measures
    display_name: Anthropometric measurements
    member: measurement
    member_plural: measurements
    is_proportion: false
    is_compositional: false
    normalization_method: none
""")
    assert c["categories"][0]["category"] == "integer.measures"
    assert c["collections"][0]["is_proportion"] is False
    assert c["collections"][0]["normalization_method"] == "none"


def test_parses_stf_docs_site_entity_with_stable_id_and_display_type():
    s = parse("""name: site
display_name: Site
display_name_plural: Sites

id_columns:
  - id_column: Site.Id
    entity_name: site

variables:
  - variable: Latitude
    display_name: Latitude
    stable_id: OBI_0001620
    data_type: number
    data_shape: continuous
    display_type: latitude
""")
    assert s["variables"][0]["stable_id"] == "OBI_0001620"


def test_parses_stf_docs_participant_entity_with_categories_ordinal_levels_hidden_multi_valued():
    p = parse("""name: participant
display_name: Participant
display_name_plural: Participants
description: People enrolled in the study, one row per person.

id_columns:
  - id_column: Household.Id
    entity_name: household
    entity_level: -1
  - id_column: Participant.Id
    entity_name: participant

variables:
  - variable: Name
    display_name: Full name
    data_type: string
    data_shape: categorical
    hidden:
      - everywhere

  - variable: Hemoglobin
    display_name: Hemoglobin
    data_type: number
    data_shape: continuous
    unit: g/dL
    display_range_min: '0'
    display_range_max: '20'
    bin_width_override: '0.5'

  - variable: Education
    display_name: Highest education level
    data_type: string
    data_shape: ordinal
    ordinal_levels:
      - none
      - primary
      - secondary
      - tertiary
    parent_category: demographics

  - variable: Symptoms
    display_name: Symptoms reported
    data_type: string
    data_shape: categorical
    is_multi_valued: true
    multi_value_delimiter: ';'

categories:
  - category: demographics
    display_name: Demographics
    display_order: 1

  - category: anthropometry
    display_name: Anthropometry
    definition: Body measurements.
    parent_category: clinical
    display_order: 1
""")
    assert p["description"] == "People enrolled in the study, one row per person."
    assert p["variables"][0]["hidden"] == ["everywhere"]
    assert p["variables"][1]["display_range_max"] == "20"  # quoted stays a string
    assert p["variables"][1]["unit"] == "g/dL"
    assert p["variables"][2]["ordinal_levels"] == ["none", "primary", "secondary", "tertiary"]
    assert p["variables"][3]["is_multi_valued"] is True
    assert p["variables"][3]["multi_value_delimiter"] == ";"
    assert p["categories"][0]["display_order"] == 1
    assert p["categories"][1]["parent_category"] == "clinical"


def test_scalar_resolution():
    d = parse("""a: 12
b: -3
c: 1.5
d: True
e: FALSE
f: null
g: ~
h:
i: yes
j: no
k: on
l: 007x
m: '12'
n: "true"
""")
    assert d == {"a": 12, "b": -3, "c": 1.5, "d": True, "e": False, "f": None, "g": None, "h": None,
                 "i": "yes", "j": "no", "k": "on", "l": "007x", "m": "12", "n": "true"}


def test_quoting_and_escapes():
    d = parse("""a: 'it''s'
b: "say \\"hi\\"\\\\ \\n\\tend"
c: "a: b"
"quoted key": v
""")
    assert d["a"] == "it's"
    assert d["b"] == 'say "hi"\\ \n\tend'
    assert d["c"] == "a: b"
    assert d["quoted key"] == "v"


def test_flow_sequences_and_empty_flow_mapping():
    d = parse("""a: []
b: [x, 'b c', "d, e", 3]
c: {}
d: [ ]
""")
    assert d == {"a": [], "b": ["x", "b c", "d, e", 3], "c": {}, "d": []}


def test_block_scalars():
    d = parse("""lit: |
  line one
  line two

keep: |-
  no newline
fold: >
  folded
  text

  para two
foldstrip: >-
  a
  b
after: x
""")
    assert d["lit"] == "line one\nline two\n"
    assert d["keep"] == "no newline"
    assert d["fold"] == "folded text\npara two\n"
    assert d["foldstrip"] == "a b"
    assert d["after"] == "x"


def test_block_scalar_inside_a_sequence_of_mappings_keeps_hash_as_text():
    d = parse("""variables:
  - variable: a
    definition: |
      # not a comment
      second
  - variable: b
""")
    assert d["variables"][0]["definition"] == "# not a comment\nsecond\n"
    assert d["variables"][1]["variable"] == "b"


def test_comments_full_line_and_trailing():
    d = parse("""# header
a: 1 # trailing
b: 'x # not a comment' # but this is
c: a#b
list:
  # inside
  - x # c
  - y
""")
    assert d == {"a": 1, "b": "x # not a comment", "c": "a#b", "list": ["x", "y"]}


def test_sequence_at_the_same_indent_as_its_key_nested_sequences_crlf_bom_leading_doc_start():
    assert parse("k:\n- a\n- b: 1\n  c: 2\nz: 3\n") == {"k": ["a", {"b": 1, "c": 2}], "z": 3}
    assert parse("- - a\n  - b\n- c\n") == [["a", "b"], "c"]
    assert parse("\ufeffa: 1\r\nb: x\r\n") == {"a": 1, "b": "x"}
    assert parse("---\na: 1\n") == {"a": 1}
    assert parse("") is None


@pytest.mark.parametrize("text,line", [
    ("a: 1\nb: &x 2\n", 2),
    ("a: 1\nb: *x\n", 2),
    ("a: 1\nb: !!str 2\n", 2),
    ("a: 1\n---\nb: 2\n", 2),
    ("a: 1\nb: {x: 1}\n", 2),
    ("a: 1\nb: [a, [b]]\n", 2),
    ("a: 1\nb: [a,\n  b]\n", 2),
    ("a: 1\nb: \"unterminated\n", 2),
    ("a: 1\nb: \"bad \\q\"\n", 2),
    ("a: 1\n\tb: 2\n", 2),
    ("a: 1\n  b: 2\n", 2),
    ("- &x a\n", 1),
])
def test_unsupported_constructs_throw_yaml_error_with_the_line(text, line):
    with pytest.raises(YamlError) as e:
        load_stf_yaml(text)
    assert e.value.line == line, json.dumps(text)
    assert str(e.value).startswith(f"line {line}: ")


ROUND_TRIP = ["yes", "no", "on", "off", "null", "Null", "~", "true", "False", "1.0", "007", "12", "-3", ".5",
              "a: b", "a:", "#x", "-x", "- x", "- ", "x #y", "it's", "", " lead", "trail ", "[a]", "{a}", "&a", "*a", "!t",
              "%x", "@x", "`x", "|", ">", "?", ",x", "'q'", '"q"', "line1\nline2", "a\tb", 'say "hi"\nnext', "cr\r\nlf\\",
              "plain", "a,b", "p#q", "http://x/y",
              "0x1F", "0o17", "0b101", ".inf", "-.Inf", ".NaN", "1.", "1e3", "1_000", "1:30"]


@pytest.mark.parametrize("s", ROUND_TRIP)
def test_round_trip_dump_yaml_output_parses_back_to_the_same_string(s):
    out = dump_yaml({"k": s})
    assert parse(out)["k"] == s, f"value {json.dumps(s)} via {json.dumps(out)}"


# ---- ported from the yamlScalar test in tests/tabular-stf-common.test.js ----

def test_needs_quoting_yaml_11_booleans_numbers_and_multi_line_text():
    for s in ["on", "OFF", "y", "N", "yes", "null", "1.0", "a: b", "#x", "-x", "+5", ".5"]:
        assert needs_quoting(s), s
    for s in ["0x1F", "0X1f", "0o17", "0b101", ".inf", "-.Inf", "+.INF", ".NaN", "1.", "1e3", "1E-3", "1.5e+3",
              "1_000", "1:30", "-1:30:05.5"]:
        assert needs_quoting(s), s
    for s in ["0x", "1.2.3", "1e", "e3", "inf", "NaN", ".infinity", "12:60", "x1", "1a", "v1.0"]:
        assert not needs_quoting(s), s
        assert dump_yaml({"k": s}) == f"k: {s}\n"
    assert not needs_quoting("it's")
    assert dump_yaml({"k": "it's"}) == "k: it's\n"
    assert dump_yaml({"k": "yes"}) == "k: 'yes'\n"
    assert dump_yaml({"k": "a\nb"}) == 'k: "a\\nb"\n'
    assert dump_yaml({"k": "a\tb"}) == 'k: "a\\tb"\n'
    assert dump_yaml({"k": 'say "hi"\r\n\\'}) == 'k: "say \\"hi\\"\\r\\n\\\\"\n'


# ---- new ----

TRICKY = ["yes", "No", "on", "OFF", "y", "NA", "007", "1e3", "1_000", "0x1F", "1:30",
          ".inf", "2023-01-01", "a: b", "a #b", "#x", "", " pad", "it's", "line\nbreak", "true", "null", "~"]


def test_dump_round_trips_as_text_under_yaml_1_2_and_1_1():
    text = dump_yaml({"values": TRICKY})
    assert load_stf_yaml(text)[0]["values"] == TRICKY
    from ruamel.yaml import YAML
    as_11 = YAML(typ="safe", pure=True).load("%YAML 1.1\n---\n" + text)["values"]
    # R's yaml keeps timestamps as text; ruamel's 1.1 resolver makes a date, so skip that one
    assert [v for v, t in zip(as_11, TRICKY) if t != "2023-01-01"] == [t for t in TRICKY if t != "2023-01-01"]


def test_reader_types_like_yaml_lite():
    data, _ = load_stf_yaml("a: [1.0, 2.0, 1e3, 2024-01-01, yes, 'true', true, ~, -1.0]\n")
    assert data["a"] == [1, 2, "1e3", "2024-01-01", "yes", "true", True, None, -1]
    assert type(data["a"][0]) is int and type(data["a"][8]) is int


def test_unquoted_yaml11_values_warn_quoted_do_not():
    _, warnings = load_stf_yaml("levels: [yes, 'no', on]\n")
    assert len(warnings) == 2
    assert all("quote it" in w for w in warnings)
    assert warnings[0] == ('line 1: unquoted value "yes" would be read as a non-text value by '
                           "study-wrangler's YAML 1.1 reader; quote it")


def test_yaml11_resolves():
    for s in ["y", "Yes", "NO", "on", "Off", "true", "FALSE", "null", "~", "1e3", "0x1F", "1:30", ".inf", "12"]:
        assert yaml11_resolves(s), s
    for s in ["NA", "yess", "2023-01-01", "a: b", "", "it's", "none"]:
        assert not yaml11_resolves(s), s


def test_dump_layout_block_style_indented_sequences_and_empty_lists():
    data = {"name": "participant", "id_columns": [{"id_column": "x", "entity_level": -1,
                                                    "provider_label": ["X"]}],
            "flag": True, "categories": []}
    assert dump_yaml(data) == (
        "name: participant\n"
        "id_columns:\n"
        "  - id_column: x\n"
        "    entity_level: -1\n"
        "    provider_label:\n"
        "      - X\n"
        "flag: true\n"
        "categories: []\n"
    )


def test_dump_does_not_fold_long_lines():
    long = " ".join(["word"] * 300)
    assert dump_yaml({"definition": long}) == f"definition: {long}\n"
