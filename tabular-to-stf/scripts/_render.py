"""Renders a curation spec plus input tables to STF file texts: study.yaml,
entity-<name>.{tsv,yaml} and curation-notes.md (render_stf, pure). Every problem
found is collected and raised as one RenderError. render_to_dir is the CLI side:
it reads the inputs, writes the STF directory, the saved spec and raw-data/.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _common import infer_type, is_valid_iso_date, to_column_name, unique_column_names
from _constants import RAW_DIR, SAVED_SPEC
from _geo import GEO, is_latitude_name, is_longitude_name, validator_sees_latitude, validator_sees_longitude
from _notes import render_notes
from _read_table import Table, read_table
from _spec import validate_spec
from _transforms import TransformError, apply_transforms
from _yaml import dump_yaml


class RenderError(Exception):
    def __init__(self, messages: list[str]):
        super().__init__("\n".join(messages))
        self.messages = messages


SKIPPED = ("proposed", "rejected")
MAX_LISTED = 10


def _looks_lat(s: str) -> bool:
    return is_latitude_name(s) or validator_sees_latitude(s)


def _looks_lng(s: str) -> bool:
    return is_longitude_name(s) or validator_sees_longitude(s)


def _passes_lat(s: str) -> bool:
    return is_latitude_name(s) and validator_sees_latitude(s)


def _passes_lng(s: str) -> bool:
    return is_longitude_name(s) and validator_sees_longitude(s)


_A = re.ASCII
_NUMBER = re.compile(r"-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?", _A)
_INTEGER = re.compile(r"-?(0|[1-9]\d*)", _A)


# Leading zeros are refused for numbers: the loader reads such a column as text
PARSES = {
    "string": lambda v: True,
    "integer": lambda v: _INTEGER.fullmatch(v) is not None,
    "number": lambda v: _NUMBER.fullmatch(v) is not None,
    "longitude": lambda v: _NUMBER.fullmatch(v) is not None,
    "date": is_valid_iso_date,
}


def _js_string(x: Any) -> str:
    """JS String(x), for spec fields the validator does not type-check."""
    if isinstance(x, str):
        return x
    if isinstance(x, bool):
        return "true" if x else "false"
    if x is None:
        return "null"
    if isinstance(x, float):
        if math.isnan(x):
            return "NaN"
        if math.isinf(x):
            return "Infinity" if x > 0 else "-Infinity"
        if x.is_integer() and abs(x) < 1e21:
            return str(int(x))
        return repr(x)
    if isinstance(x, list):
        return ",".join("" if v is None else _js_string(v) for v in x)
    if isinstance(x, dict):
        return "[object Object]"
    return str(x)


def _js_truthy(x: Any) -> bool:
    return isinstance(x, (list, dict)) or bool(x)


def _tree_order(entities: list[dict]) -> list[str]:
    """Entity names in pre-order from the root, siblings in spec order."""
    out: list[str] = []

    def visit(name: str) -> None:
        out.append(name)
        for e in entities:
            if "parent" in e and e["parent"] == name:
                visit(e["name"])

    root = next((e for e in entities if "parent" not in e), None)
    if root is not None:
        visit(root["name"])
    return out


def _original_headers(entity: str, input_headers: list[str], transforms: list[dict]) -> dict[str, str | None]:
    """Current header -> original input header (None for derived columns), following applied transforms."""
    origin: dict[str, str | None] = {h: h for h in input_headers}
    for t in transforms:
        if t["entity"] != entity or t.get("approval") in SKIPPED:
            continue
        if t["op"] == "rename-column":
            origin[t["to"]] = origin.get(t["from"])
            origin.pop(t["from"], None)
        if t["op"] == "derive-column":
            origin[t["column"]] = None
        if t["op"] == "drop-column":
            origin.pop(t["column"], None)
    return origin


@dataclass(eq=False)
class _Col:
    idx: int
    header: str
    name: str
    explicit: bool
    label: str | None
    v: dict | None = None
    fixed: bool = False
    entity: str | None = None
    level: int = 0
    geo: str | None = None


def _assign_names(cols: list[_Col], entity: str, errors: list[str]) -> None:
    """The parent ID column (`fixed`) keeps the parent's own ID name, since study-wrangler joins on it.
    Explicit names are kept too (a clash with either is an error); auto names get _2, _3, ... suffixes."""
    by_name: dict[str, _Col] = {}
    kept = [c for c in cols if c.fixed] + [c for c in cols if c.explicit and not c.fixed]
    for c in kept:
        other = by_name.get(c.name)
        if other is not None and other.fixed:
            errors.append(f'{entity}: output column name "{c.name}" for column "{c.header}" is the ID column name of parent entity '
                          f'"{other.entity}"; the parent ID column must keep that name, so choose another')
        elif other is not None:
            errors.append(f'{entity}: output column name "{c.name}" is used by both "{other.header}" and "{c.header}"')
        else:
            by_name[c.name] = c
    order = kept + [c for c in cols if not c.explicit and not c.fixed]
    unique = unique_column_names([c.name for c in order])
    for c, name in zip(order, unique):
        if not c.explicit and not c.fixed:
            c.name = name


def _list_or_null(items: list) -> list | None:
    # The JS wrote `key:` with no items for an empty list, which reads back as null
    return list(items) if items else None


def _variable_yaml(v: dict) -> dict:
    out: dict[str, Any] = {"variable": v["variable"]}
    if v.get("provider_label") is not None:
        out["provider_label"] = [v["provider_label"]]
    out["display_name"] = v["display_name"]
    for key in ("definition", "data_type", "data_shape", "unit"):
        if key in v:
            out[key] = v[key]
    for key in ("ordinal_levels", "vocabulary_order"):
        if key in v:
            out[key] = _list_or_null(v[key])
    for key in ("is_multi_valued", "multi_value_delimiter", "parent_category", "stable_id", "display_type"):
        if key in v:
            out[key] = v[key]
    return out


def _category_yaml(c: dict) -> dict:
    out = {"category": c["category"], "display_name": c["displayName"]}
    if "definition" in c:
        out["definition"] = c["definition"]
    if "parentCategory" in c:
        out["parent_category"] = c["parentCategory"]
    return out


def _entity_yaml(e: dict, id_cols: list[_Col], variables: list[dict]) -> str:
    ids = []
    for c in id_cols:
        item: dict[str, Any] = {"id_column": c.name, "entity_name": c.entity}
        if c.level:
            item["entity_level"] = c.level
        if c.label is not None:
            item["provider_label"] = [c.label]
        ids.append(item)
    return dump_yaml({
        "name": e["name"],
        "display_name": e["displayName"],
        "display_name_plural": e["displayNamePlural"],
        "id_columns": ids,
        "variables": [_variable_yaml(v) for v in variables],
        "categories": [_category_yaml(c) for c in e.get("categories") or []],
    })


def _check_geo(e: dict, cols: list[_Col], geo_cols: list[_Col], errors: list[str]) -> None:
    """Coordinate-like columns outside the geo pair. Every column is checked by name and by provider label."""
    others = [c for c in cols if not any(c is g for g in geo_cols)]
    if e.get("geo"):
        def axis(s: str) -> str | None:
            return "latitude" if _looks_lat(s) else "longitude" if _looks_lng(s) else None
        for c in others:
            where = f"{e['name']}.{c.name}"
            if axis(c.name):
                errors.append(f'{where}: name "{c.name}" looks like a {axis(c.name)} to EDA, but {e["name"]} already has geo '
                              "coordinates; give it another name with a rename-column transform or the variable's name")
            elif c.label is not None and axis(c.label):
                errors.append(f'{where}: provider_label "{c.label}" looks like a {axis(c.label)} to the EDA validator, but '
                              f"{e['name']} already has geo coordinates; set the variable's providerLabel to a wording without it")
        return
    hits = []
    for c in cols:
        texts = [c.name] + ([c.label] if c.label is not None else [])
        if any(_looks_lat(t) for t in texts):
            hits.append(c.name)
        if any(_looks_lng(t) for t in texts):
            hits.append(c.name)
    if len(hits) >= 2:
        errors.append(f"{e['name']}: {len(hits)} columns look like coordinates ({', '.join(hits)}); EDA validation fails on "
                      "more than one. Declare the pair as geo, or rename the others")


def _render_entity(e: dict, spec: dict, input_table: Table, table: Table, parent: dict | None,
                   errors: list[str], decisions: list[str]) -> dict | None:
    headers, rows = table.headers, table.rows
    name = e["name"]

    def at(h: str) -> int:
        return headers.index(h) if h in headers else -1

    origin = _original_headers(name, input_table.headers, spec.get("transforms") or [])
    start_errors = len(errors)

    id_idx = at(e["idColumn"])
    if id_idx < 0:
        errors.append(f'{name}: ID column "{e["idColumn"]}" not found after transforms')
    has_parent = "parent" in e
    parent_idx = at(e["parentColumn"]) if has_parent else -1
    if has_parent and parent_idx < 0:
        errors.append(f'{name}: parent column "{e["parentColumn"]}" not found after transforms')
    id_idxs = (id_idx, parent_idx)

    seen: set[str] = set()
    var_cols: list[_Col] = []
    for v in e["variables"]:
        idx = at(v["column"])
        if idx < 0:
            errors.append(f'{name}: variable column "{v["column"]}" not found after transforms')
            continue
        if idx in id_idxs:
            errors.append(f'{name}: variable column "{v["column"]}" is an ID column')
            continue
        if v["column"] in seen:
            errors.append(f'{name}: variable column "{v["column"]}" is listed twice')
            continue
        seen.add(v["column"])
        label = v["providerLabel"] if v.get("providerLabel") is not None else origin.get(v["column"])
        var_cols.append(_Col(idx=idx, header=v["column"], name=v["name"] if "name" in v else to_column_name(v["column"]),
                             explicit="name" in v, label=label, v=v))
    for i, h in enumerate(headers):
        if i not in id_idxs and h not in seen:
            errors.append(f"unaccounted column {name}.{h}: list it in variables or remove it with drop-column")
    if len(errors) > start_errors:
        return None

    geo_cols: list[_Col] = []
    if e.get("geo"):
        for axis, passes in (("latitude", _passes_lat), ("longitude", _passes_lng)):
            c = next((x for x in var_cols if x.header == e["geo"][axis]), None)
            if c is None:
                errors.append(f'{name}: geo.{axis} column "{e["geo"][axis]}" must be listed in variables')
                continue
            if not passes(c.name):
                decisions.append(f"`{name}.{c.name}` is the {axis}; written as `{axis}` so that both EDA's inference "
                                 "and its validator recognise it.")
                c.name = axis
                c.explicit = True
            c.geo = axis
            geo_cols.append(c)

    id_cols: list[_Col] = []
    if parent is not None:
        id_cols.append(_Col(idx=parent_idx, header=e["parentColumn"], name=parent["idName"], explicit=False, fixed=True,
                            entity=parent["name"], level=-1, label=origin.get(e["parentColumn"])))
    id_cols.append(_Col(idx=id_idx, header=e["idColumn"], name=e["idName"] if "idName" in e else to_column_name(e["idColumn"]),
                        explicit="idName" in e, entity=name, label=origin.get(e["idColumn"])))
    cols = id_cols + var_cols
    _assign_names(cols, name, errors)
    _check_geo(e, cols, geo_cols, errors)

    for c in var_cols:
        if "providerLabel" in c.v:
            was = origin.get(c.header)
            source = "derived column" if was is None else f'original header "{was}"'
            decisions.append(f'`{name}.{c.name}`: provider_label set to "{c.v["providerLabel"]}" ({source}).')

    def row_id(r: int) -> str:
        return f"row {r + 1}" if rows[r][id_idx] == "" else rows[r][id_idx]

    for c in cols:
        bad = [row_id(r) for r in range(len(rows)) if re.search(r"[\t\n\r]", rows[r][c.idx])]
        if len(bad) == 1:
            errors.append(f"{name}.{c.header}: value in row {bad[0]} contains a tab or line break")
        elif bad:
            more = ", ..." if len(bad) > MAX_LISTED else ""
            errors.append(f"{name}.{c.header}: values in rows {', '.join(bad[:MAX_LISTED])}{more} contain a tab or line break")

    variables = []
    for c in var_cols:
        v = c.v
        values = [r[c.idx] for r in rows]
        g = GEO[c.geo] if c.geo else None
        declared = g["data_type"] if g else v.get("dataType")
        data_type = declared if declared is not None else infer_type(values)["data_type"]
        if declared:
            bad_rows = [r for r in range(len(rows)) if values[r] != "" and not PARSES[declared](values[r])]
            if bad_rows:
                n = len(bad_rows)
                listed = ", ".join(f"{json.dumps(values[r], ensure_ascii=False)} ({row_id(r)})" for r in bad_rows[:MAX_LISTED])
                errors.append(f"{name}.{c.header}: declared {declared} but {n} value{'' if n == 1 else 's'} "
                              f"do{'es' if n == 1 else ''} not parse: {listed}{', ...' if n > MAX_LISTED else ''}")
        if g:
            data_shape = "continuous"
        elif v.get("dataShape") is not None:
            data_shape = v["dataShape"]
        else:
            data_shape = "ordinal" if "ordinalLevels" in v else "categorical" if data_type == "string" else "continuous"
        # Keys present only where the JS value was not undefined
        var: dict[str, Any] = {
            "variable": c.name,
            "provider_label": c.label,
            "display_name": _js_string(v.get("displayName") if v.get("displayName") is not None
                                       else c.label if c.label is not None else c.name),
            "data_type": data_type,
            "data_shape": data_shape,
        }
        for key, field in (("definition", "definition"), ("unit", "unit"), ("parent_category", "parentCategory"),
                           ("multi_value_delimiter", "multiValueDelimiter")):
            if field in v:
                var[key] = _js_string(v[field])
        for key, field in (("ordinal_levels", "ordinalLevels"), ("vocabulary_order", "vocabularyOrder")):
            if field in v and _js_truthy(v[field]):
                var[key] = [_js_string(x) for x in v[field]]
        if "isMultiValued" in v:
            var["is_multi_valued"] = _js_truthy(v["isMultiValued"])
        if g:
            var["stable_id"] = g["stable_id"]
            var["display_type"] = g["display_type"]
        else:
            if "stableId" in v:
                var["stable_id"] = _js_string(v["stableId"])
            if "displayType" in v:
                var["display_type"] = v["displayType"]
        variables.append(var)

    own_id = id_cols[-1]
    header = [f"{c.name} \\\\ Descriptors" if c is own_id else c.name for c in cols]
    out = ["\t".join(header)] + ["\t".join(row[c.idx] for c in cols) for row in rows]
    return {"idName": own_id.name, "tsv": "\n".join(out) + "\n", "yaml": _entity_yaml(e, id_cols, variables)}


def render_stf(spec: dict, tables: dict[str, Table], source_dir: str = RAW_DIR) -> tuple[dict[str, str], list[dict]]:
    """Returns (files, log). `tables` maps entity name to its input Table.
    `source_dir` is how curation-notes.md refers to the input files' folder."""
    spec_errors = validate_spec(spec)
    if spec_errors:
        raise RenderError(spec_errors)
    missing = [f"{e['name']}: no input table" for e in spec["entities"] if e["name"] not in tables]
    if missing:
        raise RenderError(missing)

    try:
        transformed, log = apply_transforms(tables, spec)
    except TransformError as err:
        raise RenderError([str(err)]) from None

    errors: list[str] = []
    decisions: list[str] = []
    files: dict[str, str] = {}
    done: dict[str, dict] = {}
    order = _tree_order(spec["entities"])
    by_name = {e["name"]: e for e in spec["entities"]}
    for name in order:
        e = by_name[name]
        parent = done.get(e["parent"]) if "parent" in e else None
        if "parent" in e and parent is None:
            continue  # the parent failed; its errors are already listed
        r = _render_entity(e, spec, tables[name], transformed[name], parent, errors, decisions)
        if r is None:
            continue
        done[name] = {"name": name, "idName": r["idName"]}
        files[f"entity-{name}.tsv"] = r["tsv"]
        files[f"entity-{name}.yaml"] = r["yaml"]
    if errors:
        raise RenderError(errors)

    files["study.yaml"] = dump_yaml({"name": spec["study"]["name"], "entities": order})
    sources = [{"entity": e["name"], "path": f"{source_dir}/{e['file']}", "rows": len(tables[e["name"]].rows)}
               for e in spec["entities"]]
    sources += [{"path": f"{source_dir}/{f}"} for f in spec.get("extraFiles") or []]
    files["curation-notes.md"] = render_notes(spec, log, sources=sources, decisions=decisions)
    return files, log


def _write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def render_to_dir(spec_path: Path, out_dir: Path, copy_raw: bool = True) -> list[Path]:
    """Renders spec_path into out_dir, with raw-data/ copies of the inputs unless copy_raw is False.
    The saved spec reads from raw-data/, so the folder re-renders on its own. Inputs are never modified.
    Returns the paths written: the STF files, the saved spec, then the raw-data copies."""
    spec_path = Path(spec_path)
    out_dir = Path(os.path.abspath(out_dir))
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec_errors = validate_spec(spec)
    if spec_errors:
        raise RenderError(spec_errors)
    input_dir = spec["inputDir"] if os.path.isabs(spec["inputDir"]) else os.path.abspath(spec_path.parent / spec["inputDir"])

    if out_dir.exists() and any(out_dir.iterdir()) and not (out_dir / SAVED_SPEC).exists():
        raise ValueError(f"{out_dir} is not empty and has no {SAVED_SPEC}; choose an empty or new directory")

    tables = {e["name"]: read_table(Path(input_dir) / e["file"]) for e in spec["entities"]}
    files, _ = render_stf(spec, tables, source_dir=RAW_DIR if copy_raw else input_dir)

    # Plan the raw-data copies before writing anything: a same-named file with other bytes is an error
    raw_dir = out_dir / RAW_DIR
    copies: list[tuple[bytes, Path]] = []
    if copy_raw and Path(os.path.abspath(input_dir)) != raw_dir:
        names = list(dict.fromkeys([*(e["file"] for e in spec["entities"]), *(spec.get("extraFiles") or [])]))
        for name in names:
            source = Path(input_dir) / name
            target = raw_dir / name
            data = source.read_bytes()
            if target.exists():
                if target.read_bytes() != data:
                    raise ValueError(f"{RAW_DIR}/{name} differs from {source}; inputs are immutable, so render into a new directory")
            else:
                copies.append((data, target))
    elif copy_raw:
        for name in spec.get("extraFiles") or []:
            if not (raw_dir / name).exists():
                raise ValueError(f"extra file not found: {raw_dir / name}")

    out_dir.mkdir(parents=True, exist_ok=True)
    for data, target in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    saved = {**spec, "inputDir": RAW_DIR if copy_raw else input_dir}
    written = {**files, SAVED_SPEC: json.dumps(saved, indent=2, ensure_ascii=False) + "\n"}
    for name, text in written.items():
        _write_text(out_dir / name, text)
    return [out_dir / name for name in written] + [target for _, target in copies]
