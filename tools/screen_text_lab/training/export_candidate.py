"""Export an explicitly identified development checkpoint using the official inference path."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import traceback

from .contracts import sha256, shape_audit
from .provenance import file_snapshot, source_evidence


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run(args):
    import numpy as np
    import paddle
    import yaml

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    origin = json.loads(args.origin_result.read_text(encoding="utf-8"))
    diagnostic = origin["status"] == "diagnostic_completed"
    training_origin_path = args.origin_result
    training_origin = origin
    if diagnostic:
        if args.role != "F" or origin.get("additional_training_steps") != 0:
            raise ValueError("BN diagnostic must be an F combination with zero additional training")
        parent = origin["parent_training_result"]
        training_origin_path = Path(parent["path"])
        if sha256(training_origin_path) != parent["sha256"]:
            raise ValueError("Diagnostic parent training result changed")
        training_origin = json.loads(training_origin_path.read_text(encoding="utf-8"))
        diagnostic_record = origin["diagnostic_recipe"]
        if sha256(Path(diagnostic_record["path"])) != diagnostic_record["sha256"]:
            raise ValueError("Diagnostic recipe changed")
        diagnostic_recipe = json.loads(Path(diagnostic_record["path"]).read_text(encoding="utf-8"))
        if origin["dictionary"]["sha256"] != sha256(args.dictionary):
            raise ValueError("Diagnostic dictionary changed")
        if diagnostic_recipe["mode"] != origin["mode"] or diagnostic_recipe["additional_training_steps"] != 0:
            raise ValueError("Diagnostic mode or additional steps changed")
    if args.role == "F" and (training_origin["status"] != "completed" or training_origin.get("completed_steps", 0) <= 0
                             or not origin.get("provenance_unchanged") or not training_origin.get("provenance_unchanged")):
        raise ValueError("F export needs a completed, provenance-stable training result")
    if args.role == "R" and origin["status"] != "initialized":
        raise ValueError("R_B export needs an explicitly initialized expansion result")
    if origin["checkpoint"]["sha256"] != sha256(args.checkpoint):
        raise ValueError("Checkpoint differs from its recorded origin")
    if Path(origin["checkpoint"]["path"]).resolve() != args.checkpoint.resolve():
        raise ValueError("Origin names another checkpoint")
    if args.role == "F":
        recipe_path = training_origin_path.parent / "recipe.json"
        if sha256(recipe_path) != training_origin["recipe_sha256"]:
            raise ValueError("Training recipe changed")
        recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
        if recipe["loader"]["dictionary_sha256"] != sha256(args.dictionary):
            raise ValueError("Training dictionary changed")
    elif origin["dictionary"]["sha256"] != sha256(args.dictionary):
        raise ValueError("Expansion dictionary changed")
    if args.role == "R":
        for key in ("architecture", "mapping", "proof"):
            record = origin[key]
            if sha256(Path(record["path"])) != record["sha256"]:
                raise ValueError(f"Expansion {key} changed")
    config_path = args.source / "configs/rec/PP-OCRv5/multi_language/korean_PP-OCRv5_mobile_rec.yml"
    inputs = json.loads((args.inputs / "manifest.json").read_text(encoding="utf-8"))
    files = [args.checkpoint, args.dictionary, args.origin_result, config_path,
             args.inputs / "manifest.json", Path(__file__)]
    if diagnostic:
        files.extend([training_origin_path, recipe_path, Path(diagnostic_record["path"])])
    before = file_snapshot(files)
    source_before = source_evidence(args.source)
    if diagnostic and source_before != diagnostic_recipe["source"]:
        raise ValueError("Diagnostic/export official source differs")
    if args.role == "F" and (recipe["source_config_sha256"] != sha256(config_path)
                             or recipe["source_revision"] != source_before["revision"]):
        raise ValueError("Training/export official source differs")
    sys.path.insert(0, str(args.source.resolve()))
    from ppocr.modeling.architectures import build_model
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    architecture = copy.deepcopy(config["Architecture"])
    chars = args.dictionary.read_text(encoding="utf-8").splitlines()
    count = len(chars) + 2
    architecture["Head"]["out_channels_list"] = {"CTCLabelDecode": count,
        "SARLabelDecode": count + 2, "NRTRLabelDecode": count + 3}
    architecture["Head"]["head_list"][1]["NRTRHead"]["max_text_length"] = 66
    if args.role == "R":
        expected_architecture = json.loads(Path(origin["architecture"]["path"]).read_text(encoding="utf-8"))
        if architecture != expected_architecture or source_before != origin["source"]:
            raise ValueError("Expansion/export architecture or source differs")
    write_json(output / "architecture.json", architecture)
    paddle.set_device("cpu")
    model = build_model(copy.deepcopy(architecture))
    state = paddle.load(str(args.checkpoint))
    audit = shape_audit({key: value.shape for key, value in model.state_dict().items()},
                        {key: value.shape for key, value in state.items()})
    write_json(output / "weight-audit.json", audit)
    if not audit["ok"]:
        raise ValueError("Candidate checkpoint has unexpected keys or shapes")
    model.set_state_dict(state)
    model.eval()
    outputs = []
    with paddle.no_grad():
        for item in inputs["items"]:
            path = args.inputs / item["tensor"]
            if sha256(path) != item["sha256"]:
                raise ValueError("Fixed input changed")
            prediction = model(paddle.to_tensor(np.load(path, allow_pickle=False))).numpy()
            if prediction.dtype != np.float32 or not np.isfinite(prediction).all():
                raise ValueError("Candidate prediction is not finite float32")
            destination = output / f"{item['id']}-cpu.npy"
            np.save(destination, prediction, allow_pickle=False)
            outputs.append({"id": item["id"], "input_sha256": item["sha256"],
                            "path": destination.name, "sha256": sha256(destination), "shape": list(prediction.shape)})
    if not args.no_reparameterize:
        for layer in model.sublayers():
            if hasattr(layer, "rep") and not getattr(layer, "is_repped", False):
                layer.rep()
    static = paddle.jit.to_static(model, input_spec=[paddle.static.InputSpec(
        shape=[None, 3, 48, -1], dtype="float32", name="x")], full_graph=True)
    paddle.jit.save(static, str(output / "inference"))
    if before != file_snapshot(files) or source_before != source_evidence(args.source):
        raise ValueError("Candidate export inputs or official source changed")
    (output / "dict.txt").write_bytes(args.dictionary.read_bytes())
    result = {"status": ("exported_diagnostic" if diagnostic else
                          "exported_trained" if args.role == "F" else "exported_initialized"),
              "id": args.id, "role": args.role, "paddle": paddle.__version__,
              "checkpoint_sha256": sha256(args.checkpoint), "dictionary_sha256": sha256(args.dictionary),
              "config_sha256": sha256(config_path), "source": source_before,
              "architecture_sha256": sha256(output / "architecture.json"),
              "weight_audit_sha256": sha256(output / "weight-audit.json"),
              "origin_result": {"path": str(args.origin_result.resolve()), "sha256": sha256(args.origin_result)},
              "scope": "bn_stat_combination_diagnostic" if diagnostic else "primary",
              "reparameterized": not args.no_reparameterize,
              "additional_training_steps": 0 if diagnostic else None,
              "input_manifest_sha256": sha256(args.inputs / "manifest.json"), "outputs": outputs,
              "producer_sha256": sha256(Path(__file__)), "provenance_unchanged": True,
              "export": [{"file": path.name, "sha256": sha256(path), "size": path.stat().st_size}
                         for path in sorted(output.glob("inference.*"))]}
    write_json(output / "result.json", result)
    print(json.dumps({"status": result["status"], "output": str(output), "outputs": len(outputs)}), flush=True)


def main():
    parser = argparse.ArgumentParser(__doc__)
    for name in ("source", "checkpoint", "dictionary", "origin-result", "inputs", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--role", choices=["R", "F"], required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--no-reparameterize", action="store_true",
                        help="Diagnostic export retaining the original eval branches; keep normal export as default")
    args = parser.parse_args()
    try:
        run(args)
    except Exception as error:
        args.output.mkdir(parents=True, exist_ok=True)
        write_json(args.output / "failure.json", {"error": str(error), "traceback": traceback.format_exc()})
        raise


if __name__ == "__main__":
    main()
