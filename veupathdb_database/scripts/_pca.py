"""PCA output parsing and reporting. The EDA compute returns only per-sample scores;
variance explained is parsed from computed-variable display names (fragile: a
candidate server-side change), and every association is computed locally."""
import math
import re

from _eda import EdaError
from _samples import NUMERIC_TYPES
from _stats import outliers, score_against_pc

_VARIANCE = re.compile(r"PC\s*(\d+)\s*\(\s*([0-9.]+)\s*%\s*variance\s*\)", re.IGNORECASE)
_PC = re.compile(r"PC\d+")


def _num(cell):
    try:
        x = float(cell)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def parse_scores(tsv):
    lines = [line for line in tsv.splitlines() if line.strip()]
    if not lines:
        raise EdaError("PCA tabular output is empty")
    header = lines[0].split("\t")
    cols = [i for i, h in enumerate(header) if _PC.fullmatch(h)]
    if not cols:
        raise EdaError(f"no PC columns in the PCA output header: {header}")
    scores = {}
    for line in lines[1:]:
        cells = line.split("\t")
        scores[cells[0]] = [_num(cells[i]) if i < len(cells) else None for i in cols]
    return [header[i] for i in cols], scores


def parse_variance(meta):
    out = {}
    for v in meta.get("variables", []):
        m = _VARIANCE.search(v.get("displayName", ""))
        out[v["variableSpec"]["variableId"]] = float(m.group(2)) if m else None
    return out


def pca_report(pcs, scores, variance, rows, var_meta, outlier_pcs=2):
    by_sample = {r["sampleId"]: r for r in rows}
    sample_ids = [s for s in scores if s in by_sample]
    tracks, not_scored = {}, []
    for k, pc in enumerate(pcs):
        pc_values = [scores[s][k] for s in sample_ids]
        ranked = []
        for vid, meta in var_meta.items():
            kind = "continuous" if meta.get("type") in NUMERIC_TYPES else "categorical"
            res = score_against_pc(kind, [by_sample[s].get(vid) for s in sample_ids], pc_values)
            entry = {"pc": pc, "variableId": vid, "displayName": meta["displayName"], **res}
            (not_scored if "not_scored" in res else ranked).append(entry)
        tracks[pc] = sorted(ranked, key=lambda e: (-e["value"], e["variableId"]))
    return {
        "pcs": [{"pc": pc, "variance": variance.get(pc)} for pc in pcs],
        "samples": len(sample_ids),
        "unmatched": sorted(set(scores) - set(by_sample)),
        "tracks": tracks,
        "notScored": not_scored,
        "outliers": outliers({s: scores[s][:outlier_pcs] for s in sample_ids}),
        "scores": {s: dict(zip(pcs, scores[s])) for s in sample_ids},
    }


def render_pca(report, top=5):
    lines = [
        f"PCA {report['datasetId']}  value={report['valueVariable']}  dataFormat={report['dataFormat']}  "
        f"job {report['jobId']}  {report['samples']} samples"
    ]
    for pc in report["pcs"]:
        var = f"{pc['variance']:g}% variance" if pc["variance"] is not None else "variance unknown"
        lines.append(f"{pc['pc']} ({var}) tracks:")
        ranked = report["tracks"][pc["pc"]][:top]
        if not ranked:
            lines.append("  (no scorable variables)")
        for e in ranked:
            if e["stat"] == "r":
                lines.append(f"  {e['displayName']} ({e['variableId']})  r={e['r']:+.2f} R²={e['r2']:.2f}  n={e['n']}")
            else:
                lines.append(f"  {e['displayName']} ({e['variableId']})  eta²={e['eta2']:.2f}  n={e['n']}, {e['levels']} levels")
    o = report["outliers"]
    if o.get("not_scored"):
        lines.append(f"outliers: not scored ({o['not_scored']})")
    else:
        head = f"outliers (standardised distance > {o['threshold']:g} in PC1–PC{o['pcs']})"
        if o["samples"]:
            found = ", ".join(f"{s['sampleId']} ({s['distance']})" for s in o["samples"])
            lines.append(f"{head}: {found}  → candidates for --filters")
        else:
            lines.append(f"{head}: none")
    grouped = {}
    for e in report["notScored"]:
        grouped.setdefault((e["displayName"], e["variableId"], e["not_scored"]), []).append(e["pc"])
    for (name, vid, reason), pcs in grouped.items():
        lines.append(f"not scored: {name} ({vid}) on {', '.join(pcs)}: {reason}")
    if report["unmatched"]:
        lines.append(f"PCA samples missing from the sample table: {', '.join(report['unmatched'][:10])}")
    lines += [f"note: {n}" for n in report["notes"]]
    return lines
