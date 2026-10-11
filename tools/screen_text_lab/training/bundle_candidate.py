"""Register a trained/initialized candidate only after complete export parity.

Manual CPU tool. The 21 probes check this checkpoint's Paddle→ONNX conversion;
they do not require parity with P and do not measure OCR accuracy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from .compare import (ATOL, RTOL, EXPECTED_IDS, _conversion_chain, _hash, _json,
                      _local, validate_manifest, validate_probabilities, validate_session)
from .contracts import class_mapping, class_tokens, sha256


def verify_bundle_provenance(bundle_path, metadata, files):
    """Check a saved successful report and its current files, without inference.

    Supports current F/R_B candidate reports and the earlier zero-step R_A
    reproduction report. Bare origin declarations never authorize inference.
    """
    bundle_path = Path(bundle_path).resolve()
    provenance = metadata.get("provenance", {})
    observed = {}

    def remember(path, expected):
        path = Path(path).resolve()
        if not _hash(expected) or sha256(path) != expected:
            raise ValueError(f"Bundle provenance hash mismatch: {path.name}")
        if str(path) in observed and observed[str(path)] != expected:
            raise ValueError("Bundle evidence changed while reading")
        observed[str(path)] = expected
        return path

    for key in ("model", "dictionary"):
        remember(files[key], metadata.get(key + "_sha256"))
    candidate = provenance.get("kind") == "audited_candidate_export"
    if candidate:
        parity = provenance.get("parity", {})
        report_path = remember(_local(bundle_path.parent, parity.get("path")), parity.get("sha256"))
    elif (metadata.get("role") == "R" and type(provenance.get("training_steps")) is int
          and provenance["training_steps"] == 0 and isinstance(provenance.get("reproduction_report"), str)):
        report_path = remember(Path(provenance["reproduction_report"]), provenance.get("reproduction_report_sha256"))
    else:
        raise ValueError("Bundle needs a successful candidate or zero-step R reproduction report")
    report = _json(report_path)
    if report.get("status") not in {"passed", "passed_product_visible"} or report.get("atol") != ATOL or report.get("rtol") != RTOL:
        raise ValueError("Bundle parity report did not pass the fixed tolerances")
    snapshot = report.get("files")
    if not isinstance(snapshot, dict) or not snapshot:
        raise ValueError("Bundle parity report has no file snapshot")
    for path, expected in snapshot.items():
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise ValueError("Parity snapshot paths must be absolute")
        remember(Path(path), expected)
    model_path = Path(files["model"]).resolve()
    if snapshot.get(str(model_path)) != metadata["model_sha256"]:
        raise ValueError("Bundle model was not measured by its parity report")
    if candidate:
        if (report.get("scope") != "candidate_checkpoint_paddle_to_onnx_parity_only"
                or report.get("text_scope") != "all_21_probes_including_noise"
                or report.get("provenance_unchanged") is not True
                or report.get("role") != metadata.get("role") or report.get("id") != metadata.get("id")):
            raise ValueError("Candidate report role/id/scope differs from bundle")
        items = report.get("items", [])
        numeric_key = "product_visible_allclose" if report["status"] == "passed_product_visible" else "allclose"
        if ([item.get("id") for item in items] != list(EXPECTED_IDS)
                or not all(item.get(key) is True for item in items for key in (numeric_key, "strings_equal", "warning_080_equal"))):
            raise ValueError("Candidate parity report is incomplete or contains differences")
        if report["status"] == "passed_product_visible" and (
                report.get("full_tensor_parity") is not False or metadata.get("full_tensor_parity") is not False
                or metadata.get("parity_scope") != "product_visible_ctc_steps"
                or all(item.get("allclose") is True for item in items)):
            raise ValueError("Padding-only numerical differences must remain explicit")
        export_path = remember(bundle_path.parent / "result.json", provenance.get("export_result_sha256"))
        conversion_path = remember(bundle_path.parent / "rec.conversion.json", provenance.get("conversion_result_sha256"))
        exported = _json(export_path)
        expected_status = {"F": {"exported_trained", "exported_diagnostic"}, "R": {"exported_initialized"}}.get(metadata.get("role"), set())
        origin = exported.get("origin_result", {})
        if (exported.get("status") not in expected_status
                or exported.get("role") != metadata["role"] or exported.get("id") != metadata["id"]
                or exported.get("dictionary_sha256") != metadata["dictionary_sha256"]
                or origin != provenance.get("origin_result")
                or exported.get("checkpoint_sha256") != provenance.get("checkpoint_sha256")
                or exported.get("input_manifest_sha256") != provenance.get("input_manifest_sha256")
                or exported.get("source") != provenance.get("source")):
            raise ValueError("Bundle differs from its candidate export/origin")
        if (snapshot.get(str(export_path)) != observed[str(export_path)]
                or snapshot.get(str(conversion_path)) != observed[str(conversion_path)]
                or snapshot.get(str(Path(origin.get("path", "")).resolve())) != origin.get("sha256")):
            raise ValueError("Candidate report did not bind export/conversion/origin")
        origin_data = _json(remember(Path(origin["path"]), origin["sha256"]))
        if exported.get("status") == "exported_diagnostic" and (
                metadata.get("scope") != "bn_stat_combination_diagnostic"
                or provenance.get("origin_kind") != "bn_stat_combination_diagnostic"
                or origin_data.get("status") != "diagnostic_completed"
                or provenance.get("mode") != origin_data.get("mode")
                or provenance.get("additional_training_steps") != 0):
            raise ValueError("Diagnostic bundle lost its separate zero-additional-training scope")
    else:
        if report["status"] != "passed":
            raise ValueError("Untrained R reproduction requires full tensor parity")
        if not all(report.get(key) is True for key in ("tensor_allclose", "text_strings_equal", "warning_080_equal")):
            raise ValueError("R reproduction gates did not all pass")
        required = [item for item in report.get("items", []) if item.get("required") is True]
        expected_pairs = {(identifier, tuple(pair)) for identifier in EXPECTED_IDS
                          for pair in (("P", "R_cpu"), ("P", "R_gpu"), ("P", "R_onnx"),
                                       ("R_cpu", "R_gpu"), ("R_cpu", "R_onnx"))}
        if (len(required) != len(expected_pairs)
                or {(item.get("id"), tuple(item.get("pair", []))) for item in required} != expected_pairs
                or any(item.get("allclose") is not True or (not item.get("synthetic_noise") and
                       (item.get("strings_equal") is not True or item.get("warning_080_equal") is not True)) for item in required)):
            raise ValueError("R reproduction report lacks complete required P/R evidence")
        info = report.get("provenance", {})
        export_path = remember(_local(bundle_path.parent, provenance.get("export_result")), info.get("export_result_sha256"))
        conversion_path = remember(_local(bundle_path.parent, provenance.get("conversion_result")), info.get("R_conversion", {}).get("metadata_sha256"))
        exported = _json(export_path)
        if (exported.get("status") != "exported_untrained"
                or exported.get("dictionary_sha256") != metadata["dictionary_sha256"]
                or info.get("dictionary_sha256") != metadata["dictionary_sha256"]):
            raise ValueError("R bundle export/dictionary is unrelated to reproduction")
    _conversion_chain(conversion_path, model_path, export_path, lambda path, expected=None:
                      remember(path, expected if expected is not None else snapshot.get(str(Path(path).resolve()))))
    if any(sha256(Path(path)) != value for path, value in observed.items()):
        raise ValueError("Bundle provenance changed during verification")
    return {"kind": "candidate_export" if candidate else "untrained_reproduction", "report_path": str(report_path),
            "report_sha256": observed[str(report_path)], "files": observed}


def _training_origin(origin_path, origin, exported, remember):
    """Follow either a completed training result or a separately named BN diagnostic."""
    diagnostic = exported["status"] == "exported_diagnostic"
    if diagnostic:
        if (origin.get("status") != "diagnostic_completed" or origin.get("provenance_unchanged") is not True
                or type(origin.get("additional_training_steps")) is not int or origin["additional_training_steps"] != 0
                or origin.get("mode") not in {"trained_weights_original_bn", "original_weights_trained_bn"}):
            raise ValueError("BN diagnostic origin is incomplete or claims additional training")
        ref = origin.get("diagnostic_recipe", {})
        diagnostic_recipe = _json(remember(Path(ref.get("path", "")), ref.get("sha256", "")))
        parent_ref = origin.get("parent_training_result", {})
        if (diagnostic_recipe.get("parent_training_result") != parent_ref
                or diagnostic_recipe.get("mode") != origin["mode"]
                or diagnostic_recipe.get("additional_training_steps") != 0
                or diagnostic_recipe.get("source") != exported["source"]
                or any(diagnostic_recipe.get(key) is not True for key in ("all_other_tensors_bitwise_equal", "all_requested_stats_bitwise_equal"))):
            raise ValueError("Diagnostic recipe/source/preservation proof differs")
        proofs, stats = diagnostic_recipe.get("tensor_proofs", {}), diagnostic_recipe.get("stat_keys", [])
        if (not isinstance(proofs, dict) or not proofs or not isinstance(stats, list) or not stats
                or len(set(stats)) != len(stats)
                or set(stats) != {key for key in proofs if key.endswith(("._mean", "._variance"))}):
            raise ValueError("Diagnostic BN-stat key inventory is incomplete")
        statistic_source = "original" if origin["mode"] == "trained_weights_original_bn" else "trained"
        for key, proof in proofs.items():
            expected_source = statistic_source if key in stats else ("trained" if statistic_source == "original" else "original")
            if proof.get("source") != expected_source or not _hash(proof.get("sha256")):
                raise ValueError("Diagnostic tensor provenance differs from the declared BN combination")
        for key in ("original_checkpoint", "trained_checkpoint", "dictionary"):
            item = diagnostic_recipe.get(key, {})
            remember(Path(item.get("path", "")), item.get("sha256", ""))
        if (diagnostic_recipe.get("dictionary") != origin.get("dictionary")
                or origin["dictionary"].get("sha256") != exported["dictionary_sha256"]):
            raise ValueError("Diagnostic dictionary differs from parent/export")
        origin_path = remember(Path(parent_ref.get("path", "")), parent_ref.get("sha256", ""))
        parent = _json(origin_path)
        if parent.get("checkpoint") != diagnostic_recipe.get("trained_checkpoint"):
            raise ValueError("Diagnostic trained checkpoint differs from parent training")
    else:
        parent, diagnostic_recipe = origin, None
    if (parent.get("status") != "completed" or type(parent.get("completed_steps")) is not int
            or parent["completed_steps"] < 1 or parent.get("provenance_unchanged") is not True):
        raise ValueError("F requires completed, provenance-stable parent training")
    recipe = _json(remember(origin_path.parent / "recipe.json", parent.get("recipe_sha256", "")))
    if (recipe.get("loader", {}).get("dictionary_sha256") != exported["dictionary_sha256"]
            or recipe.get("source_config_sha256") != exported["config_sha256"]
            or recipe.get("source_revision") != exported["source"]["revision"]):
        raise ValueError("Training/export dictionary, config or revision differs")
    if diagnostic_recipe is not None and diagnostic_recipe["original_checkpoint"]["sha256"] != recipe.get("checkpoint_sha256"):
        raise ValueError("Diagnostic original checkpoint differs from the parent's actual initialization")
    before = _json(remember(origin_path.parent / "provenance-before.json", parent.get("provenance_before_sha256", "")))
    after = _json(remember(origin_path.parent / "provenance-after.json", parent.get("provenance_after_sha256", "")))
    if before != after or before.get("source") != exported["source"] or not before.get("files"):
        raise ValueError("Parent training provenance/source is incomplete or changed")
    return {"kind": "bn_stat_combination_diagnostic" if diagnostic else "finetuned_checkpoint",
            "mode": origin.get("mode") if diagnostic else None,
            "additional_training_steps": 0 if diagnostic else parent["completed_steps"],
            "parent_training_steps": parent["completed_steps"]}


def load_candidate_evidence(export_dir, inputs):
    """Validate stored provenance and tensors without loading a model runtime."""
    import numpy as np

    export_dir, inputs = Path(export_dir).resolve(), Path(inputs).resolve()
    files = {}

    def remember(path, expected=None):
        path = Path(path).resolve()
        value = sha256(path)
        if expected is not None and (not _hash(expected) or value != expected):
            raise ValueError(f"Candidate artifact hash mismatch: {path.name}")
        if str(path) in files and files[str(path)] != value:
            raise ValueError("Candidate artifact changed while loading")
        files[str(path)] = value
        return path

    result_path = remember(export_dir / "result.json")
    exported = _json(result_path)
    role = exported.get("role")
    statuses = {"F": {"exported_trained", "exported_diagnostic"}, "R": {"exported_initialized"}}.get(role, set())
    if (exported.get("status") not in statuses
            or exported.get("provenance_unchanged") is not True
            or not isinstance(exported.get("id"), str) or not exported["id"]):
        raise ValueError("Candidate export is incomplete or role/status differs")
    for key in ("checkpoint_sha256", "dictionary_sha256", "config_sha256", "architecture_sha256",
                "weight_audit_sha256", "producer_sha256", "input_manifest_sha256"):
        if not _hash(exported.get(key)):
            raise ValueError(f"Candidate export lacks {key}")
    source = exported.get("source", {})
    if (not isinstance(source.get("revision"), str) or len(source["revision"]) != 40
            or type(source.get("verified_python_yaml_files")) is not int or source["verified_python_yaml_files"] < 1
            or any(not _hash(source.get(key)) for key in ("tree_sha256", "archive_sha256", "bootstrap_sha256"))):
        raise ValueError("Candidate official source evidence is incomplete")
    origin_ref = exported.get("origin_result", {})
    if not isinstance(origin_ref.get("path"), str) or not _hash(origin_ref.get("sha256")):
        raise ValueError("Candidate origin result is missing")
    origin_path = remember(Path(origin_ref["path"]), origin_ref["sha256"])
    origin = _json(origin_path)
    checkpoint = origin.get("checkpoint", {})
    if not isinstance(checkpoint.get("path"), str) or checkpoint.get("sha256") != exported["checkpoint_sha256"]:
        raise ValueError("Candidate checkpoint differs from its origin")
    remember(Path(checkpoint["path"]), exported["checkpoint_sha256"])
    origin_scope = {"kind": "initialized_expansion", "additional_training_steps": 0}
    if role == "F":
        origin_scope = _training_origin(origin_path, origin, exported, remember)
    else:
        dictionary = origin.get("dictionary", {})
        if (origin.get("status") != "initialized" or not isinstance(dictionary.get("path"), str)
                or dictionary.get("sha256") != exported["dictionary_sha256"]
                or origin.get("training_steps") != 0 or origin.get("provenance_unchanged") is not True
                or origin.get("source") != source or origin.get("input_manifest_sha256") != exported["input_manifest_sha256"]):
            raise ValueError("R requires the initialized checkpoint's expanded dictionary")
        remember(Path(dictionary["path"]), exported["dictionary_sha256"])
    chars = remember(export_dir / "dict.txt", exported["dictionary_sha256"]).read_text(encoding="utf-8").splitlines()
    if not chars or "\0" in chars:
        raise ValueError("Candidate dictionary is empty or contains NUL")
    tokens = class_tokens(chars)
    charset, classes = list(tokens[1:]), len(tokens)
    architecture = _json(remember(export_dir / "architecture.json", exported["architecture_sha256"]))
    expansion = None
    if role == "R":
        proof_files = {}
        for key in ("architecture", "mapping", "proof"):
            ref = origin.get(key, {})
            if not isinstance(ref.get("path"), str) or not _hash(ref.get("sha256")):
                raise ValueError(f"Expansion {key} reference missing")
            proof_files[key] = _json(remember(Path(ref["path"]), ref["sha256"]))
        expansion = proof_files["proof"]
        old_count = expansion.get("old_dictionary_count")
        if (proof_files["architecture"] != architecture or type(old_count) is not int or not 0 < old_count < len(chars)
                or expansion.get("new_dictionary_count") != len(chars)
                or expansion.get("status") != "expanded_parameters_verified"
                or any(expansion.get(key) is not True for key in ("all_old_slices_bitwise_equal", "all_new_class_slices_initialization_preserved", "inputs_preserved"))):
            raise ValueError("Expansion architecture or preservation proof is incomplete")
        mappings = {head: class_mapping(chars[:old_count], chars, head) for head in ("ctc", "nrtr")}
        mappings["nrtr"].append(len(class_tokens(chars, "nrtr")))
        if proof_files["mapping"] != mappings or expansion.get("class_id_mapping") != mappings:
            raise ValueError("Expansion mapping differs from dictionary order/space/NRTR extra slot")
        logit = expansion.get("masked_old_ctc_logits", {})
        if logit.get("passed") is not True or logit.get("atol") != ATOL or logit.get("rtol") != RTOL:
            raise ValueError("Actual masked old-class logit parity was not measured/passed")
    audit = _json(remember(export_dir / "weight-audit.json", exported["weight_audit_sha256"]))
    if (audit.get("ok") is not True or type(audit.get("expected_count")) is not int or audit["expected_count"] < 1
            or audit.get("actual_count") != audit["expected_count"]
            or any(audit.get(key) != [] for key in ("missing", "extra", "shape_mismatches"))):
        raise ValueError("Candidate weight audit is incomplete")
    inventory = exported.get("export", [])
    if (not inventory or len({item.get("file") for item in inventory}) != len(inventory)
            or not {"inference.json", "inference.pdiparams"}.issubset(item.get("file") for item in inventory)):
        raise ValueError("Candidate export inventory is incomplete or duplicated")
    for item in inventory:
        path = remember(_local(export_dir, item.get("file")), item.get("sha256", ""))
        if path.stat().st_size != item.get("size"):
            raise ValueError("Candidate export size changed")
    conversion = _conversion_chain(export_dir / "rec.conversion.json", export_dir / "rec.onnx", result_path, remember)
    manifest = _json(remember(inputs / "manifest.json", exported["input_manifest_sha256"]))
    items = validate_manifest(manifest)
    if expansion is not None:
        logits = expansion["masked_old_ctc_logits"].get("items", [])
        if ([item.get("id") for item in logits] != list(EXPECTED_IDS)
                or any(row.get("allclose") is not True or row.get("input_sha256") != item["sha256"]
                       or row.get("shape") != item["output_shape"] for row, item in zip(logits, items))):
            raise ValueError("Expansion logit parity lacks all 21 frozen inputs/shapes")
    outputs = exported.get("outputs", [])
    if [item.get("id") for item in outputs] != list(EXPECTED_IDS):
        raise ValueError("Candidate CPU output IDs/order are incomplete or duplicated")
    if (len({item.get("tensor") for item in items}) != len(items)
            or [item.get("path") for item in outputs] != [f"{identifier}-cpu.npy" for identifier in EXPECTED_IDS]):
        raise ValueError("Candidate tensor/output files are aliased or unexpectedly named")
    loaded = []
    for item, recorded in zip(items, outputs):
        tensor = np.load(remember(_local(inputs, item.get("tensor")), item["sha256"]), allow_pickle=False)
        if tensor.dtype != np.float32 or list(tensor.shape) != item["shape"] or not np.isfinite(tensor).all():
            raise ValueError("Candidate input tensor dtype/shape/finite mismatch")
        if recorded.get("input_sha256") != item["sha256"]:
            raise ValueError("Candidate CPU output belongs to another input")
        prediction = np.load(remember(_local(export_dir, recorded.get("path")), recorded.get("sha256", "")), allow_pickle=False)
        validate_probabilities(prediction, batch=tensor.shape[0], classes=classes, label=item["id"])
        if list(prediction.shape) != recorded.get("shape") or list(prediction.shape[:2]) != item["output_shape"][:2]:
            raise ValueError("Candidate CPU output geometry differs from its recorded/frozen shape")
        loaded.append({"record": item, "tensor": tensor, "prediction": prediction})
    batch = loaded[6]["tensor"]
    for slot, entry in enumerate(loaded[:6]):
        width = entry["tensor"].shape[-1]
        if not np.array_equal(batch[slot, :, :, :width], entry["tensor"][0]) or np.any(batch[slot, :, :, width:] != 0):
            raise ValueError("Candidate mixed batch differs from frozen singles")
    if any(sha256(Path(path)) != value for path, value in files.items()):
        raise ValueError("Candidate evidence changed while loading")
    return {"export": exported, "origin": origin, "origin_scope": origin_scope, "charset": charset, "items": loaded, "files": files,
            "conversion": conversion, "input_manifest_sha256": exported["input_manifest_sha256"]}


def compare_output(record, tensor, expected, actual, charset, decoder):
    """Every probe, including noise, must preserve text and raw 0.80 warning."""
    import numpy as np

    for label, value in (("Paddle", expected), ("ONNX", actual)):
        validate_probabilities(value, batch=tensor.shape[0], classes=len(charset) + 1, label=label)
    if actual.shape != expected.shape:
        raise ValueError("Candidate Paddle/ONNX tensor shapes differ")
    decoding, visible_allclose, padding_differences = [], True, 0
    for slot, width in enumerate(record["widths"]):
        steps = max(1, int(np.ceil(expected.shape[1] * width / tensor.shape[-1])))
        visible_allclose &= bool(np.allclose(expected[slot, :steps], actual[slot, :steps], atol=ATOL, rtol=RTOL))
        padding_differences += int((~np.isclose(expected[slot, steps:], actual[slot, steps:], atol=ATOL, rtol=RTOL)).sum())
        left, left_score = decoder(expected[slot, :steps], charset)
        right, right_score = decoder(actual[slot, :steps], charset)
        decoding.append({"slot": slot, "steps": steps, "paddle_text": left, "onnx_text": right,
                         "strings_equal": left == right, "paddle_score": float(left_score), "onnx_score": float(right_score),
                         "warning_080_equal": (left_score < .8) == (right_score < .8)})
    absolute = np.abs(expected - actual)
    return {"id": record["id"], "synthetic_noise": record.get("synthetic_noise", False),
            "shape": list(actual.shape), "allclose": bool(np.allclose(expected, actual, atol=ATOL, rtol=RTOL)),
            "product_visible_allclose": visible_allclose, "padding_different_elements": padding_differences,
            "max_abs_diff": float(absolute.max()), "mean_abs_diff": float(absolute.mean()),
            "strings_equal": all(item["strings_equal"] for item in decoding),
            "warning_080_equal": all(item["warning_080_equal"] for item in decoding), "decoding": decoding}


def run(export_dir, inputs, registration_id=None):
    import onnxruntime as ort
    from screen_text.engine import ctc_decode

    export_dir = Path(export_dir).resolve()
    if registration_id is not None and (not isinstance(registration_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", registration_id)):
        raise ValueError("Registration ID must be a safe, short file suffix")
    suffix = "-" + registration_id if registration_id is not None else ""
    result_path, bundle_path = export_dir / f"candidate-parity{suffix}.json", export_dir / f"bundle{suffix}.json"
    if result_path.exists() or bundle_path.exists():
        raise FileExistsError("Candidate parity/bundle output already exists; preserve previous evidence")
    evidence = load_candidate_evidence(export_dir, inputs)
    code_directory = export_dir / ("evidence-code" + suffix)
    code_directory.mkdir(exist_ok=False)
    code = []
    for name in ("bundle_candidate.py", "compare.py", "contracts.py"):
        path = Path(__file__).with_name(name).resolve()
        value = sha256(path)
        saved = code_directory / name
        saved.write_bytes(path.read_bytes())
        if sha256(saved) != value or sha256(path) != value:
            raise ValueError("Verifier source changed during snapshot")
        evidence["files"][str(saved)] = value
        code.append({"original_path": str(path), "sha256": value, "saved_path": str(saved)})
    ort.disable_telemetry_events()
    options = ort.SessionOptions()
    options.intra_op_num_threads, options.inter_op_num_threads = 2, 1
    session = ort.InferenceSession(str(export_dir / "rec.onnx"), options, providers=["CPUExecutionProvider"])
    validate_session(session, len(evidence["charset"]) + 1)
    rows = []
    for item in evidence["items"]:
        actual = session.run(None, {"x": item["tensor"]})[0]
        rows.append(compare_output(item["record"], item["tensor"], item["prediction"], actual, evidence["charset"], ctc_decode))
        print(f"Candidate export parity: {item['record']['id']}", flush=True)
    unchanged = (all(sha256(Path(path)) == value for path, value in evidence["files"].items())
                 and all(sha256(Path(item["original_path"])) == item["sha256"] for item in code))
    complete = len(rows) == len(EXPECTED_IDS)
    full_passed = complete and all(row[key] for row in rows for key in ("allclose", "strings_equal", "warning_080_equal"))
    visible_passed = complete and all(row[key] for row in rows for key in ("product_visible_allclose", "strings_equal", "warning_080_equal"))
    status = ("inputs_changed" if not unchanged else "passed" if full_passed else
              "passed_product_visible" if visible_passed else "differences_found")
    exported = evidence["export"]
    result = {"schema_version": 1, "status": status, "full_tensor_parity": full_passed,
              "scope": "candidate_checkpoint_paddle_to_onnx_parity_only", "role": exported["role"], "id": exported["id"],
              "atol": ATOL, "rtol": RTOL, "text_scope": "all_21_probes_including_noise", "items": rows,
              "files": evidence["files"], "provenance_unchanged": unchanged, "producer_sha256": sha256(Path(__file__)),
              "verifier_code": code, "origin_scope": evidence["origin_scope"], "registration_id": registration_id,
              "limitations": ["No P/R initialization parity claim; this compares one checkpoint's export.",
                              "No OCR accuracy, product safety, latency or deployment approval."]}
    with result_path.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    if result["status"] in {"passed", "passed_product_visible"}:
        bundle = {"schema_version": 1, "role": exported["role"], "id": exported["id"], "model": "rec.onnx",
                  "model_sha256": evidence["files"][str(export_dir / "rec.onnx")], "dictionary": "dict.txt", "dictionary_sha256": exported["dictionary_sha256"],
                  "scope": evidence["origin_scope"]["kind"],
                  "full_tensor_parity": full_passed,
                  "parity_scope": "all_ctc_steps" if full_passed else "product_visible_ctc_steps",
                  "provenance": {"kind": "audited_candidate_export", "parity": {"path": result_path.name, "sha256": sha256(result_path)},
                                 "origin_kind": evidence["origin_scope"]["kind"], "mode": evidence["origin_scope"].get("mode"),
                                 "additional_training_steps": evidence["origin_scope"]["additional_training_steps"],
                                 "origin_result": exported["origin_result"], "export_result_sha256": sha256(export_dir / "result.json"),
                                 "conversion_result_sha256": sha256(export_dir / "rec.conversion.json"),
                                 "input_manifest_sha256": evidence["input_manifest_sha256"],
                                 "checkpoint_sha256": exported["checkpoint_sha256"], "source": exported["source"]}}
        with bundle_path.open("x", encoding="utf-8") as stream:
            json.dump(bundle, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return result


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--registration-id", help="Create separately named parity/bundle evidence, preserving earlier registrations")
    args = parser.parse_args()
    result = run(args.export_dir, args.inputs, args.registration_id)
    registered = result["status"] in {"passed", "passed_product_visible"}
    print(json.dumps({"status": result["status"], "bundle_created": registered}), flush=True)
    return 0 if registered else 1


if __name__ == "__main__":
    raise SystemExit(main())
