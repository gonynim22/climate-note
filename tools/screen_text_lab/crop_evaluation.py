"""학습 selection 줄 crop의 수동 CPU 평가. 제품/일반 검사의 진입점과 분리한다."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time

from .corpus import ID_PATTERN, contained_file, digest, json_hash, read_json
from .metrics import score_case, summarize
from .runner import append_event, complete_records, read_jsonl


def candidate_bundle(path, lab_root):
    """실험 폴더 안의 명시적인 모델·사전 해시만 허용한다."""
    from tools.verify import inside
    from .training.bundle_candidate import verify_bundle_provenance
    path = inside(Path(path), Path(lab_root))
    before = digest(path)
    value = read_json(path)
    if value.get("schema_version") != 1 or value.get("role") not in {"R", "F"}:
        raise ValueError("후보 schema_version/role 오류")
    if not isinstance(value.get("id"), str) or not value["id"] or not isinstance(value.get("provenance"), dict):
        raise ValueError("후보 ID/출처가 필요합니다")
    files = {}
    for key in ("model", "dictionary"):
        source = contained_file(path.parent, value[key])
        if digest(source) != value[key + "_sha256"]:
            raise ValueError(f"후보 {key} 해시 불일치")
        files[key] = source
    evidence = verify_bundle_provenance(path, value, files)
    if digest(path) != before:
        raise ValueError("읽는 동안 후보 등록 파일 변경")
    return value | {"bundle_sha256": before, "verified_provenance": evidence}, files


def candidate_charset(path):
    with open(path, encoding="utf-8", newline="") as stream:
        chars = [line.rstrip("\r\n") for line in stream]
    if not chars or any(len(char) != 1 or char.isspace() for char in chars) or len(set(chars)) != len(chars):
        raise ValueError("빈 항목/여러 글자/공백/중복이 있는 사전")
    return chars + [" "]


def validate_session(session, chars):
    inputs, outputs = session.get_inputs(), session.get_outputs()
    if len(inputs) != 1 or inputs[0].name != "x" or inputs[0].type != "tensor(float)":
        raise ValueError("후보 입력은 float32 x 하나여야 합니다")
    shape = inputs[0].shape
    if len(shape) != 4 or shape[1:3] != [3, 48] or isinstance(shape[0], int) or isinstance(shape[3], int):
        raise ValueError("후보 입력은 dynamic [N,3,48,W]여야 합니다")
    if len(outputs) != 1 or outputs[0].type != "tensor(float)" or len(outputs[0].shape) != 3 or outputs[0].shape[-1] != len(chars) + 1:
        raise ValueError("후보 CTC 출력/사전 불일치")


class ProbabilitySession:
    """경고 점수에 logits/NaN을 잘못 사용하는 것을 차단한다."""

    def __init__(self, session):
        self.session = session

    def run(self, output_names, inputs):
        import numpy as np
        outputs = self.session.run(output_names, inputs)
        values = outputs[0]
        if (not np.isfinite(values).all() or values.min() < 0 or values.max() > 1
                or not np.allclose(values.sum(axis=-1), 1, atol=1e-3, rtol=0)):
            raise ValueError("CTC 출력이 유한한 확률분포가 아닙니다")
        return outputs


def validate_selection(cases):
    if not cases or len(cases) > 20000:
        raise ValueError("선택 자료 개수 범위 오류")
    for case in cases:
        if case.get("split") != "selection" or case.get("evaluation_scope") != "line_crop":
            raise ValueError("선택 자료의 line_crop만 허용합니다. final/holdout/train은 실행하지 않습니다")
        if not isinstance(case.get("case_id"), str) or not ID_PATTERN.fullmatch(case["case_id"]):
            raise ValueError("안전하지 않은 사례 ID")
        if case.get("review_status") not in {"generated", "reviewed", "unreviewed"}:
            raise ValueError("정답 검토 상태가 필요합니다")


def validate_worker_records(cases, records):
    """자식이 돌려준 정답·군집·입력 식별자를 부모의 고정 요청과 대조한다."""
    expected = {case["case_id"]: case for case in cases}
    seen = set()
    for record in records:
        case_id = record.get("case_id")
        if case_id in seen or case_id not in expected:
            raise ValueError("실행 기록의 중복/알 수 없는 사례 ID")
        seen.add(case_id)
        case = expected[case_id]
        if any(record.get(key) != value for key, value in case.items()):
            raise ValueError("실행 기록의 정답/이미지/메타데이터가 원본 요청과 다릅니다")
        if record.get("expected_sha256") != json_hash(case["expected"]):
            raise ValueError("실행 기록의 정답 해시 불일치")
        if record.get("status") not in {"ok", "error"}:
            raise ValueError("실행 기록의 상태 오류")
        if record["status"] == "ok" and record.get("metrics") != score_case(case, record["prediction"]):
            raise ValueError("실행 기록의 채점 불일치")


def dependency_snapshot(root):
    names = ["src/app_paths.py", "screen_text/__init__.py", "screen_text/engine.py", "screen_text/layout.py",
             "tools/verify.py", "tools/smoke_release.py", "tools/screen_text_lab/__init__.py",
             "tools/screen_text_lab/crop_evaluation.py", "tools/screen_text_lab/corpus.py",
             "tools/screen_text_lab/metrics.py", "tools/screen_text_lab/runner.py",
             "tools/screen_text_lab/engine_adapter.py", "requirements-lock.txt",
             "tools/screen_text_lab/training/__init__.py", "tools/screen_text_lab/training/bundle_candidate.py",
             "tools/screen_text_lab/training/compare.py", "tools/screen_text_lab/training/contracts.py"]
    names += [str(path.relative_to(root)) for path in (root / "tools/screen_text_lab/datasets").glob("*.py")]
    return {name: digest(root / name) for name in names}


def crop_prediction(engine, rgb):
    """정답/메타데이터 없이 제품의 전처리·CTC·경고 계산을 호출한다."""
    from screen_text.layout import TextBox
    from .engine_adapter import pack_prediction
    height, width = rgb.shape[:2]
    text, score = engine._read(rgb, [(0, 0, width, height)], lambda: False)[0]
    text = text.strip()  # OcrEngine.recognize와 동일한 출력 처리
    prediction = pack_prediction([TextBox(0, 0, width, height, text, score)] if text else [])
    prediction["timing_scope"] = "line_crop_recognition_only_not_product_latency"
    return prediction


def worker(directory):
    from tools.verify import ROOT, inside, write_json
    directory = inside(Path(directory), ROOT / "output/harness")
    if Path(os.environ.get("CLIMATENOTE_TEST_APPDATA", "")).resolve() != (directory / "appdata").resolve():
        raise ValueError("격리 AppData가 필요합니다")
    request = read_json(directory / "request.json")
    append_event(directory / "progress.jsonl", {"phase": "loading", "sequence": 0})
    try:
        import numpy as np
        import onnxruntime as ort
        from PIL import Image
        from screen_text.engine import OcrEngine
        model = directory / "model.onnx"
        dictionary = directory / "dictionary.txt"
        if digest(model) != request["model"]["model_sha256"] or digest(dictionary) != request["model"]["dictionary_sha256"]:
            raise ValueError("실행 사본 모델/사전 해시 불일치")
        chars = candidate_charset(dictionary)
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.intra_op_num_threads = request["threads"]
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
        validate_session(session, chars)
        # 검출기는 줄 crop 진단에서 필요 없다. _read 자체는 제품 메서드를 그대로 사용한다.
        engine = object.__new__(OcrEngine)
        engine._rec, engine._charset = ProbabilitySession(session), chars
        for index, case in enumerate(request["cases"], 1):
            append_event(directory / "progress.jsonl", {"phase": "case", "sequence": index, "case_id": case["case_id"]})
            record = dict(case, expected_sha256=json_hash(case["expected"]), status="error", metrics=None)
            try:
                path = contained_file(directory / "cases", case["case_id"] + ".png")
                if digest(path) != case["image_sha256"]:
                    raise ValueError("실행 사본 이미지 해시 불일치")
                with Image.open(path) as image:
                    rgb = np.asarray(image.convert("RGB")).copy()
                started = time.perf_counter()
                prediction = crop_prediction(engine, rgb)
                prediction["total_ms"] = (time.perf_counter() - started) * 1000
                record.update(status="ok", prediction=prediction, metrics=score_case(case, prediction))
            except Exception as error:
                record.update(error_type=type(error).__name__, error_message=str(error))
            append_event(directory / "cases.jsonl", record)
        append_event(directory / "progress.jsonl", {"phase": "finished", "sequence": len(request["cases"]) + 1})
        return 0
    except Exception as error:
        write_json(directory / "worker-error.json", {"type": type(error).__name__, "message": str(error)})
        return 2


def run(dataset, bundle=None, threads=4, timeout=120):
    from tools.verify import ROOT, create_run_dir, doctor, inside, isolated_env, write_json, atomic_text
    from tools.smoke_release import managed_launch
    from .datasets.audit import validate_manifest
    if threads < 1 or threads > 16 or timeout < 1:
        raise ValueError("threads/timeout 범위 오류")
    dataset = inside(Path(dataset), ROOT / "output/screen_text_lab/training_data")
    if dataset.name != "selection":
        raise ValueError("selection 폴더만 열 수 있습니다")
    manifest_before = digest(dataset / "manifest.json")
    validated = validate_manifest(dataset)
    if digest(dataset / "manifest.json") != manifest_before:
        raise ValueError("검증 중 manifest 변경")
    cases = validated["cases"]
    validate_selection(cases)
    audit = {"status": "passed", "cases": len(cases), "manifest_sha256": manifest_before}
    if bundle:
        metadata, files = candidate_bundle(bundle, ROOT / "output/screen_text_lab")
    else:
        from screen_text.engine import verify_models
        product = verify_models()
        files = {"model": product["rec"], "dictionary": product["dict"]}
        metadata = {"id": "product", "role": "P", "model_sha256": digest(files["model"]),
                    "dictionary_sha256": digest(files["dictionary"]), "provenance": "verified_product_manifest"}
    directory = create_run_dir()
    environment = isolated_env(directory)
    before = dependency_snapshot(ROOT)
    inputs_before = {str(path): digest(path) for path in [dataset / "manifest.json", *files.values()]}
    if bundle:
        inputs_before[str(Path(bundle).resolve())] = digest(Path(bundle))
        inputs_before.update(metadata["verified_provenance"]["files"])
    if inputs_before[str(dataset / "manifest.json")] != manifest_before:
        raise ValueError("실행 준비 중 manifest 변경")
    request = {"cases": cases, "model": metadata, "threads": threads, "dataset": str(dataset)}
    write_json(directory / "request.json", request)
    inputs_before[str(directory / "request.json")] = digest(directory / "request.json")
    result = {"kind": "selection_line_crop", "run_id": directory.name, "status": "error", "model": metadata,
              "inputs_before": inputs_before, "source_before": before, "dataset_audit": audit,
              "evaluation_scope": "line_crop", "product_adoption": "not_evaluated",
              "timing_scope": "single_run_with_concurrent_work_not_product_latency"}
    status, progress = "error", {}
    try:
        result["doctor"] = doctor()
        if result["doctor"]["errors"]:
            raise ValueError("doctor 실패")
        (directory / "cases").mkdir()
        for case in cases:
            target = directory / "cases" / (case["case_id"] + ".png")
            shutil.copyfile(contained_file(dataset, case["image"]), target)
            if digest(target) != case["image_sha256"]:
                raise ValueError("복사 중 이미지 변경")
        for key, name in (("model", "model.onnx"), ("dictionary", "dictionary.txt")):
            shutil.copyfile(files[key], directory / name)
        command = [sys.executable, str(ROOT / "tools/smoke_release.py"), "_launch", sys.executable,
                   "-m", "tools.screen_text_lab.crop_evaluation", "_worker", str(directory)]
        deadline, previous = time.monotonic() + timeout, None
        with managed_launch(command, environment, directory / "worker.log") as (_, process):
            while process.poll() is None:
                events = read_jsonl(directory / "progress.jsonl", tolerate_partial=True)
                progress = events[-1] if events else {}
                current = (progress.get("phase"), progress.get("sequence"))
                if current != previous:
                    previous, deadline = current, time.monotonic() + timeout
                    if progress.get("phase") == "case" and progress["sequence"] % 20 == 0:
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
        result["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        raw_records = read_jsonl(directory / "cases.jsonl", tolerate_partial=True)
        try:
            validate_worker_records(cases, raw_records)
        except (KeyError, TypeError, ValueError) as error:
            status = "invalid_records"
            result["record_check_error"] = str(error)
        records = complete_records(cases, raw_records, progress, status)
        try:
            result["source_after"] = dependency_snapshot(ROOT)
            result["inputs_after"] = {path: digest(Path(path)) for path in inputs_before}
            if before != result["source_after"] or inputs_before != result["inputs_after"]:
                status = "inputs_changed"
            for case in cases:
                if digest(contained_file(dataset, case["image"])) != case["image_sha256"]:
                    status = "inputs_changed"
        except (OSError, ValueError) as error:
            status = "inputs_changed"
            result["input_check_error"] = str(error)
        if status == "completed" and any(record["status"] != "ok" for record in records):
            status = "partial"
        result.update(status=status, metrics=summarize(records))
        atomic_text(directory / "cases.jsonl", "".join(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n" for record in records))
        result["cases_sha256"] = digest(directory / "cases.jsonl")
        write_json(directory / "result.json", result)
        atomic_text(directory / "summary.md", f"# 선택 자료 줄 인식\n\n- 실행: {directory.name}\n- 상태: {status}\n"
                    f"- 모델: {metadata['role']} / {metadata['id']}\n- 사례: {len(cases)}\n"
                    "- 제품 전처리/CTC/경고 계산을 사용한 줄 crop 진단. 검출·표 구조·전체 화면·제품 지연시간·채택 검증은 미실행.\n"
                    "- 상세 지표: result.json, 사례별 출력: cases.jsonl\n")
    print(f"{status}: {directory / 'summary.md'}", flush=True)
    return directory, 0 if status == "completed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("run")
    command.add_argument("dataset")
    command.add_argument("--bundle")
    command.add_argument("--threads", type=int, default=4)
    command.add_argument("--timeout", type=int, default=120)
    internal = commands.add_parser("_worker")
    internal.add_argument("directory")
    args = parser.parse_args()
    if args.command == "_worker":
        return worker(args.directory)
    return run(args.dataset, args.bundle, args.threads, args.timeout)[1]


if __name__ == "__main__":
    raise SystemExit(main())
