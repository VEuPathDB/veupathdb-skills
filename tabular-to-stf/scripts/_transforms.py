"""Applies the spec's ordered transforms to the input tables. Works on copies;
inputs are never modified. `proposed` and `rejected` transforms are logged
but not applied.

The log counts changed cells for every transform. For `user` transforms it
also lists `ids`, the IDs of the rows with a changed cell, in row order; not
for `auto` ones, which may touch millions of rows.

Row IDs (replace-cells, parse-dates errors, log ids) are the values in the
entity's idColumn, which the spec names as it is *after* renames. A transform
that runs before the producing rename-column finds the column under its
pre-rename name instead.
"""

from __future__ import annotations

import dataclasses
import datetime
import re

from _read_table import Table
from _spec import js_json

SKIPPED = ("proposed", "rejected")

# What JavaScript's String.prototype.trim strips (differs from str.strip).
_JS_WHITESPACE = (
    "\t\n\v\f\r           "
    "       　﻿"
)

_TOKENS = {"YYYY": "([0-9]{4})", "DD": "([0-9]{2})", "MM": "([0-9]{2})", "D": "([0-9]{1,2})", "M": "([0-9]{1,2})"}
_TOKEN_ORDER = ("YYYY", "DD", "MM", "D", "M")


class TransformError(ValueError):
    pass


def _copy_table(t: Table) -> Table:
    return dataclasses.replace(t, headers=list(t.headers), rows=[list(r) for r in t.rows])


def _describe(entity, index, op):
    return f'entity "{entity}", transforms[{index}] ({op})'


def _col_index(table, name, entity, index, op):
    try:
        return table.headers.index(name)
    except ValueError:
        raise TransformError(f"{_describe(entity, index, op)}: column {js_json(name)} not found") from None


def _id_index(table, id_column, renames):
    """idColumn's current index, following renames in the spec that have not run yet.
    A name seen twice means the renames form a cycle (or a no-op), so the column is not there."""
    seen = set()
    name = id_column
    while name not in seen:
        if name in table.headers:
            return table.headers.index(name)
        seen.add(name)
        r = next((x for x in renames if x.get("to") == name), None)
        if r is None:
            return -1
        name = r.get("from")
    return -1


def _date_parser(fmt):
    order = []
    pattern = ""
    i = 0
    while i < len(fmt):
        tok = next((t for t in _TOKEN_ORDER if fmt.startswith(t, i)), None)
        if tok:
            pattern += _TOKENS[tok]
            order.append(tok[0])
            i += len(tok)
        else:
            pattern += re.escape(fmt[i])
            i += 1
    rx = re.compile(pattern)

    def parse(value):
        m = rx.fullmatch(value)
        if not m:
            return None
        p = {k: int(m.group(i + 1)) for i, k in enumerate(order)}
        if "Y" not in p or "M" not in p or "D" not in p:
            return None
        y, mo, d = p["Y"], p["M"], p["D"]
        # JS Date.UTC maps years 0-99 to 1900-1999, so the round-trip check rejects them.
        if y < 100:
            return None
        try:
            datetime.date(y, mo, d)
        except ValueError:
            return None
        return f"{y:04d}-{mo:02d}-{d:02d}"

    return parse


def _apply_one(t, index, table, id_column, renames):
    op = t["op"]
    where = _describe(t["entity"], index, op)

    def col(name):
        return _col_index(table, name, t["entity"], index, op)

    def cols():
        # JS treats an empty columns array as given (truthy): zero columns.
        if t.get("columns") is not None:
            return [col(c) for c in t["columns"]]
        return list(range(len(table.headers)))

    # Changed-row IDs are kept only for user transforms (see the module docstring).
    track = t.get("approval") == "user"
    idc = _id_index(table, id_column, renames) if track else -1
    changed = []

    def note_row(row, r):
        if track:
            changed.append(row[idc] if idc >= 0 else f"row {r + 1}")

    def with_ids(result):
        return {**result, "ids": changed} if track else result

    def map_cells(indexes, fn):
        n = 0
        for r, row in enumerate(table.rows):
            hit = False
            for c in indexes:
                nxt = fn(row[c])
                if nxt != row[c]:
                    row[c] = nxt
                    n += 1
                    hit = True
            if hit:
                note_row(row, r)
        return n

    if op == "trim":
        return with_ids({"cellsChanged": map_cells(cols(), lambda v: v.strip(_JS_WHITESPACE))})
    if op == "blank-placeholders":
        values = t["values"]
        return with_ids({"cellsChanged": map_cells(cols(), lambda v: "" if v in values else v)})
    if op == "map-values":
        c = col(t["column"])
        m = t["map"]
        return with_ids({"column": t["column"], "cellsChanged": map_cells([c], lambda v: m[v] if v in m else v)})
    if op == "rename-column":
        c = col(t["from"])
        if t["from"] != t["to"] and t["to"] in table.headers:
            raise TransformError(f"{where}: column {js_json(t['to'])} already exists")
        table.headers[c] = t["to"]
        return {"column": t["to"], "cellsChanged": 0}
    if op == "replace-cells":
        c = col(t["column"])
        rid = _id_index(table, id_column, renames)
        if rid < 0:
            raise TransformError(f"{where}: ID column {js_json(id_column)} not found")
        by_id = {r[rid]: r for r in table.rows}
        n = 0
        for cell in t["cells"]:
            row = by_id.get(cell["id"])
            if row is None:
                raise TransformError(f"{where}: row ID {js_json(cell['id'])} not found")
            if row[c] != cell["from"]:
                raise TransformError(
                    f"{where}: row ID {js_json(cell['id'])} column {js_json(t['column'])} is "
                    f"{js_json(row[c])}, spec expects {js_json(cell['from'])} (stale spec?)"
                )
            if cell["to"] != row[c]:
                row[c] = cell["to"]
                n += 1
                changed.append(cell["id"])
        return with_ids({"column": t["column"], "cellsChanged": n})
    if op == "parse-dates":
        c = col(t["column"])
        parse = _date_parser(t["format"])
        rid = _id_index(table, id_column, renames)
        bad = []
        out = []
        for r, row in enumerate(table.rows):
            if row[c] == "":
                out.append("")
                continue
            iso = parse(row[c])
            if iso is None:
                bad.append(row[rid] if rid >= 0 else f"row {r + 1}")
            out.append(iso)
        if bad:
            raise TransformError(
                f"{where}: values in column {js_json(t['column'])} do not match format "
                f"{t['format']} for row IDs: {', '.join(bad)}"
            )
        n = 0
        for r, row in enumerate(table.rows):
            if row[c] != out[r]:
                row[c] = out[r]
                n += 1
                note_row(row, r)
        return with_ids({"column": t["column"], "cellsChanged": n})
    if op == "derive-column":
        src = col(t["from"])
        if t["column"] in table.headers:
            raise TransformError(f"{where}: column {js_json(t['column'])} already exists")
        table.headers.append(t["column"])
        m = t["map"]
        for row in table.rows:
            row.append(m[row[src]] if row[src] in m else t["default"])
        return {"column": t["column"], "cellsChanged": 0}
    if op == "drop-column":
        c = col(t["column"])
        del table.headers[c]
        for row in table.rows:
            del row[c]
        return {"column": t["column"], "cellsChanged": 0}
    raise TransformError(f"{where}: unknown op")


def apply_transforms(tables: dict[str, Table], spec: dict) -> tuple[dict[str, Table], list[dict]]:
    out = {name: _copy_table(t) for name, t in tables.items()}
    id_columns = {e["name"]: e.get("idColumn") for e in spec.get("entities") or []}
    transforms = spec.get("transforms") or []
    log = []
    for index, t in enumerate(transforms):
        entry = {
            "index": index,
            "op": t["op"],
            "entity": t["entity"],
            "approval": t.get("approval"),
            "cellsChanged": 0,
        }
        if "column" in t:
            entry["column"] = t["column"]
        log.append(entry)
        if t.get("approval") in SKIPPED:
            continue
        table = out.get(t["entity"])
        if table is None:
            raise TransformError(f"{_describe(t['entity'], index, t['op'])}: no table for entity")
        later = [
            x for x in transforms[index + 1:]
            if x["op"] == "rename-column" and x["entity"] == t["entity"] and x.get("approval") not in SKIPPED
        ]
        entry.update(_apply_one(t, index, table, id_columns.get(t["entity"]), later))
    return out, log
