"""새 버전 알림 개발 미리보기: 최신 버전을 가짜로 넣어 알림·점·안내창 강조를 합성 데이터에서 본다.

    .\\.venv\\Scripts\\python.exe tools/dev_update_check_preview.py --latest v4.7
    .\\.venv\\Scripts\\python.exe tools/dev_update_check_preview.py --latest v4.7 --scale medium --date 2026-12-25

- 데이터 폴더는 `output/harness/<run-id>/appdata`(합성)다. 실제 AppData·DB·salt·잠금 파일,
  자동 실행 레지스트리를 건드리지 않는다. 같은 합성 데이터로 다시 보려면 `--reuse <run-id>`.
- `update_check.check_latest`를 바꿔 끼우므로 네트워크를 쓰지 않는다. 첫 확인은 1초 뒤다.
- 배포 EXE·`build.spec`·`build_app.py`에 넣지 않는다(tests/test_source_layout.py가 막는다).
  앱에 버전을 바꾸는 숨은 옵션이나 환경 변수를 두지 않기 위한 개발 전용 도구다.
"""

import argparse
from datetime import date
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # `python tools/...` 직접 실행에서 `tools` 패키지를 찾게 한다.

from tools import dev_holiday_theme_preview as theme_preview  # noqa: E402  (합성 폴더·시드 도구 공유)

MAIN_SCRIPT = ROOT / "main.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--latest", required=True, help="서버가 돌려준 것처럼 쓸 태그(예: v4.7). 지금 버전보다 새로워야 한다.")
    parser.add_argument("--scale", choices=theme_preview.SCALES, default="compact",
                        help="새 합성 데이터의 캘린더 크기(기본 compact). --reuse에서는 저장된 값을 쓴다.")
    parser.add_argument("--date", type=date.fromisoformat,
                        help="공휴일 테마 판정에 쓸 날짜(YYYY-MM-DD). 머리줄 색이 바뀐 점 테두리를 볼 때 쓴다.")
    parser.add_argument("--reuse", metavar="RUN_ID",
                        help="output/harness/<RUN_ID>의 합성 데이터를 다시 쓴다(새로 만들지 않는다).")
    parser.add_argument("--check-only", action="store_true",
                        help="앱을 띄우지 않고 격리 경로와 판정만 JSON으로 출력한다.")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = theme_preview.prepare_run(args.reuse)
    appdata = run_dir / "appdata"
    # main.py를 가져오기만 한다. 이 시점에 앱 모듈이 격리된 LOCALAPPDATA를 보고, main.py 맨 위가 src 경로를 넣는다.
    entry = runpy.run_path(str(MAIN_SCRIPT), run_name="dev_update_check_preview")
    from app_info import APP_VERSION
    import database as db
    import holiday_theme
    import security
    import ui_update_check
    import update_check

    if Path(security.APP_DIR).resolve().parent != appdata.resolve():
        raise SystemExit(f"격리 실패: 앱 데이터 폴더가 합성 폴더가 아닙니다: {security.APP_DIR}")
    if not update_check.is_newer(args.latest, APP_VERSION):
        raise SystemExit(f"--latest는 지금 버전({APP_VERSION})보다 새로운 태그여야 합니다: {args.latest}")
    report = {"run_dir": str(run_dir), "app_dir": str(security.APP_DIR), "latest": args.latest,
              "current": APP_VERSION}
    print(json.dumps(report, ensure_ascii=False), flush=True)
    if args.check_only:
        return 0
    if args.date is not None:
        theme_preview.pin_theme_date(holiday_theme, args.date)
    if args.reuse is None:
        theme_preview.seed_synthetic_data(db, args.scale, args.date or date.today())
    db.save_setting(db.SETTING_INTERNET_ACCESS, "1")
    update_check.check_latest = lambda opener=None: update_check.CheckResult(latest_tag=args.latest)
    ui_update_check.FIRST_CHECK_DELAY_MS = 1000
    sys.argv = [str(MAIN_SCRIPT)]
    entry["main"]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
