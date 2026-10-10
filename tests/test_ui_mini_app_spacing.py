"""디자인 점검 20·21번: 날짜·시간 계산기 입력과 안내 사이 빈 공간, 문서 변환 빈 목록 안내·버튼."""
from pathlib import Path

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication, QLabel, QWidget

import database as db
import ui_document_converter as doc
from hwp_conversion import ConversionEnvironment
from ui_date_time_calculator import MODES, DateTimeCalculatorWindow


@pytest.fixture(autouse=True)
def isolated(app_dir, monkeypatch):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    monkeypatch.setattr(doc, "detect_environment",
                        lambda: ConversionEnvironment(Path("hwp.exe"), Path("HwpxConverter.exe")))


def _show(qtbot, win):
    qtbot.addWidget(win)
    win.show_near(QRect(10, 10, 64, 48), QApplication.primaryScreen().availableGeometry())
    qtbot.waitExposed(win)
    QApplication.processEvents()
    return win


@pytest.mark.parametrize("mode", list(MODES))
def test_date_time_rows_and_note_pack_to_top(qtbot, mode):
    win = _show(qtbot, DateTimeCalculatorWindow())
    win.select_mode(mode)
    QApplication.processEvents()
    page = win.page_widgets[mode]
    widgets = sorted((w for w in page.findChildren(QWidget, options=Qt.FindDirectChildrenOnly) if w.isVisible()),
                     key=lambda w: w.geometry().top())
    bottom = widgets[0].geometry().bottom()
    for widget in widgets:
        # 남는 높이가 줄 묶음·안내 글자 안으로 퍼져 글자가 아래로 떨어지지 않는다.
        # (가로줄 안의 작은 라벨은 같은 줄 버튼 높이에 맞춰지는 것이 정상이라 뺀다.)
        if isinstance(widget, QLabel) and widget not in win._form_notes:
            continue
        assert widget.height() <= max(widget.sizeHint().height(), widget.minimumHeight()) + 4, (mode, widget)
    for widget in widgets[1:]:
        assert widget.geometry().top() - bottom <= 12, (mode, widget)
        bottom = max(bottom, widget.geometry().bottom())


def _doc(qtbot):
    return _show(qtbot, doc.DocumentConverterWindow())


def test_empty_list_shows_drop_hint_and_hides_rare_buttons(qtbot, tmp_path):
    win = _doc(qtbot)
    assert win.empty_hint.isVisible()
    assert "끌어 놓으세요" in win.empty_hint.text()
    for button in (win.remove_button, win.clear_button, win.retry_button, win.cancel_button, win.open_button):
        assert button.isHidden(), button.text()
    assert win.add_button.isVisible() and win.start_button.isVisible()

    source = tmp_path / "a.hwp"
    source.touch()
    win.add_files([source])
    QApplication.processEvents()
    assert not win.empty_hint.isVisible()
    assert not win.remove_button.isHidden() and not win.clear_button.isHidden()
    assert win.retry_button.isHidden() and win.open_button.isHidden()


def test_retry_open_and_cancel_appear_when_relevant(qtbot, tmp_path, monkeypatch):
    win = _doc(qtbot)
    files = [tmp_path / name for name in ("a.hwp", "b.hwp")]
    for file in files:
        file.touch()
    win.add_files(files)
    calls = []
    monkeypatch.setattr(win.runner, "start", lambda source, directory: calls.append(source))
    win.start_conversion()
    assert not win.cancel_button.isHidden()  # 변환 중에만 취소
    win.runner.finished.emit(False, "", "합성 실패")
    qtbot.waitUntil(lambda: len(calls) == 2)
    win.runner.finished.emit(True, str(tmp_path / "b.hwpx"), "완료")
    QApplication.processEvents()
    assert win.cancel_button.isHidden()
    assert not win.retry_button.isHidden()  # 실패가 있으니 재시도
    assert not win.open_button.isHidden()   # 완료 결과가 있으니 폴더 열기
