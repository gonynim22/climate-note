"""Bind executed official source bytes to the downloaded, pinned archive."""

import hashlib
import json
from pathlib import Path
import zipfile

from .contracts import sha256


def file_snapshot(paths) -> dict:
    return {str(Path(path).resolve()): sha256(Path(path)) for path in paths}


def source_evidence(source: Path) -> dict:
    source = source.resolve()
    bootstrap_path = source.parent.parent / "bootstrap.json"
    bootstrap = json.loads(bootstrap_path.read_text(encoding="utf-8"))
    asset = next(item for item in bootstrap["assets"] if item["url"].startswith("https://codeload.github.com/"))
    archive_path = Path(asset["path"])
    if sha256(archive_path) != asset["sha256"] or asset["url"].rsplit("/", 1)[-1] != bootstrap["revision"]:
        raise ValueError("Pinned source archive provenance changed")
    records = {}
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            relative = Path(*Path(name).parts[1:])
            if relative.suffix.lower() not in {".py", ".yaml", ".yml"}:
                continue
            digest = hashlib.sha256(archive.read(name)).hexdigest()
            if sha256(source / relative) != digest:
                raise ValueError(f"Official source differs from the pinned archive: {relative}")
            records[relative.as_posix()] = digest
    if not records:
        raise ValueError("Empty source archive")
    return {"revision": bootstrap["revision"], "bootstrap_sha256": sha256(bootstrap_path),
            "archive_sha256": asset["sha256"], "verified_python_yaml_files": len(records),
            "tree_sha256": hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()}
