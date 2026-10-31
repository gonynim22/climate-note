"""Synthetic calendar column investigation; never imports the app before isolation.

Run with the project's venv. Results are kept in a fresh output/harness directory.
Variants are process-local controls, not changes to application code.
"""

import argparse
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("baseline", "stretch", "ignored", "both"), default="baseline")
    parser.add_argument("--pattern", choices=("all", "weekdays", "mixed"), default="weekdays")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-columns-" + uuid.uuid4().hex[:8]
    run = root / "output" / "harness" / run_id
    run.mkdir(parents=True)
    os.environ["LOCALAPPDATA"] = str(run / "appdata")
    os.environ["CLIMATENOTE_SKIP_STARTUP_REFRESH"] = "1"
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "src"))  # 앱 모듈(B안)

    from PySide6.QtCore import QRect, QTimer, QCoreApplication, QEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QSizePolicy
    import database as db
    from app_fonts import apply_app_font, load_ui_fonts
    from ui_main import MainCalendarWindow, CalendarDayButton

    app = QApplication([])
    load_ui_fonts()
    apply_app_font(db.DEFAULT_APP_FONT, app)
    db.migrate()
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    today = date.today()
    sample_dates = {}
    # This month only; no holiday generation or production dataset is used.
    for day in range(1, 29):
        target = today.replace(day=day)
        col = (target.weekday() + 1) % 7
        sample_dates.setdefault(col, target.isoformat())
        if args.pattern == "weekdays" and col not in (1, 2, 3, 4):
            continue
        text = "합성 일정 회의 자료 검토 및 현장 점검 결과 정리 " * 3
        if args.pattern == "mixed" and col in (0, 5, 6):
            text = "짧은 일정"
        db.add_schedule(target.isoformat(), text)

    class Screen:
        def __init__(self, width, height):
            self.rect = QRect(0, 0, width, height)

        def availableGeometry(self):
            return self.rect

    screen = Screen(args.width, args.height)
    MainCalendarWindow._get_target_screen = lambda self: screen
    if args.variant in ("ignored", "both"):
        make_chip = CalendarDayButton._make_chip

        def controlled_chip(self, *values, **kwargs):
            chip = make_chip(self, *values, **kwargs)
            chip.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            return chip

        CalendarDayButton._make_chip = controlled_chip
    if args.variant in ("stretch", "both"):
        build = MainCalendarWindow._build_ui

        def controlled_build(self):
            build(self)
            for col in range(7):
                self.calendar_grid.setColumnStretch(col, 1)

        MainCalendarWindow._build_ui = controlled_build

    win = MainCalendarWindow()
    win.show()
    snapshots = []

    def record(stage):
        QTest.qWait(400)
        cols = []
        for col in range(7):
            cell = win._day_cells[sample_dates[col]]
            chip_item = cell._chips_layout.itemAt(0)
            chip = chip_item.widget() if chip_item else None
            cols.append({
                "col": col, "date": cell.target_date,
                "width": win.calendar_grid.cellRect(1, col).width(),
                "cell_width": cell.width(), "cell_min_hint": cell.minimumSizeHint().width(),
                "cell_hint": cell.sizeHint().width(),
                "container_width": cell._chips_container.width(),
                "chip_width": chip.width() if chip else None,
                "chip_min_hint": chip.minimumSizeHint().width() if chip else None,
                "chip_text": chip.text() if chip else None,
            })
        snapshot = {"stage": stage, "window": [win.width(), win.height()], "columns": cols}
        snapshots.append(snapshot)
        print(stage, "widths=", [c["width"] for c in cols], "hints=", [c["cell_min_hint"] for c in cols], flush=True)
        win.grab().save(str(run / (stage + ".png")))

    record("portrait-startup")
    for col in (5, 6):
        db.add_schedule(sample_dates[col], "금토 합성 일정 확인 회의")
        win._refresh_cell_for_date(sample_dates[col])
    record("portrait-added-friday-saturday")
    win._on_next_month()
    QTest.qWait(100)
    win._on_today()
    record("portrait-month-return")
    screen = Screen(1920, 1080)
    win._on_screen_changed()
    record("landscape")
    screen = Screen(args.width, args.height)
    win._on_screen_changed()
    record("portrait-after-screen-change")
    win._on_next_month()
    QTest.qWait(100)
    win._on_today()
    record("portrait-after-second-month-return")

    report = {
        "run_id": run_id, "arguments": vars(args), "platform": app.platformName(),
        "qt_scale_factor": os.environ.get("QT_SCALE_FACTOR", "default"),
        "source_sha256": hashlib.sha256((root / "src" / "ui_main.py").read_bytes()).hexdigest(),
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "snapshots": snapshots,
        "manual_unverified": "Actual company monitor, native Windows layout, mixed DPI and KVM",
    }
    with open(run / "result.json", "w", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    lines = ["# Calendar column diagnostic", "", f"Run: {run_id}", f"Arguments: {vars(args)}", "", "Measurements only; this is not a passing UI regression check.", "", "| Stage | Widths (Sun..Sat) |", "|---|---|"]
    lines.extend(f"| {s['stage']} | {[c['width'] for c in s['columns']]} |" for s in snapshots)
    lines += ["", "Actual company monitor / native Windows / mixed DPI / KVM: unverified."]
    with open(run / "summary.md", "w", encoding="utf-8") as output:
        output.write("\n".join(lines) + "\n")
    for timer in win.findChildren(QTimer):
        timer.stop()
    win._discard_data_widgets()
    win.hide()
    win.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    print("REPORT", run / "summary.md", flush=True)


if __name__ == "__main__":
    main()
