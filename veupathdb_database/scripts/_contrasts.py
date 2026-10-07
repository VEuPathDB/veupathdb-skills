"""Contrast enumeration and canonical compute bodies (pure functions; no I/O).

Canonical form: labels sorted within each group, filters sorted by
(entityId, variableId) with set values sorted, pValueFloor 1e-200, and the
method implied by the search family. The same canonical contrast always gives
the same EDA job, shared with website users and other agents.
"""
import hashlib
import itertools
import json

from _eda import EdaError
from _samples import COUNT_VALUE_IDS, GENE_ID

PLUGIN_DE = "differentialexpression"
PLUGIN_PCA = "dimensionalityreduction"
P_VALUE_FLOOR = "1e-200"
METHODS = ("DESeq", "limma")
NOTEBOOK_METHODS = {"differentialExpressionNotebook": "DESeq", "antibodyArrayNotebook": "limma"}
VALUE_PREFERENCE = ("SEQUENCE_READ_COUNT", "SEQUENCE_READ_COUNT_SENSE", "NORMALIZED_INTENSITY", "NORMALIZED_EXPRESSION")
MIN_REPLICATES = 2
LOW_REPLICATES = 3
MAX_PAIRWISE_LEVELS = 6
MAX_CACHE_CHECKS = 30
MAX_CANDIDATES = 50  # crossed designs multiply strata; past this, narrow with --vars


class ContrastError(EdaError):
    pass


def _compact(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def job_id(plugin, body):
    """EDA job id: MD5 of ["plugin", key-sorted compact JSON of the body] (service-eda
    JobIDs.kt). Matches live ids for label-based configs. The server's jobID is
    authoritative: Java may render numeric filter values differently."""
    payload = json.dumps([plugin, _compact(body)], separators=(",", ":"), ensure_ascii=False)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def canonical_group(group):
    out = []
    for g in group:
        item = {k: str(g[k]) for k in ("label", "min", "max") if g.get(k) is not None}
        if "label" not in item:
            raise ContrastError(f"every group entry needs a label: {g!r}")
        out.append(item)
    return sorted(out, key=lambda g: (g["label"], g.get("min", ""), g.get("max", "")))


def canonical_filters(filters):
    out = []
    for f in filters or []:
        f = dict(f)
        for key in ("stringSet", "numberSet", "dateSet"):
            if key in f:
                f[key] = sorted(f[key], key=str)
        out.append(f)
    return sorted(out, key=lambda f: (f.get("entityId", ""), f.get("variableId", ""), _compact(f)))


def merge_filters(*lists):
    merged = {}
    for f in canonical_filters(list(itertools.chain(*lists))):
        key = (f.get("entityId"), f.get("variableId"))
        if key in merged and _compact(merged[key]) != _compact(f):
            raise ContrastError(f"conflicting filters on {key[1]} ({key[0]}): {merged[key]} vs {f}")
        merged[key] = f
    return canonical_filters(list(merged.values()))


def de_config(expr_entity_id, value_var, comparator, group_a, group_b, method):
    if method not in METHODS:
        raise ContrastError(f"method must be one of {METHODS}, got {method!r}")
    return {
        "identifierVariable": {"entityId": expr_entity_id, "variableId": GENE_ID},
        "valueVariable": {"entityId": expr_entity_id, "variableId": value_var},
        "comparator": {
            "variable": {"entityId": comparator["entityId"], "variableId": comparator["variableId"]},
            "groupA": canonical_group(group_a),
            "groupB": canonical_group(group_b),
        },
        "differentialExpressionMethod": method,
        "pValueFloor": P_VALUE_FLOOR,
    }


def data_format(value_var):
    return "rawCounts" if value_var in COUNT_VALUE_IDS else "normalizedValues"


def pca_config(expr_entity_id, value_var, n_pcs=None):
    """The notebook's PCA config (no nPCs, so the job matches website runs);
    an explicit n_pcs makes a separate job."""
    cfg = {
        "identifierVariable": {"entityId": expr_entity_id, "variableId": GENE_ID},
        "valueVariable": {"entityId": expr_entity_id, "variableId": value_var},
        "dataFormat": data_format(value_var),
    }
    if n_pcs is not None:
        cfg["nPCs"] = int(n_pcs)
    return cfg


def compute_body(study_id, config, filters):
    """Exactly the body the WSF plugin POSTs, so job ids match WDK steps and notebooks."""
    if study_id.startswith("DS_"):
        raise ContrastError(f"compute bodies take the STUDY_ id, not {study_id}; resolve it via /permissions")
    return {"studyId": study_id, "filters": canonical_filters(filters), "config": config, "derivedVariables": []}


def choose_value_var(expr, requested=None):
    available = expr["valueIds"]
    if requested:
        if requested not in available:
            raise ContrastError(
                f"--value-var {requested} is not on {expr['entityId']}; available: {', '.join(available)}"
            )
        return requested, None
    for pref in VALUE_PREFERENCE:
        if pref in available:
            others = [v for v in available if v != pref]
            note = f"using {pref}; also available: {', '.join(others)} (--value-var)" if others else None
            return pref, note
    return available[0], None


def choose_method(notebook, value_var, requested="auto"):
    implied = NOTEBOOK_METHODS.get(notebook) or ("DESeq" if value_var in COUNT_VALUE_IDS else "limma")
    if requested in (None, "auto"):
        return implied, None
    if requested not in METHODS:
        raise ContrastError(f"--method must be auto, DESeq or limma, got {requested!r}")
    if requested == implied:
        return requested, None
    return requested, (
        f"--method {requested} differs from the {implied} the website uses here: "
        "a separate job, not shared with website users"
    )
