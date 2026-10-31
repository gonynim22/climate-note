"""한 일괄에 한 QProcess, 소유 Windows Job, 부모만 수행하는 결과 확정."""
import json
from pathlib import Path
import sys
import tempfile
import time

import pywintypes
from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from app_paths import resource_root
from file_conversion import FileConversionError, MAX_FILES, TARGETS, output_name, publish_output, settings_for
from hwp_conversion_runner import ConversionJob


def worker_command(stage, job_name):
    arguments = [] if getattr(sys, "frozen", False) else [str(resource_root() / "main.py")]
    return sys.executable, [*arguments, "--file-convert-worker", str(stage), job_name]


class FileConversionRunner(QObject):
    item_finished = Signal(int, dict)
    finished = Signal(str)  # 정리 실패 등 일괄 상태
    TIMEOUT_SECONDS = 60

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = self._job = None
        self._temporaries = []
        self._items = []
        self.results = {}
        self._cancelled = False
        self._failure = ""
        self._inspect = False
        self._progress = b""
        self._last_progress = 0
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._poll)

    @property
    def busy(self):
        return self._process is not None

    def start(self, sources, target_id=None, settings=None, directory=None, *, inspect_only=False):
        if self.busy:
            return False
        if not sources or len(sources) > MAX_FILES:
            raise FileConversionError("100개 이하 파일을 골라 주세요")
        self._cancelled, self._failure, self._progress = False, "", b""
        self.results, self._items = {}, []
        self._inspect, self._target = inspect_only, target_id
        options = {} if inspect_only else settings_for(target_id, settings)
        paths = [Path(source).resolve() for source in sources]
        batches = [paths] if target_id == "pdf_bundle" else [[path] for path in paths]
        roots = {}
        try:
            for index, batch in enumerate(batches):
                destination = Path(directory).resolve() if directory else batch[0].parent
                # 판독은 저장 폴더 선택 전에도 필요하다. 원본 폴더 쓰기 권한을 요구하지 않는다.
                key = None if inspect_only else destination
                if key not in roots:
                    temporary = tempfile.TemporaryDirectory(prefix=".climatenote-conv-", dir=key)
                    self._temporaries.append(temporary)
                    roots[key] = Path(temporary.name)
                item_stage = roots[key] / "items" / str(index)
                item_stage.mkdir(parents=True)
                self._items.append({"sources": [str(path) for path in batch], "stage": str(item_stage),
                                    "directory": str(destination)})
            self._stage = Path(self._temporaries[0].name)
            with open(self._stage / "job.json", "x", encoding="utf-8") as stream:
                json.dump({"inspect": inspect_only, "target": target_id, "settings": options, "items": self._items},
                          stream, ensure_ascii=False)
            self._job = ConversionJob()
        except (OSError, RuntimeError, pywintypes.error) as exc:
            cleanup = self._cleanup()
            raise FileConversionError("저장 폴더에 쓸 수 없어요" + ("" if cleanup else " · 임시 파일 정리를 완료하지 못했습니다")) from exc
        process = QProcess(self)
        self._process = process
        process.started.connect(self._started)
        process.finished.connect(self._process_finished)
        process.errorOccurred.connect(self._process_error)
        program, arguments = worker_command(self._stage, self._job.name)
        process.setProgram(program)
        process.setArguments(arguments)
        # 디코더 진단에 원본 정보가 섞여도 지속 로그/부모 버퍼에 남기지 않는다.
        process.setStandardOutputFile(QProcess.nullDevice())
        process.setStandardErrorFile(QProcess.nullDevice())
        self._last_progress = time.monotonic()
        process.start()
        self._timer.start()
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
            (self._stage / "go").touch(exist_ok=False)
        except (OSError, RuntimeError, pywintypes.error):
            self._failure = "변환 작업을 안전하게 분리할 수 없습니다"
            self.cancel()

    def _process_error(self, error):
        if self.sender() is self._process and error == QProcess.FailedToStart:
            self._failure = "변환 작업 프로그램을 실행하지 못했습니다"
            self._complete(self._process, -1)

    def _poll(self):
        if not self.busy or self._cancelled:
            return
        try:
            with open(self._stage / "progress.json", "rb") as stream:
                progress = stream.read(1024)
            if progress != self._progress:
                self._progress = progress
                self._last_progress = time.monotonic()
        except FileNotFoundError:
            pass  # 부트로더/첫 디코더 초기화 중에는 아직 진행 파일이 없다. 제한 시간은 적용한다.
        except OSError:
            self._failure = "변환 진행 상태를 읽을 수 없어요"
            self.cancel()
            return
        self._collect()
        if self.busy and not self._cancelled and time.monotonic() - self._last_progress > self.TIMEOUT_SECONDS:
            self._timeout()

    def _collect(self):
        for index, item in enumerate(self._items):
            if self._cancelled or index in self.results:
                continue
            result_path = Path(item["stage"]) / "result.json"
            if not result_path.is_file():
                break
            try:
                with open(result_path, encoding="utf-8") as stream:
                    result = json.loads(stream.read(512 * 1024))
                if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
                    raise ValueError("invalid result")
                if result["ok"] and not self._inspect and not result.get("skipped"):
                    target = TARGETS[self._target]
                    expected = "result" if target.naming == "pages" else "result." + (target.extension or Path(item["sources"][0]).suffix.lstrip("."))
                    if result.get("artifact") != expected:
                        raise ValueError("invalid artifact")
                    artifact = Path(item["stage"]) / expected
                    if artifact.is_symlink() or (target.naming == "pages" and not artifact.is_dir()):
                        raise ValueError("invalid artifact")
                    name = output_name(item["sources"], self._target)
                    result["bytes"] = (sum(path.stat().st_size for path in artifact.iterdir())
                                       if artifact.is_dir() else artifact.stat().st_size)
                    output = publish_output(artifact, item["directory"], name, target.naming == "pages")
                    result["output"] = str(output)
            except (OSError, ValueError, TypeError, KeyError):
                result = {"ok": False, "message": "변환 결과를 저장하지 못했어요. 원본은 그대로 두었어요"}
            self.results[index] = result
            self._last_progress = time.monotonic()
            self.item_finished.emit(index, result)

    def _timeout(self):
        self._failure = "시간이 너무 오래 걸려 멈췄어요"
        self.cancel()

    def cancel(self):
        self._cancelled = True  # Job 종료 전에 늦은 결과의 확정을 금지한다.
        self._timer.stop()
        if self._job:
            self._job.close()
        if self._process is not None and self._process.state() != QProcess.NotRunning:
            self._process.kill()

    def _process_finished(self, code, _status):
        self._complete(self.sender(), code)

    def _complete(self, process, code):
        if process is None or process is not self._process:
            return
        self._timer.stop()
        if not self._cancelled:
            self._collect()
        first = True
        for index in range(len(self._items)):
            if index in self.results:
                continue
            message = ((self._failure or "변환 작업이 비정상 종료되었습니다") if first and (self._failure or not self._cancelled)
                       else "취소됨")
            result = {"ok": False, "cancelled": message == "취소됨", "message": message}
            self.results[index] = result
            self.item_finished.emit(index, result)
            first = False
        self._process = None
        process.started.disconnect(self._started)
        process.finished.disconnect(self._process_finished)
        process.errorOccurred.disconnect(self._process_error)
        process.deleteLater()
        cleanup = self._cleanup()
        self.finished.emit("" if cleanup else "임시 파일 정리를 완료하지 못했습니다")

    def _cleanup(self):
        if self._job:
            self._job.close()
            self._job = None
        ok = True
        for temporary in self._temporaries:
            try:
                temporary.cleanup()
            except OSError:
                ok = False  # 이 작업이 소유한 폴더만 정리하며 실패를 화면에 알린다.
        self._temporaries.clear()
        return ok

    def shutdown(self):
        self.cancel()
        if self._process is not None:
            self._process.waitForFinished(3000)
        if self._process is None:
            self._cleanup()
