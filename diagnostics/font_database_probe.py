"""Standalone probes for machine-specific ClimateNote Settings hangs."""
from __future__ import annotations

import hashlib
import os
import platform
import sqlite3
import sys
import threading
import time
import traceback
import winreg
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import QTimer, Qt, QUrl, qVersion
from PySide6.QtGui import QDesktopServices, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


PROBE_NAME = "기후노트 설정 멈춤 진단"
WATCHDOG_FIRST_SECONDS = 10
WATCHDOG_SECOND_SECONDS = 30
_FONT_REGISTRY_PATH = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"


def _log_dir() -> Path:
    override = (
        os.environ.get("CLIMATENOTE_DIAGNOSTIC_LOG_DIR")
        or os.environ.get("CLIMATENOTE_FONT_PROBE_LOG_DIR")
    )
    if override:
        return Path(override)
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home()
    return base / "ClimateNoteSettingsProbe"


def log_path() -> Path:
    return _log_dir() / "settings_probe.log"


def _append_log(message: str) -> None:
    """Durably append one diagnostic line before a potentially hanging call."""
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")
        f.flush()
        os.fsync(f.fileno())


def _session_details(mode: str) -> str:
    python_version = platform.python_version()
    frozen = bool(getattr(sys, "frozen", False))
    return (
        f"SESSION_START mode={mode} pid={os.getpid()} frozen={frozen} "
        f"windows={platform.platform()} python={python_version} "
        f"pyside={PYSIDE_VERSION} qt={qVersion()}"
    )


def _watch_for_hang(test_id: str, finished: threading.Event) -> None:
    if finished.wait(WATCHDOG_FIRST_SECONDS):
        return
    _append_log(
        f"WATCHDOG_10S test={test_id} 시작 이후 10초 동안 반환되지 않음"
    )
    remaining = WATCHDOG_SECOND_SECONDS - WATCHDOG_FIRST_SECONDS
    if finished.wait(remaining):
        return
    _append_log(
        f"WATCHDOG_30S test={test_id} 시작 이후 30초 동안 반환되지 않음; "
        "해당 단계 정지 가능성 높음"
    )


def probe_screen_info() -> str:
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication이 없습니다.")
    details = []
    summary = []
    for index, screen in enumerate(app.screens()):
        geometry = screen.geometry()
        available = screen.availableGeometry()
        details.append(
            f"[{index}] {screen.name()} "
            f"geometry=({geometry.x()},{geometry.y()},"
            f"{geometry.width()},{geometry.height()}) "
            f"available=({available.x()},{available.y()},"
            f"{available.width()},{available.height()}) "
            f"logicalDpi={screen.logicalDotsPerInch():.2f} "
            f"physicalDpi={screen.physicalDotsPerInch():.2f} "
            f"dpr={screen.devicePixelRatio():.2f}"
        )
        summary.append(
            f"{screen.name()} · DPI {screen.logicalDotsPerInch():.0f}"
        )
    _append_log(f"SCREEN_COMPLETE count={len(details)}\n" + "\n".join(details))
    return f"정상 · 화면 {len(details)}개\n" + "\n".join(summary)


def _registry_font_values(root, root_name: str) -> list[str]:
    try:
        with winreg.OpenKey(root, _FONT_REGISTRY_PATH) as key:
            value_count = winreg.QueryInfoKey(key)[1]
            return [
                f"{root_name}: {winreg.EnumValue(key, index)[0]}"
                for index in range(value_count)
            ]
    except FileNotFoundError:
        return []


def probe_font_registry() -> str:
    _append_log("FONT_REGISTRY_START Windows 글꼴 레지스트리 조회 직전")
    values = _registry_font_values(winreg.HKEY_LOCAL_MACHINE, "HKLM")
    values.extend(_registry_font_values(winreg.HKEY_CURRENT_USER, "HKCU"))
    digest = hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()
    _append_log(
        f"FONT_REGISTRY_COMPLETE count={len(values)} sha256={digest}"
    )
    return f"정상 · Windows 글꼴 {len(values)}개"


def probe_font_families() -> str:
    """Run the exact Qt call used while ClimateNote Settings is constructed."""
    _append_log("FONT_ENUM_START QFontDatabase.families() 호출 직전")
    started = time.perf_counter()
    families = list(QFontDatabase.families())
    elapsed = time.perf_counter() - started
    digest = hashlib.sha256("\n".join(families).encode("utf-8")).hexdigest()
    _append_log(
        f"FONT_ENUM_COMPLETE elapsed={elapsed:.3f}s count={len(families)} "
        f"sha256={digest}"
    )
    return (
        f"정상 · Qt 글꼴 {len(families)}개\n"
        f"소요 {elapsed:.3f}초"
    )


def probe_sqlite_wal() -> str:
    """Exercise WAL on a disposable probe DB, never the ClimateNote DB."""
    probe_dir = _log_dir() / "sqlite_probe"
    probe_dir.mkdir(parents=True, exist_ok=True)
    db_path = probe_dir / f"probe_{os.getpid()}_{time.time_ns()}.db"
    started = time.perf_counter()
    _append_log(f"SQLITE_START isolated_db={db_path}")
    try:
        with closing(sqlite3.connect(str(db_path), timeout=5)) as conn:
            journal_mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            conn.execute("CREATE TABLE probe (id INTEGER PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO probe(value) VALUES (?)", ("ok",))
            conn.commit()
        # SettingsWindow가 여러 get_setting()을 순차 호출하는 경로처럼 새 연결과
        # WAL 확인을 반복한다. 실제 ClimateNote DB에는 접근하지 않는다.
        roundtrips = 12
        for _index in range(roundtrips):
            with closing(sqlite3.connect(str(db_path), timeout=5)) as conn:
                journal_mode = conn.execute(
                    "PRAGMA journal_mode=WAL"
                ).fetchone()[0]
                value = conn.execute(
                    "SELECT value FROM probe WHERE id=1"
                ).fetchone()[0]
        with closing(sqlite3.connect(str(db_path), timeout=5)) as conn:
            quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
        elapsed = time.perf_counter() - started
        _append_log(
            f"SQLITE_COMPLETE elapsed={elapsed:.3f}s "
            f"journal_mode={journal_mode} quick_check={quick_check} value={value}"
        )
        return (
            f"정상 · SQLite WAL {roundtrips}회\n"
            f"소요 {elapsed:.3f}초 · 검사 {quick_check}"
        )
    finally:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(db_path) + suffix)
            try:
                candidate.unlink(missing_ok=True)
            except OSError as exc:
                _append_log(f"SQLITE_TEMP_CLEANUP_ERROR path={candidate} error={exc}")


class AuxiliaryTestWindow(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Window | Qt.WindowCloseButtonHint)
        self.setWindowTitle("기후노트 보조 창 진단")
        self.resize(420, 210)
        layout = QVBoxLayout(self)
        message = QLabel(
            "이 창이 앞에 보이고 버튼이 눌리면 정상입니다.",
            self,
        )
        message.setAlignment(Qt.AlignCenter)
        message.setWordWrap(True)
        layout.addWidget(message, 1)
        close_button = QPushButton("정상 · 닫기", self)
        close_button.setObjectName("testButton")
        close_button.setMinimumHeight(52)
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)


class SettingsProbeWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._probe_running = False
        self._test_buttons: list[QPushButton] = []
        self._aux_window: AuxiliaryTestWindow | None = None
        self.setWindowTitle(PROBE_NAME)
        self.setMinimumSize(680, 680)
        self.resize(720, 680)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        self.setStyleSheet(
            "QPushButton#testButton, QPushButton#primaryTestButton {"
            "  min-height: 54px; padding: 0 18px; text-align: left;"
            "  font-size: 15px; font-weight: 600;"
            "  color: #1F2937; background: #F7FAFF;"
            "  border: 1px solid #C8D3E2; border-radius: 10px;"
            "}"
            "QPushButton#testButton:hover {"
            "  background: #EAF2FF; border-color: #7AA7E8;"
            "}"
            "QPushButton#primaryTestButton {"
            "  color: white; background: #2563EB; border-color: #2563EB;"
            "}"
            "QPushButton#primaryTestButton:hover { background: #1D4ED8; }"
            "QPushButton#testButton:disabled, QPushButton#primaryTestButton:disabled {"
            "  color: #8A93A3; background: #EDF0F5; border-color: #D8DDE6;"
            "}"
            "QLabel#solutionBox {"
            "  color: #374151; background: #F3F6FA;"
            "  border: 1px solid #D7DEE8; border-radius: 9px; padding: 10px 12px;"
            "}"
        )

        title = QLabel(PROBE_NAME, self)
        title_font = title.font()
        title_font.setPixelSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        description = QLabel(
            "1번부터 순서대로 누르세요.\n"
            "멈추면 30초 뒤 종료하고, 다시 열어 다음 번호를 검사하세요.",
            self,
        )
        description.setWordWrap(True)
        description.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(description)

        tests = QGridLayout()
        tests.setHorizontalSpacing(10)
        tests.setVerticalSpacing(10)
        self._add_test_button(
            tests, 0, 0, "① 화면 · DPI", "screen", probe_screen_info
        )
        self._add_test_button(
            tests, 0, 1, "② Windows 글꼴",
            "font_registry", probe_font_registry,
        )
        self._add_test_button(
            tests, 1, 0, "③ Qt 글꼴 전체 조회",
            "qt_font_database", probe_font_families, primary=True,
        )
        self._add_test_button(
            tests, 1, 1, "④ SQLite 저장소",
            "sqlite_wal", probe_sqlite_wal,
        )
        aux_button = QPushButton("⑤ 새 창 표시", self)
        aux_button.setObjectName("testButton")
        aux_button.setMinimumHeight(54)
        aux_button.clicked.connect(self._open_auxiliary_window)
        tests.addWidget(aux_button, 2, 0, 1, 2)
        self._test_buttons.append(aux_button)
        layout.addLayout(tests)

        self.status_label = QLabel("검사 대기 중", self)
        status_font = self.status_label.font()
        status_font.setBold(True)
        self.status_label.setFont(status_font)
        layout.addWidget(self.status_label)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.result_view = QPlainTextEdit(self)
        self.result_view.setReadOnly(True)
        self.result_view.setFixedHeight(76)
        self.result_view.setPlainText("검사 결과가 여기에 표시됩니다.")
        layout.addWidget(self.result_view)

        solution = QLabel(
            "멈춘 번호별 조치\n"
            "① 모니터 재연결 · 그래픽 드라이버 점검\n"
            "② Windows 글꼴 등록 상태와 최근 설치 글꼴 점검\n"
            "③ 상세 해결 (②는 정상이고 ③만 멈출 때)\n"
            "  1. 설정 > 개인 설정 > 글꼴에서 최근 설치한 글꼴 제거\n"
            "  2. 제어판 > 모양 및 개인 설정 > 글꼴 > 글꼴 설정에서 기본값 복원\n"
            "  3. PC 재부팅 후 ③ 재검사\n"
            "  4. 계속 멈추면 전산 담당자에게 Windows Font Cache 초기화 요청\n"
            "④ 기후노트 완전 종료 · 중복 실행/보안 프로그램 잠금 점검\n"
            "⑤ 바탕화면 고정 OFF 상태로 재검사",
            self,
        )
        solution.setObjectName("solutionBox")
        solution.setWordWrap(True)
        layout.addWidget(solution)

        footer = QHBoxLayout()
        log_button = QPushButton("로그 열기", self)
        log_button.setMinimumHeight(36)
        log_button.clicked.connect(self._open_log_folder)
        footer.addWidget(log_button)
        footer.addStretch(1)
        layout.addLayout(footer)

    def _add_test_button(
        self,
        layout: QGridLayout,
        row: int,
        column: int,
        text: str,
        test_id: str,
        probe: Callable[[], str],
        primary: bool = False,
    ) -> None:
        button = QPushButton(text, self)
        button.setObjectName("primaryTestButton" if primary else "testButton")
        button.setMinimumHeight(54)
        button.clicked.connect(
            lambda _checked=False, tid=test_id, label=text, fn=probe:
            self._start_probe(tid, label, fn)
        )
        layout.addWidget(button, row, column)
        self._test_buttons.append(button)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for button in self._test_buttons:
            button.setEnabled(enabled)

    def _start_probe(
        self,
        test_id: str,
        label: str,
        probe: Callable[[], str],
    ) -> None:
        if self._probe_running:
            return
        self._probe_running = True
        self._set_buttons_enabled(False)
        self.progress.show()
        self.status_label.setText(f"{label} 시작…")
        self.result_view.setPlainText(
            f"{label} 검사 중…\n30초 넘으면 종료하세요."
        )
        _append_log(_session_details("gui"))
        _append_log(f"TEST_START id={test_id} label={label}")
        QTimer.singleShot(
            100,
            lambda: self._run_probe(test_id, label, probe),
        )

    def _run_probe(
        self,
        test_id: str,
        label: str,
        probe: Callable[[], str],
    ) -> None:
        finished = threading.Event()
        watchdog = threading.Thread(
            target=_watch_for_hang,
            args=(test_id, finished),
            name=f"probe-watchdog-{test_id}",
            daemon=True,
        )
        watchdog.start()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        started = time.perf_counter()
        try:
            result = probe()
            elapsed = time.perf_counter() - started
            _append_log(f"TEST_COMPLETE id={test_id} elapsed={elapsed:.3f}s")
            self.status_label.setText(f"{label} 정상 완료")
            self.result_view.setPlainText(result)
        except Exception:
            details = traceback.format_exc()
            _append_log(f"TEST_ERROR id={test_id}\n{details}")
            self.status_label.setText(f"{label} 오류")
            self.result_view.setPlainText(details)
        finally:
            finished.set()
            QApplication.restoreOverrideCursor()
            self.progress.hide()
            self._set_buttons_enabled(True)
            self._probe_running = False

    def _open_auxiliary_window(self) -> None:
        _append_log(_session_details("gui"))
        _append_log("TEST_START id=aux_window label=부모 없는 보조 창")
        if self._aux_window is None:
            self._aux_window = AuxiliaryTestWindow()
        self._aux_window.show()
        self._aux_window.setWindowState(
            (self._aux_window.windowState() & ~Qt.WindowMinimized)
            | Qt.WindowActive
        )
        self._aux_window.raise_()
        self._aux_window.activateWindow()
        QTimer.singleShot(300, self._record_auxiliary_window_state)

    def _record_auxiliary_window_state(self) -> None:
        if self._aux_window is None:
            return
        geometry = self._aux_window.frameGeometry()
        state = (
            f"visible={self._aux_window.isVisible()} "
            f"active={self._aux_window.isActiveWindow()} "
            f"geometry=({geometry.x()},{geometry.y()},"
            f"{geometry.width()},{geometry.height()})"
        )
        _append_log(f"TEST_COMPLETE id=aux_window {state}")
        self.status_label.setText("보조 창 표시 상태를 직접 확인하세요")
        self.result_view.setPlainText(
            f"새 창 상태: {state}\n"
            "앞에 보이고 버튼이 눌리면 정상입니다."
        )

    def _open_log_folder(self) -> None:
        folder = _log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def _run_probe_once(test_id: str, probe: Callable[[], str]) -> int:
    _append_log(_session_details("probe-once"))
    _append_log(f"TEST_START id={test_id}")
    started = time.perf_counter()
    try:
        probe()
    except Exception:
        _append_log(f"TEST_ERROR id={test_id}\n{traceback.format_exc()}")
        return 1
    elapsed = time.perf_counter() - started
    _append_log(f"TEST_COMPLETE id={test_id} elapsed={elapsed:.3f}s")
    return 0


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(PROBE_NAME)

    if "--probe-once" in sys.argv:
        return _run_probe_once("qt_font_database", probe_font_families)
    if "--probe-all" in sys.argv:
        probes = (
            ("screen", probe_screen_info),
            ("font_registry", probe_font_registry),
            ("sqlite_wal", probe_sqlite_wal),
            ("qt_font_database", probe_font_families),
        )
        for test_id, probe in probes:
            result = _run_probe_once(test_id, probe)
            if result:
                return result
        return 0

    window = SettingsProbeWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
