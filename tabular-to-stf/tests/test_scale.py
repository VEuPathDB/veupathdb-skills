"""Opt-in scale test: STF_SCALE_TEST=1. 1,000 parents and 1,000,000 children through the CLI."""
import json
import os
import re
import time

import pytest

from conftest import run_cli

try:
    import resource
except ImportError:  # not available on Windows
    resource = None

PARENTS = 1000
CHILDREN = 1_000_000
BUDGET_SECONDS = 900


def _peak_mib() -> str:
    if resource is None:
        return "n/a"
    # High-water mark over all child processes so far; KiB on Linux.
    return f"{resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024:.0f} MiB"


def _write_inputs(directory) -> None:
    with open(directory / "parent.csv", "w", encoding="utf-8", newline="\n") as f:
        f.write("parent_id,name\n")
        f.writelines(f"P{i},Parent {i}\n" for i in range(PARENTS))
    statuses = ("ok", "late", "lost")
    with open(directory / "child.csv", "w", encoding="utf-8", newline="\n") as f:
        f.write("child_id,parent_id,age,weight,visit_date,sex,status,note\n")
        for start in range(0, CHILDREN, 50_000):
            f.writelines(
                f"C{i},P{i % PARENTS},{i % 90},{30 + (i % 500) / 10:.1f},"
                f"2023-{(i % 12) + 1:02d}-{(i % 28) + 1:02d},{'F' if i % 2 else 'M'},"
                f"{statuses[i % 3]},{'' if i % 7 == 0 else f'note {i % 1000}'}\n"
                for i in range(start, min(start + 50_000, CHILDREN))
            )


@pytest.mark.skipif(os.environ.get("STF_SCALE_TEST") != "1", reason="set STF_SCALE_TEST=1 to run")
def test_scale_profile_render_check_1m_child_rows(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    started = time.monotonic()

    def stage(label, since):
        now = time.monotonic()
        print(f"  {label}: step {now - since:.1f}s, total {now - started:.1f}s, children peak rss {_peak_mib()}")
        return now

    _write_inputs(inputs)
    t = stage("generated", started)

    # The full profile to a file, a summary line per file on stdout.
    work = tmp_path / "work"
    work.mkdir()
    profile_path = work / "profile.json"
    r = run_cli("profile", str(inputs), "--out", str(profile_path))
    assert r.returncode == 0, r.stderr
    assert re.search(r"^child\.csv: 1000000 rows, 8 columns, ", r.stdout, re.MULTILINE)
    assert len(json.loads(profile_path.read_text(encoding="utf-8"))["files"]) == 2
    t = stage("profile --out", t)

    one = run_cli("profile", str(inputs), "--file", "child.csv")
    assert one.returncode == 0, one.stderr
    assert len(one.stdout) < 30_000, f"--file child.csv printed {len(one.stdout)} chars"
    print(f"  profile CLI: --out summary {len(r.stdout)} chars, --file child.csv {len(one.stdout)} chars")
    t = stage("profile --file", t)

    spec = {
        "specVersion": "1.0.0",
        "study": {"name": "Scale test"},
        "inputDir": str(inputs),
        "entities": [
            {"name": "parent", "displayName": "Parent", "displayNamePlural": "Parents",
             "file": "parent.csv", "idColumn": "parent_id", "variables": [{"column": "name"}]},
            {"name": "child", "displayName": "Child", "displayNamePlural": "Children",
             "file": "child.csv", "idColumn": "child_id", "parent": "parent", "parentColumn": "parent_id",
             "variables": [{"column": c} for c in ("age", "weight", "visit_date", "sex", "status", "note")]},
        ],
        "transforms": [],
    }
    spec_path = work / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    out_dir = tmp_path / "stf"
    r = run_cli("render", str(spec_path), str(out_dir), "--no-raw-data")
    assert r.returncode == 0, r.stderr
    t = stage("render", t)

    r = run_cli("check", str(out_dir), "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(r.stdout)["errors"] == []
    t = stage("check", t)

    total = time.monotonic() - started
    print(f"  scale result: wall {total:.1f}s, children peak rss {_peak_mib()}")
    assert total < BUDGET_SECONDS
