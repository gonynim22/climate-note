# tests/test_ui_sticky_panel.py - '크게' 모드 미니 스티키 패널 테스트

import sqlite3

import pytest
from PySide6.QtWidgets import QApplication

import database as db


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_sticky_mini_card_saves_content(app_dir, qtbot, qapp):
    """미니 카드 본문 편집 후 save() 시 DB(암호화)에 반영된다."""
    from ui_sticky_panel import StickyMiniCard

    nid = db.create_sticky_note("memo")
    card = StickyMiniCard(nid, "", db.DEFAULT_STICKY_COLOR)
    qtbot.addWidget(card)

    card.text_edit.setPlainText("회의 준비")
    card.save()

    notes = {n["id"]: n for n in db.get_open_sticky_notes()}
    assert "회의 준비" in notes[nid]["content"]


def test_decryption_failed_mini_card_refuses_save(app_dir, qtbot, qapp):
    from ui_sticky_panel import StickyMiniCard

    note_id = db.create_sticky_note("memo")
    db.update_sticky_note(note_id, content="패널 원본")
    card = StickyMiniCard(
        note_id, "", db.DEFAULT_STICKY_COLOR,
        decryption_failed=True,
    )
    qtbot.addWidget(card)

    assert card.save() is False
    note = next(n for n in db.get_open_sticky_notes() if n["id"] == note_id)
    assert "패널 원본" in note["content"]


def test_sticky_side_panel_save_all_reports_failure(
        app_dir, qtbot, qapp, monkeypatch):
    """종료 게이트가 미니 카드 저장 실패를 감지할 수 있어야 한다."""
    from ui_sticky_panel import StickySidePanel

    db.create_sticky_note("memo")
    db.create_sticky_note("memo")
    panel = StickySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    monkeypatch.setattr(panel._cards[0], "save", lambda: False)
    later_saves = []
    monkeypatch.setattr(
        panel._cards[1], "save", lambda: later_saves.append(True) or True
    )

    assert panel.save_all() is False
    assert later_saves == [True]


def test_sticky_mini_card_save_failure_rearms_retry_timer(
        app_dir, qtbot, qapp, monkeypatch):
    """미니 카드의 종료 저장 실패도 자동 저장 재시도로 이어진다."""
    from ui_sticky_panel import StickyMiniCard

    note_id = db.create_sticky_note("memo")
    card = StickyMiniCard(note_id, "", db.DEFAULT_STICKY_COLOR)
    qtbot.addWidget(card)
    card.text_edit.setPlainText("재시도할 패널 내용")

    def _fail_update(*_args, **_kwargs):
        raise sqlite3.OperationalError("simulated save failure")

    monkeypatch.setattr(db, "update_sticky_note", _fail_update)

    assert card.save() is False
    assert card._save_timer.isActive()


def test_sticky_side_panel_reload_lists_open_notes(app_dir, qtbot, qapp):
    """패널 reload() 가 열린 스티키 노트 수만큼 카드를 만든다."""
    from ui_sticky_panel import StickySidePanel

    db.create_sticky_note("memo")
    db.create_sticky_note("memo")

    panel = StickySidePanel()
    qtbot.addWidget(panel)
    panel.reload()

    assert len(panel._cards) == 2


def test_sticky_side_panel_reload_flushes_only_pending_cards(
        app_dir, qtbot, qapp, monkeypatch):
    """reload 전에 편집 중인 카드만 저장해 최신 내용을 유지한다."""
    from ui_sticky_panel import StickySidePanel

    first_id = db.create_sticky_note("memo")
    db.create_sticky_note("memo")
    panel = StickySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    first_card = next(card for card in panel._cards if card.note_id == first_id)
    first_card.text_edit.setPlainText("reload 직전 수정")

    original_update = db.update_sticky_note
    saved_ids = []

    def _track_update(note_id, **kwargs):
        if "content" in kwargs:
            saved_ids.append(note_id)
        return original_update(note_id, **kwargs)

    monkeypatch.setattr(db, "update_sticky_note", _track_update)

    panel.reload()

    reloaded = next(card for card in panel._cards if card.note_id == first_id)
    assert reloaded.text_edit.toPlainText() == "reload 직전 수정"
    assert saved_ids == [first_id]


def test_sticky_side_panel_reload_failure_keeps_current_cards(
        app_dir, qtbot, qapp, monkeypatch):
    """DB 재조회 실패를 빈 목록으로 오인해 현재 패널을 지우면 안 된다."""
    from ui_sticky_panel import StickySidePanel

    note_id = db.create_sticky_note("memo")
    db.update_sticky_note(note_id, content="현재 패널 원본")
    panel = StickySidePanel()
    qtbot.addWidget(panel)
    assert panel.reload() is True
    before_cards = list(panel._cards)

    def _fail_reload():
        raise sqlite3.OperationalError("simulated reload failure")

    monkeypatch.setattr(db, "get_open_sticky_notes", _fail_reload)

    assert panel.reload() is False
    assert panel._cards == before_cards
    assert "현재 패널 원본" in panel._cards[0].text_edit.toPlainText()


def test_sticky_side_panel_empty_state(app_dir, qtbot, qapp):
    """열린 노트가 없으면 카드 0개, 빈 상태 라벨 표시."""
    from ui_sticky_panel import StickySidePanel

    panel = StickySidePanel()
    qtbot.addWidget(panel)
    panel.reload()

    assert len(panel._cards) == 0
    assert panel._empty_label.isVisibleTo(panel)


def test_large_mode_activates_side_panel_and_hides_floating(app_dir, qtbot, qapp):
    """large 스케일에서 플로팅 스티키는 숨고 우측 패널 카드로 표시된다."""
    from ui_main import MainCalendarWindow

    db.create_sticky_note("memo")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")

    win = MainCalendarWindow()
    qtbot.addWidget(win)

    assert win._sticky_in_panel_mode is True
    assert win._sticky_side_panel is not None
    assert len(win._sticky_side_panel._cards) == 1
    assert all(not w.isVisible() for w in win._sticky_windows.values())


def test_large_quit_save_uses_panel_as_single_source_of_truth(
        app_dir, qtbot, qapp):
    """large 종료 저장 뒤 숨은 플로팅 복사본이 최신 패널 편집을 덮지 않는다."""
    from ui_main import MainCalendarWindow

    note_id = db.create_sticky_note("memo")
    db.update_sticky_note(note_id, content="이전 내용")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")

    win = MainCalendarWindow()
    qtbot.addWidget(win)
    floating = win._sticky_windows[note_id]
    assert floating.text_edit.toPlainText() == "이전 내용"
    assert not floating.isVisible()

    card = next(
        card for card in win._sticky_side_panel._cards
        if card.note_id == note_id
    )
    card.text_edit.setPlainText("패널의 최신 내용")

    assert win.save_all_sticky_notes() is True
    note = next(n for n in db.get_open_sticky_notes() if n["id"] == note_id)
    assert "패널의 최신 내용" in note["content"]


def test_entering_large_keeps_floating_source_when_first_save_fails(
        app_dir, qtbot, qapp, monkeypatch):
    """large 진입 저장 실패 직후 종료해도 플로팅 최신 편집을 잃지 않는다."""
    import ui_main
    from ui_main import MainCalendarWindow

    note_id = db.create_sticky_note("memo")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "compact")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._sticky_windows[note_id].text_edit.setPlainText("진입 직전 최신 내용")

    original_update = db.update_sticky_note
    failed_once = []

    def _fail_first_content_save(target_id, **kwargs):
        if "content" in kwargs and not failed_once:
            failed_once.append(True)
            raise sqlite3.OperationalError("simulated first-write failure")
        return original_update(target_id, **kwargs)

    monkeypatch.setattr(db, "update_sticky_note", _fail_first_content_save)
    monkeypatch.setattr(ui_main.InfoBar, "error", lambda **kwargs: None)
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    win._apply_calendar_scale()

    assert win._sticky_in_panel_mode is False
    assert win.prepare_for_quit() is True
    note = next(n for n in db.get_open_sticky_notes() if n["id"] == note_id)
    assert "진입 직전 최신 내용" in note["content"]


def test_leaving_large_keeps_panel_source_when_first_save_fails(
        app_dir, qtbot, qapp, monkeypatch):
    """large 이탈 저장 실패 직후 종료해도 패널 최신 편집을 잃지 않는다."""
    import ui_main
    from ui_main import MainCalendarWindow

    note_id = db.create_sticky_note("memo")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    card = next(c for c in win._sticky_side_panel._cards if c.note_id == note_id)
    card.text_edit.setPlainText("이탈 직전 최신 내용")

    original_update = db.update_sticky_note
    failed_once = []

    def _fail_first_content_save(target_id, **kwargs):
        if "content" in kwargs and not failed_once:
            failed_once.append(True)
            raise sqlite3.OperationalError("simulated first-write failure")
        return original_update(target_id, **kwargs)

    monkeypatch.setattr(db, "update_sticky_note", _fail_first_content_save)
    monkeypatch.setattr(ui_main.InfoBar, "error", lambda **kwargs: None)
    db.save_setting(db.SETTING_CALENDAR_SCALE, "compact")
    win._apply_calendar_scale()

    assert win._sticky_in_panel_mode is True
    assert win.prepare_for_quit() is True
    note = next(n for n in db.get_open_sticky_notes() if n["id"] == note_id)
    assert "이탈 직전 최신 내용" in note["content"]


def _expanded_row_order(win):
    """우측 컬럼(_expanded_row)에 담긴 위젯 objectName 순서를 반환."""
    lay = win._expanded_row.layout()
    return [
        lay.itemAt(i).widget().objectName()
        for i in range(lay.count())
        if lay.itemAt(i).widget() is not None
    ]


def test_reapplying_large_keeps_card_order(app_dir, qtbot, qapp):
    from ui_main import MainCalendarWindow

    db.create_sticky_note("memo")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")

    win = MainCalendarWindow()
    qtbot.addWidget(win)

    expected = ["schedulePanel", "ddaySidePanel", "focusSidePanel", "stickySidePanel"]
    assert _expanded_row_order(win) == expected
    win._apply_calendar_scale()
    assert _expanded_row_order(win) == expected
    win._apply_calendar_scale()
    assert _expanded_row_order(win) == expected


def test_large_mode_hides_dday_focus_and_shows_panels(app_dir, qtbot, qapp):
    from ui_main import MainCalendarWindow
    db.create_sticky_note("memo")
    db.create_dday_widget("마감", "2026-12-31")
    db.create_focus_widget("집중", "25/5")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    win = MainCalendarWindow()
    qtbot.addWidget(win)

    assert win._dday_in_panel_mode is True
    assert win._focus_in_panel_mode is True
    assert all(not w.isVisible() for w in win._dday_windows.values())
    assert all(not w.isVisible() for w in win._focus_windows.values())
    assert len(win._dday_side_panel._cards) == 1
    assert win._focus_side_panel._card is not None


def test_large_mode_outer_corner_radii_only(app_dir, qtbot, qapp):
    """large에서 우측 컬럼은 바깥 모서리만 라운드: 일정=우상단, 스티키=우하단."""
    from ui_main import MainCalendarWindow

    db.create_sticky_note("memo")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")

    win = MainCalendarWindow()
    qtbot.addWidget(win)

    sched_qss = win.schedule_panel.styleSheet()
    assert "border-top-right-radius: 12px" in sched_qss
    # 스티키 패널이 아래에 이어지므로 일정 패널 우하단은 각져야 한다
    assert "border-bottom-right-radius: 0px" in sched_qss

    panel_qss = win._sticky_side_panel.styleSheet()
    # 4모서리 일괄 라운드(border-radius:12px) 금지 — 우하단만 라운드
    assert "border-radius:12px" not in panel_qss
    assert "border-bottom-right-radius:12px" in panel_qss


def test_mini_list_background_is_scoped_to_avoid_menu_leak(app_dir, qtbot, qapp):
    """_list 배경 투명 규칙은 objectName으로 스코프되어야 한다.

    선택자 없는 'background:transparent;'는 자식 QTextEdit 우클릭 컨텍스트
    메뉴(QMenu)까지 전파돼 메뉴 배경이 투명해지고 글자가 뒤 배경에 비쳐
    '흐릿해서 읽을 수 없는' 회귀를 만든다('작게' 모드 플로팅 노트와 달라짐).
    따라서 규칙은 반드시 #objectName 으로 스코프되어 메뉴로 새지 않아야 한다.
    """
    from ui_sticky_panel import StickySidePanel

    panel = StickySidePanel()
    qtbot.addWidget(panel)

    qss = panel._list.styleSheet()
    # 스코프된 선택자가 있어야 하고, 'bare' 규칙(선택자 없는 background)은 없어야 한다
    assert "#" in qss, "_list 배경 규칙이 objectName으로 스코프되지 않음 (메뉴로 전파됨)"
    assert panel._list.objectName(), "_list 에 objectName 이 설정되어야 함"
    assert panel._list.objectName() in qss


def test_leaving_large_restores_floating_with_panel_edits(app_dir, qtbot, qapp):
    """large→compact 전환 시 패널 편집 내용이 DB·플로팅 창에 반영되고 패널 모드 해제."""
    from ui_main import MainCalendarWindow

    nid = db.create_sticky_note("memo")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")

    win = MainCalendarWindow()
    qtbot.addWidget(win)
    assert win._sticky_in_panel_mode is True

    card = win._sticky_side_panel._cards[0]
    card.text_edit.setPlainText("패널에서 수정")

    db.save_setting(db.SETTING_CALENDAR_SCALE, "compact")
    win._apply_calendar_scale()

    assert win._sticky_in_panel_mode is False
    notes = {n["id"]: n for n in db.get_open_sticky_notes()}
    assert "패널에서 수정" in notes[nid]["content"]
    assert "패널에서 수정" in win._sticky_windows[nid].text_edit.toPlainText()


def test_panel_toolbar_bold_applies_to_active_card(app_dir, qtbot, qapp):
    from ui_sticky_panel import StickySidePanel
    db.create_sticky_note("memo")
    panel = StickySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    card = panel._cards[0]
    panel._set_active_card(card)
    card.text_edit.setPlainText("굵게 대상")
    card.text_edit.selectAll()
    panel._toolbar.bold_toggled.emit(True)
    assert "font-weight" in card.text_edit.toHtml()


def test_panel_toolbar_bg_color_updates_db(app_dir, qtbot, qapp):
    from ui_sticky_panel import StickySidePanel
    nid = db.create_sticky_note("memo")
    panel = StickySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    panel._set_active_card(panel._cards[0])
    panel._toolbar.bg_color_picked.emit("#D0FFF1")
    notes = {n["id"]: n for n in db.get_open_sticky_notes()}
    assert notes[nid]["color"] == "#D0FFF1"


def test_panel_card_delete_trashes_note(app_dir, qtbot, qapp, monkeypatch):
    from ui_sticky_panel import StickySidePanel
    nid = db.create_sticky_note("memo")
    panel = StickySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    card = panel._cards[0]
    monkeypatch.setattr(card, "_confirm_delete", lambda: True)

    received = []
    panel.note_trashed.connect(received.append)
    card._on_delete()

    assert len(panel._cards) == 0
    assert all(n["id"] != nid for n in db.get_open_sticky_notes())
    assert any(n["id"] == nid for n in db.get_trashed_sticky_notes())
    assert received == [nid]


def test_panel_delete_flushes_target_and_other_pending_cards(
        app_dir, qtbot, qapp):
    """삭제 직전 대상과 나머지 카드의 pending 본문을 모두 보존한다."""
    from ui_sticky_panel import StickySidePanel

    keep_id = db.create_sticky_note("memo")
    delete_id = db.create_sticky_note("memo")
    panel = StickySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    cards = {card.note_id: card for card in panel._cards}
    cards[keep_id].text_edit.setPlainText("남길 카드 최신 내용")
    cards[delete_id].text_edit.setPlainText("삭제 카드 최신 내용")

    panel._on_card_delete(delete_id)

    open_notes = {note["id"]: note for note in db.get_open_sticky_notes()}
    trashed = {note["id"]: note for note in db.get_trashed_sticky_notes()}
    assert "남길 카드 최신 내용" in open_notes[keep_id]["content"]
    assert "삭제 카드 최신 내용" in trashed[delete_id]["content"]
    remaining_card = next(
        card for card in panel._cards if card.note_id == keep_id
    )
    assert remaining_card.text_edit.toPlainText() == "남길 카드 최신 내용"


def test_main_panel_delete_removes_floating(app_dir, qtbot, qapp):
    from ui_main import MainCalendarWindow
    nid = db.create_sticky_note("memo")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    assert nid in win._sticky_windows
    win._on_panel_note_trashed(nid)
    assert nid not in win._sticky_windows
