"""STF directory checker. Reads study.yaml, entity-<name>.{tsv,yaml} and
curation-notes.md and reports every problem found; the goal is that a pass
means `study_from_stf(dir, validate = FALSE)` loads in study-wrangler.
Read-only, and it ignores subdirectories (raw-data/ included) and files
study.yaml does not name, as the loaders do.

Handles the standard layout of full STF only. STF-lite and transposed entity
files are reported, not checked: validate those in mode 2.

Presence of a YAML field means the key is present (a null value counts); strict
equality and set/map membership go through _key, so true is not 1 and a list
never equals another list.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any

from _common import is_valid_column_name
from _constants import DATA_SHAPES, DATA_TYPES, DISPLAY_TYPES, HIDDEN
from _container import STUDY_WRANGLER_VERSION
from _geo import GEO, is_latitude_name, is_longitude_name, validator_sees_latitude, validator_sees_longitude
from _read_table import NotUtf8Error, decode_utf8, parse_delimited
from _spec import MISSING, js_json
from _yaml import YamlError, load_stf_yaml

MARKER = " \\\\ Descriptors"
MAX_PER_KIND = 5  # value errors reported per file, column and kind

_NUMBER = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", re.ASCII)
_INTEGER = re.compile(r"[+-]?\d+", re.ASCII)
_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})", re.ASCII)
_ENTITY_YAML = re.compile(r"entity-.*\.yaml")
_RAW_MENTION = re.compile(r"raw-data/[^\s`'\"()<>\]]+")
_TRAILING_PUNCT = re.compile(r"[.,;:]+$")


def js_str(v: Any) -> str:
    """JS String(v) for YAML values."""
    if v is MISSING:
        return "undefined"
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ",".join("" if x is None or x is MISSING else js_str(x) for x in v)
    if isinstance(v, dict):
        return "[object Object]"
    return str(v)


def _key(v: Any) -> tuple:
    """A hashable key with JS SameValueZero semantics (Set/Map membership, strict equality)."""
    if isinstance(v, bool):
        return ("bool", v)
    if isinstance(v, (int, float)):
        return ("number", v)
    if isinstance(v, str):
        return ("string", v)
    if v is None:
        return ("null",)
    if v is MISSING:
        return ("undefined",)
    return ("object", id(v))


def _same(a: Any, b: Any) -> bool:
    return _key(a) == _key(b)


def _is_int(v: Any) -> bool:
    """JS Number.isInteger."""
    return isinstance(v, int) and not isinstance(v, bool) or isinstance(v, float) and v.is_integer()


def _js_falsy(v: Any) -> bool:
    """JS `!v` for a YAML value: an empty mapping or list is truthy."""
    return v is None or v is MISSING or v is False or v == "" or (_key(v)[0] == "number" and v == 0)


def _as_list(v: Any) -> list:
    if v is None or v is MISSING:
        return []
    return v if isinstance(v, list) else [v]


def _is_missing(v: str) -> bool:
    return v == "" or v == "NA"


def _get(d: dict, k: str) -> Any:
    return d.get(k, MISSING)


def _compare_versions(a: str, b: str) -> float:
    """Numeric dotted-version comparison: negative, 0 or positive."""
    pa = [_js_number(x) for x in a.split(".")]
    pb = [_js_number(x) for x in b.split(".")]
    for i in range(max(len(pa), len(pb))):
        d = (pa[i] if i < len(pa) else 0) - (pb[i] if i < len(pb) else 0)
        if d != 0:
            return d
    return 0


def _js_number(s: str) -> float:
    try:
        return float(s) if s.strip() else 0.0
    except ValueError:
        return float("nan")


def geohash_warning(version: str = STUDY_WRANGLER_VERSION) -> str:
    if _compare_versions(version, "1.0.53") < 0:
        return ("geohash columns present; drop them before mode 2 validation, "
                "since study-wrangler <1.0.53 would duplicate them")
    return "geohash columns present; they will be recomputed by infer_geo_variables_for_eda()"


def _valid_date(s: str) -> bool:
    m = _DATE.fullmatch(s)
    if not m:
        return False
    y, mo, d = (int(g) for g in m.groups())
    if y < 100:  # JS Date.UTC maps years 0-99 to 1900-1999, so the round trip fails
        return False
    try:
        datetime.date(y, mo, d)
    except ValueError:
        return False
    return True


def _value_problem(value: str, v: dict) -> str | None:
    """Why `value` is not valid for variable v, or None."""
    data_type = _get(v, "data_type")
    if _same(data_type, "date"):
        return None if _valid_date(value) else "is not a valid YYYY-MM-DD date"
    if _same(data_type, "integer"):
        return None if _INTEGER.fullmatch(value) else "is not an integer"
    if _same(data_type, "number") or _same(data_type, "longitude"):
        if not _NUMBER.fullmatch(value):
            return "is not a number"
    if _same(data_type, "longitude") and not (-180 <= float(value) <= 180):
        return "is outside -180..180"
    if _same(_get(v, "display_type"), "latitude"):
        if not _NUMBER.fullmatch(value):
            return "is not a number"
        if not (-90 <= float(value) <= 90):
            return "is outside -90..90"
    return None


def _read_text(path: Path) -> str:
    """Strict UTF-8; raises NotUtf8Error ("line N: not valid UTF-8; ...") so the caller can name the file."""
    return decode_utf8(path.read_bytes())


class _Entity:
    def __init__(self, name: str, yaml_file: str, tsv_file: str, meta: dict, headers: list, rows: list):
        self.name = name
        self.yaml_file = yaml_file
        self.tsv_file = tsv_file
        self.meta = meta
        self.headers = headers
        self.rows = rows
        self.ids: list[dict] = []
        self.own: dict | None = None
        self.ancestors: list[dict] = []
        self.id_set: set[str] | None = None
        self.pending = None

    def own_id_column(self, default: str) -> str:
        """JS `e.own?.id_column ?? default` in a template literal."""
        v = _get(self.own, "id_column") if self.own is not None else MISSING
        return default if v is None or v is MISSING else js_str(v)


def _load_yaml(directory: Path, name: str, errors: list, warnings: list) -> Any:
    try:
        data, yaml_warnings = load_stf_yaml(_read_text(directory / name))
    except (YamlError, NotUtf8Error, OSError) as err:
        errors.append(f"{name}: cannot parse YAML: {err}")
        return None
    warnings.extend(f"{name}: {w}" for w in yaml_warnings)
    return data


def _load_study(directory: Path, errors: list, warnings: list):
    """Load study.yaml and every listed entity's TSV and YAML. Returns None if nothing can be checked."""
    files = [p.name for p in directory.iterdir()]
    if not (directory / "study.yaml").exists():
        if not any(_ENTITY_YAML.fullmatch(f) for f in files):
            errors.append("study.yaml: missing, and no entity-<name>.yaml files either; "
                          "STF-lite not supported; validate in mode 2")
        else:
            errors.append("study.yaml: missing")
        return None
    study = _load_yaml(directory, "study.yaml", errors, warnings)
    if _js_falsy(study):
        return None
    if not isinstance(study, dict):
        errors.append("study.yaml: must be a mapping with name and entities")
        return None
    if not isinstance(study.get("name"), str) or study["name"] == "":
        errors.append("study.yaml: name is required")
    names = _as_list(study.get("entities"))
    if not names or not all(isinstance(n, str) and n != "" for n in names):
        errors.append("study.yaml: entities must be a non-empty list of entity names")
        return None
    if len(set(names)) != len(names):
        errors.append("study.yaml: duplicate entity in entities")

    entities: dict[str, _Entity] = {}
    for name in names:
        yaml_file = f"entity-{name}.yaml"
        tsv_file = f"entity-{name}.tsv"
        have_yaml = (directory / yaml_file).exists()
        have_tsv = (directory / tsv_file).exists()
        if not have_yaml:
            errors.append(f"{yaml_file}: missing (listed in study.yaml)")
        if not have_tsv:
            errors.append(f"{tsv_file}: missing (listed in study.yaml)")
        if not have_yaml or not have_tsv:
            continue
        meta = _load_yaml(directory, yaml_file, errors, warnings)
        if _js_falsy(meta):
            continue
        if not isinstance(meta, dict):
            errors.append(f"{yaml_file}: must be a mapping")
            continue
        if not _same(_get(meta, "name"), name):
            errors.append(f"{yaml_file}: name is {js_json(_get(meta, 'name'))} but study.yaml lists {js_json(name)}")
        try:
            headers, rows = parse_delimited(_read_text(directory / tsv_file), "\t", tsv_file)
        except (ValueError, OSError) as err:
            errors.append(f"{tsv_file}: {err}")
            continue
        entities[name] = _Entity(name, yaml_file, tsv_file, meta, headers, rows)
    return study, entities


def _check_notes(directory: Path, warnings: list) -> None:
    path = directory / "curation-notes.md"
    if not path.exists():
        return
    try:
        text = _read_text(path)
    except NotUtf8Error as err:  # the notes do not stop a load, so only a warning
        warnings.append(f"curation-notes.md: {err}")
        return
    mentioned = dict.fromkeys(_RAW_MENTION.findall(text))
    for m in mentioned:
        p = _TRAILING_PUNCT.sub("", m)
        if not (directory / p).exists():
            warnings.append(f"curation-notes.md: mentions {p}, which does not exist")


def _entity_of(entities: dict, name: Any) -> _Entity | None:
    return entities.get(name) if isinstance(name, str) else None


def _check_tree(entities: dict[str, _Entity], errors: list):
    """Entity tree from the entity_level -1 links. Returns parent_of, or None on a cycle."""
    parent_of: dict[str, str] = {}
    roots: list[str] = []
    for e in entities.values():
        ids = [c for c in _as_list(e.meta.get("id_columns")) if isinstance(c, dict)]
        e.ids = ids
        own = [c for c in ids if _same(_get(c, "entity_name"), e.name)]
        ancestors = [c for c in ids if not _same(_get(c, "entity_name"), e.name)]
        e.own = own[0] if len(own) == 1 else None
        if len(own) != 1:
            errors.append(f"{e.yaml_file}: need exactly one id_column with entity_name {e.name} (its own ID); "
                          f"found {len(own)}")
        if any("entity_level" in c and not _same(c["entity_level"], 0) for c in own):
            errors.append(f"{e.yaml_file}: the own ID column must have entity_level 0")
        e.ancestors = ancestors
        levels: dict[int, dict] = {}
        for c in ancestors:
            lvl = _get(c, "entity_level")
            if not _is_int(lvl) or lvl >= 0:
                errors.append(f"{e.yaml_file}: id_column {js_str(_get(c, 'id_column'))} has entity_level "
                              f"{js_json(lvl)}; ancestors need a negative integer")
                continue
            lvl = int(lvl)
            if lvl in levels:
                errors.append(f"{e.yaml_file}: two id_columns have entity_level {lvl}")
            levels[lvl] = c
        parent_col = levels.get(-1)
        if parent_col is not None:
            parent_name = _get(parent_col, "entity_name")
            if _entity_of(entities, parent_name) is None:
                errors.append(f"{e.yaml_file}: id_column {js_str(_get(parent_col, 'id_column'))} names entity "
                              f"{js_json(parent_name)}, which study.yaml does not list")
            else:
                parent_of[e.name] = parent_name
        else:
            roots.append(e.name)
            if ancestors:
                odd = "; ".join(f"{js_str(_get(c, 'id_column'))} has entity_level {js_str(_get(c, 'entity_level'))}"
                                for c in ancestors)
                errors.append(f"{e.yaml_file}: no id_column with entity_level -1 (the immediate parent); {odd}")
    if len(roots) > 1:
        errors.append(f"study.yaml: more than one root entity (no entity_level -1 column): {', '.join(roots)}")
    if not roots and entities:
        errors.append("study.yaml: no root entity (every entity has a parent)")
    cyclic = False
    for name in parent_of:
        seen = {name}
        n = parent_of.get(name)
        while n is not None:
            if n in seen:
                cyclic = True
                errors.append(f"study.yaml: entity cycle through {name}")
                break
            seen.add(n)
            n = parent_of.get(n)
    if cyclic:
        return None
    # Each ancestor id column must sit at its distance in the tree
    for e in entities.values():
        chain = []
        n = parent_of.get(e.name)
        while n is not None:
            chain.append(n)
            n = parent_of.get(n)
        for c in e.ancestors:
            id_column = _get(c, "id_column")
            entity_name = _get(c, "entity_name")
            level = _get(c, "entity_level")
            anc = _entity_of(entities, entity_name)
            if anc is None:
                if not _same(level, -1):
                    errors.append(f"{e.yaml_file}: id_column {js_str(id_column)} names entity {js_json(entity_name)}, "
                                  "which study.yaml does not list")
                continue
            own_name = _get(anc.own, "id_column") if anc.own is not None else MISSING
            if own_name is not MISSING and not _same(id_column, own_name):
                errors.append(f"{e.yaml_file}: id_column {js_str(id_column)} refers to {entity_name}, whose own ID "
                              f"column is {js_str(own_name)}; study-wrangler joins on the name, "
                              f"so it must be {js_str(own_name)}")
            at = chain.index(entity_name) if entity_name in chain else -1
            if at < 0:
                errors.append(f"{e.yaml_file}: id_column {js_str(id_column)}: {entity_name} is not an ancestor of {e.name}")
            elif not _same(level, -(at + 1)):
                errors.append(f"{e.yaml_file}: id_column {js_str(id_column)} has entity_level {js_str(level)} "
                              f"but {entity_name} is {at + 1} level(s) up, so it must be {-(at + 1)}")
    return parent_of


class _Limiter:
    """Reports at most MAX_PER_KIND errors per key, then one line saying how many more."""

    def __init__(self, errors: list):
        self.errors = errors
        self.counts: dict[str, int] = {}

    def report(self, key: str, msg: str) -> None:
        n = self.counts.get(key, 0) + 1
        self.counts[key] = n
        if n <= MAX_PER_KIND:
            self.errors.append(msg)

    def flush(self) -> None:
        # Like the JS, counts are not reset, so a second flush repeats earlier summary lines.
        for key, n in self.counts.items():
            if n > MAX_PER_KIND:
                self.errors.append(f"{key}: {n - MAX_PER_KIND} more like this not shown")


def _check_variable_meta(e: _Entity, errors: list) -> None:
    yaml_file, meta = e.yaml_file, e.meta
    variables = _as_list(meta.get("variables"))
    categories = _as_list(meta.get("categories"))
    names: dict[str, str] = {}

    def note(kind: str, n: Any) -> None:
        if not isinstance(n, str) or n == "":
            errors.append(f"{yaml_file}: a {kind} has no name")
            return
        if n in names:
            errors.append(f"{yaml_file}: duplicate name {n} ({names[n]} and {kind})")
        else:
            names[n] = kind

    for v in variables:
        if not isinstance(v, dict):
            errors.append(f"{yaml_file}: variables entries must be mappings")
            continue
        note("variable", _get(v, "variable"))
        at = f"{yaml_file}: variable {js_str(_get(v, 'variable'))}"
        for field, allowed in (("data_type", DATA_TYPES), ("data_shape", DATA_SHAPES), ("display_type", DISPLAY_TYPES)):
            if field in v and not any(_same(v[field], x) for x in allowed):
                errors.append(f"{at}: {field} {js_json(v[field])} is not one of {', '.join(allowed)}")
        for h in _as_list(v.get("hidden")):
            if not any(_same(h, x) for x in HIDDEN):
                errors.append(f"{at}: hidden {js_json(h)} is not one of {', '.join(HIDDEN)}")
        if _same(_get(v, "data_shape"), "ordinal") and not _as_list(v.get("ordinal_levels")):
            errors.append(f"{at}: data_shape ordinal requires ordinal_levels")

    cat_names: set[tuple] = set()
    for c in categories:
        if not isinstance(c, dict):
            errors.append(f"{yaml_file}: categories entries must be mappings")
            continue
        note("category", _get(c, "category"))
        cat_names.add(_key(_get(c, "category")))
    for v in variables:
        if isinstance(v, dict) and "parent_category" in v and _key(v["parent_category"]) not in cat_names:
            errors.append(f"{yaml_file}: variable {js_str(_get(v, 'variable'))}: parent_category "
                          f"{js_json(v['parent_category'])} names no category in {e.name}")
    parent_of: dict[tuple, Any] = {}
    label: dict[tuple, Any] = {}
    for c in categories:
        if not isinstance(c, dict) or "parent_category" not in c:
            continue
        if _key(c["parent_category"]) not in cat_names:
            errors.append(f"{yaml_file}: category {js_str(_get(c, 'category'))}: parent_category "
                          f"{js_json(c['parent_category'])} names no category in {e.name}")
        else:
            k = _key(_get(c, "category"))
            parent_of[k] = _key(c["parent_category"])
            label[k] = _get(c, "category")
            label.setdefault(parent_of[k], c["parent_category"])
    cycled: set[tuple] = set()
    for start in parent_of:
        seen = {start}
        n = parent_of.get(start)
        while n is not None:
            if n in seen:
                if n not in cycled:
                    errors.append(f"{yaml_file}: category cycle through {js_str(label[n])}")
                cycled |= seen
                break
            seen.add(n)
            n = parent_of.get(n)


def _check_geo_meta(e: _Entity, errors: list, warnings: list) -> None:
    yaml_file = e.yaml_file
    variables = [v for v in _as_list(e.meta.get("variables")) if isinstance(v, dict) and isinstance(v.get("variable"), str)]

    def seen_by(v: dict, fn) -> bool:
        return any(fn(js_str(t)) for t in [v["variable"], *_as_list(v.get("provider_label"))])

    lats = [v for v in variables if seen_by(v, validator_sees_latitude)]
    lngs = [v for v in variables if seen_by(v, validator_sees_longitude)]
    for v in variables:
        lat = is_latitude_name(v["variable"]) and not seen_by(v, validator_sees_latitude)
        lng = is_longitude_name(v["variable"]) and not seen_by(v, validator_sees_longitude)
        if lat or lng:
            warnings.append(f"{yaml_file}: variable {v['variable']} matches the {'latitude' if lat else 'longitude'} "
                            "inference rule but not the validator rule; inference would set it up but validate() "
                            "would not see it")
    if len(lats) > 1:
        errors.append(f"{yaml_file}: more than one latitude column ({', '.join(v['variable'] for v in lats)})")
    if len(lngs) > 1:
        errors.append(f"{yaml_file}: more than one longitude column ({', '.join(v['variable'] for v in lngs)})")
    if len(lats) == 1 and len(lngs) == 1:
        for axis, v in (("latitude", lats[0]), ("longitude", lngs[0])):
            want = GEO[axis]
            for k in ("stable_id", "data_type", "display_type"):
                if not _same(_get(v, k), want[k]):
                    errors.append(f"{yaml_file}: {axis} column {v['variable']} needs {k} {want[k]} "
                                  f"(found {js_json(_get(v, k))})")
    elif len(lats) + len(lngs) == 1:
        v = (lats or lngs)[0]
        warnings.append(f"{yaml_file}: variable {v['variable']} looks like a {'latitude' if lats else 'longitude'} "
                        "with no partner; check for a mislabelled coordinate")
    geohash = [v for v in variables if v["variable"] in GEO["geohash_columns"]]
    if geohash:
        warnings.append(f"{yaml_file}: {geohash_warning()} ({', '.join(v['variable'] for v in geohash)})")


def _check_columns(e: _Entity, errors: list, warnings: list):
    """Column layout of one entity TSV against its YAML. Returns (marker_at, index) or None."""
    tsv_file, yaml_file, headers = e.tsv_file, e.yaml_file, e.headers
    marker_at = next((i for i, h in enumerate(headers) if h.endswith(MARKER)), -1)
    if marker_at < 0:
        errors.append(f"{tsv_file}: transposed or malformed TSV (no `\\\\ Descriptors` marker in the header row); "
                      "validate in mode 2")
        return None
    names = [h[:-len(MARKER)] if i == marker_at else h for i, h in enumerate(headers)]
    seen = set()
    for n in names:
        if n in seen:
            errors.append(f"{tsv_file}: duplicate column {n}")
        seen.add(n)
        if not is_valid_column_name(n):
            warnings.append(f"{tsv_file}: column name {js_json(n)} is not a plain identifier "
                            "(letters, digits, underscore, starting with a letter)")
    index = {n: i for i, n in enumerate(names)}
    if e.own is not None:
        own_name = _get(e.own, "id_column")
        if not _same(names[marker_at], own_name):
            errors.append(f"{tsv_file}: the Descriptors column is {names[marker_at]} but {yaml_file} gives the "
                          f"entity's own ID as {js_str(own_name)}")
    yml_cols: dict[tuple, tuple[Any, str]] = {}

    def put(n: Any, where: str) -> None:
        k = _key(n)
        yml_cols[k] = (yml_cols[k][0] if k in yml_cols else n, where)

    for c in e.ids:
        put(_get(c, "id_column"), "id_columns")
    for v in _as_list(e.meta.get("variables")):
        if isinstance(v, dict):
            put(_get(v, "variable"), "variables")
    for n in names:
        if _key(n) not in yml_cols:
            errors.append(f"{tsv_file}: column {n} is not in {yaml_file}")
    for n, where in yml_cols.values():
        if not (isinstance(n, str) and n in index):
            errors.append(f"{yaml_file}: {'id_column' if where == 'id_columns' else 'variable'} {js_str(n)} "
                          f"is not in {tsv_file}")
    return marker_at, index


def _check_rows(e: _Entity, layout, entities: dict[str, _Entity], errors: list) -> None:
    tsv_file, rows = e.tsv_file, e.rows
    marker_at, index = layout
    limiter = _Limiter(errors)
    report = limiter.report
    own_ids: set[str] = set()

    def label(r: int) -> str:
        return f"row {r + 2}" if rows[r][marker_at] == "" else rows[r][marker_at]

    for r, row in enumerate(rows):
        id_ = row[marker_at]
        if id_ == "":
            report(f"{tsv_file}: empty ID", f"{tsv_file}: row {r + 2}: empty {e.own_id_column('ID')}")
        elif id_ in own_ids:
            report(f"{tsv_file}: duplicate ID", f"{tsv_file}: {id_}: duplicate ID in {e.own_id_column('ID column')}")
        else:
            own_ids.add(id_)
    e.id_set = own_ids

    # Ancestor IDs must exist in the ancestor's own ID column (checked after all entities are loaded)
    def pending() -> None:
        for c in e.ancestors:
            anc = _entity_of(entities, _get(c, "entity_name"))
            id_column = _get(c, "id_column")
            col = index.get(id_column) if isinstance(id_column, str) else None
            if anc is None or anc.id_set is None or col is None:
                continue
            for r, row in enumerate(rows):
                v = row[col]
                if v == "":
                    report(f"{tsv_file}: {id_column}", f"{tsv_file}: {label(r)}: {id_column} is empty")
                elif v not in anc.id_set:
                    report(f"{tsv_file}: {id_column} orphan",
                           f"{tsv_file}: {label(r)}: {id_column} {v} not found in {anc.name} (entity-{anc.name}.tsv)")
        limiter.flush()

    e.pending = pending

    for v in _as_list(e.meta.get("variables")):
        if not isinstance(v, dict):
            continue
        variable = _get(v, "variable")
        col = index.get(variable) if isinstance(variable, str) else None
        if col is None:
            continue
        levels = [js_str(x) for x in _as_list(v.get("ordinal_levels"))]
        needs_parse = (any(_same(_get(v, "data_type"), t) for t in ("date", "integer", "number", "longitude"))
                       or _same(_get(v, "display_type"), "latitude"))
        if not needs_parse and not (_same(_get(v, "data_shape"), "ordinal") and levels):
            continue
        delimiter = v.get("multi_value_delimiter")
        delim = delimiter if v.get("is_multi_valued") is True and isinstance(delimiter, str) and delimiter != "" else None
        for r, row in enumerate(rows):
            cell = row[col]
            if _is_missing(cell):
                continue
            for value in cell.split(delim) if delim else [cell]:
                if needs_parse:
                    problem = _value_problem(value, v)
                else:
                    problem = None if value in levels else "is not in ordinal_levels"
                if problem:
                    report(f"{tsv_file}: {variable}", f"{tsv_file}: {label(r)}: {variable} value {js_json(value)} {problem}")
    limiter.flush()


def check_stf(path: Path) -> dict:
    """Check an STF directory. Returns {"errors": [...], "warnings": [...]}."""
    directory = Path(path)
    errors: list[str] = []
    warnings: list[str] = []
    if not directory.is_dir():
        return {"errors": [f"{path}: not a directory"], "warnings": warnings}
    loaded = _load_study(directory, errors, warnings)
    _check_notes(directory, warnings)
    if not loaded:
        return {"errors": errors, "warnings": warnings}
    _, entities = loaded

    _check_tree(entities, errors)
    for e in entities.values():
        _check_variable_meta(e, errors)
        _check_geo_meta(e, errors, warnings)
        layout = _check_columns(e, errors, warnings)
        if layout:
            _check_rows(e, layout, entities, errors)
    for e in entities.values():
        if e.pending:
            e.pending()
    return {"errors": errors, "warnings": warnings}
