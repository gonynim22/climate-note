"""실제 QProcess와 Windows Job으로 일괄·취소·시간 초과·정리를 검증."""
from pathlib import Path
import sys

import pytest

import file_conversion_runner as module


def test_real_batch_worker_outputs_and_isolation(qtbot, tmp_path):
    sources = [tmp_path / f"text{i}.csv" for i in range(3)]
    for source in sources:
        source.write_bytes("한글\r\n".encode("cp949"))
    runner = module.FileConversionRunner()
    try:
        with qtbot.waitSignal(runner.finished, timeout=20000):
            runner.start(sources, "utf8")
        assert len(runner.results) == 3 and all(r["ok"] for r in runner.results.values())
        assert all(Path(r["output"]).read_bytes() == "한글\r\n".encode("utf-8-sig") for r in runner.results.values())
        assert all(s.read_bytes() == "한글\r\n".encode("cp949") for s in sources)
        assert not list(tmp_path.glob(".climatenote-conv-*"))
    finally:
        runner.shutdown()


@pytest.fixture
def controlled_worker(tmp_path, monkeypatch):
    script = tmp_path / "batch.py"
    script.write_text('''
import json, sys, time
from pathlib import Path
root = Path(sys.argv[1])
while not (root / "go").exists():
    time.sleep(.01)
job = json.loads((root / "job.json").read_text(encoding="utf-8"))
for index, item in enumerate(job["items"]):
    stage = Path(item["stage"])
    (stage / "result.csv").write_bytes(b"published")
    if index == 0:
        (stage / "result.json").write_text(json.dumps({"ok": True, "artifact": "result.csv"}))
    else:
        (root / "waiting").touch()
        time.sleep(60)
''', encoding="utf-8")
    monkeypatch.setattr(module, "worker_command", lambda stage, job: (sys.executable, [str(script), str(stage)]))


@pytest.mark.parametrize("action", ["cancel", "_timeout", "shutdown"])
def test_partial_completion_cancel_timeout_and_late_result(qtbot, tmp_path, controlled_worker, action):
    sources = [tmp_path / f"input{i}.csv" for i in range(3)]
    for source in sources:
        source.write_bytes(b"source")
    runner = module.FileConversionRunner()
    try:
        runner.start(sources, "utf8")
        qtbot.waitUntil(lambda: 0 in runner.results, timeout=10000)
        output = Path(runner.results[0]["output"])
        stage = Path(runner._items[1]["stage"])
        # 취소 직전 결과가 생겨도 부모가 아직 확정하지 않은 결과는 남기지 않는다.
        (stage / "result.json").write_text('{"ok":true,"artifact":"result.csv"}', encoding="utf-8")
        with qtbot.waitSignal(runner.finished, timeout=10000):
            getattr(runner, action)()
        assert output.read_bytes() == b"published"
        assert not runner.results[1]["ok"] and not runner.results[2]["ok"]
        assert ("오래" in runner.results[1]["message"]) == (action == "_timeout")
        assert not (tmp_path / "input1_UTF-8.csv").exists()
        assert not list(tmp_path.glob(".climatenote-conv-*"))
    finally:
        runner.shutdown()


def test_cancel_before_start_and_job_denied(qtbot, tmp_path, monkeypatch):
    import pywintypes
    source = tmp_path / "a.csv"
    source.write_bytes(b"x")
    for denied in (False, True):
        runner = module.FileConversionRunner()
        try:
            if denied:
                def fail(self, pid):
                    raise pywintypes.error(5, "assign", "denied")
                monkeypatch.setattr(module.ConversionJob, "assign", fail)
            with qtbot.waitSignal(runner.finished, timeout=10000):
                runner.start([source], "cp949")
                if not denied:
                    runner.cancel()
            assert not runner.results[0]["ok"]
            assert not list(tmp_path.glob(".climatenote-conv-*"))
            assert not (tmp_path / "a_EUC-KR.csv").exists()
        finally:
            runner.shutdown()


def test_worker_entry_rejects_without_job_and_never_initializes_app(tmp_path):
    import subprocess
    import os
    sandbox = tmp_path / "empty_appdata"
    sandbox.mkdir()
    env = dict(os.environ, LOCALAPPDATA=str(sandbox), APPDATA=str(sandbox))
    result = subprocess.run([sys.executable, "main.py", "--file-convert-worker", str(tmp_path), "Local\\missing-file-job"],
                            env=env, timeout=20, capture_output=True)
    assert result.returncode == 2 and list(sandbox.iterdir()) == []


def test_batch_spans_source_directories_and_inspects_in_worker(qtbot, tmp_path):
    sources = []
    for name in ("one", "two"):
        folder = tmp_path / name
        folder.mkdir()
        source = folder / "표.csv"
        source.write_bytes("가나다\r\n".encode("cp949"))
        sources.append(source)
    runner = module.FileConversionRunner()
    try:
        with qtbot.waitSignal(runner.finished, timeout=15000):
            runner.start(sources, inspect_only=True)
        assert all(r["metadata"]["format"] == "cp949" for r in runner.results.values())
        with qtbot.waitSignal(runner.finished, timeout=15000):
            runner.start(sources, "utf8")
        assert [Path(r["output"]).parent for r in runner.results.values()] == [p.parent for p in sources]
        assert not list(tmp_path.rglob(".climatenote-conv-*"))
    finally:
        runner.shutdown()


def test_poll_enforces_no_progress_timeout(qtbot, tmp_path, controlled_worker):
    sources = [tmp_path / f"hang{i}.csv" for i in range(2)]
    for path in sources:
        path.write_bytes(b"source")
    runner = module.FileConversionRunner()
    runner.TIMEOUT_SECONDS = .6
    try:
        with qtbot.waitSignal(runner.finished, timeout=10000):
            runner.start(sources, "utf8")
        assert runner.results[0]["ok"]
        assert "오래" in runner.results[1]["message"]
        assert not list(tmp_path.glob(".climatenote-conv-*"))
    finally:
        runner.shutdown()


def test_failed_start_and_cleanup_failure_are_reported(qtbot, tmp_path, monkeypatch):
    source = tmp_path / "input.csv"
    source.write_bytes(b"x")
    monkeypatch.setattr(module, "worker_command", lambda *args: (str(tmp_path / "absent.exe"), []))
    runner = module.FileConversionRunner()
    cleanup = runner._cleanup

    def cleanup_warning():
        cleanup()
        return False

    monkeypatch.setattr(runner, "_cleanup", cleanup_warning)
    try:
        with qtbot.waitSignal(runner.finished, timeout=10000) as signal:
            runner.start([source], "cp949")
        assert "실행하지" in runner.results[0]["message"]
        assert "정리" in signal.args[0]
        assert not list(tmp_path.glob(".climatenote-conv-*"))
    finally:
        runner.shutdown()
