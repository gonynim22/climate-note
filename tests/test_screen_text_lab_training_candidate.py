"""Candidate export gates use tiny arrays and inert byte files, never models."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from tools.screen_text_lab.training import bundle_candidate as tool
from tools.screen_text_lab.training.compare import ATOL, RTOL, EXPECTED_IDS
from tools.screen_text_lab.training.contracts import class_mapping, class_tokens, sha256


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def chain(tmp_path, role="F"):
    inputs, exported, trained = [tmp_path / name for name in ("inputs", "export", "origin")]
    for path in (inputs, exported, trained):
        path.mkdir()
    dictionary = trained / "dict.txt"
    dictionary.write_text("가\n나\n℃\n", encoding="utf-8")
    (exported / "dict.txt").write_bytes(dictionary.read_bytes())
    checkpoint = trained / "checkpoint.pdparams"
    checkpoint.write_bytes(b"FAKE CHECKPOINT")
    recipe = {"loader": {"dictionary_sha256": sha256(dictionary)}, "source_config_sha256": "4" * 64,
              "source_revision": "a" * 40}
    write(trained / "recipe.json", recipe)
    origin = {"status": "completed" if role == "F" else "initialized", "completed_steps": 3,
              "provenance_unchanged": True, "recipe_sha256": sha256(trained / "recipe.json"),
              "checkpoint": {"path": str(checkpoint), "sha256": sha256(checkpoint)},
              "dictionary": {"path": str(dictionary), "sha256": sha256(dictionary)}}
    write(trained / "result.json", origin)
    single_widths = [8 + 8 * index for index in range(6)]
    items, outputs = [], []
    for identifier in EXPECTED_IDS:
        widths = (single_widths if identifier == "mixed-batch6" else [single_widths[int(identifier[-1])]]
                  if identifier.startswith("single-") else [int(identifier.split("-")[1])])
        shape = [len(widths), 3, 48, max(widths)]
        tensor = inputs / f"{identifier}.npy"
        np.save(tensor, np.zeros(shape, dtype=np.float32), allow_pickle=False)
        prediction = np.zeros((len(widths), 2, 5), dtype=np.float32)
        prediction[..., 1] = 1
        output = exported / f"{identifier}-cpu.npy"
        np.save(output, prediction, allow_pickle=False)
        items.append({"id": identifier, "tensor": tensor.name, "sha256": sha256(tensor), "shape": shape,
                      "widths": widths, "output_shape": [len(widths), 2, 4], "product_output_sha256": "2" * 64,
                      "synthetic_noise": identifier.startswith("width-")})
        outputs.append({"id": identifier, "path": output.name, "sha256": sha256(output), "input_sha256": sha256(tensor),
                        "shape": list(prediction.shape)})
    manifest = {"items": items, "atol": ATOL, "rtol": RTOL, "require_equal_strings": True,
                "text_parity_scope": "synthetic_text_only", "dictionary_sha256": "2" * 64, "product_sha256": "3" * 64}
    write(inputs / "manifest.json", manifest)
    write(exported / "architecture.json", {"fake": True})
    write(exported / "weight-audit.json", {"ok": True, "expected_count": 1, "actual_count": 1,
                                          "missing": [], "extra": [], "shape_mismatches": []})
    graph, parameters, model = [exported / name for name in ("inference.json", "inference.pdiparams", "rec.onnx")]
    for path in (graph, parameters, model):
        path.write_bytes(b"FAKE " + path.name.encode())
    result = {"status": "exported_trained" if role == "F" else "exported_initialized", "id": "fixture", "role": role,
              "provenance_unchanged": True, "checkpoint_sha256": sha256(checkpoint), "dictionary_sha256": sha256(dictionary),
              "config_sha256": "4" * 64, "architecture_sha256": sha256(exported / "architecture.json"),
              "weight_audit_sha256": sha256(exported / "weight-audit.json"), "producer_sha256": "5" * 64,
              "input_manifest_sha256": sha256(inputs / "manifest.json"),
              "origin_result": {"path": str(trained / "result.json"), "sha256": sha256(trained / "result.json")},
              "source": {"revision": "a" * 40, "tree_sha256": "6" * 64, "archive_sha256": "7" * 64,
                         "bootstrap_sha256": "8" * 64, "verified_python_yaml_files": 1}, "outputs": outputs,
              "export": [{"file": path.name, "size": path.stat().st_size, "sha256": sha256(path)} for path in (graph, parameters)]}
    if role == "F":
        provenance = {"source": result["source"], "files": {str(checkpoint): sha256(checkpoint)}}
        for phase in ("before", "after"):
            path = trained / f"provenance-{phase}.json"
            write(path, provenance)
            origin[f"provenance_{phase}_sha256"] = sha256(path)
        write(trained / "result.json", origin)
        result["origin_result"]["sha256"] = sha256(trained / "result.json")
    if role == "R":
        mappings = {head: class_mapping(["가", "나"], ["가", "나", "℃"], head) for head in ("ctc", "nrtr")}
        mappings["nrtr"].append(len(class_tokens(["가", "나", "℃"], "nrtr")))
        proof = {"status": "expanded_parameters_verified", "old_dictionary_count": 2, "new_dictionary_count": 3,
                 "all_old_slices_bitwise_equal": True, "all_new_class_slices_initialization_preserved": True,
                 "inputs_preserved": True, "class_id_mapping": mappings, "actual_model_logits": "not_run",
                 "masked_old_ctc_logits": {"passed": True, "atol": ATOL, "rtol": RTOL,
                     "items": [{"id": row["id"], "input_sha256": row["sha256"], "shape": row["output_shape"], "allclose": True} for row in items]}}
        (trained / "architecture.json").write_bytes((exported / "architecture.json").read_bytes())
        write(trained / "mapping.json", mappings)
        write(trained / "proof.json", proof)
        origin.update(training_steps=0, source=result["source"], input_manifest_sha256=result["input_manifest_sha256"])
        for key in ("architecture", "mapping", "proof"):
            origin[key] = {"path": str(trained / f"{key}.json"), "sha256": sha256(trained / f"{key}.json")}
        write(trained / "result.json", origin)
        result["origin_result"]["sha256"] = sha256(trained / "result.json")
    write(exported / "result.json", result)
    conversion = {"status": "converted", "enable_onnx_checker": True,
                  "graph": {"path": str(graph), "sha256": sha256(graph)},
                  "parameters": {"path": str(parameters), "sha256": sha256(parameters)},
                  "export_result": {"path": str(exported / "result.json"), "sha256": sha256(exported / "result.json")},
                  "output": {"path": str(model), "size": model.stat().st_size, "sha256": sha256(model)}}
    write(exported / "rec.conversion.json", conversion)
    return exported, inputs


def rewrite_export(exported, result):
    write(exported / "result.json", result)
    path = exported / "rec.conversion.json"
    conversion = json.loads(path.read_text(encoding="utf-8"))
    conversion["export_result"]["sha256"] = sha256(exported / "result.json")
    write(path, conversion)


@pytest.mark.parametrize("role", ["F", "R"])
def test_origin_chain_all_twenty_one_and_expanded_classes_are_supported(tmp_path, role):
    result = tool.load_candidate_evidence(*chain(tmp_path, role))
    assert len(result["items"]) == 21
    assert result["charset"] == ["가", "나", "℃", " "]
    assert result["export"]["role"] == role


def test_padding_only_difference_is_not_reported_as_full_parity():
    from screen_text.engine import ctc_decode
    tensor = np.zeros((2, 3, 48, 32), np.float32)
    expected = np.zeros((2, 4, 3), np.float32)
    expected[..., 0] = 1
    actual = expected.copy()
    actual[0, 3] = [0, 1, 0]  # First crop uses only two steps.
    result = tool.compare_output({"id": "mixed", "widths": [16, 32]}, tensor, expected, actual, ["가", " "], ctc_decode)
    assert result["allclose"] is False
    assert result["product_visible_allclose"] is True
    assert result["padding_different_elements"] == 2
    assert result["strings_equal"] and result["warning_080_equal"]
    actual[0, 0] = [0, 1, 0]
    result = tool.compare_output({"id": "mixed", "widths": [16, 32]}, tensor, expected, actual, ["가", " "], ctc_decode)
    assert result["product_visible_allclose"] is False


@pytest.mark.parametrize("mode", ["trained_weights_original_bn", "original_weights_trained_bn"])
@pytest.mark.parametrize("problem", [None, "steps", "non_stat_donor", "initialization"])
def test_bn_combination_is_separate_and_bound_to_actual_parent(tmp_path, mode, problem):
    exported, inputs = chain(tmp_path)
    result = json.loads((exported / "result.json").read_text(encoding="utf-8"))
    parent_path = Path(result["origin_result"]["path"])
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    original = tmp_path / "original.pdparams"
    original.write_bytes(b"ORIGINAL")
    recipe_path = parent_path.parent / "recipe.json"
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    recipe["checkpoint_sha256"] = sha256(original)
    write(recipe_path, recipe)
    parent["recipe_sha256"] = sha256(recipe_path)
    write(parent_path, parent)
    ref = lambda path: {"path": str(path), "sha256": sha256(path)}
    directory = tmp_path / "diagnostic"
    directory.mkdir()
    checkpoint = directory / "checkpoint.pdparams"
    checkpoint.write_bytes(b"COMBINED")
    donor = "original" if mode == "trained_weights_original_bn" else "trained"
    base = "trained" if donor == "original" else "original"
    proofs = {key: {"source": donor if key.startswith("bn.") else base, "sha256": "a" * 64}
              for key in ["bn._mean", "bn._variance", "weight"]}
    diagnostic = {"mode": mode, "additional_training_steps": 0, "source": result["source"],
                  "parent_training_result": ref(parent_path), "original_checkpoint": ref(original),
                  "trained_checkpoint": parent["checkpoint"], "dictionary": parent["dictionary"],
                  "all_other_tensors_bitwise_equal": True, "all_requested_stats_bitwise_equal": True,
                  "stat_keys": ["bn._mean", "bn._variance"], "tensor_proofs": proofs}
    if problem == "non_stat_donor":
        diagnostic["tensor_proofs"]["weight"]["source"] = donor
    if problem == "initialization":
        original.write_bytes(b"ANOTHER INITIAL MODEL")
        diagnostic["original_checkpoint"] = ref(original)
    write(directory / "diagnostic-recipe.json", diagnostic)
    origin = {"status": "diagnostic_completed", "provenance_unchanged": True, "mode": mode,
              "additional_training_steps": 1 if problem == "steps" else 0,
              "checkpoint": ref(checkpoint), "dictionary": parent["dictionary"],
              "parent_training_result": ref(parent_path), "diagnostic_recipe": ref(directory / "diagnostic-recipe.json")}
    write(directory / "result.json", origin)
    result.update(status="exported_diagnostic", origin_result=ref(directory / "result.json"),
                  checkpoint_sha256=sha256(checkpoint))
    rewrite_export(exported, result)
    if problem:
        with pytest.raises(ValueError):
            tool.load_candidate_evidence(exported, inputs)
    else:
        scope = tool.load_candidate_evidence(exported, inputs)["origin_scope"]
        assert scope["kind"] == "bn_stat_combination_diagnostic"
        assert scope["additional_training_steps"] == 0 and scope["parent_training_steps"] == 3


@pytest.mark.parametrize("problem", ["status", "role", "unchanged", "origin_hash", "checkpoint", "recipe", "source",
                                      "empty", "omitted", "duplicate", "reordered", "input_hash", "output_hash",
                                      "shape", "dict", "architecture", "weight_audit", "export_empty", "converted_model",
                                      "conversion_export", "input_missing", "manifest_empty", "manifest_order", "output_alias", "input_alias"])
def test_incomplete_or_mixed_candidate_evidence_never_registers(tmp_path, problem):
    exported, inputs = chain(tmp_path)
    result = json.loads((exported / "result.json").read_text(encoding="utf-8"))
    if problem == "status": result["status"] = "running"
    elif problem == "role": result["role"] = "P"
    elif problem == "unchanged": result["provenance_unchanged"] = False
    elif problem == "origin_hash": result["origin_result"]["sha256"] = "0" * 64
    elif problem == "checkpoint": (tmp_path / "origin/checkpoint.pdparams").write_bytes(b"changed")
    elif problem == "recipe": (tmp_path / "origin/recipe.json").write_text("{}")
    elif problem == "source": result["source"]["tree_sha256"] = "missing"
    elif problem == "empty": result["outputs"] = []
    elif problem == "omitted": result["outputs"].pop()
    elif problem == "duplicate": result["outputs"][-1] = deepcopy(result["outputs"][0])
    elif problem == "reordered": result["outputs"].reverse()
    elif problem == "input_hash": result["outputs"][0]["input_sha256"] = "0" * 64
    elif problem == "output_hash": result["outputs"][0]["sha256"] = "0" * 64
    elif problem == "shape": result["outputs"][0]["shape"] = [1, 3, 5]
    elif problem == "output_alias": result["outputs"][1]["path"] = result["outputs"][0]["path"]
    elif problem == "dict": (exported / "dict.txt").write_text("나\n가\n℃\n", encoding="utf-8")
    elif problem == "architecture": (exported / "architecture.json").write_text("{}")
    elif problem == "weight_audit": result["weight_audit_sha256"] = "0" * 64
    elif problem == "export_empty": result["export"] = []
    elif problem == "converted_model": (exported / "rec.onnx").write_bytes(b"changed")
    elif problem == "input_missing": (inputs / "single-0.npy").unlink()
    elif problem in {"manifest_empty", "manifest_order", "input_alias"}:
        path = inputs / "manifest.json"
        manifest = json.loads(path.read_text())
        if problem == "manifest_empty": manifest["items"] = []
        elif problem == "manifest_order": manifest["items"].reverse()
        else: manifest["items"][1]["tensor"] = manifest["items"][0]["tensor"]
        write(path, manifest)
        result["input_manifest_sha256"] = sha256(path)
    rewrite_export(exported, result)
    if problem == "conversion_export":
        path = exported / "rec.conversion.json"
        conversion = json.loads(path.read_text())
        conversion["export_result"]["sha256"] = "0" * 64
        write(path, conversion)
    with pytest.raises((ValueError, OSError)):
        tool.load_candidate_evidence(exported, inputs)
    assert not (exported / "bundle.json").exists()


def decoder(values, charset):
    from screen_text.engine import ctc_decode
    return ctc_decode(values, charset)


def test_warning_threshold_change_fails_despite_tensor_allclose():
    left = np.array([[[.20001, .79999, 0]]], dtype=np.float32)
    right = np.array([[[.19999, .80001, 0]]], dtype=np.float32)
    result = tool.compare_output({"id": "width-8", "widths": [8], "synthetic_noise": True},
                                 np.zeros((1, 3, 48, 8), np.float32), left, right, ["가", " "], decoder)
    assert result["allclose"] and result["strings_equal"]
    assert not result["warning_080_equal"]


def test_every_slot_uses_its_own_width_trim():
    left = np.zeros((2, 4, 4), dtype=np.float32)
    left[..., 1] = 1
    right = left.copy()
    right[0, 1:, 1], right[0, 1:, 2] = 0, 1
    result = tool.compare_output({"id": "mixed-batch6", "widths": [8, 32]},
                                 np.zeros((2, 3, 48, 32), np.float32), left, right, ["가", "나", " "], decoder)
    assert result["strings_equal"]
    assert [row["steps"] for row in result["decoding"]] == [1, 4]
    assert not result["allclose"]


def fake_runtime(monkeypatch, exported, evidence, change=False):
    predictions = iter([item["prediction"].copy() for item in evidence["items"]])
    def run(*_):
        value = next(predictions)
        if change:
            value[..., 1], value[..., 2] = 0, 1
        return [value]
    session = SimpleNamespace(run=run,
        get_inputs=lambda: [SimpleNamespace(name="x", type="tensor(float)", shape=["N", 3, 48, "W"])],
        get_outputs=lambda: [SimpleNamespace(type="tensor(float)", shape=["N", "T", 5])])
    fake = SimpleNamespace(disable_telemetry_events=lambda: None, SessionOptions=SimpleNamespace,
                           InferenceSession=lambda *args, **kwargs: session)
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)


@pytest.mark.parametrize("change", [False, True])
def test_bundle_created_only_for_complete_identical_export(tmp_path, monkeypatch, change):
    exported, inputs = chain(tmp_path)
    evidence = tool.load_candidate_evidence(exported, inputs)
    fake_runtime(monkeypatch, exported, evidence, change)
    result = tool.run(exported, inputs)
    assert (result["status"] == "passed") is not change
    assert (exported / "bundle.json").exists() is not change
    if not change:
        bundle = json.loads((exported / "bundle.json").read_text(encoding="utf-8"))
        assert bundle["model_sha256"] == sha256(exported / "rec.onnx")
        assert bundle["provenance"]["parity"]["sha256"] == sha256(exported / "candidate-parity.json")
        audit = tool.verify_bundle_provenance(exported / "bundle.json", bundle,
                    {"model": exported / "rec.onnx", "dictionary": exported / "dict.txt"})
        assert audit["kind"] == "candidate_export"
    with pytest.raises(FileExistsError):
        tool.run(exported, inputs)


@pytest.mark.parametrize("problem", ["source", "mapping", "not_measured", "empty_logits", "logit_input", "logit_shape", "failed_logits"])
def test_expansion_origin_needs_actual_masked_logit_evidence(tmp_path, problem):
    exported, inputs = chain(tmp_path, "R")
    origin_path = tmp_path / "origin/result.json"
    origin = json.loads(origin_path.read_text())
    proof_path = tmp_path / "origin/proof.json"
    proof = json.loads(proof_path.read_text())
    if problem == "source": origin["source"] = {}
    elif problem == "mapping": proof["class_id_mapping"]["ctc"][1] = 3
    elif problem == "not_measured": del proof["masked_old_ctc_logits"]
    elif problem == "empty_logits": proof["masked_old_ctc_logits"]["items"] = []
    elif problem == "logit_input": proof["masked_old_ctc_logits"]["items"][0]["input_sha256"] = "0" * 64
    elif problem == "logit_shape": proof["masked_old_ctc_logits"]["items"][0]["shape"] = [1, 3, 4]
    elif problem == "failed_logits": proof["masked_old_ctc_logits"]["items"][0]["allclose"] = False
    write(proof_path, proof)
    origin["proof"]["sha256"] = sha256(proof_path)
    write(origin_path, origin)
    result = json.loads((exported / "result.json").read_text())
    result["origin_result"]["sha256"] = sha256(origin_path)
    rewrite_export(exported, result)
    with pytest.raises(ValueError):
        tool.load_candidate_evidence(exported, inputs)


def reproduction_bundle(tmp_path):
    exported, _ = chain(tmp_path)
    result = json.loads((exported / "result.json").read_text())
    result["status"] = "exported_untrained"
    rewrite_export(exported, result)
    snapshot = {str(path.resolve()): sha256(path) for path in exported.iterdir() if path.is_file()}
    required = [{"id": identifier, "pair": list(pair), "required": True, "allclose": True,
                 "synthetic_noise": identifier.startswith("width-"), "strings_equal": True, "warning_080_equal": True}
                for identifier in EXPECTED_IDS for pair in (("P", "R_cpu"), ("P", "R_gpu"), ("P", "R_onnx"),
                                                            ("R_cpu", "R_gpu"), ("R_cpu", "R_onnx"))]
    report = {"status": "passed", "atol": ATOL, "rtol": RTOL, "tensor_allclose": True,
              "text_strings_equal": True, "warning_080_equal": True, "files": snapshot, "items": required,
              "provenance": {"export_result_sha256": sha256(exported / "result.json"),
                             "dictionary_sha256": result["dictionary_sha256"],
                             "R_conversion": {"metadata_sha256": sha256(exported / "rec.conversion.json")}}}
    report_path = tmp_path / "reproduction.json"
    write(report_path, report)
    bundle = {"role": "R", "id": "original-R", "model_sha256": sha256(exported / "rec.onnx"),
              "dictionary_sha256": sha256(exported / "dict.txt"), "provenance": {
                  "reproduction_report": str(report_path), "reproduction_report_sha256": sha256(report_path),
                  "training_steps": 0, "export_result": "result.json", "conversion_result": "rec.conversion.json"}}
    return exported, bundle, report_path


def test_earlier_untrained_R_report_can_authorize_only_R(tmp_path):
    exported, bundle, _ = reproduction_bundle(tmp_path)
    files = {"model": exported / "rec.onnx", "dictionary": exported / "dict.txt"}
    assert tool.verify_bundle_provenance(exported / "bundle.json", bundle, files)["kind"] == "untrained_reproduction"
    bundle["role"] = "F"
    with pytest.raises(ValueError):
        tool.verify_bundle_provenance(exported / "bundle.json", bundle, files)


@pytest.mark.parametrize("problem", ["declared_only", "partial", "role", "id", "model", "dict", "origin", "snapshot", "report_hash"])
def test_registered_candidate_provenance_must_remain_complete(tmp_path, monkeypatch, problem):
    exported, inputs = chain(tmp_path)
    evidence = tool.load_candidate_evidence(exported, inputs)
    fake_runtime(monkeypatch, exported, evidence)
    tool.run(exported, inputs)
    bundle_path = exported / "bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    report_path = exported / "candidate-parity.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if problem == "declared_only": bundle["provenance"] = {"run": "trust-me"}
    elif problem == "partial": report["items"].pop()
    elif problem == "role": bundle["role"] = "R"
    elif problem == "id": bundle["id"] = "another"
    elif problem == "model": (exported / "rec.onnx").write_bytes(b"changed")
    elif problem == "dict": (exported / "dict.txt").write_text("나\n가\n℃\n", encoding="utf-8")
    elif problem == "origin": bundle["provenance"]["origin_result"]["sha256"] = "0" * 64
    elif problem == "snapshot": del report["files"][str((exported / "result.json").resolve())]
    write(report_path, report)
    if problem != "declared_only":
        bundle["provenance"]["parity"]["sha256"] = "0" * 64 if problem == "report_hash" else sha256(report_path)
    with pytest.raises(ValueError):
        tool.verify_bundle_provenance(bundle_path, bundle, {"model": exported / "rec.onnx", "dictionary": exported / "dict.txt"})
