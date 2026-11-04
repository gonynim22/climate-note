"""새 버전 확인 예약: 꺼진 PC는 요청 0회, 끈 뒤 늦은 결과는 버리고, 실패는 조용히 한 번만 다시 본다."""
import logging
import re
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import database as db
import ui_update_check
import update_check
from ui_update_check import POLL_INTERVAL_MS, UpdateCheckController
from update_check import CheckResult

FAILED = CheckResult(failure="timeout")


@pytest.fixture
def server(app_dir, monkeypatch):
    """check_latest를 바꾼다. answers를 차례로 돌려주고, gate를 걸면 그동안 응답을 붙잡는다."""
    state = SimpleNamespace(answers=[CheckResult(latest_tag="v4.7")], calls=0, gate=None)

    def fake(opener=None):
        state.calls += 1
        if state.gate is not None:
            state.gate.wait(5)
        return state.answers.pop(0) if len(state.answers) > 1 else state.answers[0]

    monkeypatch.setattr(update_check, "check_latest", fake)
    return state


def _controller():
    controller = UpdateCheckController(current_version="v4.6")
    signals = []
    controller.latestChanged.connect(signals.append)
    return controller, signals


def _turn_on():
    db.save_setting(db.SETTING_INTERNET_ACCESS, "1")


def _fire(qtbot, controller, server):
    """예약 시각이 된 것처럼 하고 결과 반영까지 기다린다."""
    before = server.calls
    controller._timer.timeout.emit()
    qtbot.waitUntil(lambda: server.calls == before + 1 and not controller._poll.isActive())


def _hold_request(qtbot, controller, server):
    """요청을 응답 전 상태로 붙잡아 둔다."""
    server.gate = threading.Event()
    before = server.calls
    controller._timer.timeout.emit()
    qtbot.waitUntil(lambda: server.calls == before + 1)


@pytest.mark.parametrize("value", [None, "yes"])
def test_off_means_no_request_at_all(qtbot, app_dir, monkeypatch, value):
    def forbidden():
        raise AssertionError("꺼진 PC에서 요청을 만들었다")

    monkeypatch.setattr(update_check, "https_only_opener", forbidden)
    if value is not None:
        db.save_setting(db.SETTING_INTERNET_ACCESS, value)
    controller, signals = _controller()
    controller.start()
    controller.apply_setting()
    assert not controller._timer.isActive()
    controller._timer.timeout.emit()
    qtbot.wait(POLL_INTERVAL_MS)
    assert not controller._timer.isActive() and not controller._poll.isActive()
    assert controller._worker is None and signals == []


def test_key_is_read_again_just_before_request(qtbot, server):
    _turn_on()
    controller, _ = _controller()
    controller.start()
    db.save_setting(db.SETTING_INTERNET_ACCESS, "0")
    controller._timer.timeout.emit()
    qtbot.wait(POLL_INTERVAL_MS)
    assert server.calls == 0 and not controller._timer.isActive() and controller.latest is None


def test_unreadable_key_counts_as_off(qtbot, server, monkeypatch):
    _turn_on()

    def broken(key, default=""):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(db, "get_setting", broken)
    controller, _ = _controller()
    controller.start()
    assert not controller._timer.isActive()


def test_start_waits_a_minute_then_a_day(qtbot, server):
    _turn_on()
    controller, _ = _controller()
    controller.start()
    assert controller._timer.isActive() and controller._timer.interval() == 60_000
    assert controller._timer.isSingleShot()
    _fire(qtbot, controller, server)
    assert controller._timer.isActive() and controller._timer.interval() == 86_400_000


def test_turning_on_checks_after_five_seconds(qtbot, server):
    controller, _ = _controller()
    controller.start()
    _turn_on()
    controller.apply_setting()
    assert controller._timer.isActive() and controller._timer.interval() == 5_000


def test_settings_change_while_running_keeps_schedule(qtbot, server):
    """가져오기가 끝날 때마다 불려도 예약을 앞당기지 않는다."""
    _turn_on()
    controller, _ = _controller()
    controller.start()
    controller.apply_setting()
    assert controller._timer.interval() == 60_000


def test_failure_retries_once_then_waits_a_day(qtbot, server, caplog):
    server.answers = [FAILED, FAILED, FAILED, FAILED]
    _turn_on()
    controller, signals = _controller()
    controller.start()
    with caplog.at_level(logging.ERROR, logger="app_error"):
        intervals = []
        for _ in range(3):
            _fire(qtbot, controller, server)
            intervals.append(controller._timer.interval())
    assert intervals == [3_600_000, 86_400_000, 3_600_000]
    assert [r.getMessage() for r in caplog.records if r.name == "app_error"] == ["새 버전 확인 실패: timeout"] * 3
    assert signals == []


def test_success_after_retry_starts_a_fresh_cycle(qtbot, server):
    server.answers = [FAILED, CheckResult(latest_tag="v4.6"), FAILED, FAILED]
    _turn_on()
    controller, _ = _controller()
    controller.start()
    intervals = []
    for _ in range(3):
        _fire(qtbot, controller, server)
        intervals.append(controller._timer.interval())
    assert intervals == [3_600_000, 86_400_000, 3_600_000]


def test_newer_tag_is_reported_once(qtbot, server):
    _turn_on()
    controller, signals = _controller()
    controller.start()
    _fire(qtbot, controller, server)
    _fire(qtbot, controller, server)
    assert signals == ["v4.7"] and controller.latest == "v4.7"


def test_failure_and_empty_answer_keep_known_latest(qtbot, server):
    server.answers = [CheckResult(latest_tag="v4.7"), FAILED, CheckResult()]
    _turn_on()
    controller, signals = _controller()
    controller.start()
    for _ in range(3):
        _fire(qtbot, controller, server)
    assert controller.latest == "v4.7" and signals == ["v4.7"]


def test_even_newer_tag_replaces_latest(qtbot, server):
    server.answers = [CheckResult(latest_tag="v4.7"), CheckResult(latest_tag="v4.8")]
    _turn_on()
    controller, signals = _controller()
    controller.start()
    _fire(qtbot, controller, server)
    _fire(qtbot, controller, server)
    assert signals == ["v4.7", "v4.8"]


def test_withdrawn_release_clears_latest(qtbot, server):
    server.answers = [CheckResult(latest_tag="v4.7"), CheckResult(latest_tag="v4.6")]
    _turn_on()
    controller, signals = _controller()
    controller.start()
    _fire(qtbot, controller, server)
    _fire(qtbot, controller, server)
    assert signals == ["v4.7", None] and controller.latest is None


def test_turning_off_drops_late_result_and_clears(qtbot, server):
    _turn_on()
    controller, signals = _controller()
    controller.start()
    controller._set_latest("v4.7")
    _hold_request(qtbot, controller, server)
    server.answers = [CheckResult(latest_tag="v4.9")]
    db.save_setting(db.SETTING_INTERNET_ACCESS, "0")
    controller.apply_setting()
    assert controller.latest is None and not controller._poll.isActive()
    server.gate.set()
    qtbot.waitUntil(lambda: not controller._worker.is_alive())
    qtbot.wait(POLL_INTERVAL_MS * 2)
    assert controller.latest is None and not controller._timer.isActive()
    assert signals == ["v4.7", None]


def test_quick_off_on_keeps_one_worker(qtbot, server):
    _turn_on()
    controller, _ = _controller()
    controller.start()
    _hold_request(qtbot, controller, server)
    db.save_setting(db.SETTING_INTERNET_ACCESS, "0")
    controller.apply_setting()
    _turn_on()
    controller.apply_setting()
    controller._timer.timeout.emit()
    assert server.calls == 1
    assert controller._timer.isActive() and controller._timer.interval() == 5_000
    server.gate.set()
    qtbot.waitUntil(lambda: not controller._worker.is_alive())
    controller._timer.timeout.emit()
    qtbot.waitUntil(lambda: server.calls == 2 and not controller._poll.isActive())


def test_stop_drops_late_result(qtbot, server):
    _turn_on()
    controller, signals = _controller()
    controller.start()
    _hold_request(qtbot, controller, server)
    controller.stop()
    server.gate.set()
    qtbot.waitUntil(lambda: not controller._worker.is_alive())
    qtbot.wait(POLL_INTERVAL_MS * 2)
    assert controller.latest is None and signals == [] and not controller._timer.isActive()


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_dead_worker_counts_as_failure(qtbot, app_dir, monkeypatch):
    def broken(opener=None):
        raise RuntimeError("작업 스레드가 죽었다")

    monkeypatch.setattr(update_check, "check_latest", broken)
    _turn_on()
    controller, _ = _controller()
    controller.start()
    controller._timer.timeout.emit()
    qtbot.waitUntil(lambda: not controller._poll.isActive())
    assert controller._timer.isActive() and controller._timer.interval() == 3_600_000


def test_controller_only_reads_the_key():
    source = Path(ui_update_check.__file__).read_text(encoding="utf-8")
    assert set(re.findall(r"\bdb\.(\w+)", source)) == {"get_setting", "SETTING_INTERNET_ACCESS"}
