"""라벨 원문을 바꾸지 않는 학습 자료 사전검사와 자료 묶음 간 누출 검사."""
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import unicodedata


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    with open(path, "x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def ctc_required_steps(text):
    return len(text) + sum(left == right for left, right in zip(text, text[1:]))


def length_bucket(text):
    size = len(text)
    for maximum in (12, 23, 48, 64):
        if size <= maximum:
            return f"le_{maximum}"
    return "over_64"


def near_key(text):
    """누출 감사용 키만 숫자/공백을 통일한다. NFKC나 라벨 치환은 금지."""
    value = unicodedata.normalize("NFC", text)
    value = re.sub(r"\d+(?:[.,:]\d+)*", "#", value)
    return " ".join(value.split()).casefold()


def cross_audit(manifests, reference_texts=(), threshold=.88):
    """여러 manifest 사이의 동일 계보/이미지/원문/유사 문구를 감사한다.

    reference_texts는 이미 공개된 합성 회귀 문구만 명시적으로 전달한다.
    디스크를 탐색하거나 보류 자료 manifest를 자동 열지 않는다.
    """
    identities = defaultdict(dict)
    sources = {}
    failures = []
    warnings = []
    for manifest in manifests:
        for case in manifest["cases"]:
            split = case["split"]
            for name in ("document_id", "template_family_id", "source_group_id", "image_sha256"):
                value = case[name]
                previous = identities[name].setdefault(value, (split, case["case_id"]))
                if previous[0] != split:
                    failures.append({"kind": name, "left": previous[1], "right": case["case_id"]})
            key = " ".join(unicodedata.normalize("NFC", case["text"]).split())
            previous = identities["text"].setdefault(key, (split, case["case_id"]))
            if previous[0] != split:
                failures.append({"kind": "exact_text", "left": previous[1], "right": case["case_id"]})
            source_key = (manifest["dataset_id"], case["source_group_id"])
            if source_key in sources and sources[source_key]["text"] != case["text"]:
                failures.append({"kind": "group_text_changed", "left": sources[source_key]["case_id"],
                                 "right": case["case_id"]})
            sources[source_key] = case
    rows = list(sources.values())
    for index, left in enumerate(rows):
        left_key = near_key(left["text"])
        for right in rows[index + 1:]:
            if left["split"] == right["split"]:
                continue
            right_key = near_key(right["text"])
            ratio = SequenceMatcher(None, left_key, right_key, autojunk=False).ratio()
            if ratio >= threshold:
                failures.append({"kind": "near_text", "left": left["case_id"], "right": right["case_id"],
                                 "ratio": ratio, "threshold": threshold})
        for ref_index, reference in enumerate(reference_texts):
            reference_key = near_key(reference)
            ratio = SequenceMatcher(None, left_key, reference_key, autojunk=False).ratio()
            if ratio >= threshold:
                failures.append({"kind": "previous_synthetic_text", "case_id": left["case_id"],
                                 "reference_index": ref_index, "ratio": ratio})
    return {"status": "passed" if not failures else "failed", "near_threshold": threshold,
            "source_count": len(rows), "failures": failures, "warnings": warnings,
            "limitation": "문구 유사도는 의미 중복의 완전한 검출기가 아니다. 작성 계보와 함께 검토한다."}


def label_check(case, alphabet, steps_map=None, max_length=64):
    text = case["text"]
    reasons = []
    if not text or not text.strip():
        reasons.append("empty_label")
    if "\t" in text or "\n" in text or "\r" in text or any(ord(char) < 32 for char in text):
        reasons.append("label_control_character")
    if len(text) > max_length:
        reasons.append("length_exceeds_limit")
    if unicodedata.normalize("NFC", text) != text:
        reasons.append("non_nfc_preserved")
    oov = sorted(set(text) - alphabet)
    if oov:
        reasons.append("oov")
    if case.get("render_check", {}).get("glyph_zero_count", 0):
        reasons.append("missing_glyph")
    if case.get("render_check", {}).get("ink_clipped", False):
        reasons.append("ink_clipped")
    width, height = case["image_size"]
    native_width = max(8, (48 * width + height - 1) // height)
    bucket_width = ((native_width + 31) // 32) * 32
    observed = (steps_map or {}).get(str(bucket_width))
    required = ctc_required_steps(text)
    if observed is not None and observed < required:
        reasons.append("ctc_steps_insufficient")
    return {"eligible_without_ctc": not reasons, "reasons": reasons, "oov": oov,
            "length": len(text), "length_bucket": length_bucket(text),
            "ctc_required_steps": required, "native_width_at_48": native_width,
            "training_bucket_width": bucket_width, "ctc_observed_steps": observed,
            "ctc_status": "unmeasured" if observed is None else "passed" if observed >= required else "failed",
            "training_ready": not reasons and observed is not None}


def validate_manifest(directory):
    """원본과 crop 해시/좌표를 검증하며 사용자 폴더나 다른 corpus는 열지 않는다."""
    from PIL import Image
    directory = Path(directory).resolve()
    with open(directory / "manifest.json", encoding="utf-8") as stream:
        manifest = json.load(stream)
    if manifest.get("schema_version") != 1 or manifest.get("split") not in {"train", "selection", "final"}:
        raise ValueError("잘못된 학습 manifest 스키마/분할")
    seen = set()
    for case in manifest["cases"]:
        if case["case_id"] in seen or case["split"] != manifest["split"]:
            raise ValueError("중복 사례 ID 또는 manifest와 다른 분할")
        seen.add(case["case_id"])
        if case["text"] != case["expected"]["text"]:
            raise ValueError("원문과 정답이 다릅니다")
        sizes = {}
        for image_key, hash_key in (("image", "image_sha256"), ("source_image", "source_image_sha256")):
            relative = Path(case[image_key])
            path = (directory / relative).resolve()
            if relative.is_absolute() or not path.is_relative_to(directory):
                raise ValueError("이미지 경로가 자료 폴더를 벗어났습니다")
            if sha256(path) != case[hash_key]:
                raise ValueError("이미지 해시 불일치")
            with Image.open(path) as picture:
                if picture.format != "PNG":
                    raise ValueError("자료는 PNG여야 합니다")
                sizes[image_key] = picture.size
                picture.verify()
        if list(sizes["image"]) != case["image_size"]:
            raise ValueError("crop 이미지 크기 불일치")
        x0, y0, x1, y1 = case["crop"]
        source_width, source_height = sizes["source_image"]
        if not (0 <= x0 < x1 <= source_width and 0 <= y0 < y1 <= source_height):
            raise ValueError("crop 좌표 범위 오류")
        if sizes["image"] != (x1 - x0, y1 - y0):
            raise ValueError("crop 좌표와 이미지 크기 불일치")
        with Image.open(directory / case["source_image"]) as source, Image.open(directory / case["image"]) as crop:
            if source.crop(case["crop"]).convert("RGB").tobytes() != crop.convert("RGB").tobytes():
                raise ValueError("원본 좌표와 crop 픽셀이 다릅니다")
    return manifest


def coverage(manifest):
    cases = manifest["cases"]
    sources = {case["source_group_id"]: case for case in cases}
    oov = Counter(char for case in sources.values() for char in case["checks"]["oov"])
    return {"images": len(cases), "unique_texts": len({case["text"] for case in cases}),
            "source_groups": len(sources), "document_families": len({case["document_id"] for case in cases}),
            "template_families": len({case["template_family_id"] for case in cases}),
            "category_images": dict(Counter(case["tags"]["category"] for case in cases)),
            "category_source_groups": dict(Counter(case["tags"]["category"] for case in sources.values())),
            "length_source_groups": dict(Counter(case["checks"]["length_bucket"] for case in sources.values())),
            "oov_source_group_presence": dict(oov),
            "a_eligible_pending_ctc": sum(case["checks"]["eligible_without_ctc"] for case in cases),
            "ctc_unmeasured": sum(case["checks"]["ctc_status"] == "unmeasured" for case in cases),
            "training_ready": sum(case["checks"]["training_ready"] for case in cases),
            "excluded_reasons": dict(Counter(reason for case in cases for reason in case["checks"]["reasons"])),
            "glyph_zero_images": sum(bool(case["render_check"]["glyph_zero_count"]) for case in cases),
            "ink_clipped_images": sum(case["render_check"]["ink_clipped"] for case in cases),
            "fallback_observed_images": sum(case["render_check"]["fallback_observed"] for case in cases),
            "glyph_run_families": dict(Counter(family for case in cases for family in case["render_check"]["glyph_run_families"])),
            "human_reviewed": 0, "real_application_captures": 0,
            "independent_template_target": {"train": 1200, "selection": 200}.get(manifest["split"]),
            "target_completed": False}


def validate_source_plan(plan, reference_texts=()):
    """외부에서 작성한 새 원문 계획을 렌더 전에 감사한다. final은 허용하지 않는다."""
    if not isinstance(plan, dict) or set(plan) != {"train", "selection"}:
        raise ValueError("원문 계획은 train/selection만 포함해야 합니다")
    manifests = []
    seen = set()
    for split, rows in plan.items():
        if not isinstance(rows, list) or not rows:
            raise ValueError("각 분할에는 작성한 원문 목록이 필요합니다")
        cases = []
        for source in rows:
            if not isinstance(source, dict) or source.get("split") != split:
                raise ValueError("원문 분할이 다릅니다")
            for key in ("source_id", "source_group_id", "document_id", "template_family_id"):
                if not isinstance(source.get(key), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", source[key]):
                    raise ValueError("원문/계보 ID가 잘못되었습니다")
            if source["source_id"] in seen:
                raise ValueError("source_id 중복")
            seen.add(source["source_id"])
            if source.get("category") not in {"body", "table", "numeric", "memo"}:
                raise ValueError("본문/표셀/숫자/메모 분류가 필요합니다")
            text = source.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 8192:
                raise ValueError("원문이 비었거나 너무 깁니다")
            if "\n" in text or "\r" in text or "\t" in text:
                raise ValueError("줄 crop 원문에는 줄바꿈/Tab을 넣을 수 없습니다")
            if any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in text):
                raise ValueError("원문에 제어 문자 또는 잘못된 Unicode가 있습니다")
            if not isinstance(source.get("critical_tags"), list) or not set(source["critical_tags"]) <= {"numbers", "money", "date", "units"}:
                raise ValueError("중요 항목 태그가 잘못되었습니다")
            cases.append({**source, "case_id": source["source_id"], "image_sha256": "unrendered-" + source["source_id"]})
        manifests.append({"dataset_id": "source-plan-" + split, "cases": cases})
    result = cross_audit(manifests, reference_texts)
    if result["failures"]:
        raise ValueError("렌더 전 원문 누출 감사 실패: " + json.dumps(result["failures"], ensure_ascii=False))
    return result
