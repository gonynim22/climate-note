"""앱 초기화 전 분기하는 파일 변환 일괄 worker. 파일 판독은 Job 가입 후에만."""
import json
from pathlib import Path
import time


def write_json(path, value):
    temporary = path.with_suffix(".pending")
    with open(temporary, "x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False)
    temporary.replace(path)


def worker_main(arguments):
    if len(arguments) != 2:
        return 2
    stage, job_name = Path(arguments[0]).resolve(), arguments[1]
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
        return 2
    deadline = time.monotonic() + 15
    while not (stage / "go").is_file():
        if time.monotonic() >= deadline:
            return 2
        time.sleep(.05)

    # onefile 자식도 위의 가입 확인을 마친 뒤 Qt/디코더를 초기화한다.
    from PySide6.QtGui import QGuiApplication
    from file_conversion import FileConversionError, convert_item, inspect_source
    app = QGuiApplication(["climatenote-worker", "-platform", "offscreen"])
    try:
        with open(stage / "job.json", encoding="utf-8") as stream:
            request = json.load(stream)
        for index, item in enumerate(request["items"]):
            item_stage = Path(item["stage"])

            def progress():
                write_json(stage / "progress.json", {"index": index, "time": time.monotonic_ns()})

            progress()
            try:
                if request["inspect"]:
                    result = {"ok": True, "metadata": inspect_source(item["sources"][0])}
                else:
                    result = convert_item(item["sources"], request["target"], request["settings"], item_stage, progress)
            except FileConversionError as exc:
                result = {"ok": False, "message": str(exc)}
            except MemoryError:
                result = {"ok": False, "message": "사진이 너무 커서 열 수 없어요"}
            except OSError:
                result = {"ok": False, "message": "파일을 읽거나 저장할 수 없어요. 권한과 저장 공간을 확인해 주세요"}
            write_json(item_stage / "result.json", result)
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        return 2  # 불완전한 요청/결과는 부모가 비정상 종료로 표시한다.
    finally:
        app.quit()
