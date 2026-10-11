"""Vocabulary expansion must preserve old classes and seeded new parameters."""
import copy

import numpy as np
import pytest

from tools.screen_text_lab.training.state_expansion import (
    CLASS_PARAMETERS, bitwise_equal, expand_state,
)


def _states():
    old_chars, new_chars = ["가", "나"], ["가", "나", "℃", "㈜"]
    rng = np.random.default_rng(2411)
    old, initialized = {}, {}
    for key, spec in CLASS_PARAMETERS.items():
        old_count, new_count = (4, 6) if spec["head"] == "ctc" else (8, 10)
        if spec["feature_size"] is None:
            old_shape, new_shape = (old_count,), (new_count,)
        elif spec["axis"] == 0:
            old_shape, new_shape = (old_count, spec["feature_size"]), (new_count, spec["feature_size"])
        else:
            old_shape, new_shape = (spec["feature_size"], old_count), (spec["feature_size"], new_count)
        old[key] = rng.normal(size=old_shape).astype(np.float32)
        initialized[key] = rng.normal(size=new_shape).astype(np.float32)
    old["backbone.test.weight"] = np.array([[0.0, -0.0], [1.0, -2.0]], dtype=np.float32)
    initialized["backbone.test.weight"] = np.full((2, 2), 999.0, dtype=np.float32)
    return old, initialized, old_chars, new_chars


def test_old_classes_and_nrtr_unmapped_extra_slot_are_bitwise_preserved():
    old, initialized, old_chars, new_chars = _states()
    old_before, initialized_before = copy.deepcopy(old), copy.deepcopy(initialized)
    expanded, report = expand_state(old, initialized, old_chars, new_chars)
    assert report["class_id_mapping"]["ctc"] == [0, 1, 2, 5]
    assert report["class_id_mapping"]["nrtr"] == [0, 1, 2, 3, 4, 5, 8, 9]
    assert report["nrtr_extra_slot"]["old_id"] == 7
    assert report["nrtr_extra_slot"]["new_id"] == 9
    assert report["new_class_ids"] == {"ctc": [3, 4], "nrtr": [6, 7]}
    for key, spec in CLASS_PARAMETERS.items():
        mapping = report["class_id_mapping"][spec["head"]]
        assert bitwise_equal(np.take(expanded[key], mapping, axis=spec["axis"]), old[key])
        fresh = report["new_class_ids"][spec["head"]]
        assert bitwise_equal(np.take(expanded[key], fresh, axis=spec["axis"]),
                             np.take(initialized[key], fresh, axis=spec["axis"]))
    assert bitwise_equal(expanded["backbone.test.weight"], old["backbone.test.weight"])
    for key in old:
        assert bitwise_equal(old[key], old_before[key])
        assert bitwise_equal(initialized[key], initialized_before[key])
        assert not np.shares_memory(expanded[key], old[key])
        assert not np.shares_memory(expanded[key], initialized[key])


def test_old_projection_and_masked_softmax_preserved_but_full_softmax_changes():
    old, initialized, old_chars, new_chars = _states()
    expanded, report = expand_state(old, initialized, old_chars, new_chars)
    # A fixed feature vector isolates the copied CTC classifier from the network.
    features = np.arange(120, dtype=np.float32).reshape(1, 120) / 120
    weight, bias = "head.ctc_head.fc.weight", "head.ctc_head.fc.bias"
    old_logits = features @ old[weight] + old[bias]
    all_logits = features @ expanded[weight] + expanded[bias]
    selected = np.take(all_logits, report["class_id_mapping"]["ctc"], axis=1)
    np.testing.assert_allclose(selected, old_logits, rtol=1e-6, atol=1e-6)
    def softmax(array):
        value = np.exp(array - array.max(axis=1, keepdims=True))
        return value / value.sum(axis=1, keepdims=True)
    np.testing.assert_allclose(softmax(selected), softmax(old_logits), rtol=1e-6, atol=1e-6)
    assert not np.allclose(np.take(softmax(all_logits), report["class_id_mapping"]["ctc"], axis=1),
                           softmax(old_logits), rtol=1e-6, atol=1e-6)


@pytest.mark.parametrize("key", list(CLASS_PARAMETERS))
def test_each_class_parameter_rejects_wrong_class_dimension_or_axis(key):
    old, initialized, old_chars, new_chars = _states()
    initialized[key] = initialized[key][:-1].copy()
    with pytest.raises(ValueError, match="shape/axis"):
        expand_state(old, initialized, old_chars, new_chars)


def test_nrtr_extra_slot_must_exist_in_both_states():
    old, initialized, old_chars, new_chars = _states()
    key = "head.gtc_head.embedding.embedding.weight"
    old[key] = old[key][:-1].copy()
    with pytest.raises(ValueError, match="shape/axis"):
        expand_state(old, initialized, old_chars, new_chars)


@pytest.mark.parametrize("mutation", ["missing", "extra", "other_shape", "dtype", "nonfinite", "reorder", "duplicate", "no_growth"])
def test_unexpected_change_is_rejected_before_rewriting(mutation):
    old, initialized, old_chars, new_chars = _states()
    if mutation == "missing":
        del initialized["head.ctc_head.fc.bias"]
    elif mutation == "extra":
        initialized["new.unapproved.parameter"] = np.ones(1, dtype=np.float32)
    elif mutation == "other_shape":
        initialized["backbone.test.weight"] = np.ones((3, 2), dtype=np.float32)
    elif mutation == "dtype":
        initialized["head.ctc_head.fc.weight"] = initialized["head.ctc_head.fc.weight"].astype(np.float64)
    elif mutation == "nonfinite":
        old["head.ctc_head.fc.bias"][0] = np.nan
    elif mutation == "reorder":
        new_chars = ["나", "가", "℃", "㈜"]
    elif mutation == "duplicate":
        new_chars = ["가", "나", "℃", "℃"]
    elif mutation == "no_growth":
        new_chars = old_chars.copy()
    snapshots = {key: value.copy() for key, value in initialized.items()}
    with pytest.raises(ValueError):
        expand_state(old, initialized, old_chars, new_chars)
    assert all(bitwise_equal(value, snapshots[key]) for key, value in initialized.items())


def test_signed_zero_is_not_treated_as_bitwise_equal():
    assert not bitwise_equal(np.array([0.0], dtype=np.float32), np.array([-0.0], dtype=np.float32))
