"""Keep running BatchNorm statistics fixed while other layers train normally."""


def freeze_batchnorm_statistics(model, batchnorm_types):
    if not model.training:
        raise ValueError("Set the parent model to training mode first")
    layers = [layer for layer in model.sublayers() if isinstance(layer, batchnorm_types)]
    if not layers:
        raise ValueError("No BatchNorm layers found; refuse an ineffective frozen-stat experiment")
    for layer in layers:
        layer.eval()
    if not model.training or any(layer.training for layer in layers):
        raise ValueError("BatchNorm mode or parent training mode differs from the experiment")
    return {"mode": "frozen_running_statistics", "layers": len(layers),
            "affine_parameters": "remain_trainable", "other_training_layers": "unchanged"}
