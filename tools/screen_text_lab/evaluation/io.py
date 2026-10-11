"""Verify saved selection-run artifacts without importing OCR or image code."""
import json
from pathlib import Path
import re

from ..corpus import ID_PATTERN, contained_file, digest, json_hash
from ..metrics import score_case


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def _read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream, parse_constant=_reject_constant)


def _hashes(value):
    return isinstance(value, dict) and bool(value) and all(
        isinstance(key, str) and isinstance(item, str) and _SHA256.fullmatch(item)
        for key, item in value.items())


def load_crop_run(run_directory, *, expected_manifest_sha256=None):
    """Return records/cases/provenance only after a completed run verifies.

    No path named by the request is opened. Model/dictionary/image copies are
    read as bytes only inside the explicit run directory. The optional expected
    manifest digest is supplied by the caller's already-selected dataset; use
    it for paired comparisons. The scorer independently compares every case to
    the complete external manifest, so equal subset runs cannot pass.
    """
    directory = Path(run_directory).resolve()
    paths = {name: contained_file(directory, name) for name in ("result.json", "request.json", "cases.jsonl")}
    before = {name: digest(path) for name, path in paths.items()}
    result, request = _read_json(paths["result.json"]), _read_json(paths["request.json"])
    if (result.get("kind") != "selection_line_crop" or result.get("status") != "completed"
            or result.get("run_id") != directory.name or result.get("evaluation_scope") != "line_crop"):
        raise ValueError("Only a completed, correctly identified selection crop run can be loaded")
    if result.get("cases_sha256") != before["cases.jsonl"]:
        raise ValueError("Saved cases file hash mismatch")
    for key in ("source", "inputs"):
        old, new = result.get(key + "_before"), result.get(key + "_after")
        if not _hashes(old) or old != new:
            raise ValueError(f"Run {key} snapshot is missing or changed")
    audit = result.get("dataset_audit", {})
    manifest_sha = audit.get("manifest_sha256")
    if audit.get("status") != "passed" or not isinstance(manifest_sha, str) or not _SHA256.fullmatch(manifest_sha):
        raise ValueError("Dataset audit/manifest hash is missing")
    if not isinstance(request.get("dataset"), str) or not request["dataset"]:
        raise ValueError("Request dataset identity is missing")
    # Resolve only the path string; do not read the source dataset or any final
    # material. All source-image checks below use the saved run's own copies.
    manifest_path = str((Path(request["dataset"]) / "manifest.json").resolve())
    input_hashes = {str(Path(path).resolve()): value for path, value in result["inputs_before"].items()}
    if input_hashes.get(manifest_path) != manifest_sha:
        raise ValueError("Request dataset manifest differs from the audited input")
    if expected_manifest_sha256 is not None and manifest_sha != expected_manifest_sha256:
        raise ValueError("Run uses a different expected manifest")
    model = request.get("model", {})
    if (model != result.get("model") or model.get("role") not in {"P", "R", "F"}
            or not isinstance(model.get("id"), str) or not model["id"] or not model.get("provenance")):
        raise ValueError("Run/request model identity mismatch")
    for key, name in (("model", "model.onnx"), ("dictionary", "dictionary.txt")):
        path = contained_file(directory, name)
        value = digest(path)
        if value != model.get(key + "_sha256"):
            raise ValueError(f"Saved {key} hash mismatch")
        paths[name], before[name] = path, value
    cases = request.get("cases")
    if not isinstance(cases, list) or not cases or audit.get("cases") != len(cases):
        raise ValueError("Request cases differ from the audited count")
    expected = {}
    for case in cases:
        identifier = case.get("case_id")
        if (not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier) or identifier in expected
                or case.get("split") != "selection" or case.get("evaluation_scope") != "line_crop"):
            raise ValueError("Invalid or nonselection request case")
        expected[identifier] = case
        path = contained_file(directory, f"cases/{identifier}.png")
        value = digest(path)
        if value != case.get("image_sha256"):
            raise ValueError("Saved case image hash mismatch")
        paths[f"cases/{identifier}.png"], before[f"cases/{identifier}.png"] = path, value
    records = []
    with open(paths["cases.jsonl"], encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                raise ValueError("Empty cases JSONL record")
            records.append(json.loads(line, parse_constant=_reject_constant))
    observed = set()
    for record in records:
        identifier = record.get("case_id")
        if identifier not in expected or identifier in observed or record.get("status") != "ok":
            raise ValueError("Incomplete, duplicate or unrelated saved case")
        case = expected[identifier]
        if any(record.get(key) != value for key, value in case.items()):
            raise ValueError("Saved case metadata differs from the request")
        if record.get("expected_sha256") != json_hash(case["expected"]):
            raise ValueError("Saved expected-text hash mismatch")
        if record.get("metrics") != score_case(case, record["prediction"]):
            raise ValueError("Saved metric differs from the canonical scorer")
        observed.add(identifier)
    if observed != set(expected):
        raise ValueError("Saved run does not contain all requested cases")
    if any(digest(path) != before[name] for name, path in paths.items()):
        raise ValueError("Saved artifacts changed while reading")
    return {"directory": str(directory), "records": records, "cases": cases,
            "provenance": {"kind": result["kind"], "run_id": result["run_id"], "status": result["status"],
                           "model": model, "manifest_sha256": manifest_sha,
                           "result_sha256": before["result.json"], "request_sha256": before["request.json"],
                           "cases_sha256": before["cases.jsonl"], "source_sha256": json_hash(result["source_before"]),
                           "inputs_sha256": json_hash(result["inputs_before"]), "files": before}}
