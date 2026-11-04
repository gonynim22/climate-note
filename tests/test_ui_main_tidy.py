"""디자인 점검 10·13·14번: 바로가기 칸, 일정 줄 삭제 아이콘, 날짜 머리줄 색."""
from collections import Counter

from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QApplication

import database as db
from ui_main import MainCalendarWindow, ScheduleRow, ShortcutSidebarWidget


def _hover(widget, inside=True):
    if inside:
        local = QPointF(5, 5)
        QApplication.sendEvent(widget, QEnterEvent(local, local, QPointF(widget.mapToGlobal(QPoint(5, 5)))))
    else:
        QApplication.sendEvent(widget, QEvent(QEvent.Leave))
    QApplication.processEvents()


def _files(tmp_path, count):
    paths = []
    for index in range(count):
        path = tmp_path / f"도구{index}.txt"
        path.write_text("synthetic", encoding="utf-8")
        paths.append(path)
    return paths


def _sidebar(qtbot):
    sidebar = ShortcutSidebarWidget()
    qtbot.addWidget(sidebar)
    sidebar.load_shortcuts()
    # 화면에 띄우지 않는다. 창이 실제 커서 밑에 뜨면 합성 Leave 뒤에 진짜 Enter가 들어와 결과가 커서 위치에 흔들린다.
    sidebar.setAttribute(Qt.WA_DontShowOnScreen, True)
    sidebar.show()
    qtbot.waitUntil(sidebar.isVisible)
    return sidebar


def _shown_ids(sidebar):
    return [slot.shortcut_id for slot in sidebar.slots if not slot.isHidden()]


def test_only_first_empty_slot_shows_as_add(qtbot, app_dir, tmp_path):
    first, second = _files(tmp_path, 2)
    db.update_shortcut(1, "도구", str(first))
    sidebar = _sidebar(qtbot)

    assert _shown_ids(sidebar) == [1, 2]
    add = sidebar.slots[1]
    assert add.btn.text() == "+" and add.name_label.text() == "추가"

    # 추가 칸에 등록하면 다음 빈 칸이 추가 칸이 된다(DB 6슬롯은 그대로).
    assert add._persist("둘", str(second))
    assert _shown_ids(sidebar) == [1, 2, 3]
    assert sidebar.slots[2].name_label.text() == "추가"

    # 앞 칸을 지우면 그 칸이 추가 칸이 되고 뒤의 빈 칸은 다시 숨는다.
    sidebar.slots[0]._on_delete()
    assert _shown_ids(sidebar) == [1, 2]
    assert sidebar.slots[0].name_label.text() == "추가"


def test_all_six_filled_shows_no_add_slot(qtbot, app_dir, tmp_path):
    for index, path in enumerate(_files(tmp_path, 6), 1):
        db.update_shortcut(index, f"도구{index}", str(path))
    sidebar = _sidebar(qtbot)
    assert _shown_ids(sidebar) == [1, 2, 3, 4, 5, 6]
    assert all(slot.btn.text() == "" for slot in sidebar.slots)


def test_shortcut_icon_is_smaller_and_delete_shows_on_hover(qtbot, app_dir, tmp_path):
    (path,) = _files(tmp_path, 1)
    db.update_shortcut(1, "도구", str(path))
    sidebar = _sidebar(qtbot)
    slot, add = sidebar.slots[0], sidebar.slots[1]

    assert slot.btn.size() == QSize(64, 64)
    assert slot.btn.iconSize() == QSize(32, 32)
    assert slot.delete_btn.isHidden()
    _hover(slot)
    assert not slot.delete_btn.isHidden()
    _hover(slot, inside=False)
    assert slot.delete_btn.isHidden()
    _hover(add)
    assert add.delete_btn.isHidden()  # 빈 칸에는 지울 것이 없다


def _main(qtbot, count=2):
    for index in range(count):
        db.add_schedule("2026-10-09", f"일정 {index}", "#4CC9F0")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    win._current_year, win._current_month = 2026, 10
    win._refresh_calendar()
    win._on_date_selected("2026-10-09")
    QApplication.processEvents()
    return win


def test_schedule_delete_button_only_on_hovered_or_current_row(qtbot, app_dir):
    win = _main(qtbot)
    rows = [win.schedule_list.itemWidget(win.schedule_list.item(i)) for i in range(2)]
    assert all(isinstance(row, ScheduleRow) for row in rows)
    assert all(row.delete_button.isHidden() for row in rows)
    width = rows[0].schedule_text_label.width()

    _hover(rows[0])
    assert not rows[0].delete_button.isHidden()
    assert rows[1].delete_button.isHidden()
    assert rows[0].schedule_text_label.width() == width  # 버튼 자리를 비워 둬 글자가 밀리지 않는다
    _hover(rows[0], inside=False)
    assert rows[0].delete_button.isHidden()

    # 키보드로 고른 줄도 삭제 버튼이 보인다.
    win.schedule_list.setCurrentRow(1)
    QApplication.processEvents()
    assert not rows[1].delete_button.isHidden()
    rows[1].delete_button.click()
    assert [s["content"] for s in db.get_schedules("2026-10-09")] == ["일정 0"]


def _drawn(label):
    image = label.grab().toImage()
    counts = Counter(image.pixelColor(x, y).name()
                     for y in range(image.height()) for x in range(image.width())
                     if image.pixelColor(x, y).lightness() < 200)
    return counts.most_common(1)[0][0]


def test_date_header_uses_gray_for_lunar_and_count(qtbot, app_dir):
    db.save_setting(db.SETTING_SHOW_LUNAR, "1")
    win = _main(qtbot, count=3)
    assert "음력" in win.lunar_info_label.text()
    assert "한글날" in win.holiday_info_label.text()
    assert _drawn(win.lunar_info_label) == "#757575"
    assert _drawn(win.count_label) == "#757575"
    assert _drawn(win.holiday_info_label) == "#d32f2f"  # 공휴일만 색으로 남긴다
