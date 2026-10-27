"""v4.1 일정 알림 엔진·카드 회귀. 가짜 시계와 합성 데이터만 쓴다."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta

import pytest
from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QApplication
from shiboken6 import VoidPtr, isValid

import database as db
import ui_main
from schedule_rules import AlarmItem, ScheduleOptions
from show_desktop_guard import ShowDesktopKeeper
from ui_main import MainCalendarWindow
from ui_schedule_alarm import ScheduleAlarmCard, ScheduleAlarmScheduler

KEY = db.SETTING_SCHEDULE_ALARM_SEEN_AT


class Clock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value


@pytest.fixture(autouse=True)
def isolated_ui(app_dir, monkeypatch):
    monkeypatch.setattr(ShowDesktopKeeper, "_install_foreground_hook", lambda self: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_apply_topmost", lambda *a, **kw: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_pin_to_desktop_layer", lambda self: False)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    beeps = []
    monkeypatch.setattr(QApplication, "beep", staticmethod(lambda: beeps.append(1)))
    return beeps


def scheduler_with(qtbot, clock):
    host = QObject()  # 창 없이 엔진만 시험한다
    scheduler = ScheduleAlarmScheduler(host, now=clock)
    emitted = []
    scheduler.alarms_ready.connect(lambda items, missed: emitted.append((items, missed)))
    return scheduler, emitted, host


def test_due_alarm_shows_once_and_saves_seen_at(qtbot):
    db.add_schedule("2026-10-15", "부서 회의", options=ScheduleOptions(start_time="15:00", alarm_before=10))
    clock = Clock(datetime(2026, 10, 15, 14, 49, 59))
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    assert emitted == []
    assert db.get_setting(KEY, "") == ""  # 시작만으로는 쓰지 않는다.
    assert 0 < scheduler._timer.remainingTime() <= 1100
    clock.value = datetime(2026, 10, 15, 14, 50, 0, 500000)
    scheduler.check()
    assert [(item.content, missed) for item, missed in
            [(items[0], missed) for items, missed in emitted]] == [("부서 회의", False)]
    assert db.get_setting(KEY, "") == "2026-10-15T14:50:00"
    clock.value += timedelta(seconds=30)
    scheduler.check()
    assert len(emitted) == 1


def test_start_without_key_skips_past_alarms(qtbot):
    db.add_schedule("2026-10-15", "아침 회의", options=ScheduleOptions(start_time="09:00", alarm_before=0))
    scheduler, emitted, _host = scheduler_with(qtbot, Clock(datetime(2026, 10, 15, 14, 0)))
    scheduler.start()
    assert emitted == []
    assert db.get_setting(KEY, "") == ""


def test_missed_alarms_only_from_last_12_hours(qtbot):
    db.add_schedule("2026-10-14", "어젯밤", options=ScheduleOptions(start_time="21:00", alarm_before=0))
    db.add_schedule("2026-10-15", "새벽", options=ScheduleOptions(start_time="06:00", alarm_before=0))
    db.save_setting(KEY, "2026-10-14T20:00:00")
    scheduler, emitted, _host = scheduler_with(qtbot, Clock(datetime(2026, 10, 15, 10, 0)))
    scheduler.start()
    assert [[item.content for item in items] for items, _missed in emitted] == [["새벽"]]
    assert emitted[0][1] is True


@pytest.mark.parametrize("ahead", [timedelta(seconds=1), timedelta(hours=6),
                                   timedelta(hours=12), timedelta(hours=13)])
def test_future_seen_resumes_from_now_without_rewriting_on_start(qtbot, app_dir, ahead):
    db.add_schedule("2026-10-15", "앞으로 울릴 회의",
                    options=ScheduleOptions(start_time="10:01", alarm_before=0))
    clock = Clock(datetime(2026, 10, 15, 10, 0))
    saved = (clock.value + ahead).isoformat(timespec="seconds")
    db.save_setting(KEY, saved)
    before_export = db.export_all_data()
    salt = (app_dir / ".salt").read_bytes()
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    assert scheduler.last_check() == clock.value
    assert db.get_setting(KEY) == saved  # 보정만으로는 DB에 쓰지 않는다.
    assert emitted == []
    clock.value += timedelta(minutes=1, seconds=1)
    scheduler.check()
    assert [[alarm.content for alarm in items] for items, _missed in emitted] == [["앞으로 울릴 회의"]]
    assert db.get_setting(KEY) == "2026-10-15T10:01:01"
    assert db.export_all_data() == before_export
    assert (app_dir / ".salt").read_bytes() == salt
    scheduler.stop()


def test_future_seen_without_alarms_is_not_persisted(qtbot):
    db.save_setting(KEY, "2026-10-15T16:00:00")
    clock = Clock(datetime(2026, 10, 15, 10, 0))
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    assert scheduler.last_check() == clock.value
    scheduler.stop(persist=True)
    assert emitted == []
    assert db.get_setting(KEY) == "2026-10-15T16:00:00"


def test_clock_jumps_do_not_flood_or_repeat(qtbot):
    """Review Focus 3: 시계가 뒤로 가거나 크게 앞으로 뛰어도 중복·아주 오래된 알림이 없다."""
    for hour in range(8, 18):
        db.add_schedule("2026-10-15", f"{hour}시", options=ScheduleOptions(start_time=f"{hour:02d}:00", alarm_before=0))
    clock = Clock(datetime(2026, 10, 15, 8, 30))
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    clock.value = datetime(2026, 10, 15, 9, 0, 1)
    scheduler.check()
    clock.value = datetime(2026, 10, 15, 7, 0)  # 뒤로
    scheduler.check()
    clock.value = datetime(2026, 10, 15, 8, 0, 1)  # 아직 띄우지 않은 알림은 재개한다.
    scheduler.check()
    clock.value = datetime(2026, 10, 15, 9, 30)  # 다시 앞으로: 9시는 이미 띄웠다
    scheduler.check()
    clock.value = datetime(2026, 10, 18, 9, 0)  # 3일 뒤로 점프: 12시간 밖이라 알리지 않는다
    scheduler.check()
    assert [[item.content for item in items] for items, _missed in emitted] == [["9시"], ["8시"]]


def test_snooze_returns_after_five_minutes_unless_deleted(qtbot):
    keep = db.add_schedule("2026-10-15", "유지", options=ScheduleOptions(start_time="15:00", alarm_before=0))
    gone = db.add_schedule("2026-10-15", "삭제", options=ScheduleOptions(start_time="15:00", alarm_before=0))
    clock = Clock(datetime(2026, 10, 15, 14, 59))
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    clock.value = datetime(2026, 10, 15, 15, 0, 1)
    scheduler.check()
    scheduler.snooze(emitted[0][0])
    db.delete_schedule(gone)
    clock.value = datetime(2026, 10, 15, 15, 4)
    scheduler.check()
    assert len(emitted) == 1
    clock.value = datetime(2026, 10, 15, 15, 5, 2)
    scheduler.check()
    assert [item.schedule_id for item in emitted[1][0]] == [keep]


def test_stop_persists_last_check_only_when_alarms_exist(qtbot):
    clock = Clock(datetime(2026, 10, 15, 9, 0))
    scheduler, _emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    scheduler.stop(persist=True)
    assert db.get_setting(KEY, "") == ""
    db.add_schedule("2026-10-20", "알림", options=ScheduleOptions(alarm_before=0))
    scheduler.start()
    clock.value = datetime(2026, 10, 15, 9, 0, 40)
    scheduler.check()
    clock.value = datetime(2026, 10, 15, 9, 1, 10)
    scheduler.stop(persist=True)
    assert db.get_setting(KEY, "") == "2026-10-15T09:00:40"
    assert not scheduler.is_running()


def item(sid, content, *, start_time="15:00", day="2026-10-15", color="#4CC9F0", failed=False):
    return AlarmItem(sid, day, datetime(2026, 10, 15, 14, 50) + timedelta(seconds=sid),
                     content, color, start_time, failed)


def visible_titles(card):
    return [label.text() for label in card.findChildren(ui_main.QLabel, "scheduleAlarmItemTitle")
            if label.isVisibleTo(card)]


def card_window(qtbot):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    win._current_year, win._current_month = 2026, 10
    win._refresh_calendar()
    QApplication.processEvents()
    return win


def test_card_rows_plain_text_lock_and_beep(qtbot, isolated_ui):
    win = card_window(qtbot)
    items = [item(1, "<b>부서 회의</b>"), item(2, "보고서"), item(3, "", failed=True),
             item(4, "종일", start_time="")]
    win._on_schedule_alarms(items, False)
    card = win._alarm_card
    assert card.isVisible() and isinstance(card, ScheduleAlarmCard)
    assert card.title_label.text() == "일정 알림 4건"
    assert visible_titles(card) == ["15:00 <b>부서 회의</b>", "15:00 보고서", "15:00 내용을 읽을 수 없는 일정"]
    assert card.more_label.text() == "외 1건"
    assert card.snooze_button.isVisible()
    assert isolated_ui == [1]
    win._lock()
    QApplication.processEvents()
    assert card.is_locked_view()
    assert visible_titles(card) == []
    assert card.findChild(ui_main.QLabel, "scheduleAlarmLocked").text() == "PIN 잠금 중이라 내용을 숨겼습니다."
    assert not card.snooze_button.isVisible()
    win._unlock()
    QApplication.processEvents()
    assert len(visible_titles(card)) == 3


def test_missed_card_has_only_ok_and_sits_bottom_right(qtbot):
    win = card_window(qtbot)
    win._on_schedule_alarms([item(1, "놓친 회의")], True)
    card = win._alarm_card
    assert not card.snooze_button.isVisible() and card.ok_button.isVisible()
    available = card.screen().availableGeometry()
    frame = card.frame.geometry().translated(card.pos())
    assert abs(frame.right() + 1 - (available.right() + 1 - 12)) <= 1
    assert abs(frame.bottom() + 1 - (available.bottom() + 1 - 12)) <= 1


def test_card_click_opens_date_and_closes(qtbot):
    db.add_schedule("2026-10-20", "회의", options=ScheduleOptions(start_time="15:00", alarm_before=0))
    win = card_window(qtbot)
    win._minimize_to_tray()
    win._on_schedule_alarms([item(1, "회의", day="2026-10-20")], False)
    card = win._alarm_card
    qtbot.mouseClick(card, Qt.LeftButton, pos=card.frame.geometry().center())
    qtbot.waitUntil(lambda: win._alarm_card is None or not isValid(card))
    assert win.isVisible()
    assert win._selected_date == "2026-10-20"


def test_reset_quit_close_card_and_restart_engine(qtbot):
    db.add_schedule("2026-10-20", "알림", options=ScheduleOptions(alarm_before=0))
    win = card_window(qtbot)
    qtbot.waitUntil(lambda: win._schedule_alarm_scheduler.is_running())
    win._on_schedule_alarms([item(1, "회의")], False)
    card = win._alarm_card
    win._discard_data_widgets()
    assert not win._schedule_alarm_scheduler.is_running()
    qtbot.waitUntil(lambda: not isValid(card) or not card.isVisible())
    win._on_import_complete()
    assert win._schedule_alarm_scheduler.is_running()
    win._on_schedule_alarms([item(2, "다시")], False)
    card = win._alarm_card
    assert win.prepare_for_quit()
    assert not win._schedule_alarm_scheduler.is_running()
    qtbot.waitUntil(lambda: not isValid(card) or not card.isVisible())
    assert db.get_setting(KEY, "") != ""


def test_window_without_alarms_leaves_settings_unchanged(qtbot):
    db.add_schedule("2026-10-15", "알림 없는 일정")
    with db._connection() as conn:
        before = [tuple(row) for row in conn.execute("SELECT * FROM app_settings ORDER BY key")]
    win = card_window(qtbot)
    qtbot.waitUntil(lambda: win._schedule_alarm_scheduler.is_running())
    assert win.prepare_for_quit()
    with db._connection() as conn:
        assert [tuple(row) for row in conn.execute("SELECT * FROM app_settings ORDER BY key")] == before


# ─── 1차 수정: 카드 위치·다시 알림·저장 시각·정리 ───────────────────────


def assert_anchored(card):
    """카드 틀의 오른쪽·아래가 작업 영역 안쪽 12px에 닿아 있다."""
    available = card.screen().availableGeometry()
    frame = card.frame.geometry().translated(card.pos())
    assert abs((available.right() + 1) - (frame.right() + 1) - 12) <= 1
    assert abs((available.bottom() + 1) - (frame.bottom() + 1) - 12) <= 1


def test_open_card_stays_anchored_when_rows_change_and_on_lock_unlock(qtbot):
    win = card_window(qtbot)
    win._on_schedule_alarms([item(1, "첫째")], False)
    card = win._alarm_card
    QApplication.processEvents()
    assert_anchored(card)
    heights = [card.height()]
    for more in ([item(2, "둘째"), item(3, "셋째")], [item(4, "넷째")]):
        card.add_items(more, missed=False, locked=False)  # 이미 열려 있는 카드에 줄을 더한다.
        QApplication.processEvents()
        heights.append(card.height())
        assert_anchored(card)
    assert heights[1] > heights[0]  # 줄이 늘어 카드가 실제로 커졌다.
    win._lock()
    QApplication.processEvents()
    assert card.is_locked_view()
    assert_anchored(card)
    assert card.height() < heights[-1]
    win._unlock()
    QApplication.processEvents()
    assert not card.is_locked_view()
    assert_anchored(card)
    assert card.height() == heights[-1]


def test_snoozed_refire_is_not_missed_and_can_be_snoozed_again(qtbot):
    db.add_schedule("2026-10-15", "유지", options=ScheduleOptions(start_time="15:00", alarm_before=0))
    clock = Clock(datetime(2026, 10, 15, 14, 59))
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    clock.value = datetime(2026, 10, 15, 15, 0, 1)
    scheduler.check()
    assert emitted[0][1] is False
    for count in (2, 3):  # 5분 뒤 다시를 두 번 이어서 눌러도 계속 돌아온다.
        scheduler.snooze(emitted[-1][0])
        clock.value += timedelta(minutes=5, seconds=2)
        scheduler.check()
        assert len(emitted) == count
        assert emitted[-1][1] is False
        card = ScheduleAlarmCard()
        card.add_items(emitted[-1][0], missed=emitted[-1][1], locked=False)
        card.show_at(QApplication.primaryScreen())
        assert card.snooze_button.isVisibleTo(card)
        card.close()


def test_clock_correction_preserves_snooze_and_persists_corrected_seen(qtbot):
    db.add_schedule("2026-10-15", "회의", options=ScheduleOptions(start_time="15:00", alarm_before=0))
    clock = Clock(datetime(2026, 10, 15, 14, 59))
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    clock.value = datetime(2026, 10, 15, 15, 0, 1)
    scheduler.check()
    assert db.get_setting(KEY, "") == "2026-10-15T15:00:01"
    clock.value = datetime(2026, 10, 15, 14, 0, 0)  # 1시간 뒤로
    scheduler.check()
    assert scheduler.last_check() == clock.value
    assert db.get_setting(KEY, "") == "2026-10-15T15:00:01"  # 보정만으로는 쓰지 않는다.
    scheduler.snooze(emitted[0][0])
    clock.value = datetime(2026, 10, 15, 14, 5, 1)
    scheduler.check()
    assert len(emitted) == 2  # 명시적으로 요청한 다시 알림은 유지한다.
    assert db.get_setting(KEY, "") == "2026-10-15T14:05:01"
    clock.value = datetime(2026, 10, 15, 15, 0, 2)
    scheduler.check()
    assert len(emitted) == 2  # 원래 시각을 다시 지나도 같은 실행의 알림은 중복하지 않는다.


def test_clock_correction_is_saved_on_normal_quit_with_alarms(qtbot):
    db.add_schedule("2026-10-20", "다음 회의", options=ScheduleOptions(alarm_before=0))
    db.save_setting(KEY, "2026-10-15T16:00:00")
    clock = Clock(datetime(2026, 10, 15, 10, 0))
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    clock.value += timedelta(seconds=30)
    scheduler.check()
    scheduler.stop(persist=True)
    assert emitted == []
    assert db.get_setting(KEY) == "2026-10-15T10:00:30"


def test_clock_correction_after_restart_can_repeat_prior_execution_alarm(qtbot):
    db.add_schedule("2026-10-15", "회의", options=ScheduleOptions(start_time="15:00", alarm_before=0))
    clock = Clock(datetime(2026, 10, 15, 14, 59))
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    clock.value = datetime(2026, 10, 15, 15, 0, 1)
    scheduler.check()
    scheduler.stop(persist=True)
    clock.value = datetime(2026, 10, 15, 14, 59)
    restarted, repeated, _new_host = scheduler_with(qtbot, clock)
    restarted.start()
    assert repeated == []
    clock.value = datetime(2026, 10, 15, 15, 0, 1)
    restarted.check()
    assert len(emitted) == len(repeated) == 1  # 표시 키는 메모리 전용인 기존 계약.
    restarted.stop()


@pytest.mark.parametrize("value", ["2026-10-15T09:00:00+09:00", "2026-10-15T00:00:00Z", "읽을 수 없는 값"])
def test_seen_value_with_timezone_or_garbage_is_ignored(qtbot, value):
    db.add_schedule("2026-10-15", "아침", options=ScheduleOptions(start_time="09:00", alarm_before=0))
    db.save_setting(KEY, value)
    clock = Clock(datetime(2026, 10, 15, 14, 0))
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    assert scheduler.is_running()  # 비교할 수 없는 값 때문에 엔진이 멈춰 버리지 않는다.
    assert scheduler.last_check() == clock.value  # 키가 없는 것처럼 지금부터 센다.
    assert emitted == []


def test_fired_keys_are_pruned_after_window_and_cleared_on_stop(qtbot):
    db.add_schedule("2026-10-15", "회의", options=ScheduleOptions(start_time="15:00", alarm_before=0))
    clock = Clock(datetime(2026, 10, 15, 14, 59))
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    clock.value = datetime(2026, 10, 15, 15, 0, 1)
    scheduler.check()
    assert len(emitted) == 1 and len(scheduler._fired) == 1
    clock.value = datetime(2026, 10, 15, 20, 0)
    scheduler.check()
    assert len(scheduler._fired) == 1  # 12시간 안에서는 남겨 중복을 막는다.
    clock.value = datetime(2026, 10, 16, 4, 0)
    scheduler.check()
    assert not scheduler._fired  # 확인 창(12시간)을 벗어난 키는 지운다.
    db.add_schedule("2026-10-16", "새 회의", options=ScheduleOptions(start_time="04:02", alarm_before=0))
    clock.value = datetime(2026, 10, 16, 4, 2, 1)
    scheduler.check()
    assert len(scheduler._fired) == 1
    scheduler.stop()
    assert not scheduler._fired  # 초기화 뒤에는 일정 번호가 다시 시작하므로 비운다.


def test_check_rearms_timer_even_when_it_raises(qtbot, monkeypatch):
    clock = Clock(datetime(2026, 10, 15, 9, 0))
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    scheduler._timer.stop()
    clock.value = datetime(2026, 10, 15, 9, 0, 30)

    def boom(after, until):
        raise RuntimeError("합성 오류")

    original = db.get_alarm_occurrences
    monkeypatch.setattr(db, "get_alarm_occurrences", boom)
    with pytest.raises(RuntimeError):  # 오류는 삼키지 않고 그대로 올라온다.
        scheduler.check()
    assert scheduler.is_running()
    assert scheduler._timer.isActive() and scheduler._timer.remainingTime() > 0
    monkeypatch.setattr(db, "get_alarm_occurrences", original)
    db.add_schedule("2026-10-15", "회복", options=ScheduleOptions(start_time="09:02", alarm_before=0))
    clock.value = datetime(2026, 10, 15, 9, 2, 1)
    scheduler.check()
    assert [[i.content for i in items] for items, _missed in emitted] == [["회복"]]


def test_locked_header_always_shows_count_and_snooze_is_ignored(qtbot):
    card = ScheduleAlarmCard()
    requested = []
    card.snooze_requested.connect(requested.append)
    card.add_items([item(1, "비밀")], missed=False, locked=True)
    card.show_at(QApplication.primaryScreen())
    assert card.title_label.text() == "일정 알림 1건"  # 잠금 중에는 한 건이어도 건수를 보인다.
    card._snooze()
    assert requested == [] and card.isVisible()  # 잠금 중에는 다시 알림을 보내지 않는다.
    card.set_locked(False)
    assert card.title_label.text() == "일정 알림"
    card._snooze()
    assert len(requested) == 1


def test_resume_decides_privacy_lock_before_building_card(qtbot, monkeypatch):
    db.add_schedule("2026-10-15", "비밀 회의", options=ScheduleOptions(start_time="15:00", alarm_before=0))
    db.save_setting(db.SETTING_USE_PRIVACY_LOCK, "1")
    win = card_window(qtbot)
    scheduler = win._schedule_alarm_scheduler
    scheduler.stop()
    clock = Clock(datetime(2026, 10, 15, 14, 30))
    scheduler._now = clock
    scheduler.start()
    clock.value = datetime(2026, 10, 15, 15, 1)  # 절전 중에 알림 시각이 지났다.
    built = []
    original = ScheduleAlarmCard.add_items

    def spy(self, items, *, missed, locked, now=None):
        built.append(locked)
        return original(self, items, missed=missed, locked=locked, now=now)

    monkeypatch.setattr(ScheduleAlarmCard, "add_items", spy)
    msg = wintypes.MSG()
    msg.message = ui_main.WM_POWERBROADCAST
    msg.wParam = ui_main.PBT_APMRESUMESUSPEND
    win.nativeEvent(b"windows_generic_MSG", VoidPtr(ctypes.addressof(msg)))
    assert built == [True]  # 카드는 처음부터 잠금 모양으로 만들어진다.
    assert win._is_locked and win._alarm_card.is_locked_view()


def test_snoozed_refire_shows_text_edited_during_snooze(qtbot):
    """M6: 다시 알림은 저장된 최신 본문·색으로 돌아온다. 이 날만 지운 일정은 돌아오지 않는다."""
    edited = db.add_schedule("2026-10-15", "옛 본문", "#FFD166",
                             options=ScheduleOptions(start_time="15:00", alarm_before=0))
    series = db.add_schedule("2026-10-05", "주간 회의", options=ScheduleOptions(
        start_time="15:00", repeat_rule="weekly", alarm_before=0))
    clock = Clock(datetime(2026, 10, 12, 14, 59))
    scheduler, emitted, _host = scheduler_with(qtbot, clock)
    scheduler.start()
    clock.value = datetime(2026, 10, 12, 15, 0, 1)
    scheduler.check()
    assert [item.content for item in emitted[0][0]] == ["주간 회의"]
    scheduler.snooze(emitted[0][0])
    db.skip_schedule_occurrence(series, "2026-10-12")
    clock.value = datetime(2026, 10, 12, 15, 5, 2)
    scheduler.check()
    assert len(emitted) == 1  # 이 날만 지운 일정은 다시 울리지 않는다.

    clock.value = datetime(2026, 10, 15, 14, 59)
    scheduler.stop()
    scheduler.start()
    clock.value = datetime(2026, 10, 15, 15, 0, 1)
    scheduler.check()
    assert [item.content for item in emitted[-1][0]] == ["옛 본문"]
    scheduler.snooze(emitted[-1][0])
    db.update_schedule(edited, content="새 본문", color="#FF6B6B")
    clock.value += timedelta(minutes=5, seconds=2)
    scheduler.check()
    assert [(item.content, item.color) for item in emitted[-1][0]] == [("새 본문", "#FF6B6B")]
    assert emitted[-1][1] is False


def test_card_stripe_uses_users_display_palette_read_once(qtbot, monkeypatch):
    """M1: 카드 왼쪽 띠는 저장된 슬롯 색이 아니라 사용자가 고른 표시색이다."""
    db.save_schedule_palette(("#80CFA9", "#FF9F68", "#8FA8FF"))
    reads = []
    real_palette = db.get_schedule_palette
    monkeypatch.setattr(db, "get_schedule_palette", lambda: reads.append(1) or real_palette())
    win = card_window(qtbot)
    reads.clear()
    win._on_schedule_alarms([item(1, "첫째", color="#FFD166"), item(2, "둘째", color="#4CC9F0"),
                             item(3, "셋째", color="#123456")], False)
    card = win._alarm_card
    assert len(reads) == 1
    assert "border-left:4px solid #80CFA9" in card.frame.styleSheet()
    assert "#FFD166" not in card.frame.styleSheet()
    assert [i.color for i in card.items()] == ["#80CFA9", "#FF9F68", "#123456"]  # 팔레트 밖 색은 그대로
