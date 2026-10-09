"""한글이 설치된 PC의 HWP → HWPX 변환 창. 목록·결과는 메모리 전용."""
from dataclasses import dataclass
import os
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QGraphicsDropShadowEffect,
    QHeaderView, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from hwp_conversion import ConversionError, detect_environment
from hwp_conversion_runner import ConversionRunner
from ui_mini_app_frame import MiniAppTitleBar, mini_app_icon_path

WINDOW_WIDTH, WINDOW_HEIGHT, SHADOW_MARGIN = 480, 620, 24
MAX_FILES = 100


@dataclass
class ConversionEntry:
    source: Path
    state: str = "대기"
    detail: str = ""
    output: str = ""


class DocumentConverterWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setObjectName("documentConverter")
        self.setWindowTitle("문서 형식 변환 · 기후노트")
        self.setAccessibleName("문서 형식 변환")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        font = QFont(self.font())
        font.setPixelSize(13)
        self.setFont(font)
        self.entries = []
        self.output_directory = None
        self._dialog = None
        self._queue = []
        self._current = None
        self._disposed = False
        self._placed = False
        self._drag_origin = None
        self.environment = detect_environment()
        self.runner = ConversionRunner(self)
        self.runner.finished.connect(self._converted)
        self._next_timer = QTimer(self)
        self._next_timer.setSingleShot(True)
        self._next_timer.timeout.connect(self._run_next)
        self.setStyleSheet("""
            QWidget { color:#292C33; }
            QWidget#documentSurface { background:#FDFDFB; border-radius:16px; }
            QPushButton { background:white; border:1px solid #CDD5E0; border-radius:6px; padding:5px 8px; }
            QPushButton:hover { background:#EDF3FB; border-color:#91AACA; }
            QPushButton:focus { border:1px solid #315C98; }
            QPushButton:disabled { color:#959CA6; background:#F3F4F6; }
            QPushButton#convertStart { background:#2563EB; color:white; border:0; font-weight:bold; }
            QPushButton#convertStart:disabled { background:#A9C1F2; color:#FFFFFF; }
            QTreeWidget { background:white; border:1px solid #DDE1E9; border-radius:8px; }
            QTreeWidget::item { height:32px; }
            QHeaderView::section { background:#F5F7FA; color:#4E5663; border:0; padding:7px; }
            QProgressBar { border:0; background:#EEF1F5; border-radius:5px; text-align:center; height:16px; }
            QProgressBar::chunk { background:#A9C1F2; border-radius:5px; }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        self.surface = QWidget(self)
        self.surface.setObjectName("documentSurface")
        self.surface.setAttribute(Qt.WA_StyledBackground)
        outer.addWidget(self.surface)
        shadow = QGraphicsDropShadowEffect(self.surface)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(24, 46, 76, 80))
        self.surface.setGraphicsEffect(shadow)
        surface_layout = QVBoxLayout(self.surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)
        # 미니앱 공용 어두운 제목줄. header는 끌기 처리에 쓰는 기존 이름이다.
        self.title_bar = MiniAppTitleBar("문서 형식 변환", mini_app_icon_path("document_converter"), self.close, self.surface)
        self.header = self.title_bar
        self.title_label = self.title_bar.title_label
        self.close_button = self.title_bar.close_button
        self.close_button.installEventFilter(self)
        self.title_bar.installEventFilter(self)
        surface_layout.addWidget(self.title_bar)
        content = QWidget(self.surface)
        surface_layout.addWidget(content, 1)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 12, 18, 16)
        layout.setSpacing(10)
        self.content_layout = layout
        title = QLabel("HWP  →  HWPX")
        title.setStyleSheet("color:#172B4D;font-size:22px;font-weight:bold;")
        layout.addWidget(title)
        self.note = QLabel("한글 문서를 개방형 형식으로 변환합니다.\n원본과 기존 변환 파일은 그대로 보존합니다.")
        self.note.setStyleSheet("color:#687080;font-size:12px;")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        environment_row = QHBoxLayout()
        self.environment_label = QLabel()
        self.environment_label.setWordWrap(True)
        self.environment_label.setStyleSheet("color:#687080;font-size:12px;")
        environment_row.addWidget(self.environment_label, 1)
        self.check_button = self._button("다시 확인", self.refresh_environment)
        environment_row.addWidget(self.check_button)
        layout.addLayout(environment_row)
        actions = QHBoxLayout()
        self.add_button = self._button("파일 추가", self.select_files)
        self.remove_button = self._button("선택 제거", self.remove_selected)
        self.clear_button = self._button("목록 비우기", self.clear_entries)
        for button in (self.add_button, self.remove_button, self.clear_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.file_list = QTreeWidget()
        self.file_list.setHeaderLabels(["HWP 파일 · 끌어 넣기", "상태"])
        self.file_list.setRootIsDecorated(False)
        self.file_list.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.file_list.setMinimumHeight(80)
        self.file_list.setAcceptDrops(False)
        self.file_list.viewport().setAcceptDrops(False)
        self.file_list.header().setStretchLastSection(False)
        self.file_list.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_list.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.file_list.setColumnWidth(1, 76)
        self.file_list.setAccessibleName("변환할 HWP 파일 목록")
        layout.addWidget(self.file_list, 1)
        self.same_folder = QCheckBox("원본 파일과 같은 폴더에 저장")
        self.same_folder.setChecked(True)
        self.same_folder.toggled.connect(self._update_controls)
        layout.addWidget(self.same_folder)
        folder_row = QHBoxLayout()
        self.folder_label = QLabel("저장 폴더를 선택해 주세요")
        self.folder_label.setTextFormat(Qt.PlainText)
        self.folder_label.setMinimumWidth(0)
        self.folder_label.setWordWrap(True)
        self.folder_label.setStyleSheet("color:#687080;font-size:12px;")
        folder_row.addWidget(self.folder_label, 1)
        self.folder_button = self._button("폴더 선택", self.select_folder)
        folder_row.addWidget(self.folder_button)
        layout.addLayout(folder_row)
        self.progress = QProgressBar()
        self.progress.setFormat("%v / %m")
        layout.addWidget(self.progress)
        self.status_label = QLabel("HWP 파일을 추가하거나 이 창에 끌어 넣으세요. (최대 100개 / 파일당 100 MB)")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setStyleSheet("color:#687080;font-size:12px;")
        layout.addWidget(self.status_label)
        run_row = QHBoxLayout()
        self.start_button = self._button("변환 시작", self.start_conversion)
        self.start_button.setObjectName("convertStart")
        self.cancel_button = self._button("취소", self.cancel_conversion)
        self.retry_button = self._button("실패·취소 재시도", self.retry_failed)
        for button in (self.start_button, self.cancel_button, self.retry_button):
            button.setMinimumHeight(34)
            run_row.addWidget(button)
        layout.addLayout(run_row)
        self.open_button = self._button("선택한 결과의 저장 폴더 열기", self.open_output_folder)
        layout.addWidget(self.open_button)
        self.resize(WINDOW_WIDTH + SHADOW_MARGIN * 2, WINDOW_HEIGHT + SHADOW_MARGIN * 2)
        self._update_controls()

    def _button(self, label, callback):
        button = QPushButton(label)
        button.clicked.connect(callback)
        button.installEventFilter(self)
        return button

    def _allowed(self):
        owner = self.parentWidget()
        return (not self._disposed and self.isVisible() and self.isEnabled()
                and not getattr(owner, "_is_locked", False) and not getattr(owner, "_hidden_to_tray", False))

    @property
    def busy(self):
        return self.runner.busy or bool(self._queue) or self._next_timer.isActive()

    def refresh_environment(self):
        if not self.busy:
            self.environment = detect_environment()
            self._update_controls()

    def add_files(self, files):
        if not self._allowed() or self.busy:
            return
        existing = {os.path.normcase(str(entry.source)) for entry in self.entries}
        rejected = 0
        for name in files:
            path = Path(name).resolve()
            key = os.path.normcase(str(path))
            if path.suffix.lower() != ".hwp" or not path.is_file():
                rejected += 1
                continue
            if key in existing:
                continue
            if len(self.entries) >= MAX_FILES:
                rejected += 1
                continue
            existing.add(key)
            self.entries.append(ConversionEntry(path))
        self.status_label.setText(f"{len(self.entries)}개 파일 등록" + (f" · 지원 형식/개수 제한으로 {rejected}개 제외" if rejected else ""))
        self._render_entries()

    def select_files(self):
        self._select(False)

    def select_folder(self):
        self._select(True)

    def _select(self, folder):
        if not self._allowed() or self.busy or self._dialog is not None:
            return
        dialog = QFileDialog(self, "변환 파일 저장 폴더" if folder else "HWP 파일 추가")
        dialog.setFileMode(QFileDialog.Directory if folder else QFileDialog.ExistingFiles)
        if folder:
            dialog.setOption(QFileDialog.ShowDirsOnly)
        else:
            dialog.setNameFilter("한글 문서 (*.hwp *.HWP)")
        self._dialog = dialog

        def selected(paths):
            if self._dialog is not dialog or not self._allowed() or self.busy:
                return
            if folder and paths:
                self.output_directory = Path(paths[0]).resolve()
                self.folder_label.setText(self.output_directory.name or str(self.output_directory))
                self.folder_label.setToolTip(str(self.output_directory))
                self.same_folder.setChecked(False)
                self._update_controls()
            elif not folder:
                self.add_files(paths)

        def finished(_result):
            if self._dialog is dialog:
                self._dialog = None
            dialog.deleteLater()

        dialog.filesSelected.connect(selected)
        dialog.finished.connect(finished)
        dialog.open()

    def remove_selected(self):
        if self.busy:
            return
        indices = {self.file_list.indexOfTopLevelItem(item) for item in self.file_list.selectedItems()}
        self.entries = [entry for index, entry in enumerate(self.entries) if index not in indices]
        self._render_entries()

    def clear_entries(self):
        if not self.busy:
            self.entries.clear()
            self._render_entries()

    def start_conversion(self):
        if not self._allowed() or self.busy:
            return
        self.refresh_environment()
        if not self.environment.available or (not self.same_folder.isChecked() and self.output_directory is None):
            return
        self._queue = [index for index, entry in enumerate(self.entries) if entry.state == "대기"]
        self._run_next()

    def _run_next(self):
        if not self._allowed():
            self.cancel_conversion()
            return
        if not self._queue:
            self._update_controls()
            return
        self._current = self._queue.pop(0)
        entry = self.entries[self._current]
        entry.state, entry.detail = "변환 중", ""
        directory = entry.source.parent if self.same_folder.isChecked() else self.output_directory
        try:
            self.runner.start(entry.source, directory)
        except ConversionError as exc:
            self._converted(False, "", str(exc))
            return
        self.status_label.setText("변환 중입니다. 창을 숨기거나 닫으면 작업을 취소합니다.")
        self._render_entries()

    def _converted(self, ok, output, message):
        if self._disposed or self._current is None:
            return
        entry = self.entries[self._current]
        entry.state = "완료" if ok else ("취소" if message.startswith("취소됨") else "실패")
        entry.output, entry.detail = output, message
        self._current = None
        self.status_label.setText(message if not ok else "변환본을 저장했습니다. 표·그림·수식의 배치를 확인해 주세요.")
        if self._queue and self._allowed():
            self._next_timer.start(0)
        self._render_entries()

    def cancel_conversion(self):
        self._next_timer.stop()
        for index in self._queue:
            self.entries[index].state = "취소"
        self._queue.clear()
        self.runner.cancel()
        self._render_entries()

    def retry_failed(self):
        if self.busy or not self._allowed():
            return
        for entry in self.entries:
            if entry.state in ("실패", "취소"):
                entry.state, entry.detail = "대기", ""
        self.start_conversion()

    def _render_entries(self):
        self.file_list.clear()
        for entry in self.entries:
            item = QTreeWidgetItem([entry.source.name, entry.state])
            item.setToolTip(0, str(entry.source) + ("\n→ " + entry.output if entry.output else ""))
            item.setToolTip(1, entry.detail)
            self.file_list.addTopLevelItem(item)
        self._update_controls()

    def _update_controls(self):
        busy = self.busy
        for button in (self.add_button, self.remove_button, self.clear_button, self.check_button, self.same_folder):
            button.setEnabled(not busy)
        self.folder_button.setEnabled(not busy)
        self.folder_label.setEnabled(not self.same_folder.isChecked())
        if self.same_folder.isChecked():
            self.folder_label.setText("각 원본 파일의 폴더에 새 HWPX를 저장합니다")
            self.folder_label.setToolTip("")
        elif self.output_directory is not None:
            self.folder_label.setText(self.output_directory.name or str(self.output_directory))
            self.folder_label.setToolTip(str(self.output_directory))
        else:
            self.folder_label.setText("저장 폴더를 선택해 주세요")
        output_ready = self.same_folder.isChecked() or self.output_directory is not None
        ready = not busy and self.environment.available and output_ready
        self.start_button.setEnabled(ready and any(e.state == "대기" for e in self.entries))
        self.retry_button.setEnabled(ready and any(e.state in ("실패", "취소") for e in self.entries))
        self.cancel_button.setEnabled(busy)
        self.open_button.setEnabled(not busy and any(e.output for e in self.entries))
        self.environment_label.setText(self.environment.message)
        self.progress.setRange(0, max(1, len(self.entries)))
        self.progress.setFormat("%v / %m" if self.entries else "등록된 파일 없음")
        self.progress.setValue(sum(e.state in ("완료", "실패", "취소") for e in self.entries))

    def open_output_folder(self):
        if not self._allowed() or self.busy:
            return
        selected = self.file_list.currentIndex().row()
        entries = [self.entries[selected]] if 0 <= selected < len(self.entries) else reversed(self.entries)
        for entry in entries:
            if entry.output:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(entry.output).parent)))
                break

    def dragEnterEvent(self, event):
        if self._allowed() and not self.busy and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def show_near(self, anchor, available):
        if not self._placed:
            self.move(anchor.right() + 12, anchor.top())
            self._placed = True
        self.refresh_environment()
        self.fit_to_screen(available)
        self.show()
        self.raise_()
        self.activateWindow()
        self.add_button.setFocus()

    def fit_to_screen(self, available=None):
        if available is None:
            screen = QApplication.screenAt(self.frameGeometry().center()) or self.screen() or QApplication.primaryScreen()
            if screen is None:
                return
            available = screen.availableGeometry()
        margin = min(SHADOW_MARGIN, max(0, (available.width() - 420) // 2), max(0, (available.height() - 480) // 2))
        self.note.setVisible(available.height() >= 560)
        self.layout().setContentsMargins(margin, margin, margin, margin)
        self.content_layout.setSpacing(6 if available.height() < 560 else 10)
        shadow = self.surface.graphicsEffect()
        shadow.setEnabled(margin > 0)
        shadow.setBlurRadius(max(0, margin - 4))
        self.layout().activate()
        self.resize(min(WINDOW_WIDTH + margin * 2, available.width()), min(WINDOW_HEIGHT + margin * 2, available.height()))
        self.move(max(available.left(), min(self.x(), available.right() + 1 - self.width())),
                  max(available.top(), min(self.y(), available.bottom() + 1 - self.height())))

    def hide_owned_popups(self):
        if self._dialog is not None:
            dialog, self._dialog = self._dialog, None
            dialog.reject()

    def shutdown(self):
        self._disposed = True
        self._next_timer.stop()
        self._queue.clear()
        self.hide_owned_popups()
        self.runner.shutdown()

    def hideEvent(self, event):
        self._drag_origin = None
        self.hide_owned_popups()
        self.cancel_conversion()
        super().hideEvent(event)

    def event(self, event):
        if event.type() == QEvent.DeferredDelete:
            self.shutdown()
        return super().event(event)

    def eventFilter(self, watched, event):
        if isinstance(watched, QPushButton) and event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if not event.isAutoRepeat():
                watched.click()
            return True
        if watched in (self.header, self.title_label):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_origin = (event.globalPosition().toPoint(), self.pos())
                return True
            if event.type() == QEvent.MouseMove and self._drag_origin and event.buttons() & Qt.LeftButton:
                origin, position = self._drag_origin
                self.move(position + event.globalPosition().toPoint() - origin)
                return True
            if event.type() == QEvent.MouseButtonRelease and self._drag_origin:
                self._drag_origin = None
                self.fit_to_screen()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
