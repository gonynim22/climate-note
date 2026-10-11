"""후보 변화와 경고 비용을 집계한다. 정답/제품 예측을 수정하지 않는다."""
from collections import defaultdict

from .condition_analysis import measurements


WARNING_THRESHOLDS = (.5, .7, .8, .9)


def analyze_warnings(records):
    scored = [row for row in records if row["status"] == "ok" and row.get("metrics")]
    observed = [row for row in scored if row.get("prediction", {}).get("trace", {}).get("version") == 1
                and row["prediction"]["trace"].get("score_scope", "final") == "final"
                and "min_char_score" in row["prediction"]["trace"]]
    if not observed:
        return None
    scopes = {}
    for scope in ("strict_all", "no_space_text"):
        rows = []
        for threshold in (None, *WARNING_THRESHOLDS):
            counts = dict(true_positive=0, false_negative=0, false_positive=0, true_negative=0, added_warnings=0)
            for record in observed:
                score = record["metrics"]
                wrong = not (score["all_exact"] if scope == "strict_all" else score["no_space"]["exact"])
                product = record["prediction"]["unsure_count"] > 0
                minimum = record["prediction"]["trace"]["min_char_score"]
                warning = product or (threshold is not None and minimum is not None and minimum < threshold)
                counts["added_warnings"] += int(warning and not product)
                key = ("true_positive" if warning else "false_negative") if wrong else (
                    "false_positive" if warning else "true_negative")
                counts[key] += 1
            tp, fp, fn = (counts[key] for key in ("true_positive", "false_positive", "false_negative"))
            rows.append({"threshold": threshold, **counts,
                         "precision": tp / (tp + fp) if tp + fp else None,
                         "recall": tp / (tp + fn) if tp + fn else None})
        scopes[scope] = rows
    return {"version": 1, "cases": len(observed), "scored": len(scored),
            "excluded_missing_trace": len(scored) - len(observed),
            "excluded_unscored_or_failed": len(records) - len(scored), "scopes": scopes}


def paired_measurements(left, right):
    if len(left) != len(right) or any(a["case_id"] != b["case_id"] for a, b in zip(left, right)):
        raise ValueError("후보 분석은 순서가 같은 사례 쌍이 필요합니다")
    pairs = [(a, b) for a, b in zip(left, right) if a["status"] == b["status"] == "ok"
             and a.get("metrics") is not None and b.get("metrics") is not None]
    baseline = measurements([a for a, _ in pairs])
    candidate = measurements([b for _, b in pairs])
    changes = dict(new_wrong=0, recovered=0, no_space_new_wrong=0, no_space_recovered=0,
                   no_space_improved=0, no_space_regressed=0, no_space_equal=0)
    examples = []
    for a, b in pairs:
        old, new = a["metrics"], b["metrics"]
        changes["new_wrong"] += int(old["all_exact"] and not new["all_exact"])
        changes["recovered"] += int(not old["all_exact"] and new["all_exact"])
        changes["no_space_new_wrong"] += int(old["no_space"]["exact"] and not new["no_space"]["exact"])
        changes["no_space_recovered"] += int(not old["no_space"]["exact"] and new["no_space"]["exact"])
        delta = new["no_space"]["errors"] - old["no_space"]["errors"]
        changes["no_space_regressed" if delta > 0 else "no_space_improved" if delta < 0 else "no_space_equal"] += 1
        if delta > 0:
            examples.append({"case_id": b["case_id"], "extra_errors": delta,
                             "was_correct": old["no_space"]["exact"]})
    median = baseline["median_ms"]
    return {"cases": len(left), "pairs": len(pairs), "excluded": len(left) - len(pairs),
            "baseline": baseline, "candidate": candidate, "changes": changes,
            "median_time_ratio": candidate["median_ms"] / median if median and candidate["median_ms"] is not None else None,
            "regression_examples": sorted(examples, key=lambda row: (-row["extra_errors"], row["case_id"]))[:5]}


def analyze_candidates(left, right):
    overall = paired_measurements(left, right)
    slices = {}
    for field in ("condition", "category"):
        groups = defaultdict(lambda: ([], []))
        for old, new in zip(left, right):
            key = str(new.get("tags", {}).get(field, "미분류"))
            groups[key][0].append(old)
            groups[key][1].append(new)
        slices[field] = {key: paired_measurements(*pair) for key, pair in sorted(groups.items())}
    return {"version": 1, "overall": overall, "slices": slices}
