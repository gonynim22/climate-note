# 작업 기록: GitLab 루트 파일 정리 위험도 분석

작성일: 2026-10-31 / 상태: 분석 완료 · 파일 이동은 하지 않음 · 다른 모델 검증 대기

## 목표와 범위

- 목표: GitLab 첫 화면의 루트 목록(추적 폴더 10 + 파일 69 = 79줄)을 줄여 README가 빨리 보이게 할 때, 루트 항목별 안전·위험 수준을 근거와 함께 정한다.
- 변경 대상: 없음(분석만). 실측은 저장소를 `git archive`로 푼 복사본에서만 했다.
- 데이터 영향: 없음(7장).
- 제외 범위: 실제 이동, 정본 문서 갱신, GitLab·서버 설정 확인.
- 시작 시 사용자 변경: 미추적 `docs/work/` 기록과 `motion/`. 기준 커밋 `9cc9cb4`.

## 완료 조건

- [x] 루트 79개 항목 전부 분류(3장)
- [x] 방식 비교와 권장안(2장)
- [x] 복사본 실측: 시험 전체 비교, 빌드 7종, EXE 격리 실행·smoke(6장)
- [x] 반박 검토 2회 반영(근거 대조, 과소평가 사냥)
- [ ] 다른 모델 검증(사용자)
- [ ] 이동 여부 결정(사용자)

## 요약

- 권장은 **B안**이다. 앱 모듈 52개를 `src/` 폴더로 옮기되 패키지로 만들지 않고, `src/`를 import 경로에 넣는다. 모듈 이름이 그대로라 import 495곳과 모듈 이름 문자열 24곳을 고치지 않는다.
- 루트 79줄 → 1단계 28줄 → 2단계 25줄.
- [실측] B안 수정(20개 파일, +63/−29줄) 뒤 시험 3,110개의 결과가 원본 복사본과 같았다(차이 0).
- [실측] B안으로 만든 EXE는 모듈 541개의 이름·코드 객체가 원본 빌드와 같고, 이름 집합은 배포된 `dist/기후노트_v4.5.exe`와 같다. 저장소 smoke 5개 시나리오도 통과했다.
  - 정정(2026-10-31): 이 EXE(V3)에는 소스 실행 전용 수정 F5·F6이 빠져 있었다. 넣으면 `app_paths`·`ui_settings` 2개 모듈의 코드 객체가 달라진다. 바뀐 줄은 EXE에서 결과를 쓰지 않는다[판독](6.2).
- 사용자 데이터 영향 없음: 데이터 위치와 암호화 키가 코드 위치와 무관하다.
- 위험은 개별 파일보다 공통 장치에 있다.
  - 보호 시험의 빈 통과: 옮기면 `screen_text` 걷어내기 계약 시험이 앱 모듈을 보지 않고 통과한다(실측).
  - 빌드가 `src/`를 못 보는 변형: `app_info.py`를 루트에 남기고 `build.spec`을 안 고치면 빌드는 성공으로 끝나고 EXE만 오류 창을 띄운다(실측).
- A안(진짜 패키지)은 권장하지 않는다. import 495곳을 고쳐야 하고, 이름으로 검사하는 보호 시험 3곳이 조용히 꺼진다.
- 이동과 별개로 기존 결함 1건을 실측으로 확인했다: `screen_text/`를 걷어내고 빌드한 EXE는 `No module named 'html'`로 시작하지 못한다(9장).

## 1. 위험도 기준

- ⛔ 고정: 옮기면 규칙이 깨진다. 플랫폼·도구가 루트에서 찾거나, 경로가 배포 EXE 고지·바이트 보존·기능 스위치에 묶여 조용히 깨진다.
- ⚪ 유지 권장: 옮길 수는 있고 실패도 대개 시끄럽지만, 얻는 것이 없다.
- 🔴 높음: 빠뜨린 것이 자동 검사를 통과해 조용히 지나가고, 배포 EXE·사용자 화면·공개 GitLab 화면·보호 시험(빈 통과)에 영향을 준다.
- 🟡 중간: 파일 자체를 고쳐야 한다. 또는 빠뜨린 것이 시험은 통과하고 빌드·release·수동 실행 때에야 시끄럽게 드러난다. 또는 조용하지만 개발자 소스 실행·개발 도구에만 영향이 있다.
- 🟢 낮음: 파일 자체는 그대로다. 같이 바꿀 경로 문자열을 빠뜨리면 시험(quick 또는 full)이 바로 실패하거나, 개발 도구를 실행할 때 즉시 오류가 난다.
- 근거 표시: [실측] 복사본에서 실행해 확인, [판독] 코드나 설치된 라이브러리 소스를 읽어 확인, [추론] 확인하지 못함, [이 PC] 저장소 밖 근거라 다른 PC에서 재현할 수 없음.

## 2. 방식 비교

- B안: `src/` + 경로 추가 (권장)
  - `main.py`·`build_app.py`·`fetch_data.py`를 뺀 52개를 `git mv`로 `src/`에 넣는다. `src/`에는 `__init__.py`를 두지 않는다.
  - 경로를 넣는 곳: `main.py` 맨 위, `tests/conftest.py`, `build.spec`, `build_app.py`, 하네스·진단·실험실 하위 프로세스(4장).
  - 모듈 이름이 그대로라 import·문자열 참조·이름 기반 보호가 그대로 동작한다.
  - [실측] 이동 커밋은 52건 모두 100% rename으로 기록된다.
- A안: `climate_note/` 패키지 (비권장)
  - [판독] import 495문장(116개 파일, 그중 시험 76개 파일)과 모듈 이름 문자열 24곳(monkeypatch 19, `__import__` 4, `-c` 1)을 고쳐야 한다.
  - 이름 기반 보호 3곳이 조용히 꺼진다.
    - `tests/conftest.py:42`의 `__module__.startswith("ui_")` 창 정리. 자기검사 `tests/test_verify.py:337-350`은 가짜 이름 `ui_fixture_probe`(`:344`)를 써서 계속 통과한다.
    - `tests/test_verify.py:126`의 도구 import 부작용 검사(`security`·`database` 미적재).
    - `tests/test_screen_text_lab.py:263·272`의 실험실 앱 모듈 금지.
  - 시험이 실행하지 않는 import가 있다: `main.py:9`(HWP 작업 분기, 시험은 `worker_command`를 가짜로 바꿈 `tests/test_hwp_conversion_runner.py:30`), `main()` 안의 지연 import(`:224·255·278·290-292`). 하나라도 빠뜨리면 HWP 변환 때나 EXE에서만 드러난다.
  - `__init__.py`에 import를 넣으면 두 가지가 깨진다. 작업 프로세스 선분기 계약(AGENTS.md "파일 변환" 항목)이 깨지고, 격리되지 않은 하네스 부모 프로세스가 실제 `%LOCALAPPDATA%`에 폴더·audit.log를 만든다(`security.py:17-18·46`).
- 결론: 목표(루트 줄 수)는 같고, B안이 고칠 곳과 조용한 실패가 훨씬 적다.

## 3. 루트 항목별 분류 (79개)

⛔ 13 + ⚪ 9 + 앱 모듈 52 + 2단계 후보 5 = 79.
개수 확인: `git -c core.quotepath=off ls-files | awk -F/ '{print (NF>1? $1"/" : $1)}' | sort -u | wc -l` → 79. quotepath를 끄지 않으면 `readme/` 아래 한글 파일 이름 때문에 폴더가 하나 더 세어진다.

### 3.1 ⛔ 고정 — 13개

- `README.md`: GitLab 첫 화면에 표시된다. 저장소 상대 참조 25개의 허브다.
- `LICENSE`: GPLv3. `build.spec:37` `('LICENSE', '.')`, `licenses/components.json:13`, 번들 고지 `licenses/THIRD_PARTY_NOTICES.txt:3`("배포 루트 LICENSE"). 시험 `tests/test_packaging.py:174`, `tests/test_ui_licenses.py:59`, `tests/test_verify.py:265·301`.
- `AGENTS.md`: `CLAUDE.md:18`의 `@AGENTS.md`가 같은 폴더 기준이라 함께 루트에 있어야 매 세션 자동으로 읽힌다. Codex 등 다른 도구도 루트의 AGENTS.md를 찾는다(도구 관례).
- `CLAUDE.md`: 대체 위치 `.claude/`는 `.gitignore:39`로 무시돼 저장소에서 빠진다.
- `CONTEXT.md`: 도메인 용어집이다. 설계 문서 링크(`docs/superpowers/specs/2026-10-25-recurring-occurrence-edit-design.md:10`)가 깨진다.
  - [이 PC] Codex 스킬 `C:/Users/GG/.codex/skills/domain-modeling/CONTEXT-FORMAT.md:34·58`이 루트 CONTEXT.md를 전제하고, 없으면 루트에 새로 만든다. 여러 컨텍스트용 `CONTEXT-MAP.md`도 루트에 둔다(`:36`). 그래서 옮기면 용어집이 두 벌로 갈라지거나 루트 줄이 줄지 않는다.
- `.gitignore`: 규칙의 기준이 파일 위치다. 루트 고정 규칙(`/desgn_claude/`)과 모든 깊이 규칙(`output/`·`build/` 등)이 섞여 있다.
- `.gitattributes`: 경로별 `-text` 규칙(`:2` screen_text/models, `:5-20` licenses 원문)의 기준이 파일 위치다.
- `requirements-lock.txt`: 서버 push 검사의 OSV가 이 파일을 읽는다.
  - 근거: `docs/RELEASE_HISTORY.md:318`의 `pillow 12.3.0` 거절. pillow는 `requirements-lock.txt:6·32`에만 있고 `requirements.txt`에는 없다.
  - 하위 폴더에서도 찾는지는 미확인이라, 옮기면 취약점 차단이 조용히 꺼질 수 있다.
  - doctor(`tools/verify.py:136`), `tests/test_packaging.py:100`, 배포 고지 `licenses/APP-NOTICE.txt:17`도 이 이름을 쓴다.
- `build.spec`: `:20` `_SCREEN_TEXT = (_SPEC_DIR / "screen_text").is_dir()`가 spec 위치 기준이다. 옮기고 이 줄을 놓치면 OCR·OCR 고지가 빠진 EXE가 성공으로 빌드되고, `:137`이 `html`까지 제외해 9장 결함과 겹친다. datas도 SPECPATH 기준이다.
- `main.py`: 실행 진입점 계약이다. 다음이 모두 이 위치를 전제한다.
  - `python main.py` 명령, `build.spec:29` `Analysis(['main.py'])`.
  - 작업 프로세스 경로 `resource_root()/"main.py"`(`file_conversion_runner.py:17`, `hwp_conversion_runner.py:17`).
  - 자동 시작 갱신 `main.py:85-91`. B안에서 `src/` 경로를 넣는 기준점이기도 하다.
- `licenses/`: `.gitattributes:5-20`, `licenses/ORIGINS.json`의 SHA-256, `build.spec:36` datas, `components.json`의 `licenses/...` 경로에 묶여 있다.
  - 이 PC는 `core.autocrlf=true`(Git for Windows 시스템 설정)다. 규칙이 빠지면 새 클론에서 줄바꿈이 바뀌어 해시가 어긋난다.
  - [실측] 스크래치 저장소에서 이동 뒤 새로 체크아웃하니 SHA가 `2751a3…`→`4ad3ef…`로 바뀌었다. 이동 직후 이 PC에서는 시험이 통과해서 놓치기 쉽다.
- `screen_text/`: 폴더가 "있는지"가 기능 스위치다(`build.spec:20`). 옮기면 세 가지가 조용히 일어난다.
  - 일반 빌드가 OCR 없는 EXE를 성공으로 만든다.
  - 라이선스 창의 OCR 고지가 빠진다(`ui_licenses.py:18`).
  - 시험은 조건부로 건너뛴다(`tests/test_ui_licenses.py:38·50·64`). `.gitattributes:2`도 경로 고정이다.
- `docs/`: 배포된 v4.5 EXE의 번들 고지가 `docs/RELEASE_HISTORY.md`·`docs/UNIT_CONVERSION.md`·`docs/MONEY_NOTATION.md` 경로를 글자로 담고 있다(`licenses/THIRD_PARTY_NOTICES.txt:20`, `licenses/DATA-SOURCES.txt:17·29`). `git diff --stat v4.5 HEAD -- licenses/`는 출력이 없다. 다른 문서를 받는 목적지로만 쓴다.

### 3.2 ⚪ 유지 권장 — 9개

- `requirements.txt`: 관례 위치, `tests/test_packaging.py:92`, 문서 명령. 옮기면 🟡.
- `pytest.ini`: rootdir 기준, doctor 필수 파일(`tools/verify.py:151`). 옮기면 🟡.
- `build.bat`: `%~dp0` 기준으로 `.venv`와 `build_app.py`를 찾는다(`build.bat:4·8`). 옮기면 🟡.
- `build_app.py`: 자기 폴더로 chdir하고(`:88-89`) 그 폴더의 doctor·spec을 쓴다(`:101·113`). `build.spec:11`이 import한다. 옮기면 🟡이고, 시험 연쇄 실패도 생긴다.
  - `tests/test_build_app.py:47`이 실제 `build()`를 불러 pytest 프로세스의 cwd를 바꾼다.
  - 그래서 cwd 기준 시험(`tests/test_ui.py:741`, `tests/test_file_conversion_runner.py:151`)이 실행 순서에 따라 실패한다.
- `fetch_data.py`: 앱이 import하지 않는 개발 도구다. `ROOT = 자기 폴더`(`:29`)가 `.env`(`:40`)·백업 `output/holiday-refresh`(`:355`)·`HOLIDAYS_PATH`(`:232`)의 기준이다. 옮기면 🟡:
  - 루트 `.env`를 못 읽어 "LUNAR_API_KEY가 없습니다"가 나서 원인을 오해하기 쉽다.
  - 백업은 `.gitignore`의 `output/`(모든 깊이)에 묻힌다.
  - 시험은 기본 경로를 tmp로 바꿔 못 잡는다.
- `.env.example`: `.env`를 루트에 두라는 안내(`:4`)와 짝이다. 옮기면 🟢.
- `resources/`, `tests/`, `tools/`: 다른 항목의 목적지이거나 하네스 기준점이다.

### 3.3 앱 모듈 52개 (B안: `src/`로 이동)

#### 🟡 5개 — 같이 고칠 곳이 있다

- `app_paths.py`: `:16` `_SOURCE_ROOT = Path(__file__).resolve().parent` → `parents[1]`(소스 분기만, frozen 분기 `:25-26`은 그대로). 리소스·고지·OCR 모델·작업 프로세스 `main.py` 경로가 모두 이 한 줄로 정해진다. [실측] 빠뜨리면 quick의 `tests/test_app_paths.py`가 바로 실패하고, 연쇄로 OCR·라이선스·파일 변환 시험도 실패한다.
- `ui_settings.py`: `:82` 소스 실행 자동 시작 명령 → `Path(__file__).parent.parent / "main.py"`.
  - [실측] 빠뜨려도 시험이 모두 통과한다(시험 없음). 레지스트리에 없는 `src\main.py`가 기록된다.
  - 다음 수동 실행 때 `main.py:89`가 고쳐 쓴다. EXE는 frozen 분기(`:80-81`)라 영향이 없다. 개발자 소스 실행만 해당한다.
- `app_info.py`:
  - import 지점은 pytest가 못 잡는다: `build.spec:10`, `build_app.py:7`, 이를 거치는 `tools/verify.py:368`. 시험이 먼저 import해 sys.modules에 올려 두기 때문이다(`tests/test_packaging.py:11·17`). [실측] 실제 빌드에서 시끄럽게 실패한다.
  - 경로 문자열은 시험이 잡는다: doctor `tools/verify.py:152`는 full의 `tests/test_build_app.py:47`이, runpy `:364·537`은 quick의 `tests/test_verify.py`가 잡는다.
  - 주의: 이 파일만 루트에 남기는 변형은 🔴가 된다(4장 F3).
- `holidays.py`:
  - 파일 이동 자체는 시험이 잡는다(`tests/test_verify.py:508`, doctor).
  - 기본 경로 `fetch_data.py:232`와 `tools/verify.py:449`는 [실측] 시험이 못 잡는다. release·수동 갱신 때 "기존 holidays.py를 읽을 수 없습니다"로 시끄럽게 멈춘다. 읽기가 쓰기보다 먼저라 조용한 덮어쓰기는 없다(`fetch_data.py:362·420`).
  - 시험의 가짜 루트(`tests/test_verify.py:493·540`)도 `src/` 배치로 바꿔야 한다.
- `optional_mini_apps.py`: 걷어내기 절차(`docs/SCREEN_TEXT.md:62-68`)와 보호 시험 예외 경로(`tests/test_screen_text_ui.py:572`)에 이름이 묶여 있다. 보호 시험 자체의 위험은 5장 X-1(🔴)이다.

#### 🟢 47개 — 파일은 그대로 옮긴다

- 다른 곳의 경로 문자열만 바꾸는 7개:
  - `database.py`, `security.py`: doctor 목록(`tools/verify.py:151-152`). 빠뜨리면 full의 `tests/test_build_app.py:47`이 잡는다.
  - `hwp_conversion.py`: `tests/test_ui_licenses.py:44`가 경로로 읽는다(한컴 고지 문구, full).
  - `app_fonts.py`, `fluent_icons.py`, `ui_focus.py`: `tests/test_app_paths.py:117-118`이 경로로 읽는다(quick).
  - `ui_main.py`: `diagnostics/calendar_columns_probe.py:137`이 경로로 해시한다(시험 없음, 진단을 실행할 때 즉시 오류).
- 그대로 옮기면 끝인 40개(모두 `.py`):
  - 계산·변환·데이터: `date_time_calculator`, `file_conversion`, `file_conversion_runner`, `file_conversion_worker`, `holiday_notice`, `hwp_conversion_runner`, `hwp_conversion_worker`, `money_notation`, `popup_border_fix`, `schedule_rules`, `screen_placement`, `show_desktop_guard`, `sticky_file_links`, `unit_converter`
  - 화면: `ui_calendar_spans`, `ui_conversion_conditions`, `ui_converter_combo`, `ui_date_time_calculator`, `ui_dday`, `ui_dday_panel`, `ui_document_converter`, `ui_first_run`, `ui_focus_panel`, `ui_licenses`, `ui_mini_app_frame`, `ui_mini_apps`, `ui_money_notation`, `ui_schedule_alarm`, `ui_schedule_emoji`, `ui_schedule_options`, `ui_search`, `ui_sticky`, `ui_sticky_link_labels`, `ui_sticky_links`, `ui_sticky_panel`, `ui_text`, `ui_trash`, `ui_unit_converter`, `ui_update`, `ui_window_card`
  - [판독] 52개 중 `__file__`을 쓰는 곳은 `app_paths.py:16`과 `ui_settings.py:82`뿐이다. 나머지 리소스 경로는 모두 `resource_root()` 기준이고, cwd 기준 경로(`os.getcwd`·`Path.cwd`)는 0건이다.
  - 작업 프로세스 2개(`file_conversion_worker`, `hwp_conversion_worker`)는 `main.py`의 경로 삽입 위치(F1)만 지키면 된다.

### 3.4 2단계 후보 — 5개

- `diagnostics/` → `tools/diagnostics/` 🟡
  - 두 스크립트가 `parents[1]`을 저장소 루트로 쓴다(`build_font_probe.py:8`, `calendar_columns_probe.py:24`) → `parents[2]`로 바꾼다.
  - `build_font_probe.py:9`의 `"diagnostics"` 경로와 `:23`의 아이콘 경로도 고친다. `README_detail.md:203` 표도 고친다.
  - 시험이 없다. 대부분 실행할 때 즉시 오류가 나지만, 실행 기록은 `tools/output/`에 조용히 생긴다(`.gitignore`에 묻힘).
- `README_detail.md` → `docs/` 🔴 (링크 검사 시험을 먼저 두면 🟡)
  - 다음 링크가 공개 화면에서 조용히 깨진다(링크 시험 없음):
    - `README.md`의 링크 4개(`:12·62·63·79`, `:12`는 "상세 안내" 버튼)
    - 이 파일 안 상대 링크 34개(`readme/`를 함께 옮기면 28개)
  - 시끄럽게 실패하는 것은 `tests/test_ui_licenses.py:44` 하나다.
  - `docs/SCREEN_TEXT.md:66` 문구와 과거 기록 5곳의 링크도 낡는다.
  - GitLab Release 설명·온나라 게시물이 이 파일을 main 기준 URL로 걸었는지 미확인이다.
- `readme/` → `docs/readme/` 🔴 (같은 조건으로 🟡)
  - GitLab 첫 화면의 그림 11개(`README.md`)와 `README_detail.md`의 그림 6개가 조용히 깨진다.
  - 오래된 `app.png`·슬라이드 PNG를 외부에서 원시 URL로 걸었는지 미확인이다.
- `fonts/` → `resources/fonts/` 🟡, 유지 권장
  - `tests/test_app_paths.py:45·53-57·98-104`가 코드 경로와 build.spec datas를 함께 검사한다. 얻는 것은 1줄뿐이다.
- `icon/` → `resources/icon/` 🔴, 유지 권장
  - `main.py:122`를 놓치면 트레이 아이콘이 파란 사각형으로 조용히 바뀐다(`main.py:123-128`).
  - `_make_tray_icon`을 실행하는 시험이 없다. `tests/test_app_paths.py:60-62`는 같은 경로를 따로 적은 문자열만 본다.
  - 함께 바뀔 곳: `build.spec:33·166`, `tools/generate_app_icons.py:56·90`, `diagnostics/build_font_probe.py:23`, `tests/test_app_paths.py:62·84-85·103-104`, `AGENTS.md`·`docs/ARCHITECTURE.md:88-89`의 아이콘 서술.

### 3.5 A안이면 바뀌는 등급

- 앱 모듈 52개 모두 최소 🟡(import 재작성).
- 🔴로 오르는 것:
  - `hwp_conversion_worker.py`: `main.py:9` 분기를 시험하지 않는다.
  - `main.py`의 지연 import 6곳: release smoke만 잡는다.
  - `ui_*` 전체: conftest 창 정리가 조용히 꺼진다.
  - `security.py`·`database.py`: 도구 import 보호가 조용히 꺼진다.

## 4. B안 수정 목록 (실측으로 확정)

[실측] 아래 F1~F12를 복사본에 적용한 패치는 20개 파일 +63/−29줄이다(`output/root-cleanup-risk-20261031/b-plan-fixes.patch`, 이동 커밋 다음에 적용). 이 상태에서 시험 결과가 원본과 같았다.

### 필수 수정

- F1 `main.py` 2줄(`import sys`) 바로 다음, 작업 프로세스 분기(`:3`)보다 앞에 넣는다.

  ```python
  if not getattr(sys, "frozen", False):
      import os
      sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
  ```

  - [실측] 블록이 없거나 분기 뒤에 있으면 파일 변환 시험 4개가 실패한다. HWP 분기는 시험이 가짜로 바꿔서 못 잡는다.
  - [실측] 상대 경로 `"src"`로 넣으면 시험이 모두 통과한다(cwd=루트). 그러나 저장소 밖 cwd에서는 작업 분기가 종료 코드 1(ModuleNotFoundError)로 실패한다. 반드시 `__file__` 기준 절대 경로로 넣는다.
  - [실측] EXE에서도 진입 스크립트 `__file__`은 정의된다(`_MEIPASS\main.py`, 디스크에는 없음). frozen에서는 건너뛴다.
- F2 `tests/conftest.py`: `import security`(현재 `:25`) 앞에 `_PROJECT_ROOT / "src"`를 넣는다.
  - [실측] 없으면 `tests/test_verify.py::test_test_bootstrap_honors_run_path_before_app_import`가 실패한다.
  - `pytest.ini`의 `pythonpath = src`는 선택이다. [실측] 이것만 빼도 결과 차이가 없다. pytest 9.0.3은 이 값을 conftest보다 먼저 적용한다.
- F3 `build.spec`: `:10`의 `from app_info import`보다 앞에서 `sys.path.insert(0, str(_SPEC_DIR / "src"))`를 넣는다. 넣은 뒤 빼지 않는다.
  - [실측] 이 한 줄만으로 EXE 모듈이 원본과 같다(V2). `pathex` 추가는 선택이다. 넣는다면 절대 경로로 쓴다. 상대 경로 pathex는 PyInstaller를 실행한 cwd 기준이라 다른 cwd에서 조용히 빠진다.
  - [실측] `app_info.py`까지 옮긴 상태에서 이 줄을 빠뜨리면 `build.spec:10`에서 1초 만에 빌드가 실패한다(V5, 시끄러움).
  - [실측] 🔴 변형: `app_info.py`를 루트에 남기고 이 줄을 빠뜨리면 빌드는 "성공"한다(종료 0, 출력도 원본과 구별되지 않음). EXE에는 앱 모듈이 52개 중 1개만 들어가고, 실행하면 "No module named 'app_fonts'" 오류 창을 띄운 채 대기한다(V1·V1b). release smoke는 60초 시간 초과(`tools/smoke_release.py:541-542`)로만 잡고, 일반 빌드는 못 잡는다. 그래서 `app_info.py`는 다른 앱 모듈과 함께 `src/`로 옮긴다.
- F4 `build_app.py`: `:7`의 `from app_info import` 앞에 `src`를 넣는다(이미 있으면 넣지 않는다).
  - [실측] 빠뜨리면 pytest는 통과하고, 실제 빌드가 `build_app.py:7`에서 실패한다.
  - "없을 때만 넣기"는 `tools/verify.py:366-371`의 `insert(0)`·`pop(0)` 짝이 엉키지 않게 하려는 것이다.
- F5 `src/app_paths.py:16` → `parents[1]`. 실제 이동 때는 `.parent.parent`를 권장한다.
  - 이 줄은 모듈 수준이라 EXE에서도 import 때 실행된다(값은 frozen에서 쓰지 않음). `parents[1]`은 경로 깊이가 얕으면 IndexError를 내지만 `.parent.parent`는 예외가 없다.
  - 현재 `build.spec:159`는 `runtime_tmpdir=None`이라 `_MEIPASS`가 임시 폴더 아래여서 실제로는 둘 다 안전하다[판독].
- F6 `src/ui_settings.py:82` → `Path(__file__).parent.parent / "main.py"`. [실측] `main.py:89`가 만드는 문자열과 같다.
- F7 `tools/verify.py`: doctor 목록(`:151-152`), runpy 경로(`:364·537`), `:366` 경로, 공휴일 경로(`:449`)를 `src` 기준으로 바꾼다.
  - 앱 소스 폴더는 상대 상수(`"src"`)로 두고 호출할 때 `ROOT`와 합친다.
  - 모듈 수준 절대 상수로 만들면 `verify.ROOT`를 바꿔 끼우는 시험(`tests/test_verify.py:494`)이 실제 `src/holidays.py`를 읽게 된다[추론].
- F8 `fetch_data.py:232` `HOLIDAYS_PATH = ROOT / "src" / "holidays.py"`.
- F9 시험 경로: `tests/test_app_paths.py:117`(src 아래 파일), `tests/test_ui_licenses.py:44`(`src/hwp_conversion.py`), `tests/test_verify.py:493·508·540`(가짜 루트에 `src/holidays.py`). [실측] `:493·540`을 빠뜨리면 3개가 실패한다.
- F10 걷어내기 보호 시험 `tests/test_screen_text_ui.py:566-577`(5장 X-1):
  - 후보를 `git ls-files "*.py"`로 만든다.
  - 예외를 `src/optional_mini_apps.py`·`tests/test_screen_text_*`·`screen_text/`·`tools/screen_text_lab/`로 둔다.
  - 등록부가 실제로 정규식에 걸리는지 단언한다. "훑은 파일 수 > 0"은 이동 뒤에도 87개라 쓸모가 없다.
  - [실측] `screen_text/`·`tools/screen_text_lab/` 예외가 없으면 정상 import 15곳이 위반으로 잡혀 실패한다.
- F11 하위 프로세스·스크립트에 `src`를 더한다:
  - `tools/smoke_release.py:272`: 기존 ROOT 삽입은 유지하고 src를 더한다. [실측] ROOT를 빼면 `:371`의 `import main`이 실패한다.
  - `tests/shortcut_dialog_probe.py:10`
  - `diagnostics/calendar_columns_probe.py:31`(+ `:137` 경로)
- F12 화면 글자 실험실(개발 도구): `screen_text/__init__.py:2-3`이 `app_paths`·`ui_mini_apps`를 import하므로, `screen_text`를 import하는 모든 실험실 프로세스에 `src`가 필요하다. [실측] 시험은 이 중 어느 것도 잡지 않는다.
  - 해당하는 곳:
    - 작업 프로세스 5곳: `runner.py:257-258`, `crop_evaluation.py:231-232`, `full_candidate.py:212-213`, `warning_rule_run.py:114-115`, `disagreement_benchmark.py:165-166`
    - 부모 프로세스 import: `full_candidate.py:175`, `crop_evaluation.py:197`
    - `python -m tools.screen_text_lab.<모듈>` 직접 실행(`docs/SCREEN_TEXT_LAB.md:314·320`)
  - 권장: `tools/screen_text_lab/__init__.py` 한 곳에서 넣는다. 앱 모듈을 import하지 않으므로 `tests/test_verify.py:123`·`tests/test_screen_text_lab.py:258` 보호와 부딪치지 않는다. [판독, 미실측] 실측 패치는 작업 프로세스 env에 PYTHONPATH를 넣는 방식이었다.
  - 출처 기록 `runner.py:18`·`crop_evaluation.py:106`의 `"app_paths.py"` → `"src/app_paths.py"`. [실측] runner는 빠뜨리면 조용히 None을 기록한다.
- F13 문서: 모듈 이름은 그대로라 위치 서술만 고친다.
  - 대상: `docs/ARCHITECTURE.md` 모듈 지도(`:98-142`)·`:84`·`:105`·`:165`, `README_detail.md:181-203` 구조 표, `AGENTS.md` 명령·원칙(src 규칙), `docs/TESTING.md`, `docs/SCREEN_TEXT.md:64`.
  - `docs/ARCHITECTURE.md:165`의 "`_MEIPASS/<이름>.pyc`"는 실측으로 `.py`다(기존 서술 오류, 결론은 같음).

### 권장 보호 (이동과 함께 추가)

- G1 `src.` 접두 import 금지 시험. 대상에 `.py`뿐 아니라 `build.spec`도 넣는다.
  - [실측] `import src.database`는 `database`와 다른 모듈 객체가 된다.
  - [판독] `build.spec`·`build_app.py`를 `from src.app_info import`로 "고치면" 시험·doctor는 통과한다. 하지만 `src`가 검색 경로에 없어 V1과 같은 불량 EXE가 된다.
- G2 루트 `*.py` 허용 목록 시험(`main.py`·`build_app.py`·`fetch_data.py`, 미추적 파일 포함).
  - [판독] PyInstaller는 진입 스크립트 폴더(루트)를 `src`보다 먼저 찾는다(`.venv/Lib/site-packages/PyInstaller/building/build_main.py:628-633·685`). 소스 실행·pytest는 `src`를 먼저 찾는다.
  - 그래서 루트에 같은 이름 사본이 생기면 EXE만 사본을 쓴다.
- G3 release에 "`git ls-files src/*.py`의 모듈 이름이 모두 EXE PYZ에 있는가" 검사를 넣는다.
  - [실측] warn 파일에는 누락 51개 중 11개만 보이므로, warn 파싱보다 이 검사가 직접적이다.
  - 가능하면 직전 빌드와 PYZ 코드 객체를 비교한다. PyInstaller 6.19는 `co_filename`을 모듈 이름 기준으로 바꿔 위치가 남지 않는다(`PyInstaller/building/utils.py:694`).
- G4 `tests/test_app_paths.py:117`의 `__file__` 금지 검사를 `src/*.py` 전체로 넓힌다. 소스 `src/x.py`와 EXE `_MEIPASS/x.py`의 깊이가 달라, `__file__`로 경로를 만드는 코드는 EXE에서만 깨진다.
- G5 `HOLIDAYS_PATH == Path(holidays.__file__)`, `_get_startup_cmd()`가 루트 `main.py`를 가리키는지 단언하는 시험.
- G6 2단계 전: README·README_detail의 상대 링크·그림 존재 검사 시험.

## 5. 공통 위험

- X-1 🔴 걷어내기 계약 보호 시험의 빈 통과
  - `tests/test_screen_text_ui.py:568`은 루트 `*.py`·`tests/*.py`·`tools/*.py`만 훑는다.
  - [실측] 이동 뒤 `src/ui_text.py`에 `import screen_text`를 넣어도 통과한다. 원본에서는 같은 위반을 잡는다. 대응: F10.
- X-2 🔴 빌드가 `src/`를 못 보는 변형: F3의 🔴 변형, G1·G2.
- X-3 🟡 `src.` 접두 import의 이중 모듈: G1.
- X-4 🟡 `__file__` 깊이 차이: G4.
- X-5 🔴 `.gitattributes` 경로 규칙: `licenses/`·`screen_text/models`를 옮기면 새 클론에서 바이트가 바뀐다. 두 폴더를 고정한다(3.1).
- X-6 🟡 `.gitignore`의 모든 깊이 규칙(`security/`·`build/`·`dist/`·`output/`·`backups/`·`.env`)
  - `src/` 안에 이런 이름의 하위 폴더를 만들면 조용히 추적에서 빠진다.
  - [실측] 계획한 경로(`src/*.py` 등)는 무시되지 않는다(`git check-ignore`).
- X-7 🟡 검증 범위: `quick`·`data`(`tools/verify.py:31-44`)에는 `test_packaging`·`test_build_app`·`test_ui_licenses`·`test_screen_text_ui`·`test_security_scan_rules`가 없다. `full`과 `release`가 필수다.
- X-8 외부 링크(미확인): 저장소·앱 코드·배포 EXE에는 파일 단위 GitLab URL(`/-/blob/`·`/-/raw/`)이 없다. 외부 게시물은 확인하지 못했다.
- X-9 서버 push 검사(미확인): 대량 이동이 "새 지적"으로 보일지, OSV가 하위 폴더 lock을 찾는지 모른다. push 전에 로컬 검사를 다시 돌린다.
- X-10 이력: 순수 이동 커밋(`git mv`, 100% rename) → 수정 커밋 두 단계로 나눈다. GitLab 파일 이력 화면이 rename을 따라가는지는 미확인이다.

## 6. 실측 결과

모두 저장소를 `git archive HEAD`로 푼 복사본에서 했다. 실제 저장소·사용자 데이터·레지스트리는 건드리지 않았다. 하네스(`tools/verify.py`) 실행이 아니라 pytest·PyInstaller를 직접 실행했다.

### 6.1 시험 (offscreen)

- 환경: `.venv` Python 3.13.5, PySide6 6.11.2, pytest 9.0.3, `QT_QPA_PLATFORM=offscreen`, 파일 단위 실행. 원본 복사본과 같은 조건으로 비교했다.
- 원본 vs B안 전체 수정: 3,110개를 비교했고 결과가 다른 시험은 0개다.
  - offscreen에서는 원래 67개(17개 파일)가 실패하며, 양쪽 메시지가 같다.
  - `test_screen_text_lab_datasets.py` 22개는 offscreen에서 중단돼 일반 화면 플랫폼으로 비교했다(22/22 같음).
- 빠뜨림 실험(B안 전체 수정에서 하나씩 되돌림):

| 빠뜨린 것 | 결과 | 자동 검출 |
|---|---|---|
| `app_paths.py:16` | quick `test_app_paths` 등 다수 실패 | 잡힘 |
| `ui_settings.py:82` | 모두 통과 | 못 잡음(소스 실행 자동 시작만) |
| `fetch_data.py:232` | 모두 통과 | 못 잡음(release·수동 갱신 때 오류) |
| F4 `build_app.py` | pytest 통과, 실제 빌드 실패 | 빌드 때 |
| F3 `build.spec` 전체 | pytest 통과, 실제 빌드 실패 | 빌드 때 |
| F1 없음·분기 뒤 | 파일 변환 시험 4개 실패 | 잡힘(HWP는 못 잡음) |
| F1 상대 경로 | 모두 통과 | 못 잡음(저장소 밖 cwd에서 실패) |
| F2 conftest | 1개 실패 | 잡힘 |
| `pytest.ini` pythonpath | 차이 없음 | 불필요 |
| F11 smoke의 ROOT를 src로 바꿔 끼움 | 2개 실패 | 잡힘 |
| F12 출처 기록 | 모두 통과, runner 기록 None | 못 잡음 |
| F7 verify 경로 | 8개 실패 | 잡힘 |
| F10 보호 시험 그대로 | 위반을 넣어도 통과 | 빈 통과 |
| F10 하위 폴더 예외 없음 | 정상 import 15곳 오탐 실패 | 잡힘 |

### 6.2 빌드·EXE (PowerShell, PyInstaller 6.19.0)

- V0 원본: EXE 94,308,767 bytes, PYZ 모듈 541개. 이름 집합이 배포된 `dist/기후노트_v4.5.exe`와 같다.
- V3 B안 빌드 경로 수정(이동 + F1·F3·F4·doctor 목록, F5·F6 제외, 일반 빌드 경로 `python build_app.py`):
  - F5·F6을 넣은 EXE는 빌드하지 않았다. 넣으면 `app_paths`·`ui_settings`의 코드 객체만 달라진다. `app_paths.resource_root()`는 frozen이면 `_MEIPASS`를 돌려주고 `_SOURCE_ROOT`는 쓰지 않는다. `ui_settings._get_startup_cmd()`는 frozen 분기에서 먼저 반환한다[판독, `app_paths.py:16·25-27`, `ui_settings.py:80-82`].
  - doctor를 통과했다. PYZ 541개의 이름·코드 객체가 V0과 같다(차이는 진입 스크립트의 B안 4줄뿐).
  - 격리 실행에서 최초 설정 → 본 창이 떴고 error.log는 0바이트다.
  - 저장소 smoke 5개 시나리오(fresh·existing·blocked·upgrade·upgrade_v18)를 통과했다. 단, smoke는 원본 복사본의 하네스로 돌렸다. B안 배치의 자체 release에는 F7·F11이 필요하다.
- V2 `build.spec` sys.path 한 줄만: V0과 같은 산출물(pathex 불필요).
- V1·V1b `app_info.py` 루트 유지 + `build.spec` 무수정:
  - 빌드는 성공으로 보고된다. PYZ는 482개이고 앱 모듈은 52개 중 1개뿐이다.
  - 실행하면 "No module named 'app_fonts'" 오류 창이 뜬다. smoke는 60초 시간 초과로 실패한다.
- V5 F3 누락: `build.spec:10`에서 빌드 실패. V6 F4 누락: `build_app.py:7`에서 실패.
- V4 원본에서 `screen_text/` 걷어냄: 9장.

## 7. 데이터 안전 결론

- 사용자 데이터에는 영향이 없다. 4개 관점 조사와 2회의 반박 검토가 모두 반증에 실패했고, 실측도 같았다.
  - 데이터 폴더: `security.py:17` `APP_DIR = LOCALAPPDATA\MyDesktopCalendar`. DB `database.py:26`, 백업 `:232`, 단일 실행 잠금 `main.py:224-225`.
  - 암호화 키: MachineGuid + 사용자 이름(`security.py:55-75`) + 데이터 폴더의 salt(`:96-101`) → `derive_key`(`:154-158`). 코드 위치가 들어가지 않는다.
  - pickle·shelve·QSettings·모듈/클래스 이름 저장은 0건이고, 로거 이름은 `'app_error'`·`'audit'`로 고정이다.
  - [실측] 작업 프로세스 분기는 저장소 밖 cwd에서도 LOCALAPPDATA에 아무것도 만들지 않는다. B안 EXE는 smoke의 기존 데이터·업그레이드 시나리오를 통과했다.
- 예외는 A안뿐이다. `__init__.py`에 import를 넣으면 하네스 부모 프로세스가 실제 AppData에 폴더·audit.log를 만든다. 데이터 손실은 아니지만 `AGENTS.md`의 "실사용 AppData 금지"를 어긴다.

## 8. 옮길 때 검증 계획

원칙: 이동 따로, 기능 따로. 이동은 v4.6 기능 개발보다 먼저 기능 변경 0·DB 버전 그대로(v19)인 단계로 끝낸다. 이 단계의 EXE가 v4.5와 같은 프로그램임을 확인한 뒤에 기능을 얹어, 이후 문제의 원인이 이동인지 기능인지 갈리게 한다. DB 버전이 그대로이므로 이 단계 EXE와 v4.5 EXE는 같은 데이터를 서로 바꿔 써도 된다.

1. 브랜치에서 `git mv`만 담은 커밋 → F1~F13·G1~G5 커밋. 이 단계에는 기능 변경을 섞지 않는다.
2. `tools/verify.py full` (quick·data로는 부족, X-7).
3. PowerShell `tools/verify.py release` (EXE 빌드·격리 실행 5개).
4. G3: 새 EXE의 PYZ에 `src/` 모듈이 모두 있는지 확인하고, 배포된 `dist/기후노트_v4.5.exe`와 코드 객체를 대조한다. 예상 차이는 `app_paths`·`ui_settings` 2개(F5·F6)와 진입 스크립트뿐이다. 그 밖의 차이가 있으면 원인을 밝히기 전에 기능 개발로 넘어가지 않는다.
5. 별도 폴더에 새로 clone해서 `full`을 한 번 더 돌린다(`.gitattributes`·줄바꿈).
6. 수동: 소스 실행 자동 시작 토글 → 레지스트리 값, HWP 변환 1회, 실험실 명령 1회, push 뒤 GitLab 첫 화면.
7. 이동 단계 EXE는 따로 배포하지 않아도 된다. 그 위에서 v4.6 기능을 개발하고, 데이터 변경이 있으면 기존 규칙(열 추가만·마이그레이션 전 보호본·구 EXE 차단·왕복 시험)을 따른다.

## 9. 부수 발견: 걷어내기 빌드의 `html` 결함 (이동과 무관)

- [실측] `docs/SCREEN_TEXT.md` 걷어내기 절차대로 `screen_text/`를 지우고 빌드한 EXE는 시작하지 못한다.
  - 원인: `build.spec:137`이 screen_text가 없으면 표준 라이브러리 `html`을 제외한다. 그런데 `ui_text.py:2`가 `from html import escape`를 쓰고, `ui_main.py:6`이 ui_text를 import한다.
  - 빌드는 성공한다(warn: `excluded module named html - imported by ui_text`).
  - 실행하면 `main.py:278 → ui_main.py:6 → ui_text.py:2`에서 `ModuleNotFoundError: No module named 'html'` 오류 창이 뜬다. 새 설치에서는 최초 설정을 마치고 DB·salt·백업을 만든 뒤에 실패한다.
  - 이력: html 제외는 첫 커밋 `5d32105`(2026-08-18)부터 있었고, `ffdbd0f`(2026-10-09)에서 조건부가 됐다. `ui_text.py`는 `73149ce`(2026-10-27)에서 추가됐다. v4.5부터 잠재한다.
  - 영향 범위: 현재 배포 EXE(screen_text 포함)는 영향이 없다. OCR을 걷어낸 배포가 필요할 때 드러난다.
  - `tests/test_packaging.py:254`가 이 구성(`"html" in absent["excludes"]`)을 기대값으로 고정하고 있다. 걷어내기 절차(`docs/SCREEN_TEXT.md:68`)에는 EXE 실행 확인이 없다.
- 고칠 방향(별도 작업): html을 항상 포함하거나 ui_text의 html 의존을 없앤다. `tests/test_packaging.py:254` 기대값과 걷어내기 절차의 EXE 실행 확인도 함께 고친다.

## 10. 미확인·결정 필요

- 사용자 결정:
  - B안 진행 여부와 시점.
  - 2단계(문서·그림·진단) 진행 여부. 외부 링크를 확인한 뒤 정한다.
  - 9장 결함 수정 여부.
  - 과거 기록(docs/work·superpowers)의 깨질 링크(README_detail 5, CONTEXT 1, .py 4)를 고칠지.
- 외부 확인:
  - GitLab Release 설명·온나라 게시물·공모전 자료가 main 기준 URL로 거는지(X-8).
  - 서버 push 검사가 이동을 어떻게 처리하는지, OSV가 하위 폴더를 찾는지(X-9).
  - GitLab 파일 이력이 rename을 따라가는지, `docs/` 폴더 화면에서 `README_detail.md`가 폴더 README로 렌더되는지.
- 이번 실측 밖:
  - 실제 화면 플랫폼에서의 시험 비교(offscreen에서 원래 실패하던 67개).
  - F12의 `__init__.py` 방식.
  - G1~G6 보호 시험 자체.
  - 다른 PC의 `core.autocrlf`.
  - 실제 `tools/verify.py release` 실행.
  - F5·F6까지 넣은 EXE의 빌드·smoke·v4.5 대조(예상 차이: `app_paths`·`ui_settings` 2개).

## 11. 다른 모델이 검증하는 법

- 근거 자료는 이 PC의 `output/root-cleanup-risk-20261031/`에 있다(`output/`은 git 무시 대상).
  - `b-plan-fixes.patch`: 이동 커밋 뒤 적용한 F1~F12 수정. 문서는 `docs/SCREEN_TEXT.md` 한 줄만 들어 있다.
  - `test-trial/`: 시험 실측 스크립트(`apply_naive.py`, `apply_fixed.py`, `apply_extra.py`, `run_files.sh`, `junit_cmp.py`, `omit_variants.py`, `p4_count.py`), 로그(`logs/cmp_full.txt` 등), 탐침 결과.
  - `build-trial/`: 빌드 실측 스크립트(`apply_variant.py`, `build_variant.ps1`, `toc_compare.py`, `exe_content_compare.py`, `run_exe.py`), 로그, EXE 실행 결과(`runs/*.result.json`), smoke 결과(`v*smoke.smoke.json`).
  - `analysis/`: 초안, 1차 조사 원자료(111건), 반박 검토 2개, 실측 보고 2개, 집계 스크립트.
- 재현 명령:
  - 루트 항목 수: 3장 명령 → 79. 루트 파일 수: `git ls-files | grep -vc /` → 69.
  - A안 import 수: `.\.venv\Scripts\python.exe -I output/root-cleanup-risk-20261031/analysis/scripts/rev_count_imports.py . output/root-cleanup-risk-20261031/analysis/scripts/mods52.txt` → 495문장, 116개 파일, 시험 76개 파일.
  - 시험 실측:
    1. `git archive --format=tar HEAD | tar -x -C <폴더>`로 복사본을 만들고 `git init`·커밋한다.
    2. 52개를 `git mv`로 옮기고 패치를 적용한다.
    3. 원본·이동본에서 같은 조건으로 pytest를 돌리고 junit을 비교한다.
  - 빌드 실측: `build-trial/scripts/build_variant.ps1`을 PowerShell에서 실행한다(Git Bash는 mingw DLL이 섞인다).
- [이 PC] 표시 근거: Codex 스킬 파일(3.1 CONTEXT.md), `stash@{0}`, 스크래치 저장소의 줄바꿈 재현(3.1 licenses/), `output/` 근거 자료.

## 검증 증거

| 명령/범위 | 상태 | 결과 경로 | 유의사항 |
|---|---|---|---|
| 4개 관점 정적 조사(발견 111건) | 완료 | `output/root-cleanup-risk-20261031/analysis/wf1_dump.md` | 읽기 전용 |
| 반박 검토 2개(근거 대조·과소평가) | 완료 | `analysis/wf2_refute-*.md` | 초안 v1 대비 수정 반영 |
| 복사본 pytest 비교(3,110개) | 차이 0 | `test-trial/logs/cmp_full.txt` | offscreen, 하네스 아님 |
| 복사본 빌드 V0~V6, EXE 실행, smoke | 완료 | `build-trial/logs/`, `build-trial/runs/` | 하네스 아님, release 미실행 |
| `tools/verify.py` quick/full/release | 미실행 | — | 실제 이동 때 실행 |

## 미해결과 인계

- 남은 문제: 10장.
- 변경한 정본 문서: 없음.
- 다음 행동: 다른 모델 검증 → B안 진행 여부 결정 → 진행하면 8장 순서대로.
- 배포·커밋·push: 수행하지 않음.
