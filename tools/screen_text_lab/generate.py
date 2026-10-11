"""시험용 내용만 PNG로 렌더한다. 실제 프로그램 캡처를 가장하지 않는다."""
from datetime import datetime
from pathlib import Path
import random
import uuid

from .corpus import digest, load_corpus, read_json


def generate(seed=20261010, profile="bootstrap"):
    if profile == "conditions":
        from .conditions import generate_conditions
        return generate_conditions(seed)
    if profile != "bootstrap":
        raise ValueError("첫 버전은 bootstrap 100개 생성을 지원합니다")
    from tools.verify import ROOT, inside, write_json
    from PySide6.QtGui import QColor, QFont, QFontInfo, QFontMetrics, QGuiApplication, QImage, QPainter
    app = QGuiApplication.instance() or QGuiApplication([])
    corpus_root = inside(ROOT / "output/screen_text_lab/corpus", ROOT)
    directory = inside(corpus_root / (datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]), corpus_root)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "images").mkdir()
    recipes = read_json(Path(__file__).parent / "recipes/bootstrap.json")
    recipe_sha = digest(Path(__file__).parent / "recipes/bootstrap.json")
    rng = random.Random(seed)
    specimens = [(category, index, text, None) for category, texts in recipes.items() for index, text in enumerate(texts)]
    for i in range(10):
        table = [["항목", "수량", "금액"], [f"시험 {i + 1}", str(12 + i), f"{(12+i)*1350:,}"],
                 ["검토", str(3 + i), f"{(3+i)*2100:,}"]]
        specimens.append(("table", i, "\n".join(" ".join(row) for row in table), table))
    for i in range(10):
        table = [["날짜", "측정값", "단위"], [f"10/{i+1:02d}", f"{.125+i*.15:.3f}", "mg/L"],
                 [f"10/{i+11:02d}", f"{1.25+i*.2:.2f}", "ppm"]]
        specimens.append(("table_plain", i, "\n".join(" ".join(row) for row in table), table))
    cases = []
    for order, (category, index, text, table) in enumerate(specimens):
        size = (12, 14, 16, 20, 24)[(index + order // 10) % 5]
        dark = index % 2 == 1
        wide = index % 3 == 0
        margin = (8, 16, 28)[rng.randrange(3)]
        family = "Cascadia Mono" if category == "cli" else "Malgun Gothic"
        font = QFont(family)
        font.setPixelSize(size)
        font.setWeight(QFont.Weight.DemiBold if index == 8 else QFont.Weight.Normal)
        fm = QFontMetrics(font)
        lines = text.split("\n")
        line_height = fm.height() + max(8, round(size * .65))
        widths = [max(fm.horizontalAdvance(row[c]) for row in table) + 50 for c in range(len(table[0]))] if table else []
        needed = sum(widths) if table else max(fm.horizontalAdvance(line) for line in lines)
        width = max(1200 if wide else 240, needed + 2 * margin + 4)
        height = 2 * margin + line_height * len(lines) + 4
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor("#171C25" if dark else "#FFFFFF"))
        painter = QPainter(image)
        regions = []
        try:
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.setFont(font)
            color = QColor("#E9EEF5" if dark else "#202B3A")
            painter.setPen(color)
            for r, line in enumerate(lines):
                top, baseline = margin + r * line_height, margin + r * line_height + fm.ascent()
                if table:
                    x = margin
                    for c, cell in enumerate(table[r]):
                        painter.drawText(x + 6, baseline, cell)
                        regions.append({"box": [x + 6, top, x + 6 + fm.horizontalAdvance(cell), top + fm.height()],
                                        "text": cell, "row": r, "column": c})
                        x += widths[c]
                else:
                    painter.drawText(margin, baseline, line)
                    regions.append({"box": [margin, top, margin + fm.horizontalAdvance(line), top + fm.height()], "text": line})
            if category == "table":
                painter.setPen(QColor("#536174" if dark else "#BAC5D2"))
                for r in range(len(table) + 1):
                    y = margin - 4 + r * line_height
                    painter.drawLine(margin, y, margin + sum(widths), y)
                x = margin
                for column in range(len(widths) + 1):
                    painter.drawLine(x, margin - 4, x, margin - 4 + len(table) * line_height)
                    if column < len(widths):
                        x += widths[column]
        finally:
            painter.end()
        case_id = f"{category}-{index+1:02d}"
        path = directory / "images" / (case_id + ".png")
        if not image.save(str(path), "PNG"):
            raise OSError("합성 이미지 저장 실패")
        cases.append({"case_id": case_id, "source_group_id": f"bootstrap-{category}-{index+1:02d}" if table is None else f"bootstrap-{category}",
                      "parent_id": None, "split": "dev", "source_kind": "synthetic", "review_status": "generated",
                      "image": path.relative_to(directory).as_posix(), "image_sha256": digest(path),
                      "image_size": [width, height], "expected": {"text": text, **({"table": table} if table else {})},
                      "regions": regions, "tags": {"category": category, "font_requested": family,
                      "font_resolved": QFontInfo(font).family(), "font_px": size, "theme": "dark" if dark else "light",
                      "selection": "wide" if wide else "tight", "renderer": "QPainter synthetic", "margin_px": margin},
                      "provenance": {"seed": seed, "recipe_sha256": recipe_sha, "actual_screen_capture": False}})
    write_json(directory / "manifest.json", {"schema_version": 1, "dataset_id": directory.name,
               "description": "합성 bootstrap 100개. 실제 Windows 프로그램/DPI 캡처가 아님. 모두 개발용.",
               "seed": seed, "recipe_sha256": recipe_sha, "cases": cases})
    load_corpus(directory)
    return directory
