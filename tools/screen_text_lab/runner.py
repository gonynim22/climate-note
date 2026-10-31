"""명시적인 실행의 소유 worker와 산출물만 관리한다."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

from .corpus import contained_file, digest, json_hash, load_corpus, read_json
from .metrics import METRIC_VERSION, score_case, summarize


def source_inputs():
    from tools.verify import ROOT, git_output
    # 고정 이미지 OCR의 실제 입력을 추적한다. 무관한 캘린더 UI 작업을 실험 입력으로 취급하지 않는다.
    names = ("src/app_paths.py", "requirements.txt", "requirements-lock.txt", "tools/__init__.py",
             "tools/verify.py", "tools/smoke_release.py", "screen_text/__init__.py",
             "screen_text/engine.py", "screen_text/layout.py", "tests/test_screen_text_lab.py")
    snapshot = {"head": git_output("rev-parse", "HEAD").strip(),
                "dirty": bool(git_output("status", "--porcelain").strip()),
                "scope": "fixed_image_ocr_dependencies", "files": {}}
    for name in names:
        path = ROOT / name
        snapshot["files"][name] = digest(path) if path.is_file() else None
    for path in (ROOT / "tests").glob("test_screen_text_lab*.py"):
        snapshot["files"][path.relative_to(ROOT).as_posix()] = digest(path)
    for directory in (ROOT / "screen_text/models", ROOT / "tools/screen_text_lab"):
        if directory.is_dir():
            for path in directory.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts and path.suffix in {".py", ".onnx", ".txt", ".json", ".css", ".js"}:
                    snapshot["files"][path.relative_to(ROOT).as_posix()] = digest(path)
    return snapshot


def base_record(case):
    return {key: case.get(key) for key in ("case_id", "source_group_id", "parent_id", "split",
                                          "source_kind", "tags", "review_status", "image_sha256", "image_size", "expected")} | {
        "expected_sha256": json_hash(case["expected"]), "regions": case.get("regions", []),
        "regions_sha256": json_hash(case.get("regions", [])), "status": "not_run", "metrics": None}


def append_event(path, value):
    # Windows의 읽는 중 파일 교체 충돌을 피한다. 한 worker만 append하며 읽는 쪽은 마지막 불완전 행을 기다린다.
    with open(path, "a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()


def read_jsonl(path, tolerate_partial=False):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, "rb") as stream:
        data = stream.read()
    lines = data.splitlines(keepends=True)
    records = []
    for index, line in enumerate(lines):
        try:
            records.append(json.loads(line.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            if not tolerate_partial or index != len(lines) - 1 or line.endswith(b"\n"):
                raise
            # 쓰는 중이거나 중단된 마지막 불완전 UTF-8/JSON 행만 다음 관측까지 보류한다.
    return records


def worker(run_directory):
    from tools.verify import ROOT, inside, write_json
    directory = inside(Path(run_directory), ROOT / "output/harness")
    request = read_json(directory / "request.json")
    if Path(os.environ.get("CLIMATENOTE_TEST_APPDATA", "")).resolve() != (directory / "appdata").resolve():
        raise ValueError("격리된 AppData에서만 worker를 실행할 수 있습니다")
    progress = directory / "progress.jsonl"
    append_event(progress, {"phase": "loading", "case_id": None, "sequence": 0})
    try:
        from .engine_adapter import ProductEngine
        candidate = request.get("candidate", "baseline")
        diagnose = request.get("diagnose_regions", False)
        diagnose_ctc = request.get("diagnose_ctc", False)
        recognizer, profile = request.get('recognizer'), request.get('input_profile','native')
        from .recognizers import validate_options, process_memory
        validate_options(recognizer,profile,candidate,diagnose,diagnose_ctc)
        if diagnose and candidate != "baseline":
            raise ValueError("영역 분리 진단은 baseline에서만 지원합니다")
        if diagnose_ctc and (candidate != "baseline" or diagnose):
            raise ValueError("CTC 진단은 baseline에서 영역 진단과 별도로 실행합니다")
        model_options = {'recognizer':recognizer,'input_profile':profile} if recognizer is not None or profile!='native' else {}
        engine = ProductEngine(request.get("threads"), candidate=candidate, **model_options)
        engine_metadata = {"load_ms": engine.load_ms, "provider": "CPUExecutionProvider",
                                               "threads": request.get("threads") or min(4, os.cpu_count() or 1), "warmup_runs": 0,
                                               "candidate": candidate, "observation_version": 1,
                           "repetitions": 1, "peak_memory_bytes": None,
                           'recognizer':getattr(engine,'model_info',None),'input_profile':profile}
        if model_options:
            chars=set(engine.engine._charset)
            reviewed=[case for case in request['cases'] if case['review_status']!='unreviewed']
            unsupported=[''.join(char for char in case['expected']['text'] if not char.isspace() and char not in chars) for case in reviewed]
            engine_metadata['charset_coverage']={'scored_cases':len(reviewed),'cases_with_unsupported':sum(bool(x) for x in unsupported),
                'unsupported_characters':sorted(set(''.join(unsupported))), 'unsupported_occurrences':sum(map(len,unsupported)),
                'scope':'evaluation_only_not_passed_to_inference'}
        write_json(directory/'engine.json',engine_metadata)
        with open(directory / "cases.jsonl", "a", encoding="utf-8", newline="\n") as stream:
            for index, case in enumerate(request["cases"]):
                append_event(progress, {"phase": "case", "case_id": case["case_id"], "sequence": index + 1})
                record = base_record(case)
                try:
                    path = contained_file(directory / "cases", case["case_id"] + ".png")
                    if digest(path) != case["image_sha256"]:
                        raise ValueError("실행 사본의 이미지 해시가 다릅니다")
                    if diagnose_ctc:
                        prediction = engine.recognize(path, ctc_case=case)
                    else:
                        prediction = engine.recognize(path, region_case=case) if diagnose else engine.recognize(path)
                    record.update(prediction=prediction, metrics=score_case(case, prediction), status="ok")
                except Exception as error:
                    # 사례별 실패를 보존하고 다음 자료를 처리한다. 자동 재시도는 없다.
                    record.update(status="error", error_type=type(error).__name__)
                stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        append_event(progress, {"phase": "finished", "case_id": None, "sequence": len(request["cases"]) + 1})
        engine_metadata['memory'] = process_memory()
        write_json(directory/'engine.json',engine_metadata)
        return 0
    except Exception as error:
        write_json(directory / "worker-error.json", {"error_type": type(error).__name__, "message": str(error)})
        return 2


def read_records(directory, tolerate_partial=False):
    return read_jsonl(Path(directory) / "cases.jsonl", tolerate_partial)


def complete_records(cases, records, progress, status):
    by_id = {record["case_id"]: record for record in records}
    result = []
    for case in cases:
        record = by_id.get(case["case_id"], base_record(case))
        if record["status"] == "not_run" and progress.get("case_id") == case["case_id"]:
            record["status"] = "timeout" if status == "timeout" else "cancelled" if status == "cancelled" else "error"
        result.append(record)
    return result


def save_run(directory, result, records):
    from tools.verify import atomic_text, write_json
    from .condition_analysis import analyze_conditions
    from .diagnostic_analysis import analyze_warnings
    from .region_diagnostics import summarize_regions
    from .ctc_probe import summarize_ctc
    result["warning_analysis"] = analyze_warnings(records)
    result["region_analysis"] = summarize_regions(records)
    result["ctc_analysis"] = summarize_ctc(records)
    result["metrics"] = summarize(records)
    atomic_text(directory / "cases.jsonl", "".join(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n" for record in records))
    result["cases_sha256"] = digest(directory / "cases.jsonl")
    write_json(directory / "result.json", result)
    from .report import render_report
    try:
        condition_analysis = analyze_conditions(records)
        if condition_analysis is not None:
            result["condition_analysis"] = condition_analysis
            write_json(directory / "result.json", result)
        render_report(directory, result, records)
    except Exception as error:
        result.update(status="report_error", report_error_type=type(error).__name__)
        write_json(directory / "result.json", result)
        atomic_text(directory / "summary.md", f"# 화면 글자 따기 진단\n\nreport_error: {type(error).__name__}\n")
        raise


def run(corpus_path, suite="bootstrap", split="dev", candidate="baseline", threads=None, timeout=120,
        diagnose_regions=False, diagnose_ctc=False, case_ids=None, recognizer=None, input_profile='native'):
    from tools.verify import (ROOT, atomic_text, create_run_dir, doctor, isolated_env,
                              utc_now, write_json)
    from tools.smoke_release import managed_launch
    from .experiments import candidate_settings
    settings = candidate_settings(candidate)
    from .recognizers import validate_options, model_snapshot
    validate_options(recognizer,input_profile,candidate,diagnose_regions,diagnose_ctc)
    recognizer_before = model_snapshot(recognizer or 'product')
    if diagnose_regions and candidate != "baseline":
        raise ValueError("영역 분리 진단은 baseline에서만 지원합니다")
    if diagnose_ctc and (candidate != "baseline" or diagnose_regions):
        raise ValueError("CTC 진단은 baseline에서 영역 진단과 별도로 실행합니다")
    if not isinstance(timeout, (int, float)) or not 1 <= timeout <= 3600:
        raise ValueError("사례/모델 로드 시간 제한은 1~3600초입니다")
    if threads is not None and not 1 <= threads <= 64:
        raise ValueError("스레드 수는 1~64입니다")
    corpus = load_corpus(corpus_path)
    cases = corpus.select(suite, split)
    if case_ids is not None:
        if not case_ids or len(set(case_ids)) != len(case_ids):
            raise ValueError("case-id는 중복 없는 하나 이상의 ID여야 합니다")
        unknown = set(case_ids) - {case['case_id'] for case in cases}
        if unknown:
            raise ValueError("선택한 suite/split에 없는 case-id: " + ", ".join(sorted(unknown)))
        cases = [case for case in cases if case['case_id'] in set(case_ids)]
    directory = create_run_dir()
    env = isolated_env(directory)
    (directory / "cases").mkdir()
    before = source_inputs()
    inputs = corpus.fingerprint()
    result = {"schema_version": 1, "kind": "ocr_run", "metric_version": METRIC_VERSION,
              "run_id": directory.name, "status": "running", "started_at": utc_now(),
              "command": sys.argv, "candidate": candidate, "suite": suite, "split": split,
              "dataset_id": corpus.manifest["dataset_id"], "corpus_path": str(corpus.directory),
              "manifest_sha256": corpus.manifest_sha256, "source_before": before,
              "inputs_before": inputs, "environment": {"python": sys.version, "platform": platform.platform(),
                  "cpu": platform.processor(), "logical_cpus": os.cpu_count()},
              "config": {"threads": threads, "timeout_seconds": timeout, "candidate_settings": settings,
                         "diagnose_regions": diagnose_regions, "diagnose_ctc": diagnose_ctc, "case_ids": case_ids,
                         'recognizer':recognizer,'input_profile':input_profile},
              'recognizer_inputs_before':recognizer_before,
              "selection": {"cases": len(cases), "originals": sum(case.get("parent_id") is None for case in cases),
                            "source_groups": len({case["source_group_id"] for case in cases})},
              "limitations": ["고정 PNG 재생: 실제 Windows 캡처/DPI 검증 아님",
                              "한 번씩 실행한 시간: 워밍업·반복 통계·모델 단독 최대 메모리 미측정",
                              "출력된 비공백 CTC 문자 점수 관측: 정답 확률·누락 문자·위치별 경고 적중률 아님",
                              "후보는 격리 worker에만 적용하며 제품 기본값을 바꾸지 않음"]}
    if recognizer is not None or input_profile!='native':
        result['limitations'].extend([
            '검출/줄·표 구성은 기존 제품 고정. 입력 조건과 인식 모델만 비교하며 정답은 추론에 사용하지 않음',
            'EasyOCR는 64px 회색조 bicubic/끝 픽셀 패딩/전체 greedy. 모델 어댑터 비교이며 전체 EasyOCR 제품의 품질 평가 아님',
            '모델 간 CTC 평균 점수와 불확실 표시를 보정하지 않음. 경고 품질은 직접 비교할 수 없음',
            '시간에는 입력 해시 관측 포함. 최대 working set은 해당 worker 전체 값이며 모델 단독 메모리 아님'])
    if diagnose_ctc:
        result['limitations'].extend([
            'CTC 원인 진단: 선택 사례의 탐색 결과이며 독립 정확도 평가가 아님',
            '측정 시간에 CTC 진단 계산 포함: 제품 지연시간 비교에 사용하지 않음',
            'beam8/top5는 정답·사전·언어모델 없는 근사 탐색. 전체 경로 최적해 보장 없음',
            '정답 문자열의 경로 질량은 추론 후 일대일 대응한 영역만 계산. 영역 경계 오류와 모델 자체 오류를 분리하지 못함'])
    write_json(directory / "result.json", result)
    atomic_text(directory / "summary.md", f"# 화면 글자 따기 진단\n\n실행 {directory.name}: running\n")
    atomic_text(directory / "cases.jsonl", "")
    write_json(directory / "request.json", {"cases": cases, "threads": threads, "candidate": candidate,
                                           "diagnose_regions": diagnose_regions, "diagnose_ctc": diagnose_ctc,
                                           'recognizer':recognizer,'input_profile':input_profile})
    progress = {}
    started = time.monotonic()
    status = "error"
    print(f"원본 {result['selection']['originals']} / 전체 {len(cases)} / {split} / {candidate}", flush=True)
    print(f"실행 ID: {directory.name}", flush=True)
    try:
        environment = doctor()
        result["doctor"] = environment
        if environment["errors"]:
            raise ValueError("환경 doctor 실패: " + "; ".join(environment["errors"]))
        for case in cases:
            source = contained_file(corpus.directory, case["image"])
            target = directory / "cases" / (case["case_id"] + ".png")
            shutil.copyfile(source, target)
            if digest(target) != case["image_sha256"]:
                raise ValueError("복사 중 이미지 입력이 변경되었습니다")
        command = [sys.executable, str(ROOT / "tools/smoke_release.py"), "_launch",
                   sys.executable, "-m", "tools.screen_text_lab", "_worker", str(directory)]
        deadline, previous = time.monotonic() + timeout, None
        with managed_launch(command, env, directory / "worker.log") as (_, process):
            while process.poll() is None:
                path = directory / "progress.jsonl"
                if path.exists():
                    events = read_jsonl(path, tolerate_partial=True)
                    progress = events[-1] if events else {}
                    current = (progress.get("phase"), progress.get("sequence"))
                    if current != previous:
                        previous, deadline = current, time.monotonic() + timeout
                        if progress.get("phase") == "case" and (progress["sequence"] == 1 or progress["sequence"] % 20 == 0):
                            print(f"처리 {progress['sequence']}/{len(cases)}", flush=True)
                if time.monotonic() > deadline:
                    status = "timeout"
                    break
                time.sleep(.1)
            else:
                status = "completed" if process.returncode == 0 else "error"
            result["worker_returncode"] = process.poll()
    except KeyboardInterrupt:
        status = "cancelled"
    except Exception as error:
        result["error_type"] = type(error).__name__
        result["error_message"] = str(error)
        status = "error"
    finally:
        result["processing_seconds"] = time.monotonic() - started
        records = complete_records(cases, read_records(directory, tolerate_partial=True), progress, status)
        try:
            after, inputs_after = source_inputs(), corpus.fingerprint()
            result.update(source_after=after, inputs_after=inputs_after)
            recognizer_after = model_snapshot(recognizer or 'product')
            result['recognizer_inputs_after'] = recognizer_after
            if before["files"] != after["files"] or inputs != inputs_after or recognizer_before != recognizer_after:
                status = "inputs_changed"
        except (OSError, ValueError) as error:
            status = "inputs_changed"
            result["input_check_error"] = type(error).__name__
        if status == "completed" and any(record["status"] != "ok" for record in records):
            status = "partial"
        if status == "completed" and diagnose_regions and any(
                record.get("prediction", {}).get("region_diagnostic", {}).get("status") == "error" for record in records):
            status = "partial"
        if status == "completed" and diagnose_ctc and any(
                record.get("prediction", {}).get("ctc_diagnostic", {}).get("status") == "error" for record in records):
            status = "partial"
        result.update(status=status, finished_at=utc_now())
        engine_path = directory / "engine.json"
        if engine_path.exists():
            result["engine"] = read_json(engine_path)
        if (directory / "worker-error.json").exists():
            result["worker_error"] = read_json(directory / "worker-error.json")
        save_run(directory, result, records)
    print(f"{status}: {directory / 'report.html'}", flush=True)
    return directory, (0 if status == "completed" else 130 if status == "cancelled" else 1)
