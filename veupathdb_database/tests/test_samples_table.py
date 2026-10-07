from eda_helpers import eda_fixture, synthetic_study

TAB = {
    "ENT_s": [
        ["Sample_stable_id", "Participant_stable_id", "VAR_dose", "VAR_cond"],
        ["s1", "p1", "1.5", "control"],
        ["s2", "p1", "", "treated"],
        ["s3", "p2", "2", "treated"],
        ["s4", "p3", "3", "control"],
    ],
    "ENT_p": [["Participant_stable_id", "VAR_sex"], ["p1", "female"], ["p2", "male"], ["p3", ""]],
}


def test_build_sample_table_joins_ancestors():
    from _samples import build_sample_table, index_entities, variable_meta

    index = index_entities(synthetic_study()["rootEntity"])
    meta = variable_meta(index, ["ENT_s", "ENT_p"])
    calls = []

    def fetch(eid, ids):
        calls.append((eid, sorted(ids)))
        return TAB[eid]

    table = build_sample_table(fetch, index, "ENT_g", meta)
    assert calls == [("ENT_s", ["VAR_cond", "VAR_dose"]), ("ENT_p", ["VAR_sex"])]
    assert table["entityId"] == "ENT_s"
    assert table["rows"] == [
        {"sampleId": "s1", "VAR_dose": 1.5, "VAR_cond": "control", "VAR_sex": "female"},
        {"sampleId": "s2", "VAR_dose": None, "VAR_cond": "treated", "VAR_sex": "female"},
        {"sampleId": "s3", "VAR_dose": 2.0, "VAR_cond": "treated", "VAR_sex": "male"},
        {"sampleId": "s4", "VAR_dose": 3.0, "VAR_cond": "control", "VAR_sex": None},
    ]
    assert table["byEntity"]["ENT_p"] == [{"VAR_sex": "female"}, {"VAR_sex": "male"}, {"VAR_sex": None}]


def test_build_sample_table_heatshock_fixture():
    from _samples import ancestors, build_sample_table, index_entities, variable_meta

    index = index_entities(eda_fixture("study_heatshock.json")["rootEntity"])
    meta = variable_meta(index, ancestors(index, "ENT_fd574cd6"))
    table = build_sample_table(
        lambda eid, ids: eda_fixture("tabular_heatshock_sample.json"), index, "ENT_fd574cd6", meta
    )
    rows = table["rows"]
    assert len(rows) == 12
    temps = sorted(r["VAR_081ab087"] for r in rows)
    assert temps == ["febrile"] * 6 + ["normal"] * 6
    for vid, m in meta.items():
        if m["type"] in ("number", "integer"):
            assert all(r.get(vid) is None or isinstance(r[vid], float) for r in rows)


def test_summarise_variable_kinds():
    from _samples import summarise_variable

    cat = summarise_variable({"type": "string"}, ["b", "a", "b", None])
    assert cat == {"n": 3, "missing": 1, "distinct": 2, "kind": "categorical", "levels": [["b", 2], ["a", 1]]}
    ident = summarise_variable({"type": "string"}, [f"s{i}" for i in range(25)])
    assert ident["kind"] == "identifier" and ident["distinct"] == 25
    num = summarise_variable({"type": "number"}, [1.0, 3.0, None])
    assert num == {"n": 2, "missing": 1, "kind": "continuous", "min": 1.0, "max": 3.0, "mean": 2.0, "distinct": 2}
    empty = summarise_variable({"type": "number"}, [None, None])
    assert empty == {"n": 0, "missing": 2, "kind": "continuous"}


def test_summarise_variable_all_distinct_is_identifier():
    from _samples import summarise_variable

    s = summarise_variable({"type": "string"}, [f"SRR{i}" for i in range(12)])
    assert s["kind"] == "identifier" and s["distinct"] == 12 and s["n"] == 12
    assert summarise_variable({"type": "string"}, ["a", "b"])["kind"] == "categorical"
    assert summarise_variable({"type": "string"}, ["a", "a", "b", "b", "c", "c"])["kind"] == "categorical"


def test_convert_value_treats_non_finite_numbers_as_missing():
    from _samples import convert_value

    meta = {"type": "number"}
    assert [convert_value(meta, v) for v in ("NaN", "inf", "-inf", "Infinity")] == [None] * 4
    assert convert_value(meta, "2.5") == 2.5
