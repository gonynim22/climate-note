"""합성 줄 crop의 원본/라벨/검사/atlas를 새 버전으로 생성한다."""
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import platform
import sys
import uuid

from .audit import (coverage, cross_audit, label_check, sha256, validate_manifest, validate_source_plan, write_json)
from .sources import sources_for

CONDITIONS = (
    {"id": "reference", "font": "Malgun Gothic", "px": 16, "foreground": "#202B3A", "background": "#FFFFFF"},
    {"id": "small", "font": "Malgun Gothic", "px": 10, "foreground": "#202B3A", "background": "#FFFFFF"},
    {"id": "serif", "font": "Batang", "px": 16, "foreground": "#202B3A", "background": "#FFFFFF"},
    {"id": "dark", "font": "Malgun Gothic", "px": 14, "foreground": "#E9EEF5", "background": "#171C25"},
    {"id": "low_contrast", "font": "Malgun Gothic", "px": 12, "foreground": "#999999", "background": "#FFFFFF"},
)


def render_line(text, condition, table_cell=False):
    """높이 48 정규화 이전의 화면 픽셀 crop을 만든다. 실제 앱 캡처가 아니다."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QFont, QFontInfo, QImage, QPainter, QRawFont, QTextLayout
    font = QFont(condition["font"])
    font.setPixelSize(condition["px"])
    layout = QTextLayout(text, font)
    layout.beginLayout()
    line = layout.createLine()
    line.setLineWidth(20000)
    layout.endLayout()
    width = int(line.naturalTextWidth() + .999) + 40
    height = int(line.height() + .999) + 40
    image = QImage(width, height, QImage.Format.Format_RGB32)
    background = QColor(condition["background"])
    image.fill(background)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setPen(QColor(condition["foreground"]))
        layout.draw(painter, QPointF(20, 20))
        if table_cell:
            painter.setPen(QColor("#687383" if condition["id"] == "dark" else "#C0C7D0"))
            painter.drawRect(6, 6, width - 13, height - 13)
    finally:
        painter.end()
    # 글꼴별 실제 glyph run을 기록한다. 기본 family 하나만으로 fallback을 추정하지 않는다.
    glyph_runs = layout.glyphRuns()
    families = sorted({run.rawFont().familyName() for run in glyph_runs})
    missing = sum(index == 0 for run in glyph_runs for index in run.glyphIndexes())
    primary = QRawFont.fromFont(font)
    missing_primary = sorted({char for char in text if not char.isspace() and not primary.supportsCharacter(ord(char))})
    # 글리프가 원래 여유 경계에 닿으면 잘림으로 기록한다. 표 테두리는 제외한다.
    crop_box = [16, 16, width - 16, height - 16]
    crop = image.copy(crop_box[0], crop_box[1], crop_box[2] - crop_box[0], crop_box[3] - crop_box[1])
    edge_ink = any(crop.pixelColor(x, y) != background
                   for x, y in ([(x, 0) for x in range(crop.width())]
                                + [(x, crop.height() - 1) for x in range(crop.width())]
                                + [(0, y) for y in range(crop.height())]
                                + [(crop.width() - 1, y) for y in range(crop.height())]))
    render_check = {"glyph_zero_count": missing, "glyph_run_families": families,
                    "primary_font_missing_characters": missing_primary,
                    "fallback_observed": any(family.casefold() != QFontInfo(font).family().casefold() for family in families),
                    "ink_clipped": edge_ink, "font_resolved": QFontInfo(font).family(),
                    "note": "Qt glyph run 검사. 사람의 독립 문자 대조나 Windows ClearType 검증 아님."}
    return image, crop, crop_box, render_check


def write_atlas(directory, manifest):
    rows = []
    for case in manifest["cases"]:
        checks = case["checks"]
        rows.append("<article><h2>" + html.escape(case["case_id"]) + "</h2><img src=\""
                    + html.escape(case["image"], quote=True) + "\" alt=\"합성 줄 crop\">"
                    + "<p class=\"text\">" + html.escape(case["text"]) + "</p><p>"
                    + html.escape(f"{case['template_family_id']} | {len(case['text'])}자 | "
                                  f"OOV {checks['oov']} | {checks['ctc_status']} | "
                                  f"글리프 {case['render_check']['glyph_run_families']}")
                    + "</p><a href=\"" + html.escape(case["source_image"], quote=True) + "\">원본 합성 화면</a></article>")
    body = ("<!doctype html><html lang=\"ko\"><meta charset=\"utf-8\"><title>합성 OCR 학습 자료</title>"
            "<style>body{font:15px 'Malgun Gothic',sans-serif;margin:24px;background:#f3f5f8;color:#202b3a}"
            "article{padding:16px;background:white;border:1px solid #ccd3dc;margin:12px 0;overflow:auto}"
            "h1{font-size:24px}h2{font-size:16px}.text{white-space:pre-wrap}img{max-width:none}</style>"
            "<h1>합성 줄 자료 — " + html.escape(manifest["split"]) + "</h1>"
            "<p>직접 작성한 시험 문구와 Qt 생성 이미지입니다. 실제 앱/DPI 캡처 또는 사람 검토 완료가 아닙니다. "
            "OOV를 치환하지 않았고 표 셀 crop으로 표 구조 정확도를 검증할 수 없습니다.</p>"
            + "".join(rows) + "</html>")
    with open(directory / "atlas.html", "x", encoding="utf-8", newline="\n") as stream:
        stream.write(body)


def reference_synthetic_texts():
    """이미 평가에 사용된 합성 recipe만 읽는다. 실제 캡처/holdout 폴더는 열지 않는다."""
    from ..conditions import specimens
    rows = []
    for source in specimens():
        rows.extend(source["expected"]["text"].splitlines())
        if source["expected"].get("table"):
            rows.extend(cell for row in source["expected"]["table"] for cell in row if cell)
    return sorted(set(rows))


def generate(output_root, dictionary_path, *, run_root=None, steps_map=None, seed=20261011, source_plan=None,
             steps_provenance=None):
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtCore import qVersion
    app = QGuiApplication.instance() or QGuiApplication([])
    started = datetime.now(timezone.utc).isoformat()
    planned = source_plan if source_plan is not None else {split: sources_for(split) for split in ("train", "selection")}
    references = reference_synthetic_texts()
    source_audit = validate_source_plan(planned, references)
    suffix = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    directory = Path(output_root).resolve() / ("pilot-" + suffix)
    directory.mkdir(parents=True, exist_ok=False)
    dictionary_path = Path(dictionary_path).resolve()
    with open(dictionary_path, encoding="utf-8") as stream:
        dictionary = stream.read().splitlines()
    if len(dictionary) != len(set(dictionary)) or any(len(char) != 1 for char in dictionary):
        raise ValueError("문자 사전은 중복 없는 한 줄 한 문자여야 합니다")
    alphabet = set(dictionary) | {" "}
    manifests = []
    source_hashes = {path.name: sha256(path) for path in Path(__file__).parent.glob("*.py")}
    recipe = {"seed": seed, "conditions": CONDITIONS, "dictionary_sha256": sha256(dictionary_path),
              "source_hashes": source_hashes, "max_text_length": 64,
              "NRTR_configuration_note": "학습 encoder의 특수토큰 여유를 별도 검증해야 함; 64자이면 설정66 후보",
              "width_policy": "높이48 비율유지 ceil, 학습 후보 ceil32 bucket; 제품전처리와 구분",
              "steps_map_supplied": steps_map is not None, "Qt": qVersion(),
              "steps_provenance": steps_provenance,
              "python_version": platform.python_version(), "python_executable": sys.executable,
              "source_license": "직접 작성한 가상 행정 시험 문구. 실제 기관 문서/사용자 자료 없음.",
              "final_access": "final 생성/열람 안 함; 실제 보류 12장 접근 안 함"}
    write_json(directory / "recipe.json", recipe)
    write_json(directory / "source-plan.json", planned)
    write_json(directory / "source-plan-audit.json", source_audit)
    for split in ("train", "selection"):
        split_dir = directory / split
        (split_dir / "images").mkdir(parents=True)
        (split_dir / "sources").mkdir()
        cases = []
        for source in planned[split]:
            for condition in CONDITIONS:
                case_id = source["source_id"] + "--" + condition["id"]
                image, crop, box, render_check = render_line(source["text"], condition, source["category"] == "table")
                source_image = split_dir / "sources" / (case_id + ".png")
                crop_image = split_dir / "images" / (case_id + ".png")
                if not image.save(str(source_image), "PNG") or not crop.save(str(crop_image), "PNG"):
                    raise OSError("합성 이미지 저장 실패")
                case = {"case_id": case_id, "source_group_id": source["source_group_id"],
                        "document_id": source["document_id"], "template_family_id": source["template_family_id"],
                        "split": split, "source_kind": "synthetic", "review_status": "generated",
                        "text": source["text"], "expected": {"text": source["text"]},
                        "image": crop_image.relative_to(split_dir).as_posix(), "image_sha256": sha256(crop_image),
                        "image_size": [crop.width(), crop.height()], "crop": box,
                        "source_image": source_image.relative_to(split_dir).as_posix(), "source_image_sha256": sha256(source_image),
                        "source_size": [image.width(), image.height()], "critical_tags": source["critical_tags"],
                        "evaluation_scope": "line_crop", "render_check": render_check,
                        "tags": {"category": source["category"], "condition": condition["id"],
                                 "font_requested": condition["font"], "font_resolved": render_check["font_resolved"],
                                 "font_px": condition["px"], "theme": "dark" if condition["id"] == "dark" else "light",
                                 "renderer": "QTextLayout synthetic", "actual_windows_dpi": "not_measured",
                                 "actual_program_capture": False, "table_cell_context": source["category"] == "table"},
                        "review_provenance": {"reviewer_kind": "generator", "method": "source_text_and_render_checks",
                                              "human_reviewed": False, "created_at": started},
                        "provenance": {"seed": seed, "authoring": "new_synthetic_administrative_text",
                                       "source_license": recipe["source_license"], "source_hashes": source_hashes}}
                case["checks"] = label_check(case, alphabet, steps_map)
                case["ctc_required_steps"] = case["checks"]["ctc_required_steps"]
                cases.append(case)
        manifest = {"schema_version": 1, "dataset_id": directory.name + "-" + split,
                    "split": split, "created_at": started, "dictionary_sha256": recipe["dictionary_sha256"],
                    "cases": cases, "limitations": ["synthetic_only", "no_human_review", "crop_not_table_structure",
                                                      "pilot_below_independent_template_target", "no_final_data"]}
        write_json(split_dir / "manifest.json", manifest)
        write_json(split_dir / "coverage.json", coverage(manifest))
        excluded = [{"case_id": case["case_id"], "text": case["text"], **case["checks"]}
                    for case in cases if not case["checks"]["eligible_without_ctc"]]
        write_json(split_dir / "excluded-a.json", excluded)
        with open(split_dir / "labels-a.txt", "x", encoding="utf-8", newline="\n") as stream:
            for case in cases:
                if case["checks"]["eligible_without_ctc"]:
                    stream.write(case["image"] + "\t" + case["text"] + "\n")
        # B 원문 후보 목록이다. 사전 확장/CTC 검사 없이 학습을 허용하지 않는다.
        with open(split_dir / "labels-b-source.txt", "x", encoding="utf-8", newline="\n") as stream:
            for case in cases:
                stream.write(case["image"] + "\t" + case["text"] + "\n")
        write_atlas(split_dir, manifest)
        manifests.append(validate_manifest(split_dir))
    audit = cross_audit(manifests, references)
    write_json(directory / "cross-corpus-audit.json", audit)
    requested_widths = sorted({case["checks"]["training_bucket_width"] for manifest in manifests for case in manifest["cases"]})
    write_json(directory / "ctc-requested-widths.json", {"height": 48, "widths": requested_widths,
                                                         "status": "actual_model_measurement_required"})
    write_json(directory / "expansion-plan.json", {
        "status": "source_authoring_required", "conditions_per_source": len(CONDITIONS),
        "train": {"target_images": 6000, "target_source_groups": 1200, "current_source_groups": len(planned["train"]),
                  "current_template_families": len({source["template_family_id"] for source in planned["train"]})},
        "selection": {"target_images": 1000, "target_source_groups": 200, "current_source_groups": len(planned["selection"]),
                      "current_template_families": len({source["template_family_id"] for source in planned["selection"]})},
        "interface": "source-plan.json 목록에 직접 작성한 새 원문을 추가하고 --source-plan으로 별도버전 생성",
        "rules": ["렌더 전에 작성 문서/템플릿 가족을 분할", "숫자 치환을 독립 템플릿으로 세지 않음",
                  "새 원문 작성/사용 범위 확인", "35/35/25/5 범주 배분", "실제 캡처와 final은 별도 단계"],
    })
    result = {"status": "passed_data_checks_ctc_pending" if audit["status"] == "passed" else "failed",
              "started_at": started, "completed_at": datetime.now(timezone.utc).isoformat(),
              "dataset_root": str(directory), "source_hashes": source_hashes,
              "dictionary_sha256": recipe["dictionary_sha256"],
              "recipe_sha256": sha256(directory / "recipe.json"),
              "source_plan_sha256": sha256(directory / "source-plan.json"),
              "manifest_sha256": {split: sha256(directory / split / "manifest.json") for split in ("train", "selection")},
              "coverage": {manifest["split"]: coverage(manifest) for manifest in manifests},
              "cross_corpus_audit": audit, "image_integrity": "passed", "crop_pixel_roundtrip": "passed",
              "labels_a_note": "원문을 보존한 A 후보 라벨. 실제 모델 CTC와 학습 loader 확인 전 학습 허가 아님.",
              "full_expansion": "not_run: independent source/template targets not yet met",
              "final": "not_created_or_read", "real_capture": "not_run", "human_review": "not_run"}
    current_hashes = {path.name: sha256(path) for path in Path(__file__).parent.glob("*.py")}
    result["source_hashes_preserved"] = current_hashes == source_hashes
    result["dictionary_preserved"] = sha256(dictionary_path) == recipe["dictionary_sha256"]
    if not result["source_hashes_preserved"] or not result["dictionary_preserved"]:
        result["status"] = "failed_inputs_changed"
    if not result["status"].startswith("failed") and all(case["checks"]["ctc_status"] != "unmeasured" for manifest in manifests for case in manifest["cases"]):
        result["status"] = "passed_data_and_ctc_checks_loader_pending"
    write_json(directory / "result.json", result)
    summary = ["# OCR 합성 학습 자료 pilot", "", f"상태: {result['status']}",
               f"자료: `{directory}`", "", "원문·이미지·crop 좌표/픽셀·폰트 glyph run·OOV·길이·자료 묶음 간 누출을 검사했다.",
               "CTC의 measured/unmeasured는 coverage에 구분한다. 실제 학습 loader 검사는 별도이며 labels-a.txt만으로 학습을 허가하지 않는다.", ""]
    for split, report in result["coverage"].items():
        summary.extend([f"- {split}: {report['images']}장 / {report['unique_texts']}문구 / "
                        f"{report['document_families']}작성 문서 가족 / {report['template_families']}템플릿 가족.",
                        f"  A 사전검사 후보 {report['a_eligible_pending_ctc']}장, 제외 {report['excluded_reasons']}, "
                        f"분류 {report['category_images']}."])
    summary.extend(["", "6,000/1,000장 및 1,200/200개 독립 템플릿 목표는 완료하지 않았다. 숫자 치환으로 독립 수를 늘리지 않았다.",
                    "실제 앱·Windows DPI·사람 검토·최종 자료·제품 정확도는 미검증이다. 기존 사용자 자료와 보류 12장은 열지 않았다."])
    with open(directory / "summary.md", "x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(summary) + "\n")
    if run_root is not None:
        run_dir = Path(run_root).resolve() / ("datasets-" + suffix)
        run_dir.mkdir(parents=True, exist_ok=False)
        write_json(run_dir / "result.json", result)
        with open(run_dir / "summary.md", "x", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(summary) + "\n")
    return directory, result
