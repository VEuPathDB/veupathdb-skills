import hashlib
import json

import pytest

GOLD_BODY = {
    "studyId": "STUDY_e973eadd57",
    "filters": [],
    "derivedVariables": [],
    "config": {
        "identifierVariable": {"entityId": "ENT_fd574cd6", "variableId": "VEUPATHDB_GENE_ID"},
        "valueVariable": {"entityId": "ENT_fd574cd6", "variableId": "SEQUENCE_READ_COUNT_SENSE"},
        "comparator": {
            "variable": {"entityId": "ENT_8151325d", "variableId": "VAR_081ab087"},
            "groupA": [{"label": "normal"}],
            "groupB": [{"label": "febrile"}],
        },
        "differentialExpressionMethod": "DESeq",
        "pValueFloor": "1e-200",
    },
}
GOLD_JOB = "db04204e5386396e1ca2cb78469ab6fb"  # live jobID, plasmodb 2026-10-03
TEMP = {"entityId": "ENT_8151325d", "variableId": "VAR_081ab087"}


def test_job_id_matches_live_gold():
    from _contrasts import job_id

    assert job_id("differentialexpression", GOLD_BODY) == GOLD_JOB


def test_job_id_ignores_key_order():
    from _contrasts import job_id

    shuffled = json.loads(json.dumps(GOLD_BODY, sort_keys=True))
    shuffled = {k: shuffled[k] for k in reversed(list(shuffled))}
    assert job_id("differentialexpression", shuffled) == GOLD_JOB


def test_job_id_hashes_non_ascii_unescaped():
    from _contrasts import job_id

    body = {"studyId": "STUDY_x", "filters": [], "derivedVariables": [], "config": {"l": "naïve"}}
    inner = '{"config":{"l":"naïve"},"derivedVariables":[],"filters":[],"studyId":"STUDY_x"}'
    want = hashlib.md5(json.dumps(["p", inner], separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    assert job_id("p", body) == want


def test_de_config_reproduces_gold_and_compute_body():
    from _contrasts import compute_body, de_config

    cfg = de_config("ENT_fd574cd6", "SEQUENCE_READ_COUNT_SENSE", TEMP, [{"label": "normal"}], [{"label": "febrile"}], "DESeq")
    assert compute_body("STUDY_e973eadd57", cfg, []) == GOLD_BODY


def test_label_order_is_canonical_but_swapping_groups_is_a_new_job():
    from _contrasts import PLUGIN_DE, compute_body, de_config, job_id

    def jid(a, b):
        cfg = de_config("E", "SEQUENCE_READ_COUNT", TEMP, a, b, "DESeq")
        return job_id(PLUGIN_DE, compute_body("STUDY_x", cfg, []))

    ab = [{"label": "b"}, {"label": "a"}]
    assert jid(ab, [{"label": "c"}]) == jid(list(reversed(ab)), [{"label": "c"}])
    assert jid([{"label": "a"}], [{"label": "c"}]) != jid([{"label": "c"}], [{"label": "a"}])


def test_canonical_group_stringifies_and_sorts():
    from _contrasts import ContrastError, canonical_group

    assert canonical_group([{"label": "b"}, {"label": "a", "min": 1, "max": 2.5}]) == [
        {"label": "a", "min": "1", "max": "2.5"},
        {"label": "b"},
    ]
    with pytest.raises(ContrastError):
        canonical_group([{"min": "1", "max": "2"}])


def test_canonical_and_merged_filters():
    from _contrasts import ContrastError, canonical_filters, merge_filters

    f1 = {"entityId": "E2", "variableId": "V1", "type": "stringSet", "stringSet": ["b", "a"]}
    f2 = {"entityId": "E1", "variableId": "V9", "type": "numberRange", "min": 1, "max": 2}
    assert canonical_filters([f1, f2]) == [f2, {**f1, "stringSet": ["a", "b"]}]
    assert merge_filters([f1], [f2], [dict(f1, stringSet=["a", "b"])]) == canonical_filters([f1, f2])
    with pytest.raises(ContrastError):
        merge_filters([f1], [dict(f1, stringSet=["c"])])


def test_compute_body_refuses_dataset_ids():
    from _contrasts import ContrastError, compute_body

    with pytest.raises(ContrastError) as e:
        compute_body("DS_e973eadd57", {}, [])
    assert "STUDY_" in str(e.value)


def test_pca_config():
    from _contrasts import pca_config

    assert pca_config("E", "SEQUENCE_READ_COUNT_SENSE") == {
        "identifierVariable": {"entityId": "E", "variableId": "VEUPATHDB_GENE_ID"},
        "valueVariable": {"entityId": "E", "variableId": "SEQUENCE_READ_COUNT_SENSE"},
        "dataFormat": "rawCounts",
    }
    cfg = pca_config("E", "NORMALIZED_INTENSITY", n_pcs=5)
    assert cfg["dataFormat"] == "normalizedValues" and cfg["nPCs"] == 5


def test_choose_value_var():
    from _contrasts import ContrastError, choose_value_var

    assert choose_value_var({"entityId": "E", "valueIds": ["SEQUENCE_READ_COUNT"]}) == ("SEQUENCE_READ_COUNT", None)
    v, note = choose_value_var({"entityId": "E", "valueIds": ["SEQUENCE_READ_COUNT_SENSE", "SEQUENCE_READ_COUNT_ANTISENSE"]})
    assert v == "SEQUENCE_READ_COUNT_SENSE" and "SEQUENCE_READ_COUNT_ANTISENSE" in note
    assert choose_value_var({"entityId": "E", "valueIds": ["NORMALIZED_INTENSITY"]})[0] == "NORMALIZED_INTENSITY"
    with pytest.raises(ContrastError):
        choose_value_var({"entityId": "E", "valueIds": ["SEQUENCE_READ_COUNT"]}, "NORMALIZED_INTENSITY")


def test_choose_method():
    from _contrasts import ContrastError, choose_method

    assert choose_method("antibodyArrayNotebook", "NORMALIZED_INTENSITY") == ("limma", None)
    assert choose_method("differentialExpressionNotebook", "SEQUENCE_READ_COUNT") == ("DESeq", None)
    assert choose_method(None, "SEQUENCE_READ_COUNT_SENSE") == ("DESeq", None)
    assert choose_method(None, "NORMALIZED_EXPRESSION") == ("limma", None)
    method, note = choose_method("differentialExpressionNotebook", "SEQUENCE_READ_COUNT", "limma")
    assert method == "limma" and "separate job" in note
    with pytest.raises(ContrastError):
        choose_method(None, "SEQUENCE_READ_COUNT", "edgeR")
