"""Create synthetic fixed tensors and measure the unchanged product ONNX."""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import sha256


def measure_steps(requested: Path, product: Path, output: Path) -> dict:
    import numpy as np
    import onnxruntime as ort

    widths = json.loads(requested.read_text(encoding="utf-8"))["widths"]
    if not widths or any(not isinstance(width, int) or not 8 <= width <= 8192 for width in widths):
        raise ValueError("Widths must be explicit integers between 8 and 8192")
    ort.disable_telemetry_events()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(product), options, providers=["CPUExecutionProvider"])
    steps = {}
    for width in sorted(set(widths)):
        tensor = np.zeros((1, 3, 48, width), dtype=np.float32)
        prediction = session.run(None, {session.get_inputs()[0].name: tensor})[0]
        steps[str(width)] = prediction.shape[1]
    result = {"model_sha256": sha256(product), "height": 48,
              "requested_sha256": sha256(requested), "observed_width_steps": steps}
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Measured {len(steps)} widths: {output}", flush=True)
    return result


def prepare(output: Path, product: Path, dictionary: Path, font: Path) -> dict:
    import numpy as np
    import onnxruntime as ort
    from PIL import Image, ImageDraw, ImageFont
    from screen_text.engine import resize_bilinear

    output.mkdir(parents=True, exist_ok=False)
    texts = ["원본 재현", "합계 1,234,567원", "2026년 10월 11일 기준",
             "공문서의 작은 글자와 표 안의 숫자를 확인합니다.",
             "환경 관리 계획에 따라 사업장의 배출량과 측정 결과를 검토합니다.",
             "검토 의견: 0.125 mg/L, 25 °C, 2026-10-11, 예산 123,456,789원"]
    crops = []
    records = []
    for index, text in enumerate(texts):
        face = ImageFont.truetype(str(font), 18 + index % 3 * 3)
        bounds = face.getbbox(text)
        image = Image.new("RGB", (bounds[2] - bounds[0] + 8, bounds[3] - bounds[1] + 8), "white")
        ImageDraw.Draw(image).text((4 - bounds[0], 4 - bounds[1]), text, font=face, fill="black")
        path = output / f"crop-{index}.png"
        image.save(path)
        array = np.asarray(image)
        width = max(8, int(np.ceil(48 * array.shape[1] / array.shape[0])))
        crop = resize_bilinear(array, width, 48)[:, :, ::-1]
        crops.append(((crop / 255.0 - 0.5) / 0.5).transpose(2, 0, 1).astype(np.float32))
        records.append({"id": f"single-{index}", "text": text, "image": path.name,
                        "image_sha256": sha256(path), "widths": [width]})
    tensors = [(record, crop[None]) for record, crop in zip(records, crops)]
    widest = max(crop.shape[-1] for crop in crops)
    batch = np.zeros((6, 3, 48, widest), dtype=np.float32)
    for index, crop in enumerate(crops):
        batch[index, :, :, :crop.shape[-1]] = crop
    tensors.append(({"id": "mixed-batch6", "widths": [crop.shape[-1] for crop in crops]}, batch))
    rng = np.random.default_rng(20261011)
    for width in (8, 16, 32, 64, 96, 160, 320, 480, 640, 960, 1280, 1920, 2560, 3200):
        tensor = rng.uniform(-1, 1, (1, 3, 48, width)).astype(np.float32)
        tensors.append(({"id": f"width-{width}", "widths": [width], "synthetic_noise": True}, tensor))
    ort.disable_telemetry_events()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(product), options, providers=["CPUExecutionProvider"])
    items, steps = [], {}
    for record, tensor in tensors:
        path = output / f"{record['id']}.npy"
        np.save(path, tensor, allow_pickle=False)
        prediction = session.run(None, {session.get_inputs()[0].name: tensor})[0]
        prediction_path = output / f"{record['id']}-product.npy"
        np.save(prediction_path, prediction, allow_pickle=False)
        record.update({"tensor": path.name, "sha256": sha256(path), "shape": list(tensor.shape),
                       "product_output": prediction_path.name, "product_output_sha256": sha256(prediction_path),
                       "output_shape": list(prediction.shape)})
        items.append(record)
        if record.get("synthetic_noise"):
            steps[str(tensor.shape[-1])] = prediction.shape[1]
        print(f"Prepared {record['id']}: {tensor.shape} -> {prediction.shape}", flush=True)
    manifest = {"purpose": "untrained weight reproduction, not accuracy evaluation", "seed": 20261011,
                "preprocessing": "screen_text.engine.resize_bilinear; float32 BGR; height48; zero batch padding",
                "product": str(product.resolve()), "product_sha256": sha256(product),
                "dictionary": str(dictionary.resolve()), "dictionary_sha256": sha256(dictionary),
                "font": str(font), "font_sha256": sha256(font), "items": items,
                "text_parity_scope": "synthetic_text_only",
                "atol": 1e-4, "rtol": 1e-3, "require_equal_strings": True}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "steps-map.json").write_text(json.dumps({"model_sha256": sha256(product), "height": 48,
                                                       "observed_width_steps": steps}, indent=2), encoding="utf-8")
    return manifest
