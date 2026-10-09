"""Windows 다크 모드에서도 앱이 밝게 그려지는지 검사.

Windows가 다크면 qfluentwidgets 테마뿐 아니라 Qt 기본 위젯 팔레트(windows11 스타일)도
어두워진다. 둘 중 하나만 고정하면 흰 바탕에 흰 글자가 남으므로 둘 다 흉내 내고 검사한다.
"""
import inspect
from datetime import date

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPalette
from PySide6.QtWidgets import QApplication, QLineEdit
from qfluentwidgets import Theme, isDarkTheme, setTheme, setThemeColor, themeColor

import database as db
import main
import ui_main
from show_desktop_guard import ShowDesktopKeeper
from ui_dday import DDayCreateDialog
from ui_main import MainCalendarWindow


@pytest.fixture(autouse=True)
def quiet_native_layer(app_dir, monkeypatch):
    # 화면 색만 검사한다. 바탕 화면 고정 같은 native 레이어는 별도 검사다.
    monkeypatch.setattr(ShowDesktopKeeper, "_install_foreground_hook", lambda self: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_apply_topmost", lambda *a, **k: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_pin_to_desktop_layer", lambda self: False)
    monkeypatch.setattr(MainCalendarWindow, "_warn_keep_desktop_unavailable_once", lambda self: None)
    for kind in ("info", "success", "warning", "error"):
        monkeypatch.setattr(ui_main.InfoBar, kind, lambda *a, **k: None)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")


@pytest.fixture
def restore_light():
    yield
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Unknown)
    setTheme(Theme.LIGHT)
    setThemeColor(QColor("#2563EB"))


def _simulate_windows_dark():
    """Windows 다크 모드 상태: Qt 색 구성표와 Fluent 테마가 모두 어둡다."""
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    setTheme(Theme.DARK)


def test_light_theme_is_kept_when_windows_is_dark(qapp, restore_light):
    _simulate_windows_dark()
    main._apply_light_theme(qapp)

    assert QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Light
    assert not isDarkTheme()
    assert themeColor().name() == "#2563eb"
    # Qt 기본 위젯 팔레트도 밝아야 한다(Windows 다크면 바탕 #2d2d2d, 글자 흰색이 된다).
    palette = QLineEdit().palette()
    assert palette.color(QPalette.Base).lightness() > 240
    assert palette.color(QPalette.Text).lightness() < 40


def test_startup_does_not_follow_windows_theme():
    # 실행 중 Windows 테마를 다시 읽어 Fluent만 다크로 바꾸던 경로(1분 주기)가 돌아오면
    # 흰 창 위에 흰 글자가 다시 생긴다. 시작 때 밝은 테마 고정만 남아 있어야 한다.
    assert "AppsUseLightTheme" not in inspect.getsource(main)
    assert "_apply_light_theme(app)" in inspect.getsource(main.main)


def _seed_synthetic_data():
    day = date.today().isoformat()
    for text, color in (("주간 업무회의 10:00", "#FFD166"), ("수질 점검 결과 보고", "#4CC9F0")):
        db.add_schedule(day, text, color)
    note = db.create_sticky_note("memo", 980, 120)
    db.update_sticky_note(note, content="<p><b>이번 주 할 일</b></p><p>보고서 초안 작성</p>")
    trashed = db.create_sticky_note("memo", 300, 300)
    db.update_sticky_note(trashed, content="<p>지난주 메모</p>")
    db.trash_sticky_note(trashed)


def _grab(qtbot, widget) -> QImage:
    qtbot.wait(250)
    return widget.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)


def _render_app_windows(qtbot) -> dict[str, QImage]:
    """다크 깨짐이 보였던 창들을 합성 데이터로 띄워 이미지로 받고 모두 폐기한다."""
    before = set(QApplication.topLevelWidgets())
    win = MainCalendarWindow()
    win.move(40, 40)
    win.show()
    images = {"main": _grab(qtbot, win)}
    for name, opener, attr in (
        ("settings", win._on_settings, "_settings_window"),
        ("search", win._on_search, "_search_window"),
        ("trash", win._on_open_trash, "_trash_window"),
    ):
        opener()
        window = getattr(win, attr)
        images[name] = _grab(qtbot, window)
        window.hide()
    for index, sticky in enumerate(win._sticky_windows.values()):
        images[f"sticky{index}"] = _grab(qtbot, sticky)
    dialog = DDayCreateDialog(win)
    dialog.show()
    images["dday_create"] = _grab(qtbot, dialog)
    dialog.hide()
    # close()는 저장 확인을 띄우므로 conftest와 같이 DeferredDelete로만 폐기한다.
    for widget in QApplication.topLevelWidgets():
        if widget not in before:
            widget.hide()
            widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    return images


def _differing_ratio(a: QImage, b: QImage) -> float:
    assert a.size() == b.size()
    pa, pb = bytes(a.constBits()), bytes(b.constBits())
    total = differing = 0
    for i in range(0, len(pa), 4 * 3):  # 3픽셀마다 표본(RGB32는 줄 끝 여백이 없다)
        total += 1
        if max(abs(pa[i] - pb[i]), abs(pa[i + 1] - pb[i + 1]), abs(pa[i + 2] - pb[i + 2])) > 32:
            differing += 1
    return differing / total


def test_windows_dark_renders_same_as_light(qtbot, qapp, restore_light):
    _seed_synthetic_data()
    main._apply_light_theme(qapp)
    light = _render_app_windows(qtbot)

    _simulate_windows_dark()
    main._apply_light_theme(qapp)
    fixed = _render_app_windows(qtbot)

    assert light.keys() == fixed.keys()
    assert {"main", "settings", "search", "trash", "sticky0", "dday_create"} <= light.keys()
    ratios = {name: _differing_ratio(light[name], fixed[name]) for name in light}
    # 입력 커서 깜빡임 정도만 허용한다. 다크가 새면 입력칸·글자·창 바탕이 통째로 달라진다.
    assert all(ratio < 0.001 for ratio in ratios.values()), ratios
