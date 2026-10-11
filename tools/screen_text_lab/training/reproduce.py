"""Load fixed official weights, audit every key, run fixed tensors and export."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import time
import traceback

from .contracts import sha256, shape_audit


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def reproduce(source: Path, checkpoint: Path, inputs: Path, output: Path, *, export_only: bool = False, forward_only: bool = False) -> dict:
    import numpy as np
    import paddle
    import yaml

    sys.path.insert(0, str(source.resolve()))
    from ppocr.modeling.architectures import build_model

    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((inputs / "manifest.json").read_text(encoding="utf-8"))
    config_path = source / "configs/rec/PP-OCRv5/multi_language/korean_PP-OCRv5_mobile_rec.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    dictionary = source / config["Global"]["character_dict_path"]
    if sha256(dictionary) != manifest["dictionary_sha256"]:
        raise ValueError("Official and product dictionary bytes differ")
    characters = dictionary.read_text(encoding="utf-8").splitlines()
    classes = len(characters) + 2
    architecture = copy.deepcopy(config["Architecture"])
    architecture["Head"]["out_channels_list"] = {
        "CTCLabelDecode": classes, "SARLabelDecode": classes + 2, "NRTRLabelDecode": classes + 3}
    write_json(output / "architecture.json", architecture)
    paddle.set_device("cpu")
    model = build_model(copy.deepcopy(architecture))
    weights = paddle.load(str(checkpoint))
    expected = model.state_dict()
    audit = shape_audit({key: value.shape for key, value in expected.items()},
                        {key: value.shape for key, value in weights.items()})
    audit.update({"checkpoint_sha256": sha256(checkpoint), "config_sha256": sha256(config_path),
                  "keys": [{"key": key, "shape": list(value.shape), "dtype": str(value.dtype)}
                           for key, value in sorted(weights.items())]})
    write_json(output / "weight-audit.json", audit)
    if not audit["ok"]:
        raise ValueError("Official checkpoint has unexpected missing/extra/shape keys; see weight-audit.json")
    model.set_state_dict(weights)
    model.eval()
    print(f"Exact checkpoint audit passed: {len(weights)} keys", flush=True)
    result = {"status": "running", "paddle": paddle.__version__, "checkpoint_sha256": sha256(checkpoint),
              "dictionary_sha256": sha256(dictionary), "config_sha256": sha256(config_path),
              "input_manifest_sha256": sha256(inputs / "manifest.json"),
              "producer_sha256": sha256(Path(__file__)), "architecture_sha256": sha256(output / "architecture.json"),
              "weight_audit_sha256": sha256(output / "weight-audit.json"),
              "weight_audit": audit["ok"], "outputs": []}
    write_json(output / "result.json", result)
    for device in (() if export_only else ("cpu", "gpu:0")):
        paddle.set_device(device)
        model.to(device)
        if device.startswith("gpu"):
            paddle.utils.run_check()
        with paddle.no_grad():
            for record in manifest["items"]:
                path = inputs / record["tensor"]
                if sha256(path) != record["sha256"]:
                    raise ValueError("Fixed input tensor changed")
                tensor = np.load(path, allow_pickle=False)
                before = time.perf_counter()
                prediction = model(paddle.to_tensor(tensor)).numpy()
                elapsed = time.perf_counter() - before
                destination = output / f"{record['id']}-{device.split(':')[0]}.npy"
                np.save(destination, prediction, allow_pickle=False)
                result["outputs"].append({"id": record["id"], "device": device,
                                          "input_sha256": record["sha256"],
                                          "path": destination.name, "sha256": sha256(destination),
                                          "shape": list(prediction.shape), "seconds": elapsed})
                print(f"{device}: {record['id']} -> {prediction.shape} in {elapsed:.3f}s", flush=True)
        write_json(output / "result.json", result)
    if forward_only:
        result["status"] = "forward_completed"
        write_json(output / "result.json", result)
        return result
    paddle.set_device("cpu")
    model.to("cpu")
    model.eval()
    # Official ppocr.utils.export_model.dynamic_to_static reparameterizes LCNet
    # layers and uses a dynamic N/W input of height48. Preserve that operation.
    for layer in model.sublayers():
        if hasattr(layer, "rep") and not getattr(layer, "is_repped", False):
            layer.rep()
    static = paddle.jit.to_static(model, input_spec=[
        paddle.static.InputSpec(shape=[None, 3, 48, -1], dtype="float32", name="x")], full_graph=True)
    paddle.jit.save(static, str(output / "inference"))
    result["export"] = [{"file": path.name, "sha256": sha256(path), "size": path.stat().st_size}
                        for path in sorted(output.glob("inference.*"))]
    result["status"] = "exported_untrained"
    result["export_only"] = export_only
    write_json(output / "result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--forward-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.export_only and args.forward_only:
            raise ValueError("Choose export-only or forward-only, not both")
        reproduce(args.source, args.checkpoint, args.inputs, args.output, export_only=args.export_only,
                  forward_only=args.forward_only)
    except Exception as error:
        args.output.mkdir(parents=True, exist_ok=True)
        write_json(args.output / "failure.json", {"type": type(error).__name__, "error": str(error),
                                                  "traceback": traceback.format_exc()})
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
