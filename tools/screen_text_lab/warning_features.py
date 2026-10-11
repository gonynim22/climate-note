"""정답 없이 실제 CTC 문자 점수를 읽기 순서와 불일치 위치에 연결한다."""
from collections import defaultdict
import math
import re

from .disagreement import alignment, disagreement_marks, projection


def emitted_tokens(probs, charset, decoded):
    indices = probs.argmax(axis=1).tolist()
    maximum = probs.max(axis=1).tolist()
    chars, scores, previous = [], [], 0
    for index, score in zip(indices, maximum):
        if index and index != previous:
            chars.append(charset[index - 1]); scores.append(float(score))
        previous = index
    if ''.join(chars) != decoded[0] or any(not math.isfinite(p) or not 0 <= p <= 1 for p in scores):
        raise ValueError('CTC 문자 관측이 원 판독과 다릅니다')
    return {'text': ''.join(chars), 'scores': scores}


def pack_scored(boxes, raw, tokens, scale):
    from screen_text.layout import TextBox, build_blocks, to_plain
    from .engine_adapter import pack_prediction
    real, markers, scores_by_id, texts_by_id = [], [], {}, {}
    for i, ((x0, y0, x1, y1), (text, score)) in enumerate(zip(boxes, raw)):
        if tokens[i]['text'] != text:
            raise ValueError('영역별 문자 관측 순서가 다릅니다')
        stripped = text.strip()
        if not stripped:
            continue
        coords = (round(x0 / scale), round(y0 / scale), max(1, round((x1 - x0) / scale)), max(1, round((y1 - y0) / scale)))
        real.append(TextBox(*coords, stripped, score))
        markers.append(TextBox(*coords, f'\ue000{i}\ue001', score))
        scores_by_id[i] = [p for char, p in zip(text, tokens[i]['scores']) if not char.isspace()]
        texts_by_id[i] = projection(text)[0]
    # 같은 제품 레이아웃에 영역별 고유 표식을 넣어 표/줄의 읽기 순서만 얻는다.
    # 표식은 실제 인식·원문·복사 결과에 삽입하지 않는다.
    order = [int(i) for i in re.findall(r'\ue000(\d+)\ue001', to_plain(build_blocks(markers)))]
    prediction = pack_prediction(real)
    if len(order) != len(real) or len(set(order)) != len(order) or ''.join(texts_by_id[i] for i in order) != projection(prediction['text'])[0]:
        raise ValueError('제품 줄/표와 문자 점수의 읽기 순서가 다릅니다')
    return prediction, [p for i in order for p in scores_by_id[i]]


def site_features(native, alternative, native_scores, alternative_scores):
    left, right = projection(native)[0], projection(alternative)[0]
    if len(left) != len(native_scores) or len(right) != len(alternative_scores):
        raise ValueError('문자와 점수 수가 다릅니다')
    if any(not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1 for p in native_scores + alternative_scores):
        raise ValueError('문자 점수 범위 오류')
    aligned = alignment(left, right, trace=True)
    grouped = defaultdict(list)
    for edit in aligned['edits']:
        grouped[tuple(edit['site'])].append(edit)

    def scores_for(edits, side, scores):
        selected = {i for edit in edits for i in edit[side]}
        if not selected:
            selected = {i for edit in edits for i in (edit[side + '_gap'] - 1, edit[side + '_gap']) if 0 <= i < len(scores)}
        return min((scores[i] for i in selected), default=None)

    features = []
    for mark in disagreement_marks(native, alternative)['marks']:
        edits = grouped[(mark['kind'], mark['index'])]
        a, b = scores_for(edits, 'left', native_scores), scores_for(edits, 'right', alternative_scores)
        features.append(mark | {'native_score': a, 'alternative_score': b,
                               'gain': b - a if a is not None and b is not None else None,
                               'native_uses_neighbours': not any(edit['left'] for edit in edits),
                               'alternative_uses_neighbours': not any(edit['right'] for edit in edits)})
    return {'distance': aligned['distance'], 'sites': features}


def collect_case(engine, rgb, detections, cancelled=lambda: False):
    import numpy as np
    from screen_text import engine as module
    from .recognizers import read_regions
    scale = min(module.UPSCALE, module.MAX_SIDE / max(rgb.shape[:2]))
    work = rgb if scale == 1 else np.clip(module.resize_bilinear(
        rgb, max(1, round(rgb.shape[1] * scale)), max(1, round(rgb.shape[0] * scale))), 0, 255).astype(np.uint8)
    outputs = {}
    for name, profile in (('native', 'native'), ('alternative', 'ink-light')):
        tokens, evidence = {}, []
        def observe(index, probs, charset, decoded):
            tokens[index] = emitted_tokens(probs, charset, decoded)
        raw = read_regions(module, engine, work, detections, cancelled,
                           {'format': 'paddle', 'height': module.REC_HEIGHT, 'channels': 3}, profile,
                           evidence=evidence, observer=observe)
        prediction, scores = pack_scored(detections, raw, tokens, scale)
        outputs[name] = {'prediction': prediction, 'scores': scores, 'regions': evidence}
    outputs['features'] = site_features(outputs['native']['prediction']['text'], outputs['alternative']['prediction']['text'],
                                        outputs['native']['scores'], outputs['alternative']['scores'])
    return outputs
