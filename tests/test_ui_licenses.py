"""고지 누락·실제 열람·선택형 제거·데이터 보존 회귀."""
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

import database as db
import security
from app_paths import resource_root
from ui_licenses import LicenseDialog, license_document, license_entries
from ui_settings import SettingsWindow

ROOT = Path(__file__).resolve().parents[1]
HANCOM = "본 제품은 한컴의 HWP 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다."


def test_catalog_documents_exist_and_preserve_attribution():
    entries = license_entries(ROOT)
    assert len({entry["id"] for entry in entries}) == len(entries)
    by_id = {entry["id"]: entry for entry in entries}
    for entry in entries:
        assert entry["license"] and entry["description"] and entry["sources"]
        for filename in entry["files"]:
            path = (ROOT / filename).resolve()
            assert path.is_relative_to(ROOT)
            assert path.is_file(), filename
            assert path.read_text(encoding="utf-8-sig").strip()
    assert "GNU GENERAL PUBLIC LICENSE" in license_document(ROOT, by_id["app"])
    assert HANCOM in license_document(ROOT, by_id["hancom"])
    assert "MIT No Attribution" in license_document(ROOT, by_id["cffi"])
    assert "Mark Hammond" in license_document(ROOT, by_id["pywin32"])
    assert "Qt Virtual Keyboard는 GPLv3" in license_document(ROOT, by_id["qt"])
    if (ROOT / "screen_text").is_dir():
        assert "2016 PaddlePaddle Authors" in license_document(ROOT, by_id["ocr-models"])
        assert "7b02d0a30a07ba2b92ad1ff5a8941ae2c633de65" in license_document(ROOT, by_id["ocr-models"])


def test_hancom_notice_in_existing_product_documentation_and_source():
    for filename in ("src/hwp_conversion.py", "README.md", "README_detail.md", "docs/DOCUMENT_CONVERSION.md"):
        assert HANCOM in (ROOT / filename).read_text(encoding="utf-8")


def test_copied_originals_still_match_recorded_hashes():
    records = [ROOT / "licenses/ORIGINS.json"]
    if (ROOT / "screen_text").is_dir():
        records.append(ROOT / "screen_text/licenses/ORIGINS.json")
    for record in records:
        for item in json.loads(record.read_text(encoding="utf-8")):
            assert hashlib.sha256((ROOT / item["file"]).read_bytes()).hexdigest() == item["sha256"]


def test_optional_notices_disappear_without_app_and_no_import(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "licenses", tmp_path / "licenses")
    shutil.copyfile(ROOT / "LICENSE", tmp_path / "LICENSE")
    # 목록만 읽으며 모델이나 DB import로 활성 여부를 검사하지 않는다.
    without = license_entries(tmp_path)
    assert not {"ocr-models", "onnxruntime", "numpy"} & {x["id"] for x in without}
    assert all(not path.startswith("screen_text/") for x in without for path in x["files"])
    if (ROOT / "screen_text").is_dir():
        shutil.copytree(ROOT / "screen_text/licenses", tmp_path / "screen_text/licenses")
        with_app = license_entries(tmp_path)
        assert {"ocr-models", "onnxruntime", "numpy"} <= {x["id"] for x in with_app}
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
    assert resource_root() == tmp_path


def test_missing_original_and_catalog_are_visible_errors(qtbot, tmp_path):
    entry = dict(id="missing", name="Sample", version="1", license="MIT",
                 description="", sources=["https://example.com"], files=["absent.txt"])
    assert "고지 파일을 읽을 수 없습니다" in license_document(tmp_path, entry)
    parent = QWidget()
    qtbot.addWidget(parent)
    dlg = LicenseDialog(parent, root=tmp_path)
    assert "목록을 읽을 수 없습니다" in dlg.document.toPlainText()
    assert not dlg.component_combo.isEnabled()


def _snapshot():
    with db._connection() as connection:
        dump = tuple(connection.iterdump())
    return dump, security.SALT_FILE.read_bytes(), db.export_all_data()


def test_settings_read_all_copy_and_close_preserves_data(qtbot, app_dir, monkeypatch):
    db.add_schedule("2026-10-09", "라이선스 검사 합성 일정 🌿")
    win = SettingsWindow()
    qtbot.addWidget(win)
    win.show()
    before = _snapshot()
    def unexpected_write(*args, **kwargs):
        pytest.fail("라이선스 열람이 설정을 저장함")
    monkeypatch.setattr(db, "save_setting", unexpected_write)
    button = win.findChild(QPushButton, "licenseBtn")
    qtbot.mouseClick(button, Qt.LeftButton)
    dlg = win._license_dialog
    assert dlg is not None and dlg.isVisible()
    assert win.size().width() == 800 and win.size().height() == 560
    output = Path(os.environ.get("CLIMATENOTE_TEST_APPDATA", str(app_dir))).parent
    assert dlg.grab().save(str(output / "license-overview.png"))
    for index in range(dlg.component_combo.count()):
        dlg.component_combo.setCurrentIndex(index)
        assert "읽을 수 없습니다" not in dlg.document.toPlainText()
        assert dlg.document.isReadOnly()
        assert dlg.document.verticalScrollBar().value() == 0
        if dlg.component_combo.currentData() == "ocr-models":
            assert dlg.grab().save(str(output / "license-ocr.png"))
    previous = QApplication.clipboard().text()
    try:
        qtbot.mouseClick(dlg.copy_button, Qt.LeftButton)
        assert QApplication.clipboard().text() == dlg.document.toPlainText()
    finally:
        QApplication.clipboard().setText(previous)
    qtbot.keyClick(dlg, Qt.Key_Escape)
    assert win._license_dialog is None
    assert _snapshot() == before


@pytest.mark.parametrize("action", ["hide", "disable", "close"])
def test_license_lifetime_follows_settings(qtbot, app_dir, action):
    win = SettingsWindow()
    qtbot.addWidget(win)
    win.show()
    win._on_license()
    dlg = win._license_dialog
    win._on_license()
    assert win._license_dialog is dlg  # 같은 부모에서 중복 열기 금지
    if action == "disable":
        win.setEnabled(False)
    else:
        getattr(win, action)()
    assert win._license_dialog is None
    win._on_license()
    assert win._license_dialog is None
    win.setEnabled(True)
    win.show()
    assert win._license_dialog is None  # 복귀 시 자동 재표시 금지


def test_main_pin_lock_closes_license(qtbot, app_dir):
    from ui_main import MainCalendarWindow
    main = MainCalendarWindow()
    qtbot.addWidget(main)
    main.show()
    main._on_settings()
    settings = main._settings_window
    settings._on_license()
    assert settings._license_dialog is not None
    main._lock()
    assert settings._license_dialog is None
    main._unlock()
    assert settings._license_dialog is None


@pytest.mark.parametrize("area", [QRect(0, 0, 1920, 1080), QRect(-800, 0, 800, 600), QRect(0, 0, 360, 400)])
def test_license_layout_and_scroll_in_small_work_area(qtbot, tmp_path, area):
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.show()
    dlg = LicenseDialog(parent)
    dlg.fit_to_area(area)
    dlg.open()
    qtbot.wait(30)
    assert dlg.width() <= area.width() - 24
    assert dlg.height() <= area.height() - 24
    for control in (dlg.component_combo, dlg.document, dlg.copy_button, dlg.close_button):
        assert dlg.rect().contains(control.geometry())
    assert dlg.document.viewport().height() > 80
    scrollbar = dlg.document.verticalScrollBar()
    assert scrollbar.maximum() > 0
    scrollbar.setValue(scrollbar.maximum())
    assert scrollbar.value() == scrollbar.maximum()
    output = Path(os.environ.get("CLIMATENOTE_TEST_APPDATA", str(tmp_path))).parent
    output.mkdir(parents=True, exist_ok=True)
    assert dlg.grab().save(str(output / f"license-{area.width()}x{area.height()}.png"))
    qtbot.mouseClick(dlg.close_button, Qt.LeftButton)
