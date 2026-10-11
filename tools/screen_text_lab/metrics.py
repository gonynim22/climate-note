"""모델 없이 검증 가능한 채점. NFC/개행 이외의 원문은 자동 교정하지 않는다."""
from collections import Counter, defaultdict
import math
import statistics
import unicodedata

METRIC_VERSION = "1-nfc-lf-text-table-warning"


def normalize(text):
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def edit_counts(expected, actual):
    """최소 편집 거리. 동률은 치환→삭제→삽입 순서로 결정한다."""
    expected, actual = normalize(expected), normalize(actual)
    if len(expected) * len(actual) > 4_000_000:
        raise ValueError("채점 한도 초과: 정답/출력을 작은 영역으로 나누어 등록하세요")
    row = [(j, 0, 0, j) for j in range(len(actual) + 1)]
    for i, left in enumerate(expected, 1):
        nxt = [(i, 0, i, 0)]
        for j, right in enumerate(actual, 1):
            if left == right:
                nxt.append(row[j - 1])
            else:
                total, sub, deletion, insertion = row[j - 1]
                replace = (total + 1, sub + 1, deletion, insertion)
                total, sub, deletion, insertion = row[j]
                remove = (total + 1, sub, deletion + 1, insertion)
                total, sub, deletion, insertion = nxt[-1]
                add = (total + 1, sub, deletion, insertion + 1)
                nxt.append(min((replace, remove, add), key=lambda value: value[0]))
        row = nxt
    errors, sub, deletion, insertion = row[-1]
    return {"reference_chars": len(expected), "errors": errors, "substitutions": sub,
            "deletions": deletion, "insertions": insertion,
            "cer": errors / len(expected) if expected else None, "exact": expected == actual}


def table_score(expected, actual):
    if expected is None:
        return None
    row_count = max(len(expected), len(actual))
    total = correct = 0
    for r in range(row_count):
        left = expected[r] if r < len(expected) else []
        right = actual[r] if r < len(actual) else []
        for c in range(max(len(left), len(right))):
            total += 1
            correct += int(c < len(left) and c < len(right) and normalize(left[c]) == normalize(right[c]))
    same_shape = len(expected) == len(actual) and all(len(left) == len(right) for left, right in zip(expected, actual))
    return {"cells": total, "correct": correct, "accuracy": correct / total if total else None,
            "exact": same_shape and correct == total}


def score_case(case, prediction):
    if case["review_status"] == "unreviewed":
        return None
    expected, actual = case["expected"]["text"], prediction["text"]
    strict = edit_counts(expected, actual)
    stripped = edit_counts("".join(expected.split()), "".join(actual.split()))
    table = table_score(case["expected"].get("table"), prediction.get("table", []))
    all_exact = strict["exact"] and (table is None or table["exact"])
    return {**strict, "no_space": stripped,
            "table": table, "all_exact": all_exact,
            "wrong_without_warning": not all_exact and prediction["unsure_count"] == 0,
            "correct_with_warning": all_exact and prediction["unsure_count"] > 0}


def aggregate(records):
    scored = [record for record in records if record.get("metrics") is not None and record["status"] == "ok"]
    values = [record["metrics"] for record in scored]
    nonempty = [value for value in values if value["reference_chars"]]
    ref = sum(value["reference_chars"] for value in nonempty)
    errors = sum(value["errors"] for value in nonempty)
    wrong = sum(not value["all_exact"] for value in values)
    no_warning = sum(value["wrong_without_warning"] for value in values)
    groups = defaultdict(list)
    for record in scored:
        if record["metrics"]["cer"] is not None:
            groups[record["source_group_id"]].append(record["metrics"]["cer"])
    times = sorted(record["prediction"]["total_ms"] for record in records
                   if record["status"] == "ok" and "total_ms" in record.get("prediction", {}))
    tables = [value["table"] for value in values if value.get("table") is not None]
    cells = sum(table["cells"] for table in tables)
    empty = [value for value in values if not value["reference_chars"]]
    return {"total": len(records), "statuses": dict(Counter(record["status"] for record in records)),
            "completed": sum(record["status"] == "ok" for record in records), "scored": len(values),
            "exact": sum(value["exact"] for value in values), "all_exact": sum(value["all_exact"] for value in values), "wrong": wrong,
            "reference_chars": ref, "errors": errors, "cer": errors / ref if ref else None,
            "macro_group_cer": statistics.mean(statistics.mean(group) for group in groups.values()) if groups else None,
            "wrong_without_warning": no_warning,
            "wrong_without_warning_rate": no_warning / wrong if wrong else None,
            "correct_with_warning": sum(value["correct_with_warning"] for value in values),
            "empty_cases": len(empty), "empty_false_characters": sum(value["insertions"] for value in empty),
            "table_cells": cells, "table_correct_cells": sum(table["correct"] for table in tables),
            "median_ms": statistics.median(times) if times else None,
            "p95_ms": times[max(0, math.ceil(len(times) * .95) - 1)] if times else None}


def summarize(records):
    slices = defaultdict(list)
    for record in records:
        for key in ("source_kind", "split"):
            slices[f"{key}:{record[key]}"].append(record)
        for key, value in record.get("tags", {}).items():
            slices[f"{key}:{value}"].append(record)
    return {"overall": aggregate(records), "slices": {key: aggregate(value) for key, value in sorted(slices.items())}}
