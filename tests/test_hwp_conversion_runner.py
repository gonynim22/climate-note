"""실제 자식 프로세스로 완료·취소·Job 할당 실패·임시 파일 회수를 검증한다."""
import sys
from pathlib import Path

import pytest

import hwp_conversion_runner as module


@pytest.fixture
def fake_worker(tmp_path, monkeypatch):
    script = tmp_path / "worker.py"
    script.write_text('''
from pathlib import Path
import json, sys, time, subprocess
stage, mode = Path(sys.argv[1]), sys.argv[2]
while not (stage / 'go').exists():
    time.sleep(.01)
if mode == 'hang':
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    (stage / 'child.pid').write_text(str(child.pid))
    time.sleep(60)
elif mode == 'failure':
    (stage / 'result.json').write_text(json.dumps({'ok':False,'message':'expected failure'}))
else:
    (stage / 'result.hwpx').write_bytes(b'validated result')
    (stage / 'result.json').write_text(json.dumps({'ok':True}))
''', encoding="utf-8")
    def install(mode):
        monkeypatch.setattr(module, "worker_command", lambda source, stage, job: (sys.executable, [str(script), str(stage), mode]))
    return install


@pytest.mark.parametrize("mode", ["success", "failure"])
def test_actual_worker_completion_and_cleanup(qtbot, tmp_path, fake_worker, mode):
    fake_worker(mode)
    source = tmp_path / "입력.hwp"
    source.write_bytes(b"original")
    runner = module.ConversionRunner()
    try:
        with qtbot.waitSignal(runner.finished, timeout=10000) as result:
            runner.start(source, tmp_path)
        ok, output, message = result.args
        assert ok == (mode == "success")
        assert source.read_bytes() == b"original"
        assert not runner.busy
        assert not list(tmp_path.glob(".climatenote-hwp-*"))
        if ok:
            assert Path(output).read_bytes() == b"validated result"
        else:
            assert output == "" and message == "expected failure"
    finally:
        runner.shutdown()


@pytest.mark.parametrize("method", ["cancel", "_timeout", "shutdown"])
def test_cancel_does_not_publish_and_removes_owned_work(qtbot, tmp_path, fake_worker, method):
    fake_worker("hang")
    source = tmp_path / "입력.hwp"
    source.write_bytes(b"original")
    runner = module.ConversionRunner()
    child = None
    try:
        runner.start(source, tmp_path)
        qtbot.waitUntil(lambda: (Path(runner._temporary.name) / "child.pid").exists())
        import win32api
        import win32event
        child = win32api.OpenProcess(0x00100000, False, int((Path(runner._temporary.name) / "child.pid").read_text()))
        with qtbot.waitSignal(runner.finished, timeout=10000) as result:
            getattr(runner, method)()
        assert not result.args[0]
        assert not (tmp_path / "입력.hwpx").exists()
        assert source.read_bytes() == b"original"
        assert not list(tmp_path.glob(".climatenote-hwp-*"))
        qtbot.waitUntil(lambda: win32event.WaitForSingleObject(child, 0) == 0)
    finally:
        runner.shutdown()
        if child:
            child.Close()


def test_cancel_before_started_never_sends_go(qtbot, tmp_path, fake_worker):
    fake_worker("success")
    runner = module.ConversionRunner()
    try:
        with qtbot.waitSignal(runner.finished, timeout=10000) as result:
            runner.start(tmp_path / "input.hwp", tmp_path)
            runner.cancel()
        assert not result.args[0]
        assert not list(tmp_path.glob("*.hwpx"))
        assert not list(tmp_path.glob(".climatenote-hwp-*"))
    finally:
        runner.shutdown()


def test_job_assignment_failure_never_releases_worker(qtbot, tmp_path, fake_worker, monkeypatch):
    import pywintypes
    fake_worker("success")
    def denied(self, pid):
        raise pywintypes.error(5, "AssignProcessToJobObject", "denied")
    monkeypatch.setattr(module.ConversionJob, "assign", denied)
    runner = module.ConversionRunner()
    try:
        with qtbot.waitSignal(runner.finished, timeout=10000) as result:
            runner.start(tmp_path / "input.hwp", tmp_path)
        assert not result.args[0] and "분리" in result.args[2]
        assert not list(tmp_path.glob("*.hwpx"))
        assert not list(tmp_path.glob(".climatenote-hwp-*"))
    finally:
        runner.shutdown()
