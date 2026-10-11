from types import SimpleNamespace

import pytest

from tools.screen_text_lab.training.frozen_bn import freeze_batchnorm_statistics


def test_only_running_stat_layer_mode_is_frozen():
    class BatchNorm:
        training = True
        weight_trainable = True

        def eval(self):
            self.training = False

    bn, dropout = BatchNorm(), SimpleNamespace(training=True)
    model = SimpleNamespace(training=True, sublayers=lambda: [dropout, bn])
    result = freeze_batchnorm_statistics(model, (BatchNorm,))
    assert result["layers"] == 1 and not bn.training
    assert model.training and dropout.training and bn.weight_trainable


@pytest.mark.parametrize("training", [False, True])
def test_wrong_parent_mode_or_missing_batchnorm_is_rejected(training):
    model = SimpleNamespace(training=training, sublayers=lambda: [])
    with pytest.raises(ValueError):
        freeze_batchnorm_statistics(model, (str,))
