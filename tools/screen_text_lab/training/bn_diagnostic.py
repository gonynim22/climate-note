"""Two zero-step, CPU-only counterfactual checkpoints for BN-stat diagnostics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .contracts import class_tokens, sha256
from .provenance import file_snapshot, source_evidence
from .state_expansion import array_hash, bitwise_equal


def swap_batchnorm_statistics(base_state, donor_state):
    """Copy complete _mean/_variance pairs; preserve affine and all other arrays."""
    if not isinstance(base_state, dict) or not isinstance(donor_state, dict) or set(base_state) != set(donor_state):
        raise ValueError("BN diagnostic states must have identical keys")
    stat_keys = sorted(key for key in base_state if key.endswith(("._mean", "._variance")))
    if not stat_keys:
        raise ValueError("No running BatchNorm statistics found")
    prefixes = {key.rsplit(".", 1)[0] for key in stat_keys}
    for prefix in prefixes:
        if prefix + "._mean" not in base_state or prefix + "._variance" not in base_state:
            raise ValueError("Incomplete BatchNorm mean/variance pair")
        mean, variance = base_state[prefix + "._mean"], base_state[prefix + "._variance"]
        if mean.ndim != 1 or variance.shape != mean.shape:
            raise ValueError("BatchNorm statistics must be matching one-dimensional vectors")
    snapshots = {}
    for key in sorted(base_state):
        first, second = base_state[key], donor_state[key]
        if (not isinstance(first, np.ndarray) or not isinstance(second, np.ndarray)
                or first.dtype.kind not in "fiu" or second.dtype != first.dtype or first.shape != second.shape):
            raise ValueError(f"Tensor type, dtype or shape differs: {key}")
        if not np.isfinite(first).all() or not np.isfinite(second).all():
            raise ValueError(f"Non-finite input tensor: {key}")
        if key.endswith("._variance") and (np.any(first < 0) or np.any(second < 0)):
            raise ValueError(f"Negative running variance: {key}")
        snapshots[key] = (array_hash(first), array_hash(second))
    result, proofs, changed = {}, {}, []
    for key in sorted(base_state):
        donor = key in stat_keys
        source = donor_state[key] if donor else base_state[key]
        result[key] = source.copy(order="C")
        if not bitwise_equal(result[key], source):
            raise ValueError(f"Copied tensor differs: {key}")
        if not bitwise_equal(result[key], base_state[key]):
            changed.append(key)
        proofs[key] = {"source": "donor" if donor else "base", "sha256": array_hash(result[key]),
                       "base_sha256": snapshots[key][0], "donor_sha256": snapshots[key][1]}
    if not set(changed).issubset(stat_keys):
        raise ValueError("A non-stat tensor changed")
    if any(snapshots[key] != (array_hash(base_state[key]), array_hash(donor_state[key])) for key in base_state):
        raise ValueError("Input state changed during diagnostic construction")
    return result, {"stat_keys": stat_keys, "stat_pairs": len(prefixes), "modified_keys": changed,
                    "tensor_proofs": proofs, "all_other_tensors_bitwise_equal": True,
                    "all_requested_stats_bitwise_equal": True, "input_states_preserved": True}


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, value):
    with open(path, "x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": sha256(path)}


def run(args):
    """The parent result identifies the trained checkpoint; no GPU or training call."""
    import paddle
    parent_path = args.training_result.resolve()
    original_path = args.original_checkpoint.resolve()
    dictionary = args.dictionary.resolve()
    parent = _read(parent_path)
    if parent.get("status") != "completed" or not parent.get("provenance_unchanged") or parent.get("completed_steps", 0) <= 0:
        raise ValueError("A completed, provenance-stable training result is required")
    trained_path = Path(parent["checkpoint"]["path"]).resolve()
    if sha256(trained_path) != parent["checkpoint"]["sha256"]:
        raise ValueError("Parent training checkpoint changed")
    recipe_path = parent_path.parent / "recipe.json"
    before_path, after_path = parent_path.parent / "provenance-before.json", parent_path.parent / "provenance-after.json"
    for path, key in ((recipe_path, "recipe_sha256"), (before_path, "provenance_before_sha256"), (after_path, "provenance_after_sha256")):
        if sha256(path) != parent[key]:
            raise ValueError("Parent training recipe/provenance artifact changed")
    recipe, before_record, after_record = _read(recipe_path), _read(before_path), _read(after_path)
    if before_record != after_record:
        raise ValueError("Parent training provenance was not stable")
    if sha256(original_path) != recipe["checkpoint_sha256"] or sha256(dictionary) != recipe["loader"]["dictionary_sha256"]:
        raise ValueError("Original checkpoint or dictionary differs from training input")
    chars = dictionary.read_text(encoding="utf-8").splitlines()
    ctc_count = len(class_tokens(chars))
    # A only: original and trained states must share the same unchanged vocabulary.
    if len(chars) != 11945:
        raise ValueError("This diagnostic is frozen to the original A dictionary")
    configs = [Path(path) for path in before_record["files"] if path.replace("\\", "/").endswith(
        "/configs/rec/PP-OCRv5/multi_language/korean_PP-OCRv5_mobile_rec.yml")]
    if len(configs) != 1:
        raise ValueError("Cannot identify pinned official source from parent provenance")
    official_source = configs[0].parents[4]
    source_before = source_evidence(official_source)
    if source_before != before_record["source"] or sha256(configs[0]) != recipe["source_config_sha256"]:
        raise ValueError("Official source differs from parent training")
    watched = [parent_path, original_path, trained_path, dictionary, recipe_path, before_path, after_path,
               Path(__file__), Path(__file__).with_name("state_expansion.py"),
               Path(__file__).with_name("contracts.py"), Path(__file__).with_name("provenance.py")]
    input_before = file_snapshot(watched)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    paddle.set_device("cpu")
    original = {key: tensor.numpy().copy() for key, tensor in paddle.load(str(original_path)).items()}
    trained = {key: tensor.numpy().copy() for key, tensor in paddle.load(str(trained_path)).items()}
    if (original["head.ctc_head.fc.weight"].shape != (120, ctc_count)
            or trained["head.ctc_head.fc.weight"].shape != (120, ctc_count)):
        raise ValueError("CTC shape differs from the unchanged A dictionary")
    variants = (("trained_weights_original_bn", trained, original, "trained", "original"),
                ("original_weights_trained_bn", original, trained, "original", "trained"))
    results = []
    for mode, base, donor, base_name, donor_name in variants:
        target = output / mode
        target.mkdir()
        state, report = swap_batchnorm_statistics(base, donor)
        tensor_proofs = {key: {**proof, "source": donor_name if proof["source"] == "donor" else base_name}
                         for key, proof in report["tensor_proofs"].items()}
        diagnostic_recipe = {"original_checkpoint": _reference(original_path), "trained_checkpoint": _reference(trained_path),
                             "parent_training_result": _reference(parent_path), "dictionary": _reference(dictionary),
                             "mode": mode, "additional_training_steps": 0, "source": source_before,
                             **report, "tensor_proofs": tensor_proofs,
                             "producer_sha256": sha256(Path(__file__)), "input_hashes": input_before}
        _write(target / "diagnostic-recipe.json", diagnostic_recipe)
        checkpoint = target / "checkpoint.pdparams"
        paddle.save({key: paddle.to_tensor(value) for key, value in state.items()}, str(checkpoint))
        loaded = {key: tensor.numpy() for key, tensor in paddle.load(str(checkpoint)).items()}
        if set(loaded) != set(state) or any(not bitwise_equal(state[key], loaded[key]) for key in state):
            raise ValueError("Freshly loaded diagnostic checkpoint is not bitwise equal")
        after = file_snapshot(watched)
        if after != input_before or source_evidence(official_source) != source_before:
            raise ValueError("Diagnostic inputs or source changed")
        result = {"status": "diagnostic_completed", "mode": mode, "additional_training_steps": 0,
                  "checkpoint": _reference(checkpoint), "dictionary": _reference(dictionary),
                  "parent_training_result": _reference(parent_path),
                  "diagnostic_recipe": _reference(target / "diagnostic-recipe.json"),
                  "provenance_unchanged": True, "fresh_load_bitwise_equal": True,
                  "changed_stat_keys": report["modified_keys"], "stat_pairs": report["stat_pairs"],
                  "product_adoption": "not_evaluated", "actual_model_evaluation": "not_run"}
        _write(target / "result.json", result)
        results.append(result)
    _write(output / "result.json", {"status": "diagnostics_created", "variants": results,
                                   "additional_training_steps": 0, "device": "cpu"})
    print(json.dumps({"status": "diagnostics_created", "output": str(output)}), flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(__doc__)
    for name in ("original-checkpoint", "training-result", "dictionary", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
