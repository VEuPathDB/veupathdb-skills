import copy

import pytest
from eda_helpers import eda_fixture, synthetic_study


def _index(study):
    from _samples import index_entities

    return index_entities(study["rootEntity"])


def test_index_and_ancestors_heatshock():
    from _samples import ancestors

    index = _index(eda_fixture("study_heatshock.json"))
    assert ancestors(index, "ENT_fd574cd6") == ["ENT_8151325d"]
    assert ancestors(index, "ENT_8151325d") == []


def test_ancestors_nearest_first():
    from _samples import ancestors

    assert ancestors(_index(synthetic_study()), "ENT_g") == ["ENT_s", "ENT_p"]


def test_expression_entity_heatshock():
    from _samples import pick_expression_entity

    expr = pick_expression_entity(_index(eda_fixture("study_heatshock.json")))
    assert expr["entityId"] == "ENT_fd574cd6"
    assert expr["geneCount"] == 5720
    assert expr["valueIds"] == ["SEQUENCE_READ_COUNT_SENSE", "SEQUENCE_READ_COUNT_ANTISENSE"]


def test_expression_entity_antibody():
    from _samples import pick_expression_entity

    expr = pick_expression_entity(_index(eda_fixture("study_antibody.json")))
    assert expr["entityId"] == "GENE_ANTIBODY_ARRAY_DATA"
    assert expr["valueIds"] == ["NORMALIZED_INTENSITY"]


def test_pick_expression_entity_refuses_ambiguity():
    from _samples import SampleError, pick_expression_entity

    study = synthetic_study()
    sample = study["rootEntity"]["children"][0]
    twin = copy.deepcopy(sample["children"][0])
    twin["id"], twin["displayName"] = "ENT_g2", "host counts"
    sample["children"].append(twin)
    index = _index(study)
    with pytest.raises(SampleError) as e:
        pick_expression_entity(index)
    assert "ENT_g" in str(e.value) and "ENT_g2" in str(e.value) and "--entity" in str(e.value)
    assert pick_expression_entity(index, "ENT_g2")["displayName"] == "host counts"
    with pytest.raises(SampleError):
        pick_expression_entity(index, "ENT_nope")


def test_not_de_ready():
    from _samples import SampleError, pick_expression_entity

    study = synthetic_study()
    study["rootEntity"]["children"][0]["children"] = []
    with pytest.raises(SampleError) as e:
        pick_expression_entity(_index(study))
    assert "not DE-ready" in str(e.value)


def test_prune_entity_hides_orders_and_truncates():
    from _samples import prune_entity

    sample = synthetic_study()["rootEntity"]["children"][0]
    items = prune_entity(sample)
    assert [(i["kind"], i["id"], i["depth"]) for i in items] == [
        ("category", "VAR_cat", 0),
        ("variable", "VAR_dose", 1),
        ("variable", "VAR_cond", 1),
    ]  # empty category dropped; displayOrder respected
    cond = items[2]
    assert cond["featured"] is True and cond["entityId"] == "ENT_s"
    assert len(cond["definition"]) == 120 and cond["definition"].endswith("…")
    dose = items[1]
    assert "definition" not in dose and dose["units"] == "mg"
    assert dose["_binSpec"] == {"displayRangeMin": 0, "displayRangeMax": 10, "binWidth": 1}


def test_prune_entity_drops_hidden_variables():
    from _samples import prune_entity

    items = prune_entity(synthetic_study()["rootEntity"])
    assert [i["id"] for i in items] == ["VAR_sex"]


def test_variable_meta_and_all_var_entities():
    from _samples import all_var_entities, variable_meta

    index = _index(synthetic_study())
    meta = variable_meta(index, ["ENT_s", "ENT_p"])
    assert set(meta) == {"VAR_dose", "VAR_cond", "VAR_sex"}
    assert meta["VAR_sex"]["entityId"] == "ENT_p"
    owners = all_var_entities(index)
    assert owners["SEQUENCE_READ_COUNT"] == "ENT_g" and owners["VAR_hide"] == "ENT_p"


def test_prune_antibody_root_keeps_categories_with_variables():
    from _samples import prune_entity

    items = prune_entity(eda_fixture("study_antibody.json")["rootEntity"])
    kinds = {i["kind"] for i in items}
    assert kinds == {"category", "variable"}
    assert all(i["depth"] >= 0 for i in items)
