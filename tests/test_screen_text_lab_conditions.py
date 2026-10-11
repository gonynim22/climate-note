"""조건 계획은 메타데이터로, 렌더는 작은 표본으로 검사. 실제 OCR/대량 생성 없음."""
from collections import Counter
from copy import deepcopy

import pytest

from tools.screen_text_lab.conditions import CONDITIONS, PROFILE, render_corpus, specimens
from tools.screen_text_lab.condition_analysis import analyze_conditions
from tools.screen_text_lab.corpus import digest, json_hash, load_corpus, read_json
from tools.screen_text_lab.metrics import score_case
from tools.screen_text_lab.runner import base_record, save_run


def test_coverage_and_previously_used_text_never_enters_holdout():
    from pathlib import Path
    sources = specimens()
    assert len(sources) == 200
    assert Counter(source["category"] for source in sources) == {category: 20 for category in
        ("body", "batchim", "cli", "mixed", "numbers", "dates", "document", "symbols", "interface", "table")}
    assert Counter(source["split"] for source in sources) == {"dev": 160, "holdout": 40}
    assert len({source["expected"]["text"] for source in sources}) == 200
    assert len({source["id"] for source in sources}) == 200
    old = read_json(Path(__file__).resolve().parents[1] / "tools/screen_text_lab/recipes/bootstrap.json")
    dev_text = {source["expected"]["text"] for source in sources if source["split"] == "dev"}
    assert all(text in dev_text for values in old.values() for text in values)
    assert len(CONDITIONS) == 12 and len({condition["id"] for condition in CONDITIONS}) == 12


def test_small_render_preserves_parent_truth_split_and_pixel_hash(qapp, tmp_path):
    text = specimens()[0]
    table = next(source for source in specimens() if source["id"] == "cond-table-010")
    directory = render_corpus([text, table], [CONDITIONS[0], CONDITIONS[1], CONDITIONS[7]], tmp_path, 17)
    corpus = load_corpus(directory)
    assert len(corpus.cases) == 6
    assert sum(case["parent_id"] is None for case in corpus.cases) == 2
    by_id = {case["case_id"]: case for case in corpus.cases}
    for case in corpus.cases:
        assert digest(directory / case["image"]) == case["image_sha256"]
        assert not case["provenance"]["actual_screen_capture"]
        assert case["tags"]["profile"] == PROFILE
        if case["parent_id"]:
            parent = by_id[case["parent_id"]]
            assert case["expected"] == parent["expected"]
            assert case["source_group_id"] == parent["source_group_id"]
            assert case["split"] == parent["split"]
            assert case["image_sha256"] != parent["image_sha256"]
    table_case = by_id[table["id"]]
    assert table_case["expected"]["table"][2][1] == ""
    assert "중류 미측정" in table_case["expected"]["text"]  # 빈 셀은 표에 보존, 문자 탭은 빈 셀을 건너뜀
    assert len(table_case["regions"]) == 11


def test_condition_pixels_and_dimensions_are_real_changes(qapp, tmp_path):
    from PIL import Image
    source = {"id": "unit", "category": "body", "split": "dev", "ruled": False,
              "expected": {"text": "작은 글자 확인\n두 번째 줄"}}
    corpus = load_corpus(render_corpus([source], CONDITIONS, tmp_path, 1))
    by_condition = {case["tags"]["condition"]: case for case in corpus.cases}
    for name, case in by_condition.items():
        with Image.open(corpus.directory / case["image"]) as image:
            corner = image.convert("RGB").getpixel((0, 0))
            assert corner == ((23, 28, 37) if name == "dark" else (255, 255, 255))
            assert image.getextrema()[0][0] < image.getextrema()[0][1]
    assert by_condition["wide"]["image_size"][0] == 1600
    assert by_condition["scale125"]["image_size"][1] > by_condition["reference"]["image_size"][1]
    assert by_condition["scale150"]["image_size"][1] > by_condition["scale125"]["image_size"][1]
    assert by_condition["dense"]["image_size"][1] < by_condition["reference"]["image_size"][1]


def record(original, condition, actual, status="ok"):
    case = {"case_id": original if condition == "reference" else original + "--" + condition,
            "parent_id": None if condition == "reference" else original,
            "source_group_id": original, "source_kind": "synthetic", "split": "dev",
            "review_status": "generated", "image_size": [12, 12], "image_sha256": "a" * 64,
            "expected": {"text": "가 나"}, "tags": {"category": "body", "profile": PROFILE, "condition": condition}}
    result = base_record(case)
    result["status"] = status
    if status == "ok":
        prediction = {"text": actual, "table": [], "boxes": [], "unsure_count": 0, "total_ms": 1}
        result.update(prediction=prediction, metrics=score_case(case, prediction))
    return result


def test_paired_cer_excludes_unpaired_and_keeps_failure_counts():
    records = [record("a", "reference", "가 나"), record("a", "font10", "가 다"),
               record("b", "reference", "가 나"), record("b", "font10", "", "error"),
               record("c", "font10", "가나")]
    report = analyze_conditions(records)
    row = next(row for row in report["conditions"] if row["condition"] == "font10")
    assert row["expected_pairs"] == 3 and row["pairs"] == 1 and row["excluded"] == 2
    assert row["missing_reference"] == 1 and row["unscored_pairs"] == 1
    assert row["observed"]["scored"] == 2 and row["observed"]["statuses"]["error"] == 1
    assert row["measured"]["cer"] == pytest.approx(1 / 3)
    assert row["measured"]["no_space_cer"] == .5
    assert row["cer_delta"] == pytest.approx(1 / 3)
    assert row["changes"] == {"regressed": 1}
    assert row["regression_examples"][0]["case_id"] == "a--font10"


@pytest.mark.parametrize("change", ["duplicate", "truth", "group", "split", "parent"])
def test_pairing_rejects_incompatible_evidence(change):
    a, b = record("a", "reference", "가 나"), record("a", "font10", "가나")
    records = [a, b]
    if change == "duplicate":
        records.append(deepcopy(b))
    elif change == "truth":
        b["expected"]["text"] = "다른 원문"
        b["expected_sha256"] = json_hash(b["expected"])
    elif change == "group":
        b["source_group_id"] = "other"
    elif change == "split":
        b["split"] = "holdout"
    else:
        b["parent_id"] = None
    with pytest.raises(ValueError):
        analyze_conditions(records)


def test_regular_reports_unchanged_and_condition_report_has_examples(tmp_path):
    from PIL import Image
    (tmp_path / "cases").mkdir()
    a, b = record("a", "reference", "가 나"), record("a", "font10", "가다")
    regular = deepcopy(a)
    regular["tags"] = {"category": "body"}
    assert analyze_conditions([regular]) is None
    for case in (a, b):
        Image.new("RGB", (12, 12), "white").save(tmp_path / "cases" / (case["case_id"] + ".png"))
    result = {"run_id": "unit", "kind": "ocr_run", "status": "completed", "limitations": []}
    save_run(tmp_path, result, [a, b])
    source = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "같은 원문, 화면 조건만 바꾸면" in source
    assert 'href="cases/a--font10.html"' in source
    assert "공백 제외 CER" in source
    assert read_json(tmp_path / "result.json")["condition_analysis"]["original_groups"] == 1


def test_invalid_condition_analysis_keeps_results_and_report_error(tmp_path):
    case = record("a", "font10", "가 나")
    case["parent_id"] = None
    result = {"run_id": "unit", "kind": "ocr_run", "status": "completed"}
    with pytest.raises(ValueError):
        save_run(tmp_path, result, [case])
    assert (tmp_path / "cases.jsonl").is_file()
    assert read_json(tmp_path / "result.json")["status"] == "report_error"
