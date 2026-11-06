"""Matching a cell against a transform's keys: exact, or regex.

A regex key must match the whole cell (re.fullmatch), like an exact key. In
regex mode a replacement may refer to the pattern's groups: `$` followed by
digits takes all of them (`$10` is group 10), `$$` is a literal `$`, and any
other `$` is an error. A group that took no part in the match gives "". The
substitution is done here from match.group(n), never by re.sub or
Match.expand, so a backslash in a replacement is just a backslash. In exact
mode a replacement is literal text.
"""

from __future__ import annotations

import re

_TEMPLATE_PART = re.compile(r"\$(\d+|\$)?", re.ASCII)


class TemplateError(ValueError):
    pass


def parse_template(s: str) -> list[str | int]:
    """Literal chunks and group numbers, in order; adjacent literals are joined."""
    parts: list[str | int] = []
    literal = ""
    pos = 0
    for m in _TEMPLATE_PART.finditer(s):
        literal += s[pos:m.start()]
        pos = m.end()
        if m[1] is None:
            raise TemplateError('"$" must be followed by a group number or "$"')
        if m[1] == "$":
            literal += "$"
            continue
        if literal:
            parts.append(literal)
            literal = ""
        parts.append(int(m[1]))
    literal += s[pos:]
    if literal:
        parts.append(literal)
    return parts


def template_groups(parts: list[str | int]) -> set[int]:
    return {p for p in parts if isinstance(p, int)}


def expand(parts: list[str | int], m: re.Match) -> str:
    return "".join(p if isinstance(p, str) else (m.group(p) or "") for p in parts)


class ValueMatcher:
    """A transform's keys and replacements. Assumes a validated spec."""

    def __init__(self, mapping: dict[str, str], regex: bool):
        self.regex = regex
        self.mapping = mapping
        if regex:
            self._rules = [(k, re.compile(k), parse_template(v)) for k, v in mapping.items()]

    def hits(self, cell: str) -> list[tuple[str, str]]:
        """(key, result) for every key matching the cell, in map order."""
        if not self.regex:
            return [(cell, self.mapping[cell])] if cell in self.mapping else []
        out = []
        for key, rx, parts in self._rules:
            m = rx.fullmatch(cell)
            if m:
                out.append((key, expand(parts, m)))
        return out

    @staticmethod
    def is_ambiguous(hits: list[tuple[str, str]]) -> bool:
        return len({result for _, result in hits}) > 1
