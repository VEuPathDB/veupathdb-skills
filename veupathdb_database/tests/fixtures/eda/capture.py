"""Capture live EDA fixtures for the offline tests.

Run from veupathdb_database/ with a registered-user token (wdk.py login):
    uv run --with httpx python tests/fixtures/eda/capture.py
Overwrites the JSON/TSV files next to this script. Starts (or reuses) two shared
compute jobs on the heat-shock study; both are the website notebook's defaults.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "scripts"))

from _client import eda_client, load_token  # noqa: E402
from _eda import compute_file, volcano, wait_for_job  # noqa: E402

HEATSHOCK = "DS_e973eadd57"
ANTIBODY = "DS_24d441b301"  # GenesByAntibodyArrayEdaSubset_PlasmoDB_Crompton_Mali_AntibodyArray_RSRC
GENE = "ENT_fd574cd6"
GENE_ID = "VEUPATHDB_GENE_ID"
KEEP_STATISTICS = 200


def save(name, data):
    path = HERE / name
    text = data if isinstance(data, str) else json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path.name}", file=sys.stderr)


def trim_gene_vocab(entity):
    for v in entity.get("variables", []):
        if v["id"] == GENE_ID and "vocabulary" in v:
            v["vocabulary"] = v["vocabulary"][:5]
    for child in entity.get("children", []):
        trim_gene_vocab(child)


def main():
    c = eda_client("plasmodb", token=load_token())
    per = c.get("/permissions")["perDataset"]
    save("permissions.json", {"perDataset": {ds: per[ds] for ds in (HEATSHOCK, ANTIBODY)}})
    for tag, ds in (("heatshock", HEATSHOCK), ("antibody", ANTIBODY)):
        sid = per[ds]["studyId"]
        study = c.get(f"/studies/{sid}")["study"]
        trim_gene_vocab(study["rootEntity"])
        save(f"study_{tag}.json", study)
        root = study["rootEntity"]  # the sample entity in both fixture studies
        ids = [v["id"] for v in root["variables"] if v.get("type") != "category"]
        rows = c.post(f"/studies/{sid}/entities/{root['id']}/tabular", {"filters": [], "outputVariableIds": ids})
        save(f"tabular_{tag}_sample.json", rows)

    sid = per[HEATSHOCK]["studyId"]
    gene_var = {"entityId": GENE, "variableId": GENE_ID}
    value_var = {"entityId": GENE, "variableId": "SEQUENCE_READ_COUNT_SENSE"}
    de = {
        "studyId": sid,
        "filters": [],
        "derivedVariables": [],
        "config": {
            "identifierVariable": gene_var,
            "valueVariable": value_var,
            "comparator": {
                "variable": {"entityId": "ENT_8151325d", "variableId": "VAR_081ab087"},
                "groupA": [{"label": "normal"}],
                "groupB": [{"label": "febrile"}],
            },
            "differentialExpressionMethod": "DESeq",
            "pValueFloor": "1e-200",
        },
    }
    pca = {
        "studyId": sid,
        "filters": [],
        "derivedVariables": [],
        "config": {"identifierVariable": gene_var, "valueVariable": value_var, "dataFormat": "rawCounts"},
    }
    de_st = wait_for_job(c, "differentialexpression", de)
    pca_st = wait_for_job(c, "dimensionalityreduction", pca)
    vol = volcano(c, de)
    vol["totalStatistics"] = len(vol["statistics"])
    vol["statistics"] = vol["statistics"][:KEEP_STATISTICS]
    save("volcano_heatshock.json", vol)
    save("pca_heatshock_tabular.tsv", compute_file(c, "dimensionalityreduction", pca, "tabular"))
    save("pca_heatshock_meta.json", json.loads(compute_file(c, "dimensionalityreduction", pca, "meta")))
    save(
        "jobs.json",
        {
            "de_heatshock": {"body": de, "jobID": de_st["jobID"], "status": de_st["status"]},
            "pca_heatshock": {"body": pca, "jobID": pca_st["jobID"], "status": pca_st["status"]},
        },
    )


if __name__ == "__main__":
    main()
