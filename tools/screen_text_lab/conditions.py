"""같은 원문에 한 조건씩 적용하는 합성 자료. 실제 화면/OS DPI 캡처가 아니다."""
from collections import Counter
from datetime import datetime
from pathlib import Path
import random
import uuid

from .corpus import digest, load_corpus, read_json

PROFILE = "conditions-v1"
CONDITIONS = (
    {"id": "reference", "label": "기준 · 16px 밝음"},
    {"id": "font10", "label": "작은 글자 · 10px", "font_px": 10},
    {"id": "font12", "label": "작은 글자 · 12px", "font_px": 12},
    {"id": "font24", "label": "큰 글자 · 24px", "font_px": 24},
    {"id": "dark", "label": "어두운 배경", "theme": "dark"},
    {"id": "low_contrast", "label": "낮은 대비", "foreground": "#B6B6B6"},
    {"id": "wide", "label": "넓은 선택 · 1600px", "min_width": 1600},
    {"id": "margin2", "label": "좁은 여백 · 2px", "margin": 2},
    {"id": "dense", "label": "조밀한 줄 · 추가 간격 0", "line_gap": 0},
    {"id": "serif", "label": "명조체 · Batang", "font": "Batang"},
    {"id": "scale125", "label": "합성 배율 · 125%", "scale": 1.25},
    {"id": "scale150", "label": "합성 배율 · 150%", "scale": 1.5},
)


def specimens():
    directory = Path(__file__).parent / "recipes"
    previous = read_json(directory / "bootstrap.json")
    extra = read_json(directory / "conditions.json")
    sources = []
    for category, additions in extra["text"].items():
        texts = previous.get(category, []) + additions
        for index, text in enumerate(texts):
            sources.append({"id": f"cond-{category}-{index+1:03d}", "category": category,
                            "split": "dev" if index < 16 else "holdout",
                            "expected": {"text": text}, "ruled": False})
    for index, table in enumerate(extra["tables"]):
        sources.append({"id": f"cond-table-{index+1:03d}", "category": "table",
                        "split": "dev" if index < 16 else "holdout", "ruled": index % 2 == 0,
                        "expected": {"text": "\n".join(" ".join(cell for cell in row if cell) for row in table),
                                     "table": table}})
    return sources


def render(source, condition):
    from PySide6.QtGui import QColor, QFont, QFontInfo, QFontMetrics, QImage, QPainter
    scale = condition.get("scale", 1)
    px = lambda value: max(1, round(value * scale))
    size = px(condition.get("font_px", 16))
    margin = px(condition.get("margin", 16))
    gap = round(condition.get("line_gap", 10) * scale)
    family = condition.get("font", "Cascadia Mono" if source["category"] == "cli" else "Malgun Gothic")
    font = QFont(family)
    font.setPixelSize(size)
    fm = QFontMetrics(font)
    rows = source["expected"].get("table")
    lines = source["expected"]["text"].split("\n")
    line_height = fm.height() + gap
    widths = [max(fm.horizontalAdvance(row[c]) for row in rows) + px(40)
              for c in range(len(rows[0]))] if rows else []
    needed = sum(widths) if rows else max(fm.horizontalAdvance(line) for line in lines)
    width = max(px(condition.get("min_width", 240)), needed + 2 * margin + px(4))
    height = 2 * margin + line_height * len(lines) + px(4)
    dark = condition.get("theme") == "dark"
    background = "#171C25" if dark else "#FFFFFF"
    foreground = condition.get("foreground", "#E9EEF5" if dark else "#202B3A")
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(background))
    painter = QPainter(image)
    regions = []
    try:
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(font)
        painter.setPen(QColor(foreground))
        for row_index, line in enumerate(lines):
            top = margin + row_index * line_height
            x = margin
            cells = rows[row_index] if rows else [line]
            for column, cell in enumerate(cells):
                left = x + px(6) if rows else x
                if cell:
                    painter.drawText(left, top + fm.ascent(), cell)
                    regions.append({"box": [left, top, left + fm.horizontalAdvance(cell), top + fm.height()],
                                    "text": cell, "row": row_index, "column": column})
                if rows:
                    x += widths[column]
        if rows and source["ruled"]:
            painter.setPen(QColor("#536174" if dark else "#BAC5D2"))
            for row_index in range(len(rows) + 1):
                y = margin - px(2) + row_index * line_height
                painter.drawLine(margin, y, margin + sum(widths), y)
            x = margin
            for w in [0] + widths:
                x += w
                painter.drawLine(x, margin - px(2), x, margin - px(2) + len(rows) * line_height)
    finally:
        painter.end()
    tags = {"profile": PROFILE, "condition": condition["id"], "category": source["category"],
            "font_requested": family, "font_resolved": QFontInfo(font).family(), "font_px": size,
            "theme": "dark" if dark else "light", "foreground": foreground, "background": background,
            "margin_px": margin, "line_gap_px": gap, "synthetic_scale": scale,
            "selection": "wide" if condition["id"] == "wide" else "tight",
            "table_grid": bool(rows and source["ruled"]), "renderer": "QPainter synthetic"}
    return image, regions, tags


def render_corpus(sources, conditions, root, seed):
    from tools.verify import write_json
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    root = Path(root).resolve()
    directory = root / (datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
    (directory / "images").mkdir(parents=True, exist_ok=False)
    recipe_root = Path(__file__).parent / "recipes"
    recipe_hashes = {name: digest(recipe_root / name) for name in ("bootstrap.json", "conditions.json")}
    cases = []
    for source in sources:
        for condition in conditions:
            image, regions, tags = render(source, condition)
            case_id = source["id"] if condition["id"] == "reference" else source["id"] + "--" + condition["id"]
            path = directory / "images" / (case_id + ".png")
            if not image.save(str(path), "PNG"):
                raise OSError("조건별 합성 이미지 저장 실패")
            cases.append({"case_id": case_id, "source_group_id": source["id"],
                          "parent_id": None if condition["id"] == "reference" else source["id"],
                          "split": source["split"], "source_kind": "synthetic", "review_status": "generated",
                          "image": path.relative_to(directory).as_posix(), "image_sha256": digest(path),
                          "image_size": [image.width(), image.height()], "expected": source["expected"],
                          "regions": regions, "tags": tags,
                          "provenance": {"seed": seed, "recipe_sha256": recipe_hashes,
                                         "actual_screen_capture": False,
                                         "font_note": "font_resolved는 기본 family이며 글리프별 fallback을 보증하지 않음"}})
    random.Random(seed).shuffle(cases)
    write_json(directory / "manifest.json", {"schema_version": 1, "dataset_id": directory.name,
               "description": "같은 원문의 조건별 합성 이미지. Windows 프로그램/실제 DPI 캡처 아님.",
               "profile": PROFILE, "seed": seed, "recipe_sha256": recipe_hashes,
               "coverage": {"originals": len(sources), "conditions": len(conditions), "images": len(cases),
                            "originals_by_split": dict(Counter(source["split"] for source in sources))},
               "conditions": list(conditions), "cases": cases})
    load_corpus(directory)
    return directory


def generate_conditions(seed):
    from tools.verify import ROOT, inside
    return render_corpus(specimens(), CONDITIONS, inside(ROOT / "output/screen_text_lab/corpus", ROOT), seed)
