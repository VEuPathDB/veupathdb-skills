"""stf.py preview: what one transform does to its entity's table, without writing anything.

The transforms before it (for that entity, `auto` and `user` only) run first, so
the preview sees the cells the transform will see. The transform itself is
evaluated whatever its approval. For map-values, derive-column and
blank-placeholders the preview groups each column's distinct values into
matched, ambiguous and unmatched; for other ops it summarises the change.
"""

from __future__ import annotations

import copy
from collections import Counter

from _match import ValueMatcher
from _read_table import Table
from _spec import MATCH_OPS, js_json
from _transforms import TransformError, apply_transforms, value_columns, value_rule


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def _summary(items: list[tuple[str, int]]) -> str:
    return f"{_plural(len(items), 'distinct value')}, {_plural(sum(n for _, n in items), 'cell')}"


def _capped(items: list[tuple[str, int]], line, top: int, bottom: int) -> list[str]:
    """Lines for the `top` most and `bottom` least common items, with a line for those hidden between."""
    if len(items) <= top + bottom:
        return [line(v, n) for v, n in items]
    hidden = items[top:len(items) - bottom]
    return ([line(v, n) for v, n in items[:top]]
            + [f"  … {_plural(len(hidden), 'more distinct value')} ({_plural(sum(n for _, n in hidden), 'cell')})"]
            + [line(v, n) for v, n in items[len(items) - bottom:]])


def _value_section(t: dict, column: str, cells: list[str], top: int, bottom: int) -> list[str]:
    matcher, fallback = value_rule(t)
    regex = matcher.regex
    counts = sorted(Counter(cells).items(), key=lambda x: (-x[1], x[0]))
    matched, ambiguous, unmatched = [], [], []
    hits_of, empty = {}, 0
    for v, n in counts:
        hits = hits_of[v] = matcher.hits(v)
        if ValueMatcher.is_ambiguous(hits):
            ambiguous.append((v, n))
        elif hits:
            matched.append((v, n))
        elif v == "":
            empty = n
        else:
            unmatched.append((v, n))

    def matched_line(v, n):
        key, result = hits_of[v][0]
        return f"  {js_json(v)} → {js_json(result)}  ×{n:,}" + (f"  (key {js_json(key)})" if regex else "")

    def ambiguous_line(v, n):
        keys = ", ".join(f"{js_json(k)} → {js_json(r)}" for k, r in hits_of[v])
        return f"  {js_json(v)}  ×{n:,}  keys {keys}"

    def unmatched_line(v, n):
        default = f" → {js_json(fallback)} (default)" if fallback is not None else ""
        return f"  {js_json(v)}{default}  ×{n:,}"

    out = [f"Column {js_json(column)}"]
    out.append(f"Matched: {_summary(matched)}" if matched else "Matched: none")
    out += _capped(matched, matched_line, top, bottom)
    out.append(f"Ambiguous: {_summary(ambiguous)}" if ambiguous else "Ambiguous: none")
    out += [ambiguous_line(v, n) for v, n in ambiguous]
    if unmatched or empty:
        out.append(f"Unmatched: {_summary(unmatched)}" + (f"; {_plural(empty, 'empty cell')}" if empty else ""))
    else:
        out.append("Unmatched: none")
    out += _capped(unmatched, unmatched_line, top, bottom)
    return out


def preview_transform(spec: dict, table: Table, index: int, top: int = 10, bottom: int = 10) -> str:
    """The preview of spec["transforms"][index]; `table` is the input table of its entity.
    Raises TransformError if an earlier transform fails."""
    spec = copy.deepcopy(spec)
    t = spec["transforms"][index]
    approval = t.get("approval")
    t["approval"] = "user"
    entity = t["entity"]
    head = f"transforms[{index}] {t['op']} on entity {js_json(entity)}"
    if t["op"] in MATCH_OPS:
        head += f", match {t.get('match', 'exact')}"
    lines = [f"{head}, approval {approval}"]

    before, _ = apply_transforms({entity: table}, spec, upto=index, entity=entity)
    b = before[entity]
    if t["op"] in MATCH_OPS:
        for column in value_columns(t, b.headers):
            if column not in b.headers:
                lines.append(f"Column {js_json(column)}: not found")
                continue
            c = b.headers.index(column)
            lines += _value_section(t, column, [row[c] for row in b.rows], top, bottom)
        return "\n".join(lines)

    try:
        after, log = apply_transforms({entity: table}, spec, upto=index + 1, entity=entity)
    except TransformError as err:
        lines.append(f"This transform fails: {err}")
        return "\n".join(lines)
    lines.append(f"Cells changed: {log[-1]['cellsChanged']:,}")
    if after[entity].headers != b.headers:
        lines.append(f"Columns: {', '.join(b.headers)} → {', '.join(after[entity].headers)}")
    return "\n".join(lines)
