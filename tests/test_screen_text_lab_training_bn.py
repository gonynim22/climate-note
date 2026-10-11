"""A BN counterfactual changes running statistics only, with no training."""
import numpy as np
import pytest

from tools.screen_text_lab.training.bn_diagnostic import swap_batchnorm_statistics
from tools.screen_text_lab.training.state_expansion import bitwise_equal


def _states():
    original = {"backbone.block.bn._mean": np.array([0.0, -0.0], dtype=np.float32),
                "backbone.block.bn._variance": np.array([1.0, 2.0], dtype=np.float32),
                "backbone.block.bn.weight": np.array([3.0, 4.0], dtype=np.float32),
                "backbone.block.bn.bias": np.array([5.0, 6.0], dtype=np.float32),
                "head.ctc_head.fc.weight": np.array([[7.0, 8.0]], dtype=np.float32)}
    trained = {key: value + np.float32(10) for key, value in original.items()}
    return original, trained


@pytest.mark.parametrize("reverse", [False, True])
def test_two_directions_preserve_affine_and_other_weights(reverse):
    original, trained = _states()
    base, donor = (original, trained) if reverse else (trained, original)
    before_base = {key: value.copy() for key, value in base.items()}
    before_donor = {key: value.copy() for key, value in donor.items()}
    result, report = swap_batchnorm_statistics(base, donor)
    assert report["stat_pairs"] == 1 and len(report["modified_keys"]) == 2
    for key in base:
        reference = donor[key] if key.endswith(("._mean", "._variance")) else base[key]
        assert bitwise_equal(result[key], reference)
        assert bitwise_equal(base[key], before_base[key])
        assert bitwise_equal(donor[key], before_donor[key])
        assert not np.shares_memory(result[key], base[key])
        assert not np.shares_memory(result[key], donor[key])


@pytest.mark.parametrize("change", ["missing_pair", "shape", "dtype", "nan", "negative_variance", "no_stats", "extra"])
def test_malformed_states_cannot_create_a_diagnostic(change):
    original, trained = _states()
    if change == "missing_pair":
        del original["backbone.block.bn._variance"]
        del trained["backbone.block.bn._variance"]
    elif change == "shape":
        trained["head.ctc_head.fc.weight"] = np.ones((3, 2), dtype=np.float32)
    elif change == "dtype":
        trained["backbone.block.bn._mean"] = trained["backbone.block.bn._mean"].astype(np.float64)
    elif change == "nan":
        trained["backbone.block.bn._mean"][0] = np.nan
    elif change == "negative_variance":
        trained["backbone.block.bn._variance"][0] = -1
    elif change == "no_stats":
        original = {key: value for key, value in original.items() if not key.endswith(("._mean", "._variance"))}
        trained = {key: value for key, value in trained.items() if not key.endswith(("._mean", "._variance"))}
    else:
        trained["unexpected"] = np.zeros(1, dtype=np.float32)
    with pytest.raises(ValueError):
        swap_batchnorm_statistics(original, trained)


def test_unchanged_statistics_are_not_claimed_as_modified():
    original, _ = _states()
    result, report = swap_batchnorm_statistics(original, original)
    assert report["modified_keys"] == []
    assert all(bitwise_equal(result[key], value) for key, value in original.items())
