"""Full-path manual tool boundaries with tiny fake captures/sessions only."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from tools.screen_text_lab import full_candidate as tool
from tools.screen_text_lab.corpus import digest, json_hash
from tools.screen_text_lab.metrics import score_case


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def baseline_fixture(tmp_path, monkeypatch):
    directory = tmp_path / "output/harness" / tool.BASELINE_ID
    (directory / "cases").mkdir(parents=True)
    sources = {}
    for name in tool.BASELINE_DEPENDENCIES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("가\n나\n" if name.endswith("dict.txt") else "FAKE dependency", encoding="utf-8")
        sources[name] = digest(path)
    cases, records = [], []
    for index in range(2):
        identifier = f"fake-dev-{index}"
        image_path = directory / "cases" / (identifier + ".png")
        Image.new("RGB", (64, 24), "white").save(image_path)
        case = {"case_id": identifier, "source_group_id": f"group-{index}", "parent_id": None,
                "split": "dev", "source_kind": "program_capture", "review_status": "reviewed",
                "tags": {"category": "cli", "source_app": "Windows Notepad", "capture_encoding": "jpeg"},
                "expected": {"text": "가나"}, "image_size": [64, 24], "image_sha256": digest(image_path),
                "image": "forbidden-original-corpus.png", "review": {"reviewer": "assistant_visual_review"}}
        prediction = {"text": "가", "unsure_count": 0, "table": []}
        record = {key: value for key, value in case.items() if key not in {"image", "review"}}
        record.update(status="ok", expected_sha256=json_hash(case["expected"]), prediction=prediction,
                      metrics=score_case(case, prediction))
        cases.append(case)
        records.append(record)
    path = directory / "cases.jsonl"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
    request = {"cases": cases, "candidate": "baseline", "recognizer": None, "input_profile": "native",
               "diagnose_ctc": False, "diagnose_regions": False}
    write(directory / "request.json", request)
    result = {"run_id": tool.BASELINE_ID, "kind": "ocr_run", "status": "completed", "split": "dev",
              "cases_sha256": digest(path), "source_before": {"files": sources}, "source_after": {"files": sources},
              "inputs_before": {"manifest": "do-not-open"}, "inputs_after": {"manifest": "do-not-open"},
              "corpus_path": str(tmp_path / "never-open-original-or-holdout")}
    write(directory / "result.json", result)
    monkeypatch.setattr(tool, "BASELINE_CASES_SHA256", digest(path))
    monkeypatch.setattr(tool, "BASELINE_COUNT", 2)
    return directory, cases, records


def test_saved_dev_reuse_reads_only_approved_records_and_copies(tmp_path, monkeypatch):
    directory, _, _ = baseline_fixture(tmp_path, monkeypatch)
    loaded = tool.load_baseline(tmp_path)
    assert loaded["directory"] == directory
    assert loaded["source_groups"] == 2 and loaded["expected_table_cases"] == 0
    assert len(loaded["cases"]) == 2
    assert all(case["review_provenance"]["human_reviewed"] is False for case in loaded["cases"])
    assert all(case["evaluation_scope"] == "fixed_capture_region" for case in loaded["cases"])
    assert all("image" not in case for case in loaded["cases"])
    assert not (tmp_path / "never-open-original-or-holdout").exists()


@pytest.mark.parametrize("problem", ["status", "split", "candidate", "model", "source_changed", "input_changed",
                                      "missing_record", "duplicate", "record_changed", "request_changed", "holdout_case",
                                      "table", "image", "image_size", "current_product", "metrics"])
def test_saved_baseline_must_be_complete_unchanged_native_dev(tmp_path, monkeypatch, problem):
    directory, cases, records = baseline_fixture(tmp_path, monkeypatch)
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    if problem == "status": result["status"] = "partial"
    elif problem == "split": result["split"] = "holdout"
    elif problem == "candidate": request["candidate"] = "try-other"
    elif problem == "model": request["recognizer"] = "other-model"
    elif problem == "source_changed": result["source_after"]["files"]["screen_text/engine.py"] = "0" * 64
    elif problem == "input_changed": result["inputs_after"] = {}
    elif problem == "missing_record": records.pop()
    elif problem == "duplicate": records[1] = records[0]
    elif problem == "record_changed": records[0]["expected"] = {"text": "other"}
    elif problem == "request_changed": request["cases"][0]["expected"] = {"text": "other"}
    elif problem == "holdout_case": request["cases"][0]["split"] = "holdout"
    elif problem == "table": request["cases"][0]["expected"]["table"] = [["unapproved"]]
    elif problem == "image": (directory / "cases/fake-dev-0.png").write_bytes(b"changed")
    elif problem == "image_size": request["cases"][0]["image_size"] = [2, 2]
    elif problem == "current_product": (tmp_path / "screen_text/engine.py").write_text("changed")
    elif problem == "metrics": records[0]["metrics"]["errors"] = 0
    write(directory / "result.json", result)
    write(directory / "request.json", request)
    (directory / "cases.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
    with pytest.raises(ValueError):
        tool.load_baseline(tmp_path)


class FakeDetector:
    def __init__(self):
        self.calls = []

    def run(self, _, inputs):
        self.calls.append(inputs["x"])
        values = np.zeros((1, 1, 32, 64), dtype=np.float32)
        values[:, :, 6:18, 5:50] = .95
        return [values]


class FakeRecognizer:
    def __init__(self):
        self.calls = []

    def get_inputs(self):
        return [SimpleNamespace(name="x", type="tensor(float)", shape=["N", 3, 48, "W"])]

    def get_outputs(self):
        return [SimpleNamespace(type="tensor(float)", shape=["N", "T", 4])]

    def run(self, _, inputs):
        self.calls.append(inputs["x"])
        values = np.zeros((inputs["x"].shape[0], 5, 4), dtype=np.float32)
        for step, index in enumerate([0, 1, 1, 0, 2]):
            values[:, step, index] = 1
        return [values]


def fake_runtime(monkeypatch):
    detector, recognizer = FakeDetector(), FakeRecognizer()
    fake = SimpleNamespace(disable_telemetry_events=lambda: None, SessionOptions=SimpleNamespace,
        InferenceSession=lambda filename, *args, **kwargs: detector if Path(filename).name == "det.onnx" else recognizer)
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    return detector, recognizer


def test_product_detect_read_and_layout_all_execute_from_pixels():
    from screen_text.engine import OcrEngine
    engine = object.__new__(OcrEngine)
    detector, recognizer = FakeDetector(), FakeRecognizer()
    engine._det, engine._rec, engine._charset = detector, tool.ProbabilitySession(recognizer), ["가", "나", " "]
    prediction = tool.full_prediction(engine, np.full((24, 64, 3), 255, np.uint8))
    assert prediction["text"] == "가나" and prediction["tsv"] == "가나"
    assert prediction["boxes"] and prediction["blocks"] and prediction["unsure_count"] == 0
    assert len(detector.calls) == 1 and len(recognizer.calls) == 1
    assert recognizer.calls[0].dtype == np.float32 and recognizer.calls[0].shape[1:3] == (3, 48)
    assert prediction["timing_scope"] == "single_fixed_capture_run_not_product_latency"


@pytest.mark.parametrize("tamper", [False, True])
def test_orchestrator_isolated_worker_records_and_report_fail_closed(tmp_path, monkeypatch, tamper):
    from tools import verify, smoke_release
    from screen_text import engine as product
    baseline_dir, _, _ = baseline_fixture(tmp_path, monkeypatch)
    detector, recognizer = fake_runtime(monkeypatch)
    output = tmp_path / "output/harness/fake-candidate-run"
    output.mkdir()
    bundle = tmp_path / "output/screen_text_lab/fixture/bundle.json"
    bundle.parent.mkdir(parents=True)
    model, dictionary = bundle.parent / "rec.onnx", bundle.parent / "dict.txt"
    model.write_bytes(b"FAKE MODEL")
    dictionary.write_text("가\n나\n", encoding="utf-8")
    write(bundle, {"fake": True})
    metadata = {"id": "fake-candidate", "role": "F", "model_sha256": digest(model),
                "dictionary_sha256": digest(dictionary), "bundle_sha256": digest(bundle),
                "verified_provenance": {"files": {str(model): digest(model), str(dictionary): digest(dictionary)}}}
    monkeypatch.setattr(verify, "ROOT", tmp_path)
    monkeypatch.setattr(verify, "create_run_dir", lambda: output)
    monkeypatch.setattr(verify, "doctor", lambda: {"errors": []})
    monkeypatch.setattr(tool, "snapshot", lambda _: {"fake-code": "immutable"})
    monkeypatch.setattr(tool, "candidate_bundle", lambda *args: (metadata, {"model": model, "dictionary": dictionary}))
    monkeypatch.setattr(product, "verify_models", lambda: {"det": tmp_path / "screen_text/models/det.onnx"})

    @contextmanager
    def launch(command, environment, log):
        monkeypatch.setenv("CLIMATENOTE_TEST_APPDATA", str(output / "appdata"))
        code = tool.worker(output, command[-1])
        if tamper:
            path = output / "cases.jsonl"
            rows = tool.read_jsonl(path)
            rows[0]["expected"] = {"text": "silently-replaced"}
            path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        yield None, SimpleNamespace(returncode=code, poll=lambda: code)

    monkeypatch.setattr(smoke_release, "managed_launch", launch)
    saved, code = tool.run(bundle)
    result = json.loads((saved / "result.json").read_text(encoding="utf-8"))
    assert (code == 0) is not tamper
    assert result["status"] == ("artifact_error" if tamper else "completed")
    assert result["product_adoption"] == "not_evaluated"
    assert result["selection"]["expected_table_cases"] == 0
    assert result["cases_sha256"] == digest(saved / "cases.jsonl")
    assert len(detector.calls) == 2 and len(recognizer.calls) == 2
    assert (saved / "paired/report.html").exists()
    summary = (saved / "summary.md").read_text(encoding="utf-8")
    assert "기존 터미널 문구/Notepad" in summary and "한컴한글/PDF/Word" in summary
    assert digest(baseline_dir / "cases.jsonl") == tool.BASELINE_CASES_SHA256


def test_worker_refuses_changed_request_before_runtime_import(tmp_path, monkeypatch):
    from tools import verify
    directory = tmp_path / "output/harness/worker"
    directory.mkdir(parents=True)
    write(directory / "request.json", {})
    monkeypatch.setattr(verify, "ROOT", tmp_path)
    monkeypatch.setenv("CLIMATENOTE_TEST_APPDATA", str(directory / "appdata"))
    with pytest.raises(ValueError, match="exact parent request"):
        tool.worker(directory, "0" * 64)
