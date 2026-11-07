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

from _common import is_valid_iso_date
from _match import ValueMatcher
from _read_table import Table
from _spec import js_json

SKIPPED = ("proposed", "rejected")
_AMBIGUOUS = object()

# What JavaScript's String.prototype.trim strips (differs from str.strip).
_JS_WHITESPACE = (
    "\t\n\v\f\r           "
    "       　﻿"
)

_TOKENS = {
    "YYYY": "([0-9]{4})", "YY": "([0-9]{2})",
    "DD": "([0-9]{2})", "MM": "([0-9]{2})", "D": "([0-9]{1,2})", "M": "([0-9]{1,2})",
}
_TOKEN_ORDER = ("YYYY", "YY", "DD", "MM", "D", "M")
ISO_FORMAT = "YYYY-MM-DD"


class TransformError(ValueError):
    pass


LIST_CAP = 10


def _listed(items: list[str]) -> str:
    """The first LIST_CAP items, comma-separated, then "and N more", so an error
    stays readable when a transform fails on thousands of rows."""
    shown = ", ".join(items[:LIST_CAP])
    return shown if len(items) <= LIST_CAP else f"{shown} and {len(items) - LIST_CAP:,} more"


def date_formats(t: dict) -> list[str]:
    """A parse-dates transform's formats: `formats`, or the single `format`."""
    return list(t["formats"]) if "formats" in t else [t["format"]]


def value_rule(t: dict) -> tuple[ValueMatcher, str | None]:
    """The matcher for a MATCH_OPS transform, and the value for cells no key matches
    (derive-column's default; None means the cell stays as it is)."""
    regex = t.get("match") == "regex"
    if t["op"] == "blank-placeholders":
        return ValueMatcher({v: "" for v in t["values"]}, regex), None
    return ValueMatcher(t["map"], regex), t["default"] if t["op"] == "derive-column" else None


def value_columns(t: dict, headers: list[str]) -> list[str]:
    """The columns a MATCH_OPS transform reads."""
    if t["op"] == "map-values":
        return [t["column"]]
    if t["op"] == "derive-column":
        return [t["from"]]
    return list(t["columns"]) if t.get("columns") is not None else list(headers)


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
            order.append(tok)
            i += len(tok)
        else:
            pattern += re.escape(fmt[i])
            i += 1
    rx = re.compile(pattern)

    def parse(value):
        m = rx.fullmatch(value)
        if not m:
            return None
        p = {}
        for i, tok in enumerate(order):
            n = int(m.group(i + 1))
            p[tok[0]] = 2000 + n if tok == "YY" else n  # YY always means 20YY
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

    def value_rule_for(indexes):
        """A cached cell -> new value function for a MATCH_OPS transform; fails on ambiguous cells."""
        matcher, fallback = value_rule(t)
        if not matcher.regex:
            # Exact keys are unique, so no cell is ambiguous: a plain lookup, no extra pass.
            m = matcher.mapping
            return lambda v: m[v] if v in m else (v if fallback is None else fallback)
        cache = {}
        # Keys that all give one result cannot disagree, so skip the ambiguity pass.
        can_disagree = len(set(matcher.mapping.values())) > 1 or any("$" in v for v in matcher.mapping.values())

        def resolve(v):
            if v not in cache:
                hits = matcher.hits(v)
                if can_disagree and ValueMatcher.is_ambiguous(hits):
                    cache[v] = _AMBIGUOUS
                else:
                    cache[v] = hits[0][1] if hits else (v if fallback is None else fallback)
            return cache[v]

        if not can_disagree:
            return resolve
        rid = _id_index(table, id_column, renames)
        ambiguous, values = [], {}
        for r, row in enumerate(table.rows):
            bad = [row[c] for c in indexes if resolve(row[c]) is _AMBIGUOUS]
            if bad:
                ambiguous.append(row[rid] if rid >= 0 else f"row {r + 1}")
                values.update(dict.fromkeys(bad))
        if ambiguous:
            name = table.headers[indexes[0]] if len(indexes) == 1 else ", ".join(table.headers[c] for c in indexes)
            raise TransformError(
                f"{where}: values in column {js_json(name)} match more than one key with different results "
                f"for row IDs: {_listed(ambiguous)} (values {_listed([js_json(v) for v in values])}); "
                f"tighten the patterns or settle them with replace-cells before this transform "
                f"(stf.py preview shows the keys)"
            )
        return resolve

    if op == "trim":
        return with_ids({"cellsChanged": map_cells(cols(), lambda v: v.strip(_JS_WHITESPACE))})
    if op == "blank-placeholders":
        indexes = cols()
        return with_ids({"cellsChanged": map_cells(indexes, value_rule_for(indexes))})
    if op == "map-values":
        c = col(t["column"])
        return with_ids({"column": t["column"], "cellsChanged": map_cells([c], value_rule_for([c]))})
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
        formats = date_formats(t)
        parsers = [_date_parser(f) for f in formats]
        rid = _id_index(table, id_column, renames)
        bad = []
        ambiguous = []
        out = []
        for r, row in enumerate(table.rows):
            v = row[c]
            if v == "":
                out.append("")
                continue
            # A cell already in ISO form counts as one more reading, so a listed
            # format that reads it as a different date makes it ambiguous.
            readings = {v} if is_valid_iso_date(v) else set()
            readings.update(iso for iso in (p(v) for p in parsers) if iso is not None)
            row_id = row[rid] if rid >= 0 else f"row {r + 1}"
            if not readings:
                bad.append(row_id)
            elif len(readings) > 1:
                ambiguous.append(row_id)
            out.append(next(iter(readings)) if len(readings) == 1 else None)
        problems = []
        if bad:
            which = f"format {formats[0]}" if len(formats) == 1 else f"any of the formats {', '.join(formats)}"
            problems.append(
                f"values in column {js_json(t['column'])} do not match {which} and are not "
                f"{ISO_FORMAT} dates for row IDs: {_listed(bad)}"
            )
        if ambiguous:
            problems.append(
                f"values in column {js_json(t['column'])} read as different dates under more than one "
                f"format (counting {ISO_FORMAT}) for row IDs: {_listed(ambiguous)}; "
                f"settle them with replace-cells before this transform"
            )
        if problems:
            raise TransformError(f"{where}: {'; '.join(problems)}")
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
        resolve = value_rule_for([src])
        table.headers.append(t["column"])
        for row in table.rows:
            row.append(resolve(row[src]))
        return {"column": t["column"], "cellsChanged": 0}
    if op == "drop-column":
        c = col(t["column"])
        del table.headers[c]
        for row in table.rows:
            del row[c]
        return {"column": t["column"], "cellsChanged": 0}
    raise TransformError(f"{where}: unknown op")


def apply_transforms(tables: dict[str, Table], spec: dict, *, upto: int | None = None,
                     entity: str | None = None) -> tuple[dict[str, Table], list[dict]]:
    """Runs the transforms with index < upto (all if None); with entity, only that entity's,
    and the others are not logged. Logged indexes are the spec's."""
    out = {name: _copy_table(t) for name, t in tables.items()}
    id_columns = {e["name"]: e.get("idColumn") for e in spec.get("entities") or []}
    transforms = spec.get("transforms") or []
    log = []
    for index, t in enumerate(transforms):
        if upto is not None and index >= upto:
            break
        if entity is not None and t["entity"] != entity:
            continue
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
