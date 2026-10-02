"""비동기 변환 작업과 그 작업의 Windows Job/임시 폴더만 소유한다."""
import json
from pathlib import Path
import sys
import tempfile
import uuid

import pywintypes

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from app_paths import resource_root
from hwp_conversion import ConversionError, publish_result


def worker_command(source, stage, job_name):
    arguments = [] if getattr(sys, "frozen", False) else [str(resource_root() / "main.py")]
    return sys.executable, [*arguments, "--hwp-convert-worker", str(source), str(stage), job_name]


class ConversionJob:
    def __init__(self):
        import win32job
        self.name = "Local\\ClimateNote-Hwp-" + uuid.uuid4().hex
        self.handle = win32job.CreateJobObject(None, self.name)
        try:
            limits = win32job.QueryInformationJobObject(self.handle, win32job.JobObjectExtendedLimitInformation)
            limits["BasicLimitInformation"]["LimitFlags"] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(self.handle, win32job.JobObjectExtendedLimitInformation, limits)
        except pywintypes.error:
            self.close()
            raise

    def assign(self, pid):
        import win32api
        import win32job
        process = win32api.OpenProcess(0x0100 | 0x0001, False, pid)
        try:
            win32job.AssignProcessToJobObject(self.handle, process)
        finally:
            process.Close()

    def close(self):
        if self.handle is not None:
            self.handle.Close()
            self.handle = None


class ConversionRunner(QObject):
    finished = Signal(bool, str, str)  # 성공, 결과 경로, 사용자용 상태

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = self._job = self._temporary = None
        self._source = self._directory = None
        self._cancelled = False
        self._failure = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._timeout)

    @property
    def busy(self):
        return self._process is not None

    def start(self, source, directory):
        if self.busy:
            return False
        self._cancelled, self._failure = False, ""
        try:
            self._source, self._directory = Path(source).resolve(), Path(directory).resolve()
            self._temporary = tempfile.TemporaryDirectory(prefix=".climatenote-hwp-", dir=self._directory)
            self._job = ConversionJob()
        except (OSError, RuntimeError, pywintypes.error) as exc:
            self._cleanup()
            raise ConversionError("변환 작업을 준비할 수 없습니다. 저장 폴더 권한을 확인해 주세요.") from exc
        process = QProcess(self)
        self._process = process
        program, arguments = worker_command(self._source, Path(self._temporary.name), self._job.name)
        process.started.connect(self._started)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._process_error)
        process.setProgram(program)
        process.setArguments(arguments)
        process.start()
        self._timer.start(105000)
        return True

    def _started(self):
        process = self.sender()
        if process is not self._process:
            return
        if self._cancelled:
            process.kill()
            return
        try:
            self._job.assign(int(process.processId()))
            Path(self._temporary.name, "go").touch(exist_ok=False)
        except (OSError, RuntimeError, pywintypes.error):
            self._failure = "변환 작업을 안전하게 분리할 수 없습니다."
            self.cancel()

    def _process_error(self, error):
        process = self.sender()
        if process is self._process and error == QProcess.FailedToStart:
            self._failure = "변환 작업 프로그램을 실행하지 못했습니다."
            self._complete(process, -1)

    def _timeout(self):
        self._failure = "변환 시간이 초과되었습니다."
        self.cancel()

    def cancel(self):
        self._cancelled = True
        if self._job:
            self._job.close()
        if self._process is not None and self._process.state() != QProcess.NotRunning:
            self._process.kill()

    def _finished(self, code, _status):
        self._complete(self.sender(), code)

    def _complete(self, process, code):
        if process is not self._process:
            return
        self._timer.stop()
        ok, output = False, ""
        message = self._failure or ("취소됨" if self._cancelled else "변환 작업이 비정상 종료되었습니다.")
        if not self._cancelled and not self._failure:
            try:
                with open(Path(self._temporary.name) / "result.json", encoding="utf-8") as stream:
                    result = json.loads(stream.read(16384))
                if code == 0 and result.get("ok") is True:
                    output = str(publish_result(Path(self._temporary.name) / "result.hwpx", self._directory, self._source.name))
                    ok, message = True, "완료"
                elif isinstance(result.get("message"), str):
                    message = result["message"][:300]
            except (OSError, ValueError, AttributeError):
                message = "변환 결과를 저장하지 못했습니다. 원본은 유지되었습니다."
        self._process = None
        process.started.disconnect(self._started)
        process.finished.disconnect(self._finished)
        process.errorOccurred.disconnect(self._process_error)
        process.setParent(None)
        process.deleteLater()
        cleanup_ok = self._cleanup()
        if not cleanup_ok:
            message += " · 임시 파일 정리를 완료하지 못했습니다."
        self.finished.emit(ok, output, message)

    def _cleanup(self):
        if self._job:
            self._job.close()
            self._job = None
        if self._temporary:
            temporary, self._temporary = self._temporary, None
            try:
                temporary.cleanup()
            except OSError:
                return False  # 원본/결과를 삭제하지 않고 UI에 정리 실패를 알린다.
        return True

    def shutdown(self):
        self.cancel()
        if self._process is not None:
            self._process.waitForFinished(3000)
        if self._process is None:
            self._cleanup()
