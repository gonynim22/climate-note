# main.py - 진입점, 앱 초기화, Boss Key 등록
import sys
import os
import atexit
import sqlite3
import traceback
import logging
from logging.handlers import RotatingFileHandler

from PySide6.QtWidgets import (
    QApplication, QMessageBox, QSystemTrayIcon, QMenu,
)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import (
    QDesktopServices, QIcon, QPixmap, QColor, QKeySequence, QShortcut,
)

from qfluentwidgets import setTheme, setThemeColor, Theme, isDarkTheme, InfoBar, InfoBarPosition

from app_fonts import apply_app_font, load_app_fonts, load_icon_fonts, load_ui_fonts
import database as db
from security import audit, APP_DIR


# ─── 전역 에러 로그 설정 ──────────────────────────────────────
def _setup_error_log() -> logging.Logger:
    handler = RotatingFileHandler(
        APP_DIR / "error.log",
        maxBytes=1_000_000,   # 1MB
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s\n%(message)s\n",
                          datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger = logging.getLogger("app_error")
    logger.setLevel(logging.ERROR)
    logger.addHandler(handler)
    return logger


_error_logger = _setup_error_log()


def _global_exception_handler(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    _error_logger.error(
        "Unhandled exception:\n%s",
        "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    )


sys.excepthook = _global_exception_handler


# ─── 자동실행 레지스트리 경로 갱신 ──────────────────────────────
def _refresh_startup_path():
    """자동실행이 켜져 있으면 현재 exe 경로로 레지스트리 갱신"""
    if os.environ.get("CLIMATENOTE_SKIP_STARTUP_REFRESH") == "1":
        return
    try:
        import winreg
        reg_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "기후노트"
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, reg_key, 0,
            winreg.KEY_READ | winreg.KEY_SET_VALUE,
        ) as key:
            try:
                old_cmd, _ = winreg.QueryValueEx(key, app_name)
                if getattr(sys, "frozen", False):
                    new_cmd = f'"{sys.executable}"'
                else:
                    new_cmd = f'"{sys.executable}" "{os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")}"'
                if old_cmd != new_cmd:
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, new_cmd)
            except FileNotFoundError:
                pass  # 자동실행 미등록 상태
    except (OSError, FileNotFoundError, PermissionError):
        pass  # 레지스트리 접근 실패 시 무시 (비치명적)


# ─── Windows 다크/라이트 모드 감지 ────────────────────────────
def _detect_system_theme() -> Theme:
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return Theme.LIGHT if value == 1 else Theme.DARK
    except (OSError, FileNotFoundError):
        return Theme.LIGHT


# ─── 트레이 아이콘 생성 ────────────────────────────────────────
def _make_tray_icon(app: QApplication) -> QSystemTrayIcon:
    """시스템 트레이 아이콘 생성 (icon 파일 사용)"""
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon", "icon_fixed_32.ico")
    if os.path.exists(icon_path):
        icon = QIcon(icon_path)
    else:
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("#0078D4"))
        icon = QIcon(pixmap)

    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("기후노트")
    return tray


def _initialize_database() -> None:
    """마이그레이션 전 스냅샷 실패 시 스키마 변경을 시작하지 않는다."""
    health = db.inspect_startup_data_health()
    if not health.ok:
        raise db.DataHealthError(health)
    db.backup_before_v35()
    db.backup_before_migration()
    db.migrate()
    db.backup_database()


def _data_health_error_message(code: str) -> tuple[str, str]:
    title = "데이터 보호를 위해 실행을 중단했습니다"
    if code in {"salt_missing", "salt_invalid"}:
        detail = (
            "기존 데이터에 필요한 salt 파일을 확인하지 못했습니다. "
            "새 salt를 만들지 않았습니다."
        )
    elif code == "decrypt_failed":
        detail = (
            "기존 암호화 데이터를 안전하게 읽지 못했습니다. "
            "원래 PC·Windows 사용자 환경과 salt를 확인해 주세요."
        )
    else:
        detail = "기존 데이터베이스의 구조 또는 무결성을 확인하지 못했습니다."
    return title, (
        f"{detail}\n\n데이터와 기존 백업은 변경하지 않았습니다. "
        "데이터 폴더를 보존한 뒤 확인해 주세요."
    )


def _show_data_health_error(report: db.DataHealthReport) -> None:
    title, content = _data_health_error_message(report.code)
    dialog = QMessageBox()
    dialog.setIcon(QMessageBox.Critical)
    dialog.setWindowTitle(title)
    dialog.setText(content)
    open_folder = dialog.addButton(
        "데이터 폴더 열기", QMessageBox.ActionRole
    )
    dialog.addButton("종료", QMessageBox.RejectRole)
    dialog.exec()
    if dialog.clickedButton() is open_folder:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(APP_DIR)))


def main():
    # ── 단일 인스턴스 잠금 (DB 동시 접근 방지) ──
    import msvcrt
    from security import APP_DIR as _app_dir
    lock_path = _app_dir / ".lock"
    try:
        lock_file = open(lock_path, "w")
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        atexit.register(lock_file.close)
    except (OSError, IOError):
        # 이미 다른 인스턴스가 실행 중
        _temp_app = QApplication(sys.argv)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(None, "기후노트", "이미 실행 중입니다.\n시스템 트레이를 확인해 주세요.")
        sys.exit(0)

    # ── High DPI 지원
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("기후노트")
    app.setQuitOnLastWindowClosed(False)  # 트레이 상주
    # ── 앱 글꼴 · Font Awesome 아이콘 · UI 강조(Pretendard) 폰트 로드
    load_app_fonts(_error_logger)
    load_icon_fonts(_error_logger)
    load_ui_fonts(_error_logger)
    apply_app_font(db.DEFAULT_APP_FONT, app)

    # ── 테마 설정 (시스템 연동)
    theme = _detect_system_theme()
    setTheme(theme)
    # ── 단일 블루 액센트(#2563EB): 토글/슬라이더/포인트색을 앱 전역 통일
    setThemeColor(QColor("#2563EB"))

    # ── Win11 DWM 창 테두리가 팝업 메뉴 주위에 넓은 박스로 보이는 문제 우회
    from popup_border_fix import install_popup_border_fix
    _popup_border_filter = install_popup_border_fix(app)  # noqa: F841 (참조 유지)

    # ── DB 초기화 및 백업
    try:
        _initialize_database()
        apply_app_font(db.get_setting(db.SETTING_APP_FONT, db.DEFAULT_APP_FONT), app)
    except db.DataHealthError as e:
        _error_logger.error("데이터 건강 검사 실패: %s", e.report.code)
        _show_data_health_error(e.report)
        sys.exit(1)
    except (sqlite3.Error, OSError, ValueError) as e:
        _error_logger.error("DB 초기화 실패: %s", e)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "초기화 오류", "데이터베이스 초기화에 실패했습니다.")
        sys.exit(1)

    # ── 자동실행 경로 갱신 (업데이트 후 exe 경로 변경 대응)
    _refresh_startup_path()

    # ── 메인 창 생성
    from ui_main import MainCalendarWindow
    main_window = MainCalendarWindow()
    main_window.show()

    # ── 감사 로그: 앱 실행
    audit("앱 실행", "성공")

    # ── 공휴일 데이터 만료 알림 (마지막 연도 12월부터 표시)
    from datetime import date as _date
    from holidays import holiday_last_year
    _last_year = holiday_last_year()
    _today = _date.today()
    if _today.year == _last_year and _today.month == 12 or _today.year > _last_year:
        QTimer.singleShot(2000, lambda: InfoBar.warning(
            title="공휴일 안내",
            content=f"공휴일은 {_last_year}년 데이터까지 제공됩니다.\n이후 데이터는 패치를 통해 업데이트해 주세요.",
            parent=main_window,
            position=InfoBarPosition.TOP,
            duration=10000,
        ))

    # ── 시스템 트레이
    tray = _make_tray_icon(app)
    tray_menu = QMenu()

    show_action = tray_menu.addAction("보이기/숨기기")
    show_action.triggered.connect(main_window.toggle_visibility)

    quit_action = tray_menu.addAction("종료")
    quit_action.triggered.connect(lambda: _quit(app, main_window))

    tray.setContextMenu(tray_menu)
    tray.activated.connect(
        lambda reason: main_window.toggle_visibility()
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )
    tray.show()

    # ── 보스 키: Ctrl+Shift+H (전역 단축키)
    # PySide6 네이티브 전역 단축키는 플랫폼 제한이 있으므로
    # 앱 레벨 단축키로 등록 (창이 포커스 없을 때는 트레이로 접근)
    boss_key = QShortcut(QKeySequence("Ctrl+Shift+H"), main_window)
    boss_key.setContext(Qt.ApplicationShortcut)
    boss_key.activated.connect(main_window.toggle_visibility)

    # ── 시스템 테마 변경 감지 (1분 주기)
    theme_timer = QTimer()
    theme_timer.setInterval(60_000)
    def _check_theme():
        new_theme = _detect_system_theme()
        if (new_theme == Theme.DARK) != isDarkTheme():
            setTheme(new_theme)
            setThemeColor(QColor("#2563EB"))  # 테마 전환 후에도 블루 액센트 유지
    theme_timer.timeout.connect(_check_theme)
    theme_timer.start()

    def _on_quit():
        audit("앱 종료", "성공")
    app.aboutToQuit.connect(_on_quit)
    sys.exit(app.exec())


def _quit(app: QApplication, main_window) -> bool:
    if not main_window.prepare_for_quit():
        return False
    app.quit()
    return True


if __name__ == "__main__":
    main()
