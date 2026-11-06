"""Input profiler. Turns parsed tables into a capped, compact profile (a dict that
serialises to JSON) the curator reads instead of whole files. Values shown (top,
sampleRows, nearDuplicates) are cut to MAX_VALUE_LENGTH chars. One pass per
column over the rows, counting values in a Counter; everything else is derived
from those counts, so rows are never copied and cost stays linear in cells.

Key order of every dict matches the JS profiler (insertion order is the JSON
order).
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from decimal import Decimal

from _common import infer_type
from _constants import MAX_VALUE_LENGTH, PLACEHOLDERS
from _read_table import Table

NEAR_DUPLICATE_MAX_DISTINCT = 200
LEVENSHTEIN_MIN_LENGTH = 5
LEVENSHTEIN_MAX_DISTANCE = 2

_LEADING_ZERO = re.compile(r"0\d", re.ASCII)


def truncate_value(v: str, max_len: int = MAX_VALUE_LENGTH) -> str:
    """Cuts a long cell value to `max_len` chars plus a note of how many were dropped."""
    return f"{v[:max_len]}…[+{len(v) - max_len} chars]" if len(v) > max_len else v


def _js_number(x: float):
    """A float as JS would print it in JSON: integral values as ints, non-finite as null."""
    if not math.isfinite(x):
        return None
    if x == math.floor(x) and abs(x) < 1e21:
        return int(Decimal(repr(x)))  # shortest digits, zero-padded, like JS
    return x


def _levenshtein(a: str, b: str, limit: int) -> int:
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i]
        for j in range(1, len(b) + 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1])))
        prev = cur
    return prev[len(b)]


def _find_near_duplicates(values: list[str], cap: int) -> tuple[int, list[list[str]]]:
    """Pairs differing only by case/whitespace, then pairs within Levenshtein
    distance; each group sorted. Returns the total found and the first `cap` pairs."""
    equal: list[list[str]] = []
    close: list[list[str]] = []
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            a, b = values[i], values[j]
            pair = [a, b] if a < b else [b, a]
            if a.lower().strip() == b.lower().strip():
                equal.append(pair)
            elif (len(a) >= LEVENSHTEIN_MIN_LENGTH and len(b) >= LEVENSHTEIN_MIN_LENGTH
                  and _levenshtein(a, b, LEVENSHTEIN_MAX_DISTANCE) <= LEVENSHTEIN_MAX_DISTANCE):
                close.append(pair)
    allpairs = sorted(equal) + sorted(close)
    return len(allpairs), allpairs[:cap]


def _profile_column(header: str, c: int, rows: list[list[str]], top_n: int):
    """Profile column `c` of `rows`; returns the profile and the value counts."""
    counts = Counter(r[c] if c < len(r) else "" for r in rows)
    whitespace_cells = 0
    placeholder_cells: dict[str, int] = {}
    leading_zeros = False
    for v, n in counts.items():
        if v != v.strip():
            whitespace_cells += n
        if v in PLACEHOLDERS:
            placeholder_cells[v] = n
        if _LEADING_ZERO.match(v):
            leading_zeros = True
    distinct = list(counts)
    # infer_type only asks "do all/any values match", so the distinct values decide it.
    inferred = infer_type(distinct)
    top = [{"value": truncate_value(v), "count": n}
           for v, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]]
    column: dict = {"header": header, "distinctCount": len(counts), "top": top, "inferred": inferred}

    non_empty = [v for v in distinct if v != ""]
    if non_empty:
        if inferred["data_type"] in ("number", "integer"):
            nums = [float(v) for v in non_empty]
            column["min"] = _js_number(min(nums))
            column["max"] = _js_number(max(nums))
        elif inferred["data_type"] == "date":
            ordered = sorted(non_empty)
            column["min"] = ordered[0]
            column["max"] = ordered[-1]

    column["isCandidateId"] = len(rows) > 0 and len(counts) == len(rows) and "" not in counts
    column["leadingZeros"] = leading_zeros
    column["whitespaceCells"] = whitespace_cells
    column["placeholderCells"] = placeholder_cells
    # Unique IDs differ by construction (sample001, sample002), so pairs there are noise.
    if (inferred["data_shape"] == "categorical" and not column["isCandidateId"]
            and len(counts) <= NEAR_DUPLICATE_MAX_DISTINCT):
        near_count, near_pairs = _find_near_duplicates(non_empty, top_n)
    else:
        near_count, near_pairs = 0, []
    column["nearDuplicates"] = [[truncate_value(v) for v in pair] for pair in near_pairs]
    column["nearDuplicateCount"] = near_count
    return column, counts


def _find_parent_links(entries: list[dict]) -> list[dict]:
    """Column C of F links to candidate ID K of another file G if every value of C is in K."""
    # Keep a column's values only if it can be a link target (candidate ID) or
    # could be wholly contained in another file's candidate ID; free the rest.
    for f in entries:
        other_max = max([0] + [col["distinctCount"] for g in entries if g is not f
                               for col in g["columns"] if col["isCandidateId"]])
        for ci, col in enumerate(f["columns"]):
            # Link detection ignores blanks, so compare on the non-empty distinct count.
            non_empty = len(f["counts"][ci]) - (1 if "" in f["counts"][ci] else 0)
            if not col["isCandidateId"] and non_empty > other_max:
                f["counts"][ci] = None
    links = []
    for f in entries:
        candidate_count = sum(1 for c in f["columns"] if c["isCandidateId"])
        for ci, col in enumerate(f["columns"]):
            if col["isCandidateId"] and candidate_count == 1:
                continue
            if not f["counts"][ci]:
                continue
            values = [v for v in f["counts"][ci] if v != ""]
            if not values:
                continue
            for g in entries:
                if g is f:
                    continue
                for gi, gcol in enumerate(g["columns"]):
                    if not gcol["isCandidateId"]:
                        continue
                    keys = g["counts"][gi]
                    if all(v in keys for v in values):
                        links.append({"file": f["file"], "column": col["header"],
                                      "refFile": g["file"], "refColumn": gcol["header"]})
    return links


def profile_tables(tables: list[Table], top_n: int = 20, sample_rows: int = 5) -> dict:
    entries = []
    for t in tables:
        profiled = [_profile_column(h, c, t.rows, top_n) for c, h in enumerate(t.headers)]
        entries.append({
            "file": os.path.basename(t.file),
            "delimiter": t.delimiter,
            "rowCount": len(t.rows),
            "headers": t.headers,
            "sampleRows": [[truncate_value(v) for v in r] for r in t.rows[:sample_rows]],
            "columns": [p[0] for p in profiled],
            "counts": [p[1] for p in profiled],
        })
    parent_links = _find_parent_links(entries)
    return {
        "files": [{k: v for k, v in e.items() if k != "counts"} for e in entries],
        "parentLinks": parent_links,
    }
