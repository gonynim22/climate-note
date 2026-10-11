"""Tiny probability/byte fixtures for reproduction evidence; no model runs."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tools.screen_text_lab.training.compare import (
    ATOL, RTOL, EXPECTED_IDS, PROBE_WIDTHS, compare_predictions, load_evidence,
    validate_manifest, validate_probabilities, validate_session,
)
from tools.screen_text_lab.training.contracts import sha256


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def manifest_skeleton():
    singles = [8 + i * 8 for i in range(6)]
    items = []
    for identifier in EXPECTED_IDS:
        if identifier.startswith("single-"):
            widths = [singles[int(identifier[-1])]]
        elif identifier == "mixed-batch6":
            widths = singles
        else:
            widths = [int(identifier.split("-")[1])]
        items.append({"id": identifier, "widths": widths, "shape": [len(widths), 3, 48, max(widths)],
                      "output_shape": [len(widths), 2, 4], "sha256": "1" * 64,
                      "product_output_sha256": "2" * 64, "synthetic_noise": identifier.startswith("width-")})
    return {"items": items, "atol": ATOL, "rtol": RTOL, "require_equal_strings": True,
            "text_parity_scope": "synthetic_text_only", "dictionary_sha256": "3" * 64, "product_sha256": "4" * 64}


def fake_chain(tmp_path):
    inputs, forward, exported = [tmp_path / name for name in ("inputs", "forward", "exported")]
    for directory in (inputs, forward, exported):
        directory.mkdir()
    product = tmp_path / "fake-product.onnx"
    product.write_bytes(b"NOT A MODEL; HASH FIXTURE")
    dictionary = tmp_path / "dictionary.txt"
    dictionary.write_text("가\n나\n", encoding="utf-8")
    manifest = manifest_skeleton()
    manifest.update(product=str(product), product_sha256=sha256(product),
                    dictionary=str(dictionary), dictionary_sha256=sha256(dictionary))
    outputs = []
    for record in manifest["items"]:
        tensor = np.zeros(record["shape"], dtype=np.float32)
        tensor_path = inputs / (record["id"] + ".npy")
        np.save(tensor_path, tensor, allow_pickle=False)
        probabilities = np.zeros(record["output_shape"], dtype=np.float32)
        probabilities[..., 1] = 1
        product_path = inputs / (record["id"] + "-product.npy")
        np.save(product_path, probabilities, allow_pickle=False)
        record.update(tensor=tensor_path.name, sha256=sha256(tensor_path), product_output=product_path.name,
                      product_output_sha256=sha256(product_path))
        for device in ("cpu", "gpu:0"):
            path = forward / (record["id"] + "-" + device.split(":")[0] + ".npy")
            np.save(path, probabilities, allow_pickle=False)
            outputs.append({"id": record["id"], "device": device, "input_sha256": record["sha256"],
                            "path": path.name, "sha256": sha256(path), "shape": record["output_shape"]})
    write_json(inputs / "manifest.json", manifest)
    provenance = {"input_manifest_sha256": sha256(inputs / "manifest.json"), "dictionary_sha256": sha256(dictionary),
                  "checkpoint_sha256": "5" * 64, "config_sha256": "6" * 64,
                  "producer_sha256": "7" * 64, "weight_audit": True}
    audit = {"ok": True, "expected_count": 1, "actual_count": 1, "missing": [], "extra": [], "shape_mismatches": [],
             "checkpoint_sha256": provenance["checkpoint_sha256"], "config_sha256": provenance["config_sha256"]}
    for directory in (forward, exported):
        write_json(directory / "weight-audit.json", audit)
        write_json(directory / "architecture.json", {"fake": True})
    provenance["architecture_sha256"] = sha256(forward / "architecture.json")
    provenance["weight_audit_sha256"] = sha256(forward / "weight-audit.json")
    write_json(forward / "result.json", provenance | {"status": "forward_completed", "outputs": outputs})
    graph = exported / "inference.json"
    parameters = exported / "inference.pdiparams"
    graph.write_bytes(b"FAKE GRAPH")
    parameters.write_bytes(b"FAKE PARAMETERS")
    exports = [{"file": path.name, "size": path.stat().st_size, "sha256": sha256(path)} for path in (graph, parameters)]
    write_json(exported / "result.json", provenance | {"status": "exported_untrained", "outputs": [], "export": exports})
    onnx = tmp_path / "fake-reexported.onnx"
    onnx.write_bytes(b"FAKE CONVERSION")
    conversion_path = tmp_path / "conversion.json"
    write_json(conversion_path, {"status": "converted", "enable_onnx_checker": True,
                                "graph": {"path": str(graph), "sha256": sha256(graph)},
                                "parameters": {"path": str(parameters), "sha256": sha256(parameters)},
                                "export_result": {"path": str(exported / "result.json"), "sha256": sha256(exported / "result.json")},
                                "output": {"path": str(onnx), "sha256": sha256(onnx), "size": onnx.stat().st_size}})
    return {"inputs": inputs, "reproduced": forward, "onnx": onnx,
            "export_result": exported / "result.json", "conversion_result": conversion_path}


@pytest.mark.parametrize("problem", ["empty", "omitted", "duplicate", "order", "empty_widths", "width_count", "zero_width",
                                      "padding_width", "height", "batch", "out_batch", "out_zero", "noise_flag", "tolerance", "text_policy"])
def test_incomplete_or_altered_input_recipe_is_rejected(problem):
    manifest = manifest_skeleton()
    if problem == "empty": manifest["items"] = []
    elif problem == "omitted": manifest["items"].pop()
    elif problem == "duplicate": manifest["items"][-1] = deepcopy(manifest["items"][0])
    elif problem == "order": manifest["items"].reverse()
    elif problem == "empty_widths": manifest["items"][0]["widths"] = []
    elif problem == "width_count": manifest["items"][6]["widths"] = [48]
    elif problem == "zero_width": manifest["items"][0]["widths"] = [0]
    elif problem == "padding_width": manifest["items"][0]["widths"] = [100]
    elif problem == "height": manifest["items"][0]["shape"][2] = 32
    elif problem == "batch": manifest["items"][6]["shape"][0] = 1
    elif problem == "out_batch": manifest["items"][0]["output_shape"][0] = 2
    elif problem == "out_zero": manifest["items"][0]["output_shape"][1] = 0
    elif problem == "noise_flag": manifest["items"][0]["synthetic_noise"] = True
    elif problem == "tolerance": manifest["atol"] = .1
    elif problem == "text_policy": del manifest["text_parity_scope"]
    with pytest.raises(ValueError): validate_manifest(manifest)


def test_complete_fixed_input_recipe_has_all_twenty_one_trials():
    assert len(validate_manifest(manifest_skeleton())) == 21


def test_complete_fake_evidence_chain_loads_without_runtime(tmp_path):
    paths = fake_chain(tmp_path)
    result = load_evidence(**paths)
    assert len(result["items"]) == 21
    assert result["charset"] == ["가", "나", " "]
    assert result["provenance"]["checkpoint_sha256"] == "5" * 64
    assert result["provenance"]["HF_conversion"] is None


@pytest.mark.parametrize("problem", ["forward_status", "manifest_chain", "output_missing", "output_duplicate", "stale_output",
                                      "input_identity", "output_shape", "audit_hash", "architecture_hash", "export_status",
                                      "checkpoint_chain", "conversion_export", "conversion_hash", "conversion_model", "missing_conversion_hash",
                                      "dictionary", "product"])
def test_wrong_stale_or_modified_evidence_is_rejected(tmp_path, problem):
    paths = fake_chain(tmp_path)
    forward_path = paths["reproduced"] / "result.json"
    forward = json.loads(forward_path.read_text(encoding="utf-8"))
    exported = json.loads(paths["export_result"].read_text(encoding="utf-8"))
    conversion = json.loads(paths["conversion_result"].read_text(encoding="utf-8"))
    if problem == "forward_status": forward["status"] = "running"
    elif problem == "manifest_chain": forward["input_manifest_sha256"] = "0" * 64
    elif problem == "output_missing": forward["outputs"].pop()
    elif problem == "output_duplicate": forward["outputs"].append(forward["outputs"][0])
    elif problem == "stale_output": (paths["reproduced"] / forward["outputs"][0]["path"]).write_bytes(b"other-run")
    elif problem == "input_identity": forward["outputs"][0]["input_sha256"] = "0" * 64
    elif problem == "output_shape": forward["outputs"][0]["shape"] = [1, 3, 4]
    elif problem == "audit_hash": forward["weight_audit_sha256"] = "0" * 64
    elif problem == "architecture_hash": forward["architecture_sha256"] = "0" * 64
    elif problem == "export_status": exported["status"] = "running"
    elif problem == "checkpoint_chain": exported["checkpoint_sha256"] = "0" * 64
    elif problem == "conversion_export": conversion["export_result"]["sha256"] = "0" * 64
    elif problem == "conversion_hash": conversion["graph"]["sha256"] = "0" * 64
    elif problem == "conversion_model": conversion["output"]["path"] = str(tmp_path / "other.onnx")
    elif problem == "missing_conversion_hash": del conversion["output"]["sha256"]
    elif problem == "dictionary": (tmp_path / "dictionary.txt").write_text("나\n가\n", encoding="utf-8")
    elif problem == "product": (tmp_path / "fake-product.onnx").write_bytes(b"changed")
    write_json(forward_path, forward)
    write_json(paths["export_result"], exported)
    write_json(paths["conversion_result"], conversion)
    with pytest.raises(ValueError): load_evidence(**paths)


@pytest.mark.parametrize("problem", ["double", "nan", "inf", "negative", "over_one", "sum", "class_axis", "batch_axis"])
def test_probability_contract_rejects_logits_dtype_and_nonfinite_values(problem):
    values = np.array([[[.2, .8, 0, 0]]], dtype=np.float32)
    if problem == "double": values = values.astype(np.float64)
    elif problem == "nan": values[0, 0, 0] = np.nan
    elif problem == "inf": values[0, 0, 0] = np.inf
    elif problem == "negative": values[0, 0] = [-.1, 1.1, 0, 0]
    elif problem == "over_one": values[0, 0, 1] = 1.5
    elif problem == "sum": values *= 2
    elif problem == "class_axis": values = values[..., :3]
    elif problem == "batch_axis": values = np.repeat(values, 2, axis=0)
    with pytest.raises(ValueError): validate_probabilities(values, batch=1, classes=4, label="fake")


def decode_for_test(values, charset):
    return "".join(str(int(value)) for value in values.argmax(-1)), float(values.max(-1).mean())


def test_numerical_allclose_cannot_hide_warning_threshold_crossing():
    old = np.array([[[.19995, .80005, 0, 0]]], dtype=np.float32)
    new = np.array([[[.20005, .79995, 0, 0]]], dtype=np.float32)
    predictions = {"P": old, "R_cpu": old, "R_gpu": old, "R_onnx": new}
    result = compare_predictions({"id": "single-0", "widths": [8]}, np.zeros((1, 3, 48, 8)), predictions,
                                 ["가", "나", " "], decode_for_test)
    converted = next(row for row in result if row["pair"] == ["P", "R_onnx"])
    assert converted["allclose"] and converted["strings_equal"]
    assert not converted["warning_080_equal"]


def test_every_mixed_batch_slot_uses_product_width_cutoff_and_reports_strings():
    prediction = np.zeros((2, 4, 4), dtype=np.float32)
    prediction[..., 1] = 1
    result = compare_predictions({"id": "mixed-test", "widths": [8, 16]}, np.zeros((2, 3, 48, 16)),
                                 {key: prediction for key in ("P", "R_cpu", "R_gpu", "R_onnx")},
                                 ["가", "나", " "], decode_for_test)
    assert [row["steps"] for row in result[0]["decoding"]] == [2, 4]
    assert [row["first_text"] for row in result[0]["decoding"]] == ["11", "1111"]


def test_optional_hf_differences_are_explicitly_not_required_parity():
    old = np.array([[[0, 1, 0, 0]]], dtype=np.float32)
    hf = np.array([[[0, 0, 1, 0]]], dtype=np.float32)
    predictions = {key: old for key in ("P", "R_cpu", "R_gpu", "R_onnx")}
    predictions["HF_onnx"] = hf
    result = compare_predictions({"id": "single-0", "widths": [8]}, np.zeros((1, 3, 48, 8)), predictions,
                                 ["가", "나", " "], decode_for_test)
    diagnostic = next(row for row in result if row["pair"] == ["P", "HF_onnx"])
    assert not diagnostic["required"] and not diagnostic["strings_equal"]
    assert all(row["strings_equal"] for row in result if row["required"])


def test_session_contract_requires_dynamic_float32_input_and_character_axis():
    class Session:
        def __init__(self):
            self.input = SimpleNamespace(name="x", type="tensor(float)", shape=["N", 3, 48, "W"])
            self.output = SimpleNamespace(type="tensor(float)", shape=["N", "T", 4])
        def get_inputs(self): return [self.input]
        def get_outputs(self): return [self.output]
    session = Session()
    validate_session(session, 4)
    session.input.shape[0] = 1
    with pytest.raises(ValueError): validate_session(session, 4)
    session.input.shape[0] = "N"
    session.output.type = "tensor(double)"
    with pytest.raises(ValueError): validate_session(session, 4)


def test_hf_pair_and_frozen_tensor_content_are_required(tmp_path):
    paths = fake_chain(tmp_path)
    with pytest.raises(ValueError, match="together"):
        load_evidence(**paths, official_onnx=paths["onnx"])
    path = paths["inputs"] / "mixed-batch6.npy"
    array = np.load(path, allow_pickle=False)
    array[0, 0, 0, 0] = 1
    np.save(path, array, allow_pickle=False)
    with pytest.raises(ValueError, match="hash mismatch"):
        load_evidence(**paths)
