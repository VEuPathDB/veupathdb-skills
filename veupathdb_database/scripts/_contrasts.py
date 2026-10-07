"""Contrast enumeration and canonical compute bodies (pure functions; no I/O).

Canonical form: labels sorted within each group, filters sorted by
(entityId, variableId) with set values sorted, pValueFloor 1e-200, and the
method implied by the search family. The same canonical contrast always gives
the same EDA job, shared with website users and other agents.
"""
import difflib
import hashlib
import itertools
import json
import math
import re
from collections import Counter, defaultdict

from _eda import EdaError
from _samples import COUNT_VALUE_IDS, GENE_ID, NUMERIC_TYPES, summarise_variable

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


CONTROL_TOKENS = {
    "control", "ctrl", "normal", "wt", "wildtype", "untreated", "mock", "baseline", "uninfected",
    "naive", "vehicle", "healthy", "unexposed", "reference", "negative", "pre", "before", "0h", "t0", "d0",
}
CONTROL_PHRASES = ("wild type", "wild-type", "day 0", "time 0")


def is_control_label(label):
    s = str(label).strip().lower().replace("ï", "i")
    if any(p in s for p in CONTROL_PHRASES):
        return True
    return bool(CONTROL_TOKENS & set(re.split(r"[^a-z0-9]+", s)))


def _fmt(v):
    v = float(v)
    return str(int(v)) if v.is_integer() else repr(v)


def _usable_spec(meta):
    spec = meta.get("_binSpec") or {}
    try:
        return spec.get("displayRangeMin") is not None and float(spec["binWidth"]) > 0
    except (KeyError, TypeError, ValueError):
        return False


def _bin_entry(v, spec):
    """Half-open [start, end) bin of width binWidth anchored at displayRangeMin."""
    rmin, w = float(spec["displayRangeMin"]), float(spec["binWidth"])
    start = rmin + math.floor((float(v) - rmin) / w) * w
    # round away float drift (0.1 * 3 -> 0.30000000000000004) so labels and edges are clean
    lo, hi = _fmt(float(f"{start:.12g}")), _fmt(float(f"{start + w:.12g}"))
    return {"label": f"[{lo}, {hi})", "min": lo, "max": hi}


def comparator_levels(rows, meta):
    """(group entry, sample ids) per level; missing values are no level. Numeric values
    become half-open bins (veupathUtils whichValuesInBin): [v, next value) when there are
    few distinct values, else binWidth bins from the variable's _binSpec."""
    vid = meta["id"]
    by_value = defaultdict(list)
    for r in rows:
        v = r.get(vid)
        if v is not None:
            by_value[v].append(r["sampleId"])
    if meta.get("type") in NUMERIC_TYPES:
        values = sorted(by_value)
        entries = []
        if len(values) > MAX_PAIRWISE_LEVELS and _usable_spec(meta):
            bins = {}
            for v in values:
                entry = _bin_entry(v, meta["_binSpec"])
                bins.setdefault(entry["label"], (entry, []))[1].extend(by_value[v])
            entries = list(bins.values())
        else:
            for i, v in enumerate(values):
                nxt = values[i + 1] if i + 1 < len(values) else v + 1
                entries.append(({"label": _fmt(v), "min": _fmt(v), "max": _fmt(nxt)}, by_value[v]))
    else:
        entries = [({"label": str(v)}, ids) for v, ids in by_value.items()]
    return sorted(entries, key=lambda e: (-len(e[1]), e[0]["label"]))


def samples_in_group(rows, var_id, group):
    out = []
    for r in rows:
        v = r.get(var_id)
        if v is None:
            continue
        for g in group:
            if "min" in g and "max" in g:
                try:
                    x = float(v)
                except (TypeError, ValueError):
                    continue
                if float(g["min"]) <= x < float(g["max"]):
                    out.append(r["sampleId"])
                    break
            elif str(v) == g["label"]:
                out.append(r["sampleId"])
                break
    return out


def aliased(rows, a, b):
    """a and b partition the samples (that have both) identically."""
    pairs = {(r.get(a), r.get(b)) for r in rows if r.get(a) is not None and r.get(b) is not None}
    return len(pairs) >= 2 and len({x for x, _ in pairs}) == len(pairs) == len({y for _, y in pairs})


def determines(rows, a, b):
    """Every level of a maps to one level of b (a is as fine as, or finer than, b)."""
    seen = {}
    for r in rows:
        x, y = r.get(a), r.get(b)
        if x is None or y is None:
            continue
        if seen.setdefault(x, y) != y:
            return False
    return len(seen) >= 2


def _low_note(n_a, n_b):
    n = min(n_a, n_b)
    return f"low replicates (n={n} in the smaller group)" if n < LOW_REPLICATES else None


def replicate_check(n_a, n_b):
    if min(n_a, n_b) < MIN_REPLICATES:
        raise ContrastError(
            f"too few replicates (groupA n={n_a}, groupB n={n_b}); DESeq2/limma need at least "
            f"{MIN_REPLICATES} per group"
        )
    return _low_note(n_a, n_b)


def _counts_by(rows, sample_ids, var_id):
    ids = set(sample_ids)
    return Counter(r.get(var_id) for r in rows if r["sampleId"] in ids and r.get(var_id) is not None)


def _filter_for(meta, value):
    base = {"entityId": meta["entityId"], "variableId": meta["id"]}
    if meta.get("type") in NUMERIC_TYPES:
        return {**base, "type": "numberRange", "min": value, "max": value}
    return {**base, "type": "stringSet", "stringSet": [str(value)]}


def _profile(rows, meta):
    summary = summarise_variable(meta, [r.get(meta["id"]) for r in rows])
    if summary["kind"] == "identifier":
        return {"usable": [], "excluded": [], "identifier": True,
                "reason": "identifier-like (almost every sample has its own value)"}
    levels = comparator_levels(rows, meta)
    prof = {
        "usable": [(e, ids) for e, ids in levels if len(ids) >= MIN_REPLICATES],
        "excluded": [(e["label"], len(ids)) for e, ids in levels if len(ids) < MIN_REPLICATES],
        "identifier": False,
        "reason": None,
    }
    if meta.get("type") in NUMERIC_TYPES and len(levels) > MAX_PAIRWISE_LEVELS and not _usable_spec(meta):
        prof["reason"] = f"continuous with {len(levels)} distinct values: write a contrast file with numeric ranges"
    elif len(prof["usable"]) < 2:
        prof["reason"] = "fewer than 2 levels with 2+ samples"
    elif len(prof["usable"]) > MAX_PAIRWISE_LEVELS:
        prof["reason"] = f"{len(prof['usable'])} levels (> {MAX_PAIRWISE_LEVELS}): pool levels into groups in a contrast file"
    return prof


def _comparator(meta):
    return {"entityId": meta["entityId"], "variableId": meta["id"], "displayName": meta["displayName"]}


def _pair_candidates(rows, var_meta, prof, vid, base, aliases):
    meta = var_meta[vid]
    p = prof[vid]
    twins = [a["displayName"] for a in aliases if a["sameAs"] == vid]
    alias_ids = {a["variableId"] for a in aliases}
    # sorted: note order must not depend on dict order; aliases are covered by their twin
    others = sorted(z for z in var_meta if z != vid and not prof[z]["identifier"] and z not in alias_ids)
    confounders = [z for z in others if not determines(rows, z, vid)]
    stratifiers = [z for z in others if prof[z]["reason"] is None and not aliased(rows, vid, z) and not determines(rows, z, vid)]
    out = []
    for (ea, ids_a), (eb, ids_b) in itertools.combinations(p["usable"], 2):
        # One orientation per pair. The control-label match is only a hint: the agent
        # decides the reference, and a swap reuses the cached mirror job (Task 10).
        ca, cb = is_control_label(ea["label"]), is_control_label(eb["label"])
        (ga, a_ids), (gb, b_ids) = (ea, ids_a), (eb, ids_b)
        if cb and not ca:
            (ga, a_ids), (gb, b_ids) = (gb, b_ids), (ga, a_ids)
        reference = "label match" if ca != cb else "arbitrary"
        notes = []
        if reference == "label match":
            notes.append(f"reference guessed from label {ga['label']!r}: swap groups in a contrast file if "
                         "groupB is the real baseline (same statistics, sign flipped)")
        else:
            notes.append("reference unclear: groupA chosen arbitrarily; swap groups in a contrast file if "
                         "groupB is the baseline (same statistics, sign flipped)")
        if twins:
            notes.append(f"same grouping as {', '.join(twins)}: effects cannot be separated")
        if p["excluded"]:
            notes.append("levels with <2 samples left out: " + ", ".join(f"{label} ({n})" for label, n in p["excluded"]))
        low = _low_note(len(a_ids), len(b_ids))
        if low:
            notes.append(low)
        for z in confounders:
            za, zb = _counts_by(rows, a_ids, z), _counts_by(rows, b_ids, z)
            if len(za) == 1 and len(zb) == 1 and set(za) != set(zb):
                notes.append(f"groups also differ in {var_meta[z]['displayName']}: {_label(next(iter(za)))} vs {_label(next(iter(zb)))}")
        strata = []
        for z in stratifiers:
            za, zb = _counts_by(rows, a_ids, z), _counts_by(rows, b_ids, z)
            if len(za) < 2 and len(zb) < 2:
                continue
            shared = sorted((v for v in set(za) & set(zb) if za[v] >= MIN_REPLICATES and zb[v] >= MIN_REPLICATES), key=str)
            if not shared:
                continue
            zname = var_meta[z]["displayName"]
            notes.append(f"{zname} varies within the groups (the compute has no covariates): stratified versions follow")
            for v in shared:
                strata.append({
                    "comparator": _comparator(meta),
                    "groupA": canonical_group([ga]),
                    "groupB": canonical_group([gb]),
                    "reference": reference,
                    "filters": merge_filters(base, [_filter_for(var_meta[z], v)]),
                    "nA": za[v],
                    "nB": zb[v],
                    "notes": [n for n in [_low_note(za[v], zb[v])] if n] + [f"stratum of the contrast above: {zname} = {_label(v)}"],
                    "stratum": {"variableId": z, "displayName": zname, "label": _label(v)},
                })
        out.append({
            "comparator": _comparator(meta),
            "groupA": canonical_group([ga]),
            "groupB": canonical_group([gb]),
            "reference": reference,
            "filters": list(base),
            "nA": len(a_ids),
            "nB": len(b_ids),
            "notes": notes,
            "stratum": None,
        })
        out.extend(strata)
    return out


def _label(v):
    return _fmt(v) if isinstance(v, float) else str(v)


def enumerate_contrasts(rows, var_meta, base_filters=(), only_vars=None, max_candidates=MAX_CANDIDATES):
    """Deterministic candidates; the agent ranks them. Order: fewest levels first,
    categorical before numeric, featured first, then display name. At most
    max_candidates are returned (None = no cap); `truncated` says how many exist."""
    base = canonical_filters(base_filters)
    prof = {vid: _profile(rows, m) for vid, m in var_meta.items()}

    def order(vid):
        m = var_meta[vid]
        return (len(prof[vid]["usable"]), m.get("type") in NUMERIC_TYPES, not m.get("featured"), m.get("displayName", ""), vid)

    skipped, aliases, comparators = [], [], []
    for vid in sorted(var_meta, key=order):
        m, p = var_meta[vid], prof[vid]
        if p["reason"]:
            if not only_vars or vid in only_vars:
                entry = {"variableId": vid, "displayName": m["displayName"], "reason": p["reason"]}
                levels = [[e["label"], len(ids)] for e, ids in p["usable"]] + [[label, n] for label, n in p["excluded"]]
                if levels and not p["identifier"]:
                    entry["levels"] = levels
                skipped.append(entry)
            continue
        twin = next((c for c in comparators if aliased(rows, c, vid)), None)
        if twin:
            aliases.append({"variableId": vid, "displayName": m["displayName"], "sameAs": twin, "sameAsName": var_meta[twin]["displayName"]})
            continue
        comparators.append(vid)
    # aliases are found over all variables, so --vars cannot change what counts as an
    # alias; an alias named explicitly in --vars is still offered as a comparator
    alias_ids = {a["variableId"] for a in aliases}
    selected = comparators
    if only_vars:
        selected = [v for v in sorted(var_meta, key=order) if v in only_vars and (v in comparators or v in alias_ids)]
    candidates = []
    for vid in selected:
        for cand in _pair_candidates(rows, var_meta, prof, vid, base, aliases):
            cand["index"] = len(candidates) + 1
            candidates.append(cand)
    # Z nested within X: every Z level sits inside one X level (e.g. sample label within condition)
    nested = [
        {"variableId": z, "displayName": var_meta[z]["displayName"], "within": vid, "withinName": var_meta[vid]["displayName"]}
        for vid in selected
        for z in comparators
        if z != vid and determines(rows, z, vid) and not aliased(rows, z, vid)
    ]
    truncated = None
    if max_candidates is not None and len(candidates) > max_candidates:
        truncated = {"shown": max_candidates, "total": len(candidates)}
        candidates = candidates[:max_candidates]
    return {"candidates": candidates, "skipped": skipped, "aliases": aliases, "nested": nested, "truncated": truncated}


def load_contrast(obj, var_meta, var_entities, chain, base_filters=()):
    """Validate a contrast file: {"comparator": {"variableId", "entityId"?}, "groupA", "groupB", "filters"?}."""
    if not isinstance(obj, dict):
        raise ContrastError("a contrast file holds one JSON object: {comparator, groupA, groupB, filters?}")
    vid = (obj.get("comparator") or {}).get("variableId")
    if vid not in var_meta:
        if vid in var_entities:
            raise ContrastError(
                f"comparator {vid} sits on {var_entities[vid]}, which is not a parent of the expression "
                f"entity; the notebook only offers comparators on {', '.join(chain)}"
            )
        hint = difflib.get_close_matches(str(vid), list(var_meta), n=3, cutoff=0.5)
        raise ContrastError(f"unknown comparator variable {vid!r}; did you mean {hint}?")
    m = var_meta[vid]
    numeric = m.get("type") in NUMERIC_TYPES
    groups = {}
    for key in ("groupA", "groupB"):
        group = canonical_group(obj.get(key) or [])
        if not group:
            raise ContrastError(f"{key} is empty")
        if numeric and any("min" not in g or "max" not in g for g in group):
            raise ContrastError(f"{key}: numeric comparator {vid} needs min and max on every entry (bins are [min, max))")
        vocab = m.get("vocabulary")
        if vocab and not numeric:
            bad = [g["label"] for g in group if g["label"] not in vocab]
            if bad:
                hints = {b: difflib.get_close_matches(b, vocab, n=2, cutoff=0.5) for b in bad}
                raise ContrastError(f"unknown {m['displayName']} label(s) {bad}; did you mean {hints}? vocabulary: {vocab}")
        groups[key] = group
    return {
        "comparator": _comparator(m),
        "groupA": groups["groupA"],
        "groupB": groups["groupB"],
        "filters": merge_filters(base_filters, obj.get("filters") or []),
        "reference": "contrast file",
        "notes": [],
        "stratum": None,
    }
