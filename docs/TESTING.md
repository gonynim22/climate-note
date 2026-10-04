# Testing & Security Audit Reference

## 개발 하네스 — 다음 버전부터의 기본 경로

Windows / Python 3.13과 `requirements-lock.txt`의 직접 의존성 9개를 사용한다. HWP 변환 후속에서 기존 lock의 `pywin32==311`을 직접 의존성으로 명시했으며 버전 업그레이드는 없다.
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
| `data` | DB·암호화·건강 검사·백업·Import/Export·스티키 저장·메인 UI·스트레스 | 데이터 또는 저장/보기 전환 변경 |
| `full` | 전체 pytest 1회 | 공통 실행기·격리 변경, 기능 마무리 |
| `release` | 전체 pytest 1회 → 새 EXE 빌드 → 격리 실행 3개 시나리오 | 배포 산출물 검증 |

`data`는 저장 계약 검사가 들어 있는 `test_ui.py`도 포함하므로 짧은 단위 테스트 묶음이 아니다.
정확한 대상은 `tools/verify.py`의 `QUICK_TESTS`·`DATA_TESTS`가 정본이다.
`quick --tests`는 기본 회귀를 유지하면서 `tests/` 안의 파일 또는 `파일::테스트`를 추가한다.
대상이 없는 경우, 수집 오류, 0건 수집, 전부 skip은 통과가 아니다.
`full`/`release` 실행 전에 `quick`/`data`를 의무적으로 중복 실행하지 않는다.

캘린더 열 너비 변경은 `tests/test_ui_calendar_columns.py`를 포함한다. 창이 화면 안에 들어오는지만 확인해서는 요일 열 축소를 검출하지 못한다. 이 검사는 세로 논리 작업 영역(1080×1920, 864×1536, 720×1280)과 medium/compact에서 실제 날짜 열·요일 제목의 배치를 검사한다. `QT_SCALE_FACTOR=1.25`/`1.5`의 별도 실행은 합성 배율 확인이며 실제 혼합 DPI/KVM 수동 확인을 대신하지 않는다.

날짜·시간 계산기는 `tests/test_date_time_calculator.py`, `tests/test_ui_date_time_calculator.py`, `tests/test_date_time_integration.py`, `tests/test_ui_mini_apps.py`를 함께 검사한다. 초 보존/분 복사 정책·월말/윤년/역순·공휴일 범위/중복 제외·합산 행과 최근 복원·두 앱의 독립 수명·저장 실패/초기화 성공/실패·DB/Export/salt 불변을 포함한다. UI에는 스크롤 영역을 두지 않는다. 날짜 포함/날짜만/합산 종류와 오류 상태에서 입력·결과·복사·최근의 가로/세로 경계를 확인한다. 합산 이전/다음·24개 상한·숨긴 항목 오류/포커스 보존·종류별 선택과 최근 복원을 검사한다. `QT_SCALE_FACTOR=1.25`/`1.5`의 합성 배율은 실제 혼합 DPI/KVM 확인을 대체하지 않는다. 상세 기준은 [날짜·시간 계약](DATE_TIME_CALCULATION.md)을 따른다.

금액·숫자 표기 도우미는 `tests/test_money_notation.py`, `tests/test_ui_money_notation.py`, `tests/test_money_notation_integration.py`, `tests/test_ui_mini_apps.py`, `tests/test_mini_app_icons.py`를 함께 검사한다. 순수 계산은 시행규칙 예시·경계와 별도 참조 구현(결정적 난수 2만 건)을 대조하고 입력 거부·사사오입 경계·`Decimal` 정확도를 확인한다. UI는 세 모드×정상/오류/최장 입력×1000×900·480×500·420×500 작업 영역에서 스크롤·잘림이 없는지, 복사 형식·최근 기록·키보드를 검사한다. 통합은 세 앱의 독립 세션과 9개 수명 지점, DB/Export/salt 불변을 검사한다. `QT_SCALE_FACTOR=1.25`/`1.5`의 합성 배율은 실제 혼합 DPI/KVM 확인을 대체하지 않는다. 상세 기준은 [금액·숫자 표기 계약](MONEY_NOTATION.md)을 따른다.

### 실행 격리와 증거

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

보고서에는 검사 전후 소스·빌드 설정·테스트·개발 지침의 SHA-256을 기록한다.
미추적 코드도 포함하고 `.env`, 내부 `security/`, 사용자 데이터·가상환경·빌드 출력은 제외한다.
진행 기록인 `docs/work/`·`docs/superpowers/`도 제외한다. 검사 중 코드가 달라지면
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
잘못 포함시킨 사례가 있었다(v3.8c 최초 release). EXE 검사는 `build/build/Analysis-00.toc`의
바이너리 출처 경로를 대조해 이런 제3자 DLL 혼입을 찾아낸다.

1. 신규 설치: 빈 AppData → 응답하는 창 → 현재 schema·SQLite 무결성·32바이트 salt·유효한 일일 `.cnbak`·오류 로그 확인.
2. 기존 데이터: 현재 저장 계약의 합성 일정·메모·열린/휴지통 스티키·D-Day·집중/세션·바로가기·설정 → 실행 전후 raw/복호화 내용 해시·ID·salt 불변과 최초 보호백업 확인.
3. 시작 차단: 합성 DB의 salt 손상 → 데이터 보호 오류창만 표시 → 원본 DB·salt·기존 보호백업 해시 불변 확인.

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
| 라이선스·SBOM·Qt 고지·서명 후속 과제 | 미확인 | [보류 기록](RELEASE_HISTORY.md) |

최종 배포 판단 / 근거: `<별도 기입>`

## Test Suite

- **KVM 위치 왕복(v3.8 후속)**: `test_ui_kvm_position.py`는 원래 조사 재현 파일을 정식 회귀로 승격했다. 세 크기의 자유/모서리·이동 ON/OFF, 분리→재연결, 화면 목록 순서/객체/원점 변경, 재실행, 임시 논리 크기, 없는/모호한 장치, 설정창 열린 중 순서 변경/저장 실패, 초기화, DPI 신호와 드래그 취소, 스티키/D-Day/집중 위치 및 DB dump/Export/salt 보존, PIN Export/Import 왕복을 검사한다. `quick --tests tests/test_ui_kvm_position.py tests/test_ui_screen_change.py tests/test_ui_calendar_drag.py tests/test_ui_calendar_move.py tests/test_ui.py` 또는 `full`/`release`로 실행한다. 합성 QScreen 목록과 숨겨진 실제 Qt 창을 사용하므로 회사 KVM 이벤트 순서·실제 혼합 DPI/Win+D 실기 검증은 별도다.

- **단위 환산기(v3.8a)**: `test_unit_converter.py`는 182개 항목의 독립 기준값·모든 단위 쌍 왕복·경계·오류 입력·표시·기록·반복 교환을 검사한다. `test_ui_unit_converter.py`는 실제 입력/단위 목록/키보드/주머니 실행·재사용·잠금/트레이/사이드바/초기화 성공·실패/종료 보류·모니터 보정·DB 전체 dump/Export/salt 보존과 합성 PNG를 확인한다. ppm의 몰/질량분율 구분·0/100% 경계·밀도 없는 ppm↔mg/L 차단, 440×580 내용/488×628 외곽 배치·실제 반투명 그림자/모서리 잘림·그림자 여백 클릭 후 계산 상태 보존·28px 행/0px 간격/큰 글꼴의 모든 분류 이름/기호 배치·작은 화면 스크롤과 기본 크기 복원도 검사한다. 주머니·일정 이모지·데이터 수명 회귀를 함께 실행한다. 125/150%는 별도 프로세스의 합성 배율이다. 실제 EXE에서 주머니→환산→닫기도 격리 데이터로 확인하고 기존 3개 smoke 시나리오와 구분한다. [계수 정본](UNIT_CONVERSION.md), [확대·환경 단위 기록](work/2026-09-21-mini-app-environment.md), [현재 그림자·가독성 기록](work/2026-09-23-unit-converter-shadow.md).

- **조건 계산 회귀(v3.8a)**: 물/직접 밀도·기체 물질/온도/절대압·온도차의 독립 기준값과 역환산, 미선택/빈 값/음수/비유한 값·100% 경계를 검사한다. UI에서는 실제 입력·근사 표시·다른 단위·교환·조건별 기록 복원/중복 구분·기록 겹침/잘림·기체 팝업 잠금 정리·340×400 조건 접근성을 검사한다. DB dump/Export/salt 보존 시나리오에도 새 계산 조건을 포함한다. 125/150% 합성 배율과 신규 release/번들 대조는 [현재 기록](work/2026-09-23-v3.8a-water-conversion-plan.md)에 남긴다.

- **환산기 드롭다운**: `test_ui_unit_converter.py`는 FROM/TO·물질·온도 모드를 실제 클릭한 직후 실제 목록이 표시되고 임시 `QRollEffect`가 생성되지 않는지 검사한다. 전역 콤보 효과 ON/OFF 보존, 선택·Alt+Down/Esc·숨김, 동일 높이/화살표 픽셀·읽을 수 있는 목록 행, 팝업 예외 후 효과 복원을 포함한다. 최종 표시만 기다리면 150ms 중간 이미지 회귀를 놓친다. 선택 클릭은 native 커서 이동과 Qt의 최초 release 보호 시간을 고려한다. 125/150% 및 새 EXE 증거는 [현재 기록](work/2026-09-24-unit-converter-dropdown-fix.md)을 따른다.
- **미니앱 주머니**: `test_ui_mini_apps.py`는 세 크기/짧은 화면의 6슬롯 접근·252×280px 본체/그림자 포함 300×328px 창/104×100px 타일 4칸·SVG 아이콘 로드·머리부 앱 개수·사이드바 버튼 스타일·반투명 그림자와 모서리 잘림·예정 타일 클릭/Tab 차단·실제 앱의 예정 자리 대체와 2열/세로 스크롤·실제 클릭/키보드/반복 열기·그림자 여백 닫기·음수 좌표 모니터 위치 보정·일정 저장 실패 게이트·잠금/트레이/보기 전환 취소·기존 DB 전체 dump/Export/바로가기/salt 불변을 검사한다. 미니앱/환산기 DB 비교는 기동 시 예약된 스티키 크기 스냅 저장 완료 후 기준 snapshot을 잡고 조작 구간의 전체 raw 불변을 확인한다. 기존 `test_ui.py`의 바로가기 등록/관리/드롭과 `test_ui_data_lifecycle.py`·`test_ui_schedule_emoji.py`의 수명 회귀를 함께 실행한다. 합성 PNG와 실제 EXE 자동 smoke·실제 혼합 DPI/KVM 수동 확인을 구분한다. [현재 주머니 기록](work/2026-09-27-v3.8c-money-notation-pocket.md).
- **미니앱 아이콘**: `test_mini_app_icons.py`는 `resources/icons/mini_apps/*.svg`가 텍스트·이미지·필터·마스크·CSS·외부 참조 없는 QtSvg Tiny 파일인지 검사한다. 48px의 100/125/150% 렌더에서 둥근 모서리 투명·그라데이션 양 끝 색·가운데 흰 선, 날짜·시간 시계 면, 준비 중 점선, 런처 강조색을 확인한다.

- **이동 토글·스마일**: `test_ui_calendar_move.py`는 세 크기 실제 마우스 드래그·Tab/Space/Enter·설정 저장 실패·Import/초기화·잠금/트레이 취소·기본 380px 헤더를 검사한다. `test_ui_calendar_drag.py`는 OFF 차단·화면 간 크기/위치 보정을, `test_ui_schedule_emoji.py`는 색상 원과 스마일의 실제 렌더 외경/중심·선택/Undo를 검사한다. 관련 `quick --tests` 또는 `release`에서 합성 PNG를 남기며 실제 혼합 DPI/KVM 수동 검증을 대신하지 않는다.

- **스티키 파일 링크(v3.7b)**: `test_sticky_file_links.py`의 Qt href/밑줄 메타데이터 왕복·경로 검사, `test_ui_sticky_file_links.py`의 서식·Undo·체크박스·두 보기·외부 실행 가로채기·주의 표시 무변경·8개 기존 테이블 raw/salt 보존, `test_ui_data_lifecycle.py`의 최신 링크 Export/실패·잠금/트레이/폐기/보기 전환 취소를 검사한다. 하네스 실행에는 `sticky-file-links.png` 합성 UI 캡처를 남긴다. 실제 파일 드롭·IME·기본 프로그램·혼합 DPI/KVM은 별도 수동 확인이다.

- **Location**: `tests/` (pytest 기반 전체 테스트)
- **바로가기 대화상자(v3.8d)**: `tests/test_ui_shortcut_dialogs.py`와 기존 `tests/test_ui.py`를 검사한다. `shortcut_dialog_probe.py`는 별도 Job/합성 AppData에서 실제 메뉴 클릭과 Qt 파일/폴더/이름 변경/경로 재지정 대화상자의 확인·취소를 실행한다. 클릭 처리 중 대화상자가 열리지 않는지, 메뉴가 폐기되는지, 기존 데이터·salt·다른 슬롯이 보존되는지 확인한다. native 선택창은 별도 격리 재현으로 검사하고 회사 PC/실제 사용자 입력·KVM 확인과 구분한다. 예약 호출은 슬롯/부모 숨김·비활성·잠금/트레이·재조회·폐기를 검사한다.
- **구조**: `conftest.py` (격리 픽스처) + DB/보안/스트레스/UI 테스트와 `test_ui_calendar_drag.py`, `test_ui_sticky.py`, `test_show_desktop_guard.py`
- **데이터 UI 수명**: `test_ui_data_lifecycle.py`는 실제 합성 `.enc` 가져오기 후 편집기·집중 타이머 유지, 최신 저장 실패/보호백업 실패 차단, 초기화 전 플로팅/미니 패널 타이머 폐기와 ID 재사용, PIN 잠금·보조 창·예약된 표시를 검사한다. `data`와 `full`에 포함한다. 이 검사는 실제 Windows 잠금/절전·Win+D 수동 확인을 대체하지 않는다.
- **일정 이모지**: `test_ui_schedule_emoji.py`는 16개 선택지·접두 치환 Undo·인라인 팝업 포커스·저장 실패 보류·잠금/트레이/초기화 뒤 콜백 무효화·모드별 표시/검색을 검사한다. `quick --tests tests/test_ui_schedule_emoji.py tests/test_edge_cases.py` 또는 `full`로 실행한다. `test_edge_cases.py`의 PIN `.enc` 왕복 검사는 기존 행·암호문·색상·설정·salt 보존을 포함한다. 하네스 실행 시 합성 UI PNG를 실행 폴더에 남기며, 이는 실제 한글 IME와 혼합 DPI/KVM 검증을 대신하지 않는다.
- **컬러 글리프 경계**: `test_emoji_rendering.py`는 스마일·다트·책·시계의 원본 ARGB 비트맵과 `QPainter` 텍스트 렌더의 경계를 비교한다. Qt 6.10.2에서 5건 실패하고 6.11.2에서 통과하는 Windows 글리프 캐시 회귀 검사다. 위 일정 UI 검사와 함께 `quick --tests`에 추가하거나 `full`/`release`로 실행하며 원본·렌더 PNG를 실행 폴더에 보존한다.
- **격리 전략**: `app_dir` 픽스처가 `security.APP_DIR`, `SALT_FILE`, `database.DB_FILE` 등을 `monkeypatch`로 `tmp_path`에 패치하고 Fernet 캐시 초기화. 테스트 간 DB/암호화 키 완전 격리.
- **스트레스 커버**: 1년×3색상 1,095개 일정, 365회 메모 upsert, 10KB 메모, Export/Import 왕복, 100회 추가/삭제 사이클, 백업 회전, VACUUM 무결성
- **리소스/빌드 커버**: 번들 Fluent UI System Icons 존재 여부, 일반 SVG tint, 컬러 SVG palette 보존, `build.spec` 리소스/라이선스/QtSvg 포함, 설정창 라이선스 고지를 검증한다.
- **v3.4 무손상 커버**: v16→v17 전후 schedule raw row exact snapshot, 팔레트 설정 Export/Import 왕복, canonical 3슬롯 유지, 음수 모니터 좌표 drag/clamp, 모든 크기에서 이동 토글 OFF 시 드래그 차단, 800×560 설정 최소 크기, sticky HTML/plain-text 불변, Win+D topmost pulse/데스크톱 레이어 재고정/hook 해제를 검증한다.
- **의존성**: `pytest`, `pytest-timeout` (`requirements.txt`에 포함)

```bash
python -m pytest tests/ -v
python -m pytest tests/test_stress.py -v --timeout=120   # 스트레스 테스트만
```

### v3.4 수동 릴리스 게이트

- Windows 11에서 `바탕화면 고정` ON → Win+D 후 메인/스티키/D-Day/집중 창이 남고 바탕화면 아이콘보다 위에 있는지 확인한다.
- 이어서 Explorer 폴더와 브라우저를 각각 활성화해 모든 일반 창이 기후노트 위에 표시되는지 확인한다.
- 듀얼 모니터(좌측 음수 좌표 포함)로 캘린더를 드래그한 뒤 재시작·크기 변경·모니터 분리 시 작업 영역 안에 복원되는지 확인한다.

### 테스트 추가 기준

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
