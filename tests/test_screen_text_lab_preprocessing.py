"""고정 픽셀 전처리와 수명 검증. 실제 모델 세션은 만들지 않는다."""
import numpy as np
import pytest

from tools.screen_text_lab.experiments import observe_engine
from tools.screen_text_lab.preprocessing import normalize_crop


def test_crop_preserves_input_polarity_and_punctuation_bounds():
    crop = np.full((24, 100, 3), 20, dtype=np.uint8)
    crop[8:16, 10:75] = 220
    crop[15, 80:82] = 180  # 작은 문장부호도 경계에 포함
    original = crop.copy()
    light = normalize_crop(crop, "rec-light")
    assert np.array_equal(light, 255-crop)
    ink = normalize_crop(crop, "rec-ink")
    assert ink.shape == (12, 76, 3)
    assert np.all(ink[:2] == 235)
    assert np.all(ink[9, 72:74] == 75)
    assert np.array_equal(crop, original)
    assert normalize_crop(crop, "rec-320") is crop


def test_blank_low_contrast_and_complex_background_are_not_normalized():
    blank = np.full((24, 100, 3), 20, dtype=np.uint8)
    faint = blank.copy()
    faint[8:16, 10:80] = 40
    striped = blank.copy()
    striped[:, ::2] = 220
    for crop in (blank, faint, striped):
        for mode in ("rec-ink", "rec-light"):
            assert normalize_crop(crop, mode) is crop


@pytest.mark.parametrize("candidate", ["det-aspect", "rec-320", "rec-light", "rec-ink", "rec-ink-native", "det-ink-native", "rec-selective"])
def test_new_candidates_restore_methods_and_cancel_without_rec_session(candidate):
    from screen_text import engine as module
    engine = object.__new__(module.OcrEngine)
    saved_decode = module.ctc_decode
    with pytest.raises(module.RecognitionCancelled):
        with observe_engine(module, engine, candidate):
            engine._read(np.full((30, 50, 3), 255, dtype=np.uint8), [(0, 0, 50, 30)], lambda: True)
    assert "_read" not in vars(engine) and "_detect" not in vars(engine)
    assert module.ctc_decode is saved_decode


def test_rec320_keeps_end_steps_and_zero_padded_minimum_width():
    from screen_text import engine as module
    engine = object.__new__(module.OcrEngine)
    engine._charset = ["가", "나"]
    seen = []
    class Reader:
        def run(self, _, values):
            seen.append(values["x"].copy())
            probs = np.zeros((2, 80, 3), dtype=np.float32)
            probs[:, :, 0] = 1
            probs[:, 0] = [0, 1, 0]
            probs[:, -1] = [0, 0, 1]
            return [probs]
    engine._rec = Reader()
    pixels = np.full((48, 100, 3), 255, dtype=np.uint8)
    with observe_engine(module, engine, "rec-320") as trace:
        result = engine._read(pixels, [(0, 0, 24, 48), (0, 0, 100, 48)], lambda: False)
    assert result == [("가나", 1.), ("가나", 1.)]
    assert seen[0].shape == (2, 3, 48, 320)
    assert np.all(seen[0][0, :, :, :24] == 1)
    assert np.all(seen[0][0, :, :, 24:] == 0)
    assert trace["nonspace_emitted_chars"] == 4


def test_detector_keeps_aspect_and_discards_padding_detections():
    from screen_text import engine as module
    engine = object.__new__(module.OcrEngine)
    seen = []
    class Detector:
        def run(self, _, values):
            seen.append(values["x"].copy())
            h, w = values["x"].shape[2:]
            prob = np.zeros((1, 1, h, w), dtype=np.float32)
            prob[0, 0, 2:6, 20:40] = 1
            prob[0, 0, 24:28, 800:820] = 1  # 아래 패딩에서 나온 잡음
            return [prob]
    engine._det = Detector()
    image = np.full((20, 1600, 3), 180, dtype=np.uint8)
    with observe_engine(module, engine, "det-aspect"):
        boxes = engine._detect(image)
    assert seen[0].shape == (1, 3, 32, 960)
    assert len(boxes) == 1
    x0, y0, x1, y1 = boxes[0]
    assert 0 <= x0 < x1 <= 1600 and 0 <= y0 < y1 <= 20


def test_native_ink_rejects_tiny_ink_and_excessive_recognition_width():
    for h in (1, 4):
        crop = np.full((100, 500, 3), 255, dtype=np.uint8)
        crop[50:50+h, 10:490] = 0
        assert normalize_crop(crop, "rec-ink-native") is crop


def test_native_ink_keeps_original_width_padding_and_step_truncation():
    from screen_text import engine as module
    engine = object.__new__(module.OcrEngine)
    engine._charset = ["가", "나"]
    seen=[]
    class Reader:
        def run(self, _, values):
            seen.append(values['x'].shape)
            probs = np.zeros((2, 25, 3), dtype=np.float32)
            probs[:, :, 0]=1
            probs[:, 0]=[0,1,0]
            probs[:, -1]=[0,0,1]
            return [probs]
    engine._rec=Reader()
    pixels=np.full((48,100,3),255,dtype=np.uint8)
    with observe_engine(module,engine,'rec-ink-native'):
        result=engine._read(pixels,[(0,0,24,48),(0,0,100,48)],lambda:False)
    assert result==[('가',1.),('가나',1.)]
    assert seen==[(2,3,48,100)]


def test_selective_retries_only_low_scores_and_requires_gain_and_nonempty_output(monkeypatch):
    from tools.screen_text_lab import preprocessing
    pixels=np.full((24,100,3),255,dtype=np.uint8)
    pixels[8:16,10:80]=0
    boxes=[(0,0,100,24)]*4
    first=[('유지',.99),('원본',.90),('원본',.94),('원본',.93)]
    calls=[]
    def alternatives(module,engine,image,selected,cancelled,mode):
        calls.append(len(selected))
        return [('대안',.96),('미달',.95),(' ',.99)]
    monkeypatch.setattr(preprocessing,'read_padded',alternatives)
    result=preprocessing.read_selective(None,None,pixels,boxes,lambda:False,lambda *args:list(first))
    assert calls==[3]
    assert result==[('유지',.99),('대안',.96),('원본',.94),('원본',.93)]
    blank=np.full_like(pixels,255)
    preprocessing.read_selective(None,None,blank,boxes,lambda:False,lambda *args:list(first))
    assert calls==[3]


def test_stable_retry_preserves_original_spacing_and_score_when_letters_agree(monkeypatch):
    from tools.screen_text_lab import preprocessing
    pixels=np.full((24,100,3),255,dtype=np.uint8)
    pixels[8:16,10:80]=0
    monkeypatch.setattr(preprocessing,'read_padded',lambda *args: [('가나다',.99)])
    result=preprocessing.read_selective(None,None,pixels,[(0,0,100,24)],lambda:False,
                                      lambda *args:[('가 나 다',.94)],preserve_spaces=True)
    assert result==[('가 나 다',.94)]
