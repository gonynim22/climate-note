"""같은 정답/원본의 기준 조건과 변형 조건만 짝지어 비교한다."""
from collections import Counter, defaultdict

from .conditions import CONDITIONS, PROFILE
from .corpus import json_hash
from .metrics import aggregate


def measurements(records):
    result = aggregate(records)
    scores = [record["metrics"]["no_space"] for record in records
              if record["status"] == "ok" and record.get("metrics")]
    reference = sum(score["reference_chars"] for score in scores if score["reference_chars"])
    errors = sum(score["errors"] for score in scores if score["reference_chars"])
    result.update(no_space_reference_chars=reference, no_space_errors=errors,
                  no_space_cer=errors / reference if reference else None)
    return result


def analyze_conditions(records):
    from .compare import classify
    selected = [record for record in records if record.get("tags", {}).get("profile") == PROFILE]
    if not selected:
        return None
    groups = defaultdict(dict)
    known = {condition["id"] for condition in CONDITIONS}
    for record in selected:
        condition = record["tags"].get("condition")
        parent = record.get("parent_id")
        if condition not in known or (condition == "reference") != (parent is None):
            raise ValueError("조건 자료의 기준/변형 연결이 잘못되었습니다")
        original = parent or record["case_id"]
        if condition in groups[original]:
            raise ValueError("동일 원본/조건 결과가 중복됩니다")
        if json_hash(record["expected"]) != record["expected_sha256"]:
            raise ValueError("조건 자료의 정답 해시가 다릅니다")
        groups[original][condition] = record
    rows = []
    for condition in CONDITIONS:
        condition_id = condition["id"]
        left, right, observed, examples = [], [], [], []
        missing_reference = missing_condition = unscored = 0
        changes = Counter()
        categories = defaultdict(lambda: ([], []))
        for group in groups.values():
            baseline, variant = group.get("reference"), group.get(condition_id)
            if variant is not None:
                observed.append(variant)
            missing_reference += baseline is None
            missing_condition += variant is None
            if baseline is None or variant is None:
                continue
            for key in ("expected_sha256", "source_group_id", "split", "source_kind", "review_status"):
                if baseline.get(key) != variant.get(key):
                    raise ValueError(f"조건 비교 중 {key}가 달라졌습니다")
            if baseline["status"] != "ok" or variant["status"] != "ok" or not baseline.get("metrics") or not variant.get("metrics"):
                unscored += 1
                continue
            left.append(baseline)
            right.append(variant)
            category = baseline["tags"]["category"]
            categories[category][0].append(baseline)
            categories[category][1].append(variant)
            change = classify(baseline, variant)
            changes[change] += 1
            if change == "regressed":
                examples.append({"reference_id": baseline["case_id"], "case_id": variant["case_id"],
                                 "extra_errors": variant["metrics"]["errors"] - baseline["metrics"]["errors"]})
        a, b = measurements(left), measurements(right)
        rows.append({"condition": condition_id, "label": condition["label"], "expected_pairs": len(groups),
                     "pairs": len(left), "excluded": len(groups) - len(left),
                     "missing_reference": missing_reference, "missing_condition": missing_condition, "unscored_pairs": unscored,
                     "reference": a, "measured": b, "observed": measurements(observed),
                     "cer_delta": b["cer"] - a["cer"] if a["cer"] is not None and b["cer"] is not None else None,
                     "changes": dict(changes),
                     "categories": {key: {"reference": measurements(pair[0]), "measured": measurements(pair[1])}
                                    for key, pair in sorted(categories.items())},
                     "regression_examples": sorted(examples, key=lambda x: (-x["extra_errors"], x["case_id"]))[:3]})
    return {"profile": PROFILE, "original_groups": len(groups), "records": len(selected),
            "ignored_records": len(records) - len(selected), "conditions": rows,
            "scope": "조건마다 동일 원문 쌍만 집계. 합성 자료의 조건 영향이며 실제 업무 정확도/모델 개선 비교가 아님."}
