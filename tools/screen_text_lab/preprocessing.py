"""픽셀만 사용하는 고정 전처리 후보. 모델/정답/Qt는 import하지 않는다."""


def detect_aspect(module, engine, image, cancelled=lambda: False):
    import numpy as np
    height, width = image.shape[:2]
    ratio = min(1., module.DET_LIMIT / max(height, width))
    scaled_h, scaled_w = max(1, round(height * ratio)), max(1, round(width * ratio))
    new_h, new_w = (scaled_h + 31) // 32 * 32, (scaled_w + 31) // 32 * 32
    pixels = module.resize_bilinear(image, scaled_w, scaled_h)
    # 끝 픽셀을 연장한다. 모서리에 강한 검정/흰색 테두리를 새로 만들지 않는다.
    pixels = np.pad(pixels, ((0, new_h-scaled_h), (0, new_w-scaled_w), (0, 0)), mode="edge")
    tensor = ((pixels[:, :, ::-1] / 255. - module.DET_MEAN) / module.DET_STD)
    tensor = tensor.transpose(2, 0, 1)[None].astype(np.float32)
    prob = engine._det.run(None, {"x": tensor})[0][0, 0][:scaled_h, :scaled_w]
    boxes = []
    for x0, y0, x1, y1, runs in module.label_components(prob > module.DET_THRESHOLD, cancelled):
        if (x1-x0+1) * (y1-y0+1) < module.MIN_BOX_AREA:
            continue
        score = float(np.mean(np.concatenate([prob[y, a:b+1] for y, a, b in runs])))
        if score < module.BOX_THRESHOLD:
            continue
        fx0, fy0, fx1, fy1 = module.expand_box(x0, y0, x1, y1)
        box = (max(0, int(fx0 * width/scaled_w)), max(0, int(fy0 * height/scaled_h)),
               min(width, round(fx1 * width/scaled_w)), min(height, round(fy1 * height/scaled_h)))
        if box[2]-box[0] >= 2 and box[3]-box[1] >= 2:
            boxes.append(box)
    return boxes


def normalize_crop(crop, mode):
    import numpy as np
    if mode == "rec-320":
        return crop
    pixels = crop.astype(np.float32)
    border = np.concatenate((pixels[0], pixels[-1], pixels[:, 0], pixels[:, -1]))
    background = np.median(border, axis=0)
    # 복잡한 사진/테두리/선택 영역은 원본을 유지한다.
    if np.mean(np.max(np.abs(border-background), axis=1) <= 16) < .85:
        return crop
    distance = np.max(np.abs(pixels-background), axis=2)
    contrast = float(distance.max())
    if contrast < 24:
        return crop
    if mode in ("rec-ink", "rec-ink-native"):
        ys, xs = np.nonzero(distance > max(12., contrast * .18))
        if len(xs) < 4:
            return crop
        x0, x1, y0, y1 = xs.min(), xs.max()+1, ys.min(), ys.max()+1
        pad = max(1, round((y1-y0) * .2))
        if mode == "rec-ink-native":
            # 가는 선/점 때문에 인식 폭이 폭증하지 않게 기존 정규화 폭의 2배 안으로 제한한다.
            if y1-y0 < 4 or (x1-x0+pad*2)/(y1-y0+pad*2) > 2*crop.shape[1]/crop.shape[0]:
                return crop
        normalized = np.empty((y1-y0+pad*2, x1-x0+pad*2, 3), dtype=np.float32)
        normalized[:] = background
        normalized[pad:-pad, pad:-pad] = pixels[y0:y1, x0:x1]
        pixels = normalized
    if float(np.mean(background)) < 127.5:
        pixels = 255. - pixels
    return pixels


def read_padded(module, engine, image, boxes, cancelled, mode):
    import numpy as np
    crops = []
    for x0, y0, x1, y1 in boxes:
        crop = normalize_crop(image[y0:y1, x0:x1], mode)
        width = max(8, int(np.ceil(module.REC_HEIGHT * crop.shape[1] / max(1, crop.shape[0]))))
        crops.append(module.resize_bilinear(crop, width, module.REC_HEIGHT)[:, :, ::-1])
    results = [("", 0.)] * len(crops)
    order = sorted(range(len(crops)), key=lambda i: crops[i].shape[1])
    for start in range(0, len(order), module.REC_BATCH):
        if cancelled():
            raise module.RecognitionCancelled
        ids = order[start:start + module.REC_BATCH]
        widest = max(8 if mode == "rec-ink-native" else 320, max(crops[i].shape[1] for i in ids))
        batch = np.zeros((len(ids), 3, module.REC_HEIGHT, widest), dtype=np.float32)
        for slot, i in enumerate(ids):
            batch[slot, :, :, :crops[i].shape[1]] = ((crops[i]/255. - .5)/.5).transpose(2, 0, 1)
        probs = engine._rec.run(None, {"x": batch})[0]
        for slot, i in enumerate(ids):
            steps = max(1, int(np.ceil(probs.shape[1] * crops[i].shape[1] / widest))) if mode == "rec-ink-native" else probs.shape[1]
            results[i] = module.ctc_decode(probs[slot, :steps], engine._charset)
    return results


def read_selective(module, engine, image, boxes, cancelled, base_read, preserve_spaces=False):
    results = base_read(image, boxes, cancelled)
    ids = []
    for i, ((x0, y0, x1, y1), (_, score)) in enumerate(zip(boxes, results)):
        if score >= .97:
            continue
        crop = image[y0:y1, x0:x1]
        if normalize_crop(crop, "rec-ink-native") is not crop:
            ids.append(i)
    if ids:
        alternatives = read_padded(module, engine, image, [boxes[i] for i in ids], cancelled, "rec-ink-native")
        for i, (text, score) in zip(ids, alternatives):
            if preserve_spaces and "".join(text.split()) == "".join(results[i][0].split()):
                continue
            if text.strip() and score >= results[i][1] + .02:
                results[i] = (text, score)
    return results
