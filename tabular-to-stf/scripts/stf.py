#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruamel.yaml>=0.18"]
# ///
"""stf.py - tabular-to-stf command line.

  stf.py profile <inputDir> [--top N] [--file <name>] [--out <path>]

profile: profiles every .csv/.tsv/.txt file in a directory (columns, types, top
values, quirks, parent links) as compact JSON. Values longer than 80 chars are
cut. Read-only on the inputs.

  --file <name>  only that file's entry, and only the parent links involving
                 it (links are still found across all files)
  --out <path>   write the full profile to <path> and print one summary line
                 per file instead (name, rows, columns, size of its entry)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

PROFILE_USAGE = "Usage: stf.py profile <inputDir> [--top N] [--file <name>] [--out <path>]"
_TABLE_NAME = re.compile(r"\.(csv|tsv|txt)$", re.IGNORECASE)
_NUMERIC = re.compile(r"\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?\s*", re.ASCII)


def _dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _kb(n: int) -> str:
    """Like JS (n / 1024).toFixed(1): ties round up, not to even."""
    return f"{(Decimal(n) / 1024).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)} KB"


def _positive_int(text: str) -> int | None:
    """Like JS Number(text) accepted by Number.isInteger and >= 1, else None."""
    if not _NUMERIC.fullmatch(text):
        return None
    x = float(text)
    return int(x) if x == int(x) and x >= 1 else None


def cmd_profile(args) -> int:
    from _profile import profile_tables
    from _read_table import read_table

    if len(args.inputDir) != 1:
        raise ValueError(PROFILE_USAGE)
    directory = Path(args.inputDir[0])
    top_n = _positive_int(args.top)
    if top_n is None:
        raise ValueError(f'--top must be a positive integer, got "{args.top}"')
    if not directory.is_dir():
        raise ValueError(f"Not a directory: {directory}")
    if args.out and Path(args.out).absolute().parent == directory.absolute():
        raise ValueError(f"--out must not be in the input directory {directory}; inputs are never modified")

    names = sorted(p.name for p in directory.iterdir() if _TABLE_NAME.search(p.name))
    if not names:
        raise ValueError(f"No .csv/.tsv/.txt files in {directory}")
    if args.file is not None and args.file not in names:
        raise ValueError(f"--file {args.file}: no such table in {directory} (have: {', '.join(names)})")
    profile = profile_tables([read_table(directory / n) for n in names], top_n=top_n)
    if args.file is not None:
        f = args.file
        profile = {
            "files": [x for x in profile["files"] if x["file"] == f],
            "parentLinks": [l for l in profile["parentLinks"] if l["file"] == f or l["refFile"] == f],
        }

    text = _dumps(profile)
    if args.out is None:
        print(text)
        return 0
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{text}\n")
    print(f"Wrote {args.out} ({_kb(len(text.encode('utf-8')))}); read one file at a time with --file <name>")
    for f in profile["files"]:
        print(f"{f['file']}: {f['rowCount']} rows, {len(f['headers'])} columns, {_kb(len(_dumps(f).encode('utf-8')))}")
    print(f"parentLinks: {len(profile['parentLinks'])}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stf.py", description="tabular-to-stf command line")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("profile", usage=PROFILE_USAGE.removeprefix("Usage: "),
                       description="Profile every .csv/.tsv/.txt file in a directory as compact JSON.")
    # nargs="*" so a missing/extra directory gets the JS usage error, not argparse's.
    p.add_argument("inputDir", nargs="*", metavar="inputDir", help="directory of input tables")
    p.add_argument("--top", default="20", metavar="N", help="values kept per column's top list (default 20)")
    p.add_argument("--file", metavar="NAME", help="only this file's entry and the parent links involving it")
    p.add_argument("--out", metavar="PATH", help="write the full profile here; print a summary per file")
    p.set_defaults(func=cmd_profile)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", newline="\n")
    try:
        args = build_parser().parse_args(argv)
        return args.func(args)
    except SystemExit:
        raise
    except Exception as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
