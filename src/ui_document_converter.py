"""파일 넣기 → 추천 → 결과 비교. 목록·선택·미리보기는 메모리 전용."""
import base64
from dataclasses import dataclass, field
import os
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGraphicsDropShadowEffect, QGridLayout,
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

from app_paths import resource_root
from file_conversion import (
    FileConversionError, KINDS, MAX_FILES, MAX_SOURCE_BYTES, TARGETS, file_filter,
    kind_for, recommend, relation_groups, source_format,
)
from file_conversion_runner import FileConversionRunner
from hwp_conversion import ConversionError, detect_environment
from hwp_conversion_runner import ConversionRunner
from ui_converter_combo import ConverterCombo
from ui_mini_app_frame import MiniAppTitleBar, mini_app_icon_path

WINDOW_WIDTH, WINDOW_HEIGHT, SHADOW_MARGIN = 480, 620, 24


def font_at(size, bold=False):
    font = QFont("Malgun Gothic")
    font.setPixelSize(size)
    font.setBold(bold)
    return font


def size_text(count):
    return f"{count / (1024 * 1024):.1f} MB" if count >= 1024 * 1024 else f"{count / 1024:.1f} KB"


def label(text="", size=12, color="#687080", bold=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    widget.setFont(font_at(size, bold))
    widget.setStyleSheet(f"color:{color};background:transparent;border:0;")
    return widget


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


class ElidedLabel(QLabel):
    def __init__(self, size=12, bold=False, color="#687080"):
        super().__init__()
        self.setFont(font_at(size, bold))
        self.setTextFormat(Qt.PlainText)
        self.setStyleSheet(f"color:{color};background:transparent;border:0")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self.palette().windowText().color())
        painter.drawText(self.rect(), Qt.AlignVCenter,
                         self.fontMetrics().elidedText(self.text(), Qt.ElideRight, self.width()))


class Preview(QWidget):
    def __init__(self, width, height):
        super().__init__()
        self.setFixedSize(width, height)
        self.kind, self.format, self.image = "image", "", QImage()

    def set_entry(self, entry, output=False, target=None):
        self.kind = kind_for(entry.source)
        self.format = TARGETS[target].name if output and target else entry.metadata.get("format", source_format(entry.source)).upper()
        self.image = QImage()
        preview = entry.result_preview if output else entry.metadata.get("preview")
        if preview:
            self.image.loadFromData(base64.b64decode(preview), "PNG")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 8, 8)
        painter.setClipPath(path)
        kind = KINDS[self.kind]
        painter.fillRect(self.rect(), QColor(kind.background))
        if not self.image.isNull():
            size = self.image.size().scaled(self.size(), Qt.KeepAspectRatio)
            painter.drawImage(QRect((self.width()-size.width())//2, (self.height()-size.height())//2,
                                    size.width(), size.height()), self.image)
        else:
            painter.setPen(QPen(QColor(kind.color), 1.6))
            x, y = self.width()/2, self.height()/2
            painter.drawRoundedRect(QRectF(x-13, y-17, 26, 34), 3, 3)
            painter.setFont(font_at(10, True))
            painter.drawText(self.rect(), Qt.AlignCenter, self.format[:8])


class DropButton(QPushButton):
    def __init__(self):
        super().__init__()
        self.setAccessibleName("파일 고르기 또는 끌어 놓기")
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#F4F5F8"))
        painter.setPen(QPen(QColor("#2563EB" if self.hasFocus() or self.underMouse() else "#9AA6B5"), 1.5, Qt.DashLine))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 14, 14)
        painter.save()
        painter.translate(self.width()/2-62, self.height()/2-65)
        painter.setBrush(QColor("white"))
        painter.setPen(QPen(QColor("#9AA6B5"), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawRoundedRect(QRectF(0, 0, 36, 46), 5, 5)
        for y in (15, 23, 31):
            painter.drawLine(9, y, 27, y)
        painter.setPen(QPen(QColor("#6741D9"), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(47, 23, 73, 23)
        painter.drawLine(66, 16, 73, 23)
        painter.drawLine(66, 30, 73, 23)
        painter.setPen(Qt.NoPen)
        for x, height, color in ((88, 20, "#D3C6F9"), (102, 32, "#AF92F3"), (116, 44, "#9775FA")):
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRectF(x, 46-height, 9, height), 3, 3)
        painter.restore()
        painter.setPen(QColor("#1F2430"))
        painter.setFont(font_at(18, True))
        painter.drawText(QRect(0, self.height()//2+1, self.width(), 28), Qt.AlignCenter, "파일을 끌어 놓으세요")
        painter.setFont(font_at(13))
        painter.setPen(QColor("#687080"))
        painter.drawText(QRect(0, self.height()//2+35, self.width(), 24), Qt.AlignCenter, "또는 여기를 눌러 고르기")


class FormatButton(QPushButton):
    def __init__(self, target_id, card=False):
        super().__init__()
        self.target_id, self.card = target_id, card
        self.setCheckable(True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setFixedHeight(70 if card else 32)
        self.setText(TARGETS[target_id].name)
        self.setToolTip(TARGETS[target_id].description)
        self.toggled.connect(self._accessible)
        self._accessible()

    def _accessible(self):
        target = TARGETS[self.target_id]
        self.setAccessibleName(f"{target.name}, {target.tag}" + (", 선택됨" if self.isChecked() else ""))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        checked = self.isChecked()
        painter.setBrush(QColor("#EFF4FE" if checked else "#FFFFFF"))
        painter.setPen(QPen(QColor("#2563EB" if checked or self.hasFocus() else "#CDD5E0"), 2 if checked and self.card else 1))
        radius = 10 if self.card else 8
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), radius, radius)
        target = TARGETS[self.target_id]
        painter.setPen(QColor("#1D4ED8" if checked else "#1F2430"))
        painter.setFont(font_at(16 if self.card else 12, True))
        if not self.card:
            painter.drawText(self.rect(), Qt.AlignCenter, target.name)
            return
        text_rect = QRect(12, 10, self.width()-24-(20 if checked else 0), 25)
        painter.drawText(text_rect, Qt.AlignVCenter, painter.fontMetrics().elidedText(target.name, Qt.ElideRight, text_rect.width()))
        if checked:
            x, y = self.width()-20, 22
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#2563EB"))
            painter.drawEllipse(QPointF(x, y), 8, 8)
            painter.setPen(QPen(Qt.white, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(QPointF(x-3.5, y), QPointF(x-1, y+2.5))
            painter.drawLine(QPointF(x-1, y+2.5), QPointF(x+4, y-3))
        painter.setPen(QColor("#4E5663"))
        painter.setFont(font_at(11))
        painter.drawText(QRect(12, 39, self.width()-24, 18), Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(target.tag, Qt.ElideRight, self.width()-24))


class RelationMap(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(0, 100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName("사진, PDF, 한글, 표·글의 변환 가능 형식")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        scale = min(self.width()/416, self.height()/400)
        painter.translate((self.width()-416*scale)/2, (self.height()-400*scale)/2)
        painter.scale(scale, scale)
        y = 0
        for kind_id, rows in relation_groups():
            kind = KINDS[kind_id]
            center = y + ((len(rows)-1)*40+32)/2
            painter.setPen(QPen(QColor(kind.line), 2, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(120, center), QPointF(164, center))
            painter.drawLine(QPointF(164, y+16), QPointF(164, y+(len(rows)-1)*40+16))
            for offset, (name, tag) in enumerate(rows):
                top = y+offset*40
                painter.setPen(QPen(QColor(kind.line), 2, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(164, top+16, 207, top+16)
                painter.drawLine(202, top+12, 207, top+16)
                painter.drawLine(202, top+20, 207, top+16)
                painter.setPen(QPen(QColor("#DDE1E9"), 1))
                painter.setBrush(Qt.white)
                painter.drawRoundedRect(QRectF(208, top, 207, 32), 8, 8)
                painter.setPen(QColor("#292C33"))
                painter.setFont(font_at(12, True))
                painter.drawText(QRectF(218, top, 190, 32), Qt.AlignVCenter, name)
                width = painter.fontMetrics().horizontalAdvance(name)+6
                painter.setFont(font_at(12))
                painter.setPen(QColor("#687080"))
                painter.drawText(QRectF(218+width, top, 190-width, 32), Qt.AlignVCenter,
                                 painter.fontMetrics().elidedText(tag, Qt.ElideRight, max(0, 190-width)))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(kind.background))
            painter.drawRoundedRect(QRectF(0, center-28, 120, 56), 10, 10)
            painter.setPen(QColor(kind.color))
            painter.setFont(font_at(13, True))
            painter.drawText(QRectF(10, center-21, 100, 22), Qt.AlignVCenter, kind.name)
            painter.setFont(font_at(11))
            separator = " " if kind_id == "image" else " · "
            extensions = "HWP · 한글 필요" if kind_id == "hwp" else separator.join(ext.upper() for ext in kind.extensions if ext != "jpeg")
            painter.drawText(QRectF(10, center+2, 110, 19), Qt.AlignVCenter,
                             painter.fontMetrics().elidedText(extensions, Qt.ElideRight, 110))
            y += len(rows)*40+16


class Overlay(QWidget):
    """본문 안의 패널. 포커스·Esc·가림막 클릭을 패널 수명 안에서 소유한다."""
    def __init__(self, window, title, body):
        super().__init__(window.content)
        self.window = window
        self.setObjectName("converterOverlay")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet("QWidget#converterOverlay {background:rgba(23,24,29,128);}")
        self.panel = QFrame(self)
        self.panel.setObjectName("overlayPanel")
        self.panel.setStyleSheet("QFrame#overlayPanel {background:white;border:1px solid #DDE1E9;border-radius:14px;}")
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        header = QHBoxLayout()
        header.addWidget(label(title, 16, "#1F2430", True), 1)
        self.x_button = window._button("×", window.close_overlay)
        self.x_button.setFixedSize(28, 28)
        self.x_button.setAccessibleName(title + " 닫기")
        header.addWidget(self.x_button)
        layout.addLayout(header)
        layout.addWidget(body, 1)
        footer = QHBoxLayout()
        note = ElidedLabel()
        note.setText("원본은 그대로 두고 새 파일을 만들어요")
        footer.addWidget(note, 1)
        self.close_button = window._button("닫기", window.close_overlay)
        self.close_button.setFixedHeight(34)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)
        self.resize_to_body()
        QApplication.instance().installEventFilter(self)

    def resize_to_body(self):
        self.setGeometry(self.window.content.rect())
        self.panel.setGeometry(16, 16, max(1, self.width()-32), max(1, min(532, self.height()-32)))

    def mousePressEvent(self, event):
        if not self.panel.geometry().contains(event.position().toPoint()):
            self.window.close_overlay()

    def eventFilter(self, watched, event):
        if self.isVisible() and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.window.close_overlay()
                return True
            if event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
                buttons = [button for button in self.panel.findChildren(QPushButton) if button.isVisible() and button.isEnabled()]
                current = QApplication.focusWidget()
                index = buttons.index(current) if current in buttons else -1
                step = -1 if event.key() == Qt.Key_Backtab or event.modifiers() & Qt.ShiftModifier else 1
                buttons[(index+step) % len(buttons)].setFocus()
                return True
        return super().eventFilter(watched, event)


class RatioBars(QWidget):
    def __init__(self):
        super().__init__()
        self.source_bytes = self.output_bytes = 0
        self.setFixedHeight(54)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        maximum = max(1, self.source_bytes, self.output_bytes)
        for index, (name, count, color) in enumerate((("원본", self.source_bytes, "#C3CBD6"), ("결과", self.output_bytes, "#2563EB"))):
            y = index*28
            painter.setPen(QColor("#687080"))
            painter.setFont(font_at(11))
            painter.drawText(QRect(0, y, 34, 22), Qt.AlignVCenter, name)
            width = max(0, self.width()-128)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRectF(38, y+6, width*count/maximum, 10), 5, 5)
            painter.setPen(QColor("#292C33"))
            painter.setFont(font_at(12, True))
            painter.drawText(QRect(self.width()-86, y, 86, 22), Qt.AlignVCenter | Qt.AlignRight, size_text(count))


class ResultBadge(QWidget):
    def __init__(self):
        super().__init__()
        self.warning = False
        self.setFixedSize(28, 28)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#9A3412" if self.warning else "#1E7A45"))
        painter.drawEllipse(QRectF(0, 0, 28, 28))
        painter.setPen(QPen(Qt.white, 2.1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if self.warning:
            painter.drawLine(14, 7, 14, 16)
            painter.drawPoint(14, 21)
        else:
            painter.drawLine(8, 14, 12, 18)
            painter.drawLine(12, 18, 20, 10)


@dataclass
class ConversionEntry:
    source: Path
    state: str = "대기"
    detail: str = ""
    output: str = ""
    metadata: dict = field(default_factory=dict)
    output_bytes: int = 0
    output_count: int = 1
    result_preview: str = ""


class DocumentConverterWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setObjectName("documentConverter")
        self.setWindowTitle("파일 변환 · 기후노트")
        self.setAccessibleName("파일 변환")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setFont(font_at(13))
        self.entries = []
        self.output_directory = None
        self._dialog = self._overlay = None
        self._queue = []
        self._current = None
        self._disposed = self._placed = self._run_active = False
        self._drag_origin = None
        self._inspect_restart = False
        self._probe_generation = self._generation = 0
        self._run_indices = []
        self._settings = {}
        self.target_id = None
        self.environment = detect_environment()
        self.runner = ConversionRunner(self)
        self.runner.finished.connect(self._converted)
        self.file_runner = FileConversionRunner(self)
        self.file_runner.item_finished.connect(self._file_converted)
        self.file_runner.finished.connect(self._batch_finished)
        self.probe = FileConversionRunner(self)
        self.probe.item_finished.connect(self._inspected)
        self.probe.finished.connect(self._inspection_finished)
        self._next_timer = QTimer(self)
        self._next_timer.setSingleShot(True)
        self._next_timer.timeout.connect(self._run_next)
        self.setStyleSheet("""
            QWidget { color:#292C33; }
            QWidget#documentSurface { background:#FDFDFB; border-radius:16px; }
            QPushButton { background:white;border:1px solid #CDD5E0;border-radius:8px;padding:4px 8px;font-size:12px; }
            QPushButton:hover { background:#EFF4FE; }
            QPushButton:focus { border:2px solid #2563EB; }
            QPushButton:disabled { color:#9299A4;background:#F4F5F8; }
            QPushButton[primary="true"] { background:#2563EB;color:white;border:0;font-size:14px;font-weight:bold; }
            QPushButton[primary="true"]:disabled { background:#A9C1F2; }
            QPushButton[link="true"] { color:#2563EB;background:transparent;border:0;padding:2px 4px; }
            QPushButton[link="true"]:focus { border:1px solid #2563EB; }
            QFrame[card="true"] { background:white;border:1px solid #DDE1E9;border-radius:12px; }
            QWidget[gray="true"] { background:#F4F5F8;border-radius:10px; }
            QScrollArea { background:transparent;border:0; }
            QProgressBar { border:0;background:#EEF1F5;border-radius:4px; }
            QProgressBar::chunk { background:#2563EB;border-radius:4px; }
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
        self.title_bar = MiniAppTitleBar("파일 변환", mini_app_icon_path("document_converter"), self.close, self.surface)
        self.header, self.title_label, self.close_button = self.title_bar, self.title_bar.title_label, self.title_bar.close_button
        self.close_button.installEventFilter(self)
        self.title_bar.installEventFilter(self)
        surface_layout.addWidget(self.title_bar)
        self.content = QWidget(self.surface)
        self.content.installEventFilter(self)
        surface_layout.addWidget(self.content, 1)
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget()
        self.pages.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        content_layout.addWidget(self.pages)
        self._build_drop()
        self._build_pick()
        self._build_result()
        self.resize(WINDOW_WIDTH+SHADOW_MARGIN*2, WINDOW_HEIGHT+SHADOW_MARGIN*2)
        self._update_controls()

    def _button(self, text, callback, *, primary=False, link=False):
        button = QPushButton(text)
        button.setFont(font_at(14 if primary else 12, primary))
        button.setProperty("primary", primary)
        button.setProperty("link", link)
        button.clicked.connect(callback)
        button.installEventFilter(self)
        if primary:
            button.setFixedHeight(42)
        return button

    def _page(self, margins):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(*margins)
        layout.setSpacing(14)
        self.pages.addWidget(page)
        return page, layout

    def _build_drop(self):
        self.drop_page, layout = self._page((18, 18, 18, 18))
        self.add_button = DropButton()
        self.add_button.clicked.connect(self.select_files)
        self.add_button.installEventFilter(self)
        layout.addWidget(self.add_button, 1)
        self.drop_status = ElidedLabel()
        self.drop_status.hide()
        layout.addWidget(self.drop_status)
        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        for kind in KINDS.values():
            badge = label(kind.name, 11, kind.color, True)
            badge.setStyleSheet(f"color:{kind.color};background:{kind.background};border-radius:4px;padding:2px 7px;")
            bottom.addWidget(badge)
        bottom.addStretch()
        self.map_button = self._button("변환 관계도", self.open_map)
        self.map_button.setFixedHeight(32)
        self.map_button.setIcon(QIcon(str(resource_root() / "resources/icons/relation_map.svg")))
        self.map_button.setIconSize(QSize(16, 16))
        bottom.addWidget(self.map_button)
        layout.addLayout(bottom)

    def _build_pick(self):
        self.pick_page, layout = self._page((18, 14, 18, 16))
        self.content_layout = layout
        self.file_header = QFrame()
        self.file_header.setProperty("card", True)
        header = QHBoxLayout(self.file_header)
        header.setContentsMargins(10, 10, 10, 10)
        header.setSpacing(12)
        self.head_preview = Preview(44, 44)
        header.addWidget(self.head_preview)
        names = QVBoxLayout()
        names.setSpacing(3)
        self.file_name = ElidedLabel(14, True, "#292C33")
        self.file_info = ElidedLabel()
        names.addWidget(self.file_name)
        names.addWidget(self.file_info)
        header.addLayout(names, 1)
        self.list_button = self._button("목록", self.open_list, link=True)
        self.clear_button = self._button("다른 파일", self.clear_entries, link=True)
        header.addWidget(self.list_button)
        header.addWidget(self.clear_button)
        layout.addWidget(self.file_header)
        self.recommend_section = QWidget()
        section = QVBoxLayout(self.recommend_section)
        section.setContentsMargins(0, 0, 0, 0)
        section.setSpacing(6)
        section.addWidget(label("추천", 12, "#4E5663", True))
        self.recommend_layout = QHBoxLayout()
        self.recommend_layout.setSpacing(8)
        section.addLayout(self.recommend_layout)
        layout.addWidget(self.recommend_section)
        self.other_section = QWidget()
        section = QVBoxLayout(self.other_section)
        section.setContentsMargins(0, 0, 0, 0)
        section.setSpacing(6)
        section.addWidget(label("다른 형식", 12, "#4E5663", True))
        self.other_scroll = QScrollArea()
        self.other_scroll.setWidgetResizable(True)
        self.other_scroll.viewport().setAutoFillBackground(False)
        self.other_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.other_content = QWidget()
        self.other_content.setStyleSheet("background:transparent;")
        self.other_grid = QGridLayout(self.other_content)
        self.other_grid.setContentsMargins(0, 0, 0, 0)
        self.other_grid.setSpacing(6)
        for column in range(4):
            self.other_grid.setColumnStretch(column, 1)
        self.other_scroll.setWidget(self.other_content)
        section.addWidget(self.other_scroll)
        layout.addWidget(self.other_section)
        self.settings_box = QWidget()
        self.settings_box.setAttribute(Qt.WA_StyledBackground)
        self.settings_box.setProperty("gray", True)
        self.settings_box.setFixedHeight(96)
        settings_layout = QVBoxLayout(self.settings_box)
        settings_layout.setContentsMargins(12, 12, 12, 12)
        settings_layout.setSpacing(8)
        first = QHBoxLayout()
        first.setSpacing(8)
        self.setting_name = label("", 14, "#1F2430", True)
        self.setting_description = ElidedLabel(12, color="#4E5663")
        first.addWidget(self.setting_name)
        first.addWidget(self.setting_description, 1)
        self.check_button = self._button("다시 확인", self.refresh_environment)
        first.addWidget(self.check_button)
        settings_layout.addLayout(first)
        settings_layout.addStretch()
        row = QHBoxLayout()
        row.setSpacing(4)
        self.options_container = QWidget()
        self.options_layout = QHBoxLayout(self.options_container)
        self.options_layout.setContentsMargins(0, 0, 0, 0)
        self.options_layout.setSpacing(4)
        row.addWidget(self.options_container, 1)
        row.addWidget(label("저장", 12, "#4E5663"))
        self.save_combo = ConverterCombo()
        self.save_combo.setAccessibleName("결과 저장 위치")
        self.save_combo.setFixedWidth(96)
        self.save_combo.addItems(["원본 옆", "폴더 고르기…"])
        self.save_combo.activated.connect(self._save_selected)
        row.addWidget(self.save_combo)
        settings_layout.addLayout(row)
        layout.addWidget(self.settings_box)
        self.status_label = ElidedLabel()
        layout.addWidget(self.status_label)
        self.status_label.hide()
        layout.addStretch(1)
        self.start_button = self._button("바꾸기", self.start_conversion, primary=True)
        layout.addWidget(self.start_button)
        self.running_controls = QWidget()
        run_layout = QVBoxLayout(self.running_controls)
        run_layout.setContentsMargins(0, 0, 0, 0)
        run_layout.setSpacing(6)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(8)
        self.progress.setTextVisible(False)
        run_layout.addWidget(self.progress)
        row = QHBoxLayout()
        self.progress_label = label("", 12, "#1D4ED8", True)
        row.addWidget(self.progress_label, 1)
        self.cancel_button = self._button("취소", self.cancel_conversion)
        row.addWidget(self.cancel_button)
        run_layout.addLayout(row)
        layout.addWidget(self.running_controls)
        self.format_buttons = {}
        self.option_combos = {}

    def _build_result(self):
        self.result_page, layout = self._page((18, 18, 18, 16))
        heading = QHBoxLayout()
        heading.setSpacing(10)
        self.result_badge = ResultBadge()
        heading.addWidget(self.result_badge)
        self.result_title = label("", 18, "#1F2430", True)
        heading.addWidget(self.result_title, 1)
        layout.addLayout(heading)
        self.comparison = QFrame()
        self.comparison.setProperty("card", True)
        comparison = QVBoxLayout(self.comparison)
        comparison.setContentsMargins(14, 14, 14, 14)
        comparison.setSpacing(14)
        self.compare_content = QWidget()
        self.compare_layout = QVBoxLayout(self.compare_content)
        self.compare_layout.setContentsMargins(0, 0, 0, 0)
        comparison.addWidget(self.compare_content)
        self.bars = RatioBars()
        comparison.addWidget(self.bars)
        layout.addWidget(self.comparison)
        self.result_note = QWidget()
        self.result_note.setAttribute(Qt.WA_StyledBackground)
        self.result_note.setProperty("gray", True)
        note = QVBoxLayout(self.result_note)
        note.setContentsMargins(12, 12, 12, 12)
        note.setSpacing(6)
        self.folder_label = ElidedLabel(12, color="#292C33")
        note.addWidget(self.folder_label)
        self.preserve_label = label("원본은 그대로 두었어요. 결과 파일은 자동으로 열지 않아요.", 12)
        self.preserve_label.setWordWrap(True)
        note.addWidget(self.preserve_label)
        layout.addWidget(self.result_note)
        self.result_status = ElidedLabel()
        layout.addWidget(self.result_status)
        self.result_status.hide()
        layout.addStretch()
        self.again_button = self._button("같은 파일로 다른 형식도 만들기", self.back_to_pick, link=True)
        layout.addWidget(self.again_button, 0, Qt.AlignLeft)
        buttons = QHBoxLayout()
        self.open_button = self._button("저장 폴더 열기", self.open_output_folder)
        self.open_button.setFixedHeight(42)
        self.new_button = self._button("새 파일 넣기", self.clear_entries, primary=True)
        buttons.addWidget(self.open_button, 1)
        buttons.addWidget(self.new_button, 1)
        layout.addLayout(buttons)

    def _allowed(self):
        owner = self.parentWidget()
        return (not self._disposed and self.isVisible() and self.isEnabled()
                and not getattr(owner, "_is_locked", False) and not getattr(owner, "_hidden_to_tray", False))

    @property
    def busy(self):
        return self._run_active or self.runner.busy or self.file_runner.busy

    @property
    def kind(self):
        return kind_for(self.entries[0].source) if self.entries else None

    def _status(self, message):
        for widget in (self.status_label, self.drop_status):
            widget.setText(message)
            widget.setVisible(bool(message))

    def add_files(self, files):
        if not self._allowed() or self.busy or self._overlay is not None:
            return
        if self.pages.currentWidget() is self.result_page:
            self.clear_entries()
        existing = {os.path.normcase(str(entry.source)) for entry in self.entries}
        chosen_kind = self.kind
        rejected, mixed = {}, {}
        for name in files:
            try:
                path = Path(name).resolve()
                kind = kind_for(path)
                if kind is None or not path.is_file():
                    rejected["지원하지 않는 형식"] = rejected.get("지원하지 않는 형식", 0)+1
                    continue
                if chosen_kind is None:
                    chosen_kind = kind
                if kind != chosen_kind:
                    mixed[kind] = mixed.get(kind, 0)+1
                    continue
                key = os.path.normcase(str(path))
                if key in existing:
                    continue
                size = path.stat().st_size
                if size > MAX_SOURCE_BYTES:
                    rejected["100 MB 초과 파일"] = rejected.get("100 MB 초과 파일", 0)+1
                    continue
                if len(self.entries) >= MAX_FILES:
                    rejected["100개 초과 파일"] = rejected.get("100개 초과 파일", 0)+1
                    continue
            except OSError:
                rejected["읽을 수 없는 파일"] = rejected.get("읽을 수 없는 파일", 0)+1
                continue
            existing.add(key)
            self.entries.append(ConversionEntry(path, metadata={"bytes": size}))
        messages = [f"{reason} {count}개는 뺐어요" for reason, count in rejected.items()]
        if mixed:
            messages.insert(0, "한 번에 한 종류만 바꿀 수 있어요 · " +
                            ", ".join(f"{KINDS[key].name} {count}개는 뺐어요" for key, count in mixed.items()))
        self._status(" · ".join(messages))
        if self.entries:
            self.pages.setCurrentWidget(self.pick_page)
            self._generation += 1
            self._render_pick(reset=True)
            self._inspect()

    def _inspect(self):
        if self.probe.busy:
            self._inspect_restart = True
            self.probe.cancel()
            return
        self._inspect_restart = False
        if not self.entries or self.kind == "hwp" or not self._allowed():
            self._update_controls()
            return
        self._probe_generation = self._generation
        try:
            self.probe.start([entry.source for entry in self.entries], inspect_only=True)
        except FileConversionError as exc:
            self._status(str(exc))
        self._update_controls()

    def _inspected(self, index, result):
        if self._disposed or self._probe_generation != self._generation or not self._allowed():
            return
        entry = self.entries[index]
        if result.get("ok"):
            entry.metadata.update(result["metadata"])
            entry.metadata.pop("error", None)
        elif not result.get("cancelled"):
            entry.metadata["error"] = result.get("message", "파일을 읽을 수 없어요")

    def _inspection_finished(self, message):
        if self._disposed:
            return
        if self._inspect_restart:
            self._inspect()
            return
        if self._allowed() and self.entries:
            self._render_pick(reset=self.kind == "text")
            errors = [entry.metadata["error"] for entry in self.entries if "error" in entry.metadata]
            if errors or message:
                self._status(message or errors[0])
        self._update_controls()

    def _render_pick(self, reset=False):
        if not self.entries:
            return
        entry, count = self.entries[0], len(self.entries)
        self.head_preview.set_entry(entry)
        self.file_name.setText(entry.source.name + (f" 외 {count-1}개" if count > 1 else ""))
        formats = [e.metadata.get("format", source_format(e.source)) for e in self.entries]
        display = formats[0].upper() if len(set(formats)) == 1 else "여러 형식"
        if display == "CP949":
            display = "EUC-KR"
        elif display == "UTF8":
            display = "UTF-8"
        total = sum(e.metadata.get("bytes", 0) for e in self.entries)
        info = f"{display} {KINDS[self.kind].name}"
        if count > 1:
            info += f" {count}개 · 합계 {size_text(total)}"
        else:
            info += f" · {size_text(total)}"
            if "width" in entry.metadata:
                info += f" · {entry.metadata['width']} × {entry.metadata['height']}"
            if "pages" in entry.metadata:
                info += f" · {entry.metadata['pages']}쪽"
        self.file_info.setText(info)
        self.list_button.setVisible(count > 1)
        recs, others = recommend(self.kind, formats)
        previous = self.target_id
        self.format_buttons = {}
        clear_layout(self.recommend_layout)
        for target_id in recs:
            button = self._format_button(target_id, True)
            self.recommend_layout.addWidget(button, 1)
        self._render_other_formats(others)
        self.select_target(recs[0] if reset or previous not in recs+others else previous)

    def _format_button(self, target_id, card=False):
        button = FormatButton(target_id, card)
        button.installEventFilter(self)
        button.clicked.connect(lambda checked=False, key=target_id: self.select_target(key))
        self.format_buttons[target_id] = button
        return button

    def _render_other_formats(self, targets):
        clear_layout(self.other_grid)
        self.other_section.setVisible(bool(targets))
        for index, target_id in enumerate(targets):
            self.other_grid.addWidget(self._format_button(target_id), index//4, index % 4)
        content_height = ((len(targets)+3)//4)*38-6 if targets else 0
        self.other_content.setMinimumHeight(content_height)
        height = min(70, content_height)
        self.other_scroll.setFixedHeight(max(0, height))
        self.other_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if len(targets) > 8 else Qt.ScrollBarAlwaysOff)

    def select_target(self, target_id):
        if self.busy:
            return
        self.target_id = target_id
        for key, button in self.format_buttons.items():
            button.setChecked(key == target_id)
        target = TARGETS[target_id]
        self.setting_name.setText(target.name)
        self.setting_description.setText(target.description)
        clear_layout(self.options_layout)
        self.option_combos = {}
        values = self._settings.setdefault(target_id, {})
        for option in target.options:
            self.options_layout.addWidget(label(option.label, 12, "#4E5663"))
            combo = ConverterCombo()
            combo.setMinimumWidth(48)
            combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            combo.setAccessibleName(option.label)
            for text, value in option.choices:
                combo.addItem(text, value)
            combo.setCurrentIndex(max(0, combo.findData(values.get(option.key, option.choices[0][1]))))
            combo.currentIndexChanged.connect(lambda index, c=combo, k=option.key, t=target_id: self._settings[t].update({k: c.currentData()}))
            self.options_layout.addWidget(combo, 1)
            self.option_combos[option.key] = combo
        if not target.options:
            no_settings = ElidedLabel()
            no_settings.setText("따로 정할 것이 없어요")
            if target_id == "cp949":
                no_settings.setToolTip("EUC-KR 출력은 CP949 코덱을 사용해요")
            self.options_layout.addWidget(no_settings, 1)
        self._update_controls()

    def refresh_environment(self):
        if not self.busy:
            self.environment = detect_environment()
            self._update_controls()

    def _update_controls(self):
        busy = self.busy
        for widget in (self.file_header, self.recommend_section, self.other_section, self.settings_box):
            widget.setEnabled(not busy)
        self.running_controls.setVisible(busy)
        self.start_button.setVisible(not busy)
        unavailable = self.kind == "hwp" and not self.environment.available
        self.check_button.setVisible(unavailable)
        if self.target_id:
            target = TARGETS[self.target_id]
            self.setting_description.setText(self.environment.message if unavailable else target.description)
            text = target.button
            count = len(self.entries)
            if self.target_id == "pdf_bundle":
                text += f" · {count}장 → 1개"
            elif count > 1:
                text += f" · {count}개"
            self.start_button.setText(text)
        self.start_button.setEnabled(bool(self.entries) and not busy and not self.probe.busy and not unavailable)
        done = sum(entry.state in ("완료", "실패", "취소", "건너뜀") for entry in self.entries)
        self.progress.setRange(0, max(1, len(self.entries)))
        self.progress.setValue(done)
        self.progress_label.setText(f"바꾸는 중 {done} / {len(self.entries)}")
        self.open_button.setEnabled(not busy and any(entry.output for entry in self.entries))
        self.setAcceptDrops(not busy and self._overlay is None)

    def select_files(self):
        self._select(False)

    def select_folder(self):
        self._select(True)

    def _save_selected(self, index):
        if index == 0:
            self.output_directory = None
        elif index == 1:
            self.select_folder()
        self._sync_save_combo()

    def _sync_save_combo(self):
        while self.save_combo.count() > 2:
            self.save_combo.removeItem(2)
        if self.output_directory:
            self.save_combo.addItem(self.output_directory.name or str(self.output_directory))
            self.save_combo.setCurrentIndex(2)
        else:
            self.save_combo.setCurrentIndex(0)

    def _select(self, folder):
        if not self._allowed() or self.busy or self._dialog is not None or self._overlay is not None:
            return
        dialog = QFileDialog(self, "결과 저장 폴더" if folder else "변환할 파일 고르기")
        dialog.setFileMode(QFileDialog.Directory if folder else QFileDialog.ExistingFiles)
        if folder:
            dialog.setOption(QFileDialog.ShowDirsOnly)
        else:
            dialog.setNameFilter(file_filter())
        self._dialog = dialog

        def selected(paths):
            if self._dialog is not dialog or not self._allowed() or self.busy:
                return
            if folder and paths:
                self.output_directory = Path(paths[0]).resolve()
                self._sync_save_combo()
            elif not folder:
                self.add_files(paths)

        def finished(_result):
            if self._dialog is dialog:
                self._dialog = None
            dialog.deleteLater()

        dialog.filesSelected.connect(selected)
        dialog.finished.connect(finished)
        dialog.open()

    def clear_entries(self):
        if self.busy:
            return
        self.close_overlay()
        self._generation += 1
        self._inspect_restart = False
        self.probe.cancel()
        self.entries.clear()
        self.target_id = None
        self._status("")
        self.pages.setCurrentWidget(self.drop_page)
        self._update_controls()
        self.add_button.setFocus()

    def open_map(self):
        self._open_overlay("변환할 수 있는 형식", RelationMap())

    def open_list(self):
        if not self.entries:
            return
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        rows = QVBoxLayout(body)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(6)
        for entry in self.entries:
            row = QHBoxLayout()
            name = ElidedLabel(13, color="#292C33")
            name.setText(entry.source.name)
            row.addWidget(name, 1)
            remove = self._button("×", lambda checked=False, e=entry: self._remove_entry(e))
            remove.setAccessibleName(entry.source.name + " 빼기")
            remove.setFixedSize(28, 28)
            row.addWidget(remove)
            rows.addLayout(row)
        rows.addStretch()
        scroll.setWidget(body)
        self._open_overlay("넣은 파일", scroll)

    def _remove_entry(self, entry):
        if self.busy or entry not in self.entries:
            return
        self.close_overlay()
        self.entries.remove(entry)
        self._generation += 1
        if not self.entries:
            self.clear_entries()
        else:
            self._render_pick(reset=True)
            self._inspect()
            self.open_list()

    def _open_overlay(self, title, body):
        if not self._allowed() or self.busy or self._dialog is not None or self._overlay is not None:
            body.deleteLater()
            return
        self._overlay = Overlay(self, title, body)
        self.pages.setEnabled(False)
        self._overlay.show()
        self._overlay.raise_()
        self.activateWindow()
        self._overlay.close_button.setFocus()
        self.setAcceptDrops(False)

    def close_overlay(self):
        if self._overlay is not None:
            overlay, self._overlay = self._overlay, None
            QApplication.instance().removeEventFilter(overlay)
            overlay.hide()
            overlay.deleteLater()
            self.pages.setEnabled(True)
            if self._allowed():
                (self.map_button if self.pages.currentWidget() is self.drop_page else self.list_button).setFocus()
        self.setAcceptDrops(not self.busy)

    def start_conversion(self):
        self._start_indices(list(range(len(self.entries))))

    def _start_indices(self, indices):
        if not self._allowed() or self.busy or self.probe.busy or not indices:
            return
        self.refresh_environment()
        if self.kind == "hwp" and not self.environment.available:
            return
        self.hide_owned_popups()
        self._run_indices = indices
        for index in indices:
            entry = self.entries[index]
            entry.state, entry.detail, entry.output = "대기", "", ""
            entry.output_bytes, entry.result_preview = 0, ""
        self._run_active = True
        self.pages.setCurrentWidget(self.pick_page)
        self._status("")
        if self.kind == "hwp":
            self._queue = indices.copy()
            self._run_next()
        else:
            for index in indices:
                self.entries[index].state = "변환 중"
            settings = {key: combo.currentData() for key, combo in self.option_combos.items()}
            try:
                self.file_runner.start([self.entries[i].source for i in indices], self.target_id, settings, self.output_directory)
            except FileConversionError as exc:
                for index in indices:
                    self.entries[index].state, self.entries[index].detail = "실패", str(exc)
                self._batch_finished(str(exc))
        self._update_controls()

    def _run_next(self):
        if not self._allowed():
            self.cancel_conversion()
            return
        if not self._queue:
            self._batch_finished("")
            return
        self._current = self._queue.pop(0)
        entry = self.entries[self._current]
        entry.state = "변환 중"
        try:
            self.runner.start(entry.source, self.output_directory or entry.source.parent)
        except ConversionError as exc:
            self._converted(False, "", str(exc))
        self._update_controls()

    def _converted(self, ok, output, message):
        if self._disposed or self._current is None:
            return
        entry = self.entries[self._current]
        entry.state = "완료" if ok else ("취소" if message.startswith("취소됨") else "실패")
        entry.output, entry.detail = output, message
        if output:
            try:
                entry.output_bytes = Path(output).stat().st_size
            except OSError:
                entry.detail = "완료 · 결과 크기를 읽을 수 없어요"
        self._current = None
        if self._queue and self._allowed():
            self._next_timer.start(0)
        else:
            self._batch_finished("")
        self._update_controls()

    def _file_converted(self, index, result):
        if self._disposed:
            return
        indices = self._run_indices if self.target_id == "pdf_bundle" else [self._run_indices[index]]
        for original_index in indices:
            entry = self.entries[original_index]
            entry.state = ("건너뜀" if result.get("skipped") else "완료") if result.get("ok") else ("취소" if result.get("cancelled") else "실패")
            entry.detail = result.get("message", "")
            entry.output = result.get("output", "")
            entry.output_bytes = result.get("bytes", 0)
            entry.output_count = result.get("file_count", 1)
            entry.result_preview = result.get("preview", "")
            entry.metadata["result_size"] = result.get("size", "")
        self._update_controls()

    def _batch_finished(self, message):
        if self._disposed:
            return
        self._run_active = False
        self._queue.clear()
        self._current = None
        self.result_status.setText(message)
        self.result_status.setVisible(bool(message))
        self._render_result()
        self.pages.setCurrentWidget(self.result_page)
        self._update_controls()

    def cancel_conversion(self):
        was_busy = self.busy
        self._next_timer.stop()
        for index in self._queue:
            self.entries[index].state, self.entries[index].detail = "취소", "취소됨"
        self._queue.clear()
        self.runner.cancel()
        self.file_runner.cancel()
        if was_busy and not self.runner.busy and not self.file_runner.busy:
            self._batch_finished("")

    def retry_failed(self, index=None):
        indices = ([index] if index is not None else [i for i, entry in enumerate(self.entries) if entry.state in ("실패", "취소")])
        if self.target_id == "pdf_bundle":
            indices = list(range(len(self.entries)))
        self._start_indices(indices)

    def _render_result(self):
        if not self.entries or not self.target_id:
            return
        clear_layout(self.compare_layout)
        completed = [e for e in self.entries if e.state == "완료"]
        failed = [e for e in self.entries if e.state == "실패"]
        skipped = [e for e in self.entries if e.state == "건너뜀"]
        cancelled = [e for e in self.entries if e.state == "취소"]
        outputs = {entry.output: entry for entry in completed if entry.output}
        count = sum(entry.output_count for entry in outputs.values())
        name = TARGETS[self.target_id].name
        if failed or cancelled:
            title = f"{len(self.entries)}개 중 {len(completed)}개를 만들었어요"
        elif count == 1:
            title = f"{name}를 만들었어요"
        else:
            title = f"{name} {count}개를 만들었어요"
        self.result_title.setText(title)
        self.result_badge.warning = bool(failed or cancelled)
        self.result_badge.update()
        if len(self.entries) == 1 and completed and count == 1:
            entry = completed[0]
            row = QHBoxLayout()
            row.setSpacing(12)
            for output in (False, True):
                if output:
                    row.addWidget(label("→", 26, "#6741D9", True), 0, Qt.AlignCenter)
                column = QVBoxLayout()
                preview = Preview(120, 90)
                preview.set_entry(entry, output, self.target_id)
                column.addWidget(preview, 0, Qt.AlignCenter)
                column.addWidget(label("결과" if output else "원본", 11), 0, Qt.AlignHCenter)
                filename = ElidedLabel(13, True, "#292C33")
                filename.setText(Path(entry.output).name if output else entry.source.name)
                column.addWidget(filename)
                if self.kind == "image":
                    dimensions = entry.metadata.get("result_size", "") if output else f"{entry.metadata.get('width', '')} × {entry.metadata.get('height', '')}"
                    column.addWidget(label(dimensions, 12), 0, Qt.AlignHCenter)
                row.addLayout(column, 1)
            self.compare_layout.addLayout(row)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            body = QWidget()
            rows = QVBoxLayout(body)
            rows.setContentsMargins(0, 0, 0, 0)
            rows.setSpacing(0)
            visible_entries = [entry for entry in self.entries if entry.state != "취소"]
            for entry in visible_entries:
                item = QWidget()
                item.setFixedHeight(32)
                row = QHBoxLayout(item)
                row.setContentsMargins(0, 0, 0, 0)
                filename = ElidedLabel(12, color="#9A3412" if entry.state == "실패" else "#292C33")
                filename.setText((Path(entry.output).name if entry.output else entry.source.name) +
                                 (f" · {entry.detail}" if entry.state != "완료" else ""))
                row.addWidget(filename, 1)
                if entry.state == "실패":
                    index = self.entries.index(entry)
                    retry = self._button("다시 시도", lambda checked=False, i=index: self.retry_failed(i))
                    row.addWidget(retry)
                rows.addWidget(item)
            if not visible_entries:
                rows.addWidget(label("완료된 결과가 없어요"))
            scroll.setWidget(body)
            scroll.setFixedHeight(max(32, min(4, len(visible_entries))*32))
            self.compare_layout.addWidget(scroll)
        self.bars.source_bytes = sum(entry.metadata.get("bytes", 0) for entry in self.entries)
        self.bars.output_bytes = sum(entry.output_bytes for entry in outputs.values())
        self.bars.update()
        self.folder_label.setText("저장 위치  " + (self.output_directory.name if self.output_directory else "원본과 같은 폴더"))
        noun = "사진" if self.kind == "image" else "파일"
        self.again_button.setText(f"같은 {noun}으로 다른 형식도 만들기")
        if skipped or cancelled:
            counts = f"건너뜀 {len(skipped)}개 · 취소 {len(cancelled)}개"
            self.result_status.setText(" · ".join(filter(None, (self.result_status.text(), counts))))
            self.result_status.show()

    def back_to_pick(self):
        if self.busy or not self.entries:
            return
        self.pages.setCurrentWidget(self.pick_page)
        self._render_pick()

    def open_output_folder(self):
        if not self._allowed() or self.busy:
            return
        output = next((entry.output for entry in self.entries if entry.output), None)
        if output:
            path = Path(output)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path if path.is_dir() else path.parent)))

    def dragEnterEvent(self, event):
        if self._allowed() and not self.busy and self._overlay is None and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self._allowed() and not self.busy and self._overlay is None:
            self.add_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
            event.acceptProposedAction()

    def show_near(self, anchor, available):
        if not self._placed:
            self.move(anchor.right()+12, anchor.top())
            self._placed = True
        self.refresh_environment()
        self.fit_to_screen(available)
        self.show()
        self.raise_()
        self.activateWindow()
        (self.add_button if not self.entries else self.start_button).setFocus()
        if self.entries and self.kind != "hwp" and any("format" not in entry.metadata for entry in self.entries):
            self._inspect()

    def fit_to_screen(self, available=None):
        if available is None:
            screen = QApplication.screenAt(self.frameGeometry().center()) or self.screen() or QApplication.primaryScreen()
            if screen is None:
                return
            available = screen.availableGeometry()
        margin = min(SHADOW_MARGIN, max(0, (available.width()-420)//2), max(0, (available.height()-480)//2))
        compact = available.height() < 560
        self.layout().setContentsMargins(margin, margin, margin, margin)
        self.title_bar.set_compact(compact)
        for page in (self.pick_page, self.result_page):
            page.layout().setContentsMargins(18, 6 if compact else 14, 18, 10 if compact else 16)
            page.layout().setSpacing(6 if compact else 14)
        shadow = self.surface.graphicsEffect()
        shadow.setEnabled(margin > 0)
        shadow.setBlurRadius(max(0, margin-4))
        self.resize(min(WINDOW_WIDTH+margin*2, available.width()), min(WINDOW_HEIGHT+margin*2, available.height()))
        self.move(max(available.left(), min(self.x(), available.right()+1-self.width())),
                  max(available.top(), min(self.y(), available.bottom()+1-self.height())))
        if self._overlay is not None:
            self._overlay.resize_to_body()

    def hide_owned_popups(self):
        self.close_overlay()
        for combo in self.findChildren(ConverterCombo):
            combo.hidePopup()
        if self._dialog is not None:
            dialog, self._dialog = self._dialog, None
            dialog.reject()

    def shutdown(self):
        self._disposed = True
        self._next_timer.stop()
        self._queue.clear()
        self._generation += 1
        self._inspect_restart = False
        self.hide_owned_popups()
        self.probe.shutdown()
        self.file_runner.shutdown()
        self.runner.shutdown()

    def hideEvent(self, event):
        self._drag_origin = None
        self._generation += 1
        self._inspect_restart = False
        self.probe.cancel()
        self.hide_owned_popups()
        self.cancel_conversion()
        super().hideEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.EnabledChange and not self.isEnabled():
            self.hide_owned_popups()
            self._generation += 1
            self._inspect_restart = False
            self.probe.cancel()
            self.cancel_conversion()
        super().changeEvent(event)

    def event(self, event):
        if event.type() == QEvent.DeferredDelete:
            self.shutdown()
        return super().event(event)

    def eventFilter(self, watched, event):
        if watched is getattr(self, "content", None) and event.type() == QEvent.Resize and self._overlay is not None:
            self._overlay.resize_to_body()
        if isinstance(watched, QPushButton) and event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if not event.isAutoRepeat():
                watched.click()
            return True
        if watched in (getattr(self, "header", None), getattr(self, "title_label", None)):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_origin = (event.globalPosition().toPoint(), self.pos())
                return True
            if event.type() == QEvent.MouseMove and self._drag_origin and event.buttons() & Qt.LeftButton:
                origin, position = self._drag_origin
                self.move(position+event.globalPosition().toPoint()-origin)
                return True
            if event.type() == QEvent.MouseButtonRelease and self._drag_origin:
                self._drag_origin = None
                self.fit_to_screen()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self._overlay is not None:
                self.close_overlay()
            elif QApplication.activePopupWidget() is not None:
                QApplication.activePopupWidget().hide()
            else:
                self.close()
        else:
            super().keyPressEvent(event)
