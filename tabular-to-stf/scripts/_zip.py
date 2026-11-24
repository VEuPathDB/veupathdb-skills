"""Zips an STF directory for hand-over. Standard library only, so it works wherever Python does."""

import os
import shutil
import zipfile
from pathlib import Path

# For reproducible archives (tests) every file gets this time, the earliest a zip can hold.
_FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def _entries(stf_dir: Path, with_raw_data: bool) -> list[tuple[str, Path]]:
    """(name in the zip, file on disk) pairs, in a stable order.

    The STF files sit flat at the top of the zip. raw-data/ keeps its folder."""
    entity_tsvs = sorted(stf_dir.glob("entity-*.tsv"))
    if not entity_tsvs:
        raise ValueError(f"{stf_dir} has no entity-*.tsv files; not an STF directory")
    names = ["study.yaml"]
    names += [p.name for p in entity_tsvs]
    names += sorted(p.name for p in stf_dir.glob("entity-*.yaml"))
    names += [n for n in ("curation-notes.md", "curation-spec.json") if (stf_dir / n).is_file()]
    entries = [(n, stf_dir / n) for n in names]
    if with_raw_data:
        raw = stf_dir / "raw-data"
        if not raw.is_dir():
            raise ValueError(f"{stf_dir} has no raw-data/ directory to include")
        entries += [(f"raw-data/{p.relative_to(raw).as_posix()}", p)
                    for p in sorted(raw.rglob("*")) if p.is_file()]
    return entries


def zip_stf(stf_dir, out_path=None, with_raw_data: bool = False,
            reproducible: bool = False) -> tuple[Path, list[str]]:
    """Writes the zip and returns (its path, the names it holds).

    Files keep their modified times. With reproducible=True every file gets a fixed
    time instead, so the same files in the same order give the same bytes.

    The default path is <stf_dir>.zip, beside the directory. The zip must not be
    inside the STF directory, because a later render refuses a directory that holds
    files it did not write."""
    stf_dir = Path(stf_dir).resolve()
    if not stf_dir.is_dir():
        raise ValueError(f"Not a directory: {stf_dir}")
    if not (stf_dir / "study.yaml").is_file():
        raise ValueError(f"{stf_dir} has no study.yaml; not an STF directory")
    out = Path(out_path).resolve() if out_path else stf_dir.with_name(stf_dir.name + ".zip")
    if out.suffix.lower() != ".zip":
        raise ValueError(f"--out must end in .zip, got {out.name}")
    if out.is_relative_to(stf_dir):
        raise ValueError(f"--out must be outside the STF directory {stf_dir}")
    if not out.parent.is_dir():
        raise ValueError(f"Not a directory: {out.parent}")

    entries = _entries(stf_dir, with_raw_data)
    tmp = out.with_name(out.name + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for name, path in entries:
                if reproducible:
                    info = zipfile.ZipInfo(name, _FIXED_TIME)
                    info.external_attr = 0o644 << 16
                else:
                    info = zipfile.ZipInfo.from_file(path, name, strict_timestamps=False)
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(path, "rb") as src, z.open(info, "w") as dst:
                    shutil.copyfileobj(src, dst)
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    return out, [name for name, _ in entries]
