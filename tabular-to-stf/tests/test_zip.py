import shutil
import zipfile

import pytest

from conftest import FIXTURES, run_cli
from _check import check_stf
from _zip import zip_stf

EXPECTED = FIXTURES / "tabular" / "coffee-shops" / "expected"


@pytest.fixture
def stf_dir(tmp_path):
    d = tmp_path / "study-stf"
    shutil.copytree(EXPECTED, d)
    return d


def flat_names(d):
    """The files the zip should hold, flat: everything but raw-data/."""
    return sorted(p.name for p in d.iterdir() if p.is_file())


def test_zip_holds_the_stf_files_flat_and_no_raw_data(stf_dir):
    path, names = zip_stf(stf_dir)
    assert path == stf_dir.with_name("study-stf.zip")
    with zipfile.ZipFile(path) as z:
        assert z.namelist() == names
        assert sorted(names) == flat_names(stf_dir)
        assert not any("/" in n for n in names)
        assert z.testzip() is None
    assert names[0] == "study.yaml"


def test_zip_with_raw_data_keeps_the_raw_data_folder(stf_dir):
    _, names = zip_stf(stf_dir, with_raw_data=True)
    raw = sorted(f"raw-data/{p.relative_to(stf_dir / 'raw-data').as_posix()}"
                 for p in (stf_dir / "raw-data").rglob("*") if p.is_file())
    assert raw, "the fixture should have raw data"
    assert [n for n in names if n.startswith("raw-data/")] == raw
    assert sorted(n for n in names if "/" not in n) == flat_names(stf_dir)


def test_unzipped_zip_is_a_valid_stf_directory(stf_dir, tmp_path):
    path, _ = zip_stf(stf_dir)
    out = tmp_path / "unzipped"
    with zipfile.ZipFile(path) as z:
        z.extractall(out)
    assert (out / "study.yaml").read_bytes() == (stf_dir / "study.yaml").read_bytes()
    assert check_stf(out)["errors"] == []


def test_same_directory_gives_the_same_bytes(stf_dir, tmp_path):
    a, _ = zip_stf(stf_dir, tmp_path / "a.zip")
    b, _ = zip_stf(stf_dir, tmp_path / "b.zip")
    assert a.read_bytes() == b.read_bytes()


def test_out_path_is_used_and_an_existing_zip_is_replaced(stf_dir, tmp_path):
    target = tmp_path / "mine.zip"
    target.write_bytes(b"old")
    path, _ = zip_stf(stf_dir, target)
    assert path == target
    assert zipfile.is_zipfile(target)
    assert not (tmp_path / "mine.zip.tmp").exists()


def test_refuses_a_directory_that_is_not_an_stf_directory(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError, match="study.yaml"):
        zip_stf(tmp_path / "empty")


def test_refuses_a_missing_directory(tmp_path):
    with pytest.raises(ValueError, match="Not a directory"):
        zip_stf(tmp_path / "nope")


def test_refuses_a_directory_with_no_entity_files(stf_dir):
    for p in stf_dir.glob("entity-*.tsv"):
        p.unlink()
    with pytest.raises(ValueError, match="entity-"):
        zip_stf(stf_dir)


def test_refuses_to_write_inside_the_stf_directory(stf_dir):
    with pytest.raises(ValueError, match="outside the STF directory"):
        zip_stf(stf_dir, stf_dir / "inside.zip")
    assert not (stf_dir / "inside.zip").exists()


def test_refuses_an_out_path_that_is_not_a_zip(stf_dir, tmp_path):
    with pytest.raises(ValueError, match=r"\.zip"):
        zip_stf(stf_dir, tmp_path / "out.tar")


def test_refuses_raw_data_when_there_is_none(stf_dir):
    shutil.rmtree(stf_dir / "raw-data")
    with pytest.raises(ValueError, match="raw-data"):
        zip_stf(stf_dir, with_raw_data=True)


def test_cli_lists_the_files_and_writes_the_zip(stf_dir):
    r = run_cli("zip", str(stf_dir))
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0] == "study.yaml"
    assert lines[-1].startswith("Wrote ") and "study-stf.zip" in lines[-1]
    assert zipfile.is_zipfile(stf_dir.with_name("study-stf.zip"))


def test_cli_reports_errors_as_usage_errors(tmp_path):
    r = run_cli("zip", str(tmp_path))
    assert r.returncode == 1
    assert r.stderr.startswith("Error: ") and "study.yaml" in r.stderr


def test_cli_needs_exactly_one_directory():
    r = run_cli("zip")
    assert r.returncode == 1
    assert "Usage: stf.py zip" in r.stderr
