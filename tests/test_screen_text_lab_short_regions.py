"""짧은 구간 후보의 픽셀 보존·정답 비의존·결합·수명 검사. 실제 모델 없음."""
from types import SimpleNamespace
import numpy as np
import pytest

from tools.screen_text_lab.short_regions import segments, read_short


def line():
    image = np.full((20, 360, 3), 250, np.uint8)
    for x in range(4, 355, 16):
        image[4:16, x:x + 9] = 20
    return image


@pytest.mark.parametrize('target', [6, 10])
@pytest.mark.parametrize('dark', [False, True])
def test_split_only_blank_columns_complete_unmodified_pixel_partition(target, dark):
    image = line()
    if dark:
        image = 255 - image
    saved = image.copy()
    parts = segments(image, target)
    assert 1 < len(parts) <= 16
    assert parts[0][0] == 0 and parts[-1][1] == image.shape[1]
    assert all(a[1] == b[0] for a, b in zip(parts, parts[1:]))
    for _, cut, _ in parts[:-1]:
        assert np.all(image[:, cut] == image[0, 0])
    assert np.array_equal(np.concatenate([image[:, a:b] for a, b, _ in parts], axis=1), saved)
    assert np.array_equal(image, saved)


def test_short_blank_complex_unbroken_and_limit_use_whole_region():
    for image in (line()[:, :50], np.full((20, 360, 3), 250, np.uint8),
                  np.random.default_rng(4).integers(0, 256, (20, 360, 3), dtype=np.uint8)):
        assert segments(image, 6) == [(0, image.shape[1], 0)]
    solid = line(); solid[4:16, 4:356] = 20
    assert segments(solid, 6) == [(0, 360, 0)]
    long = np.tile(line(), (1, 20, 1))
    assert segments(long, 6) == [(0, 7200, 0)]


@pytest.mark.parametrize('mode', ['same', 'changed', 'empty'])
def test_retry_preserves_original_spaces_or_keeps_safe_fallback(mode):
    image = line(); saved = image.copy(); parts = segments(image, 6)
    tokens = ['가'] * len(parts)
    original = ('  '.join(tokens), .91)
    calls, evidence = [], []
    def base(pixels, boxes, cancelled):
        assert pixels is image
        calls.append(boxes)
        if len(calls) == 1:
            return [original]
        changed = tokens.copy()
        if mode == 'changed': changed[1] = '나'
        if mode == 'empty': changed[1] = ''
        return [(text, .8) for text in changed]
    got = read_short(SimpleNamespace(), None, image, [[0, 0, 360, 20]], lambda: False, base, 6, evidence)
    assert len(calls) == 2 and len(calls[1]) == len(parts)
    if mode == 'changed':
        assert '나' in got[0][0] and got[0][1] == pytest.approx(.8)
        assert evidence[0]['status'] == 'used_short'
    else:
        assert got == [original]
        assert evidence[0]['status'] == ('kept_same_letters' if mode == 'same' else 'kept_empty_part')
    assert np.array_equal(image, saved)


@pytest.mark.parametrize('outcome', ['ok', 'error', 'cancel'])
def test_observer_restores_methods_and_constants(outcome):
    from screen_text import engine as module
    from tools.screen_text_lab.experiments import observe_engine
    image = line(); count = 0
    def base(pixels, boxes, cancelled):
        nonlocal count
        count += 1
        if count == 2 and outcome == 'error': raise RuntimeError('read failed')
        return [('가', .9)] * len(boxes)
    engine = SimpleNamespace(_read=base, _detect=lambda image: [[0, 0, 360, 20]])
    original_read, original_detect, original_decode = engine._read, engine._detect, module.ctc_decode
    expected = RuntimeError if outcome == 'error' else module.RecognitionCancelled
    def invoke():
        with observe_engine(module, engine, 'rec-short-6') as trace:
            boxes = engine._detect(image)
            engine._read(image, boxes, lambda: outcome == 'cancel' and count >= 1)
        assert trace['short_regions'] and trace['detection_boxes'] == [[0, 0, 360, 20]]
    if outcome == 'ok': invoke()
    else:
        with pytest.raises(expected): invoke()
    assert engine._read is original_read and engine._detect is original_detect
    assert module.ctc_decode is original_decode
