"""Helpers shared by the STF writers: type inference and column naming. Pure."""

import re
from typing import Iterable

_A = re.ASCII
_LEADING_ZERO = re.compile(r"0\d", _A)
_INTEGER = re.compile(r"-?\d+", _A)
_NUMBER = re.compile(r"-?\d+(\.\d+)?([eE][+-]?\d+)?", _A)
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}", _A)
_COLUMN_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*", _A)
_STRING = {"data_type": "string", "data_shape": "categorical"}


def infer_type(values: Iterable[str]) -> dict[str, str]:
    non_null = [str(v) for v in values if v is not None and v != ""]
    if not non_null:
        return dict(_STRING)
    # Leading zeros mark codes (007), not quantities
    if any(_LEADING_ZERO.match(v) for v in non_null):
        return dict(_STRING)
    if all(_INTEGER.fullmatch(v) for v in non_null):
        return {"data_type": "integer", "data_shape": "continuous"}
    if all(_NUMBER.fullmatch(v) for v in non_null):
        return {"data_type": "number", "data_shape": "continuous"}
    if all(_DATE.fullmatch(v) for v in non_null):
        return {"data_type": "date", "data_shape": "continuous"}
    return dict(_STRING)


def is_valid_column_name(name: str) -> bool:
    """Names that need no quoting in R (and survive make.names), SQL or Python."""
    return _COLUMN_NAME.fullmatch(name) is not None


def to_column_name(header: str) -> str:
    """snake_case: 'Age (years)' -> 'age_years'; 'x' prefix if empty or digit-led."""
    name = re.sub(r"[^a-z0-9]+", "_", str(header).lower()).strip("_")
    return f"x{name}" if name == "" or name[0].isdigit() else name


def unique_column_names(names: list[str]) -> list[str]:
    """Keeps the first occurrence; later duplicates get _2, _3, ..."""
    seen = set(names)
    counts: dict[str, int] = {}
    first: set[str] = set()
    out = []
    for n in names:
        if n not in first:
            first.add(n)
            out.append(n)
            continue
        k = counts.get(n, 1)
        while True:
            k += 1
            candidate = f"{n}_{k}"
            if candidate not in seen:
                break
        counts[n] = k
        seen.add(candidate)
        out.append(candidate)
    return out
