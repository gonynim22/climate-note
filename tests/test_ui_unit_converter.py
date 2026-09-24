"""합성 데이터에서 환산기 실제 입력·창 수명·기존 저장 불변과 렌더를 확인한다."""
import os
from pathlib import Path
import sqlite3

import pytest
from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton, QWidget
from qfluentwidgets.common.font import fontFamilies, setFontFamilies
from shiboken6 import isValid

from app_fonts import apply_app_font
import database as db
import security
import ui_main
import ui_settings
from ui_main import MainCalendarWindow
from ui_unit_converter import UnitConverterWindow
from unit_converter import parse_number


@pytest.fixture(autouse=True)
def isolated_ui(app_dir, qapp, monkeypatch):
    previous_font, previous_families = qapp.font(), fontFamilies()
    apply_app_font(db.DEFAULT_APP_FONT, qapp)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    db.save_setting(db.SETTING_SHOW_SIDEBAR, "1")
    monkeypatch.setattr(ui_main.InfoBar, "error", lambda **kw: None)
    yield
    qapp.setFont(previous_font)
    setFontFamilies(previous_families, save=False)


def activate(qtbot, win):
    win.show()
    win.raise_()
    win.activateWindow()
    assert QTest.qWaitForWindowExposed(win)
    assert QTest.qWaitForWindowActive(win)


def converter(qtbot):
    win = UnitConverterWindow()
    qtbot.addWidget(win)
    activate(qtbot, win)
    return win


def main_window(qtbot, scale="compact"):
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    main = MainCalendarWindow()
    qtbot.addWidget(main)
    activate(qtbot, main)
    return main


def open_converter(qtbot, main, keyboard=False):
    activate(qtbot, main)
    qtbot.mouseClick(main.sidebar.mini_apps_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: main._mini_apps_popup is not None)
    pocket = main._mini_apps_popup
    assert QTest.qWaitForWindowExposed(pocket)
    assert QTest.qWaitForWindowActive(pocket)
    if keyboard:
        pocket.converter_card.setFocus()
        qtbot.waitUntil(pocket.converter_card.hasFocus)
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    else:
        qtbot.mouseClick(pocket.converter_card, Qt.LeftButton)
    win = main._unit_converter
    assert win is not None
    # Qt.Tool은 부모의 활성 상태를 공유하므로 native 노출 뒤 포커스를 확인한다.
    assert QTest.qWaitForWindowExposed(win)
    assert QTest.qWaitForWindowActive(win)
    qtbot.waitUntil(win.input.hasFocus)
    assert main._mini_apps_popup is None
    assert not main.sidebar.mini_apps_button.isChecked()
    return win


def capture(win, name):
    QApplication.processEvents()
    appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if appdata:
        assert win.grab().save(str(Path(appdata).parent / f"unit-converter-{name}.png"))


def test_input_swap_other_unit_and_recent_keyboard(qtbot):
    win = converter(qtbot)
    win.input.setFocus()
    qtbot.keyClick(win.input, Qt.Key_A, Qt.ControlModifier)
    qtbot.keyClicks(win.input, "123.456789012345")
    assert win._result == pytest.approx(48.6050350442303)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    assert len(win.history.items) == 1
    win.swap_button.setFocus()
    qtbot.waitUntil(win.swap_button.hasFocus)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    assert win.from_combo.currentData() == "in"
    assert win._result == pytest.approx(123.456789012345, rel=1e-14)
    assert len(win.history.items) == 1  # 버튼 Enter가 기록 저장으로 전파되지 않는다.
    qtbot.mouseClick(win._row_widgets["m"][0], Qt.LeftButton)
    assert win.to_combo.currentData() == "m"
    assert win._result == pytest.approx(1.23456789012345)
    chip = win.recent_content.findChild(QPushButton, "recentCalculation")
    qtbot.mouseClick(chip, Qt.LeftButton)
    assert win.input.text() == "123.456789012345"
    assert win.from_combo.currentData() == "cm"
    assert win.to_combo.currentData() == "in"
    assert win.input.hasFocus()


def test_invalid_input_and_invalid_domain_do_not_save_or_swap(qtbot):
    win = converter(qtbot)
    for text in ("12abc", "1,23", "1e999", "", "-"):
        win.input.setText(text)
        assert win.input.text() == text
        assert win.result_label.text() == "—"
        assert not win.swap_button.isEnabled()
        win.save_recent()
        assert not win.history.items
    win.select_category("fuel")
    win.input.setText("0")
    assert win._result is None
    assert "0보다" in win.status_label.toolTip()
    capture(win, "invalid-fuel")
    win.input.setText("1,000")
    assert win._result == pytest.approx(.1)


@pytest.mark.parametrize("cid", ["len", "energy", "co2", "pm", "db", "cook", "fuel",
                                "gas_fraction", "mass_fraction", "water", "flow"])
def test_render_categories_and_actual_geometry(qtbot, cid):
    win = converter(qtbot)
    button = win.category_buttons[cid]
    win.category_scroll.ensureWidgetVisible(button)
    button.setFocus()
    qtbot.waitUntil(button.hasFocus)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    assert win.category_id == cid
    win.input.setText("123456.789")
    win.save_recent()
    QApplication.processEvents()
    assert win.surface.size().width() == 440
    assert win.surface.size().height() == 580
    assert win.size().width() == 488
    assert win.size().height() == 628
    for control in (win.input, win.from_combo, win.to_combo, win.result_label, win.close_button):
        point = control.mapTo(win, QPoint())
        assert win.rect().contains(point)
        assert point.x()+control.width() <= win.width()
        assert point.y()+control.height() <= win.height()
    assert win.result_label.fontMetrics().horizontalAdvance(win.result_label.text()) <= win.result_label.width()
    assert win.other_scroll.viewport().height() > 40
    assert win.body_scroll.verticalScrollBar().maximum() == 0
    assert win.from_combo.currentData(Qt.ToolTipRole)
    capture(win, cid)


def test_shadow_render_and_margin_click_preserve_calculation(qtbot):
    win = converter(qtbot)
    win.input.setText("42")
    win.save_recent()
    rendered = win.grab().toImage()
    dpr = rendered.devicePixelRatio()
    surface = win.surface.geometry()
    assert 0 < rendered.pixelColor(round((surface.left()-3)*dpr), round(surface.center().y()*dpr)).alpha() < 255
    for x, y in ((0, 0), (rendered.width()-1, 0), (0, rendered.height()-1),
                 (rendered.width()-1, rendered.height()-1)):
        assert rendered.pixelColor(x, y).alpha() == 0
    qtbot.mouseClick(win, Qt.LeftButton, pos=QPoint(5, win.height()//2))
    assert win.isVisible()
    assert win.input.text() == "42"
    assert len(win.history.items) == 1
    capture(win, "shadow")


def test_category_rail_is_compact_and_larger_text_fits(qtbot):
    win = converter(qtbot)
    groups = {}
    for category in win.category_buttons:
        button = win.category_buttons[category]
        win.category_scroll.ensureWidgetVisible(button)
        QApplication.processEvents()
        assert button.height() == 28
        labels = button.findChildren(QLabel)
        assert labels[-1].font().pixelSize() == 13
        for label in labels:
            assert label.fontMetrics().horizontalAdvance(label.text()) <= label.width()
            assert label.fontMetrics().height() <= label.height()
        button.setFocus()
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
        assert win.category_id == category
        group = win.category.group
        previous = groups.get(group)
        if previous is not None:
            assert button.y() - (previous.y()+previous.height()) == 0
        groups[group] = button
    win.select_category("len")
    QApplication.processEvents()
    capture(win, "compact-rail")


def test_combo_escape_closes_dropdown_before_window(qtbot):
    win = converter(qtbot)
    win.to_combo.setFocus()
    qtbot.waitUntil(win.to_combo.hasFocus)
    qtbot.keyClick(win.to_combo, Qt.Key_Down, Qt.AltModifier)
    qtbot.waitUntil(win.to_combo.view().isVisible)
    popup = win.to_combo.view().window()
    assert QTest.qWaitForWindowExposed(popup)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Down)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    assert not win.to_combo.view().isVisible()
    assert win.to_combo.currentData() != "in"
    win.to_combo.showPopup()
    qtbot.waitUntil(win.to_combo.view().isVisible)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Escape)
    assert win.isVisible()
    assert not win.to_combo.view().isVisible()
    win.input.setFocus()
    qtbot.keyClick(win.input, Qt.Key_Escape)
    assert not win.isVisible()


@pytest.mark.parametrize("name", ["from", "to", "gas", "temperature"])
@pytest.mark.parametrize("animated", [True, False])
def test_converter_dropdown_opens_without_transient_image_and_selects(qtbot, qapp, name, animated):
    win = converter(qtbot)
    win.select_category("temp" if name == "temperature" else "gas_fraction")
    if name != "temperature":
        win.to_combo.setCurrentIndex(win.to_combo.findData("mgm3"))
    combo = {"from": win.from_combo, "to": win.to_combo,
             "gas": win.conditions_panel.gas_picker,
             "temperature": win.conditions_panel.temperature_mode}[name]
    QApplication.processEvents()
    shown = []

    class PopupObserver(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
                shown.append(obj.metaObject().className())
            return False

    observer = PopupObserver()
    qapp.installEventFilter(observer)
    previous = QApplication.isEffectEnabled(Qt.UI_AnimateCombo)
    QApplication.setEffectEnabled(Qt.UI_AnimateCombo, animated)
    try:
        qtbot.mouseMove(combo, combo.rect().center())
        qtbot.wait(20)
        qtbot.mouseClick(combo, Qt.LeftButton)
        # 최종 표시만 기다리면 150ms roll 이미지의 재등장을 놓친다.
        assert combo.view().isVisible()
        assert QApplication.isEffectEnabled(Qt.UI_AnimateCombo) == animated
        assert "QRollEffect" not in shown
        assert shown.count("QComboBoxPrivateContainer") == 1
        popup = combo.view().window()
        assert QTest.qWaitForWindowExposed(popup)
        geometry = popup.geometry()
        # 기본 QComboBox는 열기 클릭의 release를 doubleClickInterval 동안
        # 보호한다. 초기 표시 검사는 위에서 동기로 하고 선택은 보호 시간 뒤 한다.
        qtbot.wait(max(180, QApplication.doubleClickInterval()+20))
        assert popup.geometry() == geometry
        assert combo.view().isVisible()
        assert "QRollEffect" not in shown

        target = (combo.currentIndex()+1) % combo.count()
        model_index = combo.model().index(target, 0)
        combo.view().scrollTo(model_index)
        point = combo.view().visualRect(model_index).center()
        qtbot.mouseMove(combo.view().viewport(), point)
        # QTest의 Windows 커서 이동은 native 이벤트 큐를 거친다.
        qtbot.wait(80)
        qtbot.mouseClick(combo.view().viewport(), Qt.LeftButton, pos=point)
        assert combo.currentIndex() == target
        assert not combo.view().isVisible()
        assert win.isVisible()

        combo.setFocus()
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Down, Qt.AltModifier)
        assert combo.view().isVisible()
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Escape)
        assert not combo.view().isVisible()
        assert combo.currentIndex() == target
        assert win.isVisible()
        combo.showPopup()
        win.hide()
        assert not combo.view().isVisible()
        assert QApplication.isEffectEnabled(Qt.UI_AnimateCombo) == animated
    finally:
        qapp.removeEventFilter(observer)
        QApplication.setEffectEnabled(Qt.UI_AnimateCombo, previous)


def test_converter_dropdowns_share_height_arrow_and_readable_rows(qtbot):
    win = converter(qtbot)
    win.select_category("gas_fraction")
    win.to_combo.setCurrentIndex(win.to_combo.findData("mgm3"))
    win.input.setFocus()
    QApplication.processEvents()
    arrows = []
    for combo in (win.from_combo, win.to_combo, win.conditions_panel.gas_picker):
        assert combo.height() == 28
        arrows.append(combo.grab(QRect(combo.width()-22, 0, 22, 28)).toImage())
    win.select_category("temp")
    QApplication.processEvents()
    combo = win.conditions_panel.temperature_mode
    assert combo.height() == 28
    arrows.append(combo.grab(QRect(combo.width()-22, 0, 22, 28)).toImage())
    assert all(arrow == arrows[0] for arrow in arrows[1:])
    for combo in (win.from_combo, win.to_combo, win.conditions_panel.temperature_mode):
        combo.showPopup()
        assert QTest.qWaitForWindowExposed(combo.view().window())
        for index in range(combo.count()):
            rect = combo.view().visualRect(combo.model().index(index, 0))
            assert rect.height() >= combo.fontMetrics().height()+4
        appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
        if appdata:
            label = "temperature" if combo is win.conditions_panel.temperature_mode else "from" if combo is win.from_combo else "to"
            assert combo.view().window().grab().save(str(Path(appdata).parent / f"converter-dropdown-{label}.png"))
        combo.hidePopup()
    capture(win, "unified-dropdowns")


def test_converter_popup_failure_restores_application_effect(qtbot, monkeypatch):
    win = converter(qtbot)
    previous = QApplication.isEffectEnabled(Qt.UI_AnimateCombo)
    QApplication.setEffectEnabled(Qt.UI_AnimateCombo, True)

    def fail(self):
        raise RuntimeError("synthetic popup failure")

    monkeypatch.setattr(QComboBox, "showPopup", fail)
    try:
        with pytest.raises(RuntimeError, match="synthetic popup failure"):
            win.to_combo.showPopup()
        assert QApplication.isEffectEnabled(Qt.UI_AnimateCombo)
    finally:
        QApplication.setEffectEnabled(Qt.UI_AnimateCombo, previous)


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
def test_pocket_launch_reuse_close_and_no_focus_theft(qtbot, scale):
    main = main_window(qtbot, scale)
    win = open_converter(qtbot, main, keyboard=scale=="medium")
    win.input.setText("42")
    qtbot.keyClick(win.input, Qt.Key_Return)
    win.close()
    assert open_converter(qtbot, main) is win
    assert win.input.text() == "42"
    assert len(win.history.items) == 1
    assert len(main.findChildren(UnitConverterWindow)) == 1
    assert win.screen().availableGeometry().contains(win.geometry())


@pytest.mark.parametrize("action", ["lock", "tray", "hide", "sidebar", "reset_prepare"])
def test_hiding_cancels_owned_popup_and_preserves_session(qtbot, action):
    main = main_window(qtbot)
    win = open_converter(qtbot, main)
    win.input.setText("42")
    win.save_recent()
    win.to_combo.showPopup()
    qtbot.waitUntil(win.to_combo.view().isVisible)
    if action == "lock":
        main._lock()
        main._open_unit_converter()
        assert not win.isEnabled()
        main._unlock()
    elif action == "tray":
        main._minimize_to_tray()
        main._open_unit_converter()
        main.toggle_visibility()
    elif action == "hide":
        main.hide()
        main.show()
    elif action == "sidebar":
        db.save_setting(db.SETTING_SHOW_SIDEBAR, "0")
        main._apply_sidebar_visibility()
    else:
        main._discard_data_widgets()
    assert not win.isVisible()
    assert not win.to_combo.view().isVisible()
    assert win.input.text() == "42"
    assert len(win.history.items) == 1


def test_scale_change_keeps_calculation_and_failed_quit_keeps_window(qtbot, monkeypatch):
    main = main_window(qtbot)
    win = open_converter(qtbot, main)
    win.input.setText("24")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    main._apply_calendar_scale()
    assert main._unit_converter is win
    assert win.isVisible()
    assert parse_number(win.input.text()) == 24
    monkeypatch.setattr(main, "save_all_sticky_notes", lambda: False)
    assert not main.prepare_for_quit()
    assert main._unit_converter is win
    monkeypatch.setattr(main, "save_all_sticky_notes", lambda: True)
    assert main.prepare_for_quit()
    assert main._unit_converter is None
    qtbot.waitUntil(lambda: not isValid(win))


def test_failed_schedule_save_blocks_converter(qtbot, monkeypatch):
    main = main_window(qtbot)
    monkeypatch.setattr(main, "_save_schedule_edit", lambda: False)
    main._open_unit_converter()
    assert main._unit_converter is None


def test_calculations_preserve_all_existing_data(qtbot, tmp_path):
    for sid in range(1, 7):
        db.update_shortcut(sid, f"기존 {sid}", str(tmp_path / f"{sid}.txt"))
    db.add_schedule("2026-09-20", "📌 기존 일정", "#FFD166")
    db.save_memo("2026-09-20", "메모 원문")
    note = db.create_sticky_note()
    db.update_sticky_note(note, content="<p>기존 스티키</p>")
    db.create_dday_widget("기념일", "2026-12-31")
    db.create_focus_widget("기존 목표")
    main = main_window(qtbot)
    # 기동 시 예약된 스티키 크기 스냅 저장을 환산기 조작과 구분한다.
    qtbot.waitUntil(lambda: all(not w._resize_timer.isActive() for w in main._sticky_windows.values()))
    with db._connection() as conn:
        before = tuple(conn.iterdump())
    salt = security.SALT_FILE.read_bytes()
    exported = db.export_all_data()
    for cid in ("len", "temp", "db", "fuel", "co2", "gas_fraction", "mass_fraction", "water", "flow"):
        win = open_converter(qtbot, main)
        win.select_category(cid)
        if cid == "gas_fraction":
            win.to_combo.setCurrentIndex(win.to_combo.findData("mgm3"))
            win.conditions_panel.gas_picker.setCurrentIndex(win.conditions_panel.gas_picker.findData("co2"))
        elif cid == "temp":
            win.conditions_panel.temperature_mode.setCurrentIndex(1)
        elif cid == "water":
            win.conditions_panel.water_approximation = False
            win.conditions_panel.density_input.setText("1.2")
        win.input.setText("12.3456789")
        win.swap()
        win.save_recent()
        win.close()
    with db._connection() as conn:
        assert tuple(conn.iterdump()) == before
    assert db.export_all_data() == exported
    assert security.SALT_FILE.read_bytes() == salt


@pytest.mark.parametrize("failure", [None, "backup", "database"])
def test_only_successful_factory_reset_discards_calculation(qtbot, monkeypatch, failure):
    main = main_window(qtbot)
    win = open_converter(qtbot, main)
    win.input.setText("42")
    win.save_recent()
    main._on_settings()
    monkeypatch.setattr(ui_settings.MessageBox, "exec", lambda self: 1)
    monkeypatch.setattr(ui_settings.InfoBar, "success", lambda **kw: None)
    monkeypatch.setattr(ui_settings.InfoBar, "error", lambda **kw: None)
    def fail(*args):
        raise OSError("synthetic reset failure")
    if failure:
        monkeypatch.setattr(db, "backup_before_operation" if failure == "backup" else "reset_database", fail)
    main._settings_window._on_reset()
    if failure:
        assert main._unit_converter is win
        assert win.input.text() == "42"
        assert len(win.history.items) == 1
    else:
        assert main._unit_converter is None
        qtbot.waitUntil(lambda: not isValid(win))


def test_disconnected_screen_and_smaller_work_area_are_clamped(qtbot, monkeypatch):
    win = converter(qtbot)
    available = QRect(-1280, 20, 1280, 700)
    class Screen:
        def availableGeometry(self):
            return available
    monkeypatch.setattr(QApplication, "screenAt", lambda point: Screen())
    win.move(3000, 2000)
    win.fit_to_screen()
    assert available.contains(win.geometry())
    available = QRect(0, 0, 340, 400)
    win.fit_to_screen()
    QApplication.processEvents()
    assert available.contains(win.geometry())
    assert win.body_scroll.verticalScrollBar().maximum() > 0
    win.body_scroll.ensureWidgetVisible(win.recent_content)
    QApplication.processEvents()
    assert win.body_scroll.horizontalScrollBar().maximum() == 0
    capture(win, "small-screen")
    available = QRect(-1280, 20, 1280, 700)
    win.fit_to_screen()
    QApplication.processEvents()
    assert win.surface.width() == 440
    assert win.surface.height() == 580
    assert win.layout().contentsMargins().left() == 24
    assert available.contains(win.geometry())


@pytest.mark.parametrize("cid,text,result,basis", [
    ("gas_fraction", "400", 400000, "몰분율"),
    ("mass_fraction", "5", 5, "질량분율"),
    ("water", "2.5", 2.5, "밀도"),
    ("flow", "6", 100, "실제 부피"),
])
def test_environment_basis_input_and_recent_restore(qtbot, cid, text, result, basis):
    win = converter(qtbot)
    win.select_category(cid)
    assert win.basis_label.isVisible()
    assert basis in win.basis_label.text()
    win.input.setFocus()
    qtbot.keyClick(win.input, Qt.Key_A, Qt.ControlModifier)
    qtbot.keyClicks(win.input, text)
    assert win._result == pytest.approx(result)
    qtbot.keyClick(win.input, Qt.Key_Return)
    win.select_category("len")
    assert "척관법" in win.basis_label.text()
    chip = win.recent_content.findChild(QPushButton, "recentCalculation")
    qtbot.mouseClick(chip, Qt.LeftButton)
    assert win.category_id == cid
    assert basis in win.basis_label.text()
    assert win._result == pytest.approx(result)
    win.input.setText("-1")
    assert win._result is None
    assert not win.swap_button.isEnabled()
    win.save_recent()
    assert len(win.history.items) == 1


def enter_text(qtbot, edit, text):
    edit.setFocus()
    qtbot.waitUntil(edit.hasFocus)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_A, Qt.ControlModifier)
    qtbot.keyClicks(QApplication.focusWidget(), text)


def test_water_conditions_edit_reset_history_and_swap(qtbot):
    win = converter(qtbot)
    win.select_category("water")
    panel = win.conditions_panel
    assert not panel.details.isVisible()
    enter_text(qtbot, win.input, "10")
    assert win._result == 10
    assert win.result_label.text() == "≈ 10"
    win.save_recent()
    qtbot.mouseClick(panel.toggle, Qt.LeftButton)
    enter_text(qtbot, panel.density_input, "1.2")
    assert win._result == pytest.approx(12)
    assert win.result_label.text() == "12"
    assert "직접 입력" in panel.summary.text()
    assert win._row_widgets["ugl"][1].text() == "12,000"
    win.save_recent()
    assert len(win.history.items) == 2
    qtbot.mouseClick(panel.toggle, Qt.LeftButton)
    assert "1.2" in panel.summary.text()
    qtbot.mouseClick(win.swap_button, Qt.LeftButton)
    assert win._result == pytest.approx(10)
    win.select_category("len")
    win.restore_recent(win.history.items[0])
    assert panel.density_input.text() == "1.2"
    assert win._result == pytest.approx(12)
    win.restore_recent(win.history.items[1])
    assert win.result_label.text() == "≈ 10"
    qtbot.mouseClick(panel.toggle, Qt.LeftButton)
    enter_text(qtbot, panel.density_input, "0")
    assert win._result is None
    assert not win.swap_button.isEnabled()
    assert panel.error.isVisible()
    win.save_recent()
    assert len(win.history.items) == 2
    qtbot.mouseClick(panel.reset_button, Qt.LeftButton)
    assert win._result == 10
    assert panel.water_approximation
    QApplication.processEvents()
    capture(win, "water-conditions")


def test_gas_selection_custom_conditions_and_recent_restore(qtbot):
    win = converter(qtbot)
    win.select_category("gas_fraction")
    panel = win.conditions_panel
    assert not panel.gas_picker.isVisible()
    enter_text(qtbot, win.input, "400")
    win.to_combo.setCurrentIndex(win.to_combo.findData("mgm3"))
    assert panel.gas_picker.isVisible()
    assert win._result is None  # 선택하지 않은 물질을 임의로 추정하지 않는다.
    panel.gas_picker.setFocus()
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Down)
    assert panel.gas_picker.currentData() == "co2"
    assert win._result == pytest.approx(719.538504984129)
    assert win.result_label.text().startswith("≈")
    win.save_recent()
    qtbot.mouseClick(panel.toggle, Qt.LeftButton)
    enter_text(qtbot, panel.gas_pressure_input, "202.65")
    assert win._result == pytest.approx(1439.077009968258)
    win.save_recent()
    assert len(win.history.items) == 2
    panel.gas_picker.setCurrentIndex(panel.gas_picker.findData("custom"))
    assert win._result is None
    enter_text(qtbot, panel.molar_mass_input, "44.0095")
    assert win._result == pytest.approx(1439.077009968258)
    enter_text(qtbot, panel.gas_temperature_input, "-273.15")
    assert win._result is None
    win.restore_recent(win.history.items[1])
    assert panel.gas_picker.currentData() == "co2"
    assert panel.gas_pressure_input.text() == "101.325"
    assert win._result == pytest.approx(719.538504984129)
    assert not panel.details.isVisible()
    qtbot.mouseClick(win.swap_button, Qt.LeftButton)
    assert win._result == pytest.approx(400)
    QApplication.processEvents()
    capture(win, "gas-conditions")


def test_temperature_difference_mode_and_history(qtbot):
    win = converter(qtbot)
    win.select_category("temp")
    panel = win.conditions_panel
    enter_text(qtbot, win.input, "10")
    assert win._result == pytest.approx(50, abs=1e-12)
    win.save_recent()
    panel.temperature_mode.setFocus()
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Down)
    assert win._result == 18
    win.save_recent()
    enter_text(qtbot, win.input, "-500")
    assert win._result == pytest.approx(-900, abs=1e-12)
    win.restore_recent(win.history.items[0])
    assert panel.temperature_mode.currentIndex() == 1
    assert win._result == 18
    win.restore_recent(win.history.items[1])
    assert panel.temperature_mode.currentIndex() == 0
    assert win._result == pytest.approx(50, abs=1e-12)
    QApplication.processEvents()
    capture(win, "temperature-mode")


@pytest.mark.parametrize("cid", ["water", "gas_fraction", "temp", "press", "db", "time"])
def test_conditions_accessible_in_small_work_area(qtbot, monkeypatch, cid):
    win = converter(qtbot)
    win.select_category(cid)
    panel = win.conditions_panel
    available = QRect(0, 0, 340, 400)
    class Screen:
        def availableGeometry(self):
            return available
    monkeypatch.setattr(QApplication, "screenAt", lambda point: Screen())
    win.fit_to_screen()
    panel.toggle.setFocus()
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    if cid == "gas_fraction":
        panel.gas_picker.setCurrentIndex(panel.gas_picker.findData("custom"))
    QApplication.processEvents()
    assert panel.details.isVisible()
    assert available.contains(win.geometry())
    assert win.body_scroll.horizontalScrollBar().maximum() == 0
    for control in (panel.toggle, panel.note, win.input, win.result_label, win.recent_content):
        win.body_scroll.ensureWidgetVisible(control)
        QApplication.processEvents()
        point = control.mapTo(win.body_scroll.viewport(), QPoint())
        assert point.x() >= 0
        assert point.x()+control.width() <= win.body_scroll.viewport().width()
        assert point.y() < win.body_scroll.viewport().height()
        assert point.y()+control.height() > 0
    capture(win, "conditions-small-" + cid)


def test_lock_closes_gas_picker_and_preserves_conditions(qtbot):
    main = main_window(qtbot)
    win = open_converter(qtbot, main)
    win.select_category("gas_fraction")
    win.to_combo.setCurrentIndex(win.to_combo.findData("mgm3"))
    panel = win.conditions_panel
    panel.gas_picker.setCurrentIndex(panel.gas_picker.findData("co2"))
    win.input.setText("400")
    panel.gas_picker.showPopup()
    qtbot.waitUntil(panel.gas_picker.view().isVisible)
    main._lock()
    assert not panel.gas_picker.view().isVisible()
    assert not win.isVisible()
    main._unlock()
    main._open_unit_converter()
    assert win._result == pytest.approx(719.538504984129)


def test_condition_history_chips_do_not_overlap_or_clip_text(qtbot):
    win = converter(qtbot)
    win.select_category("water")
    for density in (1, 1.2, 1.5):
        win.conditions_panel.water_approximation = False
        win.conditions_panel.density_input.setText(str(density))
        win.input.setText("123.456789")
        win.save_recent()
    QApplication.processEvents()
    previous = None
    for index in range(win.recent_layout.count()-1):
        button = win.recent_layout.itemAt(index).widget()
        assert button.fontMetrics().horizontalAdvance(button.text()) + 14 <= button.width()
        if previous is not None:
            assert button.x() >= previous.x() + previous.width() + win.recent_layout.spacing()
        previous = button
    assert win.recent_scroll.horizontalScrollBar().maximum() > 0
    win.recent_scroll.ensureWidgetVisible(previous)
    QApplication.processEvents()
    qtbot.mouseClick(previous, Qt.LeftButton)
    assert win.conditions_panel.density_input.text() == "1.0"
    capture(win, "condition-history")
