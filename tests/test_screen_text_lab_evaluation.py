"""Independent saved-record checks. No model, corpus, capture or final data."""
from copy import deepcopy
import itertools
import json
import random
import subprocess
import sys

import pytest

from tools.screen_text_lab.corpus import digest, json_hash
from tools.screen_text_lab.evaluation import DEFAULT_RECIPE, analyze_pair, assess, compare_three_way, load_crop_run
from tools.screen_text_lab.evaluation.report import render_report, save_report
from tools.screen_text_lab.metrics import score_case


def make_case(identifier, text="가나", *, group=None, real=False, table=None, critical=()):
    expected = {"text": text}
    if table is not None:
        expected["table"] = table
    return {"case_id": identifier, "document_id": "doc-" + (group or identifier),
            "source_group_id": group or identifier, "template_family_id": "template-" + (group or identifier),
            "split": "selection", "source_kind": "program_capture" if real else "synthetic",
            "review_status": "reviewed" if real else "generated", "image_sha256": json_hash(identifier),
            "expected": expected, "tags": {"category": "body", "app": "hwp", "condition": "native"},
            "critical_tags": list(critical), "evaluation_scope": "screen" if real else "line_crop",
            "review_provenance": {"human_reviewed": real, "reviewer_kind": "human" if real else "generator"}}


def record(case, text, *, warning=0, table=None, status="ok"):
    values = {key: deepcopy(case[key]) for key in ("case_id", "source_group_id", "split", "source_kind", "tags",
                                                 "review_status", "image_sha256", "expected")}
    values.update(expected_sha256=json_hash(case["expected"]), status=status,
                  prediction={"text": text, "unsure_count": warning})
    if table is not None:
        values["prediction"]["table"] = table
    return values


def small_recipe(cases):
    recipe = deepcopy(DEFAULT_RECIPE)
    recipe.update(bootstrap_resamples=200, minimum_real_groups=2,
                  minimum_groups_per_app={"hwp": 2}, minimum_table_groups=1,
                  required_critical_tags=["numbers"], benchmark_case_ids=[case["case_id"] for case in cases])
    return recipe


def sample_study():
    cases = [make_case(str(i), real=True, critical=["numbers"], table=[["가나"]]) for i in range(4)]
    left = [record(case, "가X", warning=1, table=[["가나"]]) for case in cases]
    right = [record(case, "가나", table=[["가나"]]) for case in cases]
    return cases, left, right, small_recipe(cases)


def evidence_for(analysis, *, candidate_ms=100):
    recipe = analysis["recipe"]
    return {"input_sha256": analysis["input_sha256"], "candidate_model_bytes": 13_401_252,
            "clipping": {row["case_id"]: False for row in analysis["rows"]},
            "benchmark": {"status": "completed", "case_ids": recipe["benchmark_case_ids"],
                          "warmup_pairs": 3, "threads": 4, "cpu": "FAKE TEST CPU",
                          "samples": [{"case_id": identifier, "repeat": repeat,
                                       "first": "baseline" if repeat % 2 == 0 else "candidate",
                                       "baseline_ms": 100, "candidate_ms": candidate_ms}
                                      for identifier in recipe["benchmark_case_ids"]
                                      for repeat in range(recipe["benchmark_repeats"])]}}


def test_exact_canonical_metrics_nfc_lf_spaces_empty_and_cer_over_one():
    cases = [make_case("unicode", "가\r\n나  다"), make_case("empty", ""), make_case("long", "a")]
    left = [record(cases[0], "가\n나 다"), record(cases[1], "spurious"), record(cases[2], "xxxx")]
    right = deepcopy(left)
    result = analyze_pair(left, right, cases)
    for row, case, source in zip(result["rows"], sorted(cases, key=lambda x: x["case_id"]), sorted(left, key=lambda x: x["case_id"])):
        assert row["baseline"] == score_case(case, source["prediction"])
    assert result["baseline"]["empty_false_characters"] == 8
    assert result["baseline"]["no_space"]["errors"] == 4
    assert result["baseline"]["strict"]["errors"] == 5
    assert next(row for row in result["rows"] if row["case_id"] == "long")["baseline"]["cer"] == 4


def test_critical_text_improvement_cannot_hide_table_content_or_shape_regression():
    case = make_case("table", "1234", table=[["1", "2"], ["3", "4"]], critical=["numbers"])
    old = record(case, "XXXX", table=[["1", "2"], ["3", "4"]])
    new = record(case, "1234", table=[["1", "2", "3", "4"]])
    result = analyze_pair([old], [new], [case])
    assert result["candidate"]["strict"]["errors"] < result["baseline"]["strict"]["errors"]
    assert result["transitions"]["counts"]["table_content_regressions"] == 1
    assert result["transitions"]["counts"]["table_shape_regressions"] == 1
    assert result["transitions"]["counts"]["table_new_wrong"] == 1


def test_shape_regression_is_reported_even_when_both_tables_are_already_wrong():
    case = make_case("table", "ab", table=[["a"], ["b"]])
    result = analyze_pair([record(case, "ab", table=[["x"]])], [record(case, "ab", table=[])], [case])
    assert result["transitions"]["counts"]["table_shape_regressions"] == 1
    assert result["transitions"]["counts"]["table_content_regressions"] == 0


def test_recovering_table_cells_cannot_hide_newly_wrong_previously_correct_cell():
    case = make_case("table", "1 2 3", real=True, table=[["1", "2", "3"]])
    left = record(case, "X Y 3", warning=1, table=[["X", "Y", "3"]])
    right = record(case, "1 2 8", warning=1, table=[["1", "2", "8"]])
    recipe = small_recipe([case])
    result = analyze_pair([left], [right], [case], recipe)
    assert result["candidate"]["table"]["wrong_cells"] < result["baseline"]["table"]["wrong_cells"]
    counts = result["transitions"]["counts"]
    assert counts["table_content_regressions"] == 0
    assert counts["table_recovered_cells"] == 2 and counts["table_new_wrong_cells"] == 1
    assert assess(result)["gates"]["tables"]["status"] == "failed"


def test_total_table_shape_gain_cannot_hide_a_new_extra_cell():
    case = make_case("table", "1", real=True, table=[["1"]])
    left = record(case, "1", table=[["1", "x", "y"]])
    right = record(case, "1", table=[["1"], ["z"]])
    recipe = small_recipe([case])
    result = analyze_pair([left], [right], [case], recipe)
    counts = result["transitions"]["counts"]
    assert counts["table_content_regressions"] == 0
    assert counts["table_new_extra_cells"] == 1
    assert assess(result)["gates"]["tables"]["status"] == "failed"


def test_warning_transitions_distinguish_same_error_losing_warning_and_false_alarm():
    cases = [make_case("silent"), make_case("false")]
    left = [record(cases[0], "XX", warning=1), record(cases[1], "가나")]
    right = [record(cases[0], "XX"), record(cases[1], "가나", warning=1)]
    result = analyze_pair(left, right, cases)
    assert result["transitions"]["counts"]["new_silent_errors"] == 1
    assert result["transitions"]["counts"]["new_false_warnings"] == 1
    assert assess(result)["gates"]["warnings"]["status"] == "failed"


def test_oov_keeps_compatibility_characters_and_entire_primary_truth():
    case = make_case("units", "온도 20℃ 면적 3㎡", critical=["units"])
    left = [record(case, "온도 20C 면적 3m")]
    right = [record(case, "온도 20℃ 면적 3㎡")]
    result = analyze_pair(left, right, [case], supported_characters=set("온도 20 면적 3Cm"))
    assert result["rows"][0]["oov_characters"] == ["℃", "㎡"]
    assert result["candidate"]["strict"]["errors"] == 0
    assert result["baseline"]["strict"]["errors"] == 2
    assert result["slices"]["vocabulary:oov"]["candidate"]["cases"] == 1
    assert result["rows"][0]["metadata"]["expected"]["text"] == case["expected"]["text"]


def test_both_runs_missing_same_cases_is_not_a_complete_comparison():
    cases, left, right, recipe = sample_study()
    result = analyze_pair(left[:-1], right[:-1], cases, recipe)
    assert result["excluded_pairs"] == 1
    assert len(result["integrity_issues"]) == 2
    assert assess(result)["gates"]["complete_inputs"]["status"] == "failed"


@pytest.mark.parametrize("problem", ["failed", "unreviewed", "missing_warning", "missing_table", "metadata", "hash", "metrics", "extra"])
def test_missing_or_incompatible_measurements_never_pass(problem):
    cases, left, right, recipe = sample_study()
    if problem == "failed":
        right[0]["status"] = "not_run"
    elif problem == "unreviewed":
        cases[0]["review_status"] = "unreviewed"
        left[0]["review_status"] = right[0]["review_status"] = "unreviewed"
    elif problem == "missing_warning":
        del right[0]["prediction"]["unsure_count"]
    elif problem == "missing_table":
        del right[0]["prediction"]["table"]
    elif problem == "metadata":
        right[0]["source_group_id"] = "changed"
    elif problem == "hash":
        right[0]["expected_sha256"] = "0" * 64
    elif problem == "metrics":
        right[0]["metrics"] = {"errors": 0}
    elif problem == "extra":
        right.append(record(make_case("unexpected"), "가나"))
    result = analyze_pair(left, right, cases, recipe, supported_characters="가나")
    decision = assess(result, evidence_for(result))
    assert decision["status"] != "passed"
    assert decision["gates"]["complete_inputs"]["status"] == "failed"


def test_connected_document_source_template_links_and_variants_not_independent():
    cases = [make_case(str(i)) for i in range(12)]
    for i, case in enumerate(cases):
        case["document_id"] = "same-doc" if i < 6 else "other-doc"
        case["template_family_id"] = "same-template" if i in (5, 6) else f"template-{i}"
    left = [record(case, "가X") for case in cases]
    right = [record(case, "가나") for case in cases]
    result = analyze_pair(left, right, cases)
    assert result["bootstrap"]["groups"] == 1
    assert result["bootstrap"]["delta_cer_ci"] is None
    assert result["baseline"]["groups"] == 1


def test_bootstrap_is_order_independent_and_variants_dont_multiply_groups():
    cases, left, right, recipe = sample_study()
    one = analyze_pair(left, right, cases, recipe)
    duplicate_cases, duplicate_left, duplicate_right = [], [], []
    for i, case in enumerate(cases):
        for variant in range(5):
            new = deepcopy(case)
            new["case_id"] = case["case_id"] + f"-{variant}"
            duplicate_cases.append(new)
            duplicate_left.append(record(new, "가X", table=[["가나"]]))
            duplicate_right.append(record(new, "가나", table=[["가나"]]))
    two = analyze_pair(list(reversed(duplicate_left)), list(reversed(duplicate_right)), list(reversed(duplicate_cases)), recipe)
    assert one["bootstrap"] == two["bootstrap"]
    assert two["baseline"]["groups"] == 4
    assert two["baseline"]["cases"] == 20


def test_bootstrap_counterexample_large_variants_cannot_hide_direction_uncertainty():
    cases = [make_case(str(i)) for i in range(2)]
    left = [record(cases[0], "XX"), record(cases[1], "가나")]
    right = [record(cases[0], "가나"), record(cases[1], "가X")]
    recipe = small_recipe(cases)
    result = analyze_pair(left, right, cases, recipe)
    assert result["bootstrap"]["relative_reduction"] == .5
    assert result["bootstrap"]["delta_cer_ci"] == [-1, .5]
    assert result["bootstrap"]["undefined_relative_resamples"] > 0
    assert result["bootstrap"]["relative_reduction_ci"] is None


def test_cluster_bootstrap_matches_independent_exhaustive_two_group_distribution():
    # Two equiprobable groups: each two-draw bootstrap has three possible deltas.
    groups = [(2, 2, 0), (2, 0, 1)]
    exact = sorted((sum(groups[i][2] - groups[i][1] for i in draw) / sum(groups[i][0] for i in draw))
                   for draw in itertools.product(range(2), repeat=2))
    assert exact == [-1, -.25, -.25, .5]
    cases = [make_case(str(i)) for i in range(2)]
    result = analyze_pair([record(cases[0], "XX"), record(cases[1], "가나")],
                          [record(cases[0], "가나"), record(cases[1], "가X")], cases, small_recipe(cases))
    assert result["bootstrap"]["delta_cer_ci"] == [exact[0], exact[-1]]


def test_micro_and_macro_group_cer_are_different_hand_computed_metrics():
    cases = [make_case("long", "aaaa"), make_case("short", "b")]
    records = [record(cases[0], "aaax"), record(cases[1], "x")]
    result = analyze_pair(records, records, cases)
    assert result["baseline"]["strict"]["cer"] == .4
    assert result["baseline"]["strict"]["macro_group_cer"] == .625


def test_net_text_gain_cannot_certify_critical_token_safety():
    cases, left, right, recipe = sample_study()
    for case, baseline, candidate in zip(cases, left, right):
        case["expected"]["text"] = "가나다123"
        baseline["expected"] = candidate["expected"] = deepcopy(case["expected"])
        baseline["expected_sha256"] = candidate["expected_sha256"] = json_hash(case["expected"])
        baseline["prediction"]["text"] = "XXX123"
        candidate["prediction"]["text"] = "가나다128"
        candidate["prediction"]["unsure_count"] = 1
    result = analyze_pair(left, right, cases, recipe, supported_characters="가나다1238")
    assert result["candidate"]["strict"]["errors"] < result["baseline"]["strict"]["errors"]
    assert result["transitions"]["counts"]["critical_regressions"] == 0
    evidence = evidence_for(result)
    assert assess(result, evidence)["gates"]["critical_details"]["status"] == "missing"
    evidence["critical_review"] = {"method": "annotated_spans", "cases": {case["case_id"]: True for case in cases}}
    assert assess(result, evidence)["gates"]["critical_details"]["status"] == "failed"
    evidence["critical_review"]["cases"] = {case["case_id"]: False for case in cases}
    assert assess(result, evidence)["gates"]["critical_details"]["status"] == "passed"


def test_actual_final_requires_document_and_template_metadata():
    cases, left, right, recipe = sample_study()
    for case in cases:
        del case["document_id"]
    result = analyze_pair(left, right, cases, recipe, supported_characters="가나")
    decision = assess(result, evidence_for(result))
    assert decision["gates"]["grouping_metadata"]["status"] == "missing"
    assert decision["status"] == "incomplete"


def test_actual_accuracy_cannot_be_hidden_by_large_synthetic_improvement():
    cases, left, right, recipe = sample_study()
    for i in range(4):
        left[i]["prediction"]["text"] = "가나"
        right[i]["prediction"]["text"] = "가X"
    for i in range(30):
        case = make_case(f"synthetic-{i}")
        cases.append(case)
        left.append(record(case, "XX"))
        right.append(record(case, "가나"))
    result = analyze_pair(left, right, cases, recipe, supported_characters="가나")
    assert result["bootstrap"]["relative_reduction"] > .2
    decision = assess(result, evidence_for(result))
    assert decision["gates"]["actual_accuracy"]["status"] == "failed"
    assert decision["gates"]["strict_errors"]["status"] == "failed"


def test_fake_complete_quality_fixture_passes_but_never_approves_deployment():
    cases, left, right, recipe = sample_study()
    result = analyze_pair(left, right, cases, recipe, supported_characters="가나")
    decision = assess(result, evidence_for(result))
    assert decision["status"] == "passed", decision
    assert not decision["deployment_approved"]


def test_line_crop_study_and_missing_evidence_stay_incomplete():
    cases, left, right, recipe = sample_study()
    for case in cases:
        case["evaluation_scope"] = "line_crop"
    result = analyze_pair(left, right, cases, recipe, supported_characters="가나")
    decision = assess(result)
    assert decision["status"] == "incomplete"
    assert decision["gates"]["screen_scope"]["status"] == "missing"
    assert decision["gates"]["latency"]["status"] == "missing"
    assert decision["gates"]["clipping"]["status"] == "missing"


@pytest.mark.parametrize("problem", ["binding", "clipping", "size", "latency", "missing_repeat", "duplicate", "order", "nan", "workload"])
def test_evidence_fail_closed(problem):
    cases, left, right, recipe = sample_study()
    result = analyze_pair(left, right, cases, recipe, supported_characters="가나")
    evidence = evidence_for(result)
    if problem == "binding":
        evidence["input_sha256"] = "changed"
    elif problem == "clipping":
        del evidence["clipping"]["0"]
    elif problem == "size":
        evidence["candidate_model_bytes"] = 15_000_001
    elif problem == "latency":
        for sample in evidence["benchmark"]["samples"]:
            sample["candidate_ms"] = 111
    elif problem == "missing_repeat":
        evidence["benchmark"]["samples"].pop()
    elif problem == "duplicate":
        evidence["benchmark"]["samples"].append(evidence["benchmark"]["samples"][0])
    elif problem == "order":
        evidence["benchmark"]["samples"][0]["first"] = "candidate"
    elif problem == "nan":
        evidence["benchmark"]["samples"][0]["candidate_ms"] = float("nan")
    elif problem == "workload":
        evidence["benchmark"]["case_ids"] = ["0"]
    assert assess(result, evidence)["status"] != "passed"


def test_p95_latency_gate_catches_tail_even_with_unchanged_median():
    cases, left, right, recipe = sample_study()
    result = analyze_pair(left, right, cases, recipe, supported_characters="가나")
    evidence = evidence_for(result)
    for sample in evidence["benchmark"]["samples"][-2:]:
        sample["candidate_ms"] = 200
    decision = assess(result, evidence)
    assert decision["gates"]["latency"]["detail"]["median_ratio"] == 1
    assert decision["gates"]["latency"]["detail"]["p95_ratio"] == 2
    assert decision["gates"]["latency"]["status"] == "failed"


def test_three_way_keeps_export_drift_separate_from_training_effect():
    cases = [make_case(str(i), "abc") for i in range(3)]
    product = [record(case, "axc") for case in cases]
    reexported = [record(case, "xxx") for case in cases]
    finetuned = [record(case, "abc") for case in cases]
    result = compare_three_way(product, reexported, finetuned, cases)
    assert result["comparisons"]["P_to_R"]["candidate"]["strict"]["errors"] == 9
    assert result["comparisons"]["R_to_F"]["baseline"]["strict"]["errors"] == 9
    assert result["comparisons"]["P_to_F"]["baseline"]["strict"]["errors"] == 3
    assert result["product_decision"]["status"] != "passed"


def test_recipe_and_duplicate_identifiers_are_rejected():
    case = make_case("one")
    row = record(case, "가나")
    with pytest.raises(ValueError, match="duplicate"):
        analyze_pair([row, row], [row], [case])
    recipe = deepcopy(DEFAULT_RECIPE)
    recipe["bootstrap_resamples"] = 0
    with pytest.raises(ValueError, match="resamples"):
        analyze_pair([row], [row], [case], recipe)
    recipe = deepcopy(DEFAULT_RECIPE)
    recipe["cluster_fields"] = ["document_id"]
    with pytest.raises(ValueError, match="variants"):
        analyze_pair([row], [row], [case], recipe)


def test_html_escapes_exact_text_and_output_never_overwrites(tmp_path):
    case = make_case("html", '<script>alert("x")</script> & ℃')
    row = record(case, case["expected"]["text"])
    analysis = analyze_pair([row], [row], [case])
    html = render_report(analysis, assess(analysis))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html and "℃" in html
    output = tmp_path / "new-report"
    path = save_report(output, analysis, assess(analysis))
    assert path.is_file()
    assert json.loads((output / "result.json").read_text(encoding="utf-8"))["analysis"]["input_sha256"] == analysis["input_sha256"]
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        save_report(output, analysis)
    assert path.read_bytes() == before


def test_analysis_does_not_mutate_input_or_global_random():
    cases, left, right, recipe = sample_study()
    saved = deepcopy((cases, left, right, recipe))
    state = random.getstate()
    analyze_pair(left, right, cases, recipe)
    assert (cases, left, right, recipe) == saved
    assert random.getstate() == state


def test_evaluation_import_does_not_load_models_images_qt_or_product():
    script = '''
import importlib.abc
import sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'screen_text', 'onnxruntime', 'PIL', 'numpy', 'PySide6'}:
            raise RuntimeError('forbidden runtime import: ' + fullname)
sys.meta_path.insert(0, Block())
from tools.screen_text_lab.evaluation import analyze_pair, assess
from tools.screen_text_lab.evaluation.report import render_report
'''
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0, completed.stderr


def fake_crop_run(tmp_path):
    """Byte placeholders exercise provenance only; never load them as models."""
    directory = tmp_path / "fake-run"
    directory.mkdir()
    (directory / "cases").mkdir()
    (directory / "model.onnx").write_bytes(b"FAKE MODEL FOR HASH CHECK ONLY")
    (directory / "dictionary.txt").write_text("가\n나\n", encoding="utf-8")
    (directory / "cases/one.png").write_bytes(b"FAKE IMAGE FOR HASH CHECK ONLY")
    case = make_case("one")
    case["image_sha256"] = digest(directory / "cases/one.png")
    row = record(case, "가나")
    row.update({key: deepcopy(value) for key, value in case.items()})
    row["metrics"] = score_case(case, row["prediction"])
    model = {"role": "P", "id": "fake-product", "provenance": "unit_test_only",
             "model_sha256": digest(directory / "model.onnx"),
             "dictionary_sha256": digest(directory / "dictionary.txt")}
    dataset = (tmp_path / "not-opened-source-dataset/selection").resolve()
    manifest_sha = json_hash({"cases": [case]})
    request = {"dataset": str(dataset), "cases": [case], "model": model}
    snapshots = {str(dataset / "manifest.json"): manifest_sha}
    source = {"fake.py": json_hash("fake-code")}
    (directory / "cases.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    result = {"kind": "selection_line_crop", "status": "completed", "run_id": directory.name,
              "evaluation_scope": "line_crop", "model": model,
              "dataset_audit": {"status": "passed", "cases": 1, "manifest_sha256": manifest_sha},
              "source_before": source, "source_after": source,
              "inputs_before": snapshots, "inputs_after": snapshots,
              "cases_sha256": digest(directory / "cases.jsonl")}
    (directory / "request.json").write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return directory, manifest_sha


def test_saved_run_loader_returns_provenance_without_opening_source_data(tmp_path):
    directory, manifest_sha = fake_crop_run(tmp_path)
    loaded = load_crop_run(directory, expected_manifest_sha256=manifest_sha)
    assert loaded["provenance"]["model"]["role"] == "P"
    assert loaded["provenance"]["manifest_sha256"] == manifest_sha
    assert loaded["records"][0]["prediction"]["text"] == "가나"
    assert not (tmp_path / "not-opened-source-dataset").exists()
    analysis = analyze_pair(loaded["records"], loaded["records"], loaded["cases"])
    assert analysis["integrity_issues"] == []
    assert assess(analysis)["status"] != "passed"


@pytest.mark.parametrize("problem", ["kind", "partial", "identity", "cases_hash", "source", "inputs",
                                      "manifest", "request_manifest", "model", "model_copy", "dictionary_copy",
                                      "image_copy", "metadata", "metrics", "records_subset", "duplicate", "nonfinite"])
def test_saved_run_loader_rejects_changed_or_incomplete_artifacts(tmp_path, problem):
    directory, manifest_sha = fake_crop_run(tmp_path)
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    row = json.loads((directory / "cases.jsonl").read_text(encoding="utf-8"))
    if problem == "kind":
        result["kind"] = "ocr_run"
    elif problem == "partial":
        result["status"] = "partial"
    elif problem == "identity":
        result["run_id"] = "other-run"
    elif problem == "cases_hash":
        result["cases_sha256"] = "0" * 64
    elif problem == "source":
        result["source_after"]["fake.py"] = "0" * 64
    elif problem == "inputs":
        result["inputs_after"] = {}
    elif problem == "manifest":
        manifest_sha = "0" * 64
    elif problem == "request_manifest":
        request["dataset"] = str(tmp_path / "other-dataset")
    elif problem == "model":
        request["model"]["id"] = "other-model"
    elif problem == "model_copy":
        (directory / "model.onnx").write_bytes(b"changed")
    elif problem == "dictionary_copy":
        (directory / "dictionary.txt").write_bytes(b"changed")
    elif problem == "image_copy":
        (directory / "cases/one.png").write_bytes(b"changed")
    elif problem == "metadata":
        row["document_id"] = "other-document"
    elif problem == "metrics":
        row["metrics"]["errors"] = 999
    elif problem == "nonfinite":
        row["prediction"]["total_ms"] = float("nan")
    if problem in {"metadata", "metrics", "nonfinite", "records_subset", "duplicate"}:
        text = json.dumps(row, ensure_ascii=False) + "\n"
        if problem == "records_subset":
            text = ""
        elif problem == "duplicate":
            text *= 2
        (directory / "cases.jsonl").write_text(text, encoding="utf-8")
        result["cases_sha256"] = digest(directory / "cases.jsonl")
    (directory / "request.json").write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        load_crop_run(directory, expected_manifest_sha256=manifest_sha)
