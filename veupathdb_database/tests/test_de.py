import json
import math

import pytest


def stat(gene, es, p, padj="0.5"):
    return {"pointID": gene, "effectSize": es, "pValue": p, "adjustedPValue": padj}


def test_java_double_matches_java_parsing():
    from _de import java_double

    assert java_double("1.5") == 1.5
    assert java_double(" -2e-3 ") == -0.002
    assert java_double("1e-200") == 1e-200
    assert java_double("1.0d") == 1.0
    assert java_double(3) == 3.0
    assert math.isnan(java_double("NaN"))
    assert java_double("Infinity") == math.inf and java_double("-Infinity") == -math.inf
    for bad in ("NA", "nan", "inf", "Inf", "", "null", None, "1,5", True):
        assert java_double(bad) is None, bad


def test_is_retained_ports_plugin():
    from _de import is_retained

    assert is_retained("1.0", "0.05", 1, 0.05, "upAndDown")  # both bounds inclusive
    assert is_retained("-1.0", "0.05", 1, 0.05, "upAndDown")
    assert not is_retained("0.99", "0.01", 1, 0.05, "upAndDown")
    assert not is_retained("2", "0.051", 1, 0.05, "upAndDown")
    assert is_retained("2", "-0.01", 1, 0.05, "upAndDown")  # the plugin takes |p|
    assert is_retained("2", "0.01", 1, 0.05, "upOnly") and not is_retained("-2", "0.01", 1, 0.05, "upOnly")
    assert is_retained("-2", "0.01", 1, 0.05, "downOnly") and not is_retained("2", "0.01", 1, 0.05, "downOnly")
    assert not is_retained("0", "1", 0, 1, "upOnly")
    for es, p in (("NA", "0.01"), ("NaN", "0.01"), ("2", None), ("2", "NaN")):
        assert not is_retained(es, p, 0, 1, "upAndDown")


def test_parse_thresholds():
    from _de import parse_thresholds
    from _eda import EdaError

    assert parse_thresholds("1,0.05") == (1.0, 0.05, "upAndDown")
    assert parse_thresholds("0.5, 0.01, upOnly") == (0.5, 0.01, "upOnly")
    for bad in ("1", "a,0.05", "1,0", "1,1.5", "-1,0.05", "1,0.05,up"):
        with pytest.raises(EdaError):
            parse_thresholds(bad)


def test_wdk_step_skips_first_statistics_row():
    from _de import summarise, wdk_step_genes

    stats = [stat("G1", "3", "0.001"), stat("G2", "3", "0.001"), stat("G3", "0.1", "0.9")]
    th = (1.0, 0.05, "upAndDown")
    assert wdk_step_genes(stats, th) == ["G2"]
    s = summarise(stats, th)
    assert (s["passing_raw_p"], s["wdk_step_genes"], s["wdk_dropped_gene"]) == (2, 1, "G1")
    s = summarise(list(reversed(stats)), th)
    assert (s["passing_raw_p"], s["wdk_step_genes"], s["wdk_dropped_gene"]) == (2, 2, None)


def test_summarise_counts_and_tops():
    from _de import summarise

    stats = [
        stat("G0", "0.1", "0.9", "0.95"),
        stat("G1", "3", "0.001", "0.01"),
        stat("G2", "-2", "0.001", "0.02"),
        stat("G3", "4", "0.01", "0.2"),
        stat("G4", "5", "0.001", None),
        stat("G5", "NA", "NA", None),
    ]
    s = summarise(stats, (1.0, 0.05, "upAndDown"))
    assert s["tested"] == 6 and s["padj_na"] == 2
    assert s["passing_raw_p"] == 4 and s["passing_raw_genes"] == ["G1", "G2", "G3", "G4"]
    assert s["wdk_step_genes"] == 4 and s["wdk_dropped_gene"] is None
    assert s["passing_padj"] == 2
    assert [r["gene"] for r in s["top_up"]] == ["G1"]
    assert [r["gene"] for r in s["top_down"]] == ["G2"]


def test_de_table_is_json_safe():
    from _de import de_table

    rows = de_table([stat("G1", "Infinity", "NaN", None), stat("G2", "1.5", "0.01", "0.02")])
    assert rows[0] == {"gene": "G1", "effectSize": None, "pValue": None, "adjustedPValue": None}
    assert rows[1] == {"gene": "G2", "effectSize": 1.5, "pValue": 0.01, "adjustedPValue": 0.02}
    json.dumps(rows, allow_nan=False)


def test_gene_rows_statuses_case_insensitive():
    from _de import de_table, gene_rows

    table = de_table([stat("PF3D7_0100100", "1", "0.01", "0.02"), stat("PF3D7_0100200", "1", "0.01", None)])
    rows = gene_rows(table, ["pf3d7_0100100", "PF3D7_0100200", "PF3D7_9999999"])
    assert rows[0]["gene"] == "PF3D7_0100100" and rows[0]["status"] == "tested"
    assert "padj NA" in rows[1]["status"]
    assert rows[2]["status"].startswith("not tested") and rows[2]["pValue"] is None


def test_de_json_separates_identity():
    from _de import de_json, de_table, summarise

    stats = [stat("G0", "0.1", "0.9", "0.95"), stat("G1", "3", "0.001", "0.01"), stat("G2", "-2", "0.0001", "0.02")]
    s = summarise(stats, (1.0, 0.05, "upAndDown"))
    out = de_json({"comparator": "temp"}, {"jobId": "j"}, s, de_table(stats), genes=["G0"])
    assert set(out) == {"context", "provenance", "identity", "rows"}
    assert out["identity"] == {"r1": "G2", "r2": "G1", "r3": "G0"}  # ordered by p
    assert out["rows"]["r1"]["effectSize"] == -2.0 and "gene" not in out["rows"]["r1"]
    assert out["context"]["top"] == {"up": ["r2"], "down": ["r1"]}
    assert out["context"]["counts"]["passing_raw_p"] == 2
    blind = json.dumps({k: v for k, v in out.items() if k != "identity"})
    assert "G1" not in blind and "G2" not in blind
    json.dumps(out, allow_nan=False)


def test_negate_effects_flips_sign_only():
    from _de import negate_effects

    stats = [stat("G1", "1.5", "0.01", "0.02"), stat("G2", "-2e-3", "0.5"), stat("G3", "0", "1"), stat("G4", "NA", "NA", None)]
    out = negate_effects(stats)
    assert [s["effectSize"] for s in out] == ["-1.5", "0.002", "0", "NA"]
    assert [(s["pointID"], s["pValue"], s["adjustedPValue"]) for s in out] == [
        (s["pointID"], s["pValue"], s["adjustedPValue"]) for s in stats
    ]
    assert stats[0]["effectSize"] == "1.5"  # input untouched


def test_table_tsv():
    from _de import de_table, table_tsv

    text = table_tsv(de_table([stat("G1", "1.5", "0.01", None)]))
    assert text == "gene\teffectSize\tpValue\tadjustedPValue\nG1\t1.5\t0.01\tNA\n"
