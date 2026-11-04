"""새 버전 확인 예약: 설정 '인터넷 접속'을 켠 PC만 작업 스레드 하나로 확인하고 결과를 화면에 넘긴다.

- 창이 뜬 뒤 60초에 한 번, 그 뒤 24시간마다, 스위치를 켠 직후에는 5초 뒤 한 번 확인한다.
- 실패는 화면에 보이지 않는다. 1시간 뒤 한 번 더 보고, 그래도 실패하면 24시간 뒤 다시 본다.
- 요청 직전에도 키를 다시 읽는다. 저장하는 것은 없고 알게 된 버전은 메모리 전용이다.
- 요청마다 결과 큐를 새로 만든다. 끄기·초기화·종료 때 큐를 버리면 늦게 도착한 결과는 아무도 읽지 않는다.
"""

import logging
from queue import Empty, Queue
import sqlite3
from threading import Thread

from PySide6.QtCore import QObject, QTimer, Signal

from app_info import APP_VERSION
import database as db
import update_check
from update_check import CheckResult

_logger = logging.getLogger("app_error")

FIRST_CHECK_DELAY_MS = 60_000
AFTER_SWITCH_DELAY_MS = 5_000
RETRY_DELAY_MS = 3_600_000
CHECK_INTERVAL_MS = 86_400_000
POLL_INTERVAL_MS = 200


def _run_check(results: Queue) -> None:
    """작업 스레드 본체. 위젯을 잡지 않는다. check_latest는 부를 때 찾는다(개발 미리보기가 바꿔 끼운다)."""
    results.put(update_check.check_latest())


class UpdateCheckController(QObject):
    latestChanged = Signal(object)  # 새 버전 태그. 없어지면 None

    def __init__(self, parent=None, current_version: str = APP_VERSION):
        super().__init__(parent)
        self._current = current_version
        self._latest = None
        self._active = False  # 예약이 도는 중
        self._retried = False  # 직전 실패의 재시도를 이미 잡았다
        self._worker = None
        self._results = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._begin_check)
        self._poll = QTimer(self)
        self._poll.setInterval(POLL_INTERVAL_MS)
        self._poll.timeout.connect(self._poll_result)

    @property
    def latest(self) -> str | None:
        return self._latest

    def start(self) -> None:
        """창이 뜬 뒤 한 번 부른다."""
        if self._enabled():
            self._active = True
            self._timer.start(FIRST_CHECK_DELAY_MS)

    def apply_setting(self) -> None:
        """스위치 변경·가져오기·초기화 뒤에 부른다. 이미 돌고 있으면 예약을 건드리지 않는다."""
        if not self._enabled():
            self.stop()
            self._active = False
            self._retried = False
            self._set_latest(None)
        elif not self._active:
            self._active = True
            self._timer.start(AFTER_SWITCH_DELAY_MS)

    def stop(self) -> None:
        """예약과 진행 중 요청의 결과를 버린다. 표시는 건드리지 않는다."""
        self._timer.stop()
        self._poll.stop()
        self._results = None

    def _enabled(self) -> bool:
        try:
            return db.get_setting(db.SETTING_INTERNET_ACCESS, "0") == "1"
        except sqlite3.Error as e:  # 읽지 못하면 요청하지 않는다
            _logger.error("인터넷 접속 설정을 읽지 못했습니다: %s", type(e).__name__)
            return False

    def _begin_check(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            self._timer.start(AFTER_SWITCH_DELAY_MS)  # 스레드는 하나만. 앞선 요청이 끝난 뒤 다시 본다
            return
        if not self._enabled():
            self.apply_setting()
            return
        self._results = Queue(maxsize=1)
        self._worker = Thread(target=_run_check, args=(self._results,), daemon=True)
        self._worker.start()
        self._poll.start()

    def _poll_result(self) -> None:
        # 넣고 끝나는 사이를 놓치지 않게 살아 있는지를 먼저 본다.
        alive = self._worker.is_alive()
        try:
            result = self._results.get_nowait()
        except Empty:
            if alive:
                return
            result = CheckResult(failure="worker")
        self._poll.stop()
        self._results = None
        self._on_result(result)

    def _on_result(self, result: CheckResult) -> None:
        if result.failure is not None:
            _logger.error("새 버전 확인 실패: %s", result.failure)
            self._timer.start(CHECK_INTERVAL_MS if self._retried else RETRY_DELAY_MS)
            self._retried = not self._retried
            return
        self._retried = False
        self._timer.start(CHECK_INTERVAL_MS)
        if result.latest_tag is not None:
            self._set_latest(result.latest_tag if update_check.is_newer(result.latest_tag, self._current) else None)

    def _set_latest(self, tag: str | None) -> None:
        if tag != self._latest:
            self._latest = tag
            self.latestChanged.emit(tag)
