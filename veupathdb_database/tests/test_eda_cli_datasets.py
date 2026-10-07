import json

import pytest


def test_de_datasets_lists_supported_searches(run_eda, fake_wdk):
    rows = json.loads(run_eda("de-datasets", "plasmodb", "--json"))
    assert [(r["search"], r["datasetId"], r["method"]) for r in rows] == [
        ("GenesByAntibodyArrayEdaSubset_X", "DS_24d441b301", "limma"),
        ("GenesByDESeqUserDataset", None, "DESeq"),
        ("GenesByRNASeqHS_DESeq", "DS_e973eadd57", "DESeq"),
    ]
    text = run_eda("de-datasets", "plasmodb")
    assert "DS_e973eadd57\tDESeq\tdifferentialExpressionNotebook\tGenesByRNASeqHS_DESeq" in text
    assert "(user dataset: pass your DS_ id)" in text


def test_search_name_target_and_cached_notebook(run_eda, fake_wdk):
    import eda as eda_cli

    out = json.loads(run_eda("contrasts", "plasmodb", "GenesByRNASeqHS_DESeq", "--json"))
    assert out["datasetId"] == "DS_e973eadd57" and out["method"] == "DESeq"
    assert eda_cli.resolve_target_arg("plasmodb", "DS_e973eadd57") == (
        "DS_e973eadd57", "differentialExpressionNotebook", "GenesByRNASeqHS_DESeq")


def test_ds_id_alone_makes_no_wdk_call(run_eda, fake_wdk):
    import eda as eda_cli

    assert eda_cli.resolve_target_arg("plasmodb", "DS_e973eadd57") == ("DS_e973eadd57", None, None)
    assert fake_wdk.calls == []


def test_user_dataset_search_needs_ds_id(run_eda, fake_wdk, capsys):
    with pytest.raises(SystemExit):
        run_eda("study", "plasmodb", "GenesByDESeqUserDataset")
    assert "DS_" in capsys.readouterr().err


def test_unknown_search_suggests(run_eda, fake_wdk, capsys):
    with pytest.raises(SystemExit):
        run_eda("study", "plasmodb", "GenesByRNASeqHS_DESeqq")
    assert "GenesByRNASeqHS_DESeq" in capsys.readouterr().err
