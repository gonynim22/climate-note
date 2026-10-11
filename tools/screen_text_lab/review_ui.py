"""개발용 자료 등록 창. 제품 앱/DB/OCR을 import하거나 자동 실행하지 않는다."""
from copy import deepcopy

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget)

from .corpus import CorpusError
from .review_store import ReviewSession, parse_table


def combo(items):
    widget = QComboBox()
    for label, value in items:
        widget.addItem(label, value)
    return widget


SPLITS = [("개발용", "dev"), ("최종 평가용", "holdout")]
SOURCES = [("직접 캡처한 화면", "program_capture"), ("합성 시험 이미지", "synthetic"),
           ("출처 미확인 / 제공받은 이미지", "user_supplied")]


class ImageView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QColor("#25282D"))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setMinimumSize(240, 160)
        self.setAccessibleName("등록한 원본 이미지, 확대 후 드래그로 이동")

    def load(self, path):
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            raise CorpusError("원본 이미지를 표시할 수 없습니다.")
        self.scene().clear()
        self.scene().addPixmap(pixmap)
        self.setSceneRect(0, 0, pixmap.width(), pixmap.height())
        self.fit()

    def fit(self):
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def zoom(self, factor):
        scale = self.transform().m11() * factor
        if .02 <= scale <= 16:
            self.scale(factor, factor)


class RegistrationDialog(QDialog):
    def __init__(self, count, parent):
        super().__init__(parent)
        self.setWindowTitle("이미지 등록 조건")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        hint = QLabel(f"선택한 PNG {count}개에 적용할 조건입니다.\n같은 문서의 배율·테마 변형은 같은 원본 그룹으로 묶어 주세요.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        self.group = QLineEdit()
        self.group.setPlaceholderText("예: 터미널-작업로그-001")
        self.source = combo(SOURCES)
        self.split = combo(SPLITS)
        self.app_name = QLineEdit()
        self.app_name.setPlaceholderText("예: Windows Terminal (모르면 비워 두기)")
        form.addRow("원본 그룹", self.group)
        form.addRow("출처", self.source)
        form.addRow("용도", self.split)
        form.addRow("프로그램", self.app_name)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("등록")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.group.textChanged.connect(lambda text: buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(text.strip())))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ReviewWindow(QMainWindow):
    def __init__(self, directory=None, *, output_root=None):
        super().__init__()
        self.session = ReviewSession(directory)
        self.output_root = output_root
        self.current_id = None
        self.form_dirty = False
        self.loading = False
        self.setWindowTitle("화면 글자 따기 · 진단 자료 검토")
        self.resize(1280, 850)
        self.setMinimumSize(850, 580)
        font = QFont("Malgun Gothic")
        font.setPixelSize(13)
        self.setFont(font)
        self.setStyleSheet("""
            QMainWindow, QWidget#root { background: #F4F2EE; color: #24282E; }
            QLabel#heading { font-size: 23px; font-weight: 700; }
            QLabel#muted { color: #62676E; }
            QPushButton { padding: 7px 12px; background: #FFFFFF; border: 1px solid #CDCAC4; border-radius: 5px; }
            QPushButton:hover { background: #EDE9E2; }
            QPushButton#primary { background: #B74617; color: white; border-color: #B74617; font-weight: 700; }
            QPushButton:disabled { color: #929292; background: #EEECE8; }
            QLineEdit, QPlainTextEdit, QComboBox, QListWidget { background: white; color: #24282E; border: 1px solid #CDCAC4; border-radius: 3px; padding: 5px; selection-background-color: #FFD7BC; selection-color: #24282E; }
            QListWidget::item { padding: 9px 5px; border-bottom: 1px solid #EEECE8; }
            QListWidget::item:selected { background: #FFE5D4; color: #3D281E; }
            QSplitter::handle { background: #DEDAD2; }
        """)
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 18, 20, 12)
        header = QHBoxLayout()
        title = QLabel("진단 자료 검토")
        title.setObjectName("heading")
        header.addWidget(title)
        header.addStretch()
        self.open_button = QPushButton("자료 열기")
        self.open_button.clicked.connect(self.open_corpus)
        self.add_button = QPushButton("PNG 추가")
        self.add_button.clicked.connect(self.choose_images)
        self.save_button = QPushButton("새 버전 저장")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_version)
        for button in (self.open_button, self.add_button, self.save_button):
            header.addWidget(button)
        layout.addLayout(header)
        intro = QLabel("원본과 정답을 대조하고, 확인한 사례를 평가에 사용하세요. Ctrl+S: 새 버전 저장")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        split = QSplitter()
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 10, 10, 0)
        self.count_label = QLabel()
        sidebar_layout.addWidget(self.count_label)
        self.search = QLineEdit()
        self.search.setPlaceholderText("파일명·정답·그룹 검색")
        self.search.setAccessibleName("사례 검색")
        self.search.textChanged.connect(self.filter_list)
        sidebar_layout.addWidget(self.search)
        self.filter = combo([("모든 사례", "all"), ("검토 필요", "unreviewed"), ("검토 완료 / 생성 정답", "reviewed")])
        self.filter.currentIndexChanged.connect(self.filter_list)
        sidebar_layout.addWidget(self.filter)
        self.case_list = QListWidget()
        self.case_list.setAccessibleName("등록한 사례 목록")
        self.case_list.currentItemChanged.connect(self.change_case)
        sidebar_layout.addWidget(self.case_list)
        split.addWidget(sidebar)
        preview = QWidget()
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(10, 10, 10, 0)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("원본 이미지"))
        controls.addStretch()
        self.image = ImageView()
        for label, callback in (("−", lambda: self.image.zoom(.8)), ("+", lambda: self.image.zoom(1.25)),
                                ("100%", self.image.resetTransform), ("맞춤", self.image.fit)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        preview_layout.addLayout(controls)
        preview_layout.addWidget(self.image, 1)
        self.image_info = QLabel("PNG 추가로 시작하세요. 이미지는 원본 파일을 그대로 보존합니다.")
        self.image_info.setWordWrap(True)
        self.image_info.setObjectName("muted")
        preview_layout.addWidget(self.image_info)
        split.addWidget(preview)
        self.editor = QWidget()
        form_layout = QVBoxLayout(self.editor)
        form_layout.setContentsMargins(12, 10, 0, 0)
        form_layout.addWidget(QLabel("문자 정답 · 공백과 줄바꿈까지 그대로"))
        self.text = QPlainTextEdit()
        self.text.setMinimumHeight(135)
        self.text.setMaximumHeight(180)
        self.text.setPlaceholderText("화면에 실제로 보이는 글자를 입력하거나 원문에서 붙여 넣으세요.")
        self.text.setAccessibleName("문자 정답")
        form_layout.addWidget(self.text)
        self.table_enabled = QCheckBox("표 구조도 평가")
        form_layout.addWidget(self.table_enabled)
        self.table = QPlainTextEdit()
        self.table.setMinimumHeight(90)
        self.table.setMaximumHeight(120)
        self.table.setPlaceholderText("셀은 Tab, 행은 Enter로 구분합니다. 스프레드시트에서 붙여 넣을 수 있습니다.")
        self.table.setAccessibleName("표 정답 TSV")
        self.table.setTabChangesFocus(False)
        form_layout.addWidget(self.table)
        form = QFormLayout()
        self.group = QLineEdit()
        self.split = combo(SPLITS)
        form.addRow("원본 그룹", self.group)
        form.addRow("용도", self.split)
        self.tag_fields = {}
        for key, label, hint in (("source_app", "프로그램", "Windows Terminal 등"),
                                 ("category", "내용 종류", "cli / 문서 / 표 / 웹 등"),
                                 ("theme", "테마", "dark / light 등"),
                                 ("windows_scale", "Windows 배율", "예: 125%"),
                                 ("app_zoom", "앱 확대율", "예: 100%"),
                                 ("font", "글꼴", "예: Cascadia Mono"),
                                 ("font_px", "글자 크기(px)", "모르면 비워 두기")):
            field = QLineEdit()
            field.setPlaceholderText(hint)
            self.tag_fields[key] = field
            form.addRow(label, field)
        form_layout.addLayout(form)
        form_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self.editor)
        self.review_panel = QWidget()
        panel_layout = QVBoxLayout(self.review_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(scroll, 1)
        footer = QVBoxLayout()
        footer.setContentsMargins(12, 8, 0, 0)
        self.blank = QCheckBox("글자 없는 화면으로 확인")
        self.reviewed = QCheckBox("원본을 대조해 정답 확인 완료")
        footer.addWidget(self.blank)
        footer.addWidget(self.reviewed)
        note = QLabel("미검토 사례는 점수에서 제외됩니다. 정답을 바꾸면 다시 확인해 주세요.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        footer.addWidget(note)
        self.next_button = QPushButton("다음 검토 필요 사례 →")
        self.next_button.clicked.connect(self.next_unreviewed)
        footer.addWidget(self.next_button)
        panel_layout.addLayout(footer)
        split.addWidget(self.review_panel)
        split.setSizes([235, 580, 405])
        split.setChildrenCollapsible(False)
        layout.addWidget(split, 1)
        self.review_panel.setEnabled(False)
        self.table.hide()
        self.text.textChanged.connect(self.truth_changed)
        self.table.textChanged.connect(self.truth_changed)
        self.table_enabled.toggled.connect(self.truth_changed)
        self.blank.toggled.connect(self.truth_changed)
        self.reviewed.toggled.connect(self.mark_dirty)
        self.group.textChanged.connect(self.mark_dirty)
        self.split.currentIndexChanged.connect(self.mark_dirty)
        for field in self.tag_fields.values():
            field.textChanged.connect(self.mark_dirty)
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self.save_version)
        self.rebuild_list()
        if self.case_list.count():
            self.case_list.setCurrentRow(0)
        QTimer.singleShot(0, self.image.fit)

    def mark_dirty(self, *_):
        if not self.loading:
            self.form_dirty = True
            self.statusBar().showMessage("저장 전 변경 사항이 있습니다. Ctrl+S로 새 버전을 저장하세요.")

    def truth_changed(self, *_):
        self.table.setEnabled(self.table_enabled.isChecked())
        self.table.setVisible(self.table_enabled.isChecked())
        if not self.loading:
            self.reviewed.setChecked(False)
            self.mark_dirty()

    def commit_form(self):
        if self.current_id is None or not self.form_dirty:
            return
        case = next(case for case in self.session.cases if case["case_id"] == self.current_id)
        tags = deepcopy(case["tags"])
        for key, field in self.tag_fields.items():
            value = field.text().strip()
            if value == str(tags.get(key, "")):
                continue
            if value:
                tags[key] = value
            else:
                tags.pop(key, None)
        self.session.update(self.current_id, text=self.text.toPlainText(),
            table=parse_table(self.table.toPlainText()) if self.table_enabled.isChecked() else None,
            group=self.group.text(), split=self.split.currentData(), tags=tags,
            reviewed=self.reviewed.isChecked(), blank_confirmed=self.blank.isChecked())
        self.form_dirty = False

    def show_error(self, error):
        QMessageBox.warning(self, "저장/등록 확인", str(error))

    def rebuild_list(self):
        selected = self.current_id
        self.case_list.blockSignals(True)
        self.case_list.clear()
        for case in self.session.cases:
            label = "확인" if case["review_status"] != "unreviewed" else "미검토"
            name = case.get("provenance", {}).get("original_name", case["case_id"])
            item = QListWidgetItem(f"{label}  {name}\n{case['source_group_id']}")
            item.setData(Qt.ItemDataRole.UserRole, case["case_id"])
            self.case_list.addItem(item)
            if case["case_id"] == selected:
                self.case_list.setCurrentItem(item)
        self.case_list.blockSignals(False)
        checked = sum(case["review_status"] != "unreviewed" for case in self.session.cases)
        self.count_label.setText(f"{len(self.session.cases)}개 등록 · {checked}개 확인")
        self.filter_list()

    def filter_list(self, *_):
        query, state = self.search.text().casefold().strip(), self.filter.currentData()
        for index, case in enumerate(self.session.cases):
            item = self.case_list.item(index)
            haystack = (item.text() + " " + case["expected"]["text"]).casefold()
            matches_state = state == "all" or (case["review_status"] == "unreviewed") == (state == "unreviewed")
            item.setHidden(not (query in haystack and matches_state))

    def change_case(self, current, previous):
        if current is None:
            return
        try:
            self.commit_form()
            case_id = current.data(Qt.ItemDataRole.UserRole)
            self.image.load(self.session.paths[case_id])
        except (OSError, ValueError) as error:
            self.case_list.blockSignals(True)
            self.case_list.setCurrentItem(previous)
            self.case_list.blockSignals(False)
            self.show_error(error)
            return
        self.current_id = case_id
        case = next(case for case in self.session.cases if case["case_id"] == case_id)
        self.loading = True
        self.text.setPlainText(case["expected"]["text"])
        table = case["expected"].get("table")
        self.table_enabled.setChecked(table is not None)
        self.table.setPlainText("\n".join("\t".join(row) for row in table) if table else "")
        self.table.setEnabled(table is not None)
        self.table.setVisible(table is not None)
        self.group.setText(case["source_group_id"])
        self.split.setCurrentIndex(self.split.findData(case["split"]))
        for key, field in self.tag_fields.items():
            field.setText(str(case["tags"].get(key, "")))
        self.blank.setChecked(not case["expected"]["text"].strip() and case["review_status"] != "unreviewed")
        self.reviewed.setChecked(case["review_status"] != "unreviewed")
        source_name = dict((value, label) for label, value in SOURCES)[case["source_kind"]]
        self.image_info.setText(f"{source_name} · {case['image_size'][0]} × {case['image_size'][1]} px\n{case_id}")
        self.loading = False
        self.form_dirty = False
        self.review_panel.setEnabled(True)
        self.rebuild_list()

    def next_unreviewed(self):
        try:
            self.commit_form()
        except (OSError, ValueError) as error:
            self.show_error(error)
            return
        self.rebuild_list()
        start = self.case_list.currentRow()
        count = self.case_list.count()
        for offset in range(1, count + 1):
            index = (start + offset) % count
            item = self.case_list.item(index)
            if not item.isHidden() and self.session.cases[index]["review_status"] == "unreviewed":
                self.case_list.setCurrentRow(index)
                return
        self.statusBar().showMessage("현재 검색/필터 범위에서 검토할 다음 사례가 없습니다.")

    def add_images(self, paths, **metadata):
        self.commit_form()
        added, skipped = self.session.add_pngs(paths, **metadata)
        self.rebuild_list()
        if added:
            self.case_list.setCurrentRow(self.case_list.count() - added)
        self.statusBar().showMessage(f"{added}개 등록 · 같은 이미지 {skipped}개 제외 · 새 버전 저장을 눌러 보존하세요.")
        return added, skipped

    def choose_images(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "시험에 사용할 PNG 선택", "", "PNG (*.png)")
        if not paths:
            return
        dialog = RegistrationDialog(len(paths), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            tags = {"source_app": dialog.app_name.text().strip()} if dialog.app_name.text().strip() else {}
            self.add_images(paths, group=dialog.group.text(), source_kind=dialog.source.currentData(),
                            split=dialog.split.currentData(), tags=tags)
        except (OSError, ValueError) as error:
            self.show_error(error)

    def save_version(self):
        try:
            self.commit_form()
            if not self.session.dirty and self.session.directory:
                self.statusBar().showMessage(f"변경 사항 없음 · {self.session.directory}")
                return True
            path = self.session.save(self.output_root)
            self.rebuild_list()
            self.statusBar().showMessage(f"저장 완료 · {path}")
            return True
        except (OSError, ValueError) as error:
            self.show_error(error)
            return False

    def allow_leave(self):
        if not (self.form_dirty or self.session.dirty):
            return True
        question = QMessageBox(self)
        question.setWindowTitle("검토 내용 저장")
        question.setText("저장하지 않은 검토 내용이 있습니다.")
        save = question.addButton("새 버전 저장", QMessageBox.ButtonRole.AcceptRole)
        discard = question.addButton("변경 버리기", QMessageBox.ButtonRole.DestructiveRole)
        question.addButton("돌아가기", QMessageBox.ButtonRole.RejectRole)
        question.exec()
        return self.save_version() if question.clickedButton() == save else question.clickedButton() == discard

    def open_corpus(self):
        if not self.allow_leave():
            return
        path = QFileDialog.getExistingDirectory(self, "manifest.json이 들어 있는 자료 폴더 선택")
        if not path:
            return
        try:
            session = ReviewSession(path)
        except (OSError, ValueError) as error:
            self.show_error(error)
            return
        self.session = session
        self.current_id = None
        self.form_dirty = False
        self.rebuild_list()
        self.case_list.setCurrentRow(0)
        self.statusBar().showMessage(str(session.directory))

    def closeEvent(self, event):
        if self.allow_leave():
            event.accept()
        else:
            event.ignore()


def launch(directory=None):
    app = QApplication.instance() or QApplication([])
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    window = ReviewWindow(directory)
    window.show()
    return app.exec()
