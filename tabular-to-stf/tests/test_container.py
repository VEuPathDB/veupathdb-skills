import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from _check import check_stf
from _container import (
    SCRIPT, STUDY_WRANGLER_IMAGE, STUDY_WRANGLER_VERSION, container_args, detect_engine,
    image_present, pull_commands, validate_study_in_container,
)
from _render import render_to_dir
from conftest import FIXTURES, run_cli


def failing(returncode, stdout="", stderr=""):
    return subprocess.CalledProcessError(returncode, ["docker"], stdout, stderr)


def with_image(run):
    """A fake exec that answers `image inspect` with success and everything else with `run`."""
    def fake(cmd):
        if cmd[1:3] == ["image", "inspect"]:
            return ""
        return run(cmd)
    return fake


def test_the_image_is_pinned_to_one_version_constant():
    assert STUDY_WRANGLER_IMAGE == f"veupathdb/study-wrangler:{STUDY_WRANGLER_VERSION}"


def test_container_args_mounts_read_only_never_pulls_and_docker_refuses_a_missing_source():
    assert container_args("docker", Path("stf"), Path("/x/v.R")) == [
        "run", "--rm", "--pull=never",
        "--mount", f"type=bind,src={Path('stf').absolute()},dst=/stf,readonly",
        "--mount", f"type=bind,src={Path('/x/v.R').absolute()},dst=/sw/validate-study.R,readonly",
        STUDY_WRANGLER_IMAGE, "Rscript", "/sw/validate-study.R", "/stf",
    ]
    assert container_args("podman", Path("/d/stf"), Path("/x/v.R")) == [
        "run", "--rm", "--pull=never",
        "-v", f"{Path('/d/stf').absolute()}:/stf:ro,Z",
        "-v", f"{Path('/x/v.R').absolute()}:/sw/validate-study.R:ro,Z",
        STUDY_WRANGLER_IMAGE, "Rscript", "/sw/validate-study.R", "/stf",
    ]


def test_a_missing_directory_or_a_file_is_refused_before_the_engine_runs(tmp_path):
    def fake(cmd):
        raise AssertionError("exec must not run")
    with pytest.raises(ValueError, match="STF directory not found: .*nonexistent-xyz-stf"):
        validate_study_in_container(tmp_path / "nonexistent-xyz-stf", "docker", exec=fake)
    with pytest.raises(ValueError, match="STF directory not found"):
        validate_study_in_container(SCRIPT, "docker", exec=fake)


def test_detect_engine_tries_docker_first_then_podman_then_gives_up():
    tried = []

    def only(ok):
        def fake(cmd):
            tried.append(cmd)
            if cmd[0] not in ok:
                raise OSError("nope")
            return ""
        return fake

    assert detect_engine(only(["docker", "podman"])) == "docker"
    assert tried == [["docker", "version"]]
    assert detect_engine(only(["podman"])) == "podman"
    assert detect_engine(only([])) is None
    assert detect_engine(only(["docker", "podman"]), preferred="podman") == "podman"
    assert detect_engine(only(["docker"]), preferred="podman") is None


def test_validate_takes_status_from_the_marker_line(tmp_path):
    def run(out):
        return validate_study_in_container(tmp_path, "docker", exec=with_image(lambda c: out))

    status, output = run("ok\nSTF_VALIDATION: PASS\n")
    assert status == "pass"
    assert output == f"Image: {STUDY_WRANGLER_IMAGE}\nok\nSTF_VALIDATION: PASS"
    assert run("bad row\nSTF_VALIDATION: FAIL\n")[0] == "fail"
    assert run("STF_LOAD_ERROR: no study.yaml\n")[0] == "load-error"
    assert run("STF_VALIDATION_ERROR: Can't subset elements that don't exist.\n")[0] == "error"


def raises(e):
    def run(cmd):
        raise e
    return run


def test_an_r_error_in_geo_inference_or_validate_is_status_error_not_a_load_error(tmp_path):
    exec = with_image(raises(failing(2, "STF_VALIDATION_ERROR: join failed\n")))
    status, output = validate_study_in_container(tmp_path, "docker", exec=exec)
    assert status == "error"
    assert "STF_VALIDATION_ERROR: join failed" in output


@pytest.mark.skipif(sys.platform == "win32", reason="needs a #!/bin/sh fake engine")
def test_cli_result_error_exits_2_fake_docker_on_path(tmp_path):
    fake = tmp_path / "docker"
    fake.write_text(
        '#!/bin/sh\n[ "$1" = version ] && exit 0\n[ "$1" = image ] && exit 0\n'
        'echo "STF_VALIDATION_ERROR: join failed"\nexit 2\n', encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    env = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"}
    r = run_cli("validate", str(tmp_path), "--engine", "docker", env=env)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "\nResult: error\n" in "\n" + r.stdout


def test_a_failing_run_still_reports_its_marker_from_stdout_and_stderr_together(tmp_path):
    exec = with_image(raises(failing(1, "== entity: a ==\nSTF_VALIDATION: FAIL\n", "warn")))
    status, output = validate_study_in_container(tmp_path, "docker", exec=exec)
    assert status == "fail"
    assert "entity: a" in output and "FAIL" in output and "warn" in output
    assert output.index("FAIL") < output.index("warn")


def test_a_non_zero_exit_with_no_marker_is_a_load_error_carrying_the_output(tmp_path):
    exec = with_image(raises(failing(125, "", "image not known")))
    status, output = validate_study_in_container(tmp_path, "podman", exec=exec)
    assert status == "load-error"
    assert "image not known" in output


def test_validate_runs_the_engine_with_container_args(tmp_path):
    calls = []

    def run(cmd):
        calls.append(cmd)
        return "STF_VALIDATION: PASS"

    validate_study_in_container(tmp_path, "docker", exec=with_image(run))
    assert calls == [["docker", *container_args("docker", tmp_path, SCRIPT)]]


def test_image_present_runs_image_inspect_on_the_pinned_image():
    calls = []
    assert image_present("podman", exec=lambda c: calls.append(c) or "")
    assert calls == [["podman", "image", "inspect", STUDY_WRANGLER_IMAGE]]


def test_missing_image_prints_pull_commands_and_is_a_load_error(tmp_path):
    def fake(cmd):
        if cmd[1:3] == ["image", "inspect"]:
            raise subprocess.CalledProcessError(1, cmd, "", "No such image")
        raise AssertionError("container must not run")

    status, output = validate_study_in_container(tmp_path, "docker", exec=fake)
    assert status == "load-error"
    assert output.splitlines()[0] == f"Image: {STUDY_WRANGLER_IMAGE}"
    for c in pull_commands():
        assert c in output


def test_cli_without_a_directory_prints_usage_and_fails():
    r = run_cli("validate")
    assert r.returncode == 1
    assert "Usage: stf.py validate" in r.stderr


# Opt-in: needs a container engine and the pinned image already present locally.
integration = pytest.mark.skipif(os.environ.get("STF_CONTAINER_TESTS") != "1", reason="set STF_CONTAINER_TESTS=1")
DATASETS = ["clinical-epi", "mosquito", "coffee-shops"]


@pytest.fixture(scope="module")
def engine():
    e = detect_engine()
    if e is None:
        pytest.fail("no container engine")
    return e


def rendered(dataset, tmp_path) -> Path:
    base = FIXTURES / "tabular" / dataset
    work = tmp_path / "work"
    work.mkdir()
    shutil.copytree(base / "inputs", work / "inputs")
    shutil.copy(base / "spec.json", work / "spec.json")
    out = tmp_path / "out"
    render_to_dir(work / "spec.json", out)
    return out


def read(p: Path) -> str:
    return p.read_bytes().decode("utf-8")


def write(p: Path, text: str):
    p.write_bytes(text.encode("utf-8"))


@integration
@pytest.mark.parametrize("dataset", DATASETS)
def test_container_golden_passes_baseline_and_eda(dataset, tmp_path, engine):
    status, output = validate_study_in_container(rendered(dataset, tmp_path), engine)
    assert status == "pass", output


@integration
def test_container_an_orphan_child_row_does_not_pass(tmp_path, engine):
    d = rendered("mosquito", tmp_path)
    tsv = d / "entity-assay.tsv"
    lines = read(tsv).rstrip("\n").split("\n")
    orphan = lines[1].split("\t")
    orphan[0] = "NO_SUCH_SAMPLE"  # first column is the parent id
    orphan[1] = "A_ORPHAN"
    write(tsv, "\n".join(lines + ["\t".join(orphan)]) + "\n")
    status, output = validate_study_in_container(d, engine)
    assert status != "pass", output


@integration
def test_container_a_parent_id_column_under_another_name_is_status_error(tmp_path, engine):
    import re
    d = rendered("clinical-epi", tmp_path)
    tsv = d / "entity-household.tsv"
    write(tsv, re.sub(r"^village_id\t", "village_id_2\t", read(tsv)))
    y = d / "entity-household.yaml"
    write(y, read(y).replace("- id_column: village_id\n", "- id_column: village_id_2\n"))
    assert any("village_id_2 refers to village" in e for e in check_stf(d)["errors"])
    status, output = validate_study_in_container(d, engine)
    assert status == "error", output
    assert "STF_VALIDATION_ERROR:" in output


@integration
def test_container_stripped_optional_metadata_still_loads(tmp_path, engine):
    import re
    d = rendered("mosquito", tmp_path)
    for e in ["site", "collection", "sample", "assay"]:
        p = d / f"entity-{e}.yaml"
        text = read(p)
        if "\ncategories:" in text:
            text = text[: text.index("\ncategories:")]
        kept = [l for l in text.split("\n") if not re.match(r"^\s+(definition|unit|parent_category):", l)]
        write(p, "\n".join(kept) + "\n")
    assert check_stf(d)["errors"] == []
    status, output = validate_study_in_container(d, engine)
    assert status != "load-error", output


@integration
def test_container_geohash_columns_already_present_do_not_break_validation(tmp_path, engine):
    import re
    d = rendered("mosquito", tmp_path)
    names = [f"geohash_{n}" for n in range(1, 7)]
    tsv = d / "entity-site.tsv"  # the geo entity: latitude and longitude
    lines = read(tsv).rstrip("\n").split("\n")
    rows = [
        "\t".join([l, *names] if i == 0 else [l, *("abcdef"[: k + 1] for k in range(len(names)))])
        for i, l in enumerate(lines)
    ]
    write(tsv, "\n".join(rows) + "\n")
    y = d / "entity-site.yaml"
    yaml = read(y)
    block = "".join(
        f"  - variable: {n}\n    provider_label:\n      - {n}\n    display_name: {n}\n"
        "    data_type: string\n    data_shape: categorical\n" for n in names)
    assert "\nvariables:\n" in yaml
    m = re.search(r"(\nvariables:\n(?:  .*\n|\n)*?)(?=\S|$)", yaml)
    write(y, yaml[: m.start()] + m.group(0).rstrip() + "\n" + block + yaml[m.end():])
    status, output = validate_study_in_container(d, engine)
    assert status == "pass", output
