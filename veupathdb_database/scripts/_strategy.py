"""Declarative step-tree spec -> WDK steps + strategy.

Spec nodes (exactly one key each):
  {"leaf":      {"search": name, "params": {...}}}
  {"combine":   {"operator": OP, "left": node, "right": node}}
  {"transform": {"search": name, "params": {...}, "input": node}}
OP: UNION | INTERSECT | MINUS | RMINUS | LONLY | RONLY
"""
from _shaping import (
    all_search_names,
    encode_params,
    get_search_detail,
    get_search_detail_for_params,
)
from _sites import strategy_url

OPERATORS = {"UNION", "INTERSECT", "MINUS", "RMINUS", "LONLY", "RONLY"}


class SpecError(Exception):
    pass


def _kind(node):
    if not isinstance(node, dict) or len(node) != 1:
        raise SpecError(
            f"a spec node must have exactly one of leaf/combine/transform: {node!r:.120}"
        )
    kind = next(iter(node))
    if kind not in ("leaf", "combine", "transform"):
        raise SpecError(f"unknown node kind '{kind}'")
    return kind, node[kind]


def validate_spec(node):
    """Returns the search name of the leftmost leaf (used to resolve record type)."""
    kind, body = _kind(node)
    if kind == "leaf":
        if "search" not in body or not isinstance(body.get("params", {}), dict):
            raise SpecError(f"leaf needs 'search' and object 'params': {body!r:.120}")
        return body["search"]
    if kind == "combine":
        if body.get("operator") not in OPERATORS:
            raise SpecError(
                f"combine operator must be one of {sorted(OPERATORS)}, "
                f"got {body.get('operator')!r}"
            )
        first = validate_spec(body["left"])
        validate_spec(body["right"])
        return first
    # transform
    if "search" not in body or "input" not in body:
        raise SpecError(f"transform needs 'search' and 'input': {body!r:.120}")
    return validate_spec(body["input"])


def find_boolean_search(catalog, client, rt):
    listing = catalog["searches"].get(rt, [])
    name = next(
        (s["name"] for s in listing if s["name"].startswith("boolean_question_")), None
    )
    if name is None:
        raise SpecError(f"record type '{rt}' has no boolean (combine) search")
    detail = get_search_detail(client, rt, name)
    left = next(p["name"] for p in detail["parameters"] if p["name"].startswith("bq_left_op"))
    right = next(p["name"] for p in detail["parameters"] if p["name"].startswith("bq_right_op"))
    return name, left, right


def build_strategy(client, catalog, spec, name):
    first_search = validate_spec(spec)
    names = all_search_names(catalog)
    if first_search not in names:
        raise SpecError(f"unknown search '{first_search}'")
    rt = names[first_search]
    uid = client.user_id()
    bool_cache = {}

    def create(node):
        kind, body = _kind(node)
        if kind == "leaf":
            params = body.get("params", {})
            detail = get_search_detail_for_params(client, rt, body["search"], params)
            wire = encode_params(detail, params, client=client)
            step = client.post(
                f"/users/{uid}/steps",
                {"searchName": body["search"], "searchConfig": {"parameters": wire}},
                idempotent=False,
            )
            return {"stepId": step["id"]}
        if kind == "transform":
            child = create(body["input"])
            params = body.get("params", {})
            detail = get_search_detail_for_params(client, rt, body["search"], params)
            wire = encode_params(detail, params, client=client)  # input-step -> ""
            step = client.post(
                f"/users/{uid}/steps",
                {"searchName": body["search"], "searchConfig": {"parameters": wire}},
                idempotent=False,
            )
            return {"stepId": step["id"], "primaryInput": child}
        # combine
        left_tree = create(body["left"])
        right_tree = create(body["right"])
        if rt not in bool_cache:
            bool_cache[rt] = find_boolean_search(catalog, client, rt)
        bname, lparam, rparam = bool_cache[rt]
        step = client.post(
            f"/users/{uid}/steps",
            {
                "searchName": bname,
                "searchConfig": {
                    "parameters": {
                        lparam: "",
                        rparam: "",
                        "bq_operator": body["operator"],
                    }
                },
            },
            idempotent=False,
        )
        return {
            "stepId": step["id"],
            "primaryInput": left_tree,
            "secondaryInput": right_tree,
        }

    tree = create(spec)
    strat = client.post(
        f"/users/{uid}/strategies",
        {"name": name, "isPublic": False, "isSaved": False, "stepTree": tree},
        idempotent=False,
    )
    sid = strat.get("strategyId", strat.get("id"))
    detail = client.get(f"/users/{uid}/strategies/{sid}")
    return shape_strategy(client.site_id, detail)


def _count(value):
    return value if isinstance(value, int) and value >= 0 else "unmeasured"


def shape_strategy(site_id, detail):
    sid = detail.get("strategyId", detail.get("id"))
    tree = detail.get("stepTree", {})
    root = detail.get("rootStepId") or tree.get("stepId")
    steps = []
    for step_id, s in (detail.get("steps") or {}).items():
        steps.append(
            {
                "step_id": int(step_id),
                "search": s.get("searchName"),
                "displayName": s.get("customName") or s.get("displayName"),
                "count": _count(s.get("estimatedSize")),
                "valid": (s.get("validation") or {}).get("isValid"),
            }
        )
    root_count = next(
        (s["count"] for s in steps if s["step_id"] == root), "unmeasured"
    )
    return {
        "strategy_id": sid,
        "name": detail.get("name"),
        "url": strategy_url(site_id, sid),
        "root_step_id": root,
        "estimated_size": root_count,
        "steps": steps,
    }
