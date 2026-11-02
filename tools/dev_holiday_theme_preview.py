"""공휴일 테마 개발 미리보기: 날짜를 고정해 앱을 합성 데이터 폴더에서 띄운다(v4.6).

    .\\.venv\\Scripts\\python.exe tools/dev_holiday_theme_preview.py --date 2026-12-25

- 데이터 폴더는 `output/harness/<run-id>/appdata`(합성)다. 실제 AppData·DB·salt·잠금 파일,
  자동 실행 레지스트리를 건드리지 않는다. 같은 합성 데이터로 다시 보려면 `--reuse <run-id>`.
- `holiday_theme.current_match`만 그 날짜로 고정한다. 앱의 오늘 날짜(달력의 오늘 칸)는 실제 오늘이다.
- 배포 EXE·`build.spec`·`build_app.py`에 넣지 않는다(tests/test_source_layout.py가 막는다).
  테마 판정에 날짜를 바꾸는 숨은 옵션이나 환경 변수를 앱에 두지 않기 위한 개발 전용 도구다.
"""

import argparse
from datetime import date
import json
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # `python tools/...` 직접 실행에서 `tools` 패키지를 찾게 한다.

from tools import verify  # noqa: E402  (create_run_dir·isolated_env: 하네스와 같은 격리 규칙)

MAIN_SCRIPT = ROOT / "main.py"
ISOLATED_KEYS = ("LOCALAPPDATA", "CLIMATENOTE_TEST_APPDATA", "CLIMATENOTE_SKIP_STARTUP_REFRESH")
SCALES = ("compact", "medium", "large")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", required=True, type=date.fromisoformat,
                        help="테마 판정에 쓸 날짜(YYYY-MM-DD). 공휴일 3일 전부터 마지막 날까지 테마가 보인다.")
    parser.add_argument("--scale", choices=SCALES, default="compact",
                        help="새 합성 데이터의 캘린더 크기(기본 compact). --reuse에서는 저장된 값을 쓴다.")
    parser.add_argument("--theme", choices=("on", "off"), default="on",
                        help="설정의 공휴일 테마 스위치(기본 on). 합성 데이터에만 쓴다.")
    parser.add_argument("--reuse", metavar="RUN_ID",
                        help="output/harness/<RUN_ID>의 합성 데이터를 다시 쓴다(새로 만들지 않는다).")
    parser.add_argument("--no-seed", action="store_true",
                        help="일정·스티키·D-Day·집중 위젯 합성 데이터를 넣지 않는다.")
    parser.add_argument("--check-only", action="store_true",
                        help="앱을 띄우지 않고 격리 경로와 고정 날짜의 판정만 JSON으로 출력한다.")
    return parser


def prepare_run(reuse: str | None = None) -> Path:
    """합성 실행 폴더를 만들고 격리 환경 변수를 이 프로세스에 건다. 앱 모듈을 import하기 전에 불러야 한다."""
    if reuse is None:
        run_dir = verify.create_run_dir()
    else:
        run_dir = verify.inside(ROOT / "output" / "harness" / reuse, ROOT / "output" / "harness")
        if not run_dir.is_dir():
            raise SystemExit(f"합성 실행 폴더가 없습니다: {run_dir}")
    env = verify.isolated_env(run_dir)
    os.environ.update({key: env[key] for key in ISOLATED_KEYS})
    os.environ.pop("LUNAR_API_KEY", None)
    return run_dir


def pin_theme_date(holiday_theme, day: date) -> None:
    """화면 코드가 날짜를 얻는 유일한 입구 `current_match`만 고정한다."""
    import holidays
    resolve = holiday_theme.resolve_holiday_theme
    table = holidays.KOREAN_HOLIDAYS
    holiday_theme.current_match = lambda today=None: resolve(day, table)


def seed_synthetic_data(db, scale: str, pinned: date) -> None:
    """새 합성 DB와 눈에 보이는 위젯 몇 개. 크기 선택 창이 뜨지 않게 DB를 먼저 만든다."""
    db.migrate(initial_calendar_scale=scale)
    today = date.today()
    db.add_schedule(today.isoformat(), "공휴일 테마 미리보기 일정")
    db.add_schedule(today.isoformat(), "두 번째 합성 일정", "#4CC9F0")
    db.add_schedule(pinned.isoformat(), "고정 날짜의 합성 일정", "#FF6B6B")
    note = db.create_sticky_note("memo", 80, 80)
    db.update_sticky_note(note, content="<p>합성 메모: 스티키 머리띠와 스티커를 본다.</p>")
    db.create_dday_widget("합성 D-Day", pinned.isoformat(), 80, 420)
    db.create_focus_widget("합성 집중 목표", db.DEFAULT_FOCUS_MODE, 420, 80)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = prepare_run(args.reuse)
    appdata = run_dir / "appdata"
    # main.py를 가져오기만 한다(`__main__`이 아니라 main()은 아직 안 돈다). 이 시점에 앱 모듈이
    # 격리된 LOCALAPPDATA를 보고, main.py 맨 위가 src 경로를 넣는다.
    entry = runpy.run_path(str(MAIN_SCRIPT), run_name="dev_holiday_theme_preview")
    import database as db
    import holiday_theme
    import security

    if Path(security.APP_DIR).resolve().parent != appdata.resolve():
        raise SystemExit(f"격리 실패: 앱 데이터 폴더가 합성 폴더가 아닙니다: {security.APP_DIR}")
    pin_theme_date(holiday_theme, args.date)
    match = holiday_theme.current_match()
    report = {"run_dir": str(run_dir), "app_dir": str(security.APP_DIR), "date": args.date.isoformat(),
              "theme": match.theme.key if match else None, "in_holiday": bool(match and match.in_holiday)}
    print(json.dumps(report, ensure_ascii=False), flush=True)
    if args.check_only:
        return 0
    if args.reuse is None:
        if not args.no_seed:
            seed_synthetic_data(db, args.scale, args.date)
        else:
            db.migrate(initial_calendar_scale=args.scale)
    db.save_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "1" if args.theme == "on" else "0")
    sys.argv = [str(MAIN_SCRIPT)]
    entry["main"]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
