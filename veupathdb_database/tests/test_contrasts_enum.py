import pytest


def meta(vid, name=None, type_="string", entity="ENT_s", featured=False, vocab=None):
    m = {
        "kind": "variable", "id": vid, "entityId": entity, "displayName": name or vid,
        "type": type_, "dataShape": "continuous" if type_ in ("number", "integer") else "categorical",
        "featured": featured, "depth": 0,
    }
    if vocab:
        m["vocabulary"] = vocab
    return m


def crossed_rows():
    rows = []
    for strain in ("A", "B", "C"):
        for temp, deg in (("normal", 37.0), ("febrile", 41.0)):
            for rep in (1, 2):
                rows.append({
                    "sampleId": f"{strain}_{deg:g}_{rep}", "temp": temp, "deg": deg,
                    "strain": strain, "label": f"{strain}-{temp}", "name": f"{strain}_{deg:g}_{rep}",
                })
    return rows


CROSSED = {
    "temp": meta("temp", "temperature_condition"),
    "deg": meta("deg", "temperature", "number"),
    "strain": meta("strain", "strain"),
    "label": meta("label", "label", featured=True),
    "name": meta("name", "sample name"),
}


def test_is_control_label():
    from _contrasts import is_control_label

    for yes in ("WT 37C", "wild type", "Wild-Type", "Control", "pre-infection", "naïve", "mock-infected", "normal"):
        assert is_control_label(yes), yes
    for no in ("febrile", "treated", "PB31", "delta-LRR5-41C"):
        assert not is_control_label(no), no


def test_crossed_design_first_candidate_and_strata():
    from _contrasts import enumerate_contrasts

    out = enumerate_contrasts(crossed_rows(), CROSSED)
    first = out["candidates"][0]
    assert first["index"] == 1
    assert first["comparator"] == {"entityId": "ENT_s", "variableId": "temp", "displayName": "temperature_condition"}
    assert first["groupA"] == [{"label": "normal"}] and first["groupB"] == [{"label": "febrile"}]
    assert first["reference"] == "label match"
    assert (first["nA"], first["nB"], first["filters"], first["stratum"]) == (6, 6, [], None)
    assert out["truncated"] is None
    assert any("same grouping as temperature" in n for n in first["notes"])
    assert any("strain varies within the groups" in n for n in first["notes"])
    strata = out["candidates"][1:4]
    assert [s["stratum"]["label"] for s in strata] == ["A", "B", "C"]
    assert strata[0]["filters"] == [{"entityId": "ENT_s", "variableId": "strain", "type": "stringSet", "stringSet": ["A"]}]
    assert all((s["nA"], s["nB"]) == (2, 2) for s in strata)
    assert all(any("low replicates" in n for n in s["notes"]) for s in strata)
    assert out["aliases"] == [{"variableId": "deg", "displayName": "temperature", "sameAs": "temp", "sameAsName": "temperature_condition"}]
    assert any(s["variableId"] == "name" for s in out["skipped"])
    assert {"variableId": "label", "displayName": "label", "within": "temp", "withinName": "temperature_condition"} in out["nested"]
    assert not any(n["variableId"] == "strain" and n["within"] == "temp" for n in out["nested"])  # crossed, not nested


def test_indices_are_contiguous_and_deterministic():
    from _contrasts import enumerate_contrasts

    a = enumerate_contrasts(crossed_rows(), CROSSED)
    b = enumerate_contrasts(list(reversed(crossed_rows())), dict(reversed(list(CROSSED.items()))))
    assert [c["index"] for c in a["candidates"]] == list(range(1, len(a["candidates"]) + 1))
    assert a == b


def test_pair_notes_name_other_differences():
    from _contrasts import enumerate_contrasts

    out = enumerate_contrasts(crossed_rows(), CROSSED, only_vars={"label"})
    hit = next(c for c in out["candidates"] if c["groupA"] == [{"label": "A-normal"}] and c["groupB"] == [{"label": "A-febrile"}])
    assert "groups also differ in temperature_condition: normal vs febrile" in hit["notes"]
    assert all(c["comparator"]["variableId"] == "label" for c in out["candidates"])


def test_partial_confounding_is_noted():
    from _contrasts import enumerate_contrasts

    rows = (
        [{"sampleId": f"c{i}", "cond": "control", "batch": "b1"} for i in range(3)]
        + [{"sampleId": f"t{i}", "cond": "treated", "batch": "b2"} for i in range(3)]
        + [{"sampleId": "o1", "cond": "other", "batch": "b1"}, {"sampleId": "o2", "cond": "other", "batch": "b2"}]
    )
    out = enumerate_contrasts(rows, {"cond": meta("cond", "condition"), "batch": meta("batch", "batch")}, only_vars={"cond"})
    hit = next(c for c in out["candidates"] if c["groupB"] == [{"label": "treated"}] and c["groupA"] == [{"label": "control"}])
    assert "groups also differ in batch: b1 vs b2" in hit["notes"]


def test_ambiguous_orientation_lists_one_with_hint():
    from _contrasts import enumerate_contrasts

    rows = [{"sampleId": f"s{i}", "col": c} for i, c in enumerate(["red"] * 3 + ["blue"] * 3)]
    cands = enumerate_contrasts(rows, {"col": meta("col")})["candidates"]
    assert [(c["groupA"][0]["label"], c["groupB"][0]["label"]) for c in cands] == [("blue", "red")]
    assert cands[0]["reference"] == "arbitrary"
    assert any("reference unclear" in n and "swap" in n for n in cands[0]["notes"])


def test_label_matched_reference_is_a_hint_not_a_rule():
    from _contrasts import enumerate_contrasts

    rows = [{"sampleId": f"s{i}", "g": c} for i, c in enumerate(["mutant"] * 3 + ["WT"] * 3)]
    cands = enumerate_contrasts(rows, {"g": meta("g")})["candidates"]
    assert len(cands) == 1
    assert cands[0]["groupA"] == [{"label": "WT"}] and cands[0]["reference"] == "label match"
    assert any("reference guessed from label" in n and "swap" in n for n in cands[0]["notes"])


def test_candidate_list_is_capped():
    from _contrasts import enumerate_contrasts

    # three crossed 6-level factors, 2 replicates per cell: hundreds of pairs and strata
    rows = [
        {"sampleId": f"{a}{b}{c}{r}", "f1": f"a{a}", "f2": f"b{b}", "f3": f"c{c}"}
        for a in range(6) for b in range(6) for c in range(6) for r in range(2)
    ]
    var_meta = {v: meta(v) for v in ("f1", "f2", "f3")}
    out = enumerate_contrasts(rows, var_meta)
    assert [c["index"] for c in out["candidates"]] == list(range(1, 51))
    assert out["truncated"]["shown"] == 50 and out["truncated"]["total"] > 50
    assert enumerate_contrasts(rows, var_meta, max_candidates=None)["truncated"] is None


def test_missing_values_are_not_a_level():
    from _contrasts import enumerate_contrasts

    rows = [{"sampleId": f"s{i}", "cond": c} for i, c in enumerate(["control", "control", "treated", "treated", None, None])]
    out = enumerate_contrasts(rows, {"cond": meta("cond", vocab=["control", "treated"])})
    assert len(out["candidates"]) == 1
    c = out["candidates"][0]
    assert (c["nA"], c["nB"]) == (2, 2)
    assert "" not in [g["label"] for g in c["groupA"] + c["groupB"]]


def test_singleton_levels_left_out_with_note():
    from _contrasts import enumerate_contrasts

    rows = [{"sampleId": f"s{i}", "cond": c} for i, c in enumerate(["control"] * 3 + ["treated"] * 3 + ["odd"])]
    c = enumerate_contrasts(rows, {"cond": meta("cond")})["candidates"][0]
    assert "levels with <2 samples left out: odd (1)" in c["notes"]


def test_many_levels_are_summarised_not_paired():
    from _contrasts import enumerate_contrasts

    rows = [{"sampleId": f"s{i}", "stage": f"st{i // 2}"} for i in range(14)]
    out = enumerate_contrasts(rows, {"stage": meta("stage")})
    assert out["candidates"] == []
    skip = out["skipped"][0]
    assert "pool levels" in skip["reason"] and len(skip["levels"]) == 7


def test_numeric_levels_are_half_open_bins():
    from _contrasts import comparator_levels, samples_in_group

    rows = [{"sampleId": f"s{i}", "dose": d} for i, d in enumerate([0.0, 0.0, 5.0, 5.0, 10.0, 10.0])]
    levels = comparator_levels(rows, meta("dose", type_="number"))
    assert [e for e, ids in levels] == [
        {"label": "0", "min": "0", "max": "5"},
        {"label": "10", "min": "10", "max": "11"},
        {"label": "5", "min": "5", "max": "10"},
    ]
    assert samples_in_group(rows, "dose", [{"label": "5", "min": "5", "max": "10"}]) == ["s2", "s3"]


def test_replicate_check():
    from _contrasts import ContrastError, replicate_check

    with pytest.raises(ContrastError):
        replicate_check(1, 5)
    assert "low replicates" in replicate_check(2, 5)
    assert replicate_check(3, 3) is None


def test_load_contrast_validates_and_merges_filters():
    from _contrasts import ContrastError, load_contrast

    var_meta = {"temp": meta("temp", "temperature_condition", vocab=["febrile", "normal"]), "deg": meta("deg", type_="number")}
    owners = {"temp": "ENT_s", "deg": "ENT_s", "SEQUENCE_READ_COUNT": "ENT_g"}
    base = [{"entityId": "ENT_s", "variableId": "strain", "type": "stringSet", "stringSet": ["A"]}]
    c = load_contrast(
        {"comparator": {"variableId": "temp"}, "groupA": [{"label": "normal"}], "groupB": [{"label": "febrile"}]},
        var_meta, owners, ["ENT_s"], base,
    )
    assert c["comparator"]["entityId"] == "ENT_s" and c["filters"] == base
    with pytest.raises(ContrastError) as e:
        load_contrast({"comparator": {"variableId": "temp"}, "groupA": [{"label": "norml"}], "groupB": [{"label": "febrile"}]}, var_meta, owners, ["ENT_s"])
    assert "normal" in str(e.value)
    with pytest.raises(ContrastError) as e:
        load_contrast({"comparator": {"variableId": "SEQUENCE_READ_COUNT"}, "groupA": [{"label": "x"}], "groupB": [{"label": "y"}]}, var_meta, owners, ["ENT_s"])
    assert "not a parent" in str(e.value)
    with pytest.raises(ContrastError) as e:
        load_contrast({"comparator": {"variableId": "tmp"}, "groupA": [{"label": "x"}], "groupB": [{"label": "y"}]}, var_meta, owners, ["ENT_s"])
    assert "temp" in str(e.value)
    with pytest.raises(ContrastError):
        load_contrast({"comparator": {"variableId": "deg"}, "groupA": [{"label": "37"}], "groupB": [{"label": "41"}]}, var_meta, owners, ["ENT_s"])

def _binned_rows():
    # 8 distinct values; bins of width 10 anchored at 0: [0,10) x3, [10,20) x2, [20,30) x3
    vals = [1.0, 2.0, 9.0, 11.0, 19.0, 21.0, 25.0, 29.0]
    return [{"sampleId": f"s{i}", "age": v} for i, v in enumerate(vals)]


def test_many_valued_numeric_with_bin_spec_is_binned():
    from _contrasts import comparator_levels, enumerate_contrasts, samples_in_group

    m = meta("age", "age", "number")
    m["_binSpec"] = {"displayRangeMin": 0, "displayRangeMax": 30, "binWidth": 10}
    rows = _binned_rows()
    levels = comparator_levels(rows, m)
    assert [(e["label"], len(ids)) for e, ids in levels] == [("[0, 10)", 3), ("[20, 30)", 3), ("[10, 20)", 2)]
    assert levels[0][0] == {"label": "[0, 10)", "min": "0", "max": "10"}
    assert samples_in_group(rows, "age", [levels[2][0]]) == ["s3", "s4"]
    assert samples_in_group(rows, "age", [{"label": "x", "min": "9", "max": "11"}]) == ["s2"]  # half-open
    out = enumerate_contrasts(rows, {"age": m})
    assert len(out["candidates"]) == 3 and out["skipped"] == []
    assert all(c["nA"] + c["nB"] in (5, 6) for c in out["candidates"])


def test_binned_numeric_drift_is_rounded():
    from _contrasts import comparator_levels

    m = meta("x", "x", "number")
    m["_binSpec"] = {"displayRangeMin": 0, "displayRangeMax": 1, "binWidth": 0.1}
    rows = [{"sampleId": f"s{i}", "x": i / 10 + 0.05} for i in range(8)]
    labels = [e["label"] for e, ids in comparator_levels(rows, m)]
    assert sorted(labels) == sorted(f"[{i / 10:g}, {(i + 1) / 10:g})" for i in range(8))


def test_many_valued_numeric_without_bin_spec_needs_contrast_file():
    from _contrasts import enumerate_contrasts

    rows = [{"sampleId": f"s{i}", "age": float(i)} for i in range(8)]
    out = enumerate_contrasts(rows, {"age": meta("age", "age", "number")})
    assert out["candidates"] == []
    assert "write a contrast file" in out["skipped"][0]["reason"]

