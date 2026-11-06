"""curation-notes.md from the spec and the transform log: what was received,
the entity tree, every change (as replayable pseudo-code), what was flagged
and decided, and validation. Pure.
"""

import json
from typing import Iterable

from _constants import SAVED_SPEC
from _transforms import date_formats

COUNTED = ("trim", "blank-placeholders", "map-values", "parse-dates")
MAX_IDS = 10


def q(s) -> str:
    return json.dumps(s, ensure_ascii=False)


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _columns_target(t: dict) -> str:
    columns = t.get("columns")
    if columns is None:
        return f"`{t['entity']}` (all columns)"
    if len(columns) == 1:
        return f"`{t['entity']}.{columns[0]}`"
    return f"`{t['entity']}` (columns {', '.join(f'`{c}`' for c in columns)})"


def _pairs(m: dict) -> str:
    return ", ".join(f"{q(k)} → {q(v)}" for k, v in m.items())


def _describe(t: dict) -> tuple[str, str]:
    """(target, text) for one transform, e.g. `participant.age`, "80+" → "80" (row P012)."""
    op = t["op"]
    column = f"`{t['entity']}.{t.get('column')}`"
    if op == "trim":
        return _columns_target(t), "trim whitespace"
    if op == "blank-placeholders":
        return _columns_target(t), f"blank {', '.join(q(v) for v in t['values'])}"
    if op == "map-values":
        return column, _pairs(t["map"])
    if op == "rename-column":
        return f"`{t['entity']}.{t['from']}`", f"rename to {q(t['to'])}"
    if op == "replace-cells":
        groups: dict[str, list] = {}
        for c in t["cells"]:
            groups.setdefault(f"{q(c['from'])} → {q(c['to'])}", []).append(c["id"])
        text = "; ".join(f"{k} ({'row' if len(ids) == 1 else 'rows'} {', '.join(ids)})" for k, ids in groups.items())
        return column, text
    if op == "parse-dates":
        return column, f"parse dates {' or '.join(date_formats(t))} → YYYY-MM-DD"
    if op == "derive-column":
        m = f"{_pairs(t['map'])}, otherwise {q(t['default'])}" if t["map"] else f"always {q(t['default'])}"
        return column, f"new column from `{t['from']}`: {m}"
    if op == "drop-column":
        return column, "drop column"
    return f"`{t['entity']}`", op


def _row_ids(t: dict, entry: dict | None) -> str:
    """' (rows A, B and 3 more)' for a user change; auto changes keep counts only, whatever their size."""
    ids = (entry or {}).get("ids")
    if t.get("approval") != "user" or not ids:
        return ""
    shown = ", ".join(ids[:MAX_IDS])
    more = f" and {len(ids) - MAX_IDS} more" if len(ids) > MAX_IDS else ""
    return f" ({'row' if len(ids) == 1 else 'rows'} {shown}{more})"


def _line(t: dict, entry: dict | None = None) -> str:
    target, text = _describe(t)
    count = f", {plural(entry['cellsChanged'], 'cell')} changed{_row_ids(t, entry)}" if entry and t["op"] in COUNTED else ""
    instead = f" Instead: {t.get('instead')}" if t.get("approval") == "rejected" else ""
    return f"- {target}: {text}{count}. Reason: {t.get('reason')}{instead}"


def _bullets(items: list) -> str:
    return "\n".join(f"- {x}" for x in items) if items else "None."


def render_notes(spec: dict, log: list[dict], sources: list[dict] | None = None, decisions: Iterable[str] = ()) -> str:
    """`sources`: [{entity?, path, rows?}], the input files as the notes should name them.
    `decisions`: extra lines for Decisions and answers (from the renderer)."""
    transforms = spec.get("transforms") or []
    notes = spec.get("notes") or {}
    entities = spec["entities"]
    src = sources if sources is not None else [{"entity": e["name"], "path": e["file"]} for e in entities]
    by_entity = {s["entity"]: s for s in src if s.get("entity")}
    study = spec["study"]
    out = [
        f"# Curation notes: {study['name']}", "",
        f"This directory was rendered from [{SAVED_SPEC}]({SAVED_SPEC}), the curation spec that records every change below. "
        f"To re-render it, run `uv run <skill>/scripts/stf.py render <this directory>/{SAVED_SPEC} <this directory>`, "
        "where `<skill>` is the `tabular-to-stf` skill's folder.", "",
        "## Study", "",
    ]

    out.append(f"- Name: {study['name']}")
    if study.get("description"):
        out.append(f"- Description: {study['description']}")
    out.append("- Source files:")
    for s in src:
        rows = f" ({plural(s['rows'], 'row')})" if "rows" in s else ""
        out.append(f"  - `{s['path']}`{rows}")
    if any(e.get("geo") for e in entities):
        out += ["", "Before `eda` validation or export, run `map_entities(study, infer_geo_variables_for_eda)`"]

    out += ["", "## Entity tree", ""]

    def visit(e: dict, depth: int) -> None:
        source = by_entity.get(e["name"])
        path = source["path"] if source is not None and source.get("path") is not None else e["file"]
        link = f", child of `{e['parent']}` via `{e.get('parentColumn')}`" if "parent" in e else ""
        out.append(f"{'  ' * depth}- `{e['name']}` ({e['displayNamePlural']}): `{path}`, ID `{e['idColumn']}`{link}")
        for c in entities:
            if "parent" in c and c["parent"] == e["name"]:
                visit(c, depth + 1)

    root = next((e for e in entities if "parent" not in e), None)
    if root is not None:
        visit(root, 0)

    entries = [(transforms[entry["index"]], entry) for entry in log]

    def pick(approval: str) -> list:
        return [(t, entry) for t, entry in entries if t.get("approval") == approval]

    out += ["", "## Routine normalisation", ""]
    auto = pick("auto")
    out.append("\n".join(_line(t, entry) for t, entry in auto) if auto else "None.")

    out += ["", "## Data changes", ""]
    user = pick("user")
    out.append("\n".join(_line(t, entry) for t, entry in user) if user else "None.")
    proposed = pick("proposed")
    if proposed:
        out += ["", "Proposed, not applied:", "", "\n".join(_line(t) for t, _ in proposed)]
    rejected = pick("rejected")
    if rejected:
        out += ["", "Rejected:", "", "\n".join(_line(t) for t, _ in rejected)]

    out += ["", "## Flagged, not changed", ""]
    out.append(_bullets([*(notes.get("flagged") or []), *(f"PII: {p}" for p in notes.get("pii") or [])]))

    out += ["", "## Decisions and answers", ""]
    out.append(_bullets([*(notes.get("decisions") or []), *decisions]))

    out += ["", "## Validation", ""]
    validation = notes.get("validation")
    out.append(_bullets(validation) if validation else "Not run (mode 1)")
    return "\n".join(out) + "\n"
