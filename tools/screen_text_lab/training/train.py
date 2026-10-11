"""Explicit, single-GPU screen-text fine-tuning with an audited finite loader."""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import random
import sys
import time
import traceback

from .contracts import class_tokens, required_ctc_steps, sha256, shape_audit


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def load_samples(manifest_path: Path, labels_path: Path, dictionary: Path) -> tuple[list, dict]:
    from PIL import Image
    import numpy as np

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["split"] != "train":
        raise ValueError("Training only accepts an explicitly named train manifest")
    root = manifest_path.parent.resolve()
    cases = {case["image"]: case for case in manifest["cases"]}
    if any(case["split"] != "train" or case["expected"]["text"] != case["text"]
           for case in manifest["cases"]):
        raise ValueError("Every training case must belong to train and have matching expected text")
    if len(cases) != len(manifest["cases"]) or len({case["case_id"] for case in manifest["cases"]}) != len(cases):
        raise ValueError("Duplicate image or case ID in manifest")
    chars = dictionary.read_text(encoding="utf-8").splitlines()
    supported = set(class_tokens(chars)[1:])
    def ready(case):
        checks = case["checks"]
        if bool(checks["training_ready"]) != (not checks["reasons"] and checks["ctc_observed_steps"] is not None):
            raise ValueError("Inconsistent stored training-ready flag")
        reasons = set(checks["reasons"])
        if not (set(case["text"]) - supported):
            reasons.discard("oov")  # Explicit B dictionary revalidation only.
        return not reasons and checks["ctc_observed_steps"] is not None
    seen, samples = set(), []
    for line in labels_path.read_text(encoding="utf-8").splitlines():
        relative, text = line.split("\t", 1)
        if relative in seen or relative not in cases:
            raise ValueError("Duplicate or unknown labelled image")
        seen.add(relative)
        case = cases[relative]
        if not ready(case):
            raise ValueError("Label includes a case rejected by data preflight")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or sha256(path) != case["image_sha256"]:
            raise ValueError("Image escape or hash mismatch")
        if text != case["text"] or not text or len(text) > 64 or set(text) - supported:
            raise ValueError("Label text/OOV/length mismatch; no silent filtering allowed")
        with Image.open(path) as image:
            rgb = np.asarray(image.convert("RGB")).copy()
        native_width = max(8, math.ceil(48 * rgb.shape[1] / rgb.shape[0]))
        bucket = math.ceil(native_width / 32) * 32
        if bucket != case["checks"]["training_bucket_width"]:
            raise ValueError("Width differs from data preflight")
        observed = case["checks"].get("ctc_observed_steps")
        effective_steps = math.ceil(observed * native_width / bucket) if observed is not None else 0
        if observed is None or required_ctc_steps(text) > effective_steps:
            raise ValueError("Missing measured CTC capacity or impossible label")
        samples.append({"id": case["case_id"], "image": rgb, "text": text,
                        "native_width": native_width, "bucket": bucket})
    eligible = {case["image"] for case in manifest["cases"]
                if ready(case) and case["text"] and len(case["text"]) <= 64 and not (set(case["text"]) - supported)}
    if seen != eligible:
        raise ValueError("Labels do not cover exactly the dictionary-supported manifest cases")
    if not samples:
        raise ValueError("Empty training set")
    return samples, {"manifest_sha256": sha256(manifest_path), "labels_sha256": sha256(labels_path),
                     "dictionary_sha256": sha256(dictionary), "manifest_cases": len(cases),
                     "accepted_samples": len(samples), "excluded_oov_or_length": len(cases) - len(samples),
                     "silent_drops": 0, "max_width": max(sample["bucket"] for sample in samples),
                     "max_text_length": max(len(sample["text"]) for sample in samples)}


def make_batch(samples: list, encoder):
    import numpy as np
    import paddle
    from .pixels import resize_bilinear

    widest = max(sample["bucket"] for sample in samples)
    images = np.zeros((len(samples), 3, 48, widest), dtype=np.float32)
    ctc, nrtr, lengths, ratios = [], [], [], []
    for index, sample in enumerate(samples):
        width = sample["native_width"]
        resized = resize_bilinear(sample["image"], width, 48)[:, :, ::-1]
        images[index, :, :, :width] = ((resized / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)
        encoded = encoder({"image": sample["image"], "label": sample["text"]})
        if encoded is None or int(encoded["length"]) != len(sample["text"]):
            raise ValueError("Official encoder silently rejected or changed a label")
        ctc.append(encoded["label_ctc"])
        nrtr.append(encoded["label_gtc"])
        lengths.append(int(encoded["length"]))
        ratios.append(width / widest)
    arrays = [images, np.asarray(ctc, dtype=np.int64), np.asarray(nrtr, dtype=np.int64),
              np.asarray(lengths, dtype=np.int64), np.asarray(ratios, dtype=np.float64)]
    return [paddle.to_tensor(array) for array in arrays]


def learning_rate(step: int, total: int, target: float) -> float:
    warmup = max(1, math.ceil(total * 0.05))
    if step < warmup:
        return target * (step + 1) / warmup
    progress = (step - warmup) / max(1, total - warmup - 1)
    return target * 0.5 * (1 + math.cos(math.pi * min(1.0, progress)))


def run(args) -> dict:
    import numpy as np
    import paddle
    import yaml
    from .provenance import source_evidence, file_snapshot

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    config_path = args.source / "configs/rec/PP-OCRv5/multi_language/korean_PP-OCRv5_mobile_rec.yml"
    provenance_paths = [args.manifest, args.labels, args.dictionary, args.checkpoint, config_path,
                        Path(__file__), Path(__file__).with_name("pixels.py"),
                        Path(__file__).with_name("backbone.py"), Path(__file__).with_name("contracts.py"),
                        Path(__file__).with_name("provenance.py")]
    if args.freeze_bn:
        provenance_paths.append(Path(__file__).with_name("frozen_bn.py"))
    before_files = file_snapshot(provenance_paths)
    source_before = source_evidence(args.source)
    write_json(output / "provenance-before.json", {"files": before_files, "source": source_before})
    sys.path.insert(0, str(args.source.resolve()))
    # Both repositories own a `tools` namespace. The official augmentation
    # package imports tools.infer.utility even when no augmentation is enabled.
    # Extend only this isolated process with the pinned official namespace.
    import tools as tools_namespace
    tools_namespace.__path__.append(str((args.source / "tools").resolve()))
    from ppocr.modeling.architectures import build_model
    from ppocr.data.imaug.label_ops import MultiLabelEncode
    from ppocr.losses.rec_multi_loss import MultiLoss

    random.seed(args.seed)
    np.random.seed(args.seed)
    paddle.seed(args.seed)
    paddle.set_device("gpu:0")
    samples, loader_report = load_samples(args.manifest, args.labels, args.dictionary)
    write_json(output / "loader-audit.json", loader_report)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    chars = args.dictionary.read_text(encoding="utf-8").splitlines()
    count = len(chars) + 2
    architecture = copy.deepcopy(config["Architecture"])
    architecture["Head"]["out_channels_list"] = {"CTCLabelDecode": count, "SARLabelDecode": count + 2,
                                                  "NRTRLabelDecode": count + 3}
    architecture["Head"]["head_list"][1]["NRTRHead"]["max_text_length"] = 66
    model = build_model(copy.deepcopy(architecture))
    weights = paddle.load(str(args.checkpoint))
    audit = shape_audit({key: value.shape for key, value in model.state_dict().items()},
                        {key: value.shape for key, value in weights.items()})
    write_json(output / "weight-audit.json", audit)
    if not audit["ok"]:
        raise ValueError("Checkpoint shape differs; expansion must be explicit")
    model.set_state_dict(weights)
    from .backbone import enable_dynamic_training_pool
    model.eval()
    probe = paddle.zeros([1, 3, 48, max(sample["bucket"] for sample in samples)], dtype="float32")
    preserved_weights = {key: value.numpy().copy() for key, value in model.state_dict().items()}
    with paddle.no_grad():
        original_eval = model(probe).numpy()
    pooling = enable_dynamic_training_pool(model)
    with paddle.no_grad():
        adapted_eval = model(probe).numpy()
    pooling["eval_bitwise_equal_at_max_width"] = bool(np.array_equal(original_eval, adapted_eval))
    pooling["all_state_keys_and_values_preserved"] = (set(preserved_weights) == set(model.state_dict()) and
        all(np.array_equal(value, model.state_dict()[key].numpy()) for key, value in preserved_weights.items()))
    model.train()
    pooling["all_batchnorm_layers_training"] = all(layer.training for layer in model.sublayers()
                                                   if isinstance(layer, paddle.nn.BatchNorm2D))
    if not all(pooling[key] for key in ("eval_bitwise_equal_at_max_width", "all_state_keys_and_values_preserved",
                                       "all_batchnorm_layers_training")):
        raise ValueError("Lab pooling adaptation changed evaluation, parameters, or BatchNorm mode")
    write_json(output / "pooling-audit.json", pooling)
    del preserved_weights, original_eval, adapted_eval, probe
    encoder = MultiLabelEncode(max_text_length=66, character_dict_path=str(args.dictionary),
                               use_space_char=True, gtc_encode="NRTRLabelEncode")
    boundaries = {str(size): encoder({"image": samples[0]["image"], "label": "가" * size}) is not None
                  for size in (23, 24, 25, 63, 64, 65)}
    if boundaries != {"23": True, "24": True, "25": True, "63": True, "64": True, "65": False}:
        raise ValueError("Official NRTR boundary differs from the frozen contract")
    # Validate every sample with the actual official encoder before the first step.
    for sample in samples:
        encoded = encoder({"image": sample["image"], "label": sample["text"]})
        if encoded is None or int(encoded["length"]) != len(sample["text"]):
            raise ValueError("Official encoder drops a preflight-approved sample")
    loader_report["official_encoder_accepted"] = len(samples)
    loader_report["official_encoder_boundaries"] = boundaries
    write_json(output / "loader-audit.json", loader_report)
    if args.preflight_only:
        result = {"status": "preflight_passed", "loader": loader_report, "weight_audit": audit}
        write_json(output / "result.json", result)
        print(json.dumps(result, indent=2), flush=True)
        return result
    loss_fn = MultiLoss(loss_config_list=[{"CTCLoss": None}, {"NRTRLoss": None}])
    optimizer = paddle.optimizer.Adam(learning_rate=args.lr, beta1=0.9, beta2=0.999,
                                       parameters=model.parameters(), weight_decay=paddle.regularizer.L2Decay(3e-5))
    ordered = sorted(samples, key=lambda sample: (sample["bucket"], sample["id"]))
    batches = [ordered[index:index + args.batch_size] for index in range(0, len(ordered), args.batch_size)]
    total_steps = args.steps if args.steps else len(batches) * args.epochs
    recipe = {"seed": args.seed, "batch_size": args.batch_size, "total_steps": total_steps,
              "epochs": args.epochs, "target_lr": args.lr, "warmup_steps": max(1, math.ceil(total_steps * 0.05)),
              "scheduler": "linear warmup then cosine, step-based", "height": 48, "bucket_multiple": 32,
              "max_label_length": 64, "nrtr_max_text_length": 66, "augmentations": "none",
              "checkpoint_sha256": sha256(args.checkpoint), "source_config_sha256": sha256(config_path),
              "source_revision": source_before["revision"], "loader": loader_report,
              "producer_sha256": sha256(Path(__file__)), "scope": "smoke" if args.steps else "pilot"}
    recipe["batchnorm_mode"] = "frozen_running_statistics" if args.freeze_bn else "adaptive_running_statistics"
    recipe["training_pooling_adaptation"] = pooling
    recipe["pixel_helper_sha256"] = sha256(Path(__file__).with_name("pixels.py"))
    recipe["pooling_helper_sha256"] = sha256(Path(__file__).with_name("backbone.py"))
    write_json(output / "recipe.json", recipe)
    write_json(output / "architecture.json", architecture)
    model.train()
    frozen_stats, batchnorm_report = {}, {"mode": "adaptive_running_statistics"}
    if args.freeze_bn:
        from .frozen_bn import freeze_batchnorm_statistics
        batchnorm_report = freeze_batchnorm_statistics(model, tuple(getattr(paddle.nn, name) for name in
            ("BatchNorm", "BatchNorm1D", "BatchNorm2D", "BatchNorm3D", "SyncBatchNorm")))
        frozen_stats = {key: value.numpy().copy() for key, value in model.state_dict().items()
                        if key.endswith(("._mean", "._variance"))}
        if not frozen_stats:
            raise ValueError("No running statistics were captured for the frozen-BN experiment")
    first_key = "head.ctc_head.fc.weight"
    initial = model.state_dict()[first_key].numpy().copy()
    records = []
    start = time.perf_counter()
    # The first batch always probes the actual longest width, then ordered buckets.
    epoch_batches = [ordered[-args.batch_size:]] if args.steps else []
    rng = random.Random(args.seed)
    completed_samples = 0
    with (output / "steps.jsonl").open("w", encoding="utf-8") as log:
        for step in range(total_steps):
            if not epoch_batches:
                epoch_batches = list(batches)
                rng.shuffle(epoch_batches)
            chosen = epoch_batches.pop(0)
            before = time.perf_counter()
            batch = make_batch(chosen, encoder)
            rate = learning_rate(step, total_steps, args.lr)
            optimizer.set_lr(rate)
            predictions = model(batch[0], data=batch[1:])
            for slot, sample in enumerate(chosen):
                effective_steps = math.ceil(predictions["ctc"].shape[1] * sample["native_width"] / batch[0].shape[-1])
                if effective_steps < required_ctc_steps(sample["text"]):
                    raise ValueError("Actual training output has insufficient CTC steps")
            losses = loss_fn(predictions, batch)
            loss = losses["loss"]
            if not bool(paddle.isfinite(loss).item()):
                raise ValueError("Non-finite training loss")
            loss.backward()
            gradients = [paddle.all(paddle.isfinite(parameter.grad)) for parameter in model.parameters()
                         if parameter.grad is not None]
            if not gradients or not bool(paddle.all(paddle.stack(gradients)).item()):
                raise ValueError("Missing or non-finite gradients")
            ctc_gradient_norm = float(paddle.linalg.norm(model.head.ctc_head.fc.weight.grad).item())
            if not math.isfinite(ctc_gradient_norm) or ctc_gradient_norm <= 0:
                raise ValueError("CTC classifier gradient is zero or non-finite")
            optimizer.step()
            optimizer.clear_grad()
            completed_samples += len(chosen)
            row = {"step": step + 1, "lr": rate, "samples": len(chosen), "sample_ids": [sample["id"] for sample in chosen],
                   "width": batch[0].shape[-1], "seconds": time.perf_counter() - before,
                   "loss": float(loss.item()), "ctc_loss": float(losses["CTCLoss"].item()),
                   "nrtr_loss": float(losses["NRTRLoss"].item()),
                   "ctc_gradient_norm": ctc_gradient_norm,
                   "max_gpu_allocated_bytes": int(paddle.device.cuda.max_memory_allocated())}
            records.append(row)
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            log.flush()
            if step < 3 or (step + 1) % 10 == 0:
                print(f"step {step+1}/{total_steps} loss={row['loss']:.4f} width={row['width']} "
                      f"seconds={row['seconds']:.3f} VRAM={row['max_gpu_allocated_bytes']/2**20:.1f}MiB", flush=True)
    changed = bool(np.any(model.state_dict()[first_key].numpy() != initial))
    if not changed:
        raise ValueError("Training did not update the CTC classifier")
    if args.freeze_bn:
        if any(value.tobytes() != model.state_dict()[key].numpy().tobytes() for key, value in frozen_stats.items()):
            raise ValueError("Frozen BatchNorm running statistics changed during training")
        batchnorm_report.update(stat_arrays=len(frozen_stats), stats_bitwise_unchanged=True)
    write_json(output / "batchnorm-audit.json", batchnorm_report)
    model_path, optimizer_path = output / "checkpoint.pdparams", output / "checkpoint.pdopt"
    paddle.save(model.state_dict(), str(model_path))
    paddle.save(optimizer.state_dict(), str(optimizer_path))
    model.eval()
    with paddle.no_grad():
        reference = model(batch[0]).numpy()
    paddle.set_device("cpu")
    loaded_weights, loaded_optimizer = paddle.load(str(model_path)), paddle.load(str(optimizer_path))
    def same_tensors(first, second):
        return set(first) == set(second) and all(
            np.isfinite(second[key].numpy()).all() and np.array_equal(first[key].numpy(), second[key].numpy())
            for key in first)
    if not same_tensors(model.state_dict(), loaded_weights) or not same_tensors(optimizer.state_dict(), loaded_optimizer):
        raise ValueError("Saved model/optimizer tensors do not round trip exactly and finitely")
    with paddle.base.unique_name.guard():
        restored = build_model(copy.deepcopy(architecture))
        restored.set_state_dict(loaded_weights)
        restored_optimizer = paddle.optimizer.Adam(learning_rate=args.lr, parameters=restored.parameters(),
            beta1=0.9, beta2=0.999, weight_decay=paddle.regularizer.L2Decay(3e-5))
        restored_optimizer.set_state_dict(loaded_optimizer)
    if not same_tensors(loaded_weights, restored.state_dict()) or not same_tensors(loaded_optimizer, restored_optimizer.state_dict()):
        raise ValueError("Fresh objects did not restore model/optimizer tensors exactly")
    restored.eval()
    with paddle.no_grad():
        recovered = restored(paddle.to_tensor(batch[0].numpy())).numpy()
    restore_report = {"fresh_model_exact": True, "fresh_optimizer_exact": True,
                      "eval_allclose": bool(np.allclose(reference, recovered, atol=1e-4, rtol=1e-3)),
                      "eval_max_abs_diff": float(np.abs(reference - recovered).max()),
                      "exact_training_resume_supported": False}
    write_json(output / "restore-audit.json", restore_report)
    if not restore_report["eval_allclose"]:
        raise ValueError("Restored checkpoint evaluation differs")
    after_files = file_snapshot(provenance_paths)
    source_after = source_evidence(args.source)
    write_json(output / "provenance-after.json", {"files": after_files, "source": source_after})
    if before_files != after_files or source_before != source_after:
        raise ValueError("Training input/source changed during the run")
    result = {"status": "completed", "scope": recipe["scope"], "completed_steps": len(records),
              "completed_samples": completed_samples, "elapsed_seconds": time.perf_counter() - start,
              "median_step_seconds": float(np.median([row["seconds"] for row in records[1:]] or [records[0]["seconds"]])),
              "max_gpu_allocated_bytes": max(row["max_gpu_allocated_bytes"] for row in records),
              "ctc_classifier_changed": changed, "recipe_sha256": sha256(output / "recipe.json"),
              "batchnorm": batchnorm_report,
              "checkpoint": {"path": str(model_path), "sha256": sha256(model_path)},
              "optimizer": {"path": str(optimizer_path), "sha256": sha256(optimizer_path)},
              "restore": restore_report, "provenance_unchanged": True,
              "provenance_before_sha256": sha256(output / "provenance-before.json"),
              "provenance_after_sha256": sha256(output / "provenance-after.json")}
    write_json(output / "result.json", result)
    print(json.dumps(result, indent=2), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    for name in ("source", "checkpoint", "manifest", "labels", "dictionary", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--steps", type=int, default=0)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--seed", type=int, default=20261011)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--freeze-bn", action="store_true", help="Separate experiment: retain original running statistics")
    args = parser.parse_args()
    try:
        run(args)
    except Exception as error:
        args.output.mkdir(parents=True, exist_ok=True)
        write_json(args.output / "failure.json", {"type": type(error).__name__, "error": str(error),
                                                  "traceback": traceback.format_exc()})
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
