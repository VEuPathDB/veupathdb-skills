"""EDA study metadata pruning and sample-table assembly (pure functions; no I/O)."""
from collections import defaultdict

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
