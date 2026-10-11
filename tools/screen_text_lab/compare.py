"""동일한 자료/정답을 사용한 실행끼리만 비교한다."""
from collections import Counter
from pathlib import Path
import shutil

from .corpus import ID_PATTERN, contained_file, digest, json_hash, read_json
from .metrics import METRIC_VERSION
from .runner import read_records


def classify(baseline, candidate):
    left, right = baseline.get("metrics"), candidate.get("metrics")
    if baseline["status"] != "ok" or candidate["status"] != "ok" or left is None or right is None:
        return "unscored"
    left_errors, right_errors = left["errors"], right["errors"]
    if right_errors < left_errors:
        return "improved"
    if right_errors > left_errors:
        return "regressed"
    left_table, right_table = left.get("table"), right.get("table")
    if left_table is not None and right_table is not None:
        delta = (right_table["cells"] - right_table["correct"]) - (left_table["cells"] - left_table["correct"])
        if delta:
            return "regressed" if delta > 0 else "improved"
    return "unchanged" if baseline["prediction"]["text"] == candidate["prediction"]["text"] else "changed"


def pair_records(baseline, candidate, intersection=False):
    left, right = {}, {}
    for mapping, records in ((left, baseline), (right, candidate)):
        for record in records:
            case_id = record.get("case_id")
            if not isinstance(case_id, str) or not ID_PATTERN.fullmatch(case_id) or case_id in mapping:
                raise ValueError("실행 결과에 잘못되거나 중복된 case_id가 있습니다")
            if json_hash(record["expected"]) != record["expected_sha256"]:
                raise ValueError("저장된 정답 해시가 다릅니다")
            if ("region_diagnostic" in record.get("prediction", {}) and
                    json_hash(record.get("regions", [])) != record.get("regions_sha256")):
                raise ValueError("저장된 영역 주석 해시가 다릅니다")
            mapping[case_id] = record
    if not intersection and set(left) != set(right):
        raise ValueError("실행의 사례 목록이 다릅니다. 의도적인 부분 비교는 --intersection을 사용하세요")
    ids = sorted(set(left) & set(right))
    if not ids:
        raise ValueError("비교할 공통 사례가 없습니다")
    for case_id in ids:
        for key in ("image_sha256", "expected_sha256", "split", "source_group_id", "source_kind", "tags", "review_status"):
            if left[case_id].get(key) != right[case_id].get(key):
                raise ValueError(f"{case_id}: {key}가 달라 직접 비교할 수 없습니다")
        if all("region_diagnostic" in mapping[case_id].get("prediction", {}) for mapping in (left, right)):
            if left[case_id].get("regions_sha256") != right[case_id].get("regions_sha256"):
                raise ValueError(f"{case_id}: 영역 주석이 달라 단계 진단을 비교할 수 없습니다")
        if all('recognizer' in mapping[case_id].get('prediction',{}) for mapping in (left,right)):
            crops=[]
            for mapping in (left,right):
                crops.append([(row['box'],row['crop_sha256']) for row in mapping[case_id]['prediction']['recognizer']['regions']])
            if crops[0]!=crops[1]:
                raise ValueError(f'{case_id}: 검출 영역/원본 crop이 달라 고정 영역 모델 비교를 할 수 없습니다')
    return ([left[case_id] for case_id in ids], [right[case_id] for case_id in ids],
            len(left) - len(ids), len(right) - len(ids))


def load_run(value):
    from tools.verify import ROOT, inside
    boundary = ROOT / "output/harness"
    path = Path(value)
    if not path.is_absolute() and len(path.parts) == 1:
        path = boundary / path
    directory = inside(path, boundary)
    result = read_json(directory / "result.json")
    if result.get("kind") != "ocr_run" or result.get("status") not in {"completed", "partial"}:
        raise ValueError("완료/부분 완료된 OCR 실행만 비교할 수 있습니다")
    if result.get("metric_version") != METRIC_VERSION:
        raise ValueError("채점 규칙 버전이 다릅니다")
    records = read_records(directory)
    if digest(directory / "cases.jsonl") != result.get("cases_sha256"):
        raise ValueError("사례별 결과 파일이 변경되었습니다")
    return directory, result, records


def compare(baseline, candidate, intersection=False):
    from tools.verify import create_run_dir, isolated_env, utc_now, write_json
    from .report import render_report
    left_dir, left_result, left_records = load_run(baseline)
    right_dir, right_result, right_records = load_run(candidate)
    left, right, missing_left, missing_right = pair_records(left_records, right_records, intersection)
    # 저장된 원본 픽셀까지 검증한 뒤에 새 비교 산출물을 생성한다.
    for source_dir, records in ((left_dir, left), (right_dir, right)):
        for record in records:
            image = contained_file(source_dir / "cases", record["case_id"] + ".png")
            if digest(image) != record["image_sha256"]:
                raise ValueError("실행에 보관된 이미지가 변경되었습니다")
    directory = create_run_dir()
    isolated_env(directory)
    (directory / "cases").mkdir()
    changes = {record["case_id"]: classify(old, record) for old, record in zip(left, right)}
    result = {"schema_version": 1, "kind": "ocr_comparison", "metric_version": METRIC_VERSION,
              "run_id": directory.name, "status": "completed", "started_at": utc_now(),
              "dataset_id": right_result["dataset_id"], "split": right_result["split"],
              "comparison": {"baseline": left_dir.name, "candidate": right_dir.name,
                             "baseline_result_sha256": digest(left_dir / "result.json"),
                             "candidate_result_sha256": digest(right_dir / "result.json"),
                             "intersection": intersection, "excluded_baseline": missing_left,
                             "excluded_candidate": missing_right, "counts": dict(Counter(changes.values()))},
              "limitations": ["같은 사례·이미지·정답의 쌍만 비교. 상단 정확도 지표는 후보 결과.",
                               "합성/고정 이미지 결과는 실제 캡처나 전체 업무 정확도를 대표하지 않습니다.",
                               "개선/퇴행은 편집 오류 수, 동률일 때 표 셀 오류로 분류. 경고와 시간은 별도 확인."]}
    if any(meta.get('engine',{}).get('recognizer') for meta in (left_result,right_result)):
        result['recognizers']={'baseline':left_result.get('engine',{}),'candidate':right_result.get('engine',{})}
        result['limitations'].append('모델 비교의 점수/경고는 미보정. 시간은 입력 해시 관측 포함 1회이며 EasyOCR 모델 어댑터는 전체 EasyOCR 파이프라인이 아님.')
    for record in right:
        shutil.copyfile(right_dir / "cases" / (record["case_id"] + ".png"), directory / "cases" / (record["case_id"] + ".png"))
    from .metrics import summarize
    from tools.verify import atomic_text
    import json
    result["metrics"] = summarize(right)
    from .diagnostic_analysis import analyze_candidates, analyze_warnings
    result["candidate_analysis"] = analyze_candidates(left, right)
    result["warning_analysis"] = analyze_warnings(right)
    from .region_diagnostics import summarize_regions
    result["region_analysis"] = summarize_regions(right)
    atomic_text(directory / "cases.jsonl", "".join(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n" for record in right))
    result["cases_sha256"] = digest(directory / "cases.jsonl")
    result["finished_at"] = utc_now()
    write_json(directory / "result.json", result)
    try:
        render_report(directory, result, right, left, changes)
    except Exception as error:
        result.update(status="report_error", report_error_type=type(error).__name__)
        write_json(directory / "result.json", result)
        atomic_text(directory / "summary.md", f"# 실행 비교\n\nreport_error: {type(error).__name__}\n")
        raise
    return directory / "report.html"
