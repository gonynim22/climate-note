"""번들 라이선스의 읽기 전용 열람. DB·설정·네트워크에 접근하지 않는다."""
import json
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QSizePolicy, QVBoxLayout,
)

from app_info import APP_DISPLAY_NAME, APP_VERSION
from app_paths import resource_root


def license_entries(root: Path) -> list[dict]:
    """빌드와 같은 폴더 기준으로 선택형 앱의 고지도 함께 걷어낸다."""
    catalogs = [root / "licenses/components.json"]
    if (root / "screen_text").is_dir():
        catalogs.append(root / "screen_text/licenses/components.json")
    entries = []
    for catalog in catalogs:
        with open(catalog, encoding="utf-8") as stream:
            entries.extend(json.load(stream))
    return entries


def license_document(root: Path, entry: dict) -> str:
    version = APP_VERSION if entry["id"] == "app" else entry["version"]
    sections = [
        f'{entry["name"]} {version}'.strip(),
        f'라이선스: {entry["license"]}',
        entry["description"],
        "출처: " + "\n".join(entry["sources"]),
    ]
    for filename in entry["files"]:
        try:
            with open(root / filename, encoding="utf-8-sig") as stream:
                content = stream.read()
        except (OSError, UnicodeError):
            content = "고지 파일을 읽을 수 없습니다. 배포본의 고지 파일을 확인해 주세요."
        sections.append(f"──── {filename} ────\n\n{content}")
    return "\n\n".join(sections)


class LicenseDialog(QDialog):
    """설정이 소유하는 모달. 부모 숨김·비활성·닫기 때 함께 종료한다."""

    def __init__(self, parent=None, *, root=None):
        super().__init__(parent)
        self._root = Path(root) if root is not None else resource_root()
        self.setObjectName("licenseDialog")
        self.setWindowTitle(f"{APP_DISPLAY_NAME} · 라이선스 및 출처")
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setSizeGripEnabled(True)
        self.setStyleSheet(
            "QDialog#licenseDialog{background:#F7F8FA;}"
            "QLabel{color:#263247;font-family:'Malgun Gothic';font-size:13px;}"
            "QComboBox,QPlainTextEdit{background:white;color:#263247;"
            "border:1px solid #D7DAE2;border-radius:5px;"
            "font-family:'Malgun Gothic';font-size:13px;}"
            "QComboBox{min-height:30px;padding:0 8px;}"
            "QPlainTextEdit{padding:10px;selection-background-color:#2563EB;"
            "selection-color:white;}"
            "QPushButton{background:white;color:#263247;border:1px solid #D7DAE2;"
            "border-radius:5px;padding:7px 14px;font-size:13px;}"
            "QPushButton:hover{background:#EFF4FF;border-color:#2563EB;}"
            "QPushButton:focus{border:2px solid #2563EB;}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        guide = QLabel("구성요소를 선택해 라이선스 원문과 출처를 확인하세요.", self)
        guide.setWordWrap(True)
        layout.addWidget(guide)
        self.component_combo = QComboBox(self)
        self.component_combo.setAccessibleName("라이선스 구성요소")
        self.component_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.component_combo.setMinimumContentsLength(12)
        self.component_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        layout.addWidget(self.component_combo)
        self.document = QPlainTextEdit(self)
        self.document.setAccessibleName("라이선스 원문 및 출처")
        self.document.setReadOnly(True)
        self.document.setMinimumSize(0, 0)
        self.document.setTabChangesFocus(True)
        layout.addWidget(self.document, 1)
        footer = QHBoxLayout()
        self.copy_button = QPushButton("전체 복사", self)
        self.copy_button.setAutoDefault(False)
        self.copy_button.clicked.connect(self._copy)
        footer.addWidget(self.copy_button)
        footer.addStretch()
        self.close_button = QPushButton("닫기", self)
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)
        try:
            self._entries = license_entries(self._root)
        except (OSError, UnicodeError, ValueError):
            self._entries = []
            self.document.setPlainText("라이선스 목록을 읽을 수 없습니다. 배포본의 고지 파일을 확인해 주세요.")
        for entry in self._entries:
            version = APP_VERSION if entry["id"] == "app" else entry["version"]
            self.component_combo.addItem(f'{entry["name"]} {version}'.strip(), entry["id"])
        self.component_combo.currentIndexChanged.connect(self._select)
        if self._entries:
            self._select(0)
        self.component_combo.setEnabled(bool(self._entries))
        if parent is not None:
            parent.installEventFilter(self)
        screen = parent.screen() if parent is not None else QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.fit_to_area(area)

    def fit_to_area(self, area):
        """작은 작업 영역에서도 본문만 스크롤하고 조작 버튼을 남긴다."""
        self.resize(min(780, max(1, area.width() - 32)),
                    min(560, max(1, area.height() - 48)))
        self.move(area.center() - self.rect().center())

    def _select(self, index):
        if 0 <= index < len(self._entries):
            self.document.setPlainText(license_document(self._root, self._entries[index]))
            self.document.verticalScrollBar().setValue(0)

    def _copy(self):
        QApplication.clipboard().setText(self.document.toPlainText())

    def eventFilter(self, watched, event):
        if watched is self.parent() and (
            event.type() in (QEvent.Hide, QEvent.Close)
            or (event.type() == QEvent.EnabledChange and not watched.isEnabled())
        ):
            self.reject()
        return super().eventFilter(watched, event)
