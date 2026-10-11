"""Explicit lab-only dynamic-width training adaptation for the pinned LCNet.

The official recognition forward pools to [1,40] during training. Its inference
branch uses avg_pool2d([3,2]); use that same pooling during screen-line training
so labels longer than 40 CTC timesteps remain representable. No parameters,
BatchNorm training flags, inference forward, or official source file are changed.
"""

from __future__ import annotations

from types import MethodType


def enable_dynamic_training_pool(model) -> dict:
    import paddle.nn.functional as functional

    backbone = model.backbone
    if type(backbone).__name__ != "PPLCNetV3" or backbone.det:
        raise ValueError("Dynamic pooling adaptation only supports recognition PPLCNetV3")
    original_forward = backbone.forward

    def forward(self, image):
        if not self.training:
            return original_forward(image)
        features = self.conv1(image)
        features = self.blocks2(features)
        features = self.blocks3(features)
        features = self.blocks4(features)
        features = self.blocks5(features)
        features = self.blocks6(features)
        return functional.avg_pool2d(features, [3, 2])

    backbone.forward = MethodType(forward, backbone)
    return {"official_training_pool": "adaptive_avg_pool2d [1,40]",
            "lab_training_pool": "avg_pool2d [3,2] (same as official inference)",
            "inference_forward": "unchanged official bound method",
            "parameters_changed": False, "batchnorm_training": "preserved"}
