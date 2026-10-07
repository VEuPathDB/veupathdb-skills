import json

import pytest
from eda_helpers import eda_fixture

FEBRILE = [{"entityId": "ENT_8151325d", "variableId": "VAR_081ab087", "type": "stringSet", "stringSet": ["febrile"]}]


def _index():
    from _samples import index_entities

    return index_entities(eda_fixture("study_heatshock.json")["rootEntity"])


def test_validate_filters_accepts_known_values():
    from _samples import validate_filters

    assert validate_filters(FEBRILE, _index()) == FEBRILE


@pytest.mark.parametrize(
    "bad, needle",
    [
        ([{"entityId": "ENT_8151325", "variableId": "VAR_081ab087", "type": "stringSet", "stringSet": ["febrile"]}], "ENT_8151325d"),
        ([{"entityId": "ENT_8151325d", "variableId": "VAR_081ab08", "type": "stringSet", "stringSet": ["febrile"]}], "VAR_081ab087"),
        ([{"entityId": "ENT_8151325d", "variableId": "VAR_081ab087", "type": "stringSet", "stringSet": ["febril"]}], "febrile"),
        ([{"entityId": "ENT_8151325d", "variableId": "VAR_081ab087", "type": "regex", "stringSet": ["x"]}], "stringSet"),
        ([{"entityId": "ENT_8151325d", "variableId": "VAR_7033e90f", "type": "numberRange", "min": 41}], "max"),
        ([{"entityId": "ENT_8151325d", "variableId": "VAR_7033e90f", "type": "numberRange", "min": 41, "max": 37}], "min > max"),
        ([{"entityId": "ENT_8151325d", "variableId": "VAR_7033e90f", "type": "numberRange", "min": "a", "max": 37}], "different types"),
        (["not an object"], "object"),
    ],
)
def test_validate_filters_rejects_with_hints(bad, needle):
    from _samples import SampleError, validate_filters

    with pytest.raises(SampleError) as e:
        validate_filters(bad, _index())
    assert needle in str(e.value)


@pytest.fixture
def filter_file(tmp_path):
    def make(content):
        p = tmp_path / "filters.json"
        p.write_text(json.dumps(content))
        return str(p)

    return make


def test_study_with_filters_shows_subset(run_eda, filter_file):
    out = run_eda("study", "plasmodb", "DS_e973eadd57", "--filters", filter_file(FEBRILE))
    assert 'ENT_8151325d "Sample" — 6 of 12 records' in out
    assert "febrile 6" in out and "normal" not in out.split("temperature_condition", 1)[1].splitlines()[0]


def test_filter_file_forms_are_equivalent(run_eda, filter_file):
    spec = {"descriptor": {"subset": {"descriptor": FEBRILE}}}
    a = json.loads(run_eda("study", "plasmodb", "DS_e973eadd57", "--json", "--filters", filter_file(FEBRILE)))
    b = json.loads(run_eda("study", "plasmodb", "DS_e973eadd57", "--json", "--filters", filter_file({"filters": FEBRILE})))
    c = json.loads(run_eda("study", "plasmodb", "DS_e973eadd57", "--json", "--filters", filter_file(spec)))
    assert a == b == c and a["filters"] == FEBRILE and len(a["samples"]) == 6


def test_contrasts_and_de_carry_filters(run_eda, eda_mock, filter_file):
    path = filter_file(FEBRILE)
    out = json.loads(run_eda("contrasts", "plasmodb", "DS_e973eadd57", "--json", "--filters", path))
    assert not any(c["comparator"]["variableId"] == "VAR_081ab087" for c in out["candidates"])
    assert any(s["variableId"] == "VAR_081ab087" for s in out["skipped"])
    first = out["candidates"][0]
    assert all(f in first["filters"] for f in FEBRILE)
    de = json.loads(run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", "1", "--filters", path, "--json"))
    assert de["context"]["filters"] == first["filters"]
    assert eda_mock.compute_bodies("differentialexpression")[-1]["filters"] == first["filters"]
    spec = json.loads(run_eda("de-spec", "plasmodb", "DS_e973eadd57", "--contrast", "1", "--filters", path))
    assert spec["descriptor"]["subset"]["descriptor"] == first["filters"]


def test_inline_filters_equal_file(run_eda, filter_file):
    a = json.loads(run_eda("study", "plasmodb", "DS_e973eadd57", "--json", "--filters", filter_file(FEBRILE)))
    b = json.loads(run_eda("study", "plasmodb", "DS_e973eadd57", "--json", "--filters", json.dumps(FEBRILE)))
    c = json.loads(run_eda("study", "plasmodb", "DS_e973eadd57", "--json", "--filters", json.dumps({"filters": FEBRILE})))
    assert a == b == c


def test_bad_filter_file_fails_cleanly(run_eda, filter_file, tmp_path, capsys):
    with pytest.raises(SystemExit):
        run_eda("study", "plasmodb", "DS_e973eadd57", "--filters", str(tmp_path / "missing.json"))
    assert "not found" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        run_eda("study", "plasmodb", "DS_e973eadd57", "--filters", "[{")
    assert "inline JSON is not valid" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        run_eda("study", "plasmodb", "DS_e973eadd57", "--filters", filter_file({"x": 1}))
    assert "JSON array" in capsys.readouterr().err


def test_contrast_file_filters_are_validated(run_eda, tmp_path, capsys):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"comparator": {"variableId": "VAR_84f17484"}, "groupA": [{"label": "wildtype"}],
                             "groupB": [{"label": "delta-DHC mutant"}],
                             "filters": [dict(FEBRILE[0], stringSet=["hot"])]}))
    with pytest.raises(SystemExit):
        run_eda("de", "plasmodb", "DS_e973eadd57", "--contrast", str(p))
    assert "hot" in capsys.readouterr().err
