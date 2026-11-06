import json
import re
import shutil

import pytest

from conftest import FIXTURES, run_cli
from _check import check_stf, geohash_warning

TABULAR = FIXTURES / "tabular"
DATASETS = ["clinical-epi", "mosquito", "coffee-shops"]
NUM = "    display_name: X\n    data_type: number\n    data_shape: continuous"


def copy_of(dataset, tmp_path):
    """Copy a golden expected/ dir to a temp dir."""
    d = tmp_path / dataset
    shutil.copytree(TABULAR / dataset / "expected", d)
    return d


def read(d, f):
    return (d / f).read_text(encoding="utf-8")


def write(d, f, text):
    with open(d / f, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def edit(d, f, old, new):
    """Replace the first occurrence of `old`; fail loudly if the fixture changed under us."""
    text = read(d, f)
    assert old in text, f"{f} has no {old!r}"
    write(d, f, text.replace(old, new, 1))


def append_column(d, entity, name, fill):
    lines = read(d, f"entity-{entity}.tsv").split("\n")
    out = [l if l == "" else f"{l}\t{name if i == 0 else fill}" for i, l in enumerate(lines)]
    write(d, f"entity-{entity}.tsv", "\n".join(out))


def add_column(d, entity, name, fill, yaml_lines):
    """Append a column to an entity TSV (value `fill` on every row) and a variable block to its YAML."""
    append_column(d, entity, name, fill)
    # The JS fixtures had a blank line before `categories`; the Python-rendered ones do not.
    edit(d, f"entity-{entity}.yaml", "\ncategories", f"\n  - variable: {name}\n{yaml_lines}\ncategories")


def has(messages, pattern):
    return any(re.search(pattern, m) for m in messages)


@pytest.mark.parametrize("dataset", DATASETS)
def test_golden_fixture_passes_with_no_errors(dataset):
    assert check_stf(TABULAR / dataset / "expected")["errors"] == []


def test_orphan_child_row_is_an_error_naming_file_and_row_id(tmp_path):
    d = copy_of("clinical-epi", tmp_path)
    edit(d, "entity-participant.tsv", "H001\tP001", "H999\tP001")
    errors = check_stf(d)["errors"]
    assert has(errors, r"entity-participant\.tsv.*P001.*H999.*household"), errors


def test_duplicate_own_id_is_an_error(tmp_path):
    d = copy_of("clinical-epi", tmp_path)
    edit(d, "entity-participant.tsv", "\tP002\t", "\tP001\t")
    assert has(check_stf(d)["errors"], r"(?i)entity-participant\.tsv.*P001.*duplicate")


def test_empty_own_id_is_an_error(tmp_path):
    d = copy_of("clinical-epi", tmp_path)
    edit(d, "entity-participant.tsv", "\tP002\t", "\t\t")
    assert has(check_stf(d)["errors"], r"(?i)entity-participant\.tsv.*empty")


def test_tsv_column_missing_from_the_yaml_is_an_error(tmp_path):
    d = copy_of("mosquito", tmp_path)
    append_column(d, "collection", "extra_col", "x")
    assert has(check_stf(d)["errors"], r"entity-collection\.tsv.*extra_col.*not in entity-collection\.yaml")


def test_yaml_variable_missing_from_the_tsv_is_an_error(tmp_path):
    d = copy_of("mosquito", tmp_path)
    edit(d, "entity-collection.yaml", "\ncategories",
         "\n  - variable: ghost\n    display_name: Ghost\n    data_type: string\n    data_shape: categorical\ncategories")
    assert has(check_stf(d)["errors"], r"entity-collection\.yaml.*ghost.*not in entity-collection\.tsv")


def test_bad_data_type_is_an_error(tmp_path):
    d = copy_of("mosquito", tmp_path)
    edit(d, "entity-collection.yaml", "data_type: integer", "data_type: integr")
    assert has(check_stf(d)["errors"], r"entity-collection\.yaml.*trap_nights.*data_type.*integr")


def test_bad_data_shape_display_type_hidden_are_errors_ordinal_needs_ordinal_levels(tmp_path):
    d = copy_of("mosquito", tmp_path)
    edit(d, "entity-collection.yaml", "data_shape: categorical",
         "data_shape: ordinal\n    display_type: sideways\n    hidden:\n      - nowhere")
    errors = check_stf(d)["errors"]
    assert has(errors, r"display_type.*sideways"), errors
    assert has(errors, r"hidden.*nowhere")
    assert has(errors, r"ordinal.*ordinal_levels")


def test_2023_02_30_in_a_date_column_is_an_error_naming_the_row_id(tmp_path):
    d = copy_of("mosquito", tmp_path)
    edit(d, "entity-collection.tsv", "2022-07-04", "2023-02-30")
    assert has(check_stf(d)["errors"], r"entity-collection\.tsv.*C001.*collection_date.*2023-02-30")


def test_non_numeric_value_in_a_number_column_and_out_of_range_coordinates_are_errors(tmp_path):
    d = copy_of("mosquito", tmp_path)
    edit(d, "entity-site.tsv", "11.1771", "91")
    edit(d, "entity-site.tsv", "-4.2979", "-181")
    edit(d, "entity-collection.tsv", "\t1\ton", "\tmany\ton")
    errors = check_stf(d)["errors"]
    assert has(errors, r"entity-site\.tsv.*BF01.*latitude.*91"), errors
    assert has(errors, r"entity-site\.tsv.*BF01.*longitude.*-181")
    assert has(errors, r"entity-collection\.tsv.*C001.*trap_nights.*many")


def test_ordinal_value_outside_ordinal_levels_is_an_error(tmp_path):
    d = copy_of("mosquito", tmp_path)
    edit(d, "entity-collection.yaml", "data_shape: categorical\n    vocabulary_order:",
         "data_shape: ordinal\n    ordinal_levels:\n      - low\n    vocabulary_order:")
    assert has(check_stf(d)["errors"], r'entity-collection\.tsv.*trap_light.*"on".*ordinal_levels')


def test_parent_category_naming_nothing_is_an_error(tmp_path):
    d = copy_of("clinical-epi", tmp_path)
    edit(d, "entity-participant.yaml", "parent_category: demographics", "parent_category: nothing")
    assert has(check_stf(d)["errors"], r"entity-participant\.yaml.*parent_category.*nothing")


def test_category_cycle_is_an_error(tmp_path):
    d = copy_of("clinical-epi", tmp_path)
    edit(d, "entity-participant.yaml",
         "    definition: Clinical history and measurements at enrolment.\n",
         "    definition: Clinical history and measurements at enrolment.\n    parent_category: anthropometry\n")
    assert has(check_stf(d)["errors"], r"(?i)entity-participant\.yaml.*cycle")


def test_duplicate_variable_or_category_name_is_an_error(tmp_path):
    d = copy_of("clinical-epi", tmp_path)
    edit(d, "entity-participant.yaml", "  - category: behaviour", "  - category: sex")
    assert has(check_stf(d)["errors"], r"(?i)entity-participant\.yaml.*duplicate.*sex")


def test_entity_level_minus_2_on_an_immediate_parent_is_an_error(tmp_path):
    d = copy_of("clinical-epi", tmp_path)
    edit(d, "entity-participant.yaml", "entity_level: -1", "entity_level: -2")
    assert has(check_stf(d)["errors"], r"entity-participant\.yaml.*entity_level.*-2")


def test_two_latitude_like_columns_are_an_error(tmp_path):
    d = copy_of("mosquito", tmp_path)
    add_column(d, "site", "lat", "1", NUM)
    assert has(check_stf(d)["errors"], r"(?i)entity-site\.yaml.*more than one latitude")


def test_wrong_latitude_stable_id_is_an_error(tmp_path):
    d = copy_of("mosquito", tmp_path)
    edit(d, "entity-site.yaml", "OBI_0001620", "OBI_9")
    assert has(check_stf(d)["errors"], r"entity-site\.yaml.*latitude.*stable_id.*OBI_0001620")


def test_a_lone_latitude_is_a_warning_not_an_error(tmp_path):
    d = copy_of("clinical-epi", tmp_path)
    add_column(d, "household", "latitude", "1", f"{NUM}\n    stable_id: OBI_0001620\n    display_type: latitude")
    r = check_stf(d)
    assert r["errors"] == []
    assert has(r["warnings"], r"(?i)entity-household\.yaml.*latitude.*mislabelled"), r["warnings"]


def test_a_name_the_inference_accepts_but_the_validator_does_not_is_a_warning(tmp_path):
    d = copy_of("clinical-epi", tmp_path)
    add_column(d, "village", "gps_lat", "1", NUM)
    r = check_stf(d)
    assert r["errors"] == []
    assert has(r["warnings"], r"(?i)entity-village\.yaml.*gps_lat.*inference.*validator"), r["warnings"]


def test_missing_study_yaml_entity_file_is_an_error(tmp_path):
    d = copy_of("mosquito", tmp_path)
    (d / "entity-assay.yaml").unlink()
    assert has(check_stf(d)["errors"], r"entity-assay\.yaml.*missing")


def test_missing_study_yaml_is_an_error(tmp_path):
    d = copy_of("mosquito", tmp_path)
    (d / "study.yaml").unlink()
    assert has(check_stf(d)["errors"], r"study\.yaml.*missing")


def test_stf_lite_no_yaml_is_not_supported(tmp_path):
    d = copy_of("mosquito", tmp_path)
    for n in ["site", "collection", "sample", "assay"]:
        (d / f"entity-{n}.yaml").unlink()
    (d / "study.yaml").unlink()
    assert has(check_stf(d)["errors"], r"STF-lite not supported; validate in mode 2")


def test_transposed_tsv_is_reported_as_such(tmp_path):
    d = copy_of("mosquito", tmp_path)
    edit(d, "entity-site.tsv", "site_id \\\\ Descriptors", "Descriptors \\\\ site_id")
    assert has(check_stf(d)["errors"], r"entity-site\.tsv.*transposed or malformed TSV.*validate in mode 2")


def test_a_row_with_the_wrong_cell_count_is_an_error(tmp_path):
    d = copy_of("mosquito", tmp_path)
    edit(d, "entity-site.tsv", "BF01\t0123\t", "BF01\t")
    assert has(check_stf(d)["errors"], r"entity-site\.tsv.*cells")


def test_a_column_name_that_is_not_a_plain_identifier_is_a_warning(tmp_path):
    d = copy_of("mosquito", tmp_path)
    edit(d, "entity-site.tsv", "\thabitat", "\thabitat type")
    edit(d, "entity-site.yaml", "variable: habitat", "variable: habitat type")
    r = check_stf(d)
    assert r["errors"] == []
    assert has(r["warnings"], r"habitat type")


def test_adding_geohash_1_gives_a_warning_only(tmp_path):
    d = copy_of("mosquito", tmp_path)
    add_column(d, "site", "geohash_1", "a", "    display_name: G\n    data_type: string\n    data_shape: categorical")
    r = check_stf(d)
    assert r["errors"] == []
    assert has(r["warnings"], r"entity-site\.yaml.*geohash columns present; they will be recomputed by "
                              r"infer_geo_variables_for_eda\(\)"), r["warnings"]


def test_geohash_warning_wording_depends_on_the_study_wrangler_version_compared_numerically():
    assert re.search(r"drop them before mode 2 validation.*<1\.0\.53 would duplicate them", geohash_warning("1.0.52"))
    assert re.search(r"drop them", geohash_warning("1.0.9"))
    assert re.search(r"recomputed", geohash_warning("1.0.53"))
    assert re.search(r"recomputed", geohash_warning("1.0.100"))
    assert re.search(r"recomputed", geohash_warning("1.1.0"))


def test_a_childless_parent_row_is_fine(tmp_path):
    d = copy_of("clinical-epi", tmp_path)
    text = read(d, "entity-household.tsv").rstrip().split("\n")
    cols = len(text[0].split("\t"))
    write(d, "entity-household.tsv", "\n".join(text) + "\n" + "\t".join(["V01", "H999", *[""] * (cols - 2)]) + "\n")
    assert check_stf(d)["errors"] == []


def test_a_grandchild_listing_both_ancestors_passes_a_wrong_grandparent_value_fails(tmp_path):
    d = copy_of("clinical-epi", tmp_path)
    parents = {c[1]: c[0] for c in (l.split("\t") for l in read(d, "entity-participant.tsv").rstrip().split("\n")[1:])}
    rows = read(d, "entity-sample.tsv").rstrip().split("\n")
    with_household = [f"household_id\t{l}" if i == 0 else f"{parents.get(l.split(chr(9))[0])}\t{l}"
                      for i, l in enumerate(rows)]
    write(d, "entity-sample.tsv", "\n".join(with_household) + "\n")
    edit(d, "entity-sample.yaml", "id_columns:\n",
         "id_columns:\n  - id_column: household_id\n    entity_name: household\n    entity_level: -2\n")
    assert check_stf(d)["errors"] == []
    with_household[1] = re.sub(r"^[^\t]+", "H999", with_household[1])
    write(d, "entity-sample.tsv", "\n".join(with_household) + "\n")
    assert has(check_stf(d)["errors"], r"entity-sample\.tsv.*H999.*household")


def test_an_ancestor_id_column_named_other_than_the_ancestors_own_id_column_is_an_error(tmp_path):
    d = copy_of("clinical-epi", tmp_path)
    edit(d, "entity-household.tsv", "village_id\thousehold_id", "village_id_2\thousehold_id")
    edit(d, "entity-household.yaml", "- id_column: village_id\n", "- id_column: village_id_2\n")
    errors = check_stf(d)["errors"]
    assert has(errors, r"entity-household\.yaml: id_column village_id_2 refers to village, "
                       r"whose own ID column is village_id"), errors


def test_wrong_ancestor_level_for_a_grandparent_is_an_error(tmp_path):
    d = copy_of("clinical-epi", tmp_path)
    edit(d, "entity-sample.yaml", "id_columns:\n",
         "id_columns:\n  - id_column: household_id\n    entity_name: household\n    entity_level: -3\n")
    assert has(check_stf(d)["errors"], r"entity-sample\.yaml.*household.*entity_level.*-3.*-2")


def test_a_missing_raw_data_path_mentioned_in_the_notes_is_a_warning(tmp_path):
    d = copy_of("mosquito", tmp_path)
    (d / "raw-data" / "samples.tsv").unlink()
    r = check_stf(d)
    assert r["errors"] == []
    assert has(r["warnings"], r"curation-notes\.md.*raw-data/samples\.tsv")


def test_raw_data_and_unlisted_files_are_ignored(tmp_path):
    d = copy_of("mosquito", tmp_path)
    write(d, "entity-stray.tsv", "junk")
    write(d, "entity-stray.yaml", "junk: [")
    assert check_stf(d)["errors"] == []


def test_cli_exits_0_on_a_good_dir_exits_1_with_error_lines_on_a_bad_one_json(tmp_path):
    good = run_cli("check", str(TABULAR / "mosquito" / "expected"))
    assert good.returncode == 0, good.stderr
    d = copy_of("mosquito", tmp_path)
    edit(d, "entity-collection.yaml", "data_type: integer", "data_type: integr")
    bad = run_cli("check", str(d))
    assert bad.returncode == 1
    assert re.search(r"(?m)^ERROR: entity-collection\.yaml", bad.stdout)
    as_json = run_cli("check", str(d), "--json")
    assert as_json.returncode == 1
    parsed = json.loads(as_json.stdout)
    assert len(parsed["errors"]) > 0 and isinstance(parsed["warnings"], list)
    assert run_cli("check", str(d / "nope")).returncode == 1


# ---- Python-specific ----

@pytest.fixture
def good_stf(tmp_path):
    """A minimal valid STF: one entity, sample, with one string variable."""
    d = tmp_path / "stf"
    d.mkdir()
    write(d, "study.yaml", "name: s\nentities:\n  - sample\n")
    write(d, "entity-sample.yaml",
          "name: sample\nid_columns:\n  - id_column: sample_id\n    entity_name: sample\n"
          "variables:\n  - variable: note\n    data_type: string\n    data_shape: categorical\n"
          "categories: []\n")
    write(d, "entity-sample.tsv", "sample_id \\\\ Descriptors\tnote\nS1\tx\nS2\ty\n")
    return d


def set_yaml(d, entity, variable, **fields):
    """Add a variable block with the given fields (raw YAML text) to entity-<entity>.yaml."""
    block = f"  - variable: {variable}\n" + "".join(f"    {k}: {v}\n" for k, v in fields.items())
    edit(d, f"entity-{entity}.yaml", "categories:", f"{block}categories:")


def write_column(d, entity, name, values):
    """Append a column `name` to entity-<entity>.tsv, one value per data row."""
    lines = read(d, f"entity-{entity}.tsv").rstrip("\n").split("\n")
    assert len(lines) == len(values) + 1
    out = [f"{l}\t{v}" for l, v in zip(lines, [name, *values])]
    write(d, f"entity-{entity}.tsv", "\n".join(out) + "\n")


def test_good_stf_fixture_is_clean(good_stf):
    assert check_stf(good_stf) == {"errors": [], "warnings": []}


def test_float_ordinal_levels_match_integer_cells(good_stf):
    set_yaml(good_stf, "sample", variable="grade", ordinal_levels="[1.0, 2.0]", data_shape="ordinal")
    write_column(good_stf, "sample", "grade", ["1", "2"])
    assert check_stf(good_stf)["errors"] == []


def test_unquoted_yes_in_entity_yaml_is_a_warning(good_stf):
    set_yaml(good_stf, "sample", variable="flag", vocabulary_order="[yes, no]")
    warnings = check_stf(good_stf)["warnings"]
    assert any(w.startswith("entity-sample.yaml: line") and "quote it" in w for w in warnings)


def test_yaml_parse_error_is_reported(good_stf):
    write(good_stf, "entity-sample.yaml", "name: [\n")
    errors = check_stf(good_stf)["errors"]
    assert any(e.startswith("entity-sample.yaml: cannot parse YAML: line ") for e in errors), errors


def test_entity_level_false_is_not_zero(good_stf):
    # JS `false !== 0`: a boolean is not an integer level
    edit(good_stf, "entity-sample.yaml", "    entity_name: sample\n", "    entity_name: sample\n    entity_level: false\n")
    assert "entity-sample.yaml: the own ID column must have entity_level 0" in check_stf(good_stf)["errors"]


def test_more_errors_than_the_limit_are_summarised(good_stf):
    set_yaml(good_stf, "sample", variable="n", data_type="integer", data_shape="continuous")
    rows = [f"S{i}\tx\tbad" for i in range(1, 9)]
    write(good_stf, "entity-sample.tsv", "sample_id \\\\ Descriptors\tnote\tn\n" + "\n".join(rows) + "\n")
    errors = check_stf(good_stf)["errors"]
    assert sum("is not an integer" in e for e in errors) == 5
    assert "entity-sample.tsv: n: 3 more like this not shown" in errors


def test_dates_before_year_100_are_invalid_as_in_js(good_stf):
    # JS Date.UTC maps years 0-99 to 1900-1999, so the round-trip check rejects them
    set_yaml(good_stf, "sample", variable="d", data_type="date", data_shape="continuous")
    write_column(good_stf, "sample", "d", ["0050-01-01", "2020-02-29"])
    errors = check_stf(good_stf)["errors"]
    assert errors == ['entity-sample.tsv: S1: d value "0050-01-01" is not a valid YYYY-MM-DD date']


def test_an_empty_mapping_study_yaml_is_checked_not_skipped(good_stf):
    # JS `!{}` is false, so an empty mapping is reported rather than silently skipped
    write(good_stf, "study.yaml", "{}\n")
    errors = check_stf(good_stf)["errors"]
    assert errors == ["study.yaml: name is required", "study.yaml: entities must be a non-empty list of entity names"]
