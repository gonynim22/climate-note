"""최초 설치 분기와 선택값의 실제 DB/화면/백업 왕복."""
import sqlite3
import zipfile
from contextlib import closing

import pytest
from PySide6.QtCore import QObject, QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontInfo, QGuiApplication
from PySide6.QtWidgets import QDialog

import database as db
import security
from ui_first_run import (
    PREVIEW_SCREEN_WIDTH, PREVIEW_WORK_HEIGHT, FirstRunSizeDialog, preview_window_rect,
)


@pytest.fixture
def fresh_dir(app_dir, monkeypatch):
    # app_dir의 UI 폐기 가드는 유지하되 별도 빈 합성 데이터 경로를 사용한다.
    folder = app_dir.parent / "fresh" / "MyDesktopCalendar"
    folder.mkdir(parents=True)
    monkeypatch.setattr(db, "APP_DIR", folder)
    monkeypatch.setattr(db, "DB_FILE", folder / "calendar.db")
    monkeypatch.setattr(security, "APP_DIR", folder)
    monkeypatch.setattr(security, "SALT_FILE", folder / ".salt")
    return folder


def _mapped(dialog, widget):
    """자식 레이아웃 안의 위젯도 대화상자 좌표로 비교한다."""
    return QRect(widget.mapTo(dialog, QPoint(0, 0)), widget.size())


def _assert_controls_inside(dialog):
    controls = [*dialog.cards, dialog.heading, dialog.subtitle, dialog.preview, dialog.hint,
                dialog.start_button, dialog.cancel_button, dialog.close_button]
    for control in controls:
        if control.isVisible():
            assert dialog.rect().contains(_mapped(dialog, control)), (
                control, _mapped(dialog, control), dialog.rect())
    footer_top = min(_mapped(dialog, dialog.start_button).top(),
                     _mapped(dialog, dialog.cancel_button).top())
    for control in (*dialog.cards, dialog.preview, dialog.subtitle):
        assert _mapped(dialog, control).bottom() < footer_top, control
    if dialog.hint.isVisible():
        assert not _mapped(dialog, dialog.hint).intersects(_mapped(dialog, dialog.cancel_button))


def _show_on_synthetic_area(qtbot, area):
    dialog = FirstRunSizeDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(20)
    # 아래 QRect는 합성 화면이다. 실제 다중 모니터 이동 통지는 별도 검사한다.
    dialog.windowHandle().screenChanged.disconnect(dialog._screen_changed)
    dialog.fit_to_available_geometry(area)
    qtbot.wait(20)
    return dialog


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_first_choice_persists_in_database_backup_and_main(fresh_dir, scale, qtbot):
    import main
    from ui_main import MainCalendarWindow
    assert main._initialize_database(lambda: scale)
    assert db.get_setting(db.SETTING_CALENDAR_SCALE) == scale
    bundle = next((fresh_dir / "backups").glob("calendar_auto_*.cnbak"))
    with zipfile.ZipFile(bundle) as archive:
        with open(fresh_dir / "snapshot.db", "wb") as stream:
            stream.write(archive.read("calendar.db"))
    with closing(sqlite3.connect(fresh_dir / "snapshot.db")) as connection:
        assert connection.execute("SELECT value FROM app_settings WHERE key='calendar_scale'").fetchone()[0] == scale
    for _ in range(2):
        assert main._initialize_database(lambda: pytest.fail("기존 사용자는 선택창 생략"))
        window = MainCalendarWindow()
        assert window._current_calendar_scale() == scale
        assert window._sticky_in_panel_mode is (scale == "large")
        if scale == "compact":
            # 새 설치는 바로가기 사이드바 켜짐이 기본(2026-10-11)이라 기본 크기도 460px이다.
            assert window.maximumWidth() == 460
            assert not window.sidebar.isHidden()
        else:
            assert window.maximumWidth() > 460
            assert not window.sidebar.isHidden()
            assert window.schedule_panel.parent() is window._expanded_row
        window.deleteLater()
        qtbot.wait(10)


def test_cancel_repeats_without_database_salt_or_backup(fresh_dir):
    import main
    for _ in range(2):
        assert main._initialize_database(lambda: None) is False
        assert db.inspect_startup_data_health().code == "fresh"
        assert not list(fresh_dir.iterdir())


@pytest.mark.parametrize("value", ["medium", "", "invalid", None])
def test_existing_database_never_prompts_or_overwrites(app_dir, value):
    import main
    if value is None:
        with db._connection() as connection:
            connection.execute("DELETE FROM app_settings WHERE key=?", (db.SETTING_CALENDAR_SCALE,))
            connection.commit()
    else:
        db.save_setting(db.SETTING_CALENDAR_SCALE, value)
    main._initialize_database(lambda: pytest.fail("기존 DB에 설정창 표시"))
    assert db.get_setting(db.SETTING_CALENDAR_SCALE, "missing") == (value if value is not None else "missing")
    db.migrate(initial_calendar_scale="large")
    assert db.get_setting(db.SETTING_CALENDAR_SCALE, "missing") == (value if value is not None else "missing")


@pytest.mark.parametrize("residue", [".salt", "calendar.db-wal", "calendar.db-shm", "backups/calendar_old.db", "calendar.db"])
def test_incomplete_or_corrupt_dataset_does_not_prompt(fresh_dir, residue):
    import main
    path = fresh_dir / residue
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b"preserve")
    with pytest.raises(db.DataHealthError):
        main._initialize_database(lambda: pytest.fail("손상 데이터에 설정창 표시"))
    assert path.read_bytes() == b"preserve"


def test_invalid_initial_size_does_not_create_database(fresh_dir):
    import main
    with pytest.raises(ValueError):
        main._initialize_database(lambda: "huge")
    with pytest.raises(ValueError):
        db.migrate(initial_calendar_scale="huge")
    assert not list(fresh_dir.iterdir())


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_initial_scale_export_import_round_trip(fresh_dir, scale):
    import main
    assert main._initialize_database(lambda: scale)
    db.add_schedule("2026-10-04", "크기 왕복 검사")
    exported = db.export_all_data()
    salt = security.SALT_FILE.read_bytes()
    db.save_setting(db.SETTING_CALENDAR_SCALE, "compact" if scale != "compact" else "large")
    db.import_all_data(exported)
    assert db.get_setting(db.SETTING_CALENDAR_SCALE) == scale
    assert security.SALT_FILE.read_bytes() == salt


def test_factory_reset_keeps_existing_startup_path(app_dir):
    import main
    db.reset_database()
    security.reset_salt()
    assert main._initialize_database(lambda: pytest.fail("Factory Reset 후 최초 설정 표시"))
    assert db.get_setting(db.SETTING_CALENDAR_SCALE) == "compact"


def test_initial_database_write_failure_propagates(fresh_dir, monkeypatch):
    import main
    def fail(**kwargs):
        raise sqlite3.OperationalError("injected initial write failure")
    monkeypatch.setattr(db, "migrate", fail)
    with pytest.raises(sqlite3.OperationalError):
        main._initialize_database(lambda: "medium")
    assert not db.DB_FILE.exists()


def test_dataset_appearing_during_setup_is_not_overwritten(fresh_dir):
    import main
    def choose():
        db.DB_FILE.write_bytes(b"external-data")
        return "large"
    with pytest.raises(db.DataHealthError):
        main._initialize_database(choose)
    assert db.DB_FILE.read_bytes() == b"external-data"


def test_dialog_keyboard_selection_and_accept(qtbot):
    dialog = FirstRunSizeDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.activateWindow()
    dialog.cards[0].setFocus()
    qtbot.waitUntil(lambda: dialog.cards[0].hasFocus())
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Right)
    assert dialog.selected_scale == "medium"
    assert dialog.cards[1].hasFocus()
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Right)
    assert dialog.selected_scale == "large"
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Space)
    assert dialog.cards[2].isChecked()
    assert sum(card.isChecked() for card in dialog.cards) == 1
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Return)
    assert dialog.result() == QDialog.Accepted


@pytest.mark.parametrize("accept", [True, False])
def test_startup_dialog_adapter_returns_choice_or_cancellation(qapp, monkeypatch, accept):
    import main
    import ui_first_run
    dialog = FirstRunSizeDialog()
    dialog._select("medium")
    monkeypatch.setattr(ui_first_run, "FirstRunSizeDialog", lambda: dialog)
    QTimer.singleShot(0, dialog.accept if accept else dialog.reject)
    assert main._choose_initial_calendar_scale() == ("medium" if accept else None)


@pytest.mark.parametrize("close", ["escape", "title", "button", "window", "title_enter", "button_enter"])
def test_dialog_cancel_returns_rejected(qtbot, close):
    dialog = FirstRunSizeDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.mouseClick(dialog.cards[1], Qt.LeftButton)
    if close == "escape":
        qtbot.keyClick(dialog, Qt.Key_Escape)
    elif close == "window":
        dialog.close()
    elif close.endswith("_enter"):
        button = dialog.close_button if close == "title_enter" else dialog.cancel_button
        dialog.activateWindow()
        button.setFocus()
        qtbot.waitUntil(button.hasFocus)
        qtbot.keyClick(dialog.focusWidget(), Qt.Key_Return)
    else:
        qtbot.mouseClick(dialog.close_button if close == "title" else dialog.cancel_button, Qt.LeftButton)
    assert dialog.result() == QDialog.Rejected
    assert not dialog.isVisible()


@pytest.mark.parametrize("width,height,stacked,short", [
    (1000, 900, False, False), (700, 550, False, False), (800, 400, False, True),
    (540, 500, True, False), (400, 600, True, False), (320, 600, True, False),
    (400, 450, True, True), (800, 380, True, True),
])
def test_dialog_layout_fits_work_area(qtbot, width, height, stacked, short):
    area = QRect(20, 30, width, height)
    dialog = _show_on_synthetic_area(qtbot, area)
    assert (dialog.stacked, dialog.short) == (stacked, short)
    assert area.contains(dialog.geometry())
    _assert_controls_inside(dialog)
    cards = [_mapped(dialog, card) for card in dialog.cards]
    preview = _mapped(dialog, dialog.preview)
    if stacked:
        # 한 열 배치: 위에 크기 버튼 한 줄, 아래에 미리보기
        assert len({card.top() for card in cards}) == 1
        assert all(card.bottom() < preview.top() for card in cards)
        assert all(card.segment for card in dialog.cards)
    else:
        # 넓은 배치: 왼쪽 세로 목록, 오른쪽 미리보기
        assert len({card.left() for card in cards}) == 1
        assert all(card.right() < preview.left() for card in cards)
        assert not any(card.segment for card in dialog.cards)
    assert dialog.hint.isVisible() is (short and not stacked)
    assert dialog.preview.monitor_ratio() > (0.4 if height >= 450 else 0.1)


def test_work_area_round_trip_reflows_without_old_minimum(qtbot):
    dialog = FirstRunSizeDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(20)
    dialog.windowHandle().screenChanged.disconnect(dialog._screen_changed)
    for width, height in [(1000, 900), (400, 600), (800, 400), (320, 600), (1000, 900)]:
        area = QRect(0, 0, width, height)
        dialog.fit_to_available_geometry(area)
        qtbot.wait(20)
        assert area.contains(dialog.geometry()), (area, dialog.geometry())


def test_removed_screen_does_not_leave_invalid_signal_connection(qtbot, qapp):
    from shiboken6 import delete
    class Screen(QObject):
        availableGeometryChanged = Signal(QRect)
        def availableGeometry(self):
            return QRect(0, 0, 540, 500)
    dialog = FirstRunSizeDialog()
    qtbot.addWidget(dialog)
    screen = Screen()
    dialog._screen_changed(screen)
    delete(screen)
    dialog._screen_changed(qapp.primaryScreen())
    assert qapp.primaryScreen().availableGeometry().contains(dialog.geometry())


def test_release_setup_confirmation_refuses_unowned_window(monkeypatch):
    from tools import smoke_release
    monkeypatch.setattr(smoke_release, "windows_in_job", lambda job: [])
    with pytest.raises(ValueError, match="소유한"):
        smoke_release.accept_first_run_setup(object(), {"hwnd": 123, "pid": 456})


def test_preview_geometry_matches_main_window_rule(app_dir):
    from ui_main import MainCalendarWindow, _calendar_corner_coordinates
    db.save_setting(db.SETTING_SHOW_SIDEBAR, "1")  # 미리보기는 새 설치 기본값(사이드바 켜짐)을 그린다

    class Screen:
        def availableGeometry(self):
            return QRect(0, 0, PREVIEW_SCREEN_WIDTH, PREVIEW_WORK_HEIGHT)

        def physicalDotsPerInch(self):
            return 96

    screen = Screen()
    snap = round(96 * 5 / 25.4)
    for scale in db.CALENDAR_SCALES:
        width, height = MainCalendarWindow._calendar_scale_geometry(None, scale, screen)
        x, y = _calendar_corner_coordinates(screen, width, height, "bottom-right")
        rect = preview_window_rect(scale)
        assert (rect.width(), rect.height()) == (width, height)
        # 실제 창은 5mm 격자로 스냅하므로 그 이내의 차이만 허용한다.
        assert abs(rect.x() - x) <= snap and abs(rect.y() - y) <= snap


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_preview_paints_selected_window_at_its_real_position(qtbot, scale):
    dialog = _show_on_synthetic_area(qtbot, QRect(0, 0, 1000, 900))
    dialog._select(scale)
    target = QRectF(preview_window_rect(scale))
    qtbot.waitUntil(lambda: dialog.preview.window_rect() == target, timeout=2000)
    image = dialog.preview.grab().toImage()
    ratio = image.devicePixelRatio()
    window = dialog.preview.window_rect_on_widget()

    def color_at(x, y):
        return image.pixelColor(int(x * ratio), int(y * ratio))

    # 세 크기 모두 창 오른쪽 아래 안쪽은 흰 바탕(일정 열/목록 아래 빈 곳)이다.
    assert color_at(window.right() - 3, window.bottom() - 3).name() == "#ffffff"
    if scale != "large":
        outside = color_at(window.left() - 4, window.bottom() - 3)
        assert abs(outside.red() - 0xCB) <= 12
        assert abs(outside.green() - 0xD6) <= 12
        assert abs(outside.blue() - 0xE3) <= 12


def test_compact_preview_shows_shortcut_sidebar(qtbot):
    """새 설치 기본은 바로가기 켜짐이라 기본 크기 미리보기도 왼쪽에 바로가기 열을 그린다."""
    dialog = _show_on_synthetic_area(qtbot, QRect(0, 0, 1000, 900))
    dialog._select("compact")
    target = QRectF(preview_window_rect("compact"))
    qtbot.waitUntil(lambda: dialog.preview.window_rect() == target, timeout=2000)
    image = dialog.preview.grab().toImage()
    ratio = image.devicePixelRatio()
    window = dialog.preview.window_rect_on_widget()
    side = window.width() * 80 / 460
    color = image.pixelColor(int((window.left() + side / 2) * ratio), int((window.bottom() - 3) * ratio))
    assert color.name() == "#eef2f6"


def test_reselecting_during_animation_ends_at_last_choice(qtbot):
    dialog = _show_on_synthetic_area(qtbot, QRect(0, 0, 1000, 900))
    dialog._select("large")
    dialog._select("medium")
    target = QRectF(preview_window_rect("medium"))
    qtbot.waitUntil(lambda: dialog.preview.window_rect() == target, timeout=2000)
    qtbot.wait(300)
    assert dialog.preview.window_rect() == target
    assert dialog.preview.scale == "medium"


def test_header_empty_area_belongs_to_a_drag_handle(qtbot):
    dialog = _show_on_synthetic_area(qtbot, QRect(0, 0, 1000, 900))
    close = _mapped(dialog, dialog.close_button)
    # 처음 설정 글자와 X 버튼 사이 빈 머리줄은 프레임 없는 창을 끄는 손잡이여야 한다.
    point = QPoint(close.left() - 20, close.center().y())
    assert dialog.childAt(point) is dialog.brand_sub
    assert dialog.brand_sub in dialog._drag_handles


def test_dialog_stays_light_under_dark_theme(qtbot):
    from qfluentwidgets import Theme, setTheme
    setTheme(Theme.DARK)
    # Qt 자체 다크 색 구성표도 켜서 위젯 기본 팔레트가 어두워지는 경로를 실제로 통과시킨다.
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    try:
        dialog = _show_on_synthetic_area(qtbot, QRect(0, 0, 1000, 900))
        image = dialog.grab().toImage()
        ratio = image.devicePixelRatio()
        # 머리줄 위 여백(바탕)이 다크 테마에서도 흰색이어야 한다.
        assert image.pixelColor(int(dialog.width() / 2 * ratio), int(8 * ratio)).name() == "#ffffff"
    finally:
        QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Unknown)
        setTheme(Theme.LIGHT)


def test_heading_choice_and_start_use_bundled_pretendard(qtbot):
    from app_fonts import load_ui_fonts
    load_ui_fonts()
    dialog = FirstRunSizeDialog()
    qtbot.addWidget(dialog)
    assert QFontInfo(dialog.heading.font()).family() == "Pretendard"
    assert QFontInfo(dialog.start_button.font()).family() == "Pretendard"
    assert QFontInfo(dialog.subtitle.font()).family() == "Malgun Gothic"


def test_layout_fits_when_pretendard_is_unavailable(qtbot, monkeypatch):
    import ui_first_run
    original = ui_first_run._font

    def without_pretendard(px, weight=QFont.Weight.Normal, *, display=False):
        return original(px, weight, display=False)

    monkeypatch.setattr(ui_first_run, "_font", without_pretendard)
    for width, height in ((320, 600), (800, 400), (400, 450), (1000, 900)):
        dialog = _show_on_synthetic_area(qtbot, QRect(0, 0, width, height))
        _assert_controls_inside(dialog)


def test_stacked_keyboard_selection_and_accept(qtbot):
    dialog = _show_on_synthetic_area(qtbot, QRect(0, 0, 400, 600))
    assert dialog.stacked
    dialog.activateWindow()
    dialog.cards[0].setFocus()
    qtbot.waitUntil(lambda: dialog.cards[0].hasFocus())
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Right)
    assert dialog.selected_scale == "medium" and dialog.cards[1].hasFocus()
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Left)
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Left)
    assert dialog.selected_scale == "large" and dialog.cards[2].hasFocus()
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Return)
    assert dialog.result() == QDialog.Accepted
