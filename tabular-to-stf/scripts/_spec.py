"""Curation spec validator. Checks the JSON spec the curator writes; never
reads files. Returns every error found, each naming its location.

A spec field counts as present when its key is present (`"key" in d`), so a JSON
null is a present value.
"""

import json
import re
from typing import Any, Callable

from _common import is_valid_column_name
from _constants import DATA_SHAPES, DATA_TYPES, DISPLAY_TYPES, UNAMBIGUOUS_PLACEHOLDERS

SPEC_VERSION = "1.1.0"
_VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", re.ASCII)
APPROVALS = ("auto", "user", "proposed", "rejected")
ENTITY_NAME_TEXT = "/^[a-z][a-z0-9_]*$/"
_ENTITY_NAME = re.compile(r"[a-z][a-z0-9_]*")
_ABSOLUTE = re.compile(r"[\\/]|[A-Za-z]:")
_SEGMENT_SPLIT = re.compile(r"[\\/]")
NOTE_LISTS = ("flagged", "decisions", "pii", "validation")


class _Missing:
    """JS `undefined`: a key that is not there."""

    def __repr__(self) -> str:
        return "undefined"


MISSING = _Missing()


def _normalize(v: Any) -> Any:
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, list):
        return [_normalize(x) for x in v]
    if isinstance(v, dict):
        return {k: _normalize(x) for k, x in v.items()}
    return v


def js_json(v: Any) -> str:
    """JSON.stringify as used inside template literals (undefined prints as 'undefined')."""
    if v is MISSING:
        return "undefined"
    return json.dumps(_normalize(v), ensure_ascii=False, separators=(",", ":"))


def _is_obj(v: Any) -> bool:
    return isinstance(v, dict)


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and v != ""


def _is_str_array(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _is_inside_path(v: Any) -> bool:
    return _is_str(v) and _ABSOLUTE.match(v) is None and ".." not in _SEGMENT_SPLIT.split(v)


def _has(names: set[str], v: Any) -> bool:
    return isinstance(v, str) and v in names


def _key(v: Any) -> Any:
    """A hashable stand-in with JS Map-key semantics (lists and dicts by identity)."""
    if isinstance(v, (list, dict)):
        return ("id", id(v))
    if isinstance(v, bool):
        return ("bool", v)
    if isinstance(v, (int, float)):
        return ("num", float(v))
    return v


def _has_cycle(parent_of: dict, start: Any) -> bool:
    seen = set()
    n = start
    while n is not MISSING:
        k = _key(n)
        if k in seen:
            return True
        seen.add(k)
        n = parent_of.get(k, MISSING)
    return False


def parse_version(v: Any) -> tuple[int, int, int] | None:
    """(major, minor, patch) for a "MAJOR.MINOR.PATCH" string, else None."""
    m = _VERSION.fullmatch(v) if isinstance(v, str) else None
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def _check_version(v: Any, errors: list[str]) -> tuple[int, int, int] | None:
    """The spec's version if these scripts can read it; otherwise records why not."""
    have = parse_version(SPEC_VERSION)
    got = parse_version(v)
    if got is None:
        errors.append(f'specVersion: must be a version string like "{SPEC_VERSION}"')
    elif got[0] != have[0]:
        errors.append(f"specVersion: major version {got[0]} is not supported "
                      f"(these scripts support {have[0]}.x, up to {SPEC_VERSION})")
    elif got > have:
        errors.append(f"specVersion: this spec needs {v}, these scripts support up to {SPEC_VERSION}")
    else:
        return got
    return None


def _all_unambiguous(t: dict) -> bool:
    values = t.get("values")
    return isinstance(values, list) and all(v in UNAMBIGUOUS_PLACEHOLDERS for v in values)


# `auto` allowed unconditionally, never, or by a predicate on the transform.
OPS: dict[str, Callable[[dict], bool]] = {
    "trim": lambda t: True,
    "blank-placeholders": _all_unambiguous,
    "map-values": lambda t: True,
    "rename-column": lambda t: True,
    "replace-cells": lambda t: False,
    "parse-dates": lambda t: False,
    "derive-column": lambda t: False,
    "drop-column": lambda t: False,
}


def _is_string_map(m: Any) -> bool:
    return _is_obj(m) and all(isinstance(x, str) for x in m.values())


def _is_cell(x: Any) -> bool:
    return (_is_obj(x) and _is_str(x.get("id"))
            and isinstance(x.get("from"), str) and isinstance(x.get("to"), str))


def _check_transform(t: Any, i: int, entity_names: set[str], errors: list[str]) -> None:
    at = f"transforms[{i}]"
    if not _is_obj(t):
        errors.append(f"{at}: must be an object")
        return
    op_name = t.get("op", MISSING)
    auto = OPS.get(op_name) if isinstance(op_name, str) else None
    if auto is None:
        errors.append(f"{at}.op: unknown op {js_json(op_name)}")
    if not _has(entity_names, t.get("entity", MISSING)):
        errors.append(f"{at}.entity: unknown entity {js_json(t.get('entity', MISSING))}")
    if not _is_str(t.get("reason")):
        errors.append(f"{at}.reason: required")
    approval = t.get("approval", MISSING)
    if not (isinstance(approval, str) and approval in APPROVALS):
        errors.append(f"{at}.approval: must be one of {', '.join(APPROVALS)}")
    else:
        if approval == "rejected" and not _is_str(t.get("instead")):
            errors.append(f'{at}.instead: required when approval is "rejected"')
        if approval == "auto" and auto is not None and not auto(t):
            suffix = " unless values are all unambiguous placeholders" if op_name == "blank-placeholders" else ""
            errors.append(f'{at}.approval: "auto" is not allowed for {op_name}{suffix}; use "user"')
    if auto is None:
        return

    def need(field: str, ok: Callable[[Any], bool], what: str) -> None:
        if not ok(t.get(field, MISSING)):
            errors.append(f"{at}.{field}: {what}")

    def need_str(f: str) -> None:
        need(f, _is_str, "required string")

    def opt_cols() -> None:
        if "columns" in t and not (isinstance(t["columns"], list) and all(_is_str(x) for x in t["columns"])):
            errors.append(f"{at}.columns: must be an array of strings")

    if op_name == "trim":
        opt_cols()
    elif op_name == "blank-placeholders":
        opt_cols()
        need("values", lambda v: isinstance(v, list) and len(v) > 0 and all(isinstance(x, str) for x in v),
             "required non-empty array of strings")
    elif op_name == "map-values":
        need_str("column")
        need("map", _is_string_map, "required object of strings")
    elif op_name == "rename-column":
        need_str("from")
        need_str("to")
        if _is_str(t.get("from")) and t.get("from") == t.get("to"):
            errors.append(f"{at}.to: same as from ({js_json(t['from'])}); a rename must change the name")
    elif op_name == "replace-cells":
        need_str("column")
        need("cells", lambda c: isinstance(c, list) and all(_is_cell(x) for x in c),
             "required array of { id, from, to } strings")
    elif op_name == "parse-dates":
        need_str("column")
        if ("format" in t) == ("formats" in t):
            errors.append(f"{at}.formats: give either format (a string) or formats (a non-empty array of strings)")
        elif "format" in t:
            need_str("format")
        else:
            need("formats", lambda v: isinstance(v, list) and len(v) > 0 and all(_is_str(x) for x in v),
                 "required non-empty array of strings")
    elif op_name == "derive-column":
        need_str("column")
        need_str("from")
        need("map", _is_string_map, "required object of strings")
        need("default", lambda d: isinstance(d, str), "required string")
    elif op_name == "drop-column":
        need_str("column")


def _check_entity(e: Any, i: int, entity_names: set[str], errors: list[str]) -> None:
    at = f"entities[{i}]"
    if not _is_obj(e):
        errors.append(f"{at}: must be an object")
        return
    for f in ("displayName", "displayNamePlural", "file", "idColumn"):
        if not _is_str(e.get(f)):
            errors.append(f"{at}.{f}: required string")
    if _is_str(e.get("file")) and not _is_inside_path(e["file"]):
        errors.append(f'{at}.file: must be relative to inputDir, with no ".." segment (got {js_json(e["file"])})')
    if "idName" in e and not (isinstance(e["idName"], str) and is_valid_column_name(e["idName"])):
        errors.append(f"{at}.idName: invalid column name {js_json(e['idName'])}")
    if "parent" in e:
        if not _has(entity_names, e["parent"]):
            errors.append(f"{at}.parent: unknown entity {js_json(e['parent'])}")
        if not _is_str(e.get("parentColumn")):
            errors.append(f"{at}.parentColumn: required when parent is set")
    if "geo" in e:
        g = e["geo"]
        if not (_is_obj(g) and _is_str(g.get("latitude")) and _is_str(g.get("longitude"))):
            errors.append(f"{at}.geo: needs latitude and longitude column names")

    cats = e["categories"] if "categories" in e else []
    if not isinstance(cats, list):
        errors.append(f"{at}.categories: must be an array")
        return
    cat_names: set[str] = set()
    cat_parent: dict[Any, Any] = {}
    for j, c in enumerate(cats):
        cat = f"{at}.categories[{j}]"
        if not _is_obj(c) or not _is_str(c.get("category")):
            errors.append(f"{cat}.category: required string")
            continue
        if c["category"] in cat_names:
            errors.append(f"{cat}.category: duplicate {js_json(c['category'])}")
        cat_names.add(c["category"])
        if not _is_str(c.get("displayName")):
            errors.append(f"{cat}.displayName: required string")
        if "definition" in c and not isinstance(c["definition"], str):
            errors.append(f"{cat}.definition: must be a string")
        if "parentCategory" in c:
            cat_parent[c["category"]] = c["parentCategory"]
    for j, c in enumerate(cats):
        if not _is_obj(c) or "parentCategory" not in c:
            continue
        if not _has(cat_names, c["parentCategory"]):
            errors.append(f"{at}.categories[{j}].parentCategory: unknown category {js_json(c['parentCategory'])}")
        elif _has_cycle(cat_parent, c.get("category", MISSING)):
            errors.append(f"{at}.categories[{j}].parentCategory: category cycle through {js_json(c.get('category', MISSING))}")

    if not isinstance(e.get("variables"), list):
        errors.append(f"{at}.variables: must be an array")
        return
    for j, v in enumerate(e["variables"]):
        vt = f"{at}.variables[{j}]"
        if not _is_obj(v):
            errors.append(f"{vt}: must be an object")
            continue
        if not _is_str(v.get("column")):
            errors.append(f"{vt}.column: required string")
        if "name" in v and not (isinstance(v["name"], str) and is_valid_column_name(v["name"])):
            errors.append(f"{vt}.name: invalid column name {js_json(v['name'])}")
        for field, allowed in (("dataType", DATA_TYPES), ("dataShape", DATA_SHAPES), ("displayType", DISPLAY_TYPES)):
            if field in v and not (isinstance(v[field], str) and v[field] in allowed):
                errors.append(f"{vt}.{field}: must be one of {', '.join(allowed)}")
        if "parentCategory" in v and not _has(cat_names, v["parentCategory"]):
            errors.append(f"{vt}.parentCategory: unknown category {js_json(v['parentCategory'])}")
        for f in ("unit", "definition", "displayName", "providerLabel"):
            if f in v and not isinstance(v[f], str):
                errors.append(f"{vt}.{f}: must be a string")
        for f in ("ordinalLevels", "vocabularyOrder"):
            if f in v and not _is_str_array(v[f]):
                errors.append(f"{vt}.{f}: must be an array of strings")


def validate_spec(spec: Any) -> list[str]:
    errors: list[str] = []
    if not _is_obj(spec):
        return ["spec: must be an object"]
    _check_version(spec.get("specVersion"), errors)
    study = spec.get("study")
    if not _is_obj(study) or not _is_str(study.get("name")):
        errors.append("study.name: required string")
    if not _is_str(spec.get("inputDir")):
        errors.append("inputDir: required string")
    if "extraFiles" in spec and not (isinstance(spec["extraFiles"], list) and all(_is_str(x) for x in spec["extraFiles"])):
        errors.append("extraFiles: must be an array of strings")
    else:
        for i, f in enumerate(spec.get("extraFiles", [])):
            if not _is_inside_path(f):
                errors.append(f'extraFiles[{i}]: must be relative to inputDir, with no ".." segment (got {js_json(f)})')
    if "notes" in spec:
        notes = spec["notes"]
        if not _is_obj(notes):
            errors.append("notes: must be an object")
        else:
            for k in NOTE_LISTS:
                if k in notes and not _is_str_array(notes[k]):
                    errors.append(f"notes.{k}: must be an array of strings")
    entities = spec.get("entities")
    if not isinstance(entities, list) or len(entities) == 0:
        errors.append("entities: required non-empty array")
        return errors

    entity_names: set[str] = set()
    for i, e in enumerate(entities):
        name = e.get("name") if _is_obj(e) else None
        if not isinstance(name, str) or _ENTITY_NAME.fullmatch(name) is None:
            errors.append(f"entities[{i}].name: must match {ENTITY_NAME_TEXT}")
        elif name in entity_names:
            errors.append(f"entities[{i}].name: duplicate entity {js_json(name)}")
        else:
            entity_names.add(name)
    for i, e in enumerate(entities):
        _check_entity(e, i, entity_names, errors)

    roots = [e for e in entities if _is_obj(e) and "parent" not in e]
    if len(roots) != 1:
        errors.append(f"entities: need exactly one root (entity without parent), found {len(roots)}")
    parent_of = {_key(e.get("name", MISSING)): e["parent"] for e in entities if _is_obj(e) and "parent" in e}
    for i, e in enumerate(entities):
        if _is_obj(e) and "parent" in e and _has_cycle(parent_of, e.get("name", MISSING)):
            errors.append(f"entities[{i}].parent: parent cycle through {js_json(e.get('name', MISSING))}")

    transforms = spec["transforms"] if "transforms" in spec else []
    if not isinstance(transforms, list):
        errors.append("transforms: must be an array")
    else:
        for i, t in enumerate(transforms):
            _check_transform(t, i, entity_names, errors)
    return errors
