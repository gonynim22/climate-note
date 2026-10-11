"""Replay only the approved legacy dev48 captures through det→rec→layout.

This manual CPU regression uses saved JPEG-derived Notepad/CLI regions and AI
reviewed labels. It never opens the original corpus, holdout or final datasets.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sys
import time

from .corpus import ID_PATTERN, contained_file, digest, json_hash, read_json
from .crop_evaluation import (ProbabilitySession, candidate_bundle, candidate_charset,
                              dependency_snapshot, validate_session, validate_worker_records)
from .metrics import score_case, summarize
from .runner import append_event, complete_records, read_jsonl


BASELINE_ID = "20261011-132412-c26da2630f"
BASELINE_CASES_SHA256 = "b9c2e2c512cf2ee4aa568d5e33b5bac5a2f3f468aa3fa2f26230d0035d33363f"
BASELINE_COUNT = 48
BASELINE_DEPENDENCIES = ("screen_text/engine.py", "screen_text/layout.py",
                         "screen_text/models/det.onnx", "screen_text/models/rec.onnx",
                         "screen_text/models/dict.txt", "screen_text/models/MANIFEST.json",
                         "tools/screen_text_lab/metrics.py", "tools/screen_text_lab/engine_adapter.py",
                         "tools/screen_text_lab/experiments.py", "requirements-lock.txt")
LIMITATIONS = ["기존 터미널 문구/Notepad 개발 회귀 48건(24원본의 두 배율)이며 신규 학습 우선 자료가 아님",
              "JPEG 유래 고정 캡처 영역과 AI 검토 정답을 재사용하며 독립 최종평가·사람 검수 자료가 아님",
              "한컴한글/PDF/Word 공문서 본문·표·숫자·단위의 새 사용자 우선순위 평가를 대체하지 않음",
              "제품 검출→줄 인식→줄/표 구성·복사 문자열을 실행하나 기대 표 정답 0건이어서 표 정확도는 미측정",
              "실시간 캡처/창 수명/오프라인 차단/혼합 DPI/EXE 검증 미실행; 제품 채택·배포 승인 아님",
              "동시 작업 중 단회 시간은 제품 속도·최대 메모리 검증이 아님"]


def load_baseline(root):
    """Validate the single pre-authorized saved run, following no corpus paths."""
    from PIL import Image

    root = Path(root).resolve()
    directory = root / "output/harness" / BASELINE_ID
    metadata_paths = [directory / name for name in ("result.json", "request.json", "cases.jsonl")]
    files = {str(path): digest(path) for path in metadata_paths}
    if files[str(directory / "cases.jsonl")] != BASELINE_CASES_SHA256:
        raise ValueError("Approved dev baseline records changed")
    result, request = read_json(metadata_paths[0]), read_json(metadata_paths[1])
    if (result.get("run_id") != BASELINE_ID or result.get("kind") != "ocr_run" or result.get("status") != "completed"
            or result.get("split") != "dev" or result.get("cases_sha256") != BASELINE_CASES_SHA256
            or request.get("candidate") != "baseline" or request.get("recognizer") is not None
            or request.get("input_profile") != "native" or request.get("diagnose_ctc") or request.get("diagnose_regions")):
        raise ValueError("Saved baseline is not the approved completed native dev run")
    before, after = result.get("source_before", {}).get("files", {}), result.get("source_after", {}).get("files", {})
    if not before or before != after or result.get("inputs_before") != result.get("inputs_after"):
        raise ValueError("Saved baseline inputs changed during its execution")
    for name in BASELINE_DEPENDENCIES:
        value = digest(root / name)
        if before.get(name) != value:
            raise ValueError(f"Current product/scoring differs from saved P: {name}")
        files[str(root / name)] = value
    records = read_jsonl(directory / "cases.jsonl")
    cases = request.get("cases", [])
    if len(cases) != BASELINE_COUNT or len(records) != BASELINE_COUNT:
        raise ValueError("All approved dev48 cases are required")
    ids = [case.get("case_id") for case in cases]
    if len(set(ids)) != len(ids) or [row.get("case_id") for row in records] != ids:
        raise ValueError("Baseline case IDs/order are duplicated or incomplete")
    prepared, baseline = [], []
    for case, record in zip(cases, records):
        identifier = case["case_id"]
        if (not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier)
                or case.get("split") != "dev" or record.get("split") != "dev"
                or case.get("source_kind") != "program_capture"
                or case.get("tags", {}).get("category") != "cli"
                or case.get("tags", {}).get("source_app") != "Windows Notepad"
                or case.get("tags", {}).get("capture_encoding") != "jpeg"
                or "table" in case.get("expected", {})):
            raise ValueError("Baseline is outside the fixed Notepad/CLI dev regression scope")
        keys = ("case_id", "source_group_id", "parent_id", "split", "source_kind", "tags", "review_status", "image_sha256", "image_size", "expected")
        if (any(record.get(key) != case.get(key) for key in keys) or record.get("status") != "ok"
                or record.get("expected_sha256") != json_hash(case["expected"])
                or record.get("metrics") != score_case(case, record["prediction"])):
            raise ValueError("Baseline request, records and canonical scores disagree")
        path = contained_file(directory / "cases", identifier + ".png")
        if digest(path) != case["image_sha256"]:
            raise ValueError("Saved dev capture hash differs")
        with Image.open(path) as image:
            if image.format != "PNG" or list(image.size) != case["image_size"]:
                raise ValueError("Saved dev capture format/size differs")
        files[str(path)] = case["image_sha256"]
        clean = {key: deepcopy(case.get(key)) for key in keys}
        clean.update(evaluation_scope="fixed_capture_region", review_provenance={
            "reviewer_kind": "assistant", "human_reviewed": False, "method": "saved_ai_visual_review",
            "original_review": deepcopy(case.get("review", {}))}, critical_tags=[])
        prepared.append(clean)
        baseline.append(deepcopy(record) | clean)
    if any(digest(Path(path)) != value for path, value in files.items()):
        raise ValueError("Baseline artifacts changed while loading")
    return {"directory": directory, "cases": prepared, "records": baseline, "files": files,
            "source_groups": len({case["source_group_id"] for case in cases}), "expected_table_cases": 0}


def snapshot(root):
    files = dependency_snapshot(root)
    names = ["tools/screen_text_lab/full_candidate.py", "tools/screen_text_lab/report.py",
             "tools/screen_text_lab/evaluation/core.py", "tools/screen_text_lab/evaluation/report.py"]
    return files | {name: digest(root / name) for name in names}


def full_prediction(engine, rgb):
    """Only pixels enter the unchanged product detector, recognizer and layout."""
    from .engine_adapter import pack_prediction
    started = time.perf_counter()
    prediction = pack_prediction(engine.recognize(rgb))
    prediction.update(total_ms=(time.perf_counter() - started) * 1000,
                      timing_scope="single_fixed_capture_run_not_product_latency")
    return prediction


def worker(directory, request_sha256):
    from tools.verify import ROOT, inside, write_json
    directory = inside(Path(directory), ROOT / "output/harness")
    if (Path(os.environ.get("CLIMATENOTE_TEST_APPDATA", "")).resolve() != (directory / "appdata").resolve()
            or digest(directory / "request.json") != request_sha256):
        raise ValueError("Worker needs isolated AppData and the exact parent request")
    request = read_json(directory / "request.json")
    append_event(directory / "progress.jsonl", {"phase": "loading", "sequence": 0})
    try:
        import numpy as np
        import onnxruntime as ort
        from PIL import Image
        from screen_text.engine import OcrEngine
        for filename, expected in (("det.onnx", request["detector_sha256"]),
                                   ("model.onnx", request["model"]["model_sha256"]),
                                   ("dictionary.txt", request["model"]["dictionary_sha256"])):
            if digest(directory / filename) != expected:
                raise ValueError("Worker model/dictionary copy hash mismatch")
        chars = candidate_charset(directory / "dictionary.txt")
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.intra_op_num_threads, options.inter_op_num_threads = request["threads"], 1
        engine = object.__new__(OcrEngine)
        engine._det = ort.InferenceSession(str(directory / "det.onnx"), options, providers=["CPUExecutionProvider"])
        recognition = ort.InferenceSession(str(directory / "model.onnx"), options, providers=["CPUExecutionProvider"])
        validate_session(recognition, chars)
        engine._rec, engine._charset = ProbabilitySession(recognition), chars
        for index, case in enumerate(request["cases"], 1):
            append_event(directory / "progress.jsonl", {"phase": "case", "sequence": index, "case_id": case["case_id"]})
            record = dict(case, expected_sha256=json_hash(case["expected"]), status="error", metrics=None)
            try:
                path = contained_file(directory / "cases", case["case_id"] + ".png")
                if case["split"] != "dev" or digest(path) != case["image_sha256"]:
                    raise ValueError("Worker accepts the unchanged dev capture copies only")
                with Image.open(path) as image:
                    rgb = np.asarray(image.convert("RGB")).copy()
                prediction = full_prediction(engine, rgb)
                record.update(status="ok", prediction=prediction, metrics=score_case(case, prediction))
            except Exception as error:
                record.update(error_type=type(error).__name__, error_message=str(error))
            append_event(directory / "cases.jsonl", record)
        append_event(directory / "progress.jsonl", {"phase": "finished", "sequence": len(request["cases"]) + 1})
        return 0
    except Exception as error:
        write_json(directory / "worker-error.json", {"type": type(error).__name__, "message": str(error)})
        return 2


def run(bundle, threads=4, timeout=120):
    from tools.verify import ROOT, atomic_text, create_run_dir, doctor, isolated_env, write_json
    from tools.smoke_release import managed_launch
    from .evaluation import analyze_pair
    from .evaluation.report import save_report
    from .report import render_report
    from screen_text.engine import verify_models

    if type(threads) is not int or not 1 <= threads <= 16 or not 1 <= timeout <= 3600:
        raise ValueError("Invalid threads or per-progress timeout")
    baseline = load_baseline(ROOT)
    metadata, models = candidate_bundle(bundle, ROOT / "output/screen_text_lab")
    detector = verify_models()["det"]
    before = snapshot(ROOT)
    inputs = baseline["files"] | metadata["verified_provenance"]["files"]
    inputs.update({str(Path(bundle).resolve()): metadata["bundle_sha256"], str(detector): digest(detector)})
    directory = create_run_dir()
    environment = isolated_env(directory)
    request = {"cases": baseline["cases"], "model": metadata, "threads": threads,
               "detector_sha256": digest(detector), "baseline_run": BASELINE_ID}
    write_json(directory / "request.json", request)
    request_sha = digest(directory / "request.json")
    inputs[str(directory / "request.json")] = request_sha
    result = {"schema_version": 1, "kind": "legacy_dev_full_candidate", "run_id": directory.name,
              "status": "error", "split": "dev", "model": metadata, "baseline_run": BASELINE_ID,
              "source_before": before, "inputs_before": inputs, "request_sha256": request_sha,
              "evaluation_scope": "fixed_capture_region", "product_adoption": "not_evaluated",
              "selection": {"cases": len(baseline["cases"]), "source_groups": baseline["source_groups"], "expected_table_cases": 0},
              "limitations": LIMITATIONS}
    status, progress = "error", {}
    try:
        result["doctor"] = doctor()
        if result["doctor"]["errors"]:
            raise ValueError("Environment doctor failed")
        (directory / "cases").mkdir()
        for case in baseline["cases"]:
            name = case["case_id"] + ".png"
            shutil.copyfile(contained_file(baseline["directory"] / "cases", name), directory / "cases" / name)
        for source, name in ((detector, "det.onnx"), (models["model"], "model.onnx"), (models["dictionary"], "dictionary.txt")):
            shutil.copyfile(source, directory / name)
            inputs[str(directory / name)] = digest(source)
            if digest(directory / name) != inputs[str(directory / name)]:
                raise ValueError("Model changed during copy")
        command = [sys.executable, str(ROOT / "tools/smoke_release.py"), "_launch", sys.executable,
                   "-m", "tools.screen_text_lab.full_candidate", "_worker", str(directory), request_sha]
        deadline, previous = time.monotonic() + timeout, None
        with managed_launch(command, environment, directory / "worker.log") as (_, process):
            while process.poll() is None:
                events = read_jsonl(directory / "progress.jsonl", tolerate_partial=True)
                progress = events[-1] if events else {}
                current = progress.get("phase"), progress.get("sequence")
                if current != previous:
                    previous, deadline = current, time.monotonic() + timeout
                    if progress.get("phase") == "case" and progress["sequence"] % 12 == 0:
                        print(f"Legacy dev regression {progress['sequence']}/{BASELINE_COUNT}", flush=True)
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
        result["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        try:
            raw = read_jsonl(directory / "cases.jsonl", tolerate_partial=True)
            validate_worker_records(baseline["cases"], raw)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raw, status = [], "artifact_error"
            result["record_error"] = str(error)
        records = complete_records(baseline["cases"], raw, progress, status)
        try:
            result["source_after"] = snapshot(ROOT)
            result["inputs_after"] = {path: digest(Path(path)) for path in inputs}
            if before != result["source_after"] or inputs != result["inputs_after"]:
                status = "inputs_changed"
            for case in baseline["cases"]:
                if digest(contained_file(directory / "cases", case["case_id"] + ".png")) != case["image_sha256"]:
                    status = "inputs_changed"
        except (OSError, ValueError) as error:
            status = "inputs_changed"
            result["input_check_error"] = str(error)
        if status == "completed" and any(record["status"] != "ok" for record in records):
            status = "partial"
        # Fill the scoped metadata on not-run rows without inventing predictions.
        records = [record | case for record, case in zip(records, baseline["cases"])]
        analysis = analyze_pair(baseline["records"], records, baseline["cases"],
                                supported_characters=candidate_charset(ROOT / "screen_text/models/dict.txt"))
        analysis["limitations"].extend(LIMITATIONS)
        result.update(status=status, metrics=summarize(records), paired_transitions=analysis["transitions"])
        atomic_text(directory / "cases.jsonl", "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in records))
        result["cases_sha256"] = digest(directory / "cases.jsonl")
        write_json(directory / "result.json", result)
        save_report(directory / "paired", analysis)
        render_report(directory, result, records)
        with (directory / "summary.md").open("a", encoding="utf-8") as stream:
            stream.write("\n[독립 쌍 비교](paired/report.html) · 기존 CLI 회귀용이며 신규 우선순위 최종평가가 아닙니다.\n")
    print(f"{status}: {directory / 'summary.md'}", flush=True)
    return directory, 0 if status == "completed" else 1


def main():
    parser = argparse.ArgumentParser(__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("run")
    command.add_argument("--bundle", required=True)
    command.add_argument("--threads", type=int, default=4)
    command.add_argument("--timeout", type=int, default=120)
    internal = commands.add_parser("_worker")
    internal.add_argument("directory")
    internal.add_argument("request_sha256")
    args = parser.parse_args()
    if args.command == "_worker":
        return worker(args.directory, args.request_sha256)
    return run(args.bundle, args.threads, args.timeout)[1]


if __name__ == "__main__":
    raise SystemExit(main())
