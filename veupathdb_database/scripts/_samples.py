"""EDA study metadata pruning and sample-table assembly (pure functions; no I/O)."""
import math
from collections import Counter, defaultdict

from _eda import EdaError

GENE_ID = "VEUPATHDB_GENE_ID"
VALUE_IDS = (
    "SEQUENCE_READ_COUNT",
    "SEQUENCE_READ_COUNT_SENSE",
    "SEQUENCE_READ_COUNT_ANTISENSE",
    "NORMALIZED_EXPRESSION",
    "NORMALIZED_INTENSITY",
)
COUNT_VALUE_IDS = VALUE_IDS[:3]
NUMERIC_TYPES = ("number", "integer")
HIDDEN = {"everywhere", "variableTree"}
DEF_MAX = 120
IDENT_MIN_DISTINCT = 20
IDENT_COVERAGE = 0.9
VOCAB_TOP = 10
MAX_TABULAR_ROWS = 5000


class SampleError(EdaError):
    pass


def index_entities(root):
    """Entity id -> {"entity": raw entity, "parent": parent id or None}."""
    index = {}

    def walk(entity, parent):
        index[entity["id"]] = {"entity": entity, "parent": parent}
        for child in entity.get("children", []):
            walk(child, entity["id"])

    walk(root, None)
    return index


def ancestors(index, entity_id):
    """Ancestor entity ids, nearest first (the order /tabular prepends their keys)."""
    out = []
    parent = index[entity_id]["parent"]
    while parent is not None:
        out.append(parent)
        parent = index[parent]["parent"]
    return out


def expression_entities(index):
    found = []
    for eid, node in index.items():
        variables = {v["id"]: v for v in node["entity"].get("variables", [])}
        values = [v for v in VALUE_IDS if v in variables]
        if GENE_ID in variables and values:
            found.append(
                {
                    "entityId": eid,
                    "displayName": node["entity"].get("displayName", eid),
                    "geneCount": variables[GENE_ID].get("distinctValuesCount"),
                    "valueIds": values,
                }
            )
    return found


def pick_expression_entity(index, entity_id=None):
    found = expression_entities(index)
    if not found:
        raise SampleError(f"not DE-ready: no entity has {GENE_ID} plus one of {', '.join(VALUE_IDS)}")
    listing = "; ".join(f"{e['entityId']} \"{e['displayName']}\"" for e in found)
    if entity_id:
        for e in found:
            if e["entityId"] == entity_id:
                return e
        raise SampleError(f"--entity {entity_id} is not an expression entity; choose one of: {listing}")
    if len(found) > 1:
        raise SampleError(f"study has {len(found)} expression entities ({listing}); pass --entity ID")
    return found[0]


def _var_item(v, entity_id, depth):
    item = {
        "kind": "variable",
        "id": v["id"],
        "entityId": entity_id,
        "displayName": v.get("displayName", v["id"]),
        "type": v.get("type"),
        "dataShape": v.get("dataShape"),
        "featured": bool(v.get("isFeatured")),
        "depth": depth,
    }
    if v.get("units"):
        item["units"] = v["units"]
    definition = (v.get("definition") or "").strip()
    if definition:
        item["definition"] = definition if len(definition) <= DEF_MAX else definition[: DEF_MAX - 1] + "…"
    if v.get("vocabulary"):
        item["vocabulary"] = v["vocabulary"]
    dd = v.get("distributionDefaults") or {}
    if v.get("type") in NUMERIC_TYPES and "binWidth" in dd:
        item["_binSpec"] = {
            "displayRangeMin": dd.get("rangeMin"),
            "displayRangeMax": dd.get("rangeMax"),
            "binWidth": dd["binWidth"],
        }
    return item


def _drop_empty_categories(items):
    keep = []
    for i, item in enumerate(items):
        if item["kind"] == "variable":
            keep.append(item)
            continue
        j = i + 1
        while j < len(items) and items[j]["depth"] > item["depth"]:
            if items[j]["kind"] == "variable":
                keep.append(item)
                break
            j += 1
    return keep


def prune_entity(entity):
    """Visible variables in tree order (category headings kept only above variables).

    A variable's parentId may name a sibling variable (a category) or something
    else; anything that is not a sibling makes it a root. Hidden variables are
    dropped but their children are still shown at the hidden node's depth.
    """
    variables = entity.get("variables", [])
    by_id = {v["id"]: v for v in variables}
    kids = defaultdict(list)
    for v in variables:
        parent = v.get("parentId")
        kids[parent if parent in by_id else None].append(v)
    out = []

    def order(v):
        return (v.get("displayOrder", 10**6), v.get("displayName", ""))

    def walk(parent_key, depth):
        for v in sorted(kids.get(parent_key, []), key=order):
            hidden = bool(HIDDEN & set(v.get("hideFrom") or []))
            if not hidden:
                if v.get("type") == "category":
                    out.append({"kind": "category", "id": v["id"], "displayName": v.get("displayName", v["id"]), "depth": depth})
                else:
                    out.append(_var_item(v, entity["id"], depth))
            walk(v["id"], depth if hidden else depth + 1)

    walk(None, 0)
    return _drop_empty_categories(out)


def variable_meta(index, entity_ids):
    """Visible variables of the given entities: var id -> variable item."""
    meta = {}
    for eid in entity_ids:
        for item in prune_entity(index[eid]["entity"]):
            if item["kind"] == "variable":
                meta[item["id"]] = item
    return meta


def all_var_entities(index):
    return {
        v["id"]: eid
        for eid, node in index.items()
        for v in node["entity"].get("variables", [])
        if v.get("type") != "category"
    }


def convert_value(meta, raw):
    if raw is None or raw == "":
        return None
    if meta.get("type") in NUMERIC_TYPES:
        try:
            value = float(raw)
        except ValueError:
            return None
        return value if math.isfinite(value) else None
    return raw


def build_sample_table(fetch_tabular, index, expr_entity_id, var_meta):
    """Join the expression entity's ancestors into one row per sample.

    fetch_tabular(entity_id, variable_ids) returns /tabular rows: header first,
    then own key, ancestor keys (nearest first), variable values.
    """
    chain = ancestors(index, expr_entity_id)
    if not chain:
        raise SampleError(f"expression entity {expr_entity_id} has no parent sample entity")
    records, by_entity = {}, {}
    for eid in chain:
        ids = [vid for vid, m in var_meta.items() if m["entityId"] == eid]
        rows = fetch_tabular(eid, ids)
        header, data = rows[0], rows[1:]
        n_anc = len(ancestors(index, eid))
        var_cols = header[1 + n_anc:]
        table = {}
        for row in data:
            vals = {
                vid: convert_value(var_meta[vid], cell)
                for vid, cell in zip(var_cols, row[1 + n_anc:])
                if vid in var_meta
            }
            table[row[0]] = {"anc": row[1:1 + n_anc], "vals": vals}
        records[eid] = table
        by_entity[eid] = [rec["vals"] for rec in table.values()]
    out = []
    for key, rec in records[chain[0]].items():
        row = {"sampleId": key, **rec["vals"]}
        for depth, anc_key in enumerate(rec["anc"]):
            anc = records[chain[depth + 1]].get(anc_key)
            if anc:
                row.update(anc["vals"])
        out.append(row)
    return {"entityId": chain[0], "rows": out, "byEntity": by_entity}


def summarise_variable(meta, values):
    present = [v for v in values if v is not None]
    out = {"n": len(present), "missing": len(values) - len(present)}
    if meta.get("type") in NUMERIC_TYPES:
        out["kind"] = "continuous"
        if present:
            out.update(
                min=min(present),
                max=max(present),
                mean=sum(present) / len(present),
                distinct=len(set(present)),
            )
        return out
    counts = Counter(present)
    out["distinct"] = len(counts)
    n_distinct = len(counts)
    if (n_distinct > IDENT_MIN_DISTINCT and n_distinct >= IDENT_COVERAGE * len(present)) or (
        n_distinct == len(present) and len(present) >= 3
    ):
        out["kind"] = "identifier"
        return out
    out["kind"] = "categorical"
    out["levels"] = [[k, n] for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))]
    return out


def _fmt_num(x):
    return f"{x:g}" if isinstance(x, float) else str(x)


def variable_line(item, summary):
    star = "*" if item.get("featured") else " "
    indent = "  " * (item["depth"] + 1)
    units = f" ({item['units']})" if item.get("units") else ""
    head = f"{indent}{star}{item['id']}  {item['displayName']}{units}"
    kind = summary.get("kind")
    if kind == "identifier":
        return f"{head}  [identifier: {summary['distinct']} distinct / {summary['n']} records]"
    if summary.get("unavailable"):
        return f"{head}  [{item.get('dataShape') or item.get('type')}]  ({summary['unavailable']})"
    shape = item.get("dataShape") or item.get("type")
    if kind == "continuous":
        if summary["n"]:
            detail = (
                f"{_fmt_num(summary['min'])}–{_fmt_num(summary['max'])}, "
                f"mean {_fmt_num(round(summary['mean'], 3))}, {summary['missing']} missing"
            )
        else:
            detail = f"no values, {summary['missing']} missing"
    else:
        levels = summary.get("levels", [])
        detail = " · ".join(f"{label} {n}" for label, n in levels[:VOCAB_TOP])
        if len(levels) > VOCAB_TOP:
            detail += f" … {len(levels) - VOCAB_TOP} more"
        if summary.get("missing"):
            detail += f", {summary['missing']} missing"
    return f"{head}  [{shape}]  {detail}"


def render_study(dataset, expr, sections, others):
    lines = [f"{dataset['studyId']} ({dataset['datasetId']}) \"{dataset['displayName']}\""]
    desc = dataset.get("description")
    if desc:
        lines.append("  " + (desc if len(desc) <= 1000 else desc[:999] + "…"))
    lines.append(
        f"DE-ready: gene entity {expr['entityId']} \"{expr['displayName']}\" — "
        f"{GENE_ID} ({expr['geneCount']}), values: {', '.join(expr['valueIds'])}"
    )
    for s in sections:
        rec = f"{s['records']} of {s['total']} records" if s["records"] != s["total"] else f"{s['total']} records"
        lines.append(f"{s['entityId']} \"{s['displayName']}\" — {rec}")
        if s.get("note"):
            lines.append(f"  ({s['note']})")
        for item, summary in s["items"]:
            if item["kind"] == "category":
                lines.append(f"{'  ' * (item['depth'] + 1)}{item['displayName']}:")
            else:
                lines.append(variable_line(item, summary))
    for o in others:
        lines.append(
            f"{o['entityId']} \"{o['displayName']}\" — {o['records']} records "
            "(not an ancestor of the expression entity: not usable as a comparator)"
        )
    return lines


def study_json(dataset, expr, sections, others, table, filters):
    def clean(item):
        return {k: v for k, v in item.items() if not k.startswith("_") and k != "vocabulary"}

    return {
        "dataset": dataset,
        "expression": expr,
        "filters": filters,
        "entities": [
            {
                "entityId": s["entityId"],
                "displayName": s["displayName"],
                "records": s["records"],
                "total": s["total"],
                "note": s["note"],
                "variables": [{**clean(i), **({"summary": sm} if sm else {})} for i, sm in s["items"]],
            }
            for s in sections
        ],
        "otherEntities": others,
        "samples": table["rows"] if table else None,
    }


def summarise_from_distribution(meta, dist):
    """Per-variable summary from /distribution when the joint table is unavailable."""
    stats = dist.get("statistics") or {}
    out = {"n": stats.get("numVarValues", 0), "missing": stats.get("numMissingCases", 0), "source": "distribution"}
    distinct = stats.get("numDistinctValues", 0)
    if meta.get("type") in NUMERIC_TYPES:
        out.update(kind="continuous", distinct=distinct)
        if out["n"]:
            out.update(min=stats.get("subsetMin"), max=stats.get("subsetMax"), mean=stats.get("subsetMean"))
        return out
    out["distinct"] = distinct
    if distinct > IDENT_MIN_DISTINCT and distinct >= IDENT_COVERAGE * out["n"]:
        out["kind"] = "identifier"
        return out
    levels = [[b["binLabel"], b["value"]] for b in dist.get("histogram", []) if b.get("value")]
    out["kind"] = "categorical"
    out["levels"] = sorted(levels, key=lambda kv: (-kv[1], str(kv[0])))
    return out


FILTER_FIELDS = {
    "stringSet": ("stringSet",),
    "numberSet": ("numberSet",),
    "dateSet": ("dateSet",),
    "numberRange": ("min", "max"),
    "dateRange": ("min", "max"),
    "longitudeRange": ("left", "right"),
}


def validate_filters(filters, index):
    """Check EDA subset filters against the study metadata, with suggestions."""
    import difflib

    variables = {
        eid: {v["id"]: v for v in node["entity"].get("variables", []) if v.get("type") != "category"}
        for eid, node in index.items()
    }
    for f in filters:
        if not isinstance(f, dict):
            raise SampleError(f"each filter must be an object, got {f!r}")
        eid, vid, ftype = f.get("entityId"), f.get("variableId"), f.get("type")
        if eid not in variables:
            hint = difflib.get_close_matches(str(eid), list(variables), n=3, cutoff=0.5)
            raise SampleError(f"filter entity {eid!r} is not in this study; did you mean {hint}?")
        if vid not in variables[eid]:
            hint = difflib.get_close_matches(str(vid), list(variables[eid]), n=3, cutoff=0.5)
            raise SampleError(f"filter variable {vid!r} is not on {eid}; did you mean {hint}?")
        if ftype not in FILTER_FIELDS:
            raise SampleError(f"filter type {ftype!r} is not supported; use one of {sorted(FILTER_FIELDS)}")
        missing = [k for k in FILTER_FIELDS[ftype] if k not in f]
        if missing:
            raise SampleError(f"{ftype} filter on {vid} needs {missing}")
        vocab = variables[eid][vid].get("vocabulary")
        if ftype == "stringSet" and vocab:
            bad = [s for s in f["stringSet"] if s not in vocab]
            if bad:
                hints = {b: difflib.get_close_matches(str(b), vocab, n=2, cutoff=0.5) for b in bad}
                raise SampleError(f"unknown value(s) {bad} for {vid}; did you mean {hints}? vocabulary: {vocab[:20]}")
        if ftype in ("numberRange", "dateRange"):
            try:
                reversed_range = f["min"] > f["max"]
            except TypeError:
                raise SampleError(
                    f"{ftype} filter on {vid} has min {f['min']!r} and max {f['max']!r} of different types"
                ) from None
            if reversed_range:
                raise SampleError(f"{ftype} filter on {vid} has min > max")
    return filters
