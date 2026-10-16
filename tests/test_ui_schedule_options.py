"""v4.1 세부 설정 부품(아이콘·말줄임 라벨·시계 버튼·세부 카드·작은 달력·알약) 회귀. 합성 값만 쓴다."""
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QRect, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLineEdit, QPushButton, QWidget
from shiboken6 import isValid

import ui_schedule_emoji
import ui_schedule_options
from schedule_rules import ScheduleOptions
from ui_schedule_options import (
    CARD_WIDTH, ElidedLabel, ScheduleOptionsButton, ScheduleOptionsPills, ScheduleOptionsPopup,
    icon_pixmap, popup_position,
)


@pytest.fixture(autouse=True)
def _app(qapp):
    """QPixmap·QWidget을 만들기 전에 QApplication이 있어야 한다(없으면 프로세스가 멈춘다)."""
    return qapp


class Host(QWidget):
    """입력칸 + 시계 버튼 + 알약만 둔 작은 창(메인 창 없이 부품만 시험한다)."""

    def __init__(self, start="2026-10-15"):
        super().__init__()
        layout = QHBoxLayout(self)
        self.allowed = True
        self.edit = QLineEdit(self)
        self.button = ScheduleOptionsButton(self.edit, lambda: self.allowed, self)
        self.button.set_context(start)
        self.pills = ScheduleOptionsPills(self)
        layout.addWidget(self.button)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.pills)
        self.button.options_changed.connect(
            lambda options: self.pills.set_state(self.button.start_date(), options))


@pytest.fixture
def host(qtbot):
    widget = Host()
    qtbot.addWidget(widget)
    widget.resize(520, 60)
    widget.show()
    widget.activateWindow()
    assert QTest.qWaitForWindowExposed(widget)
    assert QTest.qWaitForWindowActive(widget)
    return widget


def open_card(qtbot, button):
    qtbot.mouseClick(button, Qt.LeftButton)
    qtbot.waitUntil(lambda: button._popup is not None and button._popup.isVisible())
    assert QTest.qWaitForWindowExposed(button._popup)
    return button._popup


def click(qtbot, widget):
    qtbot.mouseClick(widget, Qt.LeftButton)
    QApplication.processEvents()


def ink(image, predicate):
    return [(x, y) for y in range(image.height()) for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 0 and predicate(image.pixelColor(x, y))]


@pytest.mark.parametrize("ratio", [1.0, 1.25, 1.5])
@pytest.mark.parametrize("name", ["clock", "bell", "repeat", "calendar", "lock", "x"])
def test_icons_are_drawn_without_image_files(name, ratio):
    image = icon_pixmap(name, 12, "#94A3B8", ratio).toImage()
    assert image.width() == round(12 * ratio)
    assert ink(image, lambda color: True)


def test_unknown_icon_is_rejected():
    with pytest.raises(ValueError):
        icon_pixmap("unknown", 12, "#000000")


def test_emoji_module_reexports_moved_names():
    assert ui_schedule_emoji.SCHEDULE_CONTROL_DIAMETER == ui_schedule_options.SCHEDULE_CONTROL_DIAMETER == 22
    assert ui_schedule_emoji.popup_position is ui_schedule_options.popup_position


@pytest.mark.parametrize("anchor", [QRect(-1900, 10, 26, 26), QRect(-30, 1040, 26, 26)])
def test_popup_position_stays_on_negative_coordinate_monitor(anchor):
    available = QRect(-1920, 0, 1920, 1080)
    size = QSize(330, 480)
    assert available.contains(QRect(popup_position(anchor, size, available), size))


def test_elided_label_keeps_full_plain_text_and_shrinks(qtbot):
    text = "<b>굵게 보이면 안 됨</b> " + "긴 글 " * 40
    label = ElidedLabel(text)
    qtbot.addWidget(label)
    label.resize(80, 20)
    label.show()
    assert label.text() == text
    assert label.textFormat() == Qt.PlainText
    assert label.minimumSizeHint().width() == 0
    assert not label.grab().isNull()


def test_clock_button_turns_blue_with_dot_when_set(host):
    blue = lambda color: color.blue() > 180 and color.red() < 90  # noqa: E731
    assert host.button.size() == QSize(26, 26)
    assert not ink(host.button.grab().toImage(), blue)
    host.button.set_options(ScheduleOptions(start_time="09:00"))
    assert ink(host.button.grab().toImage(), blue)
    assert "09:00" in host.button.toolTip()


def test_chips_change_options_and_pills_immediately(qtbot, host):
    card = open_card(qtbot, host.button)
    click(qtbot, card.timed_chip)
    assert host.button.options().start_time == "09:00"
    assert card.time_edit.hasFocus()
    card.time_edit.selectAll()
    qtbot.keyClicks(card.time_edit, "1430")
    assert host.button.options().start_time == "09:00"  # Enter 전에는 반영하지 않는다.
    qtbot.keyClick(card.time_edit, Qt.Key_Return)
    assert host.button.options().start_time == "14:30"
    assert card.isVisible()
    click(qtbot, card.timed_alarm_chips[10])
    click(qtbot, card.repeat_chips["weekly"])
    assert card.repeat_caption.text() == "매주 목요일"
    assert host.button.options() == ScheduleOptions(start_time="14:30", repeat_rule="weekly", alarm_before=10)
    assert host.pills.visible_texts() == ["14:30 · 10분 전", "매주 목"]
    click(qtbot, card.all_day_chip)
    assert host.button.options() == ScheduleOptions(repeat_rule="weekly")
    assert card.all_day_alarm_box.isVisible() and not card.timed_alarm_box.isVisible()
    click(qtbot, card.all_day_alarm_chips[1440])
    assert host.pills.visible_texts() == ["하루 전 9시", "매주 목"]


@pytest.mark.parametrize("typed", ["2460", "9:5", "abc"])
def test_invalid_time_marks_field_and_keeps_last_value(qtbot, host, typed):
    card = open_card(qtbot, host.button)
    click(qtbot, card.timed_chip)
    card.time_edit.selectAll()
    qtbot.keyClicks(card.time_edit, typed)
    assert card.time_edit.property("invalid") is True
    assert host.button.options().start_time == "09:00"
    qtbot.keyClick(card.time_edit, Qt.Key_Return)
    assert card.time_edit.text() == "09:00"
    assert card.time_edit.property("invalid") is False


def test_typed_time_is_applied_when_card_closes(qtbot, host):
    card = open_card(qtbot, host.button)
    click(qtbot, card.timed_chip)
    card.time_edit.selectAll()
    qtbot.keyClicks(card.time_edit, "930")
    click(qtbot, card.done_button)
    assert host.button.options().start_time == "09:30"


def test_period_and_repeat_exclude_each_other(qtbot, host):
    card = open_card(qtbot, host.button)
    click(qtbot, card.many_days_chip)
    assert host.button.options().end_date == "2026-10-16"
    assert [rule for rule, chip in card.repeat_chips.items() if chip.isEnabled()] == [""]
    assert card.repeat_note.isVisible()
    click(qtbot, card.one_day_chip)
    assert all(chip.isEnabled() for chip in card.repeat_chips.values())
    click(qtbot, card.repeat_chips["daily"])
    assert not card.many_days_chip.isEnabled()
    assert card.period_note.isVisible()
    assert card.until_row.isVisible()


def test_mini_month_limits_range_and_picks_end(qtbot, host):
    card = open_card(qtbot, host.button)
    click(qtbot, card.many_days_chip)
    picker = card.period_picker
    assert picker.isVisible() and not card.until_picker.isVisible()
    assert not picker.button_for("2026-10-15").isEnabled()  # 시작일은 고정
    assert picker.button_for("2026-10-15").property("role") == "end"
    assert picker.button_for("2026-10-16").property("role") == "end"
    click(qtbot, picker.button_for("2026-10-23"))
    assert host.button.options().end_date == "2026-10-23"
    assert picker.button_for("2026-10-20").property("role") == "in"
    assert card.period_caption.text().startswith("10월 15일(목) ~ 23일(금) · 9일")
    picker.show_month(picker._month.replace(year=2027))  # 365일 경계
    assert picker.button_for("2027-10-15").isEnabled()
    assert not picker.button_for("2027-10-16").isEnabled()
    assert host.pills.visible_texts() == ["~10.23 · 9일"]


def test_until_picker_defaults_to_one_month_and_toggles(qtbot):
    host = Host(start="2026-01-31")
    qtbot.addWidget(host)
    host.show()
    card = open_card(qtbot, host.button)
    click(qtbot, card.repeat_chips["monthly"])
    assert card.repeat_caption.text() == "매월 31일 (없는 달은 마지막 날)"
    click(qtbot, card.until_chip)
    assert host.button.options().repeat_until == "2026-02-28"
    assert card.until_picker.isVisible()
    assert card.until_picker.title_label.text() == "2026년 2월"
    click(qtbot, card.until_picker.prev_button)
    assert not card.until_picker.button_for("2026-01-30").isEnabled()
    assert card.until_picker.button_for("2026-01-31").isEnabled()
    click(qtbot, card.until_caption)
    assert not card.until_picker.isVisible()
    click(qtbot, card.forever_chip)
    assert host.button.options() == ScheduleOptions(repeat_rule="monthly")


def test_clear_all_resets_every_part(qtbot, host):
    host.button.set_options(ScheduleOptions(start_time="10:00", repeat_rule="daily",
                                            repeat_until="2026-12-31", alarm_before=60))
    card = open_card(qtbot, host.button)
    click(qtbot, card.clear_button)
    assert host.button.options() == ScheduleOptions()
    assert host.pills.isHidden()


@pytest.mark.parametrize("state", [
    ScheduleOptions(),
    ScheduleOptions(start_time="09:00", alarm_before=1440),
    ScheduleOptions(end_date="2026-10-17"),
    ScheduleOptions(repeat_rule="monthly", repeat_until="2026-12-15"),
])
def test_card_width_fits_screen_without_clipped_chips(qtbot, host, state):
    host.button.set_options(state)
    card = open_card(qtbot, host.button)
    if state.end_date:
        click(qtbot, card.period_caption)
    if state.repeat_until:
        click(qtbot, card.until_caption)
    QApplication.processEvents()
    assert card.card.width() == CARD_WIDTH
    assert card.screen().availableGeometry().contains(card.card.geometry().translated(card.pos()))
    chips = [chip for chip in card.findChildren(QPushButton) if chip.property("segment") and chip.isVisible()]
    assert chips
    for chip in chips:
        assert chip.width() >= chip.sizeHint().width(), chip.text()
        assert card.card.rect().contains(chip.mapTo(card.card, chip.rect().bottomRight()))
    appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if appdata:
        name = "schedule-options-card-" + ("default" if state.is_default else "set") + ".png"
        assert card.grab().save(str(Path(appdata).parent / name))


def test_escape_restores_focus_and_keeps_value(qtbot, host):
    card = open_card(qtbot, host.button)
    click(qtbot, card.repeat_chips["daily"])
    qtbot.keyClick(card, Qt.Key_Escape)
    qtbot.waitUntil(lambda: host.edit.hasFocus())
    assert host.button.options() == ScheduleOptions(repeat_rule="daily")


def test_keyboard_opens_one_card_at_a_time(qtbot, host):
    button = host.button
    for _ in range(6):
        button.setFocus()
        qtbot.keyClick(button, Qt.Key_Return)
        qtbot.waitUntil(lambda: button._popup is not None and button._popup.isVisible())
        popup = button._popup
        button.open_popup()
        assert button._popup is popup
        qtbot.keyClick(popup, Qt.Key_Escape)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        assert not isValid(popup)
    assert host.findChildren(ScheduleOptionsPopup) == []


def test_closed_card_ignores_late_change_and_disallowed_open(qtbot, host):
    card = open_card(qtbot, host.button)
    host.button.close_popup()
    assert not card.isVisible()
    card.options_changed.emit(ScheduleOptions(start_time="11:00"))
    assert host.button.options() == ScheduleOptions()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not isValid(card)
    host.allowed = False  # 잠금·트레이 숨김
    host.button.open_popup()
    assert host.button._popup is None


def test_legacy_date_disables_button(qtbot):
    host = Host(start="2026-7-1")
    qtbot.addWidget(host)
    host.show()
    assert not host.button.isEnabled()
    host.button.open_popup()
    assert host.button._popup is None
    host.button.set_context("2026-07-01")
    assert host.button.isEnabled()


def test_pills_texts_and_signals(qtbot, host):
    opened, cleared = [], []
    host.pills.open_requested.connect(lambda: opened.append(True))
    host.pills.clear_requested.connect(cleared.append)
    host.pills.set_state("2026-10-21", ScheduleOptions(start_time="15:00", end_date="2026-10-23", alarm_before=10))
    QApplication.processEvents()
    assert host.pills.visible_texts() == ["15:00 · 10분 전", "~10.23 · 3일"]
    time_pill = host.pills.pills["time"]
    assert time_pill.height() == 22 and time_pill.width() <= 150
    qtbot.mouseClick(time_pill, Qt.LeftButton, pos=time_pill.clear_rect().center().toPoint())
    qtbot.mouseClick(host.pills.pills["period"], Qt.LeftButton, pos=QPoint(14, 11))
    assert cleared == ["time"] and opened == [True]
    host.pills.set_state("2026-10-21", ScheduleOptions())
    assert host.pills.isHidden()
