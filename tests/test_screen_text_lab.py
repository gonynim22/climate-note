"""진단 도구의 작은 자체 검사. 실제 OCR·캡처·대량 자료를 실행하지 않는다."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.screen_text_lab.corpus import CorpusError, digest, json_hash, load_corpus
from tools.screen_text_lab.metrics import edit_counts, score_case, summarize, table_score
from tools.screen_text_lab.compare import classify, pair_records
from tools.screen_text_lab.runner import append_event, base_record, complete_records, read_jsonl, read_records


def make_case(directory, case_id="sample", text="정답", split="dev", group="group-a"):
    from PIL import Image
    path = directory / (case_id + ".png")
    Image.new("RGB", (20, 12), color=(255, 255, len(case_id) % 255)).save(path)
    return {"case_id": case_id, "source_group_id": group, "parent_id": None,
            "split": split, "source_kind": "synthetic", "review_status": "generated",
            "image": path.name, "image_sha256": digest(path), "image_size": [20, 12],
            "expected": {"text": text}, "tags": {"category": "unit", "font_px": 14, "theme": "light"}}


def write_manifest(directory, cases):
    (directory / "manifest.json").write_text(json.dumps({"schema_version": 1,
        "dataset_id": "unit-only", "cases": cases}, ensure_ascii=False), encoding="utf-8")


def record_for(case, text, warnings=0):
    record = base_record(case)
    prediction = {"text": text, "table": [], "boxes": [], "unsure_count": warnings,
                  "total_ms": 1.0, "tsv": text, "spans_utf16": []}
    record.update(status="ok", prediction=prediction, metrics=score_case(case, prediction))
    return record


@pytest.mark.parametrize("left,right,expected", [
    ("abc", "adc", (1, 0, 0)), ("abcd", "acd", (0, 1, 0)),
    ("abc", "abxc", (0, 0, 1)), ("", "abc", (0, 0, 3)),
    ("가 나", "가나", (0, 1, 0)), ("1,000", "1000", (0, 1, 0)),
    ("가", "가", (0, 0, 0)), ("a\r\nb", "a\nb", (0, 0, 0)),
    ("커밋", "커및", (1, 0, 0)), ("ABC", "abc", (3, 0, 0)),
])
def test_edit_distance_known_answers(left, right, expected):
    result = edit_counts(left, right)
    assert (result["substitutions"], result["deletions"], result["insertions"]) == expected
    assert result["errors"] == sum(expected)


def test_empty_and_unbounded_cer():
    assert edit_counts("", "x")["cer"] is None
    assert edit_counts("a", "xyz")["cer"] == 3
    assert edit_counts("", "")["exact"]
    with pytest.raises(ValueError, match="한도"):
        edit_counts("a" * 2001, "b" * 2000)


def test_table_position_empty_cells_and_extra_rows():
    expected = [["A", ""], ["B", "2"]]
    assert table_score(expected, [["A", ""], ["B", "2"]])["accuracy"] == 1
    assert table_score(expected, [["B", "2"], ["A", ""]])["correct"] == 0
    score = table_score(expected, [["A", ""], ["B", "2"], ["extra", "3"]])
    assert score["correct"] == 4 and score["cells"] == 6 and not score["exact"]
    assert table_score(None, []) is None


def test_corpus_valid_and_select(tmp_path):
    case = make_case(tmp_path)
    write_manifest(tmp_path, [case])
    corpus = load_corpus(tmp_path)
    assert corpus.select("bootstrap", "dev") == [case]
    assert corpus.fingerprint()["images"]["sample"] == case["image_sha256"]
    with pytest.raises(CorpusError, match="사례가 없습니다"):
        corpus.select("standard", "holdout")


@pytest.mark.parametrize("mutation", ["hash", "size", "path", "duplicate", "box", "text", "table", "review"])
def test_corpus_rejects_invalid_inputs(tmp_path, mutation):
    case = make_case(tmp_path)
    cases = [case]
    if mutation == "hash":
        case["image_sha256"] = "0" * 64
    elif mutation == "size":
        case["image_size"] = [1, 1]
    elif mutation == "path":
        case["image"] = "../outside.png"
    elif mutation == "duplicate":
        cases.append(copy.deepcopy(case))
    elif mutation == "box":
        case["regions"] = [{"box": [0, 0, 100, 100]}]
    elif mutation == "text":
        case["expected"]["text"] = None
    elif mutation == "table":
        case["expected"]["table"] = [["A"], ["B", "C"]]
    else:
        case["source_kind"] = "program_capture"
    write_manifest(tmp_path, cases)
    with pytest.raises(CorpusError):
        load_corpus(tmp_path)


@pytest.mark.parametrize("mode", ["group", "image", "content", "parent"])
def test_corpus_rejects_split_leakage(tmp_path, mode):
    left = make_case(tmp_path, "one", "alpha", group="left")
    right = make_case(tmp_path, "other", "beta", split="holdout", group="right")
    if mode == "group":
        right["source_group_id"] = left["source_group_id"]
    elif mode == "image":
        right.update(image=left["image"], image_sha256=left["image_sha256"])
    elif mode == "content":
        right["expected"] = copy.deepcopy(left["expected"])
    else:
        right["parent_id"] = left["case_id"]
    write_manifest(tmp_path, [left, right])
    with pytest.raises(CorpusError):
        load_corpus(tmp_path)


def test_unreviewed_data_not_scored_and_warning_does_not_correct(tmp_path):
    case = make_case(tmp_path, text="커밋")
    wrong = record_for(case, "커및", 0)
    assert wrong["metrics"]["wrong_without_warning"]
    assert wrong["prediction"]["text"] == "커및"
    assert record_for(case, "커밋", 1)["metrics"]["correct_with_warning"]
    case["review_status"] = "unreviewed"
    assert record_for(case, "커밋")["metrics"] is None


def test_correct_text_with_wrong_table_is_not_marked_correct(tmp_path):
    from tools.screen_text_lab.report import state_of
    case = make_case(tmp_path, text="A B")
    case["expected"]["table"] = [["A", "B"]]
    record = record_for(case, "A B")
    assert record["metrics"]["exact"]
    assert not record["metrics"]["all_exact"]
    assert record["metrics"]["wrong_without_warning"]
    assert state_of(record) == "unwarned"
    assert summarize([record])["overall"]["wrong"] == 1


def test_summary_keeps_failure_empty_and_group_denominators(tmp_path):
    a = make_case(tmp_path, text="abcd", group="a")
    b = make_case(tmp_path, "second", "xy", group="b")
    empty = make_case(tmp_path, "blank", "", group="blank")
    records = [record_for(a, "abXd"), record_for(b, "xy"), record_for(empty, "ghost"), base_record(a)]
    summary = summarize(records)["overall"]
    assert summary["total"] == 4 and summary["scored"] == 3
    assert summary["errors"] == 1 and summary["reference_chars"] == 6
    assert summary["empty_false_characters"] == 5
    assert summary["macro_group_cer"] == .125
    assert summary["wrong_without_warning"] == 2


def test_comparison_improvement_regression_and_same(tmp_path):
    case = make_case(tmp_path, text="abcd")
    good, wrong = record_for(case, "abcd"), record_for(case, "abcx")
    assert classify(wrong, good) == "improved"
    assert classify(good, wrong) == "regressed"
    assert classify(good, good) == "unchanged"
    assert classify(wrong, record_for(case, "abxd")) == "changed"
    assert classify(base_record(case), good) == "unscored"
    assert pair_records([good], [wrong])[2:] == (0, 0)


@pytest.mark.parametrize("key", ["image_sha256", "expected_sha256", "split", "source_group_id", "tags"])
def test_comparison_rejects_changed_evidence(tmp_path, key):
    case = make_case(tmp_path)
    left, right = record_for(case, "정답"), record_for(case, "정답")
    right[key] = "changed"
    with pytest.raises(ValueError):
        pair_records([left], [right])


def test_comparison_requires_explicit_intersection(tmp_path):
    a, b = make_case(tmp_path), make_case(tmp_path, "second", "다른 내용", group="second")
    left, right = [record_for(a, "정답"), record_for(b, "다른 내용")], [record_for(a, "정답")]
    with pytest.raises(ValueError, match="intersection"):
        pair_records(left, right)
    assert pair_records(left, right, True)[2:] == (1, 0)


def test_incomplete_worker_results_remain_visible(tmp_path):
    a, b = make_case(tmp_path), make_case(tmp_path, "second")
    records = complete_records([a, b], [record_for(a, "정답")], {"case_id": "second"}, "timeout")
    assert [record["status"] for record in records] == ["ok", "timeout"]
    assert records[1]["metrics"] is None
    (tmp_path / "cases.jsonl").write_text(json.dumps(records[0]) + "\n{", encoding="utf-8")
    assert len(read_records(tmp_path, tolerate_partial=True)) == 1
    with pytest.raises(json.JSONDecodeError):
        read_records(tmp_path)


def test_progress_events_read_during_write_and_partial_utf8(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path = tmp_path / "progress.jsonl"
    def writer():
        for sequence in range(100):
            append_event(path, {"sequence": sequence, "text": "한글"})
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(writer)
        observed = []
        while not future.done():
            events = read_jsonl(path, tolerate_partial=True)
            if events:
                observed.append(events[-1]["sequence"])
        future.result()
    assert observed == sorted(observed)
    assert [event["sequence"] for event in read_jsonl(path)] == list(range(100))
    with open(path, "ab") as stream:
        stream.write(b'{"text":"\xed\x95')
    assert len(read_jsonl(path, tolerate_partial=True)) == 100
    with pytest.raises(UnicodeDecodeError):
        read_jsonl(path)


def test_complete_corrupt_event_is_not_silently_ignored(tmp_path):
    path = tmp_path / "progress.jsonl"
    path.write_bytes(b'{broken}\n')
    with pytest.raises(json.JSONDecodeError):
        read_jsonl(path, tolerate_partial=True)


def test_report_escapes_text_and_handles_no_timing(tmp_path):
    from tools.screen_text_lab.report import render_report
    case = make_case(tmp_path, text='<script>alert("x")</script>')
    (tmp_path / "cases").mkdir()
    (tmp_path / "sample.png").replace(tmp_path / "cases/sample.png")
    record = base_record(case)
    result = {"run_id": "unit", "status": "error", "kind": "ocr_run", "metrics": summarize([record]),
              "limitations": ["unit data"]}
    render_report(tmp_path, result, [record])
    source = (tmp_path / "cases/sample.html").read_text(encoding="utf-8")
    assert '<script>alert(' not in source
    assert '&lt;script&gt;' in source
    assert "실행 실패" not in source  # not_run is explicitly displayed instead.
    assert "미실행" in source
    assert "미측정" in (tmp_path / "report.html").read_text(encoding="utf-8")


def test_report_comparison_contains_both_predictions(tmp_path):
    from tools.screen_text_lab.report import render_report
    case = make_case(tmp_path, text="맞는 글자")
    (tmp_path / "cases").mkdir()
    (tmp_path / "sample.png").replace(tmp_path / "cases/sample.png")
    left, right = record_for(case, "맞는 글자"), record_for(case, "틀린 글자")
    result = {"run_id": "compare-unit", "status": "completed", "kind": "ocr_comparison",
              "metrics": summarize([right]), "comparison": {"baseline": "left", "candidate": "right",
              "counts": {"regressed": 1}, "excluded_baseline": 0, "excluded_candidate": 0}}
    render_report(tmp_path, result, [right], [left], {"sample": "regressed"})
    source = (tmp_path / "cases/sample.html").read_text(encoding="utf-8")
    assert "기준 결과" in source and "후보 결과" in source
    assert "맞는 글자" in source and "틀린 글자" in source
    assert 'data-state="regressed"' in (tmp_path / "report.html").read_text(encoding="utf-8")


def test_all_imports_and_help_do_not_load_app_ocr_or_images():
    code = '''
import importlib.abc, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'screen_text', 'onnxruntime', 'numpy', 'PySide6', 'PIL', 'security', 'database'}:
            raise AssertionError('unexpected runtime import: ' + fullname)
sys.meta_path.insert(0, Guard())
from tools.screen_text_lab import corpus, metrics, engine_adapter, runner, generate, compare, report, review_store, conditions, condition_analysis, experiments, diagnostic_analysis, region_diagnostics, region_report, preprocessing, ctc_analysis, ctc_probe, ctc_report, recognizers, recognizer_report, disagreement, disagreement_report, disagreement_benchmark, warning_features, warning_rules, warning_rule_run, warning_rule_report, capture_kit
from tools.screen_text_lab.__main__ import main
try:
    main(['--help'])
except SystemExit as exit:
    assert exit.code == 0
assert not any(key in sys.modules for key in ('onnxruntime','screen_text.engine','database','security'))
'''
    result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, encoding="utf-8", errors="replace", timeout=20)
    assert result.returncode == 0, result.stderr


def test_normal_harness_and_build_do_not_call_lab():
    from tools.verify import pytest_command
    root = Path(__file__).resolve().parents[1]
    for profile in ("quick", "data", "full", "release"):
        command = pytest_command(profile, [], root / "output/harness/unit-command-only")
        assert "tools.screen_text_lab" not in " ".join(command)
    for name in ("main.py", "build_app.py", "build.bat", "build.spec", "tools/verify.py"):
        assert "screen_text_lab" not in (root / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("candidate,diagnose", [("baseline", False), ("upscale-2", False), ("det-1600", False),
                                               ("unclip-1.2", False), ("baseline", True)])
def test_worker_uses_fake_engine_and_retains_case_errors(tmp_path, monkeypatch, candidate, diagnose):
    from tools.screen_text_lab import engine_adapter
    from tools.screen_text_lab.runner import worker
    from tools.verify import write_json
    from tools import verify
    monkeypatch.setattr(verify, "ROOT", tmp_path)
    directory = tmp_path / "output/harness/worker"
    directory.mkdir(parents=True)
    (directory / "cases").mkdir()
    first = make_case(directory / "cases", "first", "first")
    second = make_case(directory / "cases", "second", "second")
    write_json(directory / "request.json", {"cases": [first, second], "threads": 1, "candidate": candidate,
                                           "diagnose_regions": diagnose})
    monkeypatch.setenv("CLIMATENOTE_TEST_APPDATA", str(directory / "appdata"))
    selected = candidate
    class FakeEngine:
        load_ms = 0
        def __init__(self, threads, candidate):
            assert threads == 1
            assert candidate == selected
        def recognize(self, path, region_case=None):
            assert (region_case is not None) == diagnose
            if region_case is not None:
                assert region_case["case_id"] == path.stem
            if path.stem == "first":
                raise ValueError("intentional fake case failure")
            return {"text": "second", "table": [], "boxes": [], "unsure_count": 0, "total_ms": 1}
    monkeypatch.setattr(engine_adapter, "ProductEngine", FakeEngine)
    assert worker(directory) == 0
    records = read_records(directory)
    assert [record["status"] for record in records] == ["error", "ok"]
    assert records[1]["metrics"]["exact"]
    assert read_jsonl(directory / "progress.jsonl")[-1]["phase"] == "finished"


@pytest.mark.parametrize("mode,expected_status", [("complete", "completed"), ("change", "inputs_changed"),
                                                  ("cancel", "cancelled"), ("timeout", "timeout"),
                                                  ("diagnosis_error", "partial")])
def test_runner_handles_completion_changes_cancel_and_timeout_without_ocr(tmp_path, monkeypatch, mode, expected_status):
    from contextlib import contextmanager
    from tools import verify, smoke_release
    from tools.screen_text_lab import runner
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    case = make_case(corpus_dir)
    write_manifest(corpus_dir, [case])
    directory = tmp_path / "output/harness/run"
    directory.mkdir(parents=True)
    monkeypatch.setattr(verify, "ROOT", tmp_path)
    monkeypatch.setattr(verify, "create_run_dir", lambda: directory)
    monkeypatch.setattr(verify, "doctor", lambda: {"errors": []})
    snapshots = iter([{"files": {"source": "old"}}, {"files": {"source": "new" if mode == "change" else "old"}}])
    monkeypatch.setattr(runner, "source_inputs", lambda: next(snapshots))
    ticks = iter(range(0, 10000, 2))
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner.time, "sleep", lambda _: None)
    @contextmanager
    def fake_launch(command, env, log):
        assert env["LOCALAPPDATA"] == str(directory / "appdata")
        assert command[-3:] == ["tools.screen_text_lab", "_worker", str(directory)]
        if mode == "cancel":
            raise KeyboardInterrupt
        if mode != "timeout":
            record = record_for(case, "정답")
            if mode == "diagnosis_error":
                record["prediction"]["region_diagnostic"] = {"version": 1, "status": "error", "error_type": "RuntimeError"}
            runner.append_event(directory / "cases.jsonl", record)
        class Process:
            returncode = 0
            def poll(self):
                return None if mode == "timeout" else 0
        yield None, Process()
    monkeypatch.setattr(smoke_release, "managed_launch", fake_launch)
    output, code = runner.run(corpus_dir, timeout=1, diagnose_regions=mode == "diagnosis_error")
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == expected_status
    assert code == (0 if mode == "complete" else 130 if mode == "cancel" else 1)
    assert (output / "report.html").exists()
    assert result["cases_sha256"] == digest(output / "cases.jsonl")
