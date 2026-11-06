import json
import shutil
from pathlib import Path

import pytest

from _read_table import parse_delimited
from _render import render_to_dir
from _yaml import load_stf_yaml

DATASETS = ["clinical-epi", "mosquito", "coffee-shops"]


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def _text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


@pytest.fixture(params=DATASETS)
def rendered(request, tmp_path):
    from conftest import FIXTURES
    base = FIXTURES / "tabular" / request.param
    work = tmp_path / "work"
    work.mkdir()
    shutil.copytree(base / "inputs", work / "inputs")
    shutil.copy(base / "spec.json", work / "spec.json")
    out = tmp_path / "out"
    render_to_dir(work / "spec.json", out)
    return out, base / "expected"


def test_golden_renders_the_same_files_as_expected(rendered):
    out, expected = rendered
    assert _files(out) == _files(expected)


def test_golden_renders_the_same_content_as_expected(rendered):
    out, expected = rendered
    for name in sorted(_files(expected)):
        got, want = out / name, expected / name
        if name.endswith(".yaml"):
            assert load_stf_yaml(_text(got))[0] == load_stf_yaml(_text(want))[0], name
        elif name.endswith(".tsv") and not name.startswith("raw-data/"):
            assert parse_delimited(_text(got), "\t", name) == parse_delimited(_text(want), "\t", name), name
        elif name == "curation-spec.json":
            assert json.loads(_text(got)) == json.loads(_text(want)), name
        else:
            assert got.read_bytes() == want.read_bytes(), name


def test_golden_renders_byte_for_byte_as_expected(rendered):
    out, expected = rendered
    for name in sorted(_files(expected)):
        assert (out / name).read_bytes() == (expected / name).read_bytes(), name
