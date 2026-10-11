"""Paired, grouped OCR measurements and independent fail-closed quality gates.

The canonical NFC/LF edit scorer is reused. Critical tags describe entire cases,
not character locations. A research comparison is never a deployment approval.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import math
import random
import statistics

from ..corpus import json_hash
from ..metrics import METRIC_VERSION, normalize, score_case


DEFAULT_RECIPE = {
    "schema_version": 1,
    "bootstrap_seed": 20261011,
    "bootstrap_resamples": 2000,
    "confidence": 0.95,
    "cluster_fields": ["document_id", "source_group_id", "template_family_id"],
    "minimum_reduction": 0.20,
    "minimum_real_groups": 300,
    "minimum_groups_per_app": {"hwp": 50, "pdf": 50, "word": 50, "notepad": 50},
    "minimum_table_groups": 50,
    "required_critical_tags": ["numbers", "money", "date", "units"],
    "maximum_new_wrong": 0,
    "maximum_new_silent_errors": 0,
    "maximum_new_false_warnings": 0,
    "maximum_time_ratio": 1.10,
    "maximum_model_bytes": 15_000_000,
    "benchmark_case_ids": [],
    "benchmark_repeats": 5,
    "benchmark_warmup_pairs": 3,
}


def _number(value, *, lower=0, upper=None):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= lower
            and (upper is None or value <= upper))


def _validate_recipe(recipe):
    if set(recipe) != set(DEFAULT_RECIPE) or recipe["schema_version"] != 1:
        raise ValueError("Evaluation recipe fields/version differ from the supported schema")
    integers = ("bootstrap_seed", "bootstrap_resamples", "minimum_real_groups", "minimum_table_groups",
                "maximum_new_wrong", "maximum_new_silent_errors", "maximum_new_false_warnings",
                "maximum_model_bytes", "benchmark_repeats", "benchmark_warmup_pairs")
    if any(type(recipe[key]) is not int or recipe[key] < 0 for key in integers):
        raise ValueError("Recipe counts must be nonnegative integers")
    if not 100 <= recipe["bootstrap_resamples"] <= 100_000:
        raise ValueError("Bootstrap resamples must be between 100 and 100000")
    if not _number(recipe["confidence"], lower=.5, upper=.999):
        raise ValueError("Unsupported confidence level")
    if not _number(recipe["minimum_reduction"], upper=1) or not _number(recipe["maximum_time_ratio"], lower=1):
        raise ValueError("Invalid accuracy or latency limit")
    if recipe["benchmark_repeats"] < 5 or recipe["benchmark_warmup_pairs"] < 1:
        raise ValueError("Latency requires at least five repeats and warmup")
    for key in ("cluster_fields", "required_critical_tags", "benchmark_case_ids"):
        values = recipe[key]
        if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values) or len(set(values)) != len(values):
            raise ValueError(f"Invalid recipe list: {key}")
    if "source_group_id" not in recipe["cluster_fields"]:
        raise ValueError("Source variants must remain in the same bootstrap cluster")
    if any(key not in {"document_id", "source_group_id", "template_family_id"} for key in recipe["cluster_fields"]):
        raise ValueError("Unknown cluster field")
    apps = recipe["minimum_groups_per_app"]
    if not isinstance(apps, dict) or not apps or any(not isinstance(key, str) or not key or type(value) is not int or value < 1 for key, value in apps.items()):
        raise ValueError("App coverage must specify positive group counts")


def _index(records, name):
    result = {}
    for row in records:
        identifier = row.get("case_id")
        if not isinstance(identifier, str) or not identifier or identifier in result:
            raise ValueError(f"{name}: missing/duplicate case_id")
        result[identifier] = row
    return result


def _clusters(cases, fields):
    """Connected components retain transitive document/source/template relations."""
    parent = {identifier: identifier for identifier in cases}

    def root(identifier):
        while parent[identifier] != identifier:
            parent[identifier] = parent[parent[identifier]]
            identifier = parent[identifier]
        return identifier

    known = {}
    for identifier, case in sorted(cases.items()):
        for field in fields:
            value = case.get(field)
            if value is None:
                continue
            if not isinstance(value, str) or not value:
                raise ValueError(f"{identifier}: invalid cluster field {field}")
            key = field, value
            if key in known:
                left, right = root(identifier), root(known[key])
                parent[max(left, right)] = min(left, right)
            else:
                known[key] = identifier
    return {identifier: root(identifier) for identifier in cases}


def _prediction_issues(record, case):
    issues = []
    for key in ("source_group_id", "split", "source_kind", "tags", "review_status", "image_sha256", "expected"):
        if key not in case or record.get(key) != case[key]:
            issues.append(f"metadata_mismatch:{key}")
    if record.get("expected_sha256") != json_hash(case["expected"]):
        issues.append("expected_hash_mismatch")
    if record.get("status") != "ok":
        issues.append(f"status:{record.get('status', 'missing')}")
    if case.get("review_status") not in {"generated", "reviewed"}:
        issues.append("unreviewed")
    prediction = record.get("prediction", {})
    if not isinstance(prediction.get("text"), str):
        issues.append("missing_text")
    if type(prediction.get("unsure_count")) is not int or prediction["unsure_count"] < 0:
        issues.append("missing_warning_measurement")
    if "table" in case["expected"]:
        table = prediction.get("table")
        if not isinstance(table, list) or any(not isinstance(row, list) or any(not isinstance(cell, str) for cell in row) for row in table):
            issues.append("missing_table_measurement")
    return issues


def _summary(rows, side):
    scores = [row[side] for row in rows]
    values = {}
    for key, source in (("strict", scores), ("no_space", [score["no_space"] for score in scores])):
        nonempty = [score for score in source if score["reference_chars"]]
        count = sum(score["reference_chars"] for score in nonempty)
        errors = sum(score["errors"] for score in nonempty)
        grouped = defaultdict(list)
        for row, score in zip(rows, source):
            if score["cer"] is not None:
                grouped[row["cluster"]].append(score["cer"])
        values[key] = {"reference_chars": count, "errors": errors, "cer": errors / count if count else None,
                       "macro_group_cer": statistics.mean(statistics.mean(group) for group in grouped.values()) if grouped else None,
                       "exact": sum(score["exact"] for score in source)}
    wrong = sum(not score["all_exact"] for score in scores)
    silent = sum(score["wrong_without_warning"] for score in scores)
    correct = len(scores) - wrong
    false = sum(score["correct_with_warning"] for score in scores)
    values.update(cases=len(rows), groups=len({row["cluster"] for row in rows}),
                  all_exact=correct, wrong=wrong, silent_errors=silent,
                  silent_error_rate=silent / wrong if wrong else None,
                  false_warnings=false, false_warning_rate=false / correct if correct else None,
                  empty_false_characters=sum(score["insertions"] for score in scores if not score["reference_chars"]))
    tables = [score["table"] for score in scores if score["table"] is not None]
    values["table"] = {"cases": len(tables), "exact": sum(table["exact"] for table in tables),
                       "cells": sum(table["cells"] for table in tables),
                       "wrong_cells": sum(table["cells"] - table["correct"] for table in tables)}
    return values


def _transitions(rows):
    counts = Counter({key: 0 for key in ("new_wrong", "recovered", "new_no_space_wrong", "no_space_recovered",
                     "new_silent_errors", "new_false_warnings", "critical_regressions", "table_content_regressions",
                     "table_shape_regressions", "table_new_wrong", "table_new_wrong_cells", "table_new_extra_cells",
                     "table_recovered_cells", "empty_regressions")})
    affected = defaultdict(list)
    for row in rows:
        old, new = row["baseline"], row["candidate"]
        conditions = {
            "new_wrong": old["all_exact"] and not new["all_exact"],
            "recovered": not old["all_exact"] and new["all_exact"],
            "new_no_space_wrong": old["no_space"]["exact"] and not new["no_space"]["exact"],
            "no_space_recovered": not old["no_space"]["exact"] and new["no_space"]["exact"],
            "new_silent_errors": new["wrong_without_warning"] and not old["wrong_without_warning"],
            "new_false_warnings": old["all_exact"] and new["all_exact"] and new["correct_with_warning"] and not old["correct_with_warning"],
            "critical_regressions": bool(row["critical_tags"]) and new["errors"] > old["errors"],
            "empty_regressions": old["reference_chars"] == 0 and new["insertions"] > old["insertions"],
        }
        if old["table"] is not None:
            conditions.update(table_content_regressions=row["candidate_table_errors"] > row["baseline_table_errors"],
                              table_shape_regressions=row["candidate_table_shape_errors"] > row["baseline_table_shape_errors"],
                              table_new_wrong=old["table"]["exact"] and not new["table"]["exact"])
            for key in ("table_new_wrong_cells", "table_new_extra_cells", "table_recovered_cells"):
                counts[key] += row[key]
                if row[key]:
                    affected[key].append(row["case_id"])
        for key, condition in conditions.items():
            if condition:
                counts[key] += 1
                affected[key].append(row["case_id"])
    return {"counts": dict(counts), "case_ids": dict(affected)}


def _table_cell_transitions(expected, baseline, candidate):
    """Compare canonical expected positions; net cell-error gains cannot hide losses."""
    expected_cells = {(r, c): text for r, row in enumerate(expected) for c, text in enumerate(row)}
    old = {(r, c): text for r, row in enumerate(baseline) for c, text in enumerate(row)}
    new = {(r, c): text for r, row in enumerate(candidate) for c, text in enumerate(row)}
    lost = recovered = 0
    for position, text in expected_cells.items():
        old_correct = position in old and normalize(old[position]) == normalize(text)
        new_correct = position in new and normalize(new[position]) == normalize(text)
        lost += old_correct and not new_correct
        recovered += not old_correct and new_correct
    return {"table_new_wrong_cells": lost, "table_recovered_cells": recovered,
            "table_new_extra_cells": len((set(new) - set(expected_cells)) - set(old))}


def _percentile(values, probability):
    ordered = sorted(values)
    index = probability * (len(ordered) - 1)
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def _bootstrap(rows, recipe):
    totals = defaultdict(lambda: [0, 0, 0])
    for row in rows:
        a, b = row["baseline"]["no_space"], row["candidate"]["no_space"]
        if a["reference_chars"]:
            entry = totals[row["cluster"]]
            entry[0] += a["reference_chars"]
            entry[1] += a["errors"]
            entry[2] += b["errors"]
    groups = [totals[key] for key in sorted(totals)]
    reference = sum(group[0] for group in groups)
    old = sum(group[1] for group in groups)
    new = sum(group[2] for group in groups)
    result = {"method": "paired_connected_group_percentile", "groups": len(groups),
              "seed": recipe["bootstrap_seed"], "resamples": recipe["bootstrap_resamples"],
              "confidence": recipe["confidence"], "delta_cer": (new - old) / reference if reference else None,
              "relative_reduction": (old - new) / old if old else None,
              "delta_cer_ci": None, "relative_reduction_ci": None, "undefined_relative_resamples": 0}
    if len(groups) < 2:
        result["reason"] = "fewer_than_two_independent_groups"
        return result
    generator = random.Random(recipe["bootstrap_seed"])
    deltas, relative = [], []
    for _ in range(recipe["bootstrap_resamples"]):
        selected = generator.choices(groups, k=len(groups))
        ref = sum(group[0] for group in selected)
        a, b = sum(group[1] for group in selected), sum(group[2] for group in selected)
        deltas.append((b - a) / ref)
        if a:
            relative.append((a - b) / a)
    alpha = (1 - recipe["confidence"]) / 2
    result["delta_cer_ci"] = [_percentile(deltas, alpha), _percentile(deltas, 1 - alpha)]
    result["undefined_relative_resamples"] = recipe["bootstrap_resamples"] - len(relative)
    # Conditioning on draws with baseline errors can exaggerate reduction. Never
    # discard undefined draws and present the remaining interval as complete.
    if len(relative) == recipe["bootstrap_resamples"]:
        result["relative_reduction_ci"] = [_percentile(relative, alpha), _percentile(relative, 1 - alpha)]
    return result


def analyze_pair(baseline, candidate, expected_cases, recipe=None, *, supported_characters=None):
    """Pure analysis of saved records and an explicit complete expected manifest.

    `supported_characters` is the fixed shared vocabulary (normally P's), not a
    filter applied to text. OOV cases remain in the primary metrics unchanged.
    Missing vocabulary makes the OOV assessment incomplete.
    """
    recipe = deepcopy(DEFAULT_RECIPE if recipe is None else recipe)
    _validate_recipe(recipe)
    cases = _index(expected_cases, "manifest")
    left, right = _index(baseline, "baseline"), _index(candidate, "candidate")
    clusters = _clusters(cases, recipe["cluster_fields"])
    vocabulary = None if supported_characters is None else set(supported_characters)
    if vocabulary is not None and any(not isinstance(char, str) or len(char) != 1 for char in vocabulary):
        raise ValueError("Vocabulary must contain single Unicode codepoints")
    issues = []
    for name, records in (("baseline", left), ("candidate", right)):
        for identifier in sorted(set(cases) - set(records)):
            issues.append({"case_id": identifier, "side": name, "reason": "missing_case"})
        for identifier in sorted(set(records) - set(cases)):
            issues.append({"case_id": identifier, "side": name, "reason": "extra_case"})
    rows = []
    for identifier, case in sorted(cases.items()):
        if identifier not in left or identifier not in right:
            continue
        bad = False
        for name, record in (("baseline", left[identifier]), ("candidate", right[identifier])):
            for reason in _prediction_issues(record, case):
                issues.append({"case_id": identifier, "side": name, "reason": reason})
                bad = True
        if bad:
            continue
        a, b = score_case(case, left[identifier]["prediction"]), score_case(case, right[identifier]["prediction"])
        for name, record, score in (("baseline", left[identifier], a), ("candidate", right[identifier], b)):
            if record.get("metrics") is not None and record["metrics"] != score:
                issues.append({"case_id": identifier, "side": name, "reason": "stored_metrics_mismatch"})
        tags = case.get("critical_tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError(f"{identifier}: critical_tags must be explicit strings")
        text = normalize(case["expected"]["text"])
        oov = None if vocabulary is None else sorted({char for char in text if not char.isspace() and char not in vocabulary})
        row = {"case_id": identifier, "cluster": clusters[identifier], "baseline": a, "candidate": b,
               "critical_tags": tags, "oov_characters": oov, "metadata": deepcopy(case),
               "baseline_text": left[identifier]["prediction"]["text"],
               "candidate_text": right[identifier]["prediction"]["text"]}
        if a["table"] is not None:
            expected = case["expected"]["table"]
            for side, record in (("baseline", left[identifier]), ("candidate", right[identifier])):
                actual = record["prediction"]["table"]
                row[f"{side}_table_shape"] = len(actual) == len(expected) and all(len(x) == len(y) for x, y in zip(actual, expected))
                row[f"{side}_table_shape_errors"] = abs(len(actual) - len(expected)) + sum(
                    abs((len(expected[i]) if i < len(expected) else 0) - (len(actual[i]) if i < len(actual) else 0))
                    for i in range(max(len(expected), len(actual))))
                row[f"{side}_table_errors"] = row[side]["table"]["cells"] - row[side]["table"]["correct"]
                row[f"{side}_table"] = deepcopy(actual)
            row.update(_table_cell_transitions(expected, row["baseline_table"], row["candidate_table"]))
        rows.append(row)
    slices = defaultdict(list)
    for row in rows:
        case = row["metadata"]
        for field in ("source_kind", "split", "evaluation_scope"):
            slices[f"{field}:{case.get(field, 'unknown')}"].append(row)
        for key, value in sorted(case.get("tags", {}).items()):
            if isinstance(value, (str, int, float, bool)):
                slices[f"{key}:{value}"].append(row)
        for tag in row["critical_tags"]:
            slices[f"critical:{tag}"].append(row)
        if row["oov_characters"] is not None:
            slices["vocabulary:oov" if row["oov_characters"] else "vocabulary:supported"].append(row)
    input_hash = json_hash({"baseline": baseline, "candidate": candidate, "cases": expected_cases,
                            "recipe": recipe, "shared_vocabulary": sorted(vocabulary) if vocabulary is not None else None})
    return {"schema_version": 1, "metric_version": METRIC_VERSION, "kind": "ocr_paired_evaluation",
            "input_sha256": input_hash, "recipe_sha256": json_hash(recipe), "recipe": recipe,
            "expected_cases": len(cases), "scored_pairs": len(rows), "excluded_pairs": len(cases) - len(rows),
            "integrity_issues": issues, "baseline": _summary(rows, "baseline"), "candidate": _summary(rows, "candidate"),
            "transitions": _transitions(rows), "bootstrap": _bootstrap(rows, recipe),
            "slices": {key: {"baseline": _summary(value, "baseline"), "candidate": _summary(value, "candidate"),
                             "transitions": _transitions(value)} for key, value in sorted(slices.items())},
            "rows": rows, "vocabulary_observed": vocabulary is not None,
            "limitations": ["Critical regressions are case-level tags, not token/character accuracy.",
                            "Confidence scores are not correctness probabilities.",
                            "Saved single-run timings are not latency benchmarks.",
                            "A metric gate cannot approve deployment or establish annotation independence."]}


def _benchmark(evidence, recipe, expected_ids):
    workload = recipe["benchmark_case_ids"]
    if not workload or not set(workload).issubset(expected_ids):
        return None, "benchmark_workload_not_frozen"
    if not isinstance(evidence, dict) or evidence.get("status") != "completed":
        return None, "benchmark_missing"
    if (evidence.get("case_ids") != workload or evidence.get("warmup_pairs", -1) < recipe["benchmark_warmup_pairs"]
            or type(evidence.get("threads")) is not int or evidence["threads"] < 1
            or not isinstance(evidence.get("cpu"), str) or not evidence["cpu"]):
        return None, "benchmark_protocol_missing"
    samples = evidence.get("samples", [])
    observed = set()
    for sample in samples:
        identifier, repeat = sample.get("case_id"), sample.get("repeat")
        if identifier not in workload or type(repeat) is not int or not 0 <= repeat < recipe["benchmark_repeats"] or (identifier, repeat) in observed:
            return None, "benchmark_sample_set_mismatch"
        if sample.get("first") != ("baseline" if repeat % 2 == 0 else "candidate"):
            return None, "benchmark_order_not_alternating"
        if any(not _number(sample.get(key), lower=1e-12) for key in ("baseline_ms", "candidate_ms")):
            return None, "benchmark_invalid_time"
        observed.add((identifier, repeat))
    if len(observed) != len(workload) * recipe["benchmark_repeats"]:
        return None, "benchmark_incomplete"
    result = {"cases": len(workload), "pairs": len(samples), "repeats": recipe["benchmark_repeats"]}
    for side in ("baseline", "candidate"):
        values = sorted(sample[f"{side}_ms"] for sample in samples)
        result[side] = {"median_ms": statistics.median(values), "p95_ms": values[math.ceil(.95 * len(values)) - 1]}
    result["median_ratio"] = result["candidate"]["median_ms"] / result["baseline"]["median_ms"]
    result["p95_ratio"] = result["candidate"]["p95_ms"] / result["baseline"]["p95_ms"]
    return result, None


def assess(analysis, evidence=None):
    """Screen-level quality eligibility; absent measurements produce `incomplete`.

    Evidence is bound to the complete analysis input SHA. Its clipping entries
    must be explicit observations for every expected case. A line-crop study
    remains incomplete for product eligibility even if its CER improves.
    """
    evidence = {} if evidence is None else evidence
    recipe, rows = analysis["recipe"], analysis["rows"]
    gates = {}
    bound = evidence.get("input_sha256") == analysis["input_sha256"]

    def gate(name, observed, passed, detail):
        gates[name] = {"status": "missing" if not observed else ("passed" if passed else "failed"), "detail": detail}

    gate("complete_inputs", True, bool(analysis["expected_cases"]) and not analysis["integrity_issues"] and analysis["excluded_pairs"] == 0,
         {"excluded_pairs": analysis["excluded_pairs"], "issues": analysis["integrity_issues"]})
    scopes = Counter(row["metadata"].get("evaluation_scope", "unknown") for row in rows)
    gate("screen_scope", bool(rows) and set(scopes) == {"screen"}, True, dict(scopes))
    real = [row for row in rows if row["metadata"]["source_kind"] in {"program_capture", "user_supplied"}]
    groups = len({row["cluster"] for row in real})
    app_groups = {app: len({row["cluster"] for row in real if row["metadata"].get("tags", {}).get("app") == app})
                  for app in recipe["minimum_groups_per_app"]}
    human = bool(real) and all(row["metadata"].get("review_provenance", {}).get("human_reviewed") is True for row in real)
    gate("actual_coverage", groups >= recipe["minimum_real_groups"] and all(app_groups[app] >= minimum for app, minimum in recipe["minimum_groups_per_app"].items()) and human, True,
         {"groups": groups, "apps": app_groups, "all_real_human_reviewed": human})
    grouping_observed = bool(real) and all(
        isinstance(row["metadata"].get(field), str) and bool(row["metadata"][field])
        for row in real for field in recipe["cluster_fields"])
    gate("grouping_metadata", grouping_observed, True,
         "All configured document/source/template relations are required for final actual-screen eligibility")
    # Synthetic volume must never dilute actual-screen regression or improvement.
    real_ci = _bootstrap(real, recipe)
    real_old, real_new = _summary(real, "baseline"), _summary(real, "candidate")
    interval, reduction = real_ci["delta_cer_ci"], real_ci["relative_reduction"]
    gate("actual_accuracy", interval is not None,
         interval is not None and interval[1] < 0 and reduction is not None and reduction >= recipe["minimum_reduction"], real_ci)
    gate("strict_errors", bool(rows), analysis["candidate"]["strict"]["errors"] <= analysis["baseline"]["strict"]["errors"] and real_new["strict"]["errors"] <= real_old["strict"]["errors"],
         {"all_delta": analysis["candidate"]["strict"]["errors"] - analysis["baseline"]["strict"]["errors"],
          "actual_delta": real_new["strict"]["errors"] - real_old["strict"]["errors"]})
    changes = analysis["transitions"]["counts"]
    gate("new_wrong", bool(rows), changes["new_wrong"] <= recipe["maximum_new_wrong"] and changes["empty_regressions"] == 0, changes)
    coverage = {tag: sum(tag in row["critical_tags"] for row in real) for tag in recipe["required_critical_tags"]}
    gate("critical_cases", bool(coverage) and all(coverage.values()), changes["critical_regressions"] == 0, {"actual_coverage": coverage, "regressions": changes["critical_regressions"]})
    # A whole-case net gain can hide a newly wrong digit/unit. When both outputs
    # are wrong and differ, require independent span or human-diff evidence.
    ambiguous = {row["case_id"] for row in rows if row["critical_tags"]
                 and not row["baseline"]["exact"] and not row["candidate"]["exact"]
                 and normalize(row["baseline_text"]) != normalize(row["candidate_text"])}
    review = evidence.get("critical_review", {}) if bound else {}
    reviewed = review.get("cases", {}) if isinstance(review, dict) else {}
    review_complete = (isinstance(review, dict) and review.get("method") in {"annotated_spans", "human_diff"}
                       and isinstance(reviewed, dict) and set(reviewed) == ambiguous
                       and all(type(value) is bool for value in reviewed.values()))
    gate("critical_details", not ambiguous or review_complete,
         not ambiguous or (review_complete and not any(reviewed.values())),
         {"ambiguous_critical_changes": sorted(ambiguous), "review_method": review.get("method") if isinstance(review, dict) else None,
          "meaning": "Review values are true when a new number/unit/token error exists; net CER gain is insufficient"})
    table_groups = len({row["cluster"] for row in real if row["baseline"]["table"] is not None})
    gate("tables", table_groups >= recipe["minimum_table_groups"] and table_groups > 0,
         all(changes[key] == 0 for key in ("table_content_regressions", "table_shape_regressions", "table_new_wrong",
                                         "table_new_wrong_cells", "table_new_extra_cells")),
         {"actual_groups": table_groups, "changes": {key: value for key, value in changes.items() if key.startswith("table_")}})
    warnings_pass = (changes["new_silent_errors"] <= recipe["maximum_new_silent_errors"]
                     and changes["new_false_warnings"] <= recipe["maximum_new_false_warnings"]
                     and analysis["candidate"]["silent_errors"] <= analysis["baseline"]["silent_errors"]
                     and real_new["silent_errors"] <= real_old["silent_errors"])
    gate("warnings", bool(rows), warnings_pass, {"all_baseline": analysis["baseline"]["silent_errors"], "all_candidate": analysis["candidate"]["silent_errors"],
         "actual_baseline": real_old["silent_errors"], "actual_candidate": real_new["silent_errors"],
         "new_silent_errors": changes["new_silent_errors"], "new_false_warnings": changes["new_false_warnings"]})
    gate("oov_accounting", analysis["vocabulary_observed"], True,
         {"oov_cases": sum(bool(row["oov_characters"]) for row in rows), "primary_includes_oov": True})
    gate("evidence_binding", bool(evidence), bound, "Evidence must name the exact comparison input SHA-256")
    clipping = evidence.get("clipping", {}) if bound else {}
    identifiers = {row["case_id"] for row in rows}
    clipping_complete = isinstance(clipping, dict) and set(clipping) == identifiers and bool(identifiers) and all(type(value) is bool for value in clipping.values())
    gate("clipping", clipping_complete, clipping_complete and not any(clipping.values()), "Explicit candidate truncation observations for every case")
    size = evidence.get("candidate_model_bytes") if bound else None
    gate("model_size", type(size) is int and size > 0, type(size) is int and 0 < size <= recipe["maximum_model_bytes"], size)
    benchmark, error = _benchmark(evidence.get("benchmark") if bound else None, recipe, identifiers)
    gate("latency", benchmark is not None, benchmark is not None and benchmark["median_ratio"] <= recipe["maximum_time_ratio"] and benchmark["p95_ratio"] <= recipe["maximum_time_ratio"], benchmark if benchmark is not None else error)
    statuses = {value["status"] for value in gates.values()}
    status = "failed" if "failed" in statuses else ("incomplete" if "missing" in statuses else "passed")
    return {"status": status, "gates": gates, "deployment_approved": False,
            "scope": "offline_quality_eligibility_only", "input_sha256": analysis["input_sha256"],
            "remaining": ["Run artifact/model/dictionary/source hash provenance verified by caller", "Frozen-candidate/final-access audit", "Seed stability and untouched regression corpus", "Product lifecycle, offline/capture safety and EXE/manual verification"]}


def compare_three_way(product, reexported, finetuned, expected_cases, recipe=None, *, supported_characters=None, evidence=None):
    """P→R is export drift; R→F is training effect; P→F is product benefit."""
    comparisons = {name: analyze_pair(left, right, expected_cases, recipe, supported_characters=supported_characters)
                   for name, left, right in (("P_to_R", product, reexported), ("R_to_F", reexported, finetuned), ("P_to_F", product, finetuned))}
    return {"schema_version": 1, "comparisons": comparisons,
            "product_decision": assess(comparisons["P_to_F"], evidence),
            "interpretation": {"P_to_R": "reexport_drift", "R_to_F": "training_effect", "P_to_F": "product_benefit"}}
