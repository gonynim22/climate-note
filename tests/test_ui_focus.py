# tests/test_ui_focus.py - 집중 모드 UI/타이머 테스트

from datetime import datetime, timedelta

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QLabel

import database as db
from ui_focus import (
    FOCUS_BUBBLE_DURATION_MS,
    FOCUS_ENCOURAGEMENT_MESSAGES,
    FocusBreakPromptDialog,
    FocusCreateDialog,
    FocusTimer,
    FocusWidgetWindow,
    TOMATO_IMAGE_SIZE,
    TOMATO_MINI_IMAGE_SIZE,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_focus_timer_progress_percent():
    now = datetime(2026, 4, 27, 9, 0, 0)
    timer = FocusTimer("50/10", now_provider=lambda: now)
    timer.start("보고서")

    now = now + timedelta(minutes=18, seconds=30)

    assert timer.progress_percent() == 37
    assert timer.remaining_seconds() == 1890


def test_focus_timer_pause_resume_keeps_elapsed():
    current = datetime(2026, 4, 27, 9, 0, 0)
    timer = FocusTimer("25/5", now_provider=lambda: current)
    timer.start("분석")

    current = current + timedelta(minutes=5)
    timer.pause()
    current = current + timedelta(minutes=10)

    assert timer.elapsed_seconds() == 300

    timer.resume()
    current = current + timedelta(minutes=2)

    assert timer.elapsed_seconds() == 420


def test_focus_timer_break_phase_uses_break_duration():
    current = datetime(2026, 4, 27, 9, 0, 0)
    timer = FocusTimer("25/5", now_provider=lambda: current)
    timer.start_break()

    current = current + timedelta(minutes=2, seconds=30)

    assert timer.phase == "break"
    assert timer.progress_percent() == 50
    assert timer.remaining_seconds() == 150


def test_focus_create_dialog_mode_options(qtbot, qapp):
    dlg = FocusCreateDialog()
    qtbot.addWidget(dlg)

    assert dlg.mode_combo.count() == 3
    assert [dlg.mode_combo.itemData(i) for i in range(dlg.mode_combo.count())] == ["25/5", "50/10", "75/15"]
    assert dlg.mode_combo.itemText(0) == "짧은 집중 (25분 집중/5분 휴식, 포모도로)"
    assert dlg.mode_combo.itemText(1) == "깊은 집중 (50분 집중/10분 휴식)"
    assert dlg.mode_combo.itemText(2) == "몰입 블록 (75분 집중/15분 휴식)"
    button_texts = [button.text() for button in dlg.findChildren(QPushButton)]
    assert "추가만" not in button_texts
    assert "시작" in button_texts


def test_focus_break_prompt_dialog_text(qtbot, qapp):
    dlg = FocusBreakPromptDialog(5)
    qtbot.addWidget(dlg)

    texts = [label.text() for label in dlg.findChildren(QLabel)]
    button_texts = [button.text() for button in dlg.findChildren(QPushButton)]

    assert "집중 모드 완료, 5분 휴식하시겠습니까?" in texts
    assert "휴식 시작" in button_texts
    assert "건너뛰기" in button_texts


def test_focus_widget_ambient_hides_remaining_and_glance_shows(qtbot, app_dir, qapp):
    current = datetime(2026, 4, 27, 9, 0, 0)
    wid = db.create_focus_widget("조용한 집중", "25/5")
    data = next(w for w in db.get_open_focus_widgets() if w["id"] == wid)
    win = FocusWidgetWindow(wid, data)
    qtbot.addWidget(win)
    win.timer_model._now = lambda: current

    assert win._display_mode == "ambient"
    assert win.glance_panel.isHidden()
    assert win.tomato_mini_label.objectName() == "focusTomatoMiniImage"
    assert not win.tomato_mini_label.isHidden()
    assert win.tomato_mini_label.width() == TOMATO_MINI_IMAGE_SIZE
    mini_pixmap = win.tomato_mini_label.pixmap()
    assert mini_pixmap is not None
    assert not mini_pixmap.isNull()
    mini_image = mini_pixmap.toImage()
    assert mini_image.hasAlphaChannel()
    assert mini_image.pixelColor(0, 0).alpha() == 0
    assert not hasattr(win, "control_panel")
    assert "분" not in win.percent_label.text()

    win._start_session()
    win._set_display_mode("glance")

    assert not win.glance_panel.isHidden()
    assert win.tomato_mini_label.isHidden()
    assert win.width() == 241
    assert win.remaining_value.text() == "25:00"
    assert win.mode_value.text() == "짧은 집중"
    assert win.break_value.text() == "09:25 AM"
    assert win.tomato_label.objectName() == "focusTomatoImage"
    assert win.tomato_label.width() == TOMATO_IMAGE_SIZE
    assert win.tomato_label.toolTip() == ""
    tomato_pixmap = win.tomato_label.pixmap()
    assert tomato_pixmap is not None
    assert not tomato_pixmap.isNull()
    tomato_image = tomato_pixmap.toImage()
    assert tomato_image.hasAlphaChannel()
    assert tomato_image.pixelColor(0, 0).alpha() == 0
    assert not hasattr(win, "pin_btn")
    assert not win.close_btn.icon().isNull()
    assert "border-radius: 10px" in win.container.styleSheet()
    assert "stop:0 #FFFFFF" in win.container.styleSheet()
    assert "stop:0.48 #EEF6FF" in win.container.styleSheet()
    assert "stop:1 #DDE8FF" in win.container.styleSheet()


def test_focus_widget_control_mode_is_removed(qtbot, app_dir, qapp):
    wid = db.create_focus_widget("수정창 제거", "25/5")
    data = next(w for w in db.get_open_focus_widgets() if w["id"] == wid)
    win = FocusWidgetWindow(wid, data)
    qtbot.addWidget(win)

    win._set_display_mode("control")

    assert win._display_mode == "ambient"
    assert win.glance_panel.isHidden()
    assert win.width() == 241
    assert win.height() == 78
    assert not hasattr(win, "goal_input")
    assert not hasattr(win, "mode_combo")
    assert not hasattr(win, "start_pause_btn")


def test_focus_widget_glance_omits_duplicate_progress(qtbot, app_dir, qapp):
    wid = db.create_focus_widget("진행률 중복 제거", "25/5")
    data = next(w for w in db.get_open_focus_widgets() if w["id"] == wid)
    win = FocusWidgetWindow(wid, data)
    qtbot.addWidget(win)

    win._set_display_mode("glance")
    label_texts = [label.text() for label in win.glance_panel.findChildren(QLabel)]

    assert win.width() == 241
    assert win.height() == 126
    assert "진행률" not in label_texts
    assert hasattr(win, "tomato_label")
    assert not hasattr(win, "progress_value")


def test_focus_widget_tomato_click_shows_temporary_bubble(qtbot, app_dir, qapp, monkeypatch):
    wid = db.create_focus_widget("토마토 응원", "25/5")
    data = next(w for w in db.get_open_focus_widgets() if w["id"] == wid)
    win = FocusWidgetWindow(wid, data)
    qtbot.addWidget(win)
    monkeypatch.setattr("ui_focus.random.choice", lambda messages: "힘내")

    win._set_display_mode("glance")
    qtbot.mouseClick(win.tomato_label, Qt.LeftButton)

    assert len(FOCUS_ENCOURAGEMENT_MESSAGES) == 22
    assert win.encouragement_bubble.objectName() == "focusEncouragementBubble"
    assert win.encouragement_bubble.testAttribute(Qt.WA_TranslucentBackground)
    assert win.encouragement_bubble.text() == "힘내"
    assert not win.encouragement_bubble.isHidden()
    assert win._bubble_timer.interval() == FOCUS_BUBBLE_DURATION_MS
    assert win._bubble_timer.isActive()

    win._hide_encouragement_bubble()
    assert win.encouragement_bubble.isHidden()


def test_focus_widget_completion_starts_break_when_accepted(qtbot, app_dir, qapp, monkeypatch):
    current = datetime(2026, 4, 27, 9, 0, 0)
    wid = db.create_focus_widget("완료 후 휴식", "25/5")
    data = next(w for w in db.get_open_focus_widgets() if w["id"] == wid)
    win = FocusWidgetWindow(wid, data)
    qtbot.addWidget(win)
    win.timer_model._now = lambda: current
    monkeypatch.setattr(win, "_ask_break", lambda: True)

    win._start_session()
    current = current + timedelta(minutes=25)
    win._on_tick()

    assert win.timer_model.phase == "break"
    assert win.timer_model.status == "running"
    assert win._visual_state == "break"
    assert win.goal_label.text() == "휴식 중"
    assert win.mode_value.text() == "휴식"
    assert win.remaining_value.text() == "05:00"

    session = db.get_focus_sessions()[0]
    assert session["goal"] == "완료 후 휴식"
    assert session["completed"] == 1
    assert session["elapsed_seconds"] == 1500
    assert session["focus_rating"] is None


def test_focus_widget_completion_can_skip_break(qtbot, app_dir, qapp, monkeypatch):
    current = datetime(2026, 4, 27, 9, 0, 0)
    wid = db.create_focus_widget("휴식 건너뛰기", "25/5")
    data = next(w for w in db.get_open_focus_widgets() if w["id"] == wid)
    win = FocusWidgetWindow(wid, data)
    qtbot.addWidget(win)
    win.timer_model._now = lambda: current
    monkeypatch.setattr(win, "_ask_break", lambda: False)

    win._start_session()
    current = current + timedelta(minutes=25)
    win._on_tick()

    assert win.timer_model.phase == "focus"
    assert win.timer_model.status == "ended"
    assert win._visual_state == "complete"
    assert db.get_focus_sessions()[0]["completed"] == 1


def test_focus_widget_end_saves_review(qtbot, app_dir, qapp, monkeypatch):
    wid = db.create_focus_widget("회고 저장", "25/5")
    data = next(w for w in db.get_open_focus_widgets() if w["id"] == wid)
    win = FocusWidgetWindow(wid, data)
    qtbot.addWidget(win)

    monkeypatch.setattr(
        win,
        "_show_review",
        lambda completed: win._save_review(4, "피로", completed),
    )
    win._start_session()
    win._finish_session(completed=False)

    session = db.get_focus_sessions()[0]
    assert session["goal"] == "회고 저장"
    assert session["focus_rating"] == 4
    assert session["distraction"] == "피로"
    assert session["completed"] == 0


def test_focus_widget_load_caps_at_one(app_dir, qtbot, qapp):
    """DB에 집중 위젯이 여러 개 열려 있어도 로드 시 1개만 표시하고 나머지는 닫힘 처리."""
    from ui_main import MainCalendarWindow

    for i in range(3):
        db.create_focus_widget(f"목표{i}", db.DEFAULT_FOCUS_MODE)

    win = MainCalendarWindow()
    qtbot.addWidget(win)

    assert len(win._focus_windows) == 1

    open_rows = db.get_open_focus_widgets()
    assert len(open_rows) == 1
