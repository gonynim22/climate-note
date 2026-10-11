"""실제 모델 없이 후보 수명·제품 관측·경고 비용·짝 비교를 검증한다."""
import copy
from dataclasses import asdict
from types import SimpleNamespace

import numpy as np
import pytest

from tools.screen_text_lab.diagnostic_analysis import analyze_candidates, analyze_warnings
from tools.screen_text_lab.experiments import CANDIDATES, candidate_settings, emitted_scores, observe_engine
from tools.screen_text_lab.metrics import score_case
from tools.screen_text_lab.runner import base_record


def make_record(case_id, expected, actual, score=.99, warning=0, category="unit"):
    case = {"case_id": case_id, "source_group_id": case_id, "split": "dev", "source_kind": "synthetic",
            "tags": {"category": category, "condition": "reference"}, "review_status": "generated",
            "expected": {"text": expected}}
    record = base_record(case)
    prediction = {"text": actual, "unsure_count": warning, "total_ms": 2,
                  "trace": {"version": 1, "min_char_score": score}}
    return record | {"prediction": prediction, "status": "ok", "metrics": score_case(case, prediction)}


def test_ctc_observation_uses_emitted_steps_excludes_blank_repeat_and_space():
    from screen_text.engine import ctc_decode
    probs = np.array([[.9, .04, .04, .02], [0, .8, .1, .1], [0, .7, .2, .1],
                      [.8, .1, .05, .05], [0, .1, .6, .3], [0, .1, .2, .7], [0, .9, .05, .05]])
    charset = ["가", "나", " "]
    decoded = ctc_decode(probs, charset)
    assert decoded[0] == "가나 가"
    assert emitted_scores(probs, charset, decoded[0]) == [.8, .6, .9]
    with pytest.raises(ValueError, match="디코딩"):
        emitted_scores(probs, charset, "다른 결과")
    assert emitted_scores(np.array([[.9, .1]]), ["가"], "") == []


@pytest.mark.parametrize("candidate", ("baseline", "upscale-2", "det-1600", "unclip-1.2"))
@pytest.mark.parametrize("fail", [False, True])
def test_candidate_is_scoped_and_restores_bound_defaults_and_methods(candidate, fail):
    from screen_text.engine import expand_box, ctc_decode
    module = SimpleNamespace(UPSCALE=1., DET_LIMIT=960, expand_box=expand_box, ctc_decode=ctc_decode)
    class Engine:
        def _detect(self, image):
            return [(1, 2, 3, 4)]
        def _read(self, image, boxes, cancelled):
            return [module.ctc_decode(np.array([[.1, .9]]), ["가"])]
    engine = Engine()
    before = vars(module).copy()
    try:
        with observe_engine(module, engine, candidate) as trace:
            settings = candidate_settings(candidate)
            assert module.UPSCALE == settings.get("UPSCALE", 1.)
            assert module.DET_LIMIT == settings.get("DET_LIMIT", 960)
            assert module.expand_box(0, 0, 10, 10) == expand_box(0, 0, 10, 10, settings.get("unclip_ratio", 1.5))
            image = np.zeros((10, 20, 3), dtype=np.uint8)
            boxes = engine._detect(image)
            assert engine._read(image, boxes, lambda: False) == [("가", .9)]
            if fail:
                raise RuntimeError("intentional cancellation")
    except RuntimeError as error:
        assert fail and str(error) == "intentional cancellation"
    assert vars(module) == before
    assert "_detect" not in vars(engine) and "_read" not in vars(engine)
    if not fail:
        assert trace["min_char_score"] == .9 and trace["nonspace_emitted_chars"] == 1
        assert trace["detected_boxes"] == 1 and trace["decoded_segments"] == 1
        assert trace["work_image_size"] == [20, 10]


def test_adapter_observation_preserves_actual_product_pipeline_with_fake_sessions(tmp_path):
    from PIL import Image
    from screen_text import engine as module
    from screen_text.layout import build_blocks, plain_with_spans, to_tsv, to_html, unsure_count
    from tools.screen_text_lab.engine_adapter import ProductEngine
    engine = object.__new__(module.OcrEngine)  # 세션 생성/모델 읽기를 하지 않는다.
    class Detector:
        def run(self, _, values):
            h, w = values["x"].shape[2:]
            probs = np.zeros((1, 1, h, w), dtype=np.float32)
            probs[0, 0, 10:18, 10:50] = .99
            return [probs]
    class Reader:
        def run(self, _, values):
            return [np.tile(np.array([[[.1, .9, 0], [.1, .9, 0], [.9, .1, 0], [.2, 0, .8]]]),
                            (values["x"].shape[0], 1, 1))]
    engine._det, engine._rec, engine._charset = Detector(), Reader(), ["가", "나"]
    pixels = np.full((48, 120, 3), 255, dtype=np.uint8)
    path = tmp_path / "synthetic.png"
    Image.fromarray(pixels).save(path)
    boxes = engine.recognize(pixels)
    blocks = build_blocks(boxes)
    adapter = object.__new__(ProductEngine)
    adapter.engine, adapter.candidate = engine, "baseline"
    observed = adapter.recognize(path)
    assert observed["boxes"] == [asdict(box) for box in boxes]
    assert (observed["text"], observed["spans_utf16"]) == plain_with_spans(blocks)
    assert observed["tsv"] == to_tsv(blocks) and observed["html"] == to_html(blocks)
    assert observed["unsure_count"] == unsure_count(blocks)
    assert observed["trace"]["min_char_score"] == .8
    assert engine.recognize(pixels) == boxes


def test_candidate_validation_and_cli_keep_explicit_allowlist():
    from tools.screen_text_lab.__main__ import parser
    for name in CANDIDATES:
        args = parser().parse_args(["run", "--corpus", "unused", "--candidate", name])
        assert args.candidate == name
    with pytest.raises(ValueError):
        candidate_settings("arbitrary-loader")
    with pytest.raises(ValueError):
        from tools.screen_text_lab.runner import run
        run("does-not-exist", candidate="arbitrary-loader")


def test_warning_matrix_counts_false_alarms_missing_observation_and_blank_output():
    records = [make_record("correct", "가", "가", .6), make_record("wrong", "가", "나", .6),
               make_record("confident", "가", "나", .99), make_record("spaces", "가 나", "가나", .99),
               make_record("missing", "가", "", None), make_record("already", "가", "나", .99, 1)]
    old = make_record("old", "가", "가")
    old["prediction"].pop("trace")
    records.append(old)
    records.append(make_record("failed", "가", "가") | {"status": "error"})
    records.append(make_record("unscored", "가", "가") | {"metrics": None})
    before = copy.deepcopy(records)
    result = analyze_warnings(records)
    assert result["cases"] == 6 and result["scored"] == 7
    assert result["excluded_missing_trace"] == 1 and result["excluded_unscored_or_failed"] == 2
    row = result["scopes"]["no_space_text"][2]  # .7
    assert row["threshold"] == .7
    assert [row[key] for key in ("true_positive", "false_negative", "false_positive", "true_negative")] == [2, 2, 1, 1]
    assert row["precision"] == 2 / 3 and row["recall"] == .5 and row["added_warnings"] == 2
    strict = result["scopes"]["strict_all"][2]
    assert strict["false_negative"] == 3 and strict["true_negative"] == 0
    assert records == before
    assert analyze_warnings([old]) is None


def test_warning_matrix_excludes_scores_of_rejected_alternatives():
    record=make_record('retry','가','가')
    record['prediction']['trace']['score_scope']='all_hypotheses'
    assert analyze_warnings([record]) is None


def test_paired_analysis_exposes_new_errors_recovery_and_failed_pair_denominator():
    left = [make_record("new", "가", "가"), make_record("fixed", "가 나", "다나"),
            make_record("fail", "가", "나")]
    right = [make_record("new", "가", "나"), make_record("fixed", "가 나", "가나"),
             make_record("fail", "가", "가") | {"status": "error"}]
    result = analyze_candidates(left, right)
    paired = result["overall"]
    assert paired["pairs"] == 2 and paired["excluded"] == 1
    assert paired["changes"]["no_space_new_wrong"] == 1
    assert paired["changes"]["no_space_recovered"] == 1
    assert paired["changes"]["new_wrong"] == 1 and paired["changes"]["recovered"] == 0
    assert paired["regression_examples"] == [{"case_id": "new", "extra_errors": 1, "was_correct": True}]
    assert paired["baseline"]["no_space_errors"] == paired["candidate"]["no_space_errors"] == 1
    assert paired["median_time_ratio"] == 1
    with pytest.raises(ValueError):
        analyze_candidates(left, list(reversed(right)))


def test_diagnostic_html_keeps_scope_false_alarms_and_escapes_labels():
    from tools.screen_text_lab.report import candidate_panel, warning_panel
    left = [make_record("sample", "가", "가", .6, category="<script>")]
    right = [make_record("sample", "가", "나", .6, category="<script>")]
    html = candidate_panel(analyze_candidates(left, right))
    assert "&lt;script&gt;" in html and "<script>" not in html
    assert "복구 / 신규 오류" in html
    html = warning_panel(analyze_warnings(left))
    assert "정상에 경고" in html and "출력된 비공백" in html
    assert "사례 단위 모의 판정" in html and "표 구조 오류도 제외" in html
