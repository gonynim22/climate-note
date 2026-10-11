"""자료 등록/검토 회귀. 작은 합성 PNG만 사용하며 실제 OCR/화면 캡처는 하지 않는다."""
from copy import deepcopy
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.timeout(20)

from tools.screen_text_lab.corpus import CorpusError, digest, load_corpus
from tools.screen_text_lab.metrics import score_case
from tools.screen_text_lab.review_store import ReviewSession, parse_table


def png(path, color="white"):
    from PIL import Image
    Image.new("RGB", (200, 80), color).save(path)
    return path


def session_with_image(tmp_path):
    source = png(tmp_path / "source.png")
    session = ReviewSession()
    session.add_pngs([source], group="문서-1", source_kind="synthetic", tags={"font_px": 16})
    return session, source


def update(session, **values):
    case = session.cases[0]
    args = dict(text="원본 정답\n공백  유지", table=None, group=case["source_group_id"],
                split=case["split"], tags=case["tags"], reviewed=True)
    args.update(values)
    session.update(case["case_id"], **args)


def test_review_versions_round_trip_and_preserve_original(tmp_path):
    session, source = session_with_image(tmp_path)
    before = digest(source)
    assert session.cases[0]["review_status"] == "unreviewed"
    assert score_case(session.cases[0], {"text": "anything"}) is None
    update(session, table=[["A", ""], ["B", "2"]])
    first = session.save(tmp_path / "versions")
    first_hashes = {p.relative_to(first).as_posix(): digest(p) for p in first.rglob("*") if p.is_file()}
    reopened = ReviewSession(first)
    assert reopened.cases[0]["expected"] == {"text": "원본 정답\n공백  유지", "table": [["A", ""], ["B", "2"]]}
    update(reopened, text="새 정답", reviewed=False)
    second = reopened.save(tmp_path / "versions")
    assert first != second and digest(source) == before
    assert {p.relative_to(first).as_posix(): digest(p) for p in first.rglob("*") if p.is_file()} == first_hashes
    loaded = load_corpus(second)
    assert loaded.cases[0]["review_status"] == "unreviewed"
    assert loaded.manifest["parent_dataset"]["manifest_sha256"] == first_hashes["manifest.json"]
    assert not list((tmp_path / "versions").glob(".pending-*"))


def test_bulk_registration_is_all_or_nothing_and_skips_exact_duplicates(tmp_path):
    session, source = session_with_image(tmp_path)
    other = png(tmp_path / "second.png", "black")
    broken = tmp_path / "bad.png"
    broken.write_text("not a PNG", encoding="utf-8")
    before = deepcopy(session.cases)
    with pytest.raises(OSError):
        session.add_pngs([other, broken], group="new")
    assert session.cases == before
    assert session.add_pngs([source, other, other], group="new") == (1, 2)
    assert len(session.cases) == 2
    with pytest.raises(CorpusError, match="분할"):
        session.add_pngs([other], group="new", split="holdout")


@pytest.mark.parametrize("cause", ["changed_image", "changed_manifest", "copy_failure", "split_leak"])
def test_failed_save_preserves_inputs_and_in_memory_edits(tmp_path, monkeypatch, cause):
    from tools.screen_text_lab import review_store
    session, source = session_with_image(tmp_path)
    update(session)
    first = session.save(tmp_path / "versions")
    original = (first / "manifest.json").read_bytes()
    update(session, text="검토 중 정답")
    if cause == "changed_image":
        png(session.paths[session.cases[0]["case_id"]], "blue")
    elif cause == "changed_manifest":
        (first / "manifest.json").write_bytes(original + b"\n")
    elif cause == "copy_failure":
        def fail(*args):
            raise PermissionError("write failed")
        monkeypatch.setattr(review_store.shutil, "copyfile", fail)
    else:
        second = png(tmp_path / "holdout.png", "black")
        session.add_pngs([second], group="other", split="holdout")
        case = session.cases[1]
        session.update(case["case_id"], text="검토 중 정답", table=None, group="other", split="holdout",
                       tags={}, reviewed=True)
    with pytest.raises((OSError, ValueError)):
        session.save(tmp_path / "versions")
    assert session.cases[0]["expected"]["text"] == "검토 중 정답" and session.dirty
    assert session.directory == first
    assert len(list((tmp_path / "versions").iterdir())) == 1
    assert (first / "manifest.json").read_bytes() == original + (b"\n" if cause == "changed_manifest" else b"")
    assert source.is_file()


def test_blank_requires_explicit_confirmation_and_table_keeps_empty_cells(tmp_path):
    session, _ = session_with_image(tmp_path)
    with pytest.raises(CorpusError, match="빈 정답"):
        update(session, text="")
    update(session, text="", blank_confirmed=True)
    assert session.cases[0]["review"]["blank_confirmed"]
    assert parse_table("A\t\r\nB\t2") == [["A", ""], ["B", "2"]]
    assert parse_table("A\tB\n\t") == [["A", "B"], ["", ""]]
    with pytest.raises(CorpusError, match="열 수"):
        parse_table("A\tB\nC")


def test_existing_annotations_and_generated_status_survive_metadata_edit(tmp_path):
    session, _ = session_with_image(tmp_path)
    update(session)
    case = session.cases[0]
    case.update(review_status="generated", regions=[{"box": [0, 0, 10, 10], "text": "원본"}])
    case["tags"]["custom_flag"] = True
    first = session.save(tmp_path / "versions")
    reopened = ReviewSession(first)
    update(reopened, tags={**case["tags"], "theme": "light"})
    assert reopened.cases[0]["review_status"] == "generated"
    assert reopened.cases[0]["regions"] == case["regions"]
    assert reopened.cases[0]["tags"]["custom_flag"] is True


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from tools.screen_text_lab.review_ui import ReviewWindow
    win = ReviewWindow(output_root=tmp_path / "versions")
    def cleanup(widget):
        # pytest-qt는 fixture finalizer보다 먼저 창을 닫는다.
        widget.form_dirty = False
        widget.session.dirty = False
    qtbot.addWidget(win, before_close_func=cleanup)
    errors = []
    monkeypatch.setattr(win, "show_error", errors.append)
    win.test_errors = errors
    win.show()
    qtbot.waitExposed(win)
    return win


def test_ui_register_edit_navigate_save_reopen_and_invalidate_review(window, tmp_path, qtbot):
    from PySide6.QtCore import Qt
    source = png(tmp_path / "one.png")
    second = png(tmp_path / "two.png", "black")
    window.add_images([source, second], group="group", source_kind="synthetic")
    first_id = window.current_id
    window.text.setPlainText("커밋 / commit\n공백  보존")
    window.reviewed.setChecked(True)
    qtbot.mouseClick(window.next_button, Qt.MouseButton.LeftButton)
    assert window.current_id != first_id
    assert window.session.cases[0]["review_status"] == "reviewed"
    window.text.setPlainText("두 번째")
    window.table_enabled.setChecked(True)
    window.table.setPlainText("A\tB\n1\t")
    window.reviewed.setChecked(True)
    qtbot.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    assert not window.test_errors
    corpus = load_corpus(window.session.directory)
    assert corpus.cases[0]["expected"]["text"] == "커밋 / commit\n공백  보존"
    assert corpus.cases[1]["expected"]["table"] == [["A", "B"], ["1", ""]]
    assert not window.session.dirty and not window.form_dirty
    window.text.insertPlainText("수정")
    assert not window.reviewed.isChecked()
    window.commit_form()
    assert window.session.cases[1]["review_status"] == "unreviewed"


def test_ui_invalid_input_keeps_selection_and_failed_save_keeps_edits(window, tmp_path, monkeypatch):
    window.add_images([png(tmp_path / "a.png"), png(tmp_path / "b.png", "black")], group="group")
    original_id = window.current_id
    window.text.setPlainText("유지할 원문")
    window.table_enabled.setChecked(True)
    window.table.setPlainText("A\tB\nC")
    window.case_list.setCurrentRow(1)
    assert window.current_id == original_id and window.case_list.currentRow() == 0
    assert window.text.toPlainText() == "유지할 원문"
    assert len(window.test_errors) == 1
    window.table_enabled.setChecked(False)
    def fail(root):
        raise PermissionError("disk full")
    monkeypatch.setattr(window.session, "save", fail)
    assert window.save_version() is False
    assert window.text.toPlainText() == "유지할 원문" and window.session.dirty


def test_ui_filter_zoom_and_small_window(window, tmp_path, qtbot):
    from PySide6.QtCore import QRect, QPoint
    window.add_images([png(tmp_path / "first.png"), png(tmp_path / "second.png", "black")], group="group")
    window.text.setPlainText("첫 정답")
    window.reviewed.setChecked(True)
    window.next_unreviewed()
    window.filter.setCurrentIndex(window.filter.findData("unreviewed"))
    assert window.case_list.item(0).isHidden() and not window.case_list.item(1).isHidden()
    window.search.setText("no match")
    assert window.case_list.item(1).isHidden()
    window.search.clear()
    scale = window.image.transform().m11()
    window.image.zoom(1.25)
    assert window.image.transform().m11() == pytest.approx(scale * 1.25)
    window.resize(850, 580)
    qtbot.wait(30)
    for button in (window.add_button, window.save_button, window.open_button, window.next_button, window.reviewed):
        rect = QRect(button.mapTo(window, QPoint()), button.size())
        assert window.rect().contains(rect)
        assert button.isVisible()
    assert window.image.viewport().width() >= 150


def test_ui_close_cancel_and_save_failure_stay_open(window, tmp_path, monkeypatch):
    from tools.screen_text_lab.review_ui import QMessageBox
    window.add_images([png(tmp_path / "source.png")], group="group")
    monkeypatch.setattr(QMessageBox, "exec", lambda box: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: next(b for b in box.buttons() if b.text() == "돌아가기"))
    assert not window.close() and window.isVisible()
    window.reviewed.setChecked(True)  # 빈 정답을 검토 완료하려고 시도
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: next(b for b in box.buttons() if b.text() == "새 버전 저장"))
    assert not window.close() and window.isVisible()
    assert window.test_errors


def test_review_window_render_evidence(window, tmp_path, qtbot):
    from PySide6.QtGui import QImage, QPainter, QColor, QFont
    picture = QImage(620, 190, QImage.Format.Format_RGB32)
    picture.fill(QColor("#18202B"))
    painter = QPainter(picture)
    font = QFont("Malgun Gothic")
    font.setPixelSize(19)
    painter.setFont(font)
    painter.setPen(QColor("#EDF2F9"))
    lines = ["PS D:\\Lab> git status", "커밋 전 변경 사항을 확인합니다.", "수정 파일: 3개  /  검토 완료: 2개", "환경 점검 결과: 0.125 mg/L"]
    for index, text in enumerate(lines):
        painter.drawText(24, 35 + index * 38, text)
    painter.end()
    path = tmp_path / "합성-터미널.png"
    assert picture.save(str(path))
    window.add_images([path], group="합성-문서-001", source_kind="synthetic",
                      tags={"source_app": "Qt 시험 렌더", "theme": "dark", "font_px": 19})
    window.text.setPlainText("\n".join(lines))
    window.reviewed.setChecked(True)
    assert window.save_version()
    qtbot.wait(30)
    evidence = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if evidence:
        directory = Path(evidence).parent
        assert window.grab().save(str(directory / "screen-text-review.png"))
        window.resize(850, 580)
        qtbot.wait(30)
        assert window.grab().save(str(directory / "screen-text-review-small.png"))
