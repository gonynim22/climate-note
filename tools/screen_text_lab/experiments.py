"""명시적 실험 설정과 제품 함수 관측. runtime import는 호출할 때만 한다."""
from contextlib import contextmanager
from time import perf_counter


CANDIDATES = ("baseline", "upscale-2", "det-1600", "unclip-1.2", "det-aspect",
              "rec-320", "rec-light", "rec-ink", "rec-ink-native", "det-ink-native", "rec-selective", "rec-selective-stable",
              "rec-short-6", "rec-short-10")


def candidate_settings(name):
    settings = {"baseline": {}, "upscale-2": {"UPSCALE": 2.0},
                "det-1600": {"DET_LIMIT": 1600}, "unclip-1.2": {"unclip_ratio": 1.2},
                "det-aspect": {"detect": "aspect"},
                "rec-ink-native": {"read": "rec-ink-native"},
                "det-ink-native": {"detect": "aspect", "read": "rec-ink-native"},
                "rec-selective": {"read": "selective", "retry_below": .97, "accept_margin": .02},
                "rec-selective-stable": {"read": "selective", "retry_below": .97, "accept_margin": .02, "preserve_spaces": True},
                "rec-short-6": {"read": "short", "target_height_ratio": 6},
                "rec-short-10": {"read": "short", "target_height_ratio": 10},
                **{name: {"read": name} for name in ("rec-320", "rec-light", "rec-ink")}}
    if name not in settings:
        raise ValueError(f"지원하지 않는 진단 후보: {name}")
    return dict(settings[name])


def emitted_scores(probs, charset, decoded_text):
    """제품 디코더 결과를 바꾸지 않고 같은 CTC 출력의 비공백 점수만 관측한다."""
    import numpy as np
    indices = probs.argmax(axis=1)
    maximum = probs.max(axis=1)
    previous, chars, scores = -1, [], []
    for index, score in zip(indices, maximum):
        index = int(index)
        if index != 0 and index != previous and index <= len(charset):
            char = charset[index - 1]
            chars.append(char)
            if not char.isspace():
                scores.append(float(score))
        previous = index
    if "".join(chars) != decoded_text:
        raise ValueError("문자 점수 관측이 실제 제품 디코딩 결과와 다릅니다")
    if any(not np.isfinite(score) or not 0 <= score <= 1 for score in scores):
        raise ValueError("문자 점수가 유효 범위를 벗어났습니다")
    return scores


@contextmanager
def observe_engine(module, engine, candidate, capture_boxes=False):
    """한 worker의 직렬 호출 전용. 원본 메서드/상수를 예외·취소 때도 복원한다."""
    settings = candidate_settings(candidate)
    trace = {"version": 1, "candidate": candidate, "settings": settings,
             "detect_ms": None, "read_ms": None, "detected_boxes": 0, "decoded_segments": 0}
    saved_module = {}
    saved_methods = {}
    missing = object()
    scores = []

    def replace(name, value):
        saved_module[name] = getattr(module, name)
        setattr(module, name, value)

    try:
        for name in ("UPSCALE", "DET_LIMIT"):
            if name in settings:
                replace(name, settings[name])
        if "unclip_ratio" in settings:
            expand = module.expand_box
            # 제품 expand_box의 기본 인자는 정의 시 바인딩되어 상수 교체만으로 바뀌지 않는다.
            def expanded(x0, y0, x1, y1):
                return expand(x0, y0, x1, y1, ratio=settings["unclip_ratio"])
            replace("expand_box", expanded)
        decode = module.ctc_decode
        def decoded(probs, charset):
            result = decode(probs, charset)
            scores.extend(emitted_scores(probs, charset, result[0]))
            trace["decoded_segments"] += 1
            return result
        replace("ctc_decode", decoded)

        for name, key in (("_detect", "detect_ms"), ("_read", "read_ms")):
            original = getattr(engine, name)
            saved_methods[name] = engine.__dict__.get(name, missing)
            if name == "_detect" and settings.get("detect") == "aspect":
                from .preprocessing import detect_aspect
                original = lambda image, cancelled=lambda: False, limit=None: detect_aspect(module, engine, image, cancelled)
            if name == "_read" and "read" in settings:
                from .preprocessing import read_padded, read_selective
                if settings["read"] == "selective":
                    original = lambda image, boxes, cancelled, _base=original: read_selective(module, engine, image, boxes, cancelled, _base, settings.get("preserve_spaces", False))
                elif settings["read"] == "short":
                    from .short_regions import read_short
                    trace['short_regions'] = []
                    original = lambda image, boxes, cancelled, _base=original: read_short(
                        module, engine, image, boxes, cancelled, _base, settings['target_height_ratio'], trace['short_regions'])
                else:
                    original = lambda image, boxes, cancelled: read_padded(module, engine, image, boxes, cancelled, settings["read"])
            def timed(*args, _original=original, _key=key, **kwargs):
                started = perf_counter()
                output = _original(*args, **kwargs)
                trace[_key] = (perf_counter() - started) * 1000
                if _key == "detect_ms":
                    trace["work_image_size"] = [int(args[0].shape[1]), int(args[0].shape[0])]
                    trace["detected_boxes"] = len(output)
                    if capture_boxes or settings.get('read') == 'short':
                        trace["detection_boxes"] = [list(box) for box in output]
                return output
            setattr(engine, name, timed)
        yield trace
        trace["nonspace_emitted_chars"] = len(scores)
        trace["min_char_score"] = min(scores) if scores else None
        trace["score_scope"] = "all_hypotheses" if trace["decoded_segments"] > trace["detected_boxes"] else "final"
    finally:
        for name, value in saved_methods.items():
            if value is missing:
                delattr(engine, name)
            else:
                setattr(engine, name, value)
        for name, value in saved_module.items():
            setattr(module, name, value)
