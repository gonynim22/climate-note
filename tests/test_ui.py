# tests/test_ui.py - UI component logic & bindings tests

import pytest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call
from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QWidget

import database as db
import ui_main
from app_info import APP_RELEASE_DATE, APP_VERSION, app_credit_text, app_exe_name
from app_fonts import (
    APP_FONT_OPTIONS,
    available_system_fonts,
    resolve_app_font_family,
    system_font_family_from_key,
    system_font_key,
)
from fluent_icons import fluent_icon, fluent_icon_path
from ui_dday import DDayCreateDialog
from ui_main import (
    MainCalendarWindow,
    ShortcutSlot,
    ShortcutSidebarWidget,
    _calendar_corner_coordinates,
    _compute_arrange_layout,
    _right_aligned_grid_x,
    _snap_not_past_right,
)
from ui_search import SearchWindow
from ui_settings import (
    HEADER_BG, HEADER_BORDER, ScheduleColorPicker, SettingsWindow,
)
from ui_update import (
    UPDATE_GUIDE_HIGHLIGHT,
    UPDATE_GUIDE_URL,
    update_guide_dialog_size,
    update_guide_html,
    update_guide_text,
)

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

def test_popup_menus_use_opaque_roundmenu(qtbot, app_dir, qapp):
    """'...'/'+' 메뉴는 불투명 RoundMenu여야 한다.

    plain QMenu + QSS border-radius 는 라이브 Windows에서 배경이 투명해져
    '배경이 안 보이는 라운드'가 된다. 그림자·불투명 배경이 내장된 qfluentwidgets
    RoundMenu로 대체하고, 전체 투명도 설정과 무관하게 메뉴 투명도는 1.0으로 둔다.
    """
    from qfluentwidgets import RoundMenu

    win = MainCalendarWindow()
    qtbot.addWidget(win)

    for builder in (win._build_more_menu, win._build_add_menu):
        menu = builder()
        qtbot.addWidget(menu)
        assert isinstance(menu, RoundMenu)
        assert menu.windowOpacity() == 1.0
        menu_qss = menu.view.styleSheet()
        assert "MenuActionListWidget::item:hover" in menu_qss
        assert "background-color: #01295F" in menu_qss
        assert "color: #FFFFFF" in menu_qss
        # 액션이 실제로 채워졌는지 (separator 제외 1개 이상)
        real_actions = [a for a in menu.menuActions() if not a.isSeparator()]
        assert len(real_actions) >= 1


def test_search_window_table_headers(qtbot, app_dir, qapp):
    """검색 위젯이 테이블 포맷이고, 올바른 헤더 라벨을 지니는지 검증"""
    win = SearchWindow()
    qtbot.addWidget(win)

    table = win.result_table
    assert table.columnCount() == 3
    headers = [table.horizontalHeaderItem(i).text() for i in range(3)]
    assert headers == ["날짜", "구분", "내용"]

def test_search_window_table_populates_colors(qtbot, app_dir, qapp):
    """검색 결과가 올바르게 테이블행으로 입력되며 일정 색상 배지가 적용되는지 검증"""
    db.add_schedule("2026-05-05", "빨간일정", "#FF6B6B")
    db.save_memo("2026-05-05", "일반메모")
    
    win = SearchWindow()
    qtbot.addWidget(win)
    
    win.search_input.setText("일") # 검색어
    win._on_search()

    table = win.result_table
    assert table.rowCount() == 2
    
    badges = {}
    for i in range(table.rowCount()):
        badges[table.item(i, 2).text()] = table.item(i, 1)

    schedule_badge = badges["빨간일정"]
    assert schedule_badge.text() == "■"
    assert schedule_badge.foreground().color() == QColor(
        db.schedule_display_color("#FF6B6B")
    )
    assert badges["일반메모"].text() == "📝"

def test_settings_monitor_combo(qtbot, app_dir, qapp):
    """앱 환경설정에서 데스크탑 타겟 모니터 콤보박스가 올바른 목록을 그리는지 검증"""
    win = SettingsWindow()
    qtbot.addWidget(win)
    
    # 모니터 콤보박스 아이템들이 제대로 삽입되었는지
    assert win.monitor_combo.count() >= 1
    # 0번째 item의 userData가 "0"인지
    assert win.monitor_combo.itemData(0) == "0"


def test_settings_monitor_change_persists_and_calls_position_callback(qtbot, app_dir, qapp, monkeypatch):
    """모니터 선택 변경은 대상 모니터 설정 저장과 즉시 위치 재적용을 함께 수행한다."""
    class FakeScreen:
        def __init__(self, rect):
            self._rect = rect

        def geometry(self):
            return self._rect

        def availableGeometry(self):
            return self._rect

        def name(self):
            return str(self._rect.x())

    class FakeApplication:
        @staticmethod
        def screens():
            return [
                FakeScreen(QRect(0, 0, 1920, 1080)),
                FakeScreen(QRect(-1920, 0, 1920, 1080)),
            ]

    called = []
    monkeypatch.setattr("ui_settings.QApplication", FakeApplication)
    win = SettingsWindow(on_position_changed=lambda: called.append(True))
    qtbot.addWidget(win)

    assert win.monitor_combo.count() == 2
    win.monitor_combo.setCurrentIndex(1)

    assert db.get_setting(db.SETTING_TARGET_SCREEN) == "1"
    assert called == [True]


def test_settings_has_five_section_headers(qtbot, app_dir, qapp):
    from qfluentwidgets import StrongBodyLabel

    win = SettingsWindow()
    qtbot.addWidget(win)
    texts = [label.text() for label in win.findChildren(StrongBodyLabel)]
    for section in ["화면 표시", "위젯·도구", "데이터", "보안", "시스템"]:
        assert section in texts


def test_settings_preserves_all_existing_controls(qtbot, app_dir, qapp):
    win = SettingsWindow()
    qtbot.addWidget(win)
    for attr in [
        "startup_switch", "privacy_switch", "pin_container", "privacy_pin_edit",
        "open_data_folder_btn", "font_combo", "export_pin", "import_pin",
        "monitor_combo", "law_search_switch", "sidebar_switch", "lunar_switch",
        "schedule_color_picker", "factory_reset_btn", "quit_app_btn",
    ]:
        assert hasattr(win, attr), f"missing control: {attr}"
    assert win.factory_reset_btn.objectName() == "factoryResetButton"
    assert win.quit_app_btn.objectName() == "quitAppButton"
    assert len(win._position_btns) == 4


def test_settings_opacity_slider_persists_and_calls_callback(qtbot, app_dir, qapp):
    received = []
    win = SettingsWindow(on_opacity_changed=lambda: received.append(True))
    qtbot.addWidget(win)
    assert win.opacity_slider.minimum() == 30
    assert win.opacity_slider.maximum() == 100
    win.opacity_slider.setValue(70)
    assert db.get_setting(db.SETTING_APP_OPACITY) == "70"
    assert received == [True]
    assert win.opacity_value_label.text() == "70%"


def test_settings_scale_picker_persists_and_calls_callback(qtbot, app_dir, qapp):
    received = []
    win = SettingsWindow(on_scale_changed=lambda: received.append(True))
    qtbot.addWidget(win)
    assert win.scale_picker.current_scale() in ("compact", "medium", "large")
    win.scale_picker.select("medium")
    assert db.get_setting(db.SETTING_CALENDAR_SCALE) == "medium"
    assert received == [True]


def test_schedule_color_picker_has_three_swatches_and_ten_choices(qtbot, qapp):
    picker = ScheduleColorPicker(db.DEFAULT_SCHEDULE_PALETTE)
    qtbot.addWidget(picker)

    assert picker.colors() == db.DEFAULT_SCHEDULE_PALETTE
    assert len(picker._buttons) == 3
    assert len(db.SCHEDULE_COLOR_OPTIONS) == 10
    assert all(button.width() == 24 for button in picker._buttons)


def test_schedule_color_swatch_keeps_menu_alive_until_closed(
        qtbot, qapp, monkeypatch):
    import ui_settings

    opened = []
    deleted = []
    monkeypatch.setattr(
        ui_settings.RoundMenu,
        "exec",
        lambda menu, _position: opened.append(menu),
    )
    monkeypatch.setattr(
        ui_settings.RoundMenu,
        "deleteLater",
        lambda menu: deleted.append(menu),
    )
    picker = ScheduleColorPicker(db.DEFAULT_SCHEDULE_PALETTE)
    qtbot.addWidget(picker)

    qtbot.mouseClick(picker._buttons[0], Qt.LeftButton)

    assert len(opened) == 1
    assert deleted == []
    opened[0].closedSignal.emit()
    assert deleted == opened


def test_schedule_color_picker_rejects_duplicate_slot_color(qtbot, qapp):
    picker = ScheduleColorPicker(db.DEFAULT_SCHEDULE_PALETTE)
    qtbot.addWidget(picker)
    received = []
    picker.colorsChanged.connect(lambda colors: received.append(colors))

    assert picker.select_color(0, db.DEFAULT_SCHEDULE_PALETTE[1]) is False
    assert picker.colors() == db.DEFAULT_SCHEDULE_PALETTE
    assert received == []


def test_settings_schedule_colors_persist_and_call_callback(
        qtbot, app_dir, qapp):
    received = []
    win = SettingsWindow(
        on_schedule_colors_changed=lambda: received.append(True)
    )
    qtbot.addWidget(win)

    assert win.schedule_color_picker.select_color(0, "#FF9F68") is True
    assert db.get_schedule_palette() == ("#FF9F68", "#4CC9F0", "#FF6B6B")
    assert received == [True]


def test_settings_schedule_color_save_failure_restores_previous_swatches(
        qtbot, app_dir, qapp, monkeypatch):
    received = []
    win = SettingsWindow(
        on_schedule_colors_changed=lambda: received.append(True)
    )
    qtbot.addWidget(win)
    original = win.schedule_color_picker.colors()

    def _fail_save(_colors):
        raise ValueError("simulated palette write failure")

    monkeypatch.setattr(db, "save_schedule_palette", _fail_save)

    assert win.schedule_color_picker.select_color(0, "#FF9F68") is True
    assert win.schedule_color_picker.colors() == original
    assert received == []


def test_settings_import_resyncs_schedule_palette_picker(
        qtbot, app_dir, qapp, monkeypatch):
    """가져온 팔레트를 열린 설정창에도 반영해 다음 변경의 슬롯 덮어쓰기를 막는다."""
    import ui_settings

    win = SettingsWindow()
    qtbot.addWidget(win)
    imported = ("#FF9F68", "#80CFA9", "#B197FC")
    db.save_schedule_palette(imported)
    backup = db.export_all_data().encode("utf-8")
    db.save_schedule_palette(db.DEFAULT_SCHEDULE_PALETTE)

    backup_path = app_dir / "palette-backup.enc"
    backup_path.write_bytes(b"encrypted-placeholder")
    win.import_pin.setText("0000")
    monkeypatch.setattr(win, "_validate_pin", lambda _pin: True)
    monkeypatch.setattr(
        ui_settings.QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(backup_path), "암호화 파일 (*.enc)"),
    )
    monkeypatch.setattr(
        ui_settings,
        "decrypt_with_pin",
        lambda _data, _pin: backup,
    )
    operations = []
    original_import = db.import_all_data
    monkeypatch.setattr(
        db,
        "backup_before_operation",
        lambda operation: operations.append(f"backup:{operation}") or True,
    )

    def _tracked_import(payload):
        operations.append("import")
        original_import(payload)

    monkeypatch.setattr(db, "import_all_data", _tracked_import)

    win._on_import()

    assert operations[:2] == ["backup:import", "import"]
    assert win.schedule_color_picker.colors() == imported
    assert win._saved_schedule_colors == imported
    assert win.schedule_color_picker.select_color(0, "#F28BB5") is True
    assert db.get_schedule_palette() == (
        "#F28BB5",
        imported[1],
        imported[2],
    )


def test_atomic_export_write_preserves_existing_file_on_replace_failure(
        tmp_path, monkeypatch):
    import ui_settings

    target = tmp_path / "existing.enc"
    with open(target, "wb") as export_file:
        export_file.write(b"known-good-backup")

    def _fail_replace(_source, _target):
        raise OSError("injected replace failure")

    monkeypatch.setattr(ui_settings.os, "replace", _fail_replace)

    with pytest.raises(OSError, match="injected"):
        ui_settings._atomic_write_bytes(target, b"new-backup")

    with open(target, "rb") as export_file:
        assert export_file.read() == b"known-good-backup"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_settings_import_handles_database_error(
        qtbot, app_dir, qapp, monkeypatch):
    """구조는 해독됐지만 DB 쓰기가 실패해도 설정창 밖으로 예외를 내보내지 않는다."""
    import sqlite3
    import ui_settings

    win = SettingsWindow()
    qtbot.addWidget(win)
    backup_path = app_dir / "invalid-structure.enc"
    with open(backup_path, "wb") as backup_file:
        backup_file.write(b"encrypted-placeholder")
    win.import_pin.setText("0000")
    monkeypatch.setattr(win, "_validate_pin", lambda _pin: True)
    monkeypatch.setattr(
        ui_settings.QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(backup_path), "암호화 파일 (*.enc)"),
    )
    monkeypatch.setattr(
        ui_settings,
        "decrypt_with_pin",
        lambda _data, _pin: b"{}",
    )

    def _raise_import_error(_payload):
        raise sqlite3.DatabaseError("injected import failure")

    monkeypatch.setattr(db, "import_all_data", _raise_import_error)
    error = MagicMock()
    monkeypatch.setattr(ui_settings.InfoBar, "error", error)

    win._on_import()

    assert error.call_count == 1
    assert error.call_args.kwargs["title"] == "가져오기 실패"


def test_main_import_complete_reapplies_live_settings(
        qtbot, app_dir, qapp, monkeypatch):
    """가져온 설정과 바로가기가 재시작 없이 열린 메인 UI에 반영된다."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)

    db.save_setting(db.SETTING_SHOW_LUNAR, "1")
    db.save_setting(db.SETTING_SHOW_LAW_SEARCH, "0")
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    win._show_lunar = False

    scale = MagicMock()
    opacity = MagicMock()
    set_enabled = MagicMock()
    law_visible = MagicMock()
    shortcuts = MagicMock()
    monkeypatch.setattr(win, "_apply_calendar_scale", scale)
    monkeypatch.setattr(win, "_apply_app_opacity", opacity)
    monkeypatch.setattr(win._show_desktop_keeper, "set_enabled", set_enabled)
    monkeypatch.setattr(win.law_search_container, "setVisible", law_visible)
    monkeypatch.setattr(win.sidebar, "load_shortcuts", shortcuts)
    monkeypatch.setattr(win, "_update_schedule_color_btn", MagicMock())
    monkeypatch.setattr(win, "_load_schedules", MagicMock())
    monkeypatch.setattr(win, "_load_open_sticky_notes", MagicMock())
    monkeypatch.setattr(win, "_load_open_dday_widgets", MagicMock())
    monkeypatch.setattr(win, "_load_open_focus_widgets", MagicMock())

    win._on_import_complete()

    assert win._show_lunar is True
    scale.assert_called_once_with()
    opacity.assert_called_once_with()
    set_enabled.assert_called_once_with(False)
    law_visible.assert_called_once_with(False)
    shortcuts.assert_called_once_with()


def test_settings_schedule_color_row_stays_within_fixed_height(
        qtbot, app_dir, qapp):
    win = SettingsWindow()
    qtbot.addWidget(win)
    win.show()
    qapp.processEvents()

    assert win.size().width() == 800
    assert win.size().height() == 560
    assert win.layout().minimumSize().height() <= 560


def test_settings_has_no_scroll_area(qtbot, app_dir, qapp):
    from qfluentwidgets import ScrollArea

    win = SettingsWindow()
    qtbot.addWidget(win)
    assert win.findChildren(ScrollArea) == []


def test_calendar_position_allows_negative_monitor_coordinates():
    """주 모니터 왼쪽/위쪽에 배치된 모니터의 음수 좌표를 0으로 밀어내지 않는다."""
    class FakeScreen:
        def __init__(self, rect):
            self._rect = rect

        def availableGeometry(self):
            return self._rect

        def physicalDotsPerInch(self):
            return 96

    left_screen = FakeScreen(QRect(-1920, 0, 1920, 1080))
    x, y = _calendar_corner_coordinates(left_screen, 380, 660, "bottom-right")

    assert x < 0
    assert left_screen.availableGeometry().left() <= x <= left_screen.availableGeometry().right() - 380 + 1
    assert left_screen.availableGeometry().top() <= y <= left_screen.availableGeometry().bottom() - 660 + 1

    top_screen = FakeScreen(QRect(0, -1080, 1920, 1080))
    x, y = _calendar_corner_coordinates(top_screen, 380, 660, "top-right")

    assert y < 0
    assert top_screen.availableGeometry().left() <= x <= top_screen.availableGeometry().right() - 380 + 1
    assert top_screen.availableGeometry().top() <= y <= top_screen.availableGeometry().bottom() - 660 + 1


def test_right_arrange_snap_does_not_reduce_calendar_margin():
    """오른쪽 자동정렬은 스냅 반올림으로 캘린더의 우측 여백을 줄이지 않는다."""
    snap = 17
    calendar_right = 1906
    widget_width = 241

    start_x = _snap_not_past_right(calendar_right, snap)
    target_x = _right_aligned_grid_x(start_x, widget_width, snap)

    assert start_x <= calendar_right
    assert target_x % snap == 0
    assert target_x + widget_width <= start_x


def test_right_arrange_snap_preserves_negative_monitor_margin():
    """음수 좌표 모니터에서도 오른쪽 기준선 밖으로 위젯을 밀지 않는다."""
    snap = 19
    calendar_right = -20
    widget_width = 241

    start_x = _snap_not_past_right(calendar_right, snap)
    target_x = _right_aligned_grid_x(start_x, widget_width, snap)

    assert start_x <= calendar_right
    assert target_x + widget_width <= start_x


@pytest.mark.parametrize("value,expected", [
    ("100", 1.0), ("30", 0.30), ("55", 0.55),
    ("0", 0.30), ("200", 1.0), ("abc", 1.0), ("", 1.0), ("  70 ", 0.70),
])
def test_opacity_factor_clamps_and_parses(value, expected):
    assert ui_main._opacity_factor(value) == pytest.approx(expected)


def test_apply_app_opacity_broadcasts_to_all_registries(monkeypatch):
    monkeypatch.setattr(ui_main.db, "get_setting", lambda *args, **kwargs: "75")
    sticky = {1: MagicMock(), 2: MagicMock()}
    dday = {1: MagicMock()}
    focus = {1: MagicMock()}
    fake = SimpleNamespace(
        _sticky_windows=sticky,
        _dday_windows=dday,
        _focus_windows=focus,
        setWindowOpacity=MagicMock(),
    )
    fake._get_app_opacity = ui_main.MainCalendarWindow._get_app_opacity.__get__(fake)
    ui_main.MainCalendarWindow._apply_app_opacity(fake)
    fake.setWindowOpacity.assert_called_once_with(0.75)
    for registry in (sticky, dday, focus):
        for window in registry.values():
            window.setWindowOpacity.assert_called_once_with(0.75)


def test_main_window_position_to_corner_uses_negative_target_screen(qtbot, app_dir, qapp, monkeypatch):
    """캘린더 위치 적용은 선택 모니터가 음수 좌표여도 해당 모니터 안으로 이동한다."""
    class FakeScreen:
        def __init__(self, rect):
            self._rect = rect

        def availableGeometry(self):
            return self._rect

        def physicalDotsPerInch(self):
            return 96

    win = MainCalendarWindow()
    qtbot.addWidget(win)
    target_screen = FakeScreen(QRect(-1920, 0, 1920, 1080))
    monkeypatch.setattr(win, "_get_target_screen", lambda: target_screen)
    db.save_setting(db.SETTING_CALENDAR_POSITION, "top-left")

    win._position_to_corner()

    assert win.x() < 0
    assert target_screen.availableGeometry().contains(win.pos())


def test_settings_font_combo_replaces_maintenance(qtbot, app_dir, qapp):
    """유지보수 카드 대신 앱 글꼴 콤보박스가 제공되는지 검증."""
    win = SettingsWindow()
    qtbot.addWidget(win)

    assert hasattr(win, "font_combo")
    assert win.font_combo.count() > len(APP_FONT_OPTIONS)
    assert win.font_combo.itemData(0) == db.DEFAULT_APP_FONT
    assert win.font_combo.itemText(0) == "맑은 고딕"
    assert win.font_combo.itemText(len(APP_FONT_OPTIONS)) == "────────"
    assert resolve_app_font_family(db.DEFAULT_APP_FONT) == db.DEFAULT_APP_FONT


def test_settings_simplified_card_text_and_data_folder_button(qtbot, app_dir, qapp):
    """설정 카드 설명 문구를 줄이고 저장 경로는 폴더 버튼만 제공한다."""
    win = SettingsWindow()
    qtbot.addWidget(win)

    label_texts = [label.text() for label in win.findChildren(QLabel)]
    assert app_credit_text() in label_texts
    assert app_exe_name() == f"기후노트_{APP_VERSION}.exe"
    assert "시스템 시작 시 자동 실행" not in label_texts
    assert "PC Resume 시 PIN 입력" not in label_texts
    assert "체크박스 아이콘은 고정" not in label_texts
    assert "메인 창과 모든 위젯에 즉시 적용됩니다. (재시작 불필요)" not in label_texts
    assert "달력을 기본/중간/크게로 전환합니다. (재시작 불필요)" not in label_texts
    assert "대상 모니터와 고정할 화면 모서리를 선택합니다." not in label_texts
    assert "변경 시 앱 재시작 필요" not in label_texts
    assert not hasattr(win, "path_label")
    assert hasattr(win, "open_data_folder_btn")
    assert win.open_data_folder_btn.toolTip() == "저장 폴더 열기"


def test_settings_credit_uses_v39a_metadata(qtbot, app_dir, qapp):
    """v3.9a의 설정 하단 문구는 단일 앱 메타데이터를 따른다."""
    win = SettingsWindow()
    qtbot.addWidget(win)

    assert APP_VERSION == "v3.9a"
    assert win.author_label.text().startswith(f"v3.9a  ·  {APP_RELEASE_DATE}")


def test_update_guide_text_uses_current_version():
    text = update_guide_text()
    html = update_guide_html()

    assert UPDATE_GUIDE_HIGHLIGHT in text
    assert UPDATE_GUIDE_HIGHLIGHT in html
    assert 'bgcolor="#F7F6F3"' in html
    assert "기후노트" in text
    assert "기존 파일을 지우고, 새로 받은 파일을 실행합니다." in text
    assert "기존 파일을 지우고, 새로 받은 파일을 실행합니다." in html
    assert f"현재 앱 버전: {APP_VERSION}" in text
    assert f"현재 앱 버전: <b>{APP_VERSION}</b>" in html
    assert UPDATE_GUIDE_URL == "https://www.onnara.go.kr/kndg/home/kngList"


def test_update_guide_dialog_size_fits_calendar_width(qtbot, qapp):
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(380, 660)

    width, height = update_guide_dialog_size(parent)

    assert width <= parent.width()
    assert width == 340
    assert height == 360


def test_settings_update_guide_card_removed(qtbot, app_dir, qapp):
    win = SettingsWindow()
    qtbot.addWidget(win)

    label_texts = [label.text() for label in win.findChildren(QLabel)]

    assert not hasattr(win, "update_guide_btn")
    assert "업데이트 방법" not in label_texts


def test_main_window_more_menu_contains_secondary_actions(qtbot, app_dir, qapp, monkeypatch):
    calls = []
    monkeypatch.setattr("ui_main.show_update_guide", lambda parent=None: calls.append(parent))

    win = MainCalendarWindow()
    qtbot.addWidget(win)

    assert not hasattr(win, "_update_btn")
    assert win._more_btn.objectName() == "headerMoreButton"
    assert win._more_btn.toolTip() == "더보기"
    assert win._add_btn.iconSize().width() == 15
    assert win.month_label.font().pixelSize() == 16
    assert win.month_label.width() == 92
    assert win.findChild(QWidget, "headerLeftGroup").width() == win.findChild(QWidget, "headerRightGroup").width()
    assert win.law_search_input.placeholderText() == "AI 법령정보 또는 키워드 검색..."
    assert win.law_search_input.height() == 30

    law_search_box = win.findChild(QWidget, "lawSearchBox")
    assert law_search_box is not None
    assert law_search_box.height() == 36

    law_submit_btn = win.findChild(QWidget, "lawSearchSubmitButton")
    assert law_submit_btn is not None
    assert law_submit_btn.height() == 30
    assert law_submit_btn.toolTip() == "법제처 AI 검색 실행"
    assert not law_submit_btn.icon().isNull()

    # 메뉴는 불투명 RoundMenu (배경 투명화 방지). 액션 집합·순서·아이콘 검증.
    menu = win._build_more_menu()
    actions = [a for a in menu.menuActions() if not a.isSeparator()]
    action_texts = [a.text() for a in actions]
    assert action_texts == ["자동정렬", "앱 업데이트", "휴지통", "설정", "앱 최소화"]
    assert all(not a.icon().isNull() for a in actions)

    actions[1].trigger()  # "앱 업데이트"
    assert calls == [win]


def test_main_window_uses_bundled_fluent_menu_icons(qtbot, app_dir, qapp):
    win = MainCalendarWindow()
    qtbot.addWidget(win)

    for icon_name in [
        "add", "search", "more_vertical", "bot",
        "chevron_left", "chevron_right",
        "note", "calendar", "timer",
        "note_color", "calendar_color", "timer_color",
        "arrow_sort_color", "arrow_sync_color", "settings_color", "subtract_color",
    ]:
        assert fluent_icon_path(icon_name).exists()

    assert not win._add_btn.icon().isNull()
    assert not win._more_btn.icon().isNull()
    assert win.prev_btn.text() == ""
    assert win.next_btn.text() == ""
    assert win.prev_btn.iconSize().width() == 18
    assert win.next_btn.iconSize().width() == 18
    assert not win.prev_btn.icon().isNull()
    assert not win.next_btn.icon().isNull()

    add_menu = win._build_add_menu()
    add_action_texts = [action.text() for action in add_menu.actions()]
    assert add_action_texts == ["스티키 노트", "D-Day 위젯", "집중 모드"]
    assert all(not action.icon().isNull() for action in add_menu.actions())


def _image_has_color(image, predicate) -> bool:
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() > 0 and predicate(color):
                return True
    return False


def test_fluent_regular_icons_are_tinted_and_color_icons_preserve_palette(qapp):
    regular_image = fluent_icon("add", "#FF0000", 24).pixmap(24, 24).toImage()
    color_image = fluent_icon("arrow_sort_color", "#FF0000", 24).pixmap(24, 24).toImage()

    assert _image_has_color(
        regular_image,
        lambda color: color.red() > 180 and color.green() < 80 and color.blue() < 80,
    )
    assert _image_has_color(
        color_image,
        lambda color: color.blue() > 120 and color.red() < 80,
    )
    assert _image_has_color(
        color_image,
        lambda color: color.red() < 60 and color.green() < 60 and color.blue() < 60,
    )


def test_fluent_color_icons_use_stronger_menu_palette():
    color_svg = fluent_icon_path("note_color").read_text(encoding="utf-8")

    assert "#D9ECFF" in color_svg
    assert "#5EAFFF" in color_svg
    assert "#EAF4FF" not in color_svg
    assert "#8EC5FF" not in color_svg


def test_build_spec_bundles_fluent_icon_resources():
    with open("build.spec", encoding="utf-8") as spec_file:
        spec = spec_file.read()

    assert "('resources', 'resources')" in spec
    assert "('licenses', 'licenses')" in spec
    assert "'PySide6.QtSvg'" in spec
    assert "'PySide6.QtSvgWidgets'" in spec
    assert "'PySide6.QtXml'" in spec
    assert "'PySide6.QtNetwork'" in spec


def test_settings_license_mentions_fluent_ui_system_icons(qtbot, app_dir, qapp):
    win = SettingsWindow()
    qtbot.addWidget(win)
    win.show()
    win._on_license()
    dlg = win._license_dialog
    index = dlg.component_combo.findData("fluent-icons")
    assert index >= 0
    dlg.component_combo.setCurrentIndex(index)
    text = dlg.document.toPlainText()
    assert "Fluent UI System Icons" in text
    assert "라이선스: MIT" in text
    assert "https://github.com/microsoft/fluentui-system-icons" in text
    assert "Microsoft Corporation" in text
    dlg.reject()


def test_calendar_weekend_dates_use_weekend_colors(qtbot, app_dir, qapp):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._current_year = 2026
    win._current_month = 5
    win._refresh_calendar()

    assert "#D32F2F" in win._day_cells["2026-05-03"].day_label.styleSheet()
    assert "#1565C0" in win._day_cells["2026-05-02"].day_label.styleSheet()
    assert "#1a1a1a" in win._day_cells["2026-05-04"].day_label.styleSheet()


def test_settings_destructive_buttons_use_icon_design(qtbot, app_dir, qapp):
    """데이터 초기화와 앱 종료 버튼은 아이콘과 명확한 버튼 스타일을 사용한다."""
    win = SettingsWindow()
    qtbot.addWidget(win)

    assert win.factory_reset_btn.objectName() == "factoryResetButton"
    assert win.factory_reset_btn.text() == "초기화"  # 행 이름이 '데이터 초기화'라 영문 표기를 쓰지 않는다.
    assert win.factory_reset_btn.toolTip() == "모든 데이터를 초기화"
    assert not win.factory_reset_btn.icon().isNull()
    assert "#28a745" not in win.factory_reset_btn.styleSheet()
    assert "border-radius: 6px" in win.factory_reset_btn.styleSheet()
    assert "padding: 5px 14px 5px 34px" in win.factory_reset_btn.styleSheet()
    assert win.factory_reset_btn.minimumWidth() >= 152

    assert win.quit_app_btn.objectName() == "quitAppButton"
    assert win.quit_app_btn.text() == "앱 종료"
    assert win.quit_app_btn.toolTip() == "기후노트 종료"
    assert not win.quit_app_btn.icon().isNull()
    assert "#dc3545" not in win.quit_app_btn.styleSheet()
    assert "border-radius: 6px" in win.quit_app_btn.styleSheet()
    assert "padding: 5px 12px 5px 32px" in win.quit_app_btn.styleSheet()
    assert win.quit_app_btn.minimumWidth() >= 112


def test_settings_factory_reset_icon_visible_on_hover(qtbot, app_dir, qapp):
    """소프트 danger hover(빨강 배경) 시 아이콘이 흰색으로 바뀌어 묻히지 않는다."""
    from PySide6.QtCore import QPointF, QEvent
    from PySide6.QtGui import QEnterEvent

    win = SettingsWindow()
    qtbot.addWidget(win)
    btn = win.factory_reset_btn
    assert btn._normal_icon.cacheKey() != btn._hover_icon.cacheKey()
    btn.enterEvent(QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1)))
    assert btn.icon().cacheKey() == btn._hover_icon.cacheKey()
    btn.leaveEvent(QEvent(QEvent.Type.Leave))
    assert btn.icon().cacheKey() == btn._normal_icon.cacheKey()


def test_settings_factory_reset_no_pin(qtbot, app_dir, qapp, monkeypatch):
    """초기화는 PIN 없이 확인 팝업 수락만으로 실행된다(사용성 결정, 0011 완화)."""
    win = SettingsWindow()
    qtbot.addWidget(win)
    assert not hasattr(win, "reset_pin")

    calls = []
    monkeypatch.setattr(
        db,
        "backup_before_operation",
        lambda operation: calls.append(f"backup:{operation}") or True,
    )
    monkeypatch.setattr(db, "reset_database", lambda: calls.append("reset"))
    monkeypatch.setattr("ui_settings.reset_salt", lambda: None)
    monkeypatch.setattr("ui_settings.MessageBox.exec", lambda self: 1)  # 확인창 수락

    win._on_reset()
    assert calls == ["backup:reset", "reset"]


def test_main_window_settings_brought_to_foreground(qtbot, app_dir, qapp, monkeypatch):
    """설정창을 열 때 스티키(Qt.Tool) 위로 확실히 올라오도록 raise_+activateWindow까지 호출한다."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)

    calls = []

    class _FakeSettings:
        def __init__(self, **kwargs):
            self.reset_succeeded = MagicMock()

        def isVisible(self):
            return False

        def show(self):
            calls.append("show")

        def windowState(self):
            return Qt.WindowNoState

        def setWindowState(self, state):
            calls.append("setWindowState")

        def raise_(self):
            calls.append("raise")

        def activateWindow(self):
            calls.append("activate")

        # _on_settings가 창을 화면 안으로 클램프(_clamp_window_to_screen)하므로
        # 실제 창처럼 지오메트리 API를 제공한다. 화면 내부 사각형이라 이동은 없다.
        def screen(self):
            return None

        def frameGeometry(self):
            from PySide6.QtCore import QRect
            return QRect(100, 100, 200, 200)

    monkeypatch.setattr("ui_settings.SettingsWindow", _FakeSettings)
    win._on_settings()
    # show 후 raise_와 activateWindow가 모두 호출되어 포그라운드로 올라와야 한다
    assert "show" in calls
    assert "raise" in calls
    assert "activate" in calls
    assert win._settings_window.reset_succeeded.connect.call_args_list == [
        call(win._discard_unit_converter), call(win._discard_date_time_calculator),
        call(win._discard_money_notation),
        call(win._discard_document_converter),
        call(win._discard_optional_mini_apps),  # 선택형 미니앱 공용 연결부(등록부가 비어도 연결은 남는다)
    ]


def test_settings_font_combo_persists_and_requires_restart(qtbot, app_dir, qapp, monkeypatch):
    """글꼴 선택 변경은 저장하되, 실행 중인 QApplication 폰트는 바꾸지 않는다."""
    if not available_system_fonts():
        pytest.skip("시스템 폰트가 없는 환경(headless/offscreen) — system 폰트 선택 검증 불가")
    messages = []
    monkeypatch.setattr("ui_settings.InfoBar.error", lambda **kwargs: messages.append(kwargs))
    before_family = qapp.font().family()
    before_families = qapp.font().families()
    win = SettingsWindow()
    qtbot.addWidget(win)

    target_index = -1
    for i in range(win.font_combo.count()):
        data = win.font_combo.itemData(i)
        if isinstance(data, str) and data.startswith("system:"):
            target_index = i
            break
    assert target_index >= 0
    font_key = win.font_combo.itemData(target_index)
    win.font_combo.setCurrentIndex(target_index)

    assert db.get_setting(db.SETTING_APP_FONT) == font_key
    assert qapp.font().family() == before_family
    assert qapp.font().families() == before_families
    assert messages[-1]["title"] == "재시작 필요"
    assert messages[-1]["content"] == "글꼴 변경은 앱을 재시작해야 적용됩니다."
    assert messages[-1]["duration"] == 7000


def test_settings_system_font_selection_persists_and_requires_restart(qtbot, app_dir, qapp):
    """설치된 시스템 폰트도 선택/저장할 수 있어야 한다."""
    if not available_system_fonts():
        pytest.skip("시스템 폰트가 없는 환경(headless/offscreen) — system 폰트 선택 검증 불가")
    win = SettingsWindow()
    qtbot.addWidget(win)

    system_index = -1
    for i in range(win.font_combo.count()):
        data = win.font_combo.itemData(i)
        if isinstance(data, str) and data.startswith("system:"):
            system_index = i
            break
    assert system_index >= 0

    font_key = win.font_combo.itemData(system_index)
    win.font_combo.setCurrentIndex(system_index)

    assert db.get_setting(db.SETTING_APP_FONT) == font_key
    assert system_font_family_from_key(font_key) == win.font_combo.itemText(system_index)


def test_missing_system_font_setting_falls_back_to_malgun_gothic(qtbot, app_dir, qapp):
    """저장된 시스템 폰트가 사라졌으면 목록에 비활성 표시하고 맑은 고딕으로 fallback한다."""
    missing_key = system_font_key("Definitely Missing Font 123")
    db.save_setting(db.SETTING_APP_FONT, missing_key)

    win = SettingsWindow()
    qtbot.addWidget(win)

    index = win.font_combo.findData(missing_key)
    assert index >= 0
    assert win.font_combo.itemText(index) == "Definitely Missing Font 123 (없음)"
    assert resolve_app_font_family(missing_key) == db.DEFAULT_APP_FONT


def test_search_window_item_click_emits_date(qtbot, app_dir, qapp):
    """검색 결과 행 클릭 시 선택 날짜 signal이 발생해야 한다."""
    db.add_schedule("2026-05-05", "어린이날 일정", "#FFD166")

    win = SearchWindow()
    qtbot.addWidget(win)
    win.search_input.setText("어린이날")
    win._on_search()

    with qtbot.waitSignal(win.date_selected, timeout=1000) as blocker:
        win._on_item_clicked(win.result_table.item(0, 0))

    assert blocker.args == ["2026-05-05"]


def test_settings_sidebar_switch_persists_and_calls_callback(qtbot, app_dir, qapp):
    """v2.6 사이드바 스위치가 설정값 저장과 콜백 호출을 함께 수행하는지 검증."""
    called = []
    win = SettingsWindow(on_sidebar_changed=lambda: called.append(True))
    qtbot.addWidget(win)

    assert win.sidebar_switch.isChecked() is False

    win.sidebar_switch.setChecked(True)
    assert db.get_setting(db.SETTING_SHOW_SIDEBAR) == "1"
    assert called == [True]

    win.sidebar_switch.setChecked(False)
    assert db.get_setting(db.SETTING_SHOW_SIDEBAR) == "0"
    assert called == [True, True]


def test_shortcut_sidebar_loads_normal_and_missing_slots(qtbot, app_dir, qapp, tmp_path):
    """사이드바가 DB의 정상/끊김 바로가기 상태를 슬롯 UI에 반영하는지 검증."""
    existing = tmp_path / "existing-tool.exe"
    existing.write_text("stub", encoding="utf-8")
    missing = tmp_path / "missing-tool.exe"

    db.update_shortcut(1, "정상도구", str(existing))
    db.update_shortcut(2, "끊긴도구", str(missing))

    widget = ShortcutSidebarWidget()
    qtbot.addWidget(widget)
    widget.load_shortcuts()

    assert len(widget.slots) == 6
    normal = widget.slots[0]
    missing_slot = widget.slots[1]

    assert normal.name == "정상도구"
    assert normal.path == str(existing)
    assert normal.btn.text() == ""
    # 지우기 ×는 마우스를 올렸을 때만 보인다(디자인 점검 10번).
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent
    enter = QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5))
    assert normal.delete_btn.isHidden()
    QApplication.sendEvent(normal, enter)
    assert not normal.delete_btn.isHidden()
    QApplication.sendEvent(normal, QEvent(QEvent.Leave))
    assert normal.delete_btn.isHidden()

    assert missing_slot.name == "끊긴도구"
    assert missing_slot.path == str(missing)
    assert missing_slot.name_label.text().startswith("(!)")
    assert "파일을 찾을 수 없음" in missing_slot.toolTip()
    QApplication.sendEvent(missing_slot, enter)
    assert not missing_slot.delete_btn.isHidden()


def test_shortcut_sidebar_has_six_slots(qtbot, app_dir, qapp):
    """바로가기 사이드바가 6개 슬롯을 가진다."""
    sidebar = ShortcutSidebarWidget()
    qtbot.addWidget(sidebar)
    assert len(sidebar.slots) == 6
    # 6번째 슬롯이 DB 바로가기와 매핑되는지 (예외 없이 로드)
    sidebar.load_shortcuts()
    assert sidebar.slots[5].shortcut_id == 6


def test_shortcut_slot_delete_clears_database(qtbot, app_dir, qapp, tmp_path):
    """바로가기 슬롯 삭제 버튼 동작이 DB와 빈 슬롯 UI를 함께 갱신하는지 검증."""
    target = tmp_path / "delete-me.exe"
    target.write_text("stub", encoding="utf-8")
    db.update_shortcut(1, "삭제대상", str(target))

    widget = ShortcutSidebarWidget()
    qtbot.addWidget(widget)
    widget.load_shortcuts()

    widget.slots[0]._on_delete()

    shortcut = next(s for s in db.get_shortcuts() if s["id"] == 1)
    assert shortcut["name"] == ""
    assert shortcut["path"] == ""
    assert widget.slots[0].btn.text() == "+"
    assert widget.slots[0].name_label.text() == "추가"  # 빈 칸은 '+ 추가'(디자인 점검 10번)


def test_shortcut_empty_slot_can_choose_file(qtbot, app_dir, qapp, tmp_path,
                                             monkeypatch):
    """빈 슬롯에서 파일을 선택하면 기존 슬롯 행에 즉시 저장한다."""
    target = tmp_path / "climate-tool.exe"
    target.write_text("stub", encoding="utf-8")
    monkeypatch.setattr(
        ui_main.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(target), ""),
    )

    slot = ShortcutSlot(1)
    qtbot.addWidget(slot)
    slot._select_file()

    shortcut = next(s for s in db.get_shortcuts() if s["id"] == 1)
    assert shortcut["name"] == "climate-tool"
    assert shortcut["path"] == str(target)
    assert slot.path == str(target)


def test_shortcut_empty_slot_can_choose_folder(qtbot, app_dir, qapp, tmp_path,
                                               monkeypatch):
    """빈 슬롯에서 폴더를 선택해도 동일한 DB/UI 경로를 사용한다."""
    target = tmp_path / "업무 자료"
    target.mkdir()
    monkeypatch.setattr(
        ui_main.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(target),
    )

    slot = ShortcutSlot(2)
    qtbot.addWidget(slot)
    slot._select_folder()

    shortcut = next(s for s in db.get_shortcuts() if s["id"] == 2)
    assert shortcut["name"] == "업무 자료"
    assert shortcut["path"] == str(target)


def test_shortcut_manage_menu_renames_and_exposes_repair(qtbot, app_dir, qapp,
                                                         tmp_path, monkeypatch):
    """등록 슬롯 우클릭 메뉴는 이름 변경·경로 재지정·삭제를 제공한다."""
    target = tmp_path / "report.exe"
    target.write_text("stub", encoding="utf-8")
    db.update_shortcut(3, "기존 이름", str(target))

    slot = ShortcutSlot(3)
    qtbot.addWidget(slot)
    slot.update_data("기존 이름", str(target))
    menu = slot._build_manage_menu()
    qtbot.addWidget(menu)
    assert [action.text() for action in menu.menuActions()] == [
        "이름 변경", "경로 다시 지정", "삭제",
    ]

    monkeypatch.setattr(
        ui_main.QInputDialog,
        "getText",
        lambda *args, **kwargs: ("새 이름", True),
    )
    slot._rename()

    shortcut = next(s for s in db.get_shortcuts() if s["id"] == 3)
    assert shortcut["name"] == "새 이름"
    assert shortcut["path"] == str(target)
    assert slot.name == "새 이름"


def test_shortcut_missing_path_click_opens_repair_choices(
        qtbot, app_dir, qapp, tmp_path, monkeypatch):
    """끊어진 바로가기는 경고만 하지 않고 즉시 재지정 경로를 연다."""
    slot = ShortcutSlot(4)
    qtbot.addWidget(slot)
    slot.update_data("이동된 도구", str(tmp_path / "missing.exe"))
    calls = []
    monkeypatch.setattr(slot, "_show_registration_menu", lambda: calls.append(True))
    monkeypatch.setattr(ui_main.InfoBar, "warning", lambda **kwargs: None)

    slot._on_click()

    assert calls == [True]


def test_shortcut_reassign_preserves_custom_name(
        qtbot, app_dir, qapp, tmp_path, monkeypatch):
    """경로만 다시 지정할 때 사용자가 정한 표시 이름은 유지한다."""
    old_target = tmp_path / "old.exe"
    new_target = tmp_path / "new.exe"
    old_target.write_text("old", encoding="utf-8")
    new_target.write_text("new", encoding="utf-8")
    db.update_shortcut(5, "내 업무 도구", str(old_target))
    monkeypatch.setattr(
        ui_main.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(new_target), ""),
    )

    slot = ShortcutSlot(5)
    qtbot.addWidget(slot)
    slot.update_data("내 업무 도구", str(old_target))
    slot._select_file()

    shortcut = next(s for s in db.get_shortcuts() if s["id"] == 5)
    assert shortcut["name"] == "내 업무 도구"
    assert shortcut["path"] == str(new_target)


def test_shortcut_picker_cancel_preserves_slot(
        qtbot, app_dir, qapp, tmp_path, monkeypatch):
    """파일 선택을 취소하면 기존 바로가기를 변경하지 않는다."""
    target = tmp_path / "keep.exe"
    target.write_text("keep", encoding="utf-8")
    db.update_shortcut(6, "유지", str(target))
    monkeypatch.setattr(
        ui_main.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: ("", ""),
    )

    slot = ShortcutSlot(6)
    qtbot.addWidget(slot)
    slot.update_data("유지", str(target))
    slot._select_file()

    shortcut = next(s for s in db.get_shortcuts() if s["id"] == 6)
    assert shortcut == {"id": 6, "name": "유지", "path": str(target)}


@pytest.mark.parametrize(
    ("root_path", "expected"),
    [("C:\\", "C:"), ("\\\\server\\share\\", "share")],
)
def test_shortcut_root_path_has_visible_default_name(root_path, expected):
    """드라이브·UNC 공유 루트도 빈 이름으로 저장하지 않는다."""
    assert ShortcutSlot._default_target_name(root_path) == expected


def test_shortcut_name_label_right_click_opens_management(
        qtbot, app_dir, qapp, tmp_path, monkeypatch):
    """아이콘뿐 아니라 슬롯 이름을 우클릭해도 관리 메뉴를 연다."""
    target = tmp_path / "manage.exe"
    target.write_text("stub", encoding="utf-8")
    slot = ShortcutSlot(1)
    qtbot.addWidget(slot)
    slot.update_data("관리", str(target))
    calls = []
    monkeypatch.setattr(slot, "_show_manage_menu", lambda pos=None: calls.append(pos))

    slot.name_label.customContextMenuRequested.emit(QPoint(2, 2))

    assert len(calls) == 1


def test_shortcut_populated_left_click_still_launches(
        qtbot, app_dir, qapp, tmp_path, monkeypatch):
    """관리 기능 추가 뒤에도 정상 슬롯 좌클릭은 기존처럼 실행한다."""
    target = tmp_path / "launch.exe"
    target.write_text("stub", encoding="utf-8")
    slot = ShortcutSlot(2)
    qtbot.addWidget(slot)
    slot.update_data("실행", str(target))
    launched = []
    monkeypatch.setattr(ui_main.os, "startfile", launched.append)

    slot._on_click()

    assert launched == [str(target)]


def test_shortcut_drop_still_replaces_name_and_path(
        qtbot, app_dir, qapp, tmp_path):
    """드래그 등록은 새 대상 이름으로 교체하고 drop을 수락한다."""
    target = tmp_path / "dropped-tool.exe"
    target.write_text("stub", encoding="utf-8")
    slot = ShortcutSlot(3)
    qtbot.addWidget(slot)
    slot.update_data("예전 이름", str(tmp_path / "old.exe"))

    accepted = []
    url = SimpleNamespace(toLocalFile=lambda: str(target))
    mime = SimpleNamespace(hasUrls=lambda: True, urls=lambda: [url])
    event = SimpleNamespace(
        mimeData=lambda: mime,
        acceptProposedAction=lambda: accepted.append(True),
    )

    slot.dropEvent(event)

    shortcut = next(s for s in db.get_shortcuts() if s["id"] == 3)
    assert shortcut["name"] == "dropped-tool"
    assert shortcut["path"] == str(target)
    assert accepted == [True]


def test_shortcut_repair_action_opens_target_choices(
        qtbot, app_dir, qapp, tmp_path, monkeypatch):
    """관리 메뉴의 경로 다시 지정 액션이 파일·폴더 선택 메뉴로 이어진다."""
    target = tmp_path / "repair.exe"
    target.write_text("stub", encoding="utf-8")
    slot = ShortcutSlot(4)
    qtbot.addWidget(slot)
    slot.show()
    slot.update_data("복구", str(target))
    calls = []
    monkeypatch.setattr(slot, "_show_registration_menu", lambda: calls.append(True))
    menu = slot._build_manage_menu()
    qtbot.addWidget(menu)

    menu.menuActions()[1].trigger()
    assert calls == []
    qtbot.waitUntil(lambda: calls == [True])


def test_save_all_sticky_notes_persists_hidden_floating_note(
        qtbot, app_dir, qapp):
    """편집 직후 트레이로 숨겨도 종료 저장은 최신 HTML을 보존한다."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._on_new_sticky_note()
    sticky = next(iter(win._sticky_windows.values()))
    sticky.text_edit.setPlainText("숨긴 직후 종료해도 보존")
    sticky.hide()

    assert win.save_all_sticky_notes() is True

    note = next(n for n in db.get_open_sticky_notes() if n["id"] == sticky.note_id)
    assert "숨긴 직후 종료해도 보존" in note["content"]


def test_prepare_for_quit_blocks_when_sticky_save_fails(
        qtbot, app_dir, qapp, monkeypatch):
    """정상 종료는 모든 스티키 저장이 성공한 뒤에만 허용한다."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    monkeypatch.setattr(win, "save_all_sticky_notes", lambda: False)
    errors = []
    monkeypatch.setattr(
        ui_main.InfoBar,
        "error",
        lambda **kwargs: errors.append(kwargs),
    )

    assert win.prepare_for_quit() is False
    assert errors


def test_main_window_sidebar_visibility_changes_width(qtbot, app_dir, qapp):
    """show_sidebar 설정이 메인 창 폭과 사이드바 가시성에 반영되는지 검증."""
    db.save_setting(db.SETTING_SHOW_SIDEBAR, "0")
    win = MainCalendarWindow()
    qtbot.addWidget(win)

    assert win.maximumWidth() == 380
    assert win.sidebar.isHidden()

    db.save_setting(db.SETTING_SHOW_SIDEBAR, "1")
    win._apply_sidebar_visibility()

    assert win.maximumWidth() == 460
    assert not win.sidebar.isHidden()


def test_initial_sidebar_style_uses_intended_visibility_before_show(qtbot, app_dir, qapp):
    """첫 실행 렌더 전에도 사이드바-캘린더 경계 스타일은 설정값을 따라야 한다."""
    db.save_setting(db.SETTING_SHOW_SIDEBAR, "1")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "compact")

    win = MainCalendarWindow()
    qtbot.addWidget(win)
    calendar_section = win.right_content.findChild(QWidget, "calendarSection")
    header_section = win.right_content.findChild(QWidget, "headerSection")

    assert win.sidebar.isHidden() is False
    assert calendar_section.property("sidebarActive") == "true"
    assert header_section.property("sidebarActive") == "true"


def test_main_window_adds_focus_widget_from_menu(qtbot, app_dir, qapp, monkeypatch):
    """추가 메뉴의 집중 모드 생성 흐름이 DB와 윈도우 목록에 반영된다."""
    class FakeFocusDialog:
        def __init__(self, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def get_result(self):
            return "집중 모드 테스트", "50/10", True

    monkeypatch.setattr("ui_focus.FocusCreateDialog", FakeFocusDialog)

    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._on_new_focus_widget()

    focus_widgets = db.get_open_focus_widgets()
    assert any(w["goal"] == "집중 모드 테스트" and w["mode_key"] == "50/10" for w in focus_widgets)
    assert len(win._focus_windows) == 1
    focus_win = next(iter(win._focus_windows.values()))
    assert focus_win.timer_model.status == "running"


def test_large_dday_add_card_opens_existing_create_flow(qtbot, app_dir, qapp, monkeypatch):
    """large 모드 D-Day 추가 카드는 기존 생성 흐름을 재사용하고 패널을 갱신한다."""
    class FakeDDayDialog:
        def __init__(self, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def get_result(self):
            return "패널 추가", "2026-12-31"

    monkeypatch.setattr("ui_dday.DDayCreateDialog", FakeDDayDialog)

    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    win = MainCalendarWindow()
    qtbot.addWidget(win)

    assert win._dday_side_panel is not None
    assert win._dday_side_panel._action_card.mode == "add"

    win._dday_side_panel._action_card.clicked.emit()

    widgets = db.get_open_dday_widgets()
    assert len(widgets) == 1
    assert widgets[0]["name"] == "패널 추가"
    assert len(win._dday_windows) == 1
    assert len(win._dday_side_panel._cards) == 1
    assert win._dday_side_panel._cards[0]._name == "패널 추가"


def test_dday_dialog_enter_accepts_ok(qtbot, app_dir, qapp):
    """D-Day 입력창에서 Enter 키가 취소가 아니라 확인 동작을 수행하는지 검증."""
    dlg = DDayCreateDialog()
    qtbot.addWidget(dlg)
    dlg.name_input.setText("보고서 마감")
    dlg.year_input.setText("2026")
    dlg.month_input.setText("12")
    dlg.day_input.setText("31")
    dlg.day_input.setFocus()

    with qtbot.waitSignal(dlg.accepted, timeout=1000):
        qtbot.keyClick(dlg.day_input, Qt.Key_Return)

    assert dlg.result() == QDialog.Accepted
    assert dlg.get_result() == ("보고서 마감", "2026-12-31")


def test_calendar_holiday_dates_use_red(qtbot, app_dir, qapp):
    """공휴일은 요일과 무관하게 날짜 숫자가 빨강(#D32F2F)."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._current_year = 2026
    win._current_month = 5
    win._refresh_calendar()
    # 2026-05-05 어린이날(화요일) → 평일이지만 공휴일이라 빨강
    assert "#D32F2F" in win._day_cells["2026-05-05"].day_label.styleSheet()
    # 공휴일 아닌 평일(2026-05-04 월)은 검정 유지
    assert "#1a1a1a" in win._day_cells["2026-05-04"].day_label.styleSheet()


def test_calendar_cell_has_no_holiday_label(qtbot, app_dir, qapp):
    """공휴일명 행은 셀에서 제거되었다(하단으로 이동)."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._current_year = 2026
    win._current_month = 6
    win._refresh_calendar()
    cell = win._day_cells["2026-06-06"]
    assert not hasattr(cell, "holiday_lbl")


def test_calendar_cell_shows_total_count(qtbot, app_dir, qapp):
    """셀에 그날 총 일정 수가 표시되고, 0개면 빈칸."""
    db.add_schedule("2026-07-10", "a", "#FFD166")
    db.add_schedule("2026-07-10", "b", "#FFD166")
    db.add_schedule("2026-07-10", "c", "#4CC9F0")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._current_year = 2026
    win._current_month = 7
    win._refresh_calendar()
    assert win._day_cells["2026-07-10"].count_label.text() == "3"
    assert win._day_cells["2026-07-11"].count_label.text() == ""


def test_calendar_day_button_expanded_renders_chips(qtbot, app_dir, qapp):
    events = [
        {"content": "회의", "color": "#FFD166"},
        {"content": "점심 약속 아주 긴 제목 말줄임 확인", "color": "#4CC9F0"},
        {"content": "보고서", "color": "#FF6B6B"},
    ]
    cell = ui_main.CalendarDayButton(
        15, False, ["#FFD166", "#4CC9F0", "#FF6B6B"],
        True, "2025-08-15", False, 5, len(events), "expanded",
    )
    qtbot.addWidget(cell)
    cell.resize(140, 110)
    cell.set_events(events)
    assert cell._chips_container.isVisibleTo(cell)
    assert cell._chips_layout.count() >= 1
    cell._set_mode("compact")
    assert cell.squares_label.isVisibleTo(cell)
    assert cell.count_label.isVisibleTo(cell)
    assert not cell._chips_container.isVisibleTo(cell)
    assert cell.count_label.text() == "3"


@pytest.mark.parametrize(
    ("calendar_scale", "font_px", "chip_height", "spacing"),
    [("medium", 10, 16, 2), ("large", 13, 22, 3)],
)
def test_calendar_day_chip_metrics_follow_scale(
        qtbot, qapp, calendar_scale, font_px, chip_height, spacing):
    cell = ui_main.CalendarDayButton(
        15, False, ["#FFD166"], True, "2025-08-15",
        False, 5, 1, "expanded", calendar_scale=calendar_scale,
    )
    qtbot.addWidget(cell)
    cell.resize(140, 110)
    cell.set_events([{"content": "회의", "color": "#FFD166"}])

    chip = cell._chips_layout.itemAt(0).widget()
    assert chip.font().pixelSize() == font_px
    assert chip.height() == chip_height
    assert cell._chips_layout.spacing() == spacing


def test_calendar_day_button_selected_style_is_scoped_to_cell(qtbot, qapp):
    cell = ui_main.CalendarDayButton(
        15, False, ["#FFD166"],
        True, "2025-08-15", False, 5, 1, "expanded",
    )
    qtbot.addWidget(cell)

    cell.set_selected(True)

    assert "#calendarDayButton" in cell.styleSheet()
    # 중간·크게 칸은 고른 날을 바탕 채움 대신 테두리로 표시한다(디자인 점검 15번).
    assert "border: 2px solid #01295F" in cell.styleSheet()
    assert "background: transparent" in cell._chips_container.styleSheet()
    assert "#01295F" not in cell._chips_container.styleSheet()


def test_calendar_day_button_overflow_keeps_one_real_chip(qtbot, app_dir, qapp):
    events = [{"content": f"일정{i}", "color": "#FFD166"} for i in range(20)]
    cell = ui_main.CalendarDayButton(
        20, False, ["#FFD166"], True, "2025-08-20",
        False, 3, len(events), "expanded",
    )
    qtbot.addWidget(cell)
    cell.resize(120, 50)
    cell.set_events(events)
    count = cell._chips_layout.count()
    assert count >= 2
    assert "더" in cell._chips_layout.itemAt(count - 1).widget().text()
    assert "더" not in cell._chips_layout.itemAt(0).widget().text()


def test_calendar_scale_expanded_uncaps_width_and_forces_sidebar(qtbot, app_dir, qapp):
    db.save_setting(db.SETTING_SHOW_SIDEBAR, "0")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._apply_calendar_scale()
    assert win.maximumWidth() > 460
    assert not win.sidebar.isHidden()
    assert win.right_content.findChild(QWidget, "calendarSection").property("expanded") == "true"

    db.save_setting(db.SETTING_CALENDAR_SCALE, "compact")
    win._apply_calendar_scale()
    assert win.maximumWidth() == 380
    assert win.sidebar.isHidden()
    assert win.right_content.findChild(QWidget, "calendarSection").property("expanded") == "false"


def test_calendar_scale_reparents_schedule_panel(qtbot, app_dir, qapp):
    db.save_setting(db.SETTING_CALENDAR_SCALE, "compact")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    calendar_section = win.right_content.findChild(QWidget, "calendarSection")
    assert win.schedule_panel.parent() is calendar_section

    db.save_setting(db.SETTING_CALENDAR_SCALE, "medium")
    win._apply_calendar_scale()
    assert win._expanded_row is not None
    assert win.schedule_panel.parent() is win._expanded_row
    assert win.schedule_panel.isAncestorOf(win.schedule_list)

    db.save_setting(db.SETTING_CALENDAR_SCALE, "compact")
    win._apply_calendar_scale()
    assert win.schedule_panel.parent() is calendar_section
    assert win._expanded_row.isHidden()


def test_calendar_scale_transitions_do_not_leave_visible_old_cells(qtbot, app_dir, qapp):
    from datetime import date
    target = date.today().replace(day=10).isoformat()
    db.add_schedule(target, "전환 후 칩", "#FFD166")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    for scale in ("medium", "compact", "large"):
        db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
        win._apply_calendar_scale()
        qapp.processEvents()
        visible_cells = [
            cell for cell in win.findChildren(ui_main.CalendarDayButton)
            if cell.isVisibleTo(win)
        ]
        assert len(visible_cells) == win.calendar_grid.count()
        if scale != "compact":
            cell = win._day_cells[target]
            assert cell._chips_layout.count() >= 1
            assert cell._chips_layout.itemAt(0).widget().isVisibleTo(win)


def test_long_running_app_creates_backup_after_date_changes(
        qtbot, app_dir, qapp, monkeypatch):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._last_auto_backup_date = "2000-01-01"
    saved = []
    backed_up = []
    monkeypatch.setattr(
        win, "save_all_sticky_notes", lambda: saved.append(True) or True
    )
    monkeypatch.setattr(
        db, "backup_database", lambda: backed_up.append(True) or True
    )

    win._check_daily_auto_backup()

    assert saved == [True]
    assert backed_up == [True]
    assert win._last_auto_backup_date == date.today().isoformat()


def test_selected_holiday_shows_name_in_bottom(qtbot, app_dir, qapp):
    """공휴일 선택 시 하단 holiday_info_label에 공휴일명이 (음력 설정과 무관하게) 표시."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._current_year = 2026
    win._current_month = 6
    win._refresh_calendar()

    win._on_date_selected("2026-06-06")  # 현충일
    assert "현충일" in win.holiday_info_label.text()

    win._on_date_selected("2026-06-08")  # 평일 → 라벨 비워야 함
    assert win.holiday_info_label.text() == ""

    # 음력 표시 설정과 무관하게 공휴일명이 보여야 함 (사용자 핵심 결정)
    win._show_lunar = True
    win._on_date_selected("2026-06-06")
    assert "현충일" in win.holiday_info_label.text()
    win._show_lunar = False
    win._on_date_selected("2026-06-06")
    assert "현충일" in win.holiday_info_label.text()  # 음력 OFF여도 공휴일명 유지


def test_cell_count_updates_live_on_add_and_delete(qtbot, app_dir, qapp):
    """일정 추가/삭제 시 그리드 재빌드 없이 셀 개수가 즉시 갱신."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._current_year = 2026
    win._current_month = 7
    win._refresh_calendar()
    win._on_date_selected("2026-07-15")
    assert win._day_cells["2026-07-15"].count_label.text() == ""

    # 추가
    win._schedule_color = "#FFD166"
    win.schedule_input.setText("새 일정")
    win._on_add_schedule()
    assert win._day_cells["2026-07-15"].count_label.text() == "1"

    # 삭제
    item = win.schedule_list.item(0)
    sid = item.data(Qt.UserRole)
    win._on_delete_schedule(item, sid)
    assert win._day_cells["2026-07-15"].count_label.text() == ""


def test_schedule_right_click_menu_edits_and_deletes(
        qtbot, app_dir, qapp, monkeypatch):
    """우클릭 메뉴를 추가해도 기존 더블클릭 편집과 휴지통 삭제 경로를 재사용한다."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._on_date_selected("2026-07-15")
    win.schedule_input.setText("회의")
    win._on_add_schedule()

    item = win.schedule_list.item(0)

    # 기존 더블클릭 인라인 편집은 그대로 유지한다.
    win.schedule_list.itemDoubleClicked.emit(item)
    assert win._editing_item is item
    win._finish_current_edit(False)

    menu = win._build_schedule_context_menu(item)
    qtbot.addWidget(menu)
    actions = [action for action in menu.menuActions() if not action.isSeparator()]
    assert [action.text() for action in actions] == ["편집", "삭제"]

    actions[0].trigger()
    assert win._editing_item is item
    win._finish_current_edit(False)

    actions[1].trigger()
    assert win.schedule_list.count() == 0
    assert db.get_schedules("2026-07-15") == []

    shown = []
    monkeypatch.setattr(
        ui_main.RoundMenu,
        "exec",
        lambda self, pos: shown.append((self, pos)),
    )
    win.schedule_input.setText("우클릭 일정")
    win._on_add_schedule()
    item = win.schedule_list.item(0)
    pos = win.schedule_list.visualItemRect(item).center()
    win.schedule_list.customContextMenuRequested.emit(pos)
    assert len(shown) == 1
    assert [
        action.text() for action in shown[0][0].menuActions()
        if not action.isSeparator()
    ] == ["편집", "삭제"]


def test_settings_has_five_section_panels(qtbot, app_dir, qapp):
    from qfluentwidgets import StrongBodyLabel

    win = SettingsWindow()
    qtbot.addWidget(win)
    headers = [w for w in win.findChildren(StrongBodyLabel)
               if w.objectName() == "panelHeader"]
    assert len(headers) == 5
    assert {h.text() for h in headers} == {
        "화면 표시", "위젯·도구", "데이터", "보안", "시스템"}


def test_settings_panel_header_is_high_contrast(qtbot, app_dir, qapp):
    """시안 A: 패널 헤더가 밝은 구분 바 + 진한 굵은 글자로 고대비를 유지한다."""
    win = SettingsWindow()
    qtbot.addWidget(win)
    headers = win.findChildren(QLabel)
    panel_headers = [h for h in headers if h.objectName() == "panelHeader"]
    assert panel_headers, "panelHeader 라벨이 없음"
    # 색상은 setTextColor(네이티브), 굵기는 setFont(Bold)로 설정함 — QSS 아님
    assert panel_headers[0].font().bold()
    assert panel_headers[0].font().pixelSize() == 14
    bars = [w for w in win.findChildren(QWidget) if w.objectName() == "panelHeaderBar"]
    assert bars, "panelHeaderBar 헤더 바가 없음"
    assert HEADER_BG in bars[0].styleSheet()
    assert HEADER_BG == "#F6F6F6"
    assert "border:1px solid" in bars[0].styleSheet()
    assert HEADER_BORDER in bars[0].styleSheet()
    assert HEADER_BORDER == "#D7DAE2"


def test_settings_panel_hover_does_not_darken_body(qtbot, app_dir, qapp):
    win = SettingsWindow()
    qtbot.addWidget(win)
    panels = [w for w in win.findChildren(QWidget) if w.objectName() == "settingsPanel"]
    assert panels
    panel = panels[0]
    assert panel._hoverBackgroundColor().getRgb() == panel._normalBackgroundColor().getRgb()
    assert panel._pressedBackgroundColor().getRgb() == panel._normalBackgroundColor().getRgb()


def test_settings_panels_have_visible_outline(qtbot, app_dir, qapp):
    """회색 설정창 배경에서 섹션 카드가 구분되도록 outline 패널을 사용한다(시안 A)."""
    win = SettingsWindow()
    qtbot.addWidget(win)
    panels = [w for w in win.findChildren(QWidget) if w.objectName() == "settingsPanel"]
    assert len(panels) == 5
    assert all(p.getBorderRadius() == 11 for p in panels)
    assert panels[0].BORDER_COLOR.name().upper() == "#D7DAE2"


def test_calendar_size_picker_scales_and_select(qtbot, app_dir, qapp):
    from ui_settings import CalendarSizePicker

    assert [s[0] for s in CalendarSizePicker._SCALES] == ["compact", "medium", "large"]

    picker = CalendarSizePicker("compact")
    qtbot.addWidget(picker)
    got = []
    picker.scaleChanged.connect(lambda v: got.append(v))

    assert picker.current_scale() == "compact"
    picker.select("large")
    assert picker.current_scale() == "large"
    assert got == ["large"]

    selected = [v for v, opt in picker._options.items()
                if opt.property("selected") == "true"]
    assert selected == ["large"]


def test_calendar_size_picker_invalid_current_falls_back(qtbot, app_dir, qapp):
    from ui_settings import CalendarSizePicker

    picker = CalendarSizePicker("nonsense")
    qtbot.addWidget(picker)
    assert picker.current_scale() == "compact"


# ─── Task 1: 설정창 UI 개선 ──────────────────────────────────────

def test_settings_no_top_title(qtbot, app_dir, qapp):
    """상단 큰 '설정' 제목(TitleLabel)을 제거한다."""
    from qfluentwidgets import TitleLabel
    win = SettingsWindow()
    qtbot.addWidget(win)
    titles = [l.text() for l in win.findChildren(TitleLabel)]
    assert "설정" not in titles


def test_settings_monitor_combo_wider(qtbot, app_dir, qapp):
    win = SettingsWindow()
    qtbot.addWidget(win)
    assert win.monitor_combo.maximumWidth() == 210


def test_settings_position_row_taller(qtbot, app_dir, qapp):
    win = SettingsWindow()
    qtbot.addWidget(win)
    assert win._position_row.minimumHeight() >= 56


def test_settings_section_headers_bold(qtbot, app_dir, qapp):
    from qfluentwidgets import StrongBodyLabel
    win = SettingsWindow()
    qtbot.addWidget(win)
    headers = [w for w in win.findChildren(StrongBodyLabel)
               if w.objectName() == "panelHeader"]
    assert headers
    assert all(h.font().bold() for h in headers)


def test_settings_credit_single_line(qtbot, app_dir, qapp):
    win = SettingsWindow()
    qtbot.addWidget(win)
    assert win.author_label.wordWrap() is False


# ─── Task 3: 앱 종료 1회 종료 ─────────────────────────────────────

def test_settings_quit_closes_window_then_quits(qtbot, app_dir, qapp, monkeypatch):
    """앱 종료는 설정창을 먼저 닫고 종료한다(2회 클릭 버그 방지)."""
    calls = []
    win = SettingsWindow(
        on_quit_callback=lambda: calls.append("prepare") or True
    )
    qtbot.addWidget(win)
    win.show()
    monkeypatch.setattr(win, "close", lambda: calls.append("close"))
    monkeypatch.setattr("ui_settings.QApplication.quit", lambda: calls.append("quit"))
    win._on_quit()
    assert calls == ["prepare", "close", "quit"]


def test_settings_quit_callback_can_block_exit(qtbot, app_dir, qapp, monkeypatch):
    """메인의 종료 전 저장이 실패하면 설정창과 앱을 그대로 유지한다."""
    calls = []
    win = SettingsWindow(on_quit_callback=lambda: False)
    qtbot.addWidget(win)
    monkeypatch.setattr(win, "close", lambda: calls.append("close"))
    monkeypatch.setattr("ui_settings.QApplication.quit", lambda: calls.append("quit"))

    win._on_quit()

    assert calls == []


# ─── Task 4: 월 네비 가운데 정렬 ───────────────────────────────────

def test_month_nav_centered_symmetric_stretch(qtbot, app_dir, qapp):
    """월 네비 좌우 stretch factor가 같아야 달력 위 중앙에 온다(중간/크게에서 우측 쏠림 방지)."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    header = win.findChild(QWidget, "headerSection")
    top_bar = header.layout().itemAt(0).layout()  # 첫 행이 상단 바
    nav_index = None
    for i in range(top_bar.count()):
        lay = top_bar.itemAt(i).layout()
        if lay is not None and lay.indexOf(win.month_label) != -1:
            nav_index = i
            break
    assert nav_index is not None
    assert top_bar.stretch(nav_index - 1) == top_bar.stretch(nav_index + 1)
    assert top_bar.stretch(nav_index - 1) > 0


# ─── Task 6: D-Day 미니카드 삭제 배선 ──────────────────────────────

def test_main_panel_dday_delete_removes_widget(qtbot, app_dir, qapp, monkeypatch):
    """미니 D-Day 카드 X → 확인 수락 시 DB 삭제 + 레지스트리 정리 + 패널 갱신."""
    class _FakeBtn:
        def setText(self, *_):
            pass

    class _FakeDialog:
        def __init__(self, *a, **k):
            self.yesButton = _FakeBtn()
            self.cancelButton = _FakeBtn()

        def exec(self):
            return 1  # 수락

        def deleteLater(self):
            pass

    monkeypatch.setattr("qfluentwidgets.Dialog", _FakeDialog)

    win = MainCalendarWindow()
    qtbot.addWidget(win)
    from ui_dday import DDayWidgetWindow
    wid = db.create_dday_widget("x", "2026-12-31")
    data = next(w for w in db.get_open_dday_widgets() if w["id"] == wid)
    dwin = DDayWidgetWindow(wid, data)
    qtbot.addWidget(dwin)
    win._dday_windows[wid] = dwin

    refreshed = []
    monkeypatch.setattr(win, "_refresh_dday_panel", lambda: refreshed.append(True))

    win._on_panel_dday_delete(wid)

    assert wid not in win._dday_windows
    assert all(w["id"] != wid for w in db.get_open_dday_widgets())
    assert refreshed == [True]


# ─── Task 8: 집중 미니카드 종료 배선 ───────────────────────────────

def test_main_panel_focus_close_ends_session(qtbot, app_dir, qapp, monkeypatch):
    """집중 미니카드 X → 확인 수락 시 단일 집중 종료(DB 삭제 + 레지스트리 정리)."""
    class _FakeBtn:
        def setText(self, *_):
            pass

    class _FakeDialog:
        def __init__(self, *a, **k):
            self.yesButton = _FakeBtn()
            self.cancelButton = _FakeBtn()

        def exec(self):
            return 1

        def deleteLater(self):
            pass

    monkeypatch.setattr("qfluentwidgets.Dialog", _FakeDialog)

    win = MainCalendarWindow()
    qtbot.addWidget(win)
    from ui_focus import FocusWidgetWindow
    wid = db.create_focus_widget("집중", "25/5")
    data = next(w for w in db.get_open_focus_widgets() if w["id"] == wid)
    fwin = FocusWidgetWindow(wid, data)
    qtbot.addWidget(fwin)
    fwin.widget_closed.connect(win._on_focus_widget_closed)
    win._focus_windows[wid] = fwin

    win._on_panel_focus_close()

    assert len(win._focus_windows) == 0
    assert db.get_open_focus_widgets() == []


# ─── _compute_arrange_layout 순수 함수 테스트 ────────────────────────────────

def test_arrange_layout_empty_returns_empty():
    coords, clamped = _compute_arrange_layout(
        [], (0, 0, 100, 100), (0, 0, 1920, 1080), "bottom-right", 19
    )
    assert coords == []
    assert clamped == 0


def test_arrange_layout_all_within_screen():
    """정상 케이스: clamped == 0, 모든 위젯이 화면 안."""
    items = [(220, 95), (220, 95), (241, 78)]
    cal = (1600, 800, 1920, 1080)
    scr = (0, 0, 1920, 1080)
    snap = 19
    coords, clamped = _compute_arrange_layout(items, cal, scr, "bottom-right", snap)
    assert clamped == 0
    for (x, y), (w, h) in zip(coords, items):
        assert scr[0] <= x, f"x={x} < screen left"
        assert x + w <= scr[2], f"x+w={x+w} > screen right"
        assert scr[1] <= y, f"y={y} < screen top"
        assert y + h <= scr[3], f"y+h={y+h} > screen bottom"


def test_arrange_layout_no_overlap_with_calendar():
    """4모서리 각각: 위젯 사각형이 캘린더와 겹치지 않음."""
    items = [(220, 95), (220, 95)]
    snap = 19
    cases = [
        ("bottom-right", (1600, 800, 1920, 1080)),
        ("bottom-left",  (0,    800, 320,  1080)),
        ("top-right",    (1600, 0,   1920, 200)),
        ("top-left",     (0,    0,   320,  200)),
    ]
    scr = (0, 0, 1920, 1080)
    for pos, cal in cases:
        coords, _ = _compute_arrange_layout(items, cal, scr, pos, snap)
        for (x, y), (w, h) in zip(coords, items):
            wx1, wy1, wx2, wy2 = x, y, x + w, y + h
            cx1, cy1, cx2, cy2 = cal
            overlap = (wx2 > cx1 and cx2 > wx1 and wy2 > cy1 and cy2 > wy1)
            assert not overlap, f"pos={pos}: widget ({wx1},{wy1},{wx2},{wy2}) overlaps calendar {cal}"


def test_arrange_layout_overflow_skips_without_overlap():
    """공간 부족 시 못 담는 위젯은 None(정렬 제외)으로 두고, 배치된 것끼리는
    절대 겹치지 않으며 모두 화면 안. (엄격 비겹침)
    """
    items = [(220, 95)] * 12          # 좁은 화면에 과다
    scr = (0, 0, 400, 300)
    cal = (200, 200, 400, 300)
    coords, skipped = _compute_arrange_layout(items, cal, scr, "bottom-right", 19)
    assert skipped > 0                                  # 일부는 정렬 제외
    assert coords.count(None) == skipped               # 제외분 = None 개수
    placed = [(x, y, x + w, y + h)
              for (x, y), (w, h) in ((c, it) for c, it in zip(coords, items) if c is not None)]
    # 배치된 위젯은 모두 화면 안
    for (x1, y1, x2, y2) in placed:
        assert x1 >= scr[0] and y1 >= scr[1] and x2 <= scr[2] and y2 <= scr[3]
    # 배치된 위젯끼리 상호 비겹침
    for a in range(len(placed)):
        for b in range(a + 1, len(placed)):
            assert not ui_main._overlap(placed[a], placed[b]), f"배치된 {a}/{b} 겹침"


def test_arrange_layout_uses_l_shaped_space_before_skipping():
    """캘린더 위쪽 띠만 보지 않고, 옆 L자 공간까지 사용해 D-Day를 배치한다."""
    items = [(220, 95)] * 4
    scr = (0, 0, 500, 360)
    cal = (280, 160, 500, 360)

    coords, skipped = _compute_arrange_layout(items, cal, scr, "bottom-right", 19)

    assert skipped == 0
    assert all(c is not None for c in coords)
    placed = _rects(coords, items)
    for a in range(len(placed)):
        for b in range(a + 1, len(placed)):
            assert not ui_main._overlap(placed[a], placed[b])
    for rect in placed:
        assert not ui_main._overlap(rect, cal)


def test_arrange_layout_stacks_small_widgets_in_side_columns():
    """작은 D-Day 위젯은 캘린더 옆 공간에 세로로 쌓고 다음 열을 연다."""
    items = [(220, 95)] * 4
    scr = (0, 0, 760, 360)
    cal = (520, 90, 760, 360)

    coords, skipped = _compute_arrange_layout(items, cal, scr, "bottom-right", 19)

    assert skipped == 0
    xs = sorted({x for x, _ in coords})
    assert len(xs) == 2
    for x in xs:
        assert sum(1 for cx, _ in coords if cx == x) == 2
    placed = _rects(coords, items)
    for a in range(len(placed)):
        for b in range(a + 1, len(placed)):
            assert not ui_main._overlap(placed[a], placed[b])


def test_arrange_layout_does_not_skip_when_only_gap_is_too_strict():
    """5mm 여백은 선호하되, 실제 비겹침 배치가 가능하면 제외하지 않는다."""
    items = [(220, 95), (220, 95)]
    scr = (0, 0, 456, 240)
    cal = (228, 120, 456, 240)

    coords, skipped = _compute_arrange_layout(items, cal, scr, "bottom-right", 19)

    assert skipped == 0
    placed = _rects(coords, items)
    assert not ui_main._overlap(placed[0], placed[1])
    for rect in placed:
        assert not ui_main._overlap(rect, cal)


def test_arrange_layout_four_positions_direction():
    """right계: widget.right <= cal.right / left계: widget.x >= cal.left."""
    items = [(220, 95)]
    snap = 19
    scr = (0, 0, 1920, 1080)

    for pos, cal in [("bottom-right", (1600, 800, 1920, 1080)),
                     ("top-right",    (1600, 0,   1920, 200))]:
        coords, _ = _compute_arrange_layout(items, cal, scr, pos, snap)
        x, _ = coords[0]
        assert x + items[0][0] <= cal[2], f"{pos}: widget right {x+items[0][0]} > cal.right {cal[2]}"

    for pos, cal in [("bottom-left", (0, 800, 320, 1080)),
                     ("top-left",    (0, 0,   320, 200))]:
        coords, _ = _compute_arrange_layout(items, cal, scr, pos, snap)
        x, _ = coords[0]
        assert x >= cal[0], f"{pos}: widget left {x} < cal.left {cal[0]}"


# ─── 2D 빈-패킹 자동정렬: 보조 순수함수 ──────────────────────────────────────

def test_overlap_strict_boundary_touch_is_not_overlap():
    assert ui_main._overlap((0, 0, 10, 10), (5, 5, 15, 15)) is True
    assert ui_main._overlap((0, 0, 10, 10), (10, 0, 20, 10)) is False   # 변 공유
    assert ui_main._overlap((0, 0, 10, 10), (10, 10, 20, 20)) is False  # 꼭짓점 접촉


def test_hard_violation_detects_each_kind():
    cal = (100, 100, 200, 200)
    scr = (0, 0, 300, 300)
    coords = [(0, 0), (0, 50)]
    items = [(40, 40), (40, 40)]
    assert ui_main._hard_violation(coords, items, cal, scr, 0) is None
    assert ui_main._hard_violation([(0, 0), (10, 10)], [(40, 40), (40, 40)], cal, scr, 0) == "mutual"
    assert ui_main._hard_violation([(0, 0), (10, 10)], [(40, 40), (40, 40)], cal, scr, 1) is None
    assert ui_main._hard_violation([(120, 120)], [(40, 40)], cal, scr, 0) == "calendar"
    assert ui_main._hard_violation([(280, 0)], [(40, 40)], cal, scr, 0) == "offscreen"
    assert ui_main._hard_violation([(260, 0)], [(40, 40)], cal, scr, 0) is None


# ─── 2D 빈-패킹 자동정렬: 핵심 불변식 ────────────────────────────────────────

_NORMAL_ITEMS = [(220, 95), (220, 95), (220, 95), (220, 95), (241, 78), (220, 209)]
_POSITIONS = ["bottom-right", "bottom-left", "top-right", "top-left"]
_CAL_BY_POS = {
    "bottom-right": (1540, 420, 1920, 1080),
    "bottom-left":  (0, 420, 380, 1080),
    "top-right":    (1540, 0, 1920, 660),
    "top-left":     (0, 0, 380, 660),
}


def _rects(coords, items):
    return [(x, y, x + w, y + h) for (x, y), (w, h) in zip(coords, items)]


def test_arrange_layout_no_mutual_overlap_all_corners():
    scr = (0, 0, 1920, 1080)
    for pos in _POSITIONS:
        coords, clamped = ui_main._compute_arrange_layout(_NORMAL_ITEMS, _CAL_BY_POS[pos], scr, pos, 19)
        assert clamped == 0, f"{pos}: 정상 입력인데 clamped>0"
        rs = _rects(coords, _NORMAL_ITEMS)
        for a in range(len(rs)):
            for b in range(a + 1, len(rs)):
                assert not ui_main._overlap(rs[a], rs[b]), f"{pos}: 위젯 {a}/{b} 겹침"


def test_arrange_layout_within_screen_and_clear_of_calendar_all_corners():
    scr = (0, 0, 1920, 1080)
    for pos in _POSITIONS:
        coords, _ = ui_main._compute_arrange_layout(_NORMAL_ITEMS, _CAL_BY_POS[pos], scr, pos, 19)
        for (x1, y1, x2, y2) in _rects(coords, _NORMAL_ITEMS):
            assert x1 >= scr[0] and y1 >= scr[1] and x2 <= scr[2] and y2 <= scr[3]
            assert not ui_main._overlap((x1, y1, x2, y2), _CAL_BY_POS[pos])


def test_arrange_layout_deterministic():
    scr, cal = (0, 0, 1920, 1080), (1540, 420, 1920, 1080)
    r1 = ui_main._compute_arrange_layout(_NORMAL_ITEMS, cal, scr, "bottom-right", 19)
    r2 = ui_main._compute_arrange_layout(_NORMAL_ITEMS, cal, scr, "bottom-right", 19)
    assert r1 == r2


def test_arrange_layout_snap_grid_alignment():
    scr, cal = (0, 0, 1920, 1080), (1540, 420, 1920, 1080)
    coords, _ = ui_main._compute_arrange_layout(_NORMAL_ITEMS, cal, scr, "bottom-right", 19)
    for (x, y) in coords:
        assert x % 19 == 0 and y % 19 == 0


def test_arrange_layout_prefers_multicolumn_for_mixed_sizes():
    """D-Day 다수 + 긴 스티키 → 단일 열보다 멀티컬럼(컴팩트)을 선택한다."""
    scr, cal = (0, 0, 1920, 1080), (1540, 420, 1920, 1080)
    coords, clamped = ui_main._compute_arrange_layout(_NORMAL_ITEMS, cal, scr, "bottom-right", 19)
    assert clamped == 0
    rs = _rects(coords, _NORMAL_ITEMS)
    bw = max(r[2] for r in rs) - min(r[0] for r in rs)
    bh = max(r[3] for r in rs) - min(r[1] for r in rs)
    # 멀티컬럼: bbox 폭이 가장 넓은 단일 위젯(241)보다 크다.
    assert bw > 241, "단일 열로 배치됨 — 멀티컬럼 실패"
    # 단일 열 대비 세로가 짧다: 모든 높이 합(naive 단일열)보다 작다.
    naive_h = sum(h for (_, h) in _NORMAL_ITEMS) + 19 * (len(_NORMAL_ITEMS) - 1)
    assert bh < naive_h


def test_arrange_layout_calendar_right_edge_at_screen_edge():
    """캘린더 우변이 화면 끝에 붙은 경계(cal_r == scr_r)에서도 화면 침범·겹침 없음."""
    scr = (0, 0, 1920, 1080)
    cal = (1540, 420, 1920, 1080)   # cal_r == scr_r
    coords, clamped = ui_main._compute_arrange_layout(_NORMAL_ITEMS, cal, scr, "bottom-right", 19)
    assert clamped == 0
    for (x1, y1, x2, y2) in _rects(coords, _NORMAL_ITEMS):
        assert x2 <= 1920                       # 우측 화면 끝 침범 없음
        assert not ui_main._overlap((x1, y1, x2, y2), cal)
