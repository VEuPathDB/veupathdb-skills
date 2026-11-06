"""CSV/TSV reader.

CSV follows RFC 4180 (quoted fields, "" escapes, embedded newlines); TSV has
no quoting. Values are never trimmed. Strips a UTF-8 BOM, treats \\r\\n as a
line break and drops all empty lines at the end of the file (an empty line
before other data is still read as a row).

CSV uses a small hand-written state machine rather than the csv module so that
line numbers (the line a record starts on), text after a closing quote
(kept literally) and unterminated-quote detection match the Node original.
Single pass using find/regex slices, so linear in input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DELIMITER_BY_EXT = {".csv": ",", ".tsv": "\t", ".txt": "\t"}

_UNQUOTED = re.compile(r"[^,\r\n]*")


class TableError(ValueError):
    def __init__(self, label: str, line: int, message: str):
        super().__init__(f"{label}: line {line}: {message}")


@dataclass
class Table:
    file: str
    delimiter: str
    headers: list[str]
    rows: list[list[str]]


def _split_tsv(text: str):
    """Records of (line, cells, blank) for TSV text."""
    records = []
    for i, line in enumerate(text.split("\n")):
        if line.endswith("\r"):
            line = line[:-1]
        records.append((i + 1, line.split("\t"), line == ""))
    return records


def _split_csv(text: str, label: str):
    """RFC 4180 state machine over the whole text."""
    records = []
    n = len(text)
    i = 0
    line = 1
    while i < n:
        start_line = line
        blank = text[i] == "\n" or text.startswith("\r\n", i)
        cells = []
        while True:
            if text.startswith('"', i):
                open_line = line
                parts = []
                i += 1
                seg_start = i
                while True:
                    q = text.find('"', i)
                    if q == -1:
                        raise TableError(label, open_line, "unterminated quoted field")
                    parts.append(text[seg_start:q])
                    if text.startswith('"', q + 1):
                        parts.append('"')
                        i = seg_start = q + 2
                    else:
                        i = q + 1
                        break
                value = "".join(parts)
                line += value.count("\n")
                # Anything between the closing quote and the delimiter is kept literally.
                j = _UNQUOTED.match(text, i).end()
                if j > i:
                    value += text[i:j]
                    i = j
            else:
                j = _UNQUOTED.match(text, i).end()
                value = text[i:j]
                i = j
            cells.append(value)
            if i >= n:
                break
            c = text[i]
            if c == ",":
                i += 1
                if i >= n:
                    cells.append("")
                    break
                continue
            if c == "\r" and text.startswith("\n", i + 1):
                i += 1
            i += 1  # the newline
            line += 1
            break
        records.append((start_line, cells, blank))
    return records


def parse_delimited(text: str, delimiter: str, label: str = "input") -> tuple[list[str], list[list[str]]]:
    """Parse delimited text into (headers, rows). `label` names the source in errors."""
    if text.startswith("﻿"):
        text = text[1:]
    records = _split_tsv(text) if delimiter == "\t" else _split_csv(text, label)
    while records and records[-1][2]:
        records.pop()
    if not records:
        return [], []
    headers = records[0][1]
    rows = []
    for line, cells, _ in records[1:]:
        if len(cells) != len(headers):
            raise TableError(label, line, f"expected {len(headers)} cells but found {len(cells)}")
        rows.append(cells)
    return headers, rows


def _sniff_delimiter(text: str) -> str:
    first = text.removeprefix("﻿").split("\n", 1)[0]
    tabs = first.count("\t")
    commas = first.count(",")
    if tabs >= commas and tabs > 0:
        return "\t"
    return "," if commas > 0 else "\t"


NOT_UTF8 = "not valid UTF-8; re-save the file as UTF-8"


class NotUtf8Error(ValueError):
    def __init__(self, line: int):
        super().__init__(f"line {line}: {NOT_UTF8}")
        self.line = line


def decode_utf8(raw: bytes) -> str:
    """Strict UTF-8 decode; a BOM is kept. Raises NotUtf8Error with the line of the first bad byte."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise NotUtf8Error(raw[:e.start].count(b"\n") + 1) from None


def read_table(path: Path) -> Table:
    """Read a CSV/TSV file. Delimiter comes from the extension, else line 1."""
    path = Path(path)
    try:
        text = decode_utf8(path.read_bytes())  # parse_delimited strips a BOM
    except NotUtf8Error as e:
        raise TableError(path.name, e.line, f"{NOT_UTF8} (e.g. Excel's 'CSV UTF-8')") from None
    delimiter = DELIMITER_BY_EXT.get(path.suffix.lower()) or _sniff_delimiter(text)
    headers, rows = parse_delimited(text, delimiter, path.name)
    return Table(file=str(path), delimiter=delimiter, headers=headers, rows=rows)
