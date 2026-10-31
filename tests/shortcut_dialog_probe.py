"""실제 modal loop 회귀를 별도 프로세스에서 실행(부모가 AppData/Job 격리)."""
import ctypes
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))  # 앱 모듈(B안)


def run(directory: Path, operation: str, outcome: str) -> int:
    os.environ["LOCALAPPDATA"] = str(directory / "appdata")
    ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002)
    from PySide6.QtCore import QEvent, QObject, QPoint, QTimer, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication, QFileDialog, QInputDialog, QVBoxLayout, QWidget,
    )
    from shiboken6 import isValid
    import database as db
    import security
    from ui_main import ShortcutSlot

    errors = []
    def exception_hook(kind, value, tb):
        errors.append(str(value))
        traceback.print_exception(kind, value, tb)
    sys.excepthook = exception_hook
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    db.migrate()
    db.save_memo("2026-10-02", "보존할 기존 메모")
    db.update_shortcut(6, "다른 슬롯", str(directory / "unchanged.txt"))
    target = directory / ("selected-folder" if operation == "folder" else "selected.txt")
    if operation == "folder":
        target.mkdir()
    else:
        with open(target, "w", encoding="utf-8") as stream:
            stream.write("synthetic")
    if operation in ("rename", "repair"):
        db.update_shortcut(1, "내 업무", str(directory / "old.txt"))

    def protected_data():
        with db._connection() as conn:
            dump = list(conn.iterdump())
        with open(security.SALT_FILE, "rb") as stream:
            salt = stream.read()
        return [line for line in dump if not line.startswith('INSERT INTO "shortcuts"')], salt
    before = protected_data()
    before_shortcuts = db.get_shortcuts()
    parent = QWidget()
    layout = QVBoxLayout(parent)
    slot = ShortcutSlot(1, parent)
    slot.update_data(before_shortcuts[0]["name"], before_shortcuts[0]["path"])
    layout.addWidget(slot)
    parent.show()
    menus = []
    for method_name in ("_build_registration_menu", "_build_manage_menu"):
        original = getattr(slot, method_name)
        def tracked_build(original=original):
            menu = original()
            menus.append(menu)
            return menu
        setattr(slot, method_name, tracked_build)

    # 선택 결과를 가짜 값으로 바꾸지 않는다. 합성 파일만 기본 선택한다.
    original_file = QFileDialog.getOpenFileName
    original_folder = QFileDialog.getExistingDirectory
    QFileDialog.getOpenFileName = lambda owner, title, _directory, filters: original_file(
        owner, title, str(target), filters,
    )
    QFileDialog.getExistingDirectory = lambda owner, title: original_folder(
        owner, title, str(target),
    )
    click_active = False
    dialog_observations = []

    class DialogDriver(QObject):
        def eventFilter(self, obj, event):
            if isinstance(obj, (QFileDialog, QInputDialog)) and event.type() == QEvent.Show:
                dialog_observations.append({"during_menu_click": click_active})
                if isinstance(obj, QInputDialog):
                    obj.setTextValue("바꾼 이름")
                QTimer.singleShot(150, obj.accept if outcome == "accept" else obj.reject)
            return False
    driver = DialogDriver(app)
    app.installEventFilter(driver)

    def finish():
        rows = db.get_shortcuts()
        first = rows[0]
        if outcome == "cancel":
            expected = before_shortcuts[0]
        elif operation == "rename":
            expected = {**before_shortcuts[0], "name": "바꾼 이름"}
        else:
            expected = {"id": 1, "name": "내 업무" if operation == "repair" else target.stem,
                        "path": str(target).replace("\\", "/")}
        first = {**first, "path": first["path"].replace("\\", "/")}
        expected = {**expected, "path": expected["path"].replace("\\", "/")}
        result = {
            "errors": errors, "dialogs": dialog_observations,
            "menus_disposed": all(not isValid(menu) for menu in menus),
            "data_preserved": protected_data() == before,
            "other_slots_preserved": rows[1:] == before_shortcuts[1:],
            "slot_matches": first == expected,
        }
        result["ok"] = (
            not errors and len(dialog_observations) == 1
            and not dialog_observations[0]["during_menu_click"]
            and all(result[key] for key in (
                "menus_disposed", "data_preserved", "other_slots_preserved", "slot_matches",
            ))
        )
        with open(directory / "result.json", "w", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        app.exit(0 if result["ok"] else 1)

    def click_item(index, repair=False):
        nonlocal click_active
        menu = menus[-1]
        item = menu.view.item(index)
        click_active = True
        try:
            QTest.mouseClick(menu.view.viewport(), Qt.LeftButton,
                             pos=menu.view.visualItemRect(item).center())
        finally:
            click_active = False
        if repair:
            QTimer.singleShot(350, lambda: click_item(0))
        else:
            QTimer.singleShot(600, finish)

    def start():
        if operation in ("rename", "repair"):
            slot.btn.customContextMenuRequested.emit(QPoint(2, 2))
        else:
            QTest.mouseClick(slot.btn, Qt.LeftButton)
        index = 1 if operation in ("folder", "repair") else 0
        QTimer.singleShot(350, lambda: click_item(index, operation == "repair"))
    QTimer.singleShot(100, start)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run(Path(sys.argv[1]), sys.argv[2], sys.argv[3]))
