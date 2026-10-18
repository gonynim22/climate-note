"""OCR 자원 상한·취소 회귀. 선택형 앱을 제거할 때 함께 제외한다."""
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

def test_ocr_extreme_width_and_box_count_rejected_before_resize(monkeypatch):
    import screen_text.engine as engine
    resize = Mock(side_effect=AssertionError("limit must precede allocation"))
    monkeypatch.setattr(engine, "resize_bilinear", resize)
    instance = engine.OcrEngine.__new__(engine.OcrEngine)
    image = np.zeros((2, 4000, 3), dtype=np.uint8)
    for boxes in ([(0, 0, 4000, 2)], [(0, 0, 2, 2)] * (engine.MAX_REC_BOXES + 1)):
        with pytest.raises(engine.RecognitionLimitError):
            instance._read(image, boxes, lambda: False)
    assert not resize.called


def test_ocr_batches_bounded_and_results_kept_in_original_order():
    import screen_text.engine as engine
    instance = engine.OcrEngine.__new__(engine.OcrEngine)
    batches = []
    def run(_, inputs):
        batch = inputs["x"]
        batches.append(batch.shape)
        assert batch.shape[0] * batch.shape[3] <= engine.MAX_REC_BATCH_WIDTH
        probs = np.zeros((len(batch), 1, 3), dtype=np.float32)
        for i, item in enumerate(batch):
            probs[i, 0, 1 if item[0, 0, 0] < 0 else 2] = 1
        return [probs]
    instance._rec = SimpleNamespace(run=run)
    instance._charset = ["검정", "흰색"]
    image = np.full((96, 4000, 3), 255, dtype=np.uint8)
    image[:48] = 0
    boxes = [(0, 0, 4000, 48), (0, 48, 100, 96)] * 4
    result = instance._read(image, boxes, lambda: False)
    assert [v[0] for v in result] == ["검정", "흰색"] * 4
    assert len(batches) > 1


def test_cancelled_ocr_skips_engine_and_detection(qtbot):
    from screen_text.engine import OcrEngine, RecognitionCancelled, label_components
    from screen_text.window import ScreenTextWindow
    instance = OcrEngine.__new__(OcrEngine)
    instance._detect = Mock()
    with pytest.raises(RecognitionCancelled):
        instance.recognize(np.zeros((2, 2, 3), dtype=np.uint8), lambda: True)
    assert not instance._detect.called
    with pytest.raises(RecognitionCancelled):
        label_components(np.ones((4, 4), dtype=bool), lambda: True)
    factory = Mock()
    win = ScreenTextWindow(None, engine_factory=factory, grab=lambda: [])
    qtbot.addWidget(win)
    cancelled = Event()
    cancelled.set()
    with pytest.raises(RecognitionCancelled):
        win._engine_for_work(cancelled)
    assert not factory.called
    win.shutdown()
