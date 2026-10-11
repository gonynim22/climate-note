"""픽셀의 빈 열에서만 줄을 나누는 고정 진단 후보. 정답/사전/태그 입력 없음."""
import math


def segments(crop, target):
    """Return a complete horizontal partition and each cut's whitespace width."""
    import numpy as np
    height, width = crop.shape[:2]
    whole = [(0, width, 0)]
    if height < 4 or width < 8 or target not in (6, 10):
        return whole
    pixels = crop.astype(np.float32)
    border = np.concatenate((pixels[0], pixels[-1], pixels[:, 0], pixels[:, -1]))
    background = np.median(border, axis=0)
    if np.mean(np.max(np.abs(border - background), axis=1) <= 16) < .85:
        return whole
    distance = np.max(np.abs(pixels - background), axis=2)
    if float(distance.max()) < 24:
        return whole
    ink = distance > max(16., float(distance.max()) * .18)
    ys, xs = np.nonzero(ink)
    if not len(xs):
        return whole
    glyph_height = int(ys.max() - ys.min() + 1)
    if glyph_height < 4 or width <= glyph_height * target * 1.5:
        return whole
    blank = ~ink.any(axis=0)
    edges = np.flatnonzero(np.diff(np.r_[False, blank, False].astype(int)))
    gaps = [(int((a + b) // 2), int(b - a)) for a, b in zip(edges[::2], edges[1::2])
            if a > xs.min() and b <= xs.max() and b - a >= max(2, math.ceil(glyph_height * .10))]
    parts, left, leading_gap = [], 0, 0
    while width - left > glyph_height * target * 1.5:
        choices = [(x, gap) for x, gap in gaps
                   if left + glyph_height * 3 <= x <= left + glyph_height * (target + 2)
                   and width - x >= glyph_height * 3]
        if not choices or len(parts) >= 15:
            return whole
        cut, gap = min(choices, key=lambda item: (abs(item[0] - left - glyph_height * target), -item[1], item[0]))
        parts.append((left, cut, leading_gap))
        left, leading_gap = cut, gap
    parts.append((left, width, leading_gap))
    # The width marker used when joining is derived from pixels, not expected words.
    return [(a, b, int(gap >= math.ceil(glyph_height * .25))) for a, b, gap in parts]


def read_short(module, engine, image, boxes, cancelled, base, target, evidence):
    """Keep detector boxes/layout; retry shorter pixel crops through the original reader."""
    if cancelled():
        raise module.RecognitionCancelled
    original = base(image, boxes, cancelled)
    evidence.clear()
    children, assignments = [], []
    for index, (x0, y0, x1, y1) in enumerate(boxes):
        parts = segments(image[y0:y1, x0:x1], target)
        item = {'box': [x0, y0, x1, y1], 'native_text': original[index][0],
                'native_score': float(original[index][1]), 'parts': [], 'status': 'kept_unsplit'}
        evidence.append(item)
        if len(parts) == 1:
            continue
        ids = []
        for left, right, separator in parts:
            child = [x0 + left, y0, x0 + right, y1]
            ids.append(len(children))
            children.append(child)
            item['parts'].append({'box': child, 'space_before': bool(separator)})
        assignments.append((index, ids))
    if not children:
        return original
    if cancelled():
        raise module.RecognitionCancelled
    decoded = base(image, children, cancelled)
    if len(decoded) != len(children):
        raise ValueError('짧은 구간 판독 수가 다릅니다')
    result = list(original)
    for index, ids in assignments:
        item = evidence[index]
        for part, child_id in zip(item['parts'], ids):
            part.update(text=decoded[child_id][0].strip(), score=float(decoded[child_id][1]))
        if any(not part['text'] for part in item['parts']):
            item['status'] = 'kept_empty_part'
            continue
        text = ''.join((' ' if part['space_before'] else '') + part['text'] for part in item['parts'])
        compact = lambda value: ''.join(char for char in value if not char.isspace())
        item['short_text'] = text
        if compact(text) == compact(original[index][0]):
            item['status'] = 'kept_same_letters'
            continue
        weights = [len(compact(part['text'])) for part in item['parts']]
        if not sum(weights):
            item['status'] = 'kept_empty_part'
            continue
        score = sum(part['score'] * weight for part, weight in zip(item['parts'], weights)) / sum(weights)
        result[index] = (text, score)
        item['status'] = 'used_short'
    return result
