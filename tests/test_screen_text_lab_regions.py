"""영역 주석 직접 인식과 단계 채점의 작은 자체 검사. 모델 세션 생성 없음."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

from tools.screen_text_lab.engine_adapter import ProductEngine, pack_prediction
from tools.screen_text_lab.region_diagnostics import diagnose_regions, geometry, summarize_regions, union_area
from tools.screen_text_lab.metrics import score_case
from tools.screen_text_lab.runner import base_record


def example_case():
    return {"case_id": "two-regions", "source_group_id": "sample", "source_kind": "synthetic", "split": "dev",
            "review_status": "generated", "tags": {"condition": "reference", "category": "unit"},
            "expected": {"text": "가 나"}, "image_size": [30, 20],
            "regions": [{"box": [0, 1, 10, 12], "text": "가"}, {"box": [15, 1, 29, 12], "text": "나"}]}


def make_diagnosis(case=None):
    case = case or example_case()
    class Reader:
        calls = []
        def _read(self, image, boxes, cancelled):
            self.calls.append(copy.deepcopy(boxes))
            assert not cancelled() and image.shape == (20, 30, 3)
            return [("가", .9), ("나" if len(self.calls) == 1 else "다", .95)]
    reader = Reader()
    result = diagnose_regions(reader, np.zeros((20, 30, 3), dtype=np.uint8), case,
                              [[1, 1, 11, 12], [15, 1, 29, 12]], pack_prediction)
    return result, reader


def test_rectangle_union_coverage_and_overlap_are_not_double_counted():
    assert union_area([[0, 0, 6, 10], [4, 0, 10, 10], [0, 0, 6, 10]]) == 100
    result = geometry([{"box": [0, 0, 10, 10]}], [[0, 0, 6, 10], [4, 0, 10, 10], [0, 0, 6, 10], [20, 20, 22, 22]])
    assert result["regions"][0]["coverage"] == 1
    assert result["regions"][0]["best_iou"] == .6
    assert result["regions"][0]["height_ratio"] == 1
    assert result["multi_detection_regions"] == 1 and result["unmatched_detections"] == 1
    assert result["large_overlap_pairs"] == [[0, 2]] and result["small_detections"] == 1
    merged = geometry([{"box": [0, 0, 10, 10]}, {"box": [10, 0, 20, 10]}], [[0, 0, 20, 10]])
    assert merged["multi_region_detections"] == 1
    empty = geometry([{"box": [0, 0, 10, 10]}], [])
    assert empty["low_coverage_regions"] == 1 and empty["regions"][0]["height_ratio"] is None


def test_direct_read_uses_only_coordinates_and_padding_clips_to_source():
    case = example_case()
    before = copy.deepcopy(case)
    result, reader = make_diagnosis(case)
    assert reader.calls == [[[0, 1, 10, 12], [15, 1, 29, 12]], [[0, 0, 12, 14], [13, 0, 30, 14]]]
    assert case == before and result["status"] == "ok"
    first, second = result["variants"]
    assert first["ordered_no_space"]["errors"] == 0
    assert second["ordered_no_space"]["errors"] == 1
    assert second["regions"][1]["no_space"]["errors"] == 1
    assert first["prediction"]["text"] == "가 나"
    assert result["total_ms"] >= sum(variant["read_ms"] for variant in result["variants"])


@pytest.mark.parametrize("change,status", [("empty", "missing_annotations"), ("unreviewed", "unreviewed"),
    ("text", "missing_region_text"), ("partial", "incomplete_annotations"), ("order", "incomplete_annotations"),
    ("large_image", "input_resized"), ("many_regions", "size_limit"), ("many_detections", "size_limit")])
def test_ineligible_inputs_are_explicitly_excluded_without_extra_inference(change, status):
    case = example_case()
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    detections = []
    if change == "empty":
        case["regions"] = []
    elif change == "unreviewed":
        case["review_status"] = "unreviewed"
    elif change == "text":
        case["regions"][0].pop("text")
    elif change == "partial":
        case["regions"].pop()
    elif change == "order":
        case["regions"].reverse()
    elif change == "large_image":
        image = np.zeros((1, 4001, 3), dtype=np.uint8)
    elif change == "many_regions":
        case["regions"] *= 129
    else:
        detections = [[0, 0, 1, 1]] * 513
    class NoReader:
        def _read(self, *args):
            pytest.fail("제외된 자료를 인식하면 안 됩니다")
    assert diagnose_regions(NoReader(), image, case, detections, pack_prediction)["status"] == status


def test_adapter_keeps_baseline_prediction_and_time_separate_from_extra_calls(tmp_path):
    from PIL import Image
    from screen_text.engine import OcrEngine
    engine = object.__new__(OcrEngine)
    engine._detect = lambda image, cancelled=lambda: False: [[0, 1, 10, 12], [15, 1, 29, 12]]
    calls = []
    def read(image, boxes, cancelled):
        calls.append(copy.deepcopy(boxes))
        return [("가", .9), ("나", .95)]
    engine._read = read
    adapter = object.__new__(ProductEngine)
    adapter.engine, adapter.candidate = engine, "baseline"
    path = tmp_path / "case.png"
    Image.new("RGB", (30, 20), "white").save(path)
    normal = adapter.recognize(path)
    assert len(calls) == 1 and "region_diagnostic" not in normal
    diagnostic = adapter.recognize(path, region_case=example_case())
    assert len(calls) == 4 and diagnostic["region_diagnostic"]["status"] == "ok"
    for key in ("text", "table", "tsv", "html", "boxes", "blocks", "unsure_count", "spans_utf16"):
        assert normal[key] == diagnostic[key]
    assert diagnostic["trace"]["detection_boxes"] == [[0, 1, 10, 12], [15, 1, 29, 12]]
    assert engine._read is read
    # 첫 제품 결과 후 추가 호출만 실패해도 제품 결과는 남아야 한다.
    def fail_extra(image, boxes, cancelled):
        if len(calls) > 4:
            raise RuntimeError("extra diagnosis failed")
        return read(image, boxes, cancelled)
    engine._read = fail_extra
    failed = adapter.recognize(path, region_case=example_case())
    assert failed["text"] == normal["text"]
    assert failed["region_diagnostic"]["status"] == "error"
    assert failed["region_diagnostic"]["error_type"] == "RuntimeError"


def test_summary_preserves_excluded_and_failed_denominators():
    case = example_case()
    stage, _ = make_diagnosis(case)
    prediction = {"text": "가 다", "unsure_count": 0, "region_diagnostic": stage}
    record = base_record(case) | {"status": "ok", "prediction": prediction, "metrics": score_case(case, prediction)}
    excluded = copy.deepcopy(record)
    excluded["prediction"]["region_diagnostic"] = {"status": "missing_annotations"}
    failed = base_record(case) | {"status": "error"}
    result = summarize_regions([record, excluded, failed])
    assert result["eligible"] == 1 and result["excluded"] == 2 and result["observed"] == 2
    first, second = result["overall"]["variants"]
    assert first["case_changes"]["recovered"] == 1 and second["case_changes"]["both_wrong"] == 1
    assert first["regions_exact"] == 2 and second["region_errors"] == 1
    assert result["overall"]["baseline_cer"] == .5
    assert result["overall"]["geometry"]["regions"] == 2
    assert summarize_regions([failed]) is None


def test_regions_hash_and_text_are_checked_when_comparing(tmp_path):
    from tools.screen_text_lab.compare import pair_records
    from tools.screen_text_lab.corpus import CorpusError, digest, load_corpus
    from PIL import Image
    case = example_case()
    stage, _ = make_diagnosis(case)
    prediction = {"text": "가 나", "unsure_count": 0, "region_diagnostic": stage}
    record = base_record(case) | {"status": "ok", "prediction": prediction, "metrics": score_case(case, prediction)}
    changed = copy.deepcopy(record)
    changed["regions"][0]["text"] = "다"
    with pytest.raises(ValueError, match="주석 해시"):
        pair_records([record], [changed])
    image = tmp_path / "sample.png"
    Image.new("RGB", (30, 20), "white").save(image)
    case.update(image=image.name, image_sha256=digest(image))
    case["regions"][0]["text"] = 42
    (tmp_path / "manifest.json").write_text(json.dumps({"schema_version": 1, "dataset_id": "sample", "cases": [case]}), encoding="utf-8")
    with pytest.raises(CorpusError, match="영역 정답"):
        load_corpus(tmp_path)


def test_cli_requires_explicit_baseline_flag_and_reports_escape_text(tmp_path):
    from tools.screen_text_lab.__main__ import parser
    from tools.screen_text_lab.runner import run
    from tools.screen_text_lab.region_report import case_panel, analysis_panel
    args = parser().parse_args(["run", "--corpus", "unused"])
    assert not args.diagnose_regions
    assert parser().parse_args(["run", "--corpus", "unused", "--diagnose-regions"]).diagnose_regions
    with pytest.raises(ValueError, match="baseline"):
        run("unused", candidate="upscale-2", diagnose_regions=True)
    case = example_case()
    stage, _ = make_diagnosis(case)
    prediction = {"text": "가 나", "unsure_count": 0, "region_diagnostic": stage}
    record = base_record(case) | {"status": "ok", "prediction": prediction, "metrics": score_case(case, prediction)}
    stage["variants"][0]["prediction"]["text"] = "<script>unsafe</script>"
    html = case_panel(record)
    assert "&lt;script&gt;" in html and "<script>" not in html
    assert "주석 순서" in html and "확정 누락/중복 판정이 아닙니다" in html
    assert "비교 1/1개" in analysis_panel(summarize_regions([record]))
    from tools.screen_text_lab.report import render_case
    from PIL import Image
    (tmp_path / "cases").mkdir()
    Image.new("RGB", (30, 20), "white").save(tmp_path / "cases" / (record["case_id"] + ".png"))
    render_case(tmp_path, record)
    page = (tmp_path / "cases" / (record["case_id"] + ".html")).read_text(encoding="utf-8")
    assert "파란 점선은 정답 주석 영역" in page and "stroke:#2563eb" in page
    assert "&lt;script&gt;" in page and "<script>unsafe" not in page
