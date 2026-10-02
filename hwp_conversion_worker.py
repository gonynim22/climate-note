"""앱 초기화 없는 일회성 작업 진입점. 부모 Job 배정 뒤 go 파일을 받아 시작한다."""
import json
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import time

from hwp_conversion import (
    ConversionError, MAX_SOURCE_BYTES, detect_environment, validate_hwp, validate_hwpx,
)


@contextmanager
def external_engine_environment(env):
    """번들 DLL 검색 경로가 설치된 한컴 프로세스로 상속되지 않게 한다."""
    if not getattr(sys, "frozen", False):
        yield env
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetDllDirectoryW.argtypes = [wintypes.DWORD, wintypes.LPWSTR]
    kernel.GetDllDirectoryW.restype = wintypes.DWORD
    kernel.SetDllDirectoryW.argtypes = [wintypes.LPCWSTR]
    kernel.SetDllDirectoryW.restype = wintypes.BOOL
    previous = ctypes.create_unicode_buffer(kernel.GetDllDirectoryW(0, None) + 1)
    kernel.GetDllDirectoryW(len(previous), previous)
    bundle = os.path.normcase(os.path.normpath(sys._MEIPASS))
    clean = dict(env)
    clean["PATH"] = os.pathsep.join(
        entry for entry in env.get("PATH", "").split(os.pathsep)
        if entry and (normalized := os.path.normcase(os.path.normpath(entry.strip('"')))) != bundle
        and not normalized.startswith(bundle + os.sep)
    )
    if not kernel.SetDllDirectoryW(None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield clean
    finally:
        if not kernel.SetDllDirectoryW(previous.value or None):
            raise ctypes.WinError(ctypes.get_last_error())


def convert_to_stage(source, stage):
    environment = detect_environment()
    if not environment.available:
        raise ConversionError(environment.message)
    source = Path(source)
    if source.suffix.lower() != ".hwp" or not source.is_file():
        raise ConversionError("HWP 파일을 선택해 주세요.")
    copied = stage / "input.hwp"
    output = stage / "result.hwpx"
    with open(source, "rb") as original, open(copied, "xb") as target:
        before = os.fstat(original.fileno())
        count = 0
        while chunk := original.read(1024 * 1024):
            count += len(chunk)
            if count > MAX_SOURCE_BYTES:
                raise ConversionError("100 MB 이하의 HWP 파일을 선택해 주세요.")
            target.write(chunk)
        after = os.fstat(original.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ConversionError("복사 중 원본이 변경되었습니다. 저장을 마친 뒤 다시 시도해 주세요.")
    validate_hwp(copied)
    env = os.environ.copy()
    for variable in ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        folder = stage / variable
        folder.mkdir()
        env[variable] = str(folder)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    with external_engine_environment(env) as engine_env:
        result = subprocess.run(
            [str(environment.converter), str(copied), str(output)], cwd=stage, env=engine_env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            shell=False, startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW, timeout=90,
        )
    if result.returncode != 0:
        raise ConversionError("한컴 변환기가 문서를 변환하지 못했습니다.")
    validate_hwpx(output)


def worker_main(arguments):
    if len(arguments) != 3:
        return 2
    source, folder, job_name = arguments
    stage = Path(folder).resolve()
    # onefile 부트로더가 부모의 Job 배정 전에 자식을 만든 경우도 직접 가입한다.
    # 자식이 Job 핸들을 보유하면 부모의 Close로 종료되지 않으므로 즉시 닫는다.
    import pywintypes
    import win32api
    import win32job
    try:
        job = win32job.OpenJobObject(win32job.JOB_OBJECT_ASSIGN_PROCESS | win32job.JOB_OBJECT_QUERY, False, job_name)
        try:
            process = win32api.GetCurrentProcess()
            if not win32job.IsProcessInJob(process, job):
                win32job.AssignProcessToJobObject(job, process)
        finally:
            job.Close()
    except pywintypes.error:
        return 2  # 소유 Job에 들어갈 수 없으면 파일 접근/변환을 시작하지 않는다.
    # stdin/stdout은 PyInstaller --noconsole에서 None일 수 있으므로 파일로 교신.
    deadline = time.monotonic() + 15
    while not (stage / "go").is_file():
        if time.monotonic() >= deadline:
            return 2
        time.sleep(.05)
    try:
        convert_to_stage(source, stage)
        result = {"ok": True}
    except ConversionError as exc:
        result = {"ok": False, "message": str(exc)}
    except subprocess.TimeoutExpired:
        result = {"ok": False, "message": "변환 시간이 초과되었습니다. 문서를 확인한 뒤 다시 시도해 주세요."}
    except PermissionError:
        result = {"ok": False, "message": "파일 접근 권한이 없습니다. 문서를 닫거나 다른 저장 폴더를 선택해 주세요."}
    except (OSError, ValueError, ImportError, pywintypes.error):
        result = {"ok": False, "message": "파일을 읽거나 변환할 수 없습니다. 설치 상태와 저장 공간을 확인해 주세요."}
    with open(stage / "result.json", "w", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False)
    return 0 if result["ok"] else 1
