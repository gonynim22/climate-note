"""디자인 점검 18번: 설정 '데이터' — PIN은 입력칸 모양, 저장 경로는 한 줄로 보이고 폴더 버튼은 그대로."""
from PySide6.QtCore import QPoint, QRect, Qt

from ui_settings import SettingsWindow
import ui_settings


def _window(qtbot):
    win = SettingsWindow()
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    return win


def test_pin_fields_look_like_inputs(qtbot, app_dir):
    win = _window(qtbot)
    for edit in (win.export_pin, win.import_pin):
        assert edit.width() >= 100
        assert edit.placeholderText() == "PIN 4자리"
        assert not edit.alignment() & Qt.AlignHCenter
        assert edit.maxLength() == 4


def test_storage_path_shown_next_to_folder_button(qtbot, app_dir):
    win = _window(qtbot)
    label = win.data_path_label
    assert label.toolTip() == str(ui_settings.APP_DIR)
    assert label.text()
    assert win.open_data_folder_btn.isVisible()  # 폴더 버튼은 그대로 둔다
    path_right = label.mapTo(win, QPoint(label.width(), 0)).x()
    assert path_right <= win.open_data_folder_btn.mapTo(win, QPoint()).x()
    assert win.rect().contains(QRect(label.mapTo(win, QPoint()), label.size()))


def test_long_storage_path_is_elided_in_the_middle(qtbot, app_dir):
    win = _window(qtbot)
    long_path = "C:\\Users\\" + "아주긴사용자이름" * 6 + "\\AppData\\Local\\MyDesktopCalendar"
    win.data_path_label.set_full_text(long_path)
    text = win.data_path_label.text()
    assert "…" in text and text.startswith("C:") and text.endswith("MyDesktopCalendar")
    assert win.data_path_label.toolTip() == long_path
