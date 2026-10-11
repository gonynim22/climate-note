"""Copy a checkpoint into an explicitly expanded vocabulary without Paddle.

The caller creates the new architecture with a recorded initialization seed.
This module keeps its new-class initial values, copies every old parameter, and
does not claim that the expanded, unmasked softmax equals the old softmax.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

from .contracts import class_mapping, class_tokens


# Pinned Korean PP-OCRv5 MultiHead. No other shape changes are allowed.
CLASS_PARAMETERS = {
    "head.ctc_head.fc.weight": {"head": "ctc", "axis": 1, "feature_size": 120},
    "head.ctc_head.fc.bias": {"head": "ctc", "axis": 0, "feature_size": None},
    "head.gtc_head.embedding.embedding.weight": {"head": "nrtr", "axis": 0, "feature_size": 384},
    "head.gtc_head.tgt_word_prj.weight": {"head": "nrtr", "axis": 1, "feature_size": 384},
}

NRTR_EXTRA_SLOT_EVIDENCE = {
    "revision": "dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf",
    "head_source": "ppocr/modeling/heads/rec_nrtr_head.py:59",
    "encoder_source": "ppocr/data/imaug/label_ops.py:1321",
    "loss_source": "ppocr/losses/rec_nrtr_loss.py",
    "inference_source": "ppocr/modeling/heads/rec_multi_head.py:145",
    "role": (
        "Transformer allocates out_channels + 1 embedding/projection classes. "
        "NRTRLabelEncode emits only blank/unknown/start/end, dictionary and space IDs. "
        "The last head class therefore has no encoder token in this pinned configuration. "
        "It is not padding (padding is ID 0), nor a new dictionary character. "
        "It participates in the NRTR softmax and default label-smoothing loss, so both "
        "its embedding row and projection column are preserved at the new final index. "
        "MultiHead evaluation returns CTC only."
    ),
}


def array_hash(array: np.ndarray) -> str:
    digest = hashlib.sha256()
    digest.update(json.dumps({"shape": list(array.shape), "dtype": array.dtype.str}, sort_keys=True).encode())
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def bitwise_equal(first: np.ndarray, second: np.ndarray) -> bool:
    return (first.shape == second.shape and first.dtype == second.dtype
            and first.tobytes(order="C") == second.tobytes(order="C"))


def _expected_shape(spec, classes):
    if spec["feature_size"] is None:
        return (classes,)
    return (classes, spec["feature_size"]) if spec["axis"] == 0 else (spec["feature_size"], classes)


def _validate_array(key, array):
    if not isinstance(array, np.ndarray) or array.dtype.kind not in "fiu":
        raise ValueError(f"State parameter must be a real numeric NumPy array: {key}")
    if not np.isfinite(array).all():
        raise ValueError(f"Non-finite state parameter: {key}")


def expand_state(old_state: dict, new_state: dict, old_chars: list[str], new_chars: list[str]):
    """Return a new state and bitwise proof; never modify either input state.

    Only the four named class tensors may change shape. Vocabulary growth is
    append-only, implicit space moves, and NRTR's unnamed extra final slot moves
    after the new space. Inputs must already contain the caller's seeded official
    initial values. Actual model/logit parity is a separate CPU/Paddle check.
    """
    old_tokens = {head: class_tokens(old_chars, head) for head in ("ctc", "nrtr")}
    new_tokens = {head: class_tokens(new_chars, head) for head in ("ctc", "nrtr")}
    if len(new_chars) <= len(old_chars) or new_chars[:len(old_chars)] != old_chars:
        raise ValueError("Dictionary expansion must append new characters without reordering old characters")
    if not isinstance(old_state, dict) or not isinstance(new_state, dict) or set(old_state) != set(new_state):
        raise ValueError("Old and initialized state keys must match exactly")
    if not set(CLASS_PARAMETERS).issubset(old_state):
        raise ValueError("State is missing a required CTC/NRTR class parameter")

    maps = {head: class_mapping(old_chars, new_chars, head) for head in ("ctc", "nrtr")}
    # The extra slot is outside class_tokens() and must not become a new glyph.
    old_extra, new_extra = len(old_tokens["nrtr"]), len(new_tokens["nrtr"])
    maps["nrtr"] = maps["nrtr"] + [new_extra]
    counts_old = {"ctc": len(old_tokens["ctc"]), "nrtr": old_extra + 1}
    counts_new = {"ctc": len(new_tokens["ctc"]), "nrtr": new_extra + 1}
    new_ids = {head: sorted(set(range(counts_new[head])) - set(maps[head])) for head in maps}
    for head, mapping in maps.items():
        if len(mapping) != counts_old[head] or len(set(mapping)) != len(mapping):
            raise ValueError(f"Class mapping is not a one-to-one complete old-class map: {head}")
        if len(new_ids[head]) != len(new_chars) - len(old_chars):
            raise ValueError(f"New-class count differs from dictionary growth: {head}")
        if maps[head][len(old_tokens[head]) - 1] != len(new_tokens[head]) - 1:
            raise ValueError(f"Implicit space mapping failed: {head}")
    if maps["nrtr"][old_extra] != new_extra or new_extra in new_ids["nrtr"]:
        raise ValueError("NRTR extra slot was not preserved separately from added characters")

    # Validate the entire checkpoint before allocating any rewritten state.
    input_hashes = {}
    for key in sorted(old_state):
        old, initialized = old_state[key], new_state[key]
        _validate_array(key, old)
        _validate_array(key, initialized)
        if old.dtype != initialized.dtype:
            raise ValueError(f"Dtype mismatch: {key}")
        spec = CLASS_PARAMETERS.get(key)
        if spec:
            if old.dtype != np.dtype("float32"):
                raise ValueError(f"Class parameter must retain float32 precision: {key}")
            if (old.shape != _expected_shape(spec, counts_old[spec["head"]])
                    or initialized.shape != _expected_shape(spec, counts_new[spec["head"]])):
                raise ValueError(f"Unexpected class tensor shape/axis: {key}")
        elif old.shape != initialized.shape:
            raise ValueError(f"Shape change is outside the four-key allowlist: {key}")
        input_hashes[key] = {"old": array_hash(old), "initialized": array_hash(initialized)}

    result, proofs = {}, {}
    for key in sorted(old_state):
        old, initialized = old_state[key], new_state[key]
        spec = CLASS_PARAMETERS.get(key)
        if spec is None:
            expanded = old.copy(order="C")
            old_ok, new_ok = bitwise_equal(old, expanded), True
            proof = {"operation": "copy_old_unchanged", "old_bitwise_equal": old_ok,
                     "new_class_initialization_preserved": True}
        else:
            axis, head = spec["axis"], spec["head"]
            expanded = initialized.copy(order="C")
            index = [slice(None)] * expanded.ndim
            index[axis] = maps[head]
            expanded[tuple(index)] = old
            old_ok = bitwise_equal(old, np.take(expanded, maps[head], axis=axis))
            new_ok = bitwise_equal(np.take(initialized, new_ids[head], axis=axis),
                                   np.take(expanded, new_ids[head], axis=axis))
            proof = {"operation": "map_old_keep_new_initialization", "head": head, "axis": axis,
                     "old_bitwise_equal": old_ok, "new_class_initialization_preserved": new_ok,
                     "old_class_count": counts_old[head], "new_class_count": counts_new[head]}
        if not old_ok or not new_ok:
            raise ValueError(f"Bitwise preservation failed: {key}")
        if input_hashes[key] != {"old": array_hash(old), "initialized": array_hash(initialized)}:
            raise ValueError(f"An input state changed during expansion: {key}")
        result[key] = expanded
        proofs[key] = {**proof, "old_shape": list(old.shape), "new_shape": list(expanded.shape),
                       "old_sha256": input_hashes[key]["old"],
                       "initialized_sha256": input_hashes[key]["initialized"],
                       "expanded_sha256": array_hash(expanded)}

    report = {"status": "expanded_parameters_verified", "old_dictionary_count": len(old_chars),
              "new_dictionary_count": len(new_chars), "added_characters": new_chars[len(old_chars):],
              "class_id_mapping": maps, "new_class_ids": new_ids,
              "parameter_count": len(result), "class_parameter_allowlist": CLASS_PARAMETERS,
              "all_old_slices_bitwise_equal": True,
              "all_new_class_slices_initialization_preserved": True,
              "inputs_preserved": True, "parameter_proofs": proofs,
              "space_ids": {head: {"old": len(old_tokens[head]) - 1, "new": len(new_tokens[head]) - 1} for head in maps},
              "nrtr_extra_slot": {"old_id": old_extra, "new_id": new_extra, "preserved": True,
                                  **NRTR_EXTRA_SLOT_EVIDENCE},
              "initializer_seed": "caller must record the seed used to construct new_state",
              "actual_model_logits": "not_run",
              "softmax_note": "Only old-token projected values are preserved; full expanded softmax is not asserted equal."}
    return result, report
