"""미니앱 주머니의 실제 입력·레이아웃·기존 데이터 보존 회귀."""
import os
import sqlite3
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel
from qfluentwidgets.common.font import fontFamilies, setFontFamilies
from shiboken6 import isValid

from app_fonts import apply_app_font
from app_paths import resource_root
import database as db
import security
import ui_main
import optional_mini_apps
from ui_main import MainCalendarWindow
from ui_mini_apps import MiniAppsButton, MiniAppsPocket, pocket_position


@pytest.fixture(autouse=True)
def isolated_ui(app_dir, qapp, monkeypatch):
    previous_font, previous_families = qapp.font(), fontFamilies()
    apply_app_font(db.DEFAULT_APP_FONT, qapp)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    db.save_setting(db.SETTING_SHOW_SIDEBAR, "1")
    monkeypatch.setattr(ui_main.InfoBar, "error", lambda **kw: None)
    # 기존 4개 앱의 주머니 계약을 검사한다. 선택형 앱은 test_optional_mini_apps.py가 맡는다.
    monkeypatch.setattr(optional_mini_apps, "OPTIONAL_MINI_APPS", ())
    yield
    qapp.setFont(previous_font)
    setFontFamilies(previous_families, save=False)


def window(qtbot, scale="compact"):
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    win.activateWindow()
    assert QTest.qWaitForWindowExposed(win)
    assert QTest.qWaitForWindowActive(win)
    return win


def open_pocket(qtbot, win):
    qtbot.mouseClick(win.sidebar.mini_apps_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: win._mini_apps_popup is not None and win._mini_apps_popup.isVisible())
    assert QTest.qWaitForWindowExposed(win._mini_apps_popup)
    assert QTest.qWaitForWindowActive(win._mini_apps_popup)
    return win._mini_apps_popup


def raw_snapshot():
    with db._connection() as conn:
        return tuple(conn.iterdump())


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_sidebar_pocket_geometry_and_render(qtbot, scale):
    win = window(qtbot, scale)
    sidebar = win.sidebar
    button = sidebar.mini_apps_button
    scroll = sidebar.shortcuts_scroll
    assert sidebar.width() == 80
    assert button.size() == QSize(64, 48)
    assert not button.icon().isNull()
    assert [slot.shortcut_id for slot in sidebar.slots] == list(range(1, 7))
    assert sidebar.slots[0].mapTo(sidebar, QPoint()).y() > button.geometry().bottom()
    assert all(slot.btn.size() == QSize(64, 64) for slot in sidebar.slots)
    assert scroll.horizontalScrollBar().maximum() == 0
    if scale == "compact":
        assert win.width() == 460
        assert scroll.verticalScrollBar().maximum() == 0
        for slot in sidebar.slots:
            rect = QRect(slot.mapTo(scroll.viewport(), QPoint()), slot.size())
            assert scroll.viewport().rect().contains(rect)
    popup = open_pocket(qtbot, win)
    assert popup.size() == QSize(300, 328)
    assert popup.card.size() == QSize(252, 280)
    assert popup.converter_card.size() == QSize(104, 100)
    assert popup.apps_grid.count() == 4
    assert len(popup.pending_cards) == 0
    assert popup.count_label.text() == "4개"
    assert popup.apps_scroll.horizontalScrollBar().maximum() == 0
    assert popup.apps_scroll.verticalScrollBar().maximum() == 0
    for index in range(4):
        card = popup.apps_grid.itemAtPosition(*divmod(index, 2)).widget()
        assert card.size() == QSize(104, 100)
        assert card.iconSize() == QSize(48, 48)
        assert popup.apps_scroll.viewport().rect().contains(QRect(card.mapTo(popup.apps_scroll.viewport(), QPoint()), card.size()))
    assert popup.screen().availableGeometry().contains(popup.geometry())
    assert popup.converter_card.isVisible()
    assert popup.converter_card.text() == "단위 환산기"
    assert popup.date_time_card.isVisible()
    assert popup.date_time_card.text() == "날짜·시간\n계산기"
    assert popup.apps_grid.itemAtPosition(0, 1).widget() is popup.date_time_card
    assert not popup.date_time_card.icon().isNull()
    assert popup.apps_grid.itemAtPosition(1, 0).widget() is popup.money_card
    assert popup.money_card.text() == "금액·숫자\n표기"
    assert popup.money_card.accessibleName() == "금액·숫자 표기 도우미 실행"
    assert not popup.money_card.icon().isNull()
    assert button.isChecked()
    appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if appdata:
        target = Path(appdata).parent
        # 앱 위젯 렌더만 합성하며 실사용 데스크톱은 캡처하지 않는다.
        bounds = win.geometry().united(popup.geometry())
        dpr = win.devicePixelRatioF()
        picture = QPixmap(round(bounds.width()*dpr), round(bounds.height()*dpr))
        picture.setDevicePixelRatio(dpr)
        picture.fill(QColor("#F4F5F7"))
        painter = QPainter(picture)
        painter.drawPixmap(win.pos()-bounds.topLeft(), win.grab())
        painter.drawPixmap(popup.pos()-bounds.topLeft(), popup.grab())
        painter.end()
        assert picture.save(str(target / f"mini-apps-{scale}.png"))
        assert popup.grab().save(str(target / f"mini-apps-pocket-{scale}.png"))
    win._close_mini_apps()


def test_svg_icons_replace_generated_png_and_shadow_is_unclipped(qtbot):
    assert not (resource_root() / "resources" / "images" / "mini_apps" / "unit_converter_tile.png").exists()
    assert not (resource_root() / "resources" / "icons" / "date_time.svg").exists()
    win = window(qtbot)
    popup = open_pocket(qtbot, win)
    assert not popup.converter_card.icon().isNull()
    tile = popup.converter_card.grab().toImage()
    teal = [tile.pixelColor(x, y) for x in range(tile.width()) for y in range(tile.height())]
    assert any(c.green() - c.red() > 60 and c.blue() - c.red() > 60 for c in teal)
    rendered = popup.grab().toImage()
    dpr = rendered.devicePixelRatio()
    card = popup.card.geometry()
    assert 0 < rendered.pixelColor(round((card.left()-3)*dpr), round(card.center().y()*dpr)).alpha() < 255
    for x, y in ((0, 0), (rendered.width()-1, 0), (0, rendered.height()-1),
                 (rendered.width()-1, rendered.height()-1)):
        assert rendered.pixelColor(x, y).alpha() == 0


def test_pocket_a_header_tiles_and_sidebar_button_style(qtbot):
    win = window(qtbot)
    button = win.sidebar.mini_apps_button
    assert isinstance(button, MiniAppsButton)
    assert button.size() == QSize(64, 48)
    style = button.styleSheet()
    assert "background:#FFFFFF" in style and "border:1px solid #D9E1EC" in style
    assert "QToolButton:checked{background:#EAF2FE;border-color:#8DB4F0;color:#1D4ED8;}" in style
    popup = open_pocket(qtbot, win)
    header = popup.findChild(QLabel, "miniAppsTitle").parentWidget()
    assert header.height() == 48
    assert "background:transparent" in header.styleSheet()
    assert popup.findChild(QLabel, "miniAppsTitle").text() == "미니앱"
    assert "border:0" in popup.close_button.styleSheet()
    assert "border:1px solid #D9E1EC;border-radius:16px" in popup.card.styleSheet()
    for card in (popup.converter_card, popup.date_time_card, popup.money_card, popup.document_card, *popup.pending_cards):
        assert card.sizeHint().height() <= 100, card.text()
        assert "background:transparent;border:2px solid transparent" in card.styleSheet()
    assert all(not card.icon().isNull() for card in popup.pending_cards)


def test_upcoming_tiles_do_not_launch_or_receive_keyboard_focus(qtbot):
    win = window(qtbot)
    popup = open_pocket(qtbot, win)
    clicked = []
    for card in popup.pending_cards:
        card.clicked.connect(lambda: clicked.append(True))
        assert card.text() == "준비 중"
        assert card.accessibleName() == "곧 출시 예정"
        assert not card.isEnabled()
        assert card.focusPolicy() == Qt.NoFocus
        qtbot.mouseClick(card, Qt.LeftButton)
        card.click()
        assert popup.isVisible()
    popup.close_button.setFocus()
    visited = []
    for _ in range(12):
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
        focused = QApplication.focusWidget()
        assert focused not in popup.pending_cards
        visited.append(focused)
    assert popup.converter_card in visited
    assert popup.date_time_card in visited
    assert popup.money_card in visited
    assert popup.close_button in visited
    assert not clicked
    assert win._unit_converter is None
    assert win._date_time_calculator is None
    assert win._money_notation is None


def test_short_screen_scroll_keeps_button_and_sixth_shortcut_accessible(qtbot, tmp_path):
    # 빈 칸은 하나만 보이므로(디자인 점검 10번) 여섯 칸을 모두 채워 여섯 번째 칸까지 확인한다.
    for slot_id in range(1, 7):
        target = tmp_path / f"tool{slot_id}.txt"
        target.write_text("synthetic", encoding="utf-8")
        db.update_shortcut(slot_id, f"도구{slot_id}", str(target))
    win = window(qtbot)
    win.resize(win.width(), 500)
    qtbot.wait(20)
    sidebar = win.sidebar
    scroll = sidebar.shortcuts_scroll
    position = sidebar.mini_apps_button.pos()
    assert scroll.verticalScrollBar().maximum() > 0
    scroll.ensureWidgetVisible(sidebar.slots[-1])
    qtbot.wait(20)
    last = sidebar.slots[-1]
    rect = QRect(last.mapTo(scroll.viewport(), QPoint()), last.size())
    assert scroll.viewport().rect().contains(rect)
    assert scroll.horizontalScrollBar().maximum() == 0
    assert sidebar.mini_apps_button.pos() == position


@pytest.mark.parametrize("dismiss", ["button", "escape", "close", "shadow", "outside", "outside_window"])
def test_dismissal_keeps_button_and_popup_lifetime_in_sync(qtbot, dismiss):
    win = window(qtbot)
    popup = open_pocket(qtbot, win)
    if dismiss == "button":
        qtbot.mouseClick(win.sidebar.mini_apps_button, Qt.LeftButton)
    elif dismiss == "escape":
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Escape)
    elif dismiss == "close":
        qtbot.mouseClick(popup.close_button, Qt.LeftButton)
    elif dismiss == "shadow":
        qtbot.mouseClick(popup, Qt.LeftButton, pos=QPoint(10, popup.height()//2))
    else:
        # Qt.Popup 바깥 클릭. 원래 버튼에 재전달되어 다시 열리지 않아야 한다.
        point = win.sidebar.mini_apps_button.mapToGlobal(QPoint(20, 20))
        target = popup.windowHandle() if dismiss == "outside_window" else popup
        QTest.mouseClick(target, Qt.LeftButton, pos=popup.mapFromGlobal(point))
    qtbot.waitUntil(lambda: win._mini_apps_popup is None)
    qtbot.waitUntil(lambda: not isValid(popup))
    assert not win.sidebar.mini_apps_button.isChecked()
    assert not win.findChildren(MiniAppsPocket)


def test_keyboard_open_close_and_restore_draft_focus(qtbot):
    win = window(qtbot)
    button = win.sidebar.mini_apps_button
    win.schedule_input.setText("📌 미등록 일정 초안")
    win.schedule_input.setFocus()
    qtbot.waitUntil(win.schedule_input.hasFocus)
    popup = open_pocket(qtbot, win)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Escape)
    qtbot.waitUntil(win.schedule_input.hasFocus)
    assert win.schedule_input.text() == "📌 미등록 일정 초안"
    # 실제 Tab 포커스 순회로 미니앱 버튼에 진입한 뒤 키 입력한다.
    for _ in range(50):
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
        if QApplication.focusWidget() is button:
            break
    assert QApplication.focusWidget() is button
    for key in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
        qtbot.keyClick(QApplication.focusWidget(), key)
        qtbot.waitUntil(lambda: win._mini_apps_popup is not None)
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Escape)
        qtbot.waitUntil(button.hasFocus)


def test_repeated_pocket_use_preserves_database_salt_and_all_shortcuts(qtbot, tmp_path):
    for i in range(1, 7):
        path = tmp_path / f"sample-{i}.txt"
        path.write_text("합성 파일", encoding="utf-8")
        db.update_shortcut(i, f"업무 {i}", str(path))
    db.add_schedule("2026-09-20", "⭐ 기존 일정", "#FFD166")
    note = db.create_sticky_note()
    db.update_sticky_note(note, content="<p>기존 메모</p>")
    win = window(qtbot)
    # 기동 시 예약된 스티키 크기 스냅 저장을 마친 뒤 미니앱의 무변경을 비교한다.
    qtbot.waitUntil(lambda: all(not w._resize_timer.isActive() for w in win._sticky_windows.values()))
    original = raw_snapshot()
    salt = security.SALT_FILE.read_bytes()
    shortcuts = db.get_shortcuts()
    exported = db.export_all_data()
    for _ in range(8):
        popup = open_pocket(qtbot, win)
        qtbot.mouseClick(popup.close_button, Qt.LeftButton)
        qtbot.waitUntil(lambda: not isValid(popup))
    assert raw_snapshot() == original
    assert db.export_all_data() == exported
    assert security.SALT_FILE.read_bytes() == salt
    assert db.get_shortcuts() == shortcuts
    assert [(s.shortcut_id, s.name, s.path) for s in win.sidebar.slots] == [
        (s["id"], s["name"], s["path"]) for s in shortcuts]


@pytest.mark.parametrize("action", ["lock", "tray", "sidebar", "scale", "screen", "reset", "hide", "quit"])
def test_lifecycle_closes_pocket_and_cancels_pending_focus(qtbot, action):
    win = window(qtbot)
    popup = open_pocket(qtbot, win)
    actions = {
        "lock": win._lock, "tray": win._minimize_to_tray,
        "sidebar": lambda: (db.save_setting(db.SETTING_SHOW_SIDEBAR, "0"), win._apply_sidebar_visibility()),
        "scale": lambda: (db.save_setting(db.SETTING_CALENDAR_SCALE, "large"), win._apply_calendar_scale()),
        "screen": win._on_screen_changed, "reset": win._discard_data_widgets,
        "hide": win.hide, "quit": win.prepare_for_quit,
    }
    actions[action]()
    assert win._mini_apps_popup is None
    assert not win._mini_apps_focus_timer.isActive()
    qtbot.waitUntil(lambda: not isValid(popup))
    if action in ("lock", "tray", "sidebar", "hide"):
        win.sidebar.mini_apps_button.click()
        assert win._mini_apps_popup is None
        assert not win.sidebar.mini_apps_button.isChecked()
    if action == "lock":
        win._unlock()
        popup = open_pocket(qtbot, win)
        popup.dismiss()  # 지연된 포커스 복원 전에 잠금이 다시 발생한다.
        win._lock()
        qtbot.wait(10)
        assert not win._mini_apps_focus_timer.isActive()
        assert win._mini_apps_previous_focus is None


def test_failed_inline_save_blocks_pocket_then_retry_preserves_content(qtbot, monkeypatch):
    db.add_schedule("2026-09-20", "기존 일정", "#FFD166")
    win = window(qtbot)
    win._on_date_selected("2026-09-20")
    win._on_edit_schedule(win.schedule_list.item(0))
    editor = win._schedule_editor
    editor.edit.setText("⭐ 수정 중인 일정")
    qtbot.waitUntil(editor.edit.hasFocus)
    update = db.update_schedule
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic failure")
    monkeypatch.setattr(db, "update_schedule", fail)
    qtbot.mouseClick(win.sidebar.mini_apps_button, Qt.LeftButton)
    assert win._mini_apps_popup is None
    assert not win.sidebar.mini_apps_button.isChecked()
    assert editor.edit.text() == "⭐ 수정 중인 일정"
    assert db.get_schedules("2026-09-20")[0]["content"] == "기존 일정"
    monkeypatch.setattr(db, "update_schedule", update)
    popup = open_pocket(qtbot, win)
    assert db.get_schedules("2026-09-20")[0]["content"] == "⭐ 수정 중인 일정"
    popup.dismiss()
    qtbot.waitUntil(win.sidebar.mini_apps_button.hasFocus)


@pytest.mark.parametrize("shadow_margin", [0, 24])
@pytest.mark.parametrize("anchor", [QRect(-1900, 40, 64, 48), QRect(-70, 900, 64, 48), QRect(-180, 0, 64, 48)])
def test_position_on_negative_coordinate_monitor(anchor, shadow_margin):
    available = QRect(-1920, 0, 1920, 1040)
    size = QSize(300, 328)
    position = pocket_position(anchor, size, available, shadow_margin=shadow_margin)
    assert available.contains(QRect(position, size))
    gap = 12 if shadow_margin else 8
    if anchor.right()+1+gap-shadow_margin+size.width() <= available.right()+1:
        assert position.x()+shadow_margin == anchor.right()+1+gap
    else:
        assert position.x()+size.width()-shadow_margin == anchor.left()-gap


def test_more_developer_apps_use_two_columns_and_scroll_without_resizing(qtbot):
    win = window(qtbot)
    popup = open_pocket(qtbot, win)
    clicked = []
    cards = [popup.converter_card, popup.date_time_card, popup.money_card, popup.document_card]
    for index in range(1, 7):
        cards.append(popup.add_app(f"합성 앱 {index}", "apps", "격자 확인용",
                                  lambda checked=False, i=index: clicked.append(i)))
    QApplication.processEvents()
    assert popup.size() == QSize(300, 328)
    assert not popup.pending_cards
    assert popup.apps_grid.count() == len(cards)
    for index, card in enumerate(cards):
        assert card.size() == QSize(104, 100)
        assert popup.apps_grid.getItemPosition(index)[:2] == divmod(index, 2)
    assert cards[0].geometry().right() < cards[1].geometry().left()
    assert popup.apps_scroll.horizontalScrollBar().maximum() == 0
    qtbot.waitUntil(lambda: popup.apps_scroll.verticalScrollBar().maximum() > 0)
    popup.apps_scroll.ensureWidgetVisible(cards[-1])
    cards[-1].setFocus()
    qtbot.waitUntil(cards[-1].hasFocus)
    rect = QRect(cards[-1].mapTo(popup.apps_scroll.viewport(), QPoint()), cards[-1].size())
    assert popup.apps_scroll.viewport().rect().contains(rect)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    assert clicked == [6]
    assert popup.isVisible()
    assert popup.count_label.text() == f"{len(cards)}개"


def test_tile_icons_and_first_name_line_share_the_same_top(qtbot):
    """디자인 점검 19번: 이름이 한 줄(단위 환산기)이든 두 줄이든 아이콘 위치가 같다."""
    from ui_mini_apps import MiniAppTile
    win = window(qtbot)
    popup = open_pocket(qtbot, win)
    tiles = [tile for tile in popup.findChildren(MiniAppTile) if tile.isEnabled() and tile.isVisible()]
    one_line = next(tile for tile in tiles if "\n" not in tile.text())
    two_line = next(tile for tile in tiles if "\n" in tile.text())
    image = popup.grab().toImage()
    ratio = image.devicePixelRatio()

    def first_text_row(tile):
        """아이콘(48px) 아래에서 처음 나오는 진한 글자 줄의 y."""
        origin = tile.mapTo(popup, QPoint(0, 0))
        start = tile.ICON_TOP + tile.iconSize().height() + 4  # 배율에서 아이콘 맨 아랫줄을 글자로 세지 않는다
        for y in range(start, tile.height() - 2):
            for x in range(6, tile.width() - 6):
                color = image.pixelColor(int((origin.x() + x) * ratio), int((origin.y() + y) * ratio))
                if color.lightness() < 140:
                    return y
        return None

    assert first_text_row(one_line) is not None
    # 한 줄 이름이 두 줄 칸 가운데로 내려가지 않고 첫 줄 높이가 같다.
    assert abs(first_text_row(one_line) - first_text_row(two_line)) <= 1
