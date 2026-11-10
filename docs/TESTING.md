# Testing & Security Audit Reference

## v4.6 추가 검증 계약 (공휴일 테마)

- 테스트 파일: 판정 `test_holiday_theme.py`(실제 `holidays.py`와 합성 표, 설계 테스트 벡터 전부), 장식 정의 `test_holiday_decor.py`(순수: keyframes 끝값·위상·13키 표·참조 SVG 존재/고아 없음·Tiny 금지어·viewBox), 화면 `test_ui_holiday_theme_calendar.py`(머리줄·오늘 칸·공휴일 칸·인사말·자정/트레이/가져오기/초기화 재판정)·`test_ui_holiday_theme_widgets.py`(D-Day·스티키 표시 전용 색)·`test_ui_holiday_theme_focus.py`(바탕·모자 13종×배율 1.0/1.25/1.5)·`test_ui_holiday_decor.py`(레이어·기준점·장애물 비겹침·움직임 가입/정지 조건·스티커·중간/크게 빈 곳 재배치(삼일절 깃발 6개·개천절 구름·추석 억새·어린이날 풍선·연등 9개·추석 보름달)와 세 크기 모든 조각 그려짐(기본 크기는 작은 배치, 조각마다 불투명 픽셀 확인)·캐시 상한), 설정 `test_ui_settings_holiday_theme.py`(행 36/40px·800×560 무압축·`QT_SCALE_FACTOR` 1.25/1.5 하위 프로세스), 스위치 키의 Export/Import 왕복은 `test_database.py`다. quick·data에는 이 파일들이 없으므로 관련 변경은 `quick --tests <파일>`, 여러 화면 모듈을 건드리면 `full`로 확인한다.
- **날짜 독립(`app_dir`)**: `tests/conftest.py`의 `app_dir`는 `holiday_theme.current_match`를 `lambda today=None: None`으로 기본 패치한다. 실제 오늘이 테마 기간(예: 12/22~25)이어도 기존 UI 테스트의 색·배치가 변하지 않는다(패치를 빼면 `test_ui_calendar_cells.py` 5개가 실패하는 것을 확인했다). 테마를 검사하는 테스트는 이 위에 `current_match`를 다시 패치한다. `app_dir`를 쓰지 않는 직접 호출 테스트(`current_match` 자체)는 영향받지 않는다. 배포 EXE에 날짜 우회 옵션이 없으므로 EXE 확인은 시스템 날짜를 바꾼 테스트 PC에서 한다.
- **표시 전용 증명**: 테마 적용·해제·전환 중 `database`의 `save_`·`update_`·`create_`·`add_`·`delete_`·`trash_`·`restore_`·`import_`·`reset_`·`backup_` 접두 함수 전부를 예외로 바꿔 두고 실행한다(`_forbid_db_writes`). 스티키 크기 저장 같은 디바운스 타이머(500ms)가 이 구간 안에 만료되면 테마가 쓴 것으로 오인하므로 검사 전에 `_resize_timer`·`_save_timer`를 멈춘다(부하가 큰 PC에서 재현된 비결정 실패였다).
- **개발 미리보기**: `tools/dev_holiday_theme_preview.py --date YYYY-MM-DD`(PowerShell)는 `output/harness/<run-id>/appdata`를 `LOCALAPPDATA`로 잡고(하네스와 같은 격리·자동 실행 레지스트리 갱신 끔) `holiday_theme.current_match`만 그 날짜로 패치한 뒤 `main.py`와 같은 경로로 앱을 띄운다. 새 합성 DB에 일정·스티키·D-Day·집중 위젯을 넣고 크기 선택 창을 건너뛴다. `--scale`, `--theme on|off`, `--reuse <run-id>`(같은 합성 데이터), `--no-seed`, `--check-only`(앱 없이 경로·판정 JSON). 실제 AppData·`.lock`·실행 중인 기후노트를 건드리지 않으며(단일 인스턴스 잠금은 `APP_DIR`의 파일뿐, 프로세스 간 통신 없음) 트레이 아이콘이 하나 더 생긴다. `test_source_layout.py`가 `build.spec`·`build_app.py`·`src/`·`main.py`에 이 도구가 없음과, 바깥 `LOCALAPPDATA`가 있어도 합성 폴더만 쓰고 날짜가 고정됨을 단언한다.
- **새 버전 알림 미리보기**: `tools/dev_update_check_preview.py --latest v5.0`(PowerShell, 태그는 지금 버전보다 새로워야 한다)은 같은 합성 폴더 규칙으로 앱을 띄우고 `update_check.check_latest`를 바꿔 끼워 네트워크 없이 알림·점·안내창 강조를 1초 뒤 보여 준다. `--scale`, `--date`(공휴일 머리줄), `--reuse`, `--check-only`. `--latest`는 지금 버전보다 새로워야 한다. `test_source_layout.py`가 빌드 제외와 합성 폴더를 단언한다.
- **CPU 측정**: 개발 미리보기를 같은 합성 폴더로 테마 켬/끔 각각 띄워(메인 창+D-Day+스티키+집중 위젯, 시작 후 20초 대기) 앱 프로세스의 `TotalProcessorTime` 증가를 60초 평균으로 잰다. 한 코어 기준과 작업 관리자식(논리 프로세서 수로 나눔)을 함께 적는다. 측정 결과와 한계는 [작업 기록](work/2026-11-01-v4.6-holiday-theme.md)에 있다. 오프스크린에서 머리줄 레이어 그리기는 프레임당 약 0.4ms(한 코어의 약 1%)이므로 비용의 대부분은 그리기 자체가 아니라 부모·버튼 다시 그리기와 투명 창 내보내기(D-Day는 그림자 효과 다시 계산 포함)로 추정한다(창별 분리 측정은 머리줄 약 7%·D-Day 약 4.5%·스티키 약 0.5%, 한 코어 기준).
- **수동 확인(자동 검사 밖)**: 125%·150% 실제 배율, 혼합 DPI 모자 선명도, 트레이 숨김→복귀, PIN 잠금·해제 중 장식 정지, Win+D 후 복귀, 일정 입력 중 한글 IME, 설정 스위치 끔/켬, 집중 위젯 마우스 올림(큰 모자), 기본 크기 작은 배치의 실제 화면 모양, 태극기 규격(국기법 시행령 별표) 대조, 실제 EXE(합성 데이터·시스템 날짜 변경)는 [작업 기록](work/2026-11-01-v4.6-holiday-theme.md)의 '수동 확인 대기' 표에 기록한다. 자동 검사 통과는 이 항목의 통과를 뜻하지 않는다.

## v4.5a 추가 검증 계약 (src/ 배치)

- 앱 모듈은 `src/`에 있다. `tests/test_source_layout.py`가 루트 `*.py` 허용 목록(main·build_app·fetch_data, 미추적 파일 포함)·`src/__init__.py` 없음·`src.` 접두 import 금지(`build.spec` 포함)·`src/`의 `__file__` 사용처(`app_paths`·`ui_settings`)·공휴일 갱신 대상과 소스 실행 자동 시작 명령의 경로를 검사한다.
- `test_screen_text_ui.py`의 걷어내기 보호 시험은 추적 `.py` 전체(`git ls-files`)를 훑고 등록부가 실제로 잡히는지 단언한다. 폴더를 옮겨도 아무것도 검사하지 않고 통과하지 않는다.
- release는 빌드 뒤 `app_module_check`로 추적 중인 `src/*.py` 모듈이 모두 EXE PYZ에 들었는지 확인한다. `build.spec`이 `src/`를 못 보면 빌드는 성공하고 EXE만 시작 오류를 내며, 경고 파일에는 빠진 모듈 일부만 남는다(2026-10-31 실측). 일반 빌드(`build_app.py`)에는 이 검사가 없으므로 배포 EXE는 release로 만든다.
- quick·data에는 `test_packaging`·`test_build_app`·`test_ui_licenses`·`test_screen_text_ui`가 없다. 배치·빌드 경로를 바꾸면 `full`과 PowerShell `release`로 검증한다.

## v4.5 추가 검증 계약

- 알림 시작의 처리 시각 읽기 실패도 재시도한다. 저장값이 있는 경우 시작 전 놓친 알림, 키가 없는 경우 앱을 켠 뒤 알림을 복구하는 두 경우를 가짜 시계로 검사한다.

- 릴리스 전 재검토 회귀는 `test_database.py`에서 Qt int32를 넘는 위젯 위치/크기의 Import 쓰기 전 거절과 v1~v4 음수 모니터 좌표 왕복을 확인한다. `test_ui_schedule_alarm.py`는 일반/다시 알림 조회 실패·여러 다시 알림 중간 실패 후 처리 시각/목록 유지·다음 조회 복구·중복 없음·타이머 재예약을 검사한다. 최초 실패와 수정 검증은 [재검토 기록](work/2026-10-27-v4.5-critical-review.md)에 구분한다.

- `tests/test_schedule_storage.py`는 v19 열 추가/롤백, 반복 회차 CRUD·삭제 500개 상한·월말/윤년·반복 해제·v4 관계 remap/Import 롤백을 합성 DB에서 검사한다. UI는 `test_ui_schedule_list.py`·`test_ui_schedule_options.py`·알림 회귀와 125/150% 합성 배율로 확인한다.
- release smoke는 기존 데이터에 수정 회차를 seed해 연결·암호문·설정을 비교한다. v17와 v18 업그레이드를 각각 실행하고, v18의 세부 설정 열도 비교한다. 백업과 현재 DB에서 기존 열의 해시가 같아야 한다.
- release는 공휴일 단계 전후·pytest 후·빌드 후·smoke 후에 루트 `dist`의 파일 이름·크기·SHA-256을 기록한다. 기존 파일의 소실/변경은 실패이며 자동 삭제/복구하지 않는다. 새 산출물은 실행별 폴더에서 만든다. 과거 dist 소실의 원인은 아직 미확정이다.
- 공휴일 요청은 일시 오류만 최초 포함 3회(0.5/1.0초 대기, 각 10초 제한) 시도한다. HTTP 408/429/500/502/503/504·timeout·connection·IncompleteRead·일시 DNS만 대상이고 인증/인증서/응답 형식 오류는 재시도하지 않는다. 핵심 이름에 어린이날·현충일을 포함하며 테스트 네트워크는 차단한다.
- 파일 변환 worker 진행 JSON의 Windows 파일 경합은 실제 읽기 핸들로 재현한다. 제한 재시도 통과/지속 실패 상한을 검사하며, 과거 간헐 실패와 동일 원인이라고 단정하지 않는다.

## 개발 하네스 — 다음 버전부터의 기본 경로

Windows / Python 3.13과 `requirements-lock.txt`의 직접 의존성 10개를 사용한다. HWP 변환 후속에서 기존 lock의 `pywin32==311`을 직접 의존성으로 명시했고, push 보안 검사 1단계에서 XML 읽기용 `defusedxml==0.7.1`을 추가했다. 갱신 범위와 검증은 [1단계 작업 기록](work/2026-10-05-push-security-scan-step1.md)을 따른다. pywin32 줄의 `; sys_platform == "win32"`는 push 보안 검사(OSV) 대응 표시이며 하네스는 `;` 뒤를 버전으로 읽지 않는다([기록](work/2026-11-09-push-osv-pywin32-marker.md)).
하네스는 패키지를 설치하거나 lock을 갱신하지 않는다. 버전이 다르면 환경 오류로 중단하므로
개발자가 해당 가상환경에서 `pip install -r requirements-lock.txt`로 맞춘다.

일반 빌드도 같은 환경을 사용한다. `build.bat`은 프로젝트 `.venv` Python을 직접 실행하며,
`build_app.py`는 하네스의 `doctor()` 사전검사 실패 시 빌드를 시작하지 않는다. 자동 설치 없이
같은 인터프리터의 PyInstaller를 `--clean`으로 실행하므로 다른 Python의 이전 빌드 캐시를
재사용하지 않는다. `tests/test_build_app.py`는 환경 불일치·도구 누락 시 빌드 차단과 실패 코드 전파를 검사한다.
EXE 표시 버전이 같아도 포함된 Qt는 다를 수 있다. 이모지 글리프 수정의 산출물 확인에서는
EXE 내부 Qt DLL의 버전·해시를 검증 환경과 대조하고, 소스 렌더와 실제 EXE 캡처를 구분한다.

프로젝트 루트 PowerShell:

```powershell
.\.venv\Scripts\python.exe tools/verify.py doctor
.\.venv\Scripts\python.exe tools/verify.py quick
.\.venv\Scripts\python.exe tools/verify.py quick --tests tests/test_ui_sticky.py tests/test_ui_sticky_panel.py
.\.venv\Scripts\python.exe tools/verify.py data
.\.venv\Scripts\python.exe tools/verify.py full
.\.venv\Scripts\python.exe tools/verify.py release
```

| 프로필 | 검사 내용 | 사용 시점 |
|---|---|---|
| `doctor` | OS·Python·lock·필수 파일·출력 쓰기 확인, 앱 import 없음 | 환경 준비/드리프트 진단 |
| `quick` | 리소스·시작 경로·공휴일·실행기·핵심 DB/UI 소규모 회귀 | 일상 개발 + `--tests`로 관련 검사 추가 |
| `data` | DB·암호화·건강 검사·백업·Import/Export·스티키 저장·메인 UI·스트레스. 같은 묶음을 Python용 OpenSSL을 막은 프로세스로 한 번 더 돌린다(`pytest-no-openssl` 단계) | 데이터 또는 저장/보기 전환 변경 |
| `full` | 전체 pytest 1회 | 공통 실행기·격리 변경, 기능 마무리 |
| `release` | 공휴일 최신화(네트워크·`.env` 키 필요) → 전체 pytest 1회 → OpenSSL 없는 데이터 검사(`pytest-no-openssl`) → 새 EXE 빌드 → EXE 구성 검사(BINARY 출처·Qt DLL·앱 모듈·OpenSSL 파일과 버전 표시) → 격리 실행 시나리오(신규·기존·차단·v17 업그레이드·v18 업그레이드·새 버전 확인·화면 글자 따기) | 배포 산출물 검증 |

`data`는 저장 계약 검사가 들어 있는 `test_ui.py`도 포함하므로 짧은 단위 테스트 묶음이 아니다.

**OpenSSL 없는 데이터 검사**(v4.9): 배포 EXE에는 Python용 OpenSSL이 없어 `hashlib`·`hmac`을 Python 내장 구현이 맡는다.
`tools/run_without_openssl.py`가 어떤 모듈보다 먼저 `_ssl`·`_hashlib`의 import를 막고 pytest를 띄우며(pytest가 먼저
`hashlib`을 불러오므로 conftest에서 막으면 늦다), `data`·`release`가 `DATA_TESTS`를 이 방식으로 한 번 더 돌린다.
`tests/test_openssl_free.py`는 열쇠 재료(`security._get_hardware_id` 등)와 백업 해시가 OpenSSL이 있는 환경에서
적어 둔 값과 같은지 본다. 이 기대값은 고치지 않는다. 값이 달라지면 사용자가 기존 일정을 읽지 못한다.
`ssl`을 쓰는 테스트(`test_fetch_data.py`, `test_winhttp_get.py` 등)는 이 묶음에 넣지 않는다.
정확한 대상은 `tools/verify.py`의 `QUICK_TESTS`·`DATA_TESTS`가 정본이다.
`quick --tests`는 기본 회귀를 유지하면서 `tests/` 안의 파일 또는 `파일::테스트`를 추가한다.
대상이 없는 경우, 수집 오류, 0건 수집, 전부 skip은 통과가 아니다.
`full`/`release` 실행 전에 `quick`/`data`를 의무적으로 중복 실행하지 않는다.

`release`는 시작할 때 공휴일만 다시 받는다. 추가만 있으면 `holidays.py`를 갱신하고 계속하며, 삭제·이름 변경이 있으면 멈추고 종료 코드 1이다(`python fetch_data.py`로 받아들인 뒤 다시 실행). 키 없음·네트워크·HTTP·응답 코드 오류는 환경 문제로 종료 코드 2, 응답 형식·검증 실패와 읽을 수 없는 기존 `holidays.py`(손상·병합 충돌)는 데이터 문제로 종료 코드 1이다. 결과는 `result.json`의 `holidays`와 `summary.md`의 `## 공휴일 데이터`에 남고 키는 기록하지 않는다. pytest·빌드·EXE에는 키를 넘기지 않는다. `quick`·`data`·`full`·`doctor`는 네트워크를 쓰지 않는다.

파일 변환(v4.4)은 `tests/test_file_conversion.py`(합성 이미지·PDF·인코딩·비덮어쓰기),
`tests/test_file_conversion_runner.py`(실제 Job/QProcess·일괄·취소·시간 초과·정리),
`tests/test_ui_document_converter.py`(D안·추천·패널·파일창·수명·데이터 불변)와 기존 HWP/주머니/아이콘 검사를 사용한다.
100/125/150% 합성 배율을 확인하고 worker 선분기 때문에 전체 하네스를 실행한다.
PowerShell release 후 새 frozen EXE에서 qpdf 플러그인·offscreen 일괄·시작 비용·v4.3 대비 크기를 별도로 기록한다.
업무 PC 한글 회귀, Excel UTF-8 BOM CSV, 실제 혼합 DPI·KVM·Win+D는 수동 미확인과 구분한다.

캘린더 열 너비 변경은 `tests/test_ui_calendar_columns.py`를 포함한다. 창이 화면 안에 들어오는지만 확인해서는 요일 열 축소를 검출하지 못한다. 이 검사는 세로 논리 작업 영역(1080×1920, 864×1536, 720×1280)과 medium/compact에서 실제 날짜 열·요일 제목의 배치를 검사한다. `QT_SCALE_FACTOR=1.25`/`1.5`의 별도 실행은 합성 배율 확인이며 실제 혼합 DPI/KVM 수동 확인을 대신하지 않는다.

날짜·시간 계산기는 `tests/test_date_time_calculator.py`, `tests/test_ui_date_time_calculator.py`, `tests/test_date_time_integration.py`, `tests/test_ui_mini_apps.py`를 함께 검사한다. 초 보존/분 복사 정책·월말/윤년/역순·공휴일 범위/중복 제외·합산 행과 최근 복원·두 앱의 독립 수명·저장 실패/초기화 성공/실패·DB/Export/salt 불변을 포함한다. UI에는 스크롤 영역을 두지 않는다. 날짜 포함/날짜만/합산 종류와 오류 상태에서 입력·결과·복사·최근의 가로/세로 경계를 확인한다. 합산 이전/다음·24개 상한·숨긴 항목 오류/포커스 보존·종류별 선택과 최근 복원을 검사한다. `QT_SCALE_FACTOR=1.25`/`1.5`의 합성 배율은 실제 혼합 DPI/KVM 확인을 대체하지 않는다. 상세 기준은 [날짜·시간 계약](DATE_TIME_CALCULATION.md)을 따른다.

금액·숫자 표기 도우미는 `tests/test_money_notation.py`, `tests/test_ui_money_notation.py`, `tests/test_money_notation_integration.py`, `tests/test_ui_mini_apps.py`, `tests/test_mini_app_icons.py`를 함께 검사한다. 순수 계산은 시행규칙 예시·경계와 별도 참조 구현(결정적 난수 2만 건)을 대조하고 입력 거부·사사오입 경계·`Decimal` 정확도를 확인한다. UI는 세 모드×정상/오류/최장 입력×1000×900·480×500·420×500 작업 영역에서 스크롤·잘림이 없는지, 복사 형식·최근 기록·키보드를 검사한다. 통합은 세 앱의 독립 세션과 9개 수명 지점, DB/Export/salt 불변을 검사한다. `QT_SCALE_FACTOR=1.25`/`1.5`의 합성 배율은 실제 혼합 DPI/KVM 확인을 대체하지 않는다. 상세 기준은 [금액·숫자 표기 계약](MONEY_NOTATION.md)을 따른다.

`release`의 격리 실행에는 `screen_text` 시나리오가 있다(2026-11-07). 합성 데이터로 EXE를 띄워 UI 자동화(접근성 트리)로 미니앱 주머니와 영역 고르기를 누르고, 시험 창을 고른 영역으로 읽어 수·단위·번호(`1,234,567`, `87.3%`, `㎥`, `℃`, `Ⅱ.`)가 나오는지 본다. 실제 커서는 움직이지 않고 고르기 화면에 마우스 메시지를 보낸다. 실행 중 화면이 2~3초 어두워지고, 화면이 잠겨 있으면 캡처할 수 없어 실패한다. 선택형 미니앱을 걷어낸 빌드는 건너뛴다.

화면 글자 따기는 `tests/test_screen_text_layout.py`, `test_screen_text_engine.py`, `test_screen_text_capture.py`, `test_screen_text_ui.py`, `test_screen_text_guide.py`, `test_optional_mini_apps.py`를 함께 실행한다. 사용법 애니메이션은 단계별 프레임·단계 점·한 바퀴 처음과 끝의 흐려짐·좁은 크기와 125/150% 장치 배율·1초 동안 다시 그린 횟수(초당 약 24번 이하, 그림자 효과가 매 프레임 표면을 다시 흐리지 않게)를 `test_screen_text_guide.py`가, 사용법 화면 왕복(결과·탭·상태 유지)은 `test_screen_text_ui.py`가 검사한다. 포커스 검사는 OS 포그라운드와 무관하게 `focusWidget()`을 쓴다(`hasFocus()`는 사용자가 다른 앱을 쓰는 중이면 실패한다). 실제 화면을 찍지 않고 가짜 스크린샷과 Qt로 그린 합성 이미지만 쓴다. 125/150%는 `QT_SCALE_FACTOR` 합성 실행이며 실제 혼합 DPI/KVM·보안 프로그램 캡처 차단·한글 표 붙여넣기 확인을 대신하지 않는다.

### 화면 글자 따기 정확도 진단 도구

`test_screen_text_space_gaps.py`는 공백 판정(`word_spaces.join_words`)을 검사한다. 합성 줄로 모델이 낸 공백 유지, 넓은 자간의 음절 사이(확률이 낮으면 공백 없음), 좁은 조판(확률+작은 틈), 글자 높이만큼 벌린 머리글, `1,234`·`'25`·가운뎃점·닫는 부호 앞, 밑줄을 보고, 실제 모델로 `가. 목적`, `1. 2026년도`, 돋움·굴림·바탕의 음절 사이를 확인한다.

`test_screen_text_table_lines.py`는 표 선 격자를 검사한다: 행·열, 엑셀 눈금선, 어두운 화면, 병합 칸, 바깥선 없는 표, 표 중간을 자른 영역, 여백까지 이어진 세로선, 머리글에서 끊긴 세로선, 바탕색, 밑줄·문단 상자·글자 획이 표가 되지 않음, 칸 맞춤, 칸에 쌓인 숫자 줄의 행 나누기(값·비율 칸과 감긴 문장은 그대로), 표 앞뒤 글자 순서, HTML `rowspan`·`colspan`, TSV. `test_screen_text_small_text.py`는 여백·표 세로선 잇기(바짝 고른 글자의 세로획은 그대로)·영역 끝에 잘린 이웃 줄 거르기(실제 모델 포함)·패딩·2배 재검출·좌표 복원·메모리 부족 시 첫 결과 유지·글자별 확인 표시·바짝 고른 한 줄(실제 모델)을, `test_screen_text_marks.py`는 문장 부호 구제·별표·원문자를 검사한다.

`test_screen_text_number_marks.py`는 숫자 안 구두점을 검사한다: 쉼표·마침표 모양, 뒤 자릿수, `0,183`, 표시만 하는 `3,852`, 상자 아래의 꼬리와 다음 줄, 건너뛴 구두점, 티끌·끊긴 획, 어두운 화면, 나란한 수. `test_screen_text_units.py`는 `㎡ ㎥ ㎢ ℃`, `test_screen_text_roman.py`는 로마 숫자를 검사한다. 이 시험은 판독과 모양이 어긋나게 그려야 뜻이 있다(모양과 판독을 같게 그린 첫 시험은 고치기 전에도 통과했다).

`test_screen_text_deskew.py`는 기운 스캔본을 검사한다: 수평 쪽은 돌리지 않음, 기울기 각도, 아주 작은 기울기 무시, 높이가 다른 칸 둘, 글자가 드문 표(표 선), 그림 속의 비스듬한 선, 빈 영역, 바로 세운 뒤의 줄·모서리·배경, 실제 모델(2도 기운 여섯 줄을 끄면 0줄, 켜면 여섯 줄, 수평 쪽은 호출 없음).

`test_screen_text_cell_marks.py`는 칸과 글자 줄 사이의 표시를 검사한다: 모양 분류(크기 네 가지), 표시가 아닌 글자(`0 D C`), 빈 칸 상자, 빈 칸·글자 든 칸·칸을 채운 그림, 표 선만 남는 좁은 칸(인식이 멈추지 않음), 모델 판독을 존중하는 글자(`실적 계 15 V A`), 옅은 바탕 칸, 표시만 든 표의 격자 유지, 글자 줄 사이의 `▶`, 뒤 상자의 글머리를 두 번 내지 않음, 실제 모델의 점검표.

`test_screen_text_leading_symbols.py`는 글머리 기호 모양 분류를 합성 이미지로 검사한다: `■`(속이 찬 정사각)·`□`(속이 빈 정사각, 획이 얇아도 꼭짓점이 참)·`◇`(마름모, 모서리가 빔)·`ㅇ`(고리)·`○`(글자만큼 큰 고리, `□`가 아니고 확인 필요 표시)의 분류, `-`(짧고 납작한 막대, 모델이 이미 읽으면 그대로 두고 표 선·밑줄·윗줄·굵은 막대·점·붙은 음수 기호·`=`는 `-`가 아님), 기호가 상자 안·바로 왼쪽에 있는 경우, 글자로 시작하는 줄·뒤 글자에 붙은 덩어리·가늘고 긴 글자 모양에는 붙이지 않음, 표 테두리 건너뛰기, 왼쪽 이웃 상자의 기호를 가로채지 않음, 닮은 글자 교체·모델이 건너뛴 기호 앞붙임·고리만 확인 필요 표시, 위치 찾기가 기호를 글자와 따로 상자로 자른 경우(기호만 든 상자는 이웃 글자 높이를 기준으로 하고 글자를 통째로 기호로 바꾸며 겹치는 상자가 기호를 다시 가져가지 않음)를 확인한다. `test_screen_text_symbol_flag.py`는 `TextBox.unsure_prefix`→`Cell.unsure_prefix`로 기호 한 글자만 표시되고 복사 결과는 그대로임, UTF-16 위치, 표 칸, 그리고 실제 모델로 Qt 합성 줄(`■ □ ㅇ`, 14/16px)에서 기호가 나오고 일반 줄에는 붙지 않음을 확인한다. `test_screen_text_ui.py`는 글자 탭에서 기호 한 글자만 노랗고, 표 탭에서 그 칸이 노랗고, 고치면 '확인 완료'가 됨을 확인한다. `test_screen_text_corner_brackets.py`는 낫표 복원을 검사한다: 합성 이미지로 `┌ ┘` 꺾임만 낫표가 되고 진짜 `[ ]`·짧은 `[ ]`·방향이 반대인 꺾임·줄 가운데 뜬 꺾임·줄 높이만 한 꺾임·이웃 음절은 그대로이며 위치(steps→픽셀 대응)가 유지됨을 보고, 실제 모델로 Qt 합성 줄(16/20/24px)에서 `「 」`가 나오고 `[ ]`는 남고 낫표로 시작하는 줄에 글머리 기호가 붙지 않으며 `ctc_decode`가 상자마다 한 번임을 확인한다. 이 경로를 바꾸면 `test_screen_text_*` 전체를 함께 실행한다.

`test_screen_text_layout.py`의 순수 좌표 회귀는 병합 라벨에 의한 행 흡수, 여러 줄 셀의 읽기 순서/경고 위치, 인접 열의 작은 겹침, 한 셀의 겹친 판독 조각, 병합 머리글과 떨어진 문장 구별을 검사한다. 100/125/150/200% 좌표·평행 이동·입력 역순도 포함하며 OCR 재추론이나 실제 혼합 DPI 검사가 아니다. 실제 공개 문서 16영역과 기존 합성 dev 1,920개의 고정 상자 재구성 비교는 [표 구성 기록](work/2026-10-11-screen-text-table-layout.md)의 별도 수동 실행 증거다.

개발용 진단은 [개발 계획](work/2026-10-10-screen-text-lab-plan.md)의 자료 검증·채점·실제 엔진 실행·HTML 비교와 조건별 합성 자료·영역/CTC/입력·모델 비교를 `tools/screen_text_lab/`에 제공한다. [사용법](SCREEN_TEXT_LAB.md)의 별도 명령으로 실행한다. 첫 100개 합성 자료는 도구 검증용이며, 현재 조건 자료는 200원문×12조건이다. 원본 약 1,000개와 실제 캡처·새 원문 독립 평가 확대는 후속 범위다. 자료는 `output/screen_text_lab/corpus/`, 실행 증거와 HTML 보고서는 `output/harness/<run-id>/`에 둔다.

대규모 자료 생성·인식·후보 비교는 명시적으로 실행할 때만 동작한다. 통상 pytest·`quick/data/full/release`·일반 빌드·앱 시작·Git 훅/CI에 자동 연결하지 않는다. `tests/`에는 자료/정답 검증·채점·비교·보고서의 가벼운 자체 검사만 추가하며, 신규 자체 검사는 실제 모델 세션·대량 자료·화면 캡처를 실행하지 않는다. 기존 화면 글자 따기의 소규모 실제 모델 회귀 검사는 유지한다.

제품 인식/줄·표 구성 함수를 직접 호출한 결과를 기준으로 비교하고 원본·변형·실제 캡처를 별도 집계한다. 개발용과 최종 평가용은 문서/원본 묶음 단위로 나누며, 실사용 AppData·DB·salt·기존 실행 중인 앱에는 접근하지 않는다. 제품의 캡처 메모리 전용·오프라인 계약을 유지하고 진단 도구와 자료는 EXE에 추가하지 않는다.

`quick --tests tests/test_screen_text_lab.py`는 손계산 편집 거리·표 위치·분할 누출·이미지 해시·불완전 진행 기록·입력 변경·중단/시간 초과·HTML 이스케이프·비교 호환성을 검사한다. 실행기 경계 검사는 가짜 엔진/프로세스를 쓰고 별도 import 검사에서 제품·OCR·이미지 모듈의 조기 로드를 차단한다. 실제 모델/100개 자료 및 제품 경로 대조는 명시적인 진단 명령의 증거로 구분한다. [구현 기록](work/2026-10-10-screen-text-lab-implementation.md)을 따른다.

등록·검토 창은 `review` 명령으로만 연다. `quick --tests tests/test_screen_text_lab.py tests/test_screen_text_lab_review.py`는 작은 합성 PNG의 등록·정답/표·검토 상태·새 버전 저장/재열기·원본 보존·실패 시 입력 보존·목록/확대·창 닫기 보류를 검사한다. 창 렌더 PNG는 하네스 실행 폴더에 남긴다. 이 자체 검사에서는 OCR/실제 화면 캡처/대량 자료를 실행하지 않는다. [등록·검토 기록](work/2026-10-10-screen-text-lab-review.md)을 따른다.

`generate --profile conditions`는 200원문×12조건(2,400개)을 만드는 별도 수동 명령이다. `quick --tests tests/test_screen_text_lab.py tests/test_screen_text_lab_conditions.py`의 자체 검사는 원문 목록/분할 누출을 메타데이터로 확인하고 6개·12개의 작은 이미지만 그린다. 가짜 예측으로 같은 원문의 조건 쌍·누락/실패 분모·공백 제외 CER·보고서 링크를 검사하며 실제 OCR은 실행하지 않는다. 개발용 1,920개 실험과 최종 평가용 480개 보류는 [조건 진단 기록](work/2026-10-10-screen-text-lab-conditions.md)으로 분리한다.

진단의 전처리 후보·문자 점수 관측은 `quick --tests tests/test_screen_text_lab.py tests/test_screen_text_lab_conditions.py tests/test_screen_text_lab_candidates.py`로 검사한다. 가짜 추론 세션의 실제 제품 경로 불변·CTC 반복/blank/공백 처리·후보 설정 전달과 예외 시 원복·신규 오류/복구·오경고/미채점 분모를 확인하며 실제 모델 세션이나 대규모 실험은 실행하지 않는다. 명시적인 1,920개 후보 실험과 baseline 대조는 [후보 기록](work/2026-10-10-screen-text-lab-candidates.md)에 별도 실행 ID로 남긴다.

영역 분리 진단 자체 검사는 위 후보 검사에 `tests/test_screen_text_lab_regions.py`를 추가한다. 사각형 합집합의 중복 면적·겹침/누락 가능성, 픽셀 경계의 2px 확장, 주석 없음/불완전/미검토 분모, 좌표만 전달하는 가짜 인식기, 추가 진단 실패 시 제품 결과 보존·partial 상태, 기본 옵션 미실행과 주석 해시를 검사한다. 실제 1,920개 주석 직접 인식은 `run --diagnose-regions`로만 별도 수행하며 [영역 진단 기록](work/2026-10-10-screen-text-lab-regions.md)에 증거를 남긴다.

픽셀 전처리/선택적 재인식 후보는 `tests/test_screen_text_lab_preprocessing.py`에서 가짜 세션으로 비율·패딩·CTC 끝부분·어두운/복잡한 배경·작은 문장부호·폭 폭증 제한·취소·점수 차이·공백 보존을 검사한다. 실제 후보 비교 및 480개 최종 평가는 별도 명령으로 수행했고 [개선·최종 평가 기록](work/2026-10-10-screen-text-accuracy-improvement.md)에 남긴다. 최종 후보는 표/완전 일치 퇴행으로 제품 적용을 보류했다. 이미 사용한 holdout을 후속 튜닝의 새로운 독립 평가 자료로 취급하지 않는다.

짧은 구간 재인식은 `tests/test_screen_text_lab_short_regions.py`를 후보/진단 자체 검사와 함께 실행한다. 작은 픽셀 배열·가짜 판독으로 빈 열 분할/전체 픽셀 보존, 밝은/어두운 배경, 짧은 줄/복잡한 배경/구간 상한 fallback, 공백/빈 판독 보존, 실패·취소 때 메서드 복원을 검사한다. 실제 48개 dev의 기준/두 후보는 별도 수동 실행이며 통상 검사에 연결하지 않는다. [고정 실험과 중단 판단](work/2026-10-11-screen-text-short-regions.md)을 따른다.

CTC 출력 진단은 `tests/test_screen_text_lab_ctc.py`의 작은 분포 완전 탐색으로 문자열 경로 질량·beam·반복/blank·공백 주변화를 대조하고, 가짜 세션으로 실제 제품 배치 순서·절삭·결과 보존·정답 비의존·관측 실패/모델 실패/취소 복원·제외 분모·HTML 이스케이프를 검사한다. 기존 진단 자체 검사와 함께 `quick --tests`로 실행한다. 실제 모델 출력 추적은 별도 `run --diagnose-ctc` 명령에만 있으며 일반 빌드/테스트에 연결하지 않는다. [2026-10-11 진단 기록](work/2026-10-11-screen-text-ctc-diagnosis.md)의 선택 표본 76개는 독립 정확도 평가가 아니다.

입력/모델 비교는 `tests/test_screen_text_lab_recognizers.py`에서 가짜 세션으로 원 crop 보존·밝기/기하 분리·BGR/회색조·모델 고유 높이/패딩·softmax·제품 native 입력 동등성·취소·사전/shape 계약·누락/변조 파일 거부·수동 옵션/조합 제한·HTML 이스케이프·동일 검출 영역 비교를 검사한다. 외부 모델 파일을 읽거나 다운로드·실제 모델 추론을 하지 않는다. 기존 진단 자체 검사와 함께 `quick --tests`를 실행한다. 실제 모델/입력 조건 비교는 별도 명령이고 [실험 기록](work/2026-10-11-screen-text-model-input-comparison.md)에 실행 ID와 사용한 모델 해시를 남긴다.

불일치 경고 진단은 `tests/test_screen_text_lab_disagreement.py`에서 작은 문자열의 모든 편집 경로를 독립 열거해 최적 정렬의 위치 합집합/교집합을 대조한다. UTF-16·이모지·삽입점·공백 제외·반복 문자 모호성·화면 경고와 위치 적중 분리·미채점 분모·HTML 원문 보존/이스케이프·가짜 인식기의 검출 1회/정답 비의존/실패·취소 복원·증거 해시 관측 유무의 입력 동등성을 검사한다. 관련 진단 자체 검사와 함께 `quick --tests`로 실행하며 실제 모델은 사용하지 않는다. 저장된 결과 분석 `disagreement`와 실제 반복 성능 측정 `benchmark-disagreement`는 별도 수동 명령이다. [경고 진단 기록](work/2026-10-11-screen-text-disagreement-warning.md)에 현재 결과를 남긴다.

경고 조건 비교는 `tests/test_screen_text_lab_warning_rules.py`에서 CTC 반복/blank/공백 점수, 중복 텍스트가 있는 표의 문자 순서, UTF-16/삽입점의 직접·인접 점수, 규칙 임계값/결측값, 기존 경고 보존, 실제 오류 손실, 원문 그룹 분할/정답 비의존, 확인 채점 전 선택 파일 고정, 격리 worker/실패 상태·HTML 이스케이프를 검사한다. 가짜 세션·작은 이미지뿐이며 실제 문자 점수 수집은 별도 `warning-rules` 수동 명령으로 실행한다. 현재 결과는 [조건 비교 기록](work/2026-10-11-screen-text-warning-rules.md)에 남긴다.

실제 CLI 자료 준비는 수동 `capture-kit`·`show-capture`·`import-captures` 명령으로 제공한다. `quick --tests tests/test_screen_text_lab.py tests/test_screen_text_lab_review.py tests/test_screen_text_lab_capture_kit.py`에서 문구/개발·보류 분할, 예문 출력만 수행, 수집 계획 변경 거부, 작은 합성 PNG의 미검토 등록·같은 문구 그룹·중복/잘못된 입력·명시 폴더 비재귀 읽기·원본 보존·기존 검토 후 채점을 확인한다. 자동 검사에 실제 화면 캡처나 OCR 세션은 추가하지 않는다. 수집 예정 수와 실제 확보량을 구분하며 [실제 캡처 준비 기록](work/2026-10-11-screen-text-real-capture-intake.md)을 따른다.

추가 학습 개발 도구는 `quick --tests tests/test_screen_text_lab_training.py tests/test_screen_text_lab_datasets.py tests/test_screen_text_lab_evaluation.py tests/test_screen_text_lab_crop_evaluation.py tests/test_screen_text_lab_reproduction.py`로 검사한다. 작은 합성 배열·문자열·가짜 모델 출력으로 사전/CTC/NRTR 경계, 분할/누출/OOV 원문 보존, 사전 확장 때 공백 ID 이동, 저장 증거의 해시/누락, 원본 그룹 bootstrap, 표/숫자/경고 독립 판정, 제품 전처리 호출과 후보 확률 검증을 확인한다. 실제 Paddle 설치·GPU·대규모 합성 생성·원본 재수출·학습·CPU OCR은 별도 수동 실행이다. 협업 중 소스가 바뀐 하네스의 `inputs_changed`는 통과로 쓰지 않고 소스 동결 뒤 다시 실행한다. [계획](work/2026-10-11-screen-text-finetuning-plan.md)과 [실행 기록](work/2026-10-11-screen-text-finetuning-implementation.md)에 자료 버전·환경·실패·실제 결과를 구분한다.

사전 확장·BN 진단·후보 등록·전체 경로 연결의 보조 검사는 `tests/test_screen_text_lab_training_state.py`, `tests/test_screen_text_lab_training_bn.py`, `tests/test_screen_text_lab_training_frozen_bn.py`, `tests/test_screen_text_lab_training_candidate.py`, `tests/test_screen_text_lab_full_candidate.py`를 같은 `quick --tests` 명령에 추가한다. 전체 tensor 일치와 제품이 사용하지 않는 패딩만 차이가 있는 경우를 구분하며, 실제 사용하는 CTC 구간의 차이를 패딩 차이로 통과시키지 않는다.

개발용 다운로드의 주소/파일 경계는 `tests/test_screen_text_lab_bootstrap.py`와 `tests/test_security_scan_rules.py`를 함께 실행한다. 네트워크 없는 가짜 HTTPS 응답으로 고정 공식 주소만 허용, 파일/HTTP/FTP 차단, HTTPS 프록시 유지, 리디렉션 거부, 기존 파일 보존과 해시 기록을 검사한다. 추적 파일 대상 보안 회귀이므로 새 개발 도구를 Git에 등록한 뒤에도 실행한다. 제품 모델 다운로드나 실제 학습을 시작하지 않는다.

### 실행 격리와 증거

라이선스 안내는 `quick --tests tests/test_ui_licenses.py tests/test_ui.py tests/test_packaging.py`로 검사한다. 구성요소 원문·저작권·기록 해시, OCR 폴더 유무에 따른 목록, 파일 누락 표시, 실제 버튼 열기·전체 복사·닫기, 부모 숨김/비활성/닫기·메인 PIN 잠금, 작은 작업 영역과 합성 DB dump/Export/salt 불변을 확인한다. 125/150% 별도 quick의 합성 PNG를 확인하고 `release` 후 실제 EXE의 고지·모델·Qt/네이티브 DLL 해시를 이전 검증본과 대조한다. 이 검사는 법적 적합성·전수 SBOM 또는 외부 심사자 소스 접근을 대신하지 않는다.

최초 크기 선택은 `tests/test_first_run.py`에서 신규 선택·취소·기존/손상 분기, 세 크기의 DB/첫 백업/메인/재실행과 Export/Import, 넓은·한 열 배치의 키보드와 작은 작업 영역 8종을 검사한다. 미리보기 크기 규칙은 `ui_main`의 크기 계산·모서리 좌표(5mm 스냅 이내)와 대조하고, 선택 후 실제 그림 위치 픽셀·애니메이션 중 재선택·다크 테마에서의 밝은 화면·Pretendard 부재 시 폴백 배치를 확인한다. 125/150%는 별도 `QT_SCALE_FACTOR` 합성 실행으로 확인한다. release의 fresh 시나리오는 이번 Job 소유의 실제 최초 설정창에서 Enter로 기본 선택을 확정하고, 선택 전 DB/salt/백업 미생성 및 선택 후 메인·백업·저장값을 검사한다. existing/blocked에는 최초 설정이 없어야 한다. 제품 우회 플래그를 추가하거나 실사용 데이터를 검사 입력으로 쓰지 않는다. 실제 Windows 잠금·혼합 DPI/KVM은 수동 미확인과 구분한다.

문서 형식 변환은 `tests/test_hwp_conversion.py`, `tests/test_hwp_conversion_runner.py`, `tests/test_ui_document_converter.py`, 주머니/SVG 검사를 함께 실행한다. HWP 보호 헤더·손상 출력·동명 비덮어쓰기·원본 보존, 실제 작업 프로세스/자식의 취소·시간 초과·Job 배정 실패, 실제 파일창/드롭·작은 화면·잠금/숨김/초기화/종료와 DB/Export/salt 보존을 검사한다. 모의 엔진 검사를 실제 문서 변환 성공으로 간주하지 않는다. 설치된 공식 CLI를 사용하는 제품 UI와 frozen worker를 별도 격리 실행하고 원본/기존 결과 해시·필수 XML·작업 모드 DB 미생성·임시 폴더 정리를 확인한다. 한글 버전/DRM/서식 시각 대조는 별도다. [계약](DOCUMENT_CONVERSION.md), [현재 기록](work/2026-10-03-hwp-document-converter.md).

각 호출은 `output/harness/<시각-고유값>/`을 새로 만든다. 그 안에:

- `result.json`, `summary.md`: 상태·실제 검사 수·환경·명령·단계별 코드·입력 해시·수동 미검증 범위.
- `pytest.log`, `pytest.xml`, `pytest-tmp/`, `pytest-cache/`, `appdata/`: 검사 로그와 격리 데이터.
- `release`는 추가로 `build.log`, `build/`의 TOC, `dist/`의 신규 EXE,
  `smoke.log`, `smoke.json`, `smoke/<시나리오>/`의 합성 데이터·전후 해시를 보존한다.

출력은 gitignore 대상이다. 실행기는 이전 결과·루트 `dist/`를 재사용하거나 삭제하지 않는다.
실패 원인을 확인한 뒤 새 실행 ID로 다시 실행한다. 자동 재시도·자동 게시 기능은 없다.
여러 단계 작업에서는 [작업 양식](templates/WORK_NOTE.md)을 `docs/work/<날짜>-<주제>.md`로 복사하여
완료 조건과 실제 결과 경로를 기록한다.

수집 전에 `CLIMATENOTE_TEST_APPDATA`를 통해 `LOCALAPPDATA`를 실행 폴더로 격리한다.
이 변수는 프로젝트 `output/harness/` 하위의 해석된 경로만 허용한다.
직접 pytest는 기존 `.pytest-localappdata` 기본 경로를 유지한다. 각 테스트의 `app_dir` 픽스처도 유지한다.
`app_dir`는 DB 경로를 되돌리기 전에 해당 테스트가 만든 앱 top-level 창을 폐기한다.
메인만 qtbot에 등록한 경우에도 별도 플로팅 저장 타이머가 다음 테스트에 남지 않도록 한다.
이전부터 있던 창이나 Fluent 전역 helper는 폐기 대상에서 제외한다.
EXE는 시나리오마다 별도 AppData를 사용하고 `CLIMATENOTE_SKIP_STARTUP_REFRESH=1`로
실제 시작프로그램 경로 갱신을 막는다. 기존 앱을 종료할 필요가 없다.

보고서에는 검사 전후 저장소 파일 목록(`git ls-files`, 미추적 포함·gitignore 제외)의 SHA-256을
종류·폴더와 무관하게 기록한다(OCR 모델·fixture SQL/JSON·고지 JSON·`LICENSE`·`build.bat` 포함, 2026-10-24 v4.4b).
루트 숨김 파일(`.env` 등)·내부 `security/`·`output/`과 진행 기록인 `docs/work/`·`docs/superpowers/`,
홍보 영상 작업 `motion/`은 제외한다. 검사 중 코드가 달라지면
`inputs_changed`로 실패한다. 문서 변경만 했으면 링크·사실·지침 이전을 검토한다.

종료 코드: `0` 자동 검사 완료·통과, `1` 검증 실패/입력 변경,
`2` 인자·환경·수집·실행기·보고서 오류, `130` 사용자 중단.
단계의 실제 하위 프로세스 종료 코드는 별도 기록된다.
`running`이 남은 결과는 중단된 미완료 실행이며 통과 증거가 아니다.

### EXE 격리 검증 범위

`release`는 기존 `build.spec`을 같은 Python의 `-m PyInstaller`로 실행한다.
이번 EXE의 크기·SHA-256·Windows 버전·서명 상태와 TOC 해시를 기록한다.
현재 `NotSigned` 상태를 자동 실패로 바꾸지 않는다. 라이선스·서명 과제는 기존 결정대로 별도다.
**release·빌드는 PowerShell에서 실행한다.** Git Bash의 PATH로 실행하면 PyInstaller가
`C:\Program Files\Git\mingw64\bin`의 `libcrypto-3-x64.dll`/`libssl-3-x64.dll`을 EXE 번들에
잘못 포함시킨 사례가 있었다(v3.8c 최초 release). v4.4b부터 `release`가 빌드 직후 격리 실행 전에
`build/build/Analysis-00.toc`를 자동 대조한다. BINARY 출처는 프로젝트 `.venv`·그 기본 Python·System32의
VC 런타임(`vcruntime140*`·`msvcp140*`)만 허용하고, EXE 안 Qt DLL은 검증 환경 원본과 바이트가 같아야 한다.
어긋나면 종료 코드 1이며 결과는 `result.json`의 `bundle`과 `summary.md`의 `## EXE 구성`에 남는다.
직전 EXE와의 바이트 동일·크기 차이는 Qt 업그레이드를 막지 않도록 자동 통과 조건으로 쓰지 않는다.
v4.9부터 같은 자리에서 `openssl_check`가 이번 EXE에 Python용 OpenSSL(`libcrypto`·`libssl`·`_ssl`·`_hashlib`)과
Qt의 `qopensslbackend.dll`이 없는지 TOC와 EXE 안 파일 이름으로 확인하고, EXE 안 모든 dll·pyd에서
`OpenSSL <버전>` 표시를 ASCII와 UTF-16으로 찾는다. 표시는 `cryptography`의 `_rust.pyd`에만 있어야 하며,
결과는 `result.json`의 `bundle.openssl`과 `summary.md`의 `OpenSSL:` 줄에 남는다.
EXE 구성을 바꾼 작업은 `tools/exe_handoff_check.py --old <이전 배포 EXE> --new <이번 EXE>`로 같은 합성 데이터를
이전 → 이번 → 이전 EXE 순으로 열어, 매번 데이터 불변과 건강 검사를 확인한다(`release`에는 넣지 않는다).

1. 신규 설치: 빈 AppData → 응답하는 창 → 현재 schema·SQLite 무결성·32바이트 salt·유효한 일일 `.cnbak`·오류 로그 확인.
2. 기존 데이터: 현재 저장 계약의 합성 일정(색 3개와 시각+알림·기간·반복 끝 날짜/건너뛴 날 세부 설정)·메모·닫힌/휴지통 스티키·D-Day·집중/세션·바로가기·설정 → 실행 전후 raw/복호화 내용 해시·ID·일정 세부 설정 값·salt 불변과 최초 보호백업 확인. seed에 세부 설정 일정이 빠지면 실패한다. 알림은 검사 중 울리지 않게 한 달 뒤로 두며, 열린 스티키는 창 크기 5mm 격자 저장 때문에 seed하지 않는다.
3. 시작 차단: 합성 DB의 salt 손상 → 데이터 보호 오류창만 표시 → 원본 DB·salt·기존 보호백업 해시 불변 확인.
4. 업그레이드(v4.1): `tests/fixtures/schema_v17.sql`로 만든 v17 합성 데이터 → 새 EXE 시작 → 모든 표의 기존 열 값 해시·salt 불변, 새 열 기본값, v18, `calendar_pre_v18_v17.db`가 원본과 같은지, 그리고 '기후노트 업데이트 안내' 창이 떴는지 확인. 다른 시나리오에서 이 창이 뜨면 실패다. v4.3에서는 보호백업 후 PIN 검증값 승격을 별도 확인한다. 새 검증값이 이전 PIN을 검증함을 확인한 뒤 `privacy_pin` 하나만 이전 값으로 정규화해 기존 열 해시를 대조하며, 마이그레이션 전 보호본은 정규화 없이 원본 전체를 대조한다.
5. 새 버전 확인: 합성 데이터에서 `인터넷 접속`을 켜고 닫힌 포트(`HTTPS_PROXY=http://127.0.0.1:9`)를 준 EXE가 90초 안에 `error.log`에 `새 버전 확인 실패: connection`을 남긴다. 실패가 화면에 보이지 않는 기능이라 이 기록이 EXE에서 프록시 읽기와 WinHTTP 통신 층(`winhttp_get.py`)까지 돈다는 근거다(인터넷 불필요). 실제 TLS는 인터넷 PC에서 `tools/smoke_release.py --exe <EXE> --run-dir <실행 폴더> --live-update-check`로 105초(첫 확인 60초 + 요청 전체 상한 30초 + 마지막 읽기 10초 + 여유) 동안 실패 기록이 없는지 본다(`release`에는 넣지 않는다).

**격리된 EXE 창이 잠시 표시된다.** 각 시나리오는 60초 안에 창 응답과 백업 상태를 확인한다.
Windows Job Object에 대기 중인 launcher를 먼저 배정한 뒤 실행을 허용하고, 실패/중단 시에도
그 실행의 프로세스 트리만 정리한다. 배정 실패 시 EXE를 실행하지 않는다.
이 방식은 [Microsoft의 자식 프로세스 소속·Job 종료 계약](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)을 사용한다.
테스트·빌드 단계의 자식 프로세스도 같은 소유권 범위로 관리한다.
이름 기반 전체 프로세스 종료나 실사용 데이터 검사는 하지 않는다.

정리는 Job 닫기에 의한 **강제 종료**이며 보고서에 `graceful_quit_verified: false`로 남는다.
정상 종료 직전 저장·실제 native UI·혼합 DPI·성능·라이선스 준수는 이 smoke의 통과 범위가 아니다.
작업이 화면을 점유할 수 있으므로 `release`는 사용 가능한 데스크톱 세션에서 실행한다.
서비스 세션의 CI 연결은 Windows Runner 환경을 확인한 뒤 별도로 구성한다.

### 수동 배포 확인 기록

자동 `release` 통과는 배포 승인이 아니다. 다음 양식을 작업 기록에 포함하고,
확인하지 않은 항목은 `미확인`으로 남긴다. 기존 보류 과제를 증빙 없이 완료 처리하지 않는다.

검사일 / 담당자 / OS / 모니터·DPI / KVM / EXE SHA-256: `<기입>`

| 항목 | 결과(통과·실패·미확인) | 환경·관측·증거 |
|---|---|---|
| 버전 표시·일정 편집/삭제·설정/휴지통·정상 종료 직전 최신 스티키 저장 | 미확인 | |
| Win+D 직후 Explorer·브라우저 전환 및 바탕화면 레이어 | 미확인 | |
| 음수 좌표·혼합 DPI·가로/세로 모니터·KVM 전환 | 미확인 | |
| 특정 PC 설정/휴지통 멈춤 | 미확인 | |
| Defender 검사 | 미확인 | |
| 일정 알림(실제 시각·절전 복귀·PIN 잠금·Win+D·다중 모니터 카드 위치·알림음) | 미확인 | |
| 라이선스·SBOM·Qt 고지·서명 후속 과제 | 미확인 | [보류 기록](RELEASE_HISTORY.md) |

최종 배포 판단 / 근거: `<별도 기입>`

## Test Suite

- **KVM 위치 왕복(v3.8 후속)**: `test_ui_kvm_position.py`는 원래 조사 재현 파일을 정식 회귀로 승격했다. 세 크기의 자유/모서리·위치 편집 중/고정, 분리→재연결, 화면 목록 순서/객체/원점 변경, 재실행, 임시 논리 크기, 없는/모호한 장치, 설정창 열린 중 순서 변경/저장 실패, 초기화, DPI 신호와 드래그 취소, 스티키/D-Day/집중 위치 및 DB dump/Export/salt 보존, PIN Export/Import 왕복을 검사한다. `quick --tests tests/test_ui_kvm_position.py tests/test_ui_screen_change.py tests/test_ui_calendar_drag.py tests/test_ui_calendar_move.py tests/test_ui.py` 또는 `full`/`release`로 실행한다. 합성 QScreen 목록과 숨겨진 실제 Qt 창을 사용하므로 회사 KVM 이벤트 순서·실제 혼합 DPI/Win+D 실기 검증은 별도다.

- **단위 환산기(v3.8a)**: `test_unit_converter.py`는 182개 항목의 독립 기준값·모든 단위 쌍 왕복·경계·오류 입력·표시·기록·반복 교환을 검사한다. `test_ui_unit_converter.py`는 실제 입력/단위 목록/키보드/주머니 실행·재사용·잠금/트레이/사이드바/초기화 성공·실패/종료 보류·모니터 보정·DB 전체 dump/Export/salt 보존과 합성 PNG를 확인한다. ppm의 몰/질량분율 구분·0/100% 경계·밀도 없는 ppm↔mg/L 차단, 440×580 내용/488×628 외곽 배치·실제 반투명 그림자/모서리 잘림·그림자 여백 클릭 후 계산 상태 보존·28px 행/0px 간격/큰 글꼴의 모든 분류 이름/기호 배치·작은 화면 스크롤과 기본 크기 복원도 검사한다. 주머니·일정 이모지·데이터 수명 회귀를 함께 실행한다. 125/150%는 별도 프로세스의 합성 배율이다. 실제 EXE에서 주머니→환산→닫기도 격리 데이터로 확인하고 기존 3개 smoke 시나리오와 구분한다. [계수 정본](UNIT_CONVERSION.md), [확대·환경 단위 기록](work/2026-09-21-mini-app-environment.md), [현재 그림자·가독성 기록](work/2026-09-23-unit-converter-shadow.md).

- **조건 계산 회귀(v3.8a)**: 물/직접 밀도·기체 물질/온도/절대압·온도차의 독립 기준값과 역환산, 미선택/빈 값/음수/비유한 값·100% 경계를 검사한다. UI에서는 실제 입력·근사 표시·다른 단위·교환·조건별 기록 복원/중복 구분·기록 겹침/잘림·기체 팝업 잠금 정리·340×400 조건 접근성을 검사한다. DB dump/Export/salt 보존 시나리오에도 새 계산 조건을 포함한다. 125/150% 합성 배율과 신규 release/번들 대조는 [현재 기록](work/2026-09-23-v3.8a-water-conversion-plan.md)에 남긴다.

- **환산기 드롭다운**: `test_ui_unit_converter.py`는 FROM/TO·물질·온도 모드를 실제 클릭한 직후 실제 목록이 표시되고 임시 `QRollEffect`가 생성되지 않는지 검사한다. 전역 콤보 효과 ON/OFF 보존, 선택·Alt+Down/Esc·숨김, 동일 높이/화살표 픽셀·읽을 수 있는 목록 행, 팝업 예외 후 효과 복원을 포함한다. 최종 표시만 기다리면 150ms 중간 이미지 회귀를 놓친다. 선택 클릭은 native 커서 이동과 Qt의 최초 release 보호 시간을 고려한다. 125/150% 및 새 EXE 증거는 [현재 기록](work/2026-09-24-unit-converter-dropdown-fix.md)을 따른다.
- **미니앱 주머니**: `test_ui_mini_apps.py`는 세 크기/짧은 화면의 6슬롯 접근·252×280px 본체/그림자 포함 300×328px 창/104×100px 타일 4칸·SVG 아이콘 로드·머리부 앱 개수·사이드바 버튼 스타일·반투명 그림자와 모서리 잘림·예정 타일 클릭/Tab 차단·실제 앱의 예정 자리 대체와 2열/세로 스크롤·실제 클릭/키보드/반복 열기·그림자 여백 닫기·음수 좌표 모니터 위치 보정·일정 저장 실패 게이트·잠금/트레이/보기 전환 취소·기존 DB 전체 dump/Export/바로가기/salt 불변을 검사한다. 미니앱/환산기 DB 비교는 기동 시 예약된 스티키 크기 스냅 저장 완료 후 기준 snapshot을 잡고 조작 구간의 전체 raw 불변을 확인한다. 기존 `test_ui.py`의 바로가기 등록/관리/드롭과 `test_ui_data_lifecycle.py`·`test_ui_schedule_emoji.py`의 수명 회귀를 함께 실행한다. 합성 PNG와 실제 EXE 자동 smoke·실제 혼합 DPI/KVM 수동 확인을 구분한다. [현재 주머니 기록](work/2026-09-27-v3.8c-money-notation-pocket.md).
- **미니앱 아이콘**: `test_mini_app_icons.py`는 `resources/icons/mini_apps/*.svg`가 텍스트·이미지·필터·마스크·CSS·외부 참조 없는 QtSvg Tiny 파일인지 검사한다. 48px의 100/125/150% 렌더에서 둥근 모서리 투명·그라데이션 양 끝 색·가운데 흰 선, 날짜·시간 시계 면, 준비 중 점선, 런처 강조색을 확인한다.

- **위치 편집·스마일**: `test_ui_calendar_move.py`는 평소 고정(예전 설정 행 보존·Export 포함)·세 크기 십자 화살표 → 실제 마우스 끌기 → '완료'·Tab/Space/Enter/Esc와 포커스 이동·일정 입력 포커스와 데이터 불변·두 상태의 머리줄 배치('완료' 52×32, 연월 가운데)·점선 두 톤(머리줄 위 연한 파랑/그 밖 진한 파랑)과 안내 띠 픽셀·안내 띠가 머리줄 높이를 따라감·자동 종료 8가지(완료/Esc/비활성/잠금/트레이/크기/가져오기/초기화)와 끌던 중 종료 시 끌기 전 자리로 복귀·모니터 변경 시 편집 유지·고정 중 끌기 안내 1회와 머리줄 아래 위치(십자 화살표를 가리지 않음)·창 안 폭을 검사한다. `test_ui_calendar_drag.py`는 고정 상태 차단·화면 간 크기/위치 보정을, `test_ui_schedule_emoji.py`는 색상 원과 스마일의 실제 렌더 외경/중심·선택/Undo를 검사한다. 관련 `quick --tests` 또는 `release`에서 합성 PNG(`calendar-move-edit-*.png`)를 남기며 실제 혼합 DPI/KVM 수동 검증을 대신하지 않는다.

- **스티키 파일 링크(v3.7b)**: `test_sticky_file_links.py`의 Qt href/밑줄 메타데이터 왕복·경로 검사, `test_ui_sticky_file_links.py`의 서식·Undo·체크박스·두 보기·외부 실행 가로채기·주의 표시 무변경·8개 기존 테이블 raw/salt 보존, `test_ui_data_lifecycle.py`의 최신 링크 Export/실패·잠금/트레이/폐기/보기 전환 취소를 검사한다. 하네스 실행에는 `sticky-file-links.png` 합성 UI 캡처를 남긴다. 실제 파일 드롭·IME·기본 프로그램·혼합 DPI/KVM은 별도 수동 확인이다.

- **Location**: `tests/` (pytest 기반 전체 테스트)
- **바로가기 대화상자(v3.8d)**: `tests/test_ui_shortcut_dialogs.py`와 기존 `tests/test_ui.py`를 검사한다. `shortcut_dialog_probe.py`는 별도 Job/합성 AppData에서 실제 메뉴 클릭과 Qt 파일/폴더/이름 변경/경로 재지정 대화상자의 확인·취소를 실행한다. 클릭 처리 중 대화상자가 열리지 않는지, 메뉴가 폐기되는지, 기존 데이터·salt·다른 슬롯이 보존되는지 확인한다. native 선택창은 별도 격리 재현으로 검사하고 회사 PC/실제 사용자 입력·KVM 확인과 구분한다. 예약 호출은 슬롯/부모 숨김·비활성·잠금/트레이·재조회·폐기를 검사한다.
- **구조**: `conftest.py` (격리 픽스처) + DB/보안/스트레스/UI 테스트와 `test_ui_calendar_drag.py`, `test_ui_sticky.py`, `test_show_desktop_guard.py`
- **밝은 테마 고정**: `test_app_theme.py`는 Windows 다크(Qt 색 구성표 Dark + Fluent DARK)를 흉내 낸 뒤 고정 함수를 적용해 메인·설정·검색·휴지통·스티키·D-Day 만들기 창을 그리고, 처음부터 밝은 화면과 픽셀 차이 0.1% 미만인지 검사한다. Fluent만 또는 Qt만 고정한 반쪽 수정은 이 검사에서 실패한다. 실제 Windows 다크 설정에서의 EXE 확인은 수동으로 구분한다.
- **집중 목표·휴지통 색상**: `test_ui_focus.py`는 긴 목표가 기본/자세히 보기에서 토마토·닫기 버튼 앞에서 `…`로 줄고(앞 빈칸 없음) 전체 문구가 툴팁에 남는지, 짧은 목표는 그대로·툴팁 없음인지 실제 배치로 검사한다. `test_ui_focus_panel.py`는 긴 목표가 large 미니 카드의 최소 폭을 늘리지 않는지, `test_ui_trash.py`는 선택/비선택 행의 색상 칸 가운데 픽셀이 노트 색이고 칸 모서리는 표 바탕인지 검사한다.
- **선택 색·한글 표기**: `test_app_theme.py`는 테마 고정 뒤 팔레트 선택 색이 `#2563EB`/흰색인지와, 일정 편집·날짜·시간·금액 입력칸에서 전체 선택한 글자 바탕이 실제로 앱 파랑 픽셀로 그려지는지 검사한다(이 PC의 Windows 강조색은 청록이라 고치기 전에는 0픽셀). 시험 뒤 `setPalette(QPalette())`로 시스템 팔레트를 되돌린다. 두 미니앱 왼쪽 메뉴 머리글(`계산 종류`·`도구`)과 설정 `초기화` 버튼 글자도 검사한다.
- **미니앱 공용 창 틀**: `test_ui_mini_app_frame.py`는 다섯 미니앱 창마다 제목줄이 표면 맨 위 전체 폭·48px·`#23252B` 픽셀인지, 아이콘·제목·닫기 툴팁/접근 이름, 메뉴 앱의 메뉴 바탕(`#23252B`)과 메뉴 없는 앱의 본문(`#FDFDFB`) 픽셀, 제목줄 끌기 이동(화면 안 유지)과 닫기 버튼 Enter로 닫힘, 문서 변환에 보라 값이 남지 않음을 검사한다. 체크 색(`Accent`)은 `test_app_theme.py`가 본다.
- **보조 창 흰 카드·체크박스**: `test_ui_window_card.py`는 검색·휴지통 창이 `WindowCard`(흰 바탕 픽셀, 선 아이콘, 이모지 없는 제목)인지, 이전 노션풍 색이 남지 않았는지, 검색 처음·결과 없음에서 표 대신 안내 문구가 보이고 결과가 있으면 표가 보이는지 검사한다. `test_ui_mini_app_frame.py`의 체크박스 검사는 날짜·시간·문서 변환 체크박스가 체크 전 흰 상자, 체크 후 `#2563EB` 상자와 흰 체크 선인지 픽셀로 본다.
- **메인 화면 정돈(10·13·14번)**: `test_ui_main_tidy.py`는 빈 바로가기 칸이 첫 번째 하나만 `+ 추가`로 보이고 등록·삭제에 따라 바뀌는지, 여섯 칸이 다 차면 추가 칸이 없는지, 아이콘 32px·X는 마우스를 올렸을 때만 보이는지, 일정 줄 삭제 버튼이 마우스를 올린 줄·키보드로 고른 줄에만 보이고 글자 폭이 그대로인지, 날짜 머리줄의 음력·개수 회색과 공휴일 빨강을 실제 픽셀로 검사한다.
- **날짜 칸 개수(12번)**: `test_ui_calendar_count.py`는 색 수·일정 수 조합별 `+N` 표시와 일정 추가 때 실시간 갱신을 검사한다.
- **바로가기 기본값(2026-10-11)**: `test_sidebar_default.py`는 새 설치·초기화의 켜짐, 이미 있는 DB 값(켜짐/꺼짐) 유지, 설정 '기본 크기 바로가기' 이름이 116px 라벨 안에 들어가는지·툴팁을, `test_first_run.py`는 기본 크기 첫 실행 창 460px·사이드바 표시와 미리보기의 바로가기 열을 검사한다.

- **디자인 점검 11·15~21번**: `test_ui_calendar_move.py`(11번은 2026-10-11 J안 위치 편집으로 대체), `test_ui_calendar_cells.py`(중간·크게 숫자 왼쪽 위·오늘 원·고른 날 연한 회색(2026-10-11 되돌림)·요일 글자), `test_ui_right_column.py`(D-Day 이름 11px·한 줄 추가 칸·배경 버튼 아이콘), `test_ui_create_dialogs.py`(창 안 제목·D-day 미리보기·한국어 일요일 시작 달력·컨트롤 창 안), `test_ui_settings_data.py`(PIN 칸·저장 경로 한 줄·폴더 이름 남기는 말줄임), `test_ui_mini_apps.py`(주머니 이름 첫 줄 높이), `test_ui_mini_app_spacing.py`(날짜·시간 줄이 늘어나지 않음·문서 변환 빈 목록 안내·상태별 버튼). 문서 변환 좁은 화면 시험은 실패·완료 항목이 있어 버튼이 모두 보이는 상태로 잰다.
- **데이터 UI 수명**: `test_ui_data_lifecycle.py`는 실제 합성 `.enc` 가져오기 후 편집기·집중 타이머 유지, 최신 저장 실패/보호백업 실패 차단, 초기화 전 플로팅/미니 패널 타이머 폐기와 ID 재사용, PIN 잠금·보조 창·예약된 표시와 잠금 화면이 기본/크게 모드에서 창 전체를 불투명 배경으로 덮는지(픽셀)를 검사한다. `data`와 `full`에 포함한다. 이 검사는 실제 Windows 잠금/절전·Win+D 수동 확인을 대체하지 않는다.
- **일정 이모지**: `test_ui_schedule_emoji.py`는 16개 선택지·접두 치환 Undo·인라인 팝업 포커스·저장 실패 보류·잠금/트레이/초기화 뒤 콜백 무효화·모드별 표시/검색을 검사한다. `quick --tests tests/test_ui_schedule_emoji.py tests/test_edge_cases.py` 또는 `full`로 실행한다. `test_edge_cases.py`의 PIN `.enc` 왕복 검사는 기존 행·암호문·색상·설정·salt 보존을 포함한다. 하네스 실행 시 합성 UI PNG를 실행 폴더에 남기며, 이는 실제 한글 IME와 혼합 DPI/KVM 검증을 대신하지 않는다.
- **일정 시각·알림·반복·기간(v4.1)**: 순수 규칙 `test_schedule_rules.py`(시각 해석·검증·펼치기·월말/윤년·알림 시각·차선·문구), 저장 `test_schedule_storage.py`(v17 고정 DDL에서 마이그레이션 값 불변·멱등·중간 실패 되돌림·`schema_newer`·구 키 암호문·API·Export v3/Import v1~v3·반복 1,000개 시간 상한, data 프로필), 화면 `test_ui_schedule_options.py`·`test_ui_schedule_input.py`·`test_ui_schedule_list.py`·`test_ui_calendar_spans.py`·`test_ui_schedule_alarm.py`(가짜 시계). 100/125/150%는 `QT_SCALE_FACTOR`로 `quick --tests`를 따로 실행한다. 실제 시계의 알림·절전 복귀·PIN 잠금 중 카드·Win+D·다중 모니터 카드 위치·알림음은 수동 확인이다.
- **업데이트 안내(v4.1)**: `test_upgrade_notice.py`는 예전 형식(v17) DB를 올린 시작에서만 `on_upgrade`가 원래 버전으로 한 번 불리고 새 설치·이미 새 형식에서는 불리지 않는지, 안내 본문(이전 버전 차단 창 문구·이전 EXE와 바로가기 삭제·`backups` 사본), 부모 없는 맨 위 모달 `Dialog`가 [확인]만 두고 화면 안에 들어가며 DB 내용을 바꾸지 않는지, `smoke_release.py`가 같은 창 제목을 찾는지를 검사한다.
- **컬러 글리프 경계**: `test_emoji_rendering.py`는 스마일·다트·책·시계의 원본 ARGB 비트맵과 `QPainter` 텍스트 렌더의 경계를 비교한다. Qt 6.10.2에서 5건 실패하고 6.11.2에서 통과하는 Windows 글리프 캐시 회귀 검사다. 위 일정 UI 검사와 함께 `quick --tests`에 추가하거나 `full`/`release`로 실행하며 원본·렌더 PNG를 실행 폴더에 보존한다.
- **격리 전략**: `app_dir` 픽스처가 `security.APP_DIR`, `SALT_FILE`, `database.DB_FILE` 등을 `monkeypatch`로 `tmp_path`에 패치하고 Fernet 캐시 초기화. 테스트 간 DB/암호화 키 완전 격리.
- **스트레스 커버**: 1년×3색상 1,095개 일정, 365회 메모 upsert, 10KB 메모, Export/Import 왕복, 100회 추가/삭제 사이클, 백업 회전, VACUUM 무결성
- **리소스/빌드 커버**: 번들 Fluent UI System Icons 존재 여부, 일반 SVG tint, 컬러 SVG palette 보존, `build.spec` 리소스/라이선스/QtSvg 포함, 설정창 라이선스 고지를 검증한다.
- **v3.4 무손상 커버**: v16→v17 전후 schedule raw row exact snapshot, 팔레트 설정 Export/Import 왕복, canonical 3슬롯 유지, 음수 모니터 좌표 drag/clamp, 모든 크기에서 고정 상태(위치 편집 중이 아닐 때) 드래그 차단, 800×560 설정 최소 크기, sticky HTML/plain-text 불변, Win+D topmost pulse/데스크톱 레이어 재고정/hook 해제를 검증한다.
- **의존성**: `pytest`, `pytest-timeout` (`requirements.txt`에 포함)

```bash
python -m pytest tests/ -v
python -m pytest tests/test_stress.py -v --timeout=120   # 스트레스 테스트만
```

### v3.4 수동 릴리스 게이트

- Windows 11에서 `바탕화면 고정` ON → Win+D 후 메인/스티키/D-Day/집중 창이 남고 바탕화면 아이콘보다 위에 있는지 확인한다.
- 이어서 Explorer 폴더와 브라우저를 각각 활성화해 모든 일반 창이 기후노트 위에 표시되는지 확인한다.
- 바탕화면을 누른 뒤 Win+D, '바탕화면 보기' 버튼으로 각각 바탕화면을 보였다가 같은 키·버튼으로 되돌려, 되살아난 일반 창이 기후노트 위에 돌아오는지 확인한다(2026-10-25 이전에는 다른 창을 누를 때까지 기후노트가 위에 남았다). 바탕화면 아이콘 클릭에서 기후노트가 앞으로 튀어나오지 않는지도 함께 본다.
- 듀얼 모니터(좌측 음수 좌표 포함)로 캘린더를 드래그한 뒤 재시작·크기 변경·모니터 분리 시 작업 영역 안에 복원되는지 확인한다.

### 테스트 추가 기준

암호 라이브러리 갱신은 `quick --tests tests/test_crypto_compat.py tests/test_security.py tests/test_data_safety.py tests/test_packaging.py`로 고정 기준을 확인한 뒤 `release`로 전체 검사·빌드·격리 EXE 실행을 수행한다. `tests/fixtures/crypto_compat_cryptography46.json`은 구버전 46.0.4가 만든 합성 기준이며 재생성하지 않는다. 하드웨어/레거시/PIN 키 파생과 기존 토큰 복호화, 실제 `security.decrypt`/`legacy_decrypt` 경로를 포함한다.

별도 구버전 환경에서도 새 합성 DB·백업·PIN 파일을 읽고, 새 환경에서 구버전 기준본을 읽어야 한다. PIN은 실제 가져오기→재내보내기와 기존 메모/바로가기 보존·집중 ID remap을, 백업은 별도 폴더 복구 후 전체 암호문을 검사한다. 원본 보존 사본의 파일 해시를 전후 대조한다. EXE도 양방향으로 합성 데이터 사본에서 시작하며, Job 정리 실행을 정상 종료 저장 검증으로 기록하지 않는다. 구버전 검증 환경에는 스모크 helper의 `defusedxml` 의존성도 필요하다. 정확한 실행 ID·도구·EXE 해시는 [2단계 기록](work/2026-10-05-push-security-scan-step2.md)을 따른다.

데이터 변경이 수반되는 기능은 반드시 왕복 검증 테스트를 추가한다:
- DB 스키마 변경 → migrate 전후 데이터 보존 확인
- 신규 필드/설정 → 기본값 fallback 동작 확인
- Export/Import → 왕복 후 동일 데이터 확인

---

## Security Audit (CODEMIND) 이력

- **점검 도구**: 행안부 CODEMIND 4.5 (정적 분석)
- **점검 결과**: 72건 탐지 → 코드 수정 + 반론서 대응 (v2.0 → v2.1)

| # | 카테고리 | CWE | 규칙코드 | 대상 파일 | 대응 |
|---|---|---|---|---|---|
| 1 | 부적절한 인가 | CWE-285 | 0011_IMPRAUTH | ui_dday.py, ui_main.py, ui_sticky.py | 반론 (데스크톱 앱 특성상 웹 RBAC 비해당, PIN 잠금 + 하드웨어 암호화 이미 구현) |
| 2 | 솔트 없이 일방향 해쉬 함수 사용 | CWE-759 | 001D_ONEWAYHASH | security.py | 반론 (SHA-256은 키 재료 생성용, 실제 KDF는 PBKDF2HMAC 200K + 32B Salt로 CODEMIND 권장 초과) |
| 3 | 오류 상황 대응 부재 | CWE-390 | 0023_NOACTION | database.py, ui_main.py, ui_settings.py, ui_sticky.py | 코드 수정 |
| 4 | 부적절한 예외 처리 | CWE-754 | 0024_NOCHKERR | build_app.py, database.py, fetch_data.py, main.py, security.py, ui_dday.py, ui_main.py, ui_settings.py, ui_sticky.py | 코드 수정 |
| 5 | 부적절한 자원 해제 | CWE-404/772 | 0026_RESLEAK | main.py | 코드 수정 |

- **반론서 · 보고서**: 기관 내부 문서이므로 저장소에 포함하지 않는다. 담당자가 저장소 외부에서 별도 보관한다.
- **코딩 규칙**: [`docs/CODING_STANDARDS.md`](CODING_STANDARDS.md)
