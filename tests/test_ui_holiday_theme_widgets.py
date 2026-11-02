"""v4.6 공휴일 테마: D-Day·스티키 표시 전용 색(Task 4).

떠 있는 창과 크게 보기 패널(미니 카드)이 테마 색을 입는지, 그리고 그것이 화면에만 있고
DB·본문·저장색을 건드리지 않는지 확인한다. 모든 검사는 합성 데이터(app_dir)에서 한다.
"""
import re
from datetime import date

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

import database as db
import holiday_theme as ht
from holiday_theme import THEMES
from holidays import KOREAN_HOLIDAYS
from ui_dday import DDayWidgetWindow
from ui_dday_panel import DDayMiniCard, DDaySidePanel
from ui_holiday_decor import DecorationLayer
from ui_main import MainCalendarWindow
from ui_sticky import StickyNoteWindow
from ui_sticky_panel import StickyMiniCard, StickySidePanel


@pytest.fixture(autouse=True)
def quiet_desktop(app_dir):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")


def _writer_names():
    return [
        name for name in dir(db)
        if name.startswith(("save_", "update_", "create_", "add_", "delete_", "trash_",
                            "restore_", "import_", "reset_", "backup_"))
        and callable(getattr(db, name))
    ]


def _forbid_db_writes(monkeypatch):
    """database의 쓰기 함수를 전부 예외로 바꾼다. 테마가 저장을 시도하면 바로 실패한다."""
    def boom(*args, **kwargs):
        raise AssertionError("공휴일 테마가 DB에 쓰려 했다")

    for name in _writer_names():
        monkeypatch.setattr(db, name, boom)


def _stop_pending_saves(*widgets):
    """디바운스 저장 타이머(`_resize_timer`·`_save_timer`)를 멈춘다. 저장 자체는 이 시험의 대상이 아니다."""
    for widget in widgets:
        for name in ("_resize_timer", "_save_timer"):
            timer = getattr(widget, name, None)
            if timer is not None:
                timer.stop()


def _dday_data(**over):
    data = {"name": "마감", "target_date": "2030-01-01",
            "color": "#46679C", "x_pos": 100, "y_pos": 100}
    data.update(over)
    return data


def _sticky_data(content="", color=db.DEFAULT_STICKY_COLOR):
    return {"content": content, "x_pos": 100, "y_pos": 100,
            "width": 300, "height": 400, "color": color}


def _sticky(qtbot, content="", color=db.DEFAULT_STICKY_COLOR):
    note_id = db.create_sticky_note(note_type="memo", x=100, y=100, color=color)
    win = StickyNoteWindow(note_id, _sticky_data(content, color))
    qtbot.addWidget(win)
    return win


def _opaque_colors(icon, size):
    image = icon.pixmap(size, size).toImage().convertToFormat(QImage.Format_ARGB32)
    colors = []
    for y in range(image.height()):
        for x in range(image.width()):
            color = QColor.fromRgba(image.pixel(x, y))
            if color.alpha() >= 200:
                colors.append(color)
    return colors


def _close(color, hex_color, tol=3):
    want = QColor(hex_color)
    return (abs(color.red() - want.red()) <= tol and abs(color.green() - want.green()) <= tol
            and abs(color.blue() - want.blue()) <= tol)


# ── D-Day 떠 있는 창 ─────────────────────────────────────────────────

def test_dday_theme_is_display_only(app_dir, qtbot, monkeypatch):
    win = DDayWidgetWindow(1, _dday_data())
    qtbot.addWidget(win)
    assert "#46679C" in win.container.styleSheet()

    _forbid_db_writes(monkeypatch)
    win.set_holiday_theme(THEMES["christmas"])
    assert "#1D4A3A" in win.container.styleSheet()
    assert "#46679C" not in win.container.styleSheet()
    # 헤어라인과 둥근 모서리 같은 모양은 그대로다.
    assert "border-radius:18px" in win.container.styleSheet().replace(" ", "")

    win.set_holiday_theme(None)
    assert "#46679C" in win.container.styleSheet()
    assert "#1D4A3A" not in win.container.styleSheet()


def test_dday_color_change_during_theme_saves_and_restores_new_color(app_dir, qtbot):
    widget_id = db.create_dday_widget("마감", "2030-01-01", color="#46679C")
    data = next(w for w in db.get_open_dday_widgets() if w["id"] == widget_id)
    win = DDayWidgetWindow(widget_id, data)
    qtbot.addWidget(win)

    win.set_holiday_theme(THEMES["christmas"])
    win._apply_color("#FFFA8E", save=True)

    saved = next(w for w in db.get_open_dday_widgets() if w["id"] == widget_id)
    assert saved["color"] == "#FFFA8E"            # 사용자가 고른 색은 저장된다
    assert "#1D4A3A" in win.container.styleSheet()  # 화면은 아직 테마 색이다
    assert "#A8801F" not in win.container.styleSheet()

    win.set_holiday_theme(None)
    assert "#A8801F" in win.container.styleSheet()  # 테마가 끝나면 새로 저장한 색
    assert "#1D4A3A" not in win.container.styleSheet()


def test_dday_window_created_after_theme_start_default_is_untouched(app_dir, qtbot):
    win = DDayWidgetWindow(1, _dday_data(color="#B25C8B"))
    qtbot.addWidget(win)
    assert "#B25C8B" in win.container.styleSheet()


def test_dday_mini_card_theme_is_display_only(app_dir, qtbot, monkeypatch):
    widget_id = db.create_dday_widget("마감", "2030-01-01", color="#2E8F6E")
    data = next(w for w in db.get_open_dday_widgets() if w["id"] == widget_id)
    card = DDayMiniCard(widget_id, data)
    qtbot.addWidget(card)
    assert "#2E8F6E" in card.styleSheet()

    _forbid_db_writes(monkeypatch)
    card.set_holiday_theme(THEMES["seollal"])
    assert "#5A1F3A" in card.styleSheet()
    assert "#2E8F6E" not in card.styleSheet()
    assert "border-radius:12px" in card.styleSheet().replace(" ", "")
    card.set_holiday_theme(None)
    assert "#2E8F6E" in card.styleSheet()


# ── 스티키 떠 있는 창 ────────────────────────────────────────────────

def test_sticky_theme_is_display_only(app_dir, qtbot, monkeypatch):
    win = _sticky(qtbot, content="<p>회의 준비</p>")
    body_before = win.container.styleSheet()
    header_before = win.header_widget.styleSheet()
    html_before = win.text_edit.toHtml()

    _forbid_db_writes(monkeypatch)
    win.set_holiday_theme(THEMES["christmas"])
    assert "#DCEBDD" in win.header_widget.styleSheet()
    assert win.container.styleSheet() == body_before      # 본문 바탕·테두리 그대로
    assert win.text_edit.toHtml() == html_before          # 본문 HTML 그대로
    assert not win.text_edit.document().isModified()      # 저장할 변경도 만들지 않는다

    win.set_holiday_theme(None)
    assert win.header_widget.styleSheet() == header_before
    assert win.container.styleSheet() == body_before
    assert win.text_edit.toHtml() == html_before


def test_sticky_color_change_during_theme_saves_and_restores_new_color(app_dir, qtbot):
    win = _sticky(qtbot)
    win.set_holiday_theme(THEMES["christmas"])
    win._apply_color("#D0FFF1", save=True)

    saved = next(n for n in db.get_open_sticky_notes() if n["id"] == win.note_id)
    assert saved["color"] == "#D0FFF1"
    assert "rgba(208, 255, 241, 255)" in win.container.styleSheet()  # 본문은 새 색
    assert "#DCEBDD" in win.header_widget.styleSheet()                 # 띠는 아직 테마
    assert "rgba(168, 240, 220, 255)" not in win.header_widget.styleSheet()

    win.set_holiday_theme(None)
    assert "rgba(168, 240, 220, 255)" in win.header_widget.styleSheet()  # 민트 머리색
    assert "#DCEBDD" not in win.header_widget.styleSheet()


def test_seollal_band_uses_five_stripes(app_dir, qtbot):
    win = _sticky(qtbot)
    win.show()
    qtbot.waitExposed(win)
    win.set_holiday_theme(THEMES["seollal"])
    qss = win.header_widget.styleSheet()
    assert "qlineargradient" in qss
    for color in THEMES["seollal"].band_stripes:
        assert color in qss

    # 멈춤점은 1/5 단위다(줄 경계마다 같은 위치에서 아주 조금 어긋나게 쌍으로 둔다).
    positions = [float(v) for v in re.findall(r"stop:([0-9.]+)", qss)]
    assert len(positions) == 10
    for boundary, (end, start) in zip((0.2, 0.4, 0.6, 0.8),
                                      zip(positions[1:9:2], positions[2:9:2])):
        assert end == pytest.approx(boundary, abs=1e-4)
        assert start == pytest.approx(boundary, abs=1e-4) and start > end

    # 띠 높이 전체를 다섯 줄이 같은 두께로 나눠 갖고 경계는 단단하다(빈 곳 x=200을 읽는다).
    image = win.header_widget.grab().toImage().convertToFormat(QImage.Format_ARGB32)
    height = image.height()
    x = 200
    for index, color in enumerate(THEMES["seollal"].band_stripes):
        top, bottom = index * height / 5, (index + 1) * height / 5
        for y in (int(top) + 1, int((top + bottom) / 2), int(bottom) - 2):
            assert _close(QColor.fromRgba(image.pixel(x, y)), color), (index, y)


def test_plain_band_is_a_single_color(app_dir, qtbot):
    win = _sticky(qtbot)
    win.show()
    qtbot.waitExposed(win)
    win.set_holiday_theme(THEMES["christmas"])
    assert "qlineargradient" not in win.header_widget.styleSheet()
    # 띠 바탕만 본다: 위에 겹치는 장식 레이어(눈 쌓인 톱니·솔가지)는 숨기고 그린다.
    for layer in win.header_widget.findChildren(DecorationLayer):
        layer.hide()
    image = win.header_widget.grab().toImage().convertToFormat(QImage.Format_ARGB32)
    for y in (3, 20, image.height() - 4):
        assert _close(QColor.fromRgba(image.pixel(200, y)), "#DCEBDD"), y


def test_sticky_icons_use_band_icon_color(app_dir, qtbot):
    win = _sticky(qtbot)
    default_link = _opaque_colors(win.link_btn.icon(), 24)
    assert default_link and not all(_close(c, "#FFFFFF", 20) for c in default_link)

    win.set_holiday_theme(THEMES["chuseok"])   # 추석 band_icon은 흰색
    for button, size in ((win.link_btn, 24), (win.close_btn, 16)):
        colors = _opaque_colors(button.icon(), size)
        assert colors, button
        assert all(_close(c, "#FFFFFF", 20) for c in colors), button
    # 글자 버튼(B, ✓, A)도 같은 색이다.
    for button in (win.bold_btn, win.todo_btn, win.text_color_btn):
        assert "#FFFFFF" in button.styleSheet().upper()

    win.set_holiday_theme(None)
    restored = _opaque_colors(win.link_btn.icon(), 24)
    assert restored and not all(_close(c, "#FFFFFF", 20) for c in restored)
    for button in (win.bold_btn, win.todo_btn, win.text_color_btn):
        assert "#FFFFFF" not in button.styleSheet().upper()


def test_sticky_icon_color_follows_each_theme(app_dir, qtbot):
    """밝은 띠(성탄)의 아이콘은 그 테마의 band_icon 색이다."""
    win = _sticky(qtbot)
    win.set_holiday_theme(THEMES["christmas"])
    colors = _opaque_colors(win.link_btn.icon(), 24)
    assert colors and all(_close(c, THEMES["christmas"].band_icon, 20) for c in colors)


# ── 크게 보기 패널 ───────────────────────────────────────────────────

def test_side_panels_apply_and_keep_theme_after_reload(app_dir, qtbot):
    db.create_dday_widget("마감", "2030-01-01", color="#46679C")
    db.create_dday_widget("시험", "2030-02-01", color="#2E8F6E")
    db.create_sticky_note("memo")
    db.create_sticky_note("memo")

    dday_panel = DDaySidePanel()
    qtbot.addWidget(dday_panel)
    dday_panel.set_holiday_theme(THEMES["christmas"])
    dday_panel.reload()
    assert len(dday_panel._cards) == 2
    assert all("#1D4A3A" in card.styleSheet() for card in dday_panel._cards)
    dday_panel.reload()  # 다시 만든 카드도 테마 색
    assert all("#1D4A3A" in card.styleSheet() for card in dday_panel._cards)

    sticky_panel = StickySidePanel()
    qtbot.addWidget(sticky_panel)
    sticky_panel.set_holiday_theme(THEMES["christmas"])
    sticky_panel.reload()
    assert len(sticky_panel._cards) == 2
    assert all("#DCEBDD" in card._strip.styleSheet() for card in sticky_panel._cards)
    sticky_panel.reload()
    assert all("#DCEBDD" in card._strip.styleSheet() for card in sticky_panel._cards)

    # 테마가 끝나면 카드가 저장색으로 돌아온다.
    dday_panel.set_holiday_theme(None)
    assert ["#46679C" in dday_panel._cards[0].styleSheet(),
            "#2E8F6E" in dday_panel._cards[1].styleSheet()] == [True, True]
    sticky_panel.set_holiday_theme(None)
    assert all("#F8F26F" in card._strip.styleSheet() for card in sticky_panel._cards)


def test_sticky_mini_card_changes_only_strip(app_dir, qtbot, monkeypatch):
    note_id = db.create_sticky_note("memo")
    card = StickyMiniCard(note_id, "<p>본문</p>", db.DEFAULT_STICKY_COLOR)
    qtbot.addWidget(card)
    body_before = card.styleSheet()
    html_before = card.text_edit.toHtml()
    strip_before = card._strip.styleSheet()

    _forbid_db_writes(monkeypatch)
    card.set_holiday_theme(THEMES["liberation"])
    assert "#FBE3EA" in card._strip.styleSheet()
    assert card.styleSheet() == body_before
    assert card.text_edit.toHtml() == html_before
    assert not card.text_edit.document().isModified()

    card.set_holiday_theme(None)
    assert card._strip.styleSheet() == strip_before


def test_mini_card_color_change_during_theme_saves_and_restores(app_dir, qtbot):
    note_id = db.create_sticky_note("memo")
    card = StickyMiniCard(note_id, "", db.DEFAULT_STICKY_COLOR)
    qtbot.addWidget(card)
    card.set_holiday_theme(THEMES["christmas"])
    card.apply_color("#D0FFF1")

    saved = next(n for n in db.get_open_sticky_notes() if n["id"] == note_id)
    assert saved["color"] == "#D0FFF1"
    assert "#DCEBDD" in card._strip.styleSheet()
    card.set_holiday_theme(None)
    assert "#A8F0DC" in card._strip.styleSheet()


# ── 메인 창 연결 ─────────────────────────────────────────────────────

def _patch_only(monkeypatch, day):
    fixed = ht.resolve_holiday_theme(date.fromisoformat(day), KOREAN_HOLIDAYS)
    monkeypatch.setattr(ht, "current_match", lambda today=None: fixed)
    return fixed


def _at(monkeypatch, win, day):
    _patch_only(monkeypatch, day)
    win._holiday_theme.refresh()
    QApplication.processEvents()


@pytest.fixture
def win(qtbot, app_dir):
    w = MainCalendarWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


def test_new_floating_widgets_get_current_theme(monkeypatch, win):
    _at(monkeypatch, win, "2026-12-25")

    win._on_new_sticky_note()
    new_id = max(win._sticky_windows)
    assert "#DCEBDD" in win._sticky_windows[new_id].header_widget.styleSheet()

    note_id = db.create_sticky_note("memo")
    db.trash_sticky_note(note_id)
    win._restore_sticky_note(note_id)
    assert "#DCEBDD" in win._sticky_windows[note_id].header_widget.styleSheet()

    widget_id = db.create_dday_widget("마감", "2030-01-01", color="#46679C")
    win._load_open_dday_widgets()
    dday = win._dday_windows[widget_id]
    assert "#1D4A3A" in dday.container.styleSheet()
    QApplication.processEvents()  # 예약된 표시가 지나도 테마는 그대로다
    assert "#1D4A3A" in dday.container.styleSheet()

    # 가져오기 뒤 창을 다시 만드는 경로(_load_open_sticky_notes)도 같다.
    extra_id = db.create_sticky_note("memo")
    win._load_open_sticky_notes()
    assert "#DCEBDD" in win._sticky_windows[extra_id].header_widget.styleSheet()


def test_show_floating_widget_dresses_with_current_theme(monkeypatch, win):
    """보이기 직전에도 현재 테마로 맞춘다(예약된 표시가 늦게 와도 같은 색)."""
    note_id = db.create_sticky_note("memo")
    widget_id = db.create_dday_widget("마감", "2030-01-01", color="#46679C")
    win._load_open_sticky_notes()
    win._load_open_dday_widgets()
    _at(monkeypatch, win, "2026-12-25")
    sticky = win._sticky_windows[note_id]
    dday = win._dday_windows[widget_id]

    sticky.set_holiday_theme(None)   # 어떤 이유로 테마가 빠진 창
    dday.set_holiday_theme(None)
    win._show_floating_widget(sticky)
    win._show_floating_widget(dday)
    assert "#DCEBDD" in sticky.header_widget.styleSheet()
    assert "#1D4A3A" in dday.container.styleSheet()


def test_theme_change_reaches_existing_windows_and_panels(monkeypatch, win):
    note_id = db.create_sticky_note("memo")
    widget_id = db.create_dday_widget("마감", "2030-01-01", color="#46679C")
    win._load_open_sticky_notes()
    win._load_open_dday_widgets()
    sticky = win._sticky_windows[note_id]
    dday = win._dday_windows[widget_id]
    assert "#1D4A3A" not in dday.container.styleSheet()

    _at(monkeypatch, win, "2026-12-25")
    assert "#1D4A3A" in dday.container.styleSheet()
    assert "#DCEBDD" in sticky.header_widget.styleSheet()

    _at(monkeypatch, win, "2027-01-01")   # 신정: 다른 테마로 바뀐다
    assert "#24315E" in dday.container.styleSheet()
    assert "#FBDDBF" in sticky.header_widget.styleSheet()

    # 설정 스위치를 끄면 저장색으로 돌아온다.
    db.save_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "0")
    win._holiday_theme.refresh()
    assert "#46679C" in dday.container.styleSheet()
    assert "#FBDDBF" not in sticky.header_widget.styleSheet()


def test_large_mode_panels_get_theme_and_hidden_windows_keep_it(monkeypatch, win):
    note_id = db.create_sticky_note("memo")
    widget_id = db.create_dday_widget("마감", "2030-01-01", color="#46679C")
    win._load_open_sticky_notes()
    win._load_open_dday_widgets()
    _at(monkeypatch, win, "2026-12-25")

    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    assert win._apply_calendar_scale()
    QApplication.processEvents()
    assert win._sticky_side_panel is not None and win._dday_side_panel is not None
    assert win._sticky_side_panel._cards
    assert all("#DCEBDD" in c._strip.styleSheet() for c in win._sticky_side_panel._cards)
    assert win._dday_side_panel._cards
    assert all("#1D4A3A" in c.styleSheet() for c in win._dday_side_panel._cards)

    # 패널 모드에서 새로 생긴 창(화면에는 안 보임)도 테마를 입고 있어, 돌아가면 그대로 보인다.
    win._on_new_sticky_note()
    new_id = max(win._sticky_windows)
    assert "#DCEBDD" in win._sticky_windows[new_id].header_widget.styleSheet()
    other_dday = db.create_dday_widget("시험", "2030-02-01", color="#2E8F6E")
    win._load_open_dday_widgets()
    assert "#1D4A3A" in win._dday_windows[other_dday].container.styleSheet()
    assert all("#DCEBDD" in c._strip.styleSheet() for c in win._sticky_side_panel._cards)

    # 테마가 끝나면 패널 카드도 저장색이다.
    db.save_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "0")
    win._holiday_theme.refresh()
    assert all("#DCEBDD" not in c._strip.styleSheet() for c in win._sticky_side_panel._cards)
    assert all("#1D4A3A" not in c.styleSheet() for c in win._dday_side_panel._cards)
    assert note_id in win._sticky_windows and widget_id in win._dday_windows


def test_widget_theme_apply_writes_nothing(monkeypatch, win):
    note_id = db.create_sticky_note("memo")
    widget_id = db.create_dday_widget("마감", "2030-01-01", color="#46679C")
    win._load_open_sticky_notes()
    win._load_open_dday_widgets()
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    assert win._apply_calendar_scale()
    sticky = win._sticky_windows[note_id]
    dday = win._dday_windows[widget_id]
    before = (sticky.container.styleSheet(), sticky.text_edit.toHtml())
    # 창을 만들고 크기를 맞추며 시작된 디바운스 저장(크기 500ms·본문)은 테마와 무관하다. PC가 느려
    # 이 구간 안에 만료되면 테마가 쓴 것으로 오인하므로 미리 멈춘다.
    _stop_pending_saves(sticky, dday)

    with monkeypatch.context() as scoped:
        _forbid_db_writes(scoped)
        for day in ("2026-12-21", "2026-12-25", "2027-01-01", "2027-02-07", "2026-12-21"):
            _at(scoped, win, day)
            _stop_pending_saves(sticky, dday)
        win._holiday_theme.set_paused(True)
        win._holiday_theme.set_paused(False)

    assert (sticky.container.styleSheet(), sticky.text_edit.toHtml()) == before
    saved_dday = next(w for w in db.get_open_dday_widgets() if w["id"] == widget_id)
    assert saved_dday["color"] == "#46679C"
    assert "#46679C" in dday.container.styleSheet()
