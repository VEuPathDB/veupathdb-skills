"""study-wrangler container: version constant, engine detection, container args, validation."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

STUDY_WRANGLER_VERSION = "1.0.56"
STUDY_WRANGLER_IMAGE = f"veupathdb/study-wrangler:{STUDY_WRANGLER_VERSION}"

SCRIPT = Path(__file__).resolve().parent / "study-wrangler-validate-study.R"

# Runs a command (engine first), returns stdout, raises subprocess.CalledProcessError on failure.
Exec = Callable[[list[str]], str]


def default_exec(cmd: list[str]) -> str:
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True
    ).stdout


def failure_output(e: BaseException) -> str:
    """What a failed command printed, so a finding says why."""
    parts = [getattr(e, "stdout", None), getattr(e, "stderr", None)]
    return "\n".join(p for p in parts if p).strip() or str(e)


def detect_engine(exec: Exec = default_exec, preferred: str | None = None) -> str | None:
    """'docker' | 'podman' | None: the first engine that answers `version`; only `preferred` if given."""
    for engine in [preferred] if preferred else ["docker", "podman"]:
        try:
            exec([engine, "version"])
            return engine
        except Exception:
            pass  # not installed, or its daemon is down
    return None


def container_args(engine: str, stf_dir: Path, script_path: Path) -> list[str]:
    """Arguments for `<engine> ...`. Read-only mounts, so nothing is written as root; never pulls the image.

    Docker's -v would create a missing source as a root-owned directory, so it gets --mount, which errors.
    Podman keeps -v with ,Z (SELinux relabel): its --mount relabel option could not be confirmed.
    """
    mounts: list[str] = []
    for src, dst in [(Path(stf_dir).absolute(), "/stf"), (Path(script_path).absolute(), "/sw/validate-study.R")]:
        if engine == "podman":
            mounts += ["-v", f"{src}:{dst}:ro,Z"]
        else:
            mounts += ["--mount", f"type=bind,src={src},dst={dst},readonly"]
    return ["run", "--rm", "--pull=never", *mounts, STUDY_WRANGLER_IMAGE, "Rscript", "/sw/validate-study.R", "/stf"]


def pull_commands() -> list[str]:
    return [f"docker pull {STUDY_WRANGLER_IMAGE}", f"podman pull docker.io/{STUDY_WRANGLER_IMAGE}"]


def image_missing_reason(engine: str, exec: Exec = default_exec) -> str | None:
    """None if `image inspect` finds the pinned image, else what the engine said (no image, daemon down, ...)."""
    try:
        exec([engine, "image", "inspect", STUDY_WRANGLER_IMAGE])
        return None
    except (subprocess.CalledProcessError, OSError) as e:
        return failure_output(e)


def image_present(engine: str, exec: Exec = default_exec) -> bool:
    return image_missing_reason(engine, exec) is None


def validate_study_in_container(stf_dir: Path, engine: str, exec: Exec = default_exec) -> tuple[str, str]:
    """Validates an STF directory in the pinned container: (status, output).

    status is 'pass', 'fail', 'error' (it loaded, but geo inference or validate() raised an R error:
    STF_VALIDATION_ERROR) or 'load-error' (STF_LOAD_ERROR, no marker at all, or the image is absent).
    The first output line is always the image. The image is never pulled.
    """
    if not engine:
        raise ValueError("No container engine (docker or podman) found")
    stf_dir = Path(stf_dir)
    if not stf_dir.is_dir():
        raise ValueError(f"STF directory not found: {stf_dir}")
    if not SCRIPT.exists():
        raise ValueError(f"Validator script not found: {SCRIPT}")
    header = f"Image: {STUDY_WRANGLER_IMAGE}"
    reason = image_missing_reason(engine, exec)
    if reason is not None:
        lines = [
            header,
            "The image is not present, and this script never downloads it. "
            "Ask the user before pulling it (about 6 GB), with one of:",
            *(f"  {c}" for c in pull_commands()),
            "Engine said:",
            reason,
        ]
        return "load-error", "\n".join(lines)
    try:
        output = exec([engine, *container_args(engine, stf_dir, SCRIPT)]).strip()
    except (subprocess.CalledProcessError, OSError) as e:
        output = failure_output(e)
    # the engine's own failures (no daemon) carry no marker, so they are load-errors too
    if re.search(r"^STF_VALIDATION: PASS\s*$", output, re.M):
        status = "pass"
    elif re.search(r"^STF_VALIDATION: FAIL\s*$", output, re.M):
        status = "fail"
    elif re.search(r"^STF_VALIDATION_ERROR:", output, re.M):
        status = "error"
    else:
        status = "load-error"
    return status, f"{header}\n{output}"
