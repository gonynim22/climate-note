"""Create and audit a zero-step expanded checkpoint using official initializers."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import traceback

from .contracts import class_mapping, sha256, shape_audit
from .provenance import file_snapshot, source_evidence


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run(args):
    import numpy as np
    import paddle
    import yaml
    from .state_expansion import expand_state

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    config_path = args.source / "configs/rec/PP-OCRv5/multi_language/korean_PP-OCRv5_mobile_rec.yml"
    paths = [args.checkpoint, args.old_dictionary, args.dictionary, args.inputs / "manifest.json",
             config_path, Path(__file__), Path(__file__).with_name("state_expansion.py")]
    before = file_snapshot(paths)
    source = source_evidence(args.source)
    sys.path.insert(0, str(args.source.resolve()))
    from ppocr.modeling.architectures import build_model
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    old_chars = args.old_dictionary.read_text(encoding="utf-8").splitlines()
    new_chars = args.dictionary.read_text(encoding="utf-8").splitlines()
    def architecture_for(characters):
        architecture = copy.deepcopy(config["Architecture"])
        count = len(characters) + 2
        architecture["Head"]["out_channels_list"] = {"CTCLabelDecode": count,
            "SARLabelDecode": count + 2, "NRTRLabelDecode": count + 3}
        architecture["Head"]["head_list"][1]["NRTRHead"]["max_text_length"] = 66
        return architecture
    paddle.set_device("cpu")
    paddle.seed(args.seed)
    np.random.seed(args.seed)
    architecture = architecture_for(new_chars)
    old_model = build_model(architecture_for(old_chars))
    old_state = paddle.load(str(args.checkpoint))
    if not shape_audit({key: value.shape for key, value in old_model.state_dict().items()},
                       {key: value.shape for key, value in old_state.items()})["ok"]:
        raise ValueError("Original checkpoint has unexpected keys/shapes")
    old_model.set_state_dict(old_state)
    new_model = build_model(copy.deepcopy(architecture))
    expanded, audit = expand_state({key: value.numpy() for key, value in old_state.items()},
                                   {key: value.numpy() for key, value in new_model.state_dict().items()},
                                   old_chars, new_chars)
    new_model.set_state_dict({key: paddle.to_tensor(value) for key, value in expanded.items()})
    old_model.eval()
    new_model.eval()
    old_logits, new_logits = [], []
    old_hook = old_model.head.ctc_head.fc.register_forward_post_hook(
        lambda layer, inputs, result: old_logits.append(result.numpy()))
    new_hook = new_model.head.ctc_head.fc.register_forward_post_hook(
        lambda layer, inputs, result: new_logits.append(result.numpy()))
    items = json.loads((args.inputs / "manifest.json").read_text(encoding="utf-8"))["items"]
    mapping = class_mapping(old_chars, new_chars, "ctc")
    parity = []
    with paddle.no_grad():
        for item in items:
            path = args.inputs / item["tensor"]
            if sha256(path) != item["sha256"]:
                raise ValueError("Fixed tensor changed")
            tensor = paddle.to_tensor(np.load(path, allow_pickle=False))
            old_model(tensor)
            new_model(tensor)
            original, mapped = old_logits.pop(), new_logits.pop()[..., mapping]
            record = {"id": item["id"], "input_sha256": item["sha256"], "shape": list(original.shape),
                      "max_abs_diff": float(np.abs(original - mapped).max()),
                      "allclose": bool(np.allclose(original, mapped, atol=1e-4, rtol=1e-3))}
            parity.append(record)
            if not record["allclose"]:
                raise ValueError("Expanded checkpoint changed mapped old CTC logits")
    old_hook.remove()
    new_hook.remove()
    audit["masked_old_ctc_logits"] = {"passed": True, "atol": 1e-4, "rtol": 1e-3, "items": parity}
    audit["new_probabilities_note"] = "New classes remain in softmax; unmasked predictions may change before training."
    checkpoint = output / "checkpoint.pdparams"
    paddle.save(new_model.state_dict(), str(checkpoint))
    loaded = paddle.load(str(checkpoint))
    if not all(np.array_equal(loaded[key].numpy(), value) for key, value in expanded.items()):
        raise ValueError("Expanded checkpoint did not round trip bitwise")
    write_json(output / "architecture.json", architecture)
    write_json(output / "mapping.json", audit["class_id_mapping"])
    write_json(output / "expansion-proof.json", audit)
    if before != file_snapshot(paths) or source != source_evidence(args.source):
        raise ValueError("Expansion inputs changed")
    def artifact(path):
        return {"path": str(path.resolve()), "sha256": sha256(path)}
    result = {"status": "initialized", "training_steps": 0, "seed": args.seed,
              "added_characters": new_chars[len(old_chars):], "source": source,
              "original_checkpoint": artifact(args.checkpoint), "checkpoint": artifact(checkpoint),
              "dictionary": artifact(args.dictionary), "architecture": artifact(output / "architecture.json"),
              "mapping": artifact(output / "mapping.json"), "proof": artifact(output / "expansion-proof.json"),
              "input_manifest_sha256": sha256(args.inputs / "manifest.json"), "provenance_unchanged": True,
              "producer_sha256": sha256(Path(__file__))}
    write_json(output / "result.json", result)
    print(json.dumps({"status": "initialized", "output": str(output), "added": len(result["added_characters"])}), flush=True)


def main():
    parser = argparse.ArgumentParser(__doc__)
    for name in ("source", "checkpoint", "old-dictionary", "dictionary", "inputs", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261011)
    args = parser.parse_args()
    try:
        run(args)
    except Exception as error:
        args.output.mkdir(parents=True, exist_ok=True)
        write_json(args.output / "failure.json", {"error": str(error), "traceback": traceback.format_exc()})
        raise


if __name__ == "__main__":
    main()
