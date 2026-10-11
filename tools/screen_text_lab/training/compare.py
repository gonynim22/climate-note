"""Verify P/R/export/conversion evidence, then compare frozen tensors.

Manual reproduction check only. Optional HF inference is a separate diagnostic.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from .contracts import sha256


PROBE_WIDTHS = (8, 16, 32, 64, 96, 160, 320, 480, 640, 960, 1280, 1920, 2560, 3200)
EXPECTED_IDS = tuple(f"single-{i}" for i in range(6)) + ("mixed-batch6",) + tuple(f"width-{w}" for w in PROBE_WIDTHS)
ATOL, RTOL, PROBABILITY_ATOL = 1e-4, 1e-3, 1e-4
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def _json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream, parse_constant=_reject_constant)


def _local(directory, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError("Artifact path must be relative to its recorded directory")
    root = directory.resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path == root or not path.is_file():
        raise ValueError("Artifact escapes its recorded directory or is missing")
    return path


def _hash(value):
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def validate_manifest(manifest):
    """Reject partial/empty/changed recipes before a model session is created."""
    if (manifest.get("atol") != ATOL or manifest.get("rtol") != RTOL
            or manifest.get("require_equal_strings") is not True
            or manifest.get("text_parity_scope") != "synthetic_text_only"):
        raise ValueError("The fixed numerical/text parity recipe is missing or changed")
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) != len(EXPECTED_IDS):
        raise ValueError("Exactly six singles, batch6 and fourteen width probes are required")
    if [item.get("id") for item in items] != list(EXPECTED_IDS):
        raise ValueError("Fixed input IDs/order are incomplete, duplicated or changed")
    for item in items:
        identifier = item["id"]
        shape, widths, output_shape = item.get("shape"), item.get("widths"), item.get("output_shape")
        if (not isinstance(shape, list) or len(shape) != 4 or any(type(x) is not int or x < 1 for x in shape)
                or shape[1:3] != [3, 48]):
            raise ValueError(f"{identifier}: expected [N,3,48,W] shape")
        if (not isinstance(widths, list) or len(widths) != shape[0]
                or any(type(width) is not int or not 1 <= width <= shape[-1] for width in widths)):
            raise ValueError(f"{identifier}: every slot requires its original width")
        if (not isinstance(output_shape, list) or len(output_shape) != 3
                or any(type(x) is not int or x < 1 for x in output_shape) or output_shape[0] != shape[0]):
            raise ValueError(f"{identifier}: invalid CTC output shape")
        noise = identifier.startswith("width-")
        if bool(item.get("synthetic_noise", False)) != noise:
            raise ValueError("Text/noise-probe membership changed")
        if noise:
            width = int(identifier.removeprefix("width-"))
            if shape != [1, 3, 48, width] or widths != [width]:
                raise ValueError("Width probe geometry changed")
        elif identifier == "mixed-batch6":
            if shape[0] != 6 or widths != [entry["widths"][0] for entry in items[:6]] or shape[-1] != max(widths):
                raise ValueError("Mixed batch must retain all six source widths in order")
        elif shape[0] != 1 or widths != [shape[-1]]:
            raise ValueError("Single-text input must have one unpadded slot")
        if any(not _hash(item.get(key)) for key in ("sha256", "product_output_sha256")):
            raise ValueError("Input/product-output digest is missing")
    if any(not _hash(manifest.get(key)) for key in ("dictionary_sha256", "product_sha256")):
        raise ValueError("Dictionary/product digest is missing")
    return items


def validate_probabilities(array, *, batch, classes, label):
    import numpy as np
    if (array.dtype != np.float32 or array.ndim != 3 or array.shape[0] != batch
            or array.shape[1] < 1 or array.shape[2] != classes):
        raise ValueError(f"{label}: expected float32 [N,T,{classes}] probabilities")
    if (not np.isfinite(array).all() or array.min() < -PROBABILITY_ATOL
            or array.max() > 1 + PROBABILITY_ATOL
            or not np.allclose(array.sum(axis=-1), 1, atol=PROBABILITY_ATOL, rtol=0)):
        raise ValueError(f"{label}: output is nonfinite or not normalized probabilities")


def _conversion_chain(metadata_path, onnx_path, export_path, remember):
    conversion = _json(remember(metadata_path))
    if conversion.get("status") != "converted" or conversion.get("enable_onnx_checker") is not True:
        raise ValueError("Conversion did not complete with the ONNX checker")
    output = conversion.get("output", {})
    if not _hash(output.get("sha256")):
        raise ValueError("Conversion output digest is missing")
    if Path(output.get("path", "")).resolve() != onnx_path.resolve():
        raise ValueError("Conversion names another ONNX file")
    remember(onnx_path, output.get("sha256"))
    if output.get("size") != onnx_path.stat().st_size:
        raise ValueError("Converted ONNX size changed")
    exports = None
    if export_path is not None:
        reference = conversion.get("export_result", {})
        if not _hash(reference.get("sha256")):
            raise ValueError("Conversion export-result digest is missing")
        if Path(reference.get("path", "")).resolve() != export_path.resolve():
            raise ValueError("Conversion names another export result")
        exported = _json(remember(export_path, reference.get("sha256")))
        exports = exported.get("export", [])
    graph_files = []
    for key, expected_name in (("graph", "inference.json"), ("parameters", "inference.pdiparams")):
        item = conversion.get(key, {})
        if not isinstance(item.get("path"), str) or not item["path"] or not _hash(item.get("sha256")):
            raise ValueError("Conversion source path is missing")
        path = Path(item["path"]).resolve()
        remember(path, item.get("sha256"))
        if path.name != expected_name:
            raise ValueError("Unexpected Paddle graph/parameter filename")
        if exports is not None:
            matches = [entry for entry in exports if entry.get("file") == path.name]
            if len(matches) != 1 or matches[0].get("sha256") != item["sha256"]:
                raise ValueError("Converted graph/parameters differ from audited export")
            if path != _local(export_path.parent, matches[0]["file"]):
                raise ValueError("Conversion source is outside the recorded export")
        graph_files.append({"kind": key, "path": str(path), "sha256": item["sha256"]})
    return {"metadata": conversion, "metadata_sha256": sha256(metadata_path), "sources": graph_files}


def load_evidence(inputs, reproduced, onnx, *, export_result, conversion_result,
                  official_onnx=None, official_conversion_result=None):
    """Bind stored artifacts without creating a model session."""
    import numpy as np
    inputs, reproduced, onnx = Path(inputs), Path(reproduced), Path(onnx)
    export_result, conversion_result = Path(export_result), Path(conversion_result)
    if (official_onnx is None) != (official_conversion_result is None):
        raise ValueError("Official diagnostic requires ONNX and conversion result together")
    files = {}

    def remember(path, expected=None):
        path = Path(path).resolve()
        actual = sha256(path)
        if expected is not None and (not _hash(expected) or actual != expected):
            raise ValueError(f"Artifact hash mismatch: {path.name}")
        if str(path) in files and files[str(path)] != actual:
            raise ValueError("Artifact changed while reading evidence")
        files[str(path)] = actual
        return path

    manifest_path = remember(inputs / "manifest.json")
    manifest = _json(manifest_path)
    items = validate_manifest(manifest)
    dictionary = remember(Path(manifest["dictionary"]), manifest["dictionary_sha256"])
    remember(Path(manifest["product"]), manifest["product_sha256"])
    with open(dictionary, encoding="utf-8") as stream:
        characters = [line.rstrip("\r\n") for line in stream]
    if (not characters or any(len(char) != 1 or char.isspace() or char == "\0" for char in characters)
            or len(set(characters)) != len(characters)):
        raise ValueError("Dictionary requires unique single Unicode characters without implicit space")
    charset = characters + [" "]
    classes = len(charset) + 1
    forward_path = remember(reproduced / "result.json")
    forward = _json(forward_path)
    exported = _json(remember(export_result))
    if forward.get("status") not in {"forward_completed", "exported_untrained"} or forward.get("weight_audit") is not True:
        raise ValueError("Forward reproduction is incomplete or weight audit failed")
    if exported.get("status") != "exported_untrained" or exported.get("weight_audit") is not True:
        raise ValueError("Untrained export is incomplete or weight audit failed")
    for metadata, directory in ((forward, reproduced), (exported, export_result.parent)):
        if metadata.get("input_manifest_sha256") != files[str(manifest_path)]:
            raise ValueError("Reproduction/export belongs to another input manifest")
        if metadata.get("dictionary_sha256") != manifest["dictionary_sha256"]:
            raise ValueError("Reproduction/export dictionary differs from product")
        if not _hash(metadata.get("weight_audit_sha256")) or not _hash(metadata.get("architecture_sha256")):
            raise ValueError("Weight-audit/architecture digest is missing")
        audit = _json(remember(directory / "weight-audit.json", metadata["weight_audit_sha256"]))
        if (audit.get("ok") is not True or not audit.get("expected_count")
                or audit.get("expected_count") != audit.get("actual_count")
                or any(audit.get(key) != [] for key in ("missing", "extra", "shape_mismatches"))):
            raise ValueError("Weight audit is missing or incomplete")
        for key in ("checkpoint_sha256", "config_sha256"):
            if not _hash(metadata.get(key)) or audit.get(key) != metadata[key]:
                raise ValueError("Weight-audit checkpoint/config identity mismatch")
        remember(directory / "architecture.json", metadata["architecture_sha256"])
    for key in ("checkpoint_sha256", "config_sha256", "dictionary_sha256", "architecture_sha256"):
        if forward.get(key) != exported.get(key):
            raise ValueError(f"Forward/export provenance mismatch: {key}")
    exports = exported.get("export", [])
    if not isinstance(exports, list) or not exports or len({entry.get("file") for entry in exports}) != len(exports):
        raise ValueError("Export inventory is empty or duplicated")
    for entry in exports:
        if not _hash(entry.get("sha256")):
            raise ValueError("Export artifact digest is missing")
        path = remember(_local(export_result.parent, entry.get("file")), entry["sha256"])
        if path.stat().st_size != entry.get("size"):
            raise ValueError("Export size changed")
    conversion = _conversion_chain(conversion_result, onnx, export_result, remember)
    official = None
    if official_onnx is not None:
        official = _conversion_chain(Path(official_conversion_result), Path(official_onnx), None, remember)
    output_map = {}
    for item in forward.get("outputs", []):
        key = item.get("id"), item.get("device")
        if key in output_map:
            raise ValueError("Duplicate recorded forward output")
        output_map[key] = item
    required = {(identifier, device) for identifier in EXPECTED_IDS for device in ("cpu", "gpu:0")}
    if set(output_map) != required:
        raise ValueError("CPU/GPU forward output inventory is incomplete or unrelated")
    loaded = []
    for record in items:
        tensor = np.load(remember(_local(inputs, record["tensor"]), record["sha256"]), allow_pickle=False)
        if tensor.dtype != np.float32 or list(tensor.shape) != record["shape"] or not np.isfinite(tensor).all():
            raise ValueError("Frozen tensor shape/dtype/finite check failed")
        predictions = {"P": np.load(remember(_local(inputs, record["product_output"]), record["product_output_sha256"]), allow_pickle=False)}
        for device, role in (("cpu", "R_cpu"), ("gpu:0", "R_gpu")):
            item = output_map[(record["id"], device)]
            if item.get("input_sha256") != record["sha256"] or not _hash(item.get("sha256")):
                raise ValueError("Forward output belongs to another tensor or lacks digest")
            prediction = np.load(remember(_local(reproduced, item.get("path")), item["sha256"]), allow_pickle=False)
            if list(prediction.shape) != item.get("shape"):
                raise ValueError("Forward shape differs from recorded shape")
            predictions[role] = prediction
        for role, prediction in predictions.items():
            validate_probabilities(prediction, batch=tensor.shape[0], classes=classes, label=f"{record['id']} {role}")
            if list(prediction.shape) != record["output_shape"]:
                raise ValueError("Stored shape differs from frozen product output")
        loaded.append({"record": record, "tensor": tensor, "predictions": predictions})
    batch = loaded[6]["tensor"]
    for slot, entry in enumerate(loaded[:6]):
        width = entry["tensor"].shape[-1]
        if not np.array_equal(batch[slot, :, :, :width], entry["tensor"][0]) or np.any(batch[slot, :, :, width:] != 0):
            raise ValueError("Mixed batch pixels/padding differ from the frozen single tensors")
    if any(sha256(Path(path)) != value for path, value in files.items()):
        raise ValueError("Evidence changed while loading")
    return {"manifest": manifest, "charset": charset, "items": loaded, "files": files,
            "provenance": {"forward_result_sha256": files[str(forward_path)],
                           "export_result_sha256": files[str(export_result.resolve())],
                           "checkpoint_sha256": forward["checkpoint_sha256"], "config_sha256": forward["config_sha256"],
                           "architecture_sha256": forward["architecture_sha256"],
                           "dictionary_sha256": manifest["dictionary_sha256"], "input_manifest_sha256": files[str(manifest_path)],
                           "R_conversion": conversion, "HF_conversion": official}}


def validate_session(session, classes):
    inputs, outputs = session.get_inputs(), session.get_outputs()
    if (len(inputs) != 1 or inputs[0].name != "x" or inputs[0].type != "tensor(float)"
            or len(inputs[0].shape) != 4 or inputs[0].shape[1:3] != [3, 48]
            or isinstance(inputs[0].shape[0], int) or isinstance(inputs[0].shape[3], int)):
        raise ValueError("ONNX input must be dynamic float32 x [N,3,48,W]")
    if (len(outputs) != 1 or outputs[0].type != "tensor(float)" or len(outputs[0].shape) != 3
            or outputs[0].shape[-1] != classes):
        raise ValueError("ONNX output/dictionary contract differs")


def compare_predictions(record, tensor, predictions, charset, decoder):
    import numpy as np
    for name, prediction in predictions.items():
        validate_probabilities(prediction, batch=tensor.shape[0], classes=len(charset) + 1, label=name)
    pairs = [("P", name) for name in predictions if name != "P"] + [("R_cpu", "R_gpu"), ("R_cpu", "R_onnx")]
    items = []
    for first, second in pairs:
        expected, actual = predictions[first], predictions[second]
        if expected.shape != actual.shape:
            raise ValueError(f"Output shape mismatch for {record['id']} {first}/{second}")
        absolute = np.abs(expected - actual)
        strings = []
        for slot, width in enumerate(record["widths"]):
            steps = max(1, int(np.ceil(expected.shape[1] * width / tensor.shape[-1])))
            first_text, first_score = decoder(expected[slot, :steps], charset)
            second_text, second_score = decoder(actual[slot, :steps], charset)
            strings.append({"slot": slot, "steps": steps, "first_text": first_text, "second_text": second_text,
                            "equal": first_text == second_text, "first_score": float(first_score),
                            "second_score": float(second_score), "score_abs_diff": float(abs(first_score - second_score)),
                            "warning_080_equal": (first_score < .8) == (second_score < .8)})
        items.append({"id": record["id"], "pair": [first, second], "required": second != "HF_onnx",
                      "synthetic_noise": record.get("synthetic_noise", False), "shape": list(actual.shape), "finite": True,
                      "allclose": bool(np.allclose(expected, actual, atol=ATOL, rtol=RTOL)),
                      "max_abs_diff": float(absolute.max()), "mean_abs_diff": float(absolute.mean()),
                      "top1_step_differences": int((expected.argmax(-1) != actual.argmax(-1)).sum()),
                      "strings_equal": all(item["equal"] for item in strings),
                      "warning_080_equal": all(item["warning_080_equal"] for item in strings), "decoding": strings})
    return items


def compare(inputs, reproduced, onnx, official_onnx, output, *, export_result, conversion_result,
            official_conversion_result=None):
    import onnxruntime as ort
    from screen_text.engine import ctc_decode

    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    evidence = load_evidence(inputs, reproduced, onnx, export_result=export_result, conversion_result=conversion_result,
                             official_onnx=official_onnx, official_conversion_result=official_conversion_result)
    ort.disable_telemetry_events()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    sessions = {"R_onnx": ort.InferenceSession(str(onnx), options, providers=["CPUExecutionProvider"])}
    if official_onnx is not None:
        sessions["HF_onnx"] = ort.InferenceSession(str(official_onnx), options, providers=["CPUExecutionProvider"])
    for session in sessions.values():
        validate_session(session, len(evidence["charset"]) + 1)
    items = []
    for entry in evidence["items"]:
        record, tensor, predictions = entry["record"], entry["tensor"], entry["predictions"]
        for name, session in sessions.items():
            predictions[name] = session.run(None, {"x": tensor})[0]
        items.extend(compare_predictions(record, tensor, predictions, evidence["charset"], ctc_decode))
        print(f"Compared {record['id']}", flush=True)
    if any(sha256(Path(path)) != value for path, value in evidence["files"].items()):
        raise ValueError("Inputs/models/evidence changed during comparison")
    required = [item for item in items if item["required"]]
    text_items = [item for item in required if not item["synthetic_noise"]]
    tensor_pass = bool(required) and all(item["allclose"] for item in required)
    text_pass = bool(text_items) and all(item["strings_equal"] for item in text_items)
    warning_pass = bool(text_items) and all(item["warning_080_equal"] for item in text_items)
    result = {"status": "passed" if tensor_pass and text_pass and warning_pass else "differences_found",
              "tensor_allclose": tensor_pass, "text_strings_equal": text_pass, "warning_080_equal": warning_pass,
              "scope": "untrained reproduction; six fixed text crops, single/mixed batch6 and fourteen numerical width probes",
              "limitations": ["Not independent accuracy or full-screen product parity.",
                              "Noise strings are reported but excluded from the predeclared text gate.",
                              "HF conversion is a separate diagnostic, outside the P/R pass gate.",
                              "0.80 checks raw crop scores; table/numeric heuristics need product evaluation."],
              "atol": ATOL, "rtol": RTOL, "probability_atol": PROBABILITY_ATOL,
              "provenance": evidence["provenance"], "files": evidence["files"], "items": items}
    summaries = {}
    for item in items:
        key = " -> ".join(item["pair"])
        group = summaries.setdefault(key, {"required": item["required"], "items": 0, "allclose_failures": 0,
                                           "text_string_failures": 0, "noise_string_differences": 0,
                                           "warning_080_failures": 0, "max_abs_diff": 0.0})
        group["items"] += 1
        group["allclose_failures"] += not item["allclose"]
        group["text_string_failures"] += not item["synthetic_noise"] and not item["strings_equal"]
        group["noise_string_differences"] += item["synthetic_noise"] and not item["strings_equal"]
        group["warning_080_failures"] += not item["synthetic_noise"] and not item["warning_080_equal"]
        group["max_abs_diff"] = max(group["max_abs_diff"], item["max_abs_diff"])
    output.mkdir(parents=True, exist_ok=False)
    with open(output / "comparison.json", "x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    with open(output / "comparison-summary.json", "x", encoding="utf-8") as stream:
        json.dump(summaries, stream, indent=2, allow_nan=False)
    print(json.dumps({"status": result["status"], "pairs": summaries}, indent=2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--reproduced", type=Path, required=True)
    parser.add_argument("--onnx", type=Path, required=True)
    parser.add_argument("--export-result", type=Path, required=True)
    parser.add_argument("--conversion-result", type=Path, required=True)
    parser.add_argument("--official-onnx", type=Path)
    parser.add_argument("--official-conversion-result", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.inputs, args.reproduced, args.onnx, args.official_onnx, args.output,
                     export_result=args.export_result, conversion_result=args.conversion_result,
                     official_conversion_result=args.official_conversion_result)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
