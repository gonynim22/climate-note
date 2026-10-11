"""정답 좌표 직접 인식과 사각형 관측. 제품 기본값/예측을 변경하지 않는다."""
from collections import Counter, defaultdict
import statistics
from time import perf_counter

from .corpus import valid_text
from .metrics import edit_counts, normalize, score_case

VARIANTS = (("as-annotated", 0), ("pad-2", 2))


def no_space(text):
    return "".join(normalize(text).split())


def area(box):
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def intersection(a, b):
    box = [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]
    return box if area(box) else None


def union_area(boxes):
    """겹친 면적을 중복 합산하지 않는다. 입력은 한 주석에 잘린 교차 영역이다."""
    xs = sorted({box[x] for box in boxes for x in (0, 2)})
    total = 0
    for left, right in zip(xs, xs[1:]):
        spans = sorted((box[1], box[3]) for box in boxes if box[0] < right and box[2] > left)
        covered, end = 0, None
        for top, bottom in spans:
            covered += max(0, bottom - (top if end is None else max(top, end)))
            end = bottom if end is None else max(end, bottom)
        total += (right - left) * covered
    return total


def geometry(regions, detections):
    targets = [region["box"] for region in regions]
    overlaps, rows = [[] for _ in detections], []
    for index, target in enumerate(targets):
        intersections, matches, best, best_area = [], [], None, 0
        for det_id, detected in enumerate(detections):
            clipped = intersection(target, detected)
            overlap = area(clipped) if clipped else 0
            if clipped:
                intersections.append(clipped)
            if overlap > best_area:
                best, best_area = det_id, overlap
            if overlap / min(area(target), area(detected)) >= .5:
                matches.append(det_id)
                overlaps[det_id].append(index)
        rows.append({"index": index, "box": target, "coverage": union_area(intersections) / area(target),
                     "matched_detections": matches, "best_detection": best,
                     "best_iou": best_area / (area(target) + area(detections[best]) - best_area) if best is not None else 0,
                     "height_ratio": (detections[best][3] - detections[best][1]) / (target[3] - target[1]) if best is not None else None})
    duplicate_pairs = []
    for index, first in enumerate(detections):
        for other in range(index + 1, len(detections)):
            clipped = intersection(first, detections[other])
            if clipped and area(clipped) / min(area(first), area(detections[other])) >= .5:
                duplicate_pairs.append([index, other])
    return {"regions": rows, "detections": detections, "low_coverage_regions": sum(row["coverage"] < .5 for row in rows),
            "multi_detection_regions": sum(len(row["matched_detections"]) > 1 for row in rows),
            "multi_region_detections": sum(len(ids) > 1 for ids in overlaps),
            "unmatched_detections": sum(not ids for ids in overlaps), "large_overlap_pairs": duplicate_pairs,
            "small_detections": sum(box[3] - box[1] <= 8 or box[2] - box[0] <= 3 for box in detections)}


def diagnose_regions(engine, rgb, case, detections, pack_prediction):
    from screen_text.engine import MAX_SIDE, UPSCALE
    from screen_text.layout import TextBox
    started = perf_counter()
    regions = case.get("regions", [])
    result = {"version": 1, "status": "ok", "variants": []}
    if case["review_status"] == "unreviewed":
        return result | {"status": "unreviewed"}
    if not regions:
        return result | {"status": "missing_annotations"}
    if len(regions) > 256 or len(detections) > 512:
        return result | {"status": "size_limit"}
    if max(rgb.shape[:2]) > MAX_SIDE or UPSCALE != 1:
        return result | {"status": "input_resized"}
    if any(not valid_text(region.get("text")) or not no_space(region["text"]) for region in regions):
        return result | {"status": "missing_region_text"}
    if no_space("".join(region["text"] for region in regions)) != no_space(case["expected"]["text"]):
        return result | {"status": "incomplete_annotations"}
    result["geometry"] = geometry(regions, detections)
    height, width = rgb.shape[:2]
    for name, padding in VARIANTS:
        boxes = [[max(0, row["box"][0] - padding), max(0, row["box"][1] - padding),
                  min(width, row["box"][2] + padding), min(height, row["box"][3] + padding)] for row in regions]
        tick = perf_counter()
        # 같은 전체 RGB와 좌표만 인식기로 보낸다. 정답 문자열은 출력 뒤 채점에만 사용한다.
        outputs = engine._read(rgb, boxes, lambda: False)
        read_ms = (perf_counter() - tick) * 1000
        if len(outputs) != len(regions):
            raise ValueError("주석 영역 수와 인식 결과 수가 다릅니다")
        rows, text_boxes = [], []
        for index, (region, box, (text, score)) in enumerate(zip(regions, boxes, outputs)):
            text = text.strip()
            rows.append({"index": index, "box": box, "expected": region["text"], "text": text, "score": score,
                         "strict": edit_counts(region["text"], text),
                         "no_space": edit_counts(no_space(region["text"]), no_space(text))})
            if text:
                text_boxes.append(TextBox(box[0], box[1], box[2] - box[0], box[3] - box[1], text, score))
        prediction = pack_prediction(text_boxes)
        result["variants"].append({"name": name, "padding_px": padding, "read_ms": read_ms, "regions": rows,
            "prediction": prediction, "metrics": score_case(case, prediction),
            "ordered_no_space": edit_counts(no_space(case["expected"]["text"]), "".join(no_space(row["text"]) for row in rows))})
    result["total_ms"] = (perf_counter() - started) * 1000
    return result


def summarize_regions(records):
    observed = [row for row in records if "region_diagnostic" in row.get("prediction", {})]
    if not observed:
        return None
    statuses = Counter(row["prediction"]["region_diagnostic"]["status"] for row in observed)
    paired = [row for row in observed if row["status"] == "ok" and row.get("metrics")
              and row["prediction"]["region_diagnostic"]["status"] == "ok"]

    def measure(rows):
        baseline_errors = sum(row["metrics"]["no_space"]["errors"] for row in rows)
        reference = sum(row["metrics"]["no_space"]["reference_chars"] for row in rows)
        variants = []
        for name, _ in VARIANTS:
            values = [(row, next(value for value in row["prediction"]["region_diagnostic"]["variants"] if value["name"] == name)) for row in rows]
            counts = dict(both_correct=0, recovered=0, newly_wrong=0, both_wrong=0)
            for row, value in values:
                old, new = row["metrics"]["no_space"]["exact"], value["ordered_no_space"]["exact"]
                counts["both_correct" if old and new else "newly_wrong" if old else "recovered" if new else "both_wrong"] += 1
            errors = sum(value["ordered_no_space"]["errors"] for _, value in values)
            layout_errors = sum(value["metrics"]["no_space"]["errors"] for _, value in values)
            regional = [region for _, value in values for region in value["regions"]]
            tables = [value["metrics"]["table"] for _, value in values if value["metrics"]["table"] is not None]
            variants.append({"name": name, "ordered_errors": errors, "ordered_cer": errors / reference if reference else None,
                "layout_errors": layout_errors, "layout_cer": layout_errors / reference if reference else None,
                "region_errors": sum(region["no_space"]["errors"] for region in regional),
                "regions": len(regional), "regions_exact": sum(region["no_space"]["exact"] for region in regional),
                "case_changes": counts, "table_correct_cells": sum(table["correct"] for table in tables),
                "table_cells": sum(table["cells"] for table in tables),
                "median_read_ms": statistics.median(value["read_ms"] for _, value in values) if values else None})
        geos = [row["prediction"]["region_diagnostic"]["geometry"] for row in rows]
        regions = [region for geo in geos for region in geo["regions"]]
        heights = [region["height_ratio"] for region in regions if region["height_ratio"] is not None]
        return {"cases": len(rows), "reference_chars": reference, "baseline_errors": baseline_errors,
                "baseline_cer": baseline_errors / reference if reference else None, "variants": variants,
                "geometry": {"regions": len(regions), "detections": sum(len(geo["detections"]) for geo in geos),
                    **{key: sum(geo[key] for geo in geos) for key in ("low_coverage_regions", "multi_detection_regions",
                         "multi_region_detections", "unmatched_detections", "small_detections")},
                    "large_overlap_pairs": sum(len(geo["large_overlap_pairs"]) for geo in geos),
                    "median_coverage": statistics.median(region["coverage"] for region in regions) if regions else None,
                    "median_height_ratio": statistics.median(heights) if heights else None}}
    slices = {}
    for field in ("condition", "category"):
        groups = defaultdict(list)
        for row in paired:
            groups[str(row.get("tags", {}).get(field, "미분류"))].append(row)
        slices[field] = {key: measure(rows) for key, rows in sorted(groups.items())}
    return {"version": 1, "observed": len(observed), "total": len(records), "statuses": dict(statuses),
            "eligible": len(paired), "excluded": len(records) - len(paired), "overall": measure(paired), "slices": slices}
