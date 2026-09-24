# AGENTS.md

기후노트 개발 지침의 정본입니다. `CLAUDE.md`는 이 파일의 안내 포인터입니다.
앱 표시 버전·출시일·EXE 이름은 `app_info.py`, DB 버전은 `database.CURRENT_SCHEMA_VERSION`을 기준으로 합니다.

## 다음 버전부터의 개발 절차

1. 변경할 파일과 사용자 데이터에 미치는 영향을 확인한다. 기존 사용자 변경은 보존한다.
2. 아래 표의 관련 문서를 읽는다. 상세 계약도 이 지침의 일부이며 영구 결정은 해당 정본 문서에 반영한다.
3. 여러 단계 작업은 [작업 기록 양식](docs/templates/WORK_NOTE.md)을 `docs/work/<날짜>-<주제>.md`로 만들어 목표·완료 조건·진행 상태를 기록한다. 작은 문구 수정에는 요구하지 않는다.
4. 작업에 맞는 하네스 명령으로 검증한다. 실패·미실행·수동 확인을 구분하고, 실제 결과의 `summary.md`와 실행 ID를 남긴다.
5. 검증 뒤 코드가 바뀌면 관련 검사를 다시 실행한다. 과거 테스트 수나 다른 입력의 보고서를 현재 통과 근거로 쓰지 않는다.

| 작업 | 먼저 읽을 문서 |
|---|---|
| DB·암호화·백업·가져오기·종료 저장 | [아키텍처와 데이터 계약](docs/ARCHITECTURE.md), [보안 코딩](docs/CODING_STANDARDS.md), [검증](docs/TESTING.md) |
| 캘린더·설정·위젯·폰트·Win32 | [UI 계약](docs/UI_PATTERNS.md), [아키텍처](docs/ARCHITECTURE.md), [검증](docs/TESTING.md) |
| 빌드·리소스·의존성·배포 | [검증](docs/TESTING.md), [아키텍처](docs/ARCHITECTURE.md), [릴리스 이력과 보류 과제](docs/RELEASE_HISTORY.md) |
| 개발 도구·테스트 격리 | [검증](docs/TESTING.md) |

## 명령

프로젝트 루트 PowerShell에서 같은 Python 3.13 가상환경을 사용한다.

```powershell
.\.venv\Scripts\python.exe tools/verify.py doctor
.\.venv\Scripts\python.exe tools/verify.py quick
.\.venv\Scripts\python.exe tools/verify.py quick --tests tests/test_ui_sticky.py tests/test_ui_sticky_panel.py
.\.venv\Scripts\python.exe tools/verify.py data
.\.venv\Scripts\python.exe tools/verify.py full
.\.venv\Scripts\python.exe tools/verify.py release
```

- UI 변경은 `quick --tests <관련 파일>`, 데이터·스티키 저장 변경은 `data`, 공용 실행기·테스트 격리 변경은 `full`로 검증한다. 배포 산출물은 `release`로 검증한다.
- `full`에 하위 검사를 중복 실행하지 않는다. 문서만 고쳤으면 링크·사실·지침 유실을 확인한다.
- 출력은 `output/harness/<run-id>/`에 보존한다. 자동 검사 통과는 배포 승인이 아니다. Win+D·혼합 DPI·KVM·최종 UI 확인은 [수동 검사](docs/TESTING.md)에 남긴다.
- 앱 실행은 `python main.py`, 일반 빌드는 `.\.venv\Scripts\python.exe build_app.py` 또는 `build.bat`, 직접 전체 검사는 `python -m pytest tests -q`도 지원한다. 의존성 재현은 같은 가상환경에서 `pip install -r requirements-lock.txt`로 한다. 하네스와 일반 빌드는 패키지를 자동 설치하거나 lock을 갱신하지 않는다.
- `build.bat`은 작업 디렉터리와 무관하게 프로젝트 `.venv` Python을 실행한다. `build_app.py`는 `tools.verify.doctor()` 사전검사 후 같은 인터프리터의 PyInstaller를 `--clean`으로 실행하며, 환경 불일치·빌드 실패는 비영 종료한다. 전역 Python이나 이전 빌드 캐시의 구형 Qt가 다시 포함되지 않도록 이 경로를 유지한다.

## 핵심 개발 원칙

> **기존 사용자 데이터는 반드시 그대로 보존되어야 한다.**

- 스키마 변경: `ALTER TABLE ... ADD COLUMN`만 허용. DROP/RECREATE 금지. `migrate()` 버전 번호 올리기.
- 마이그레이션: 멱등성 보장 (`IF NOT EXISTS` 또는 `try/except sqlite3.OperationalError`).
- 암호화 변경: 기존 데이터 복호화 → 재암호화 경로 제공. 자동 삭제 금지.
- 설정 변경: 기존 `app_settings` 키 삭제 금지. 새 키 추가 + 기본값 fallback 처리.
- 데이터 변경 기능 추가 시: `tests/`에 왕복 검증 테스트 필수.

## 반드시 보존할 계약

- 망 전환/KVM 후 위치 복원은 기본·중간·크게에 동일하게 적용한다. 화면 부재·해상도/DPI 변경의 임시 보정 좌표를 캘린더·스티키·D-Day·집중의 원래 저장 좌표에 덮어쓰지 않는다. 새 `calendar_screen` v1 JSON(이름·serial·제조사·모델·작업 영역 원점)은 명시적 드래그·모니터/모서리 선택 때만 기존 인덱스·전역 x/y와 한 트랜잭션으로 저장한다. 대상 장치가 없거나 모호하면 기본 화면에 임시 표시하며 선호 정보를 유지한다. 구형 설정은 메모리 fallback, Import/초기화는 캐시 재조회, 같은 화면의 원점 변경은 상대 위치 보정을 적용한다. 설정창이 열린 동안의 목록 재정렬·장치 부재·저장 실패와 세 크기 왕복을 검증한다. DB v17·Export v2·salt·기존 본문은 유지하며 상세 계약과 검증은 [아키텍처](docs/ARCHITECTURE.md), [UI 계약](docs/UI_PATTERNS.md), [복원 개선 기록](docs/work/2026-09-22-kvm-window-position-fix.md)을 따른다.
- 단위 환산기(v3.8a 계산 기준)는 첫 번째 개발자 제공 미니앱이며 [단위 계약](docs/UNIT_CONVERSION.md)의 25분류·182항목을 사용한다. 미니앱 주머니 본체는 240×280px(그림자 여백 포함 288×328px), 92px 정사각형 타일 2×2이며 환산기는 내용 440×580px/그림자 포함 기본 488×628px다. 왼쪽 분류는 132px 폭, 28px 행/0px 간격, 이름 13px/기호 12px를 사용하며 좁은 화면에서는 내용 최소 너비를 먼저 확보하고 그림자 여백/blur를 줄인다. 환산기 생성 이미지·날짜/시간 계산기 SVG와 비활성 `곧 출시 예정` 타일 2개를 배치한다. ppm의 몰/질량분율과 수질 질량/부피 기준을 구분하고 수질은 명시적 용액 밀도(기본 물 기준 1kg/L), 기체는 선택 물질의 몰질량·온도·절대압으로만 교차 환산한다. 물 기준/이상기체 가정은 ≈로 표시하고 온도값/온도차 모드를 구분한다. 조건과 모드는 최근 기록의 중복 판정·복원에 포함하며 원본 숫자에 표시 기호를 섞지 않는다. 추정 배출량·건강위험·신발 치수 환산과 외부 코드 로더는 제외한다. 입력·최근 12개·창 상태는 메모리 전용으로 DB v17·Export v2·salt·설정 키·바로가기 6슬롯을 유지한다. 잠금/트레이/사이드바 숨김은 소유 팝업까지 정리하며, 초기화 성공 신호에서만 기록을 폐기한다. 계산 기준은 [확대·환경 단위 기록](docs/work/2026-09-21-mini-app-environment.md), 주머니 UI 검증은 [주머니 개선 기록](docs/work/2026-09-23-mini-app-pocket-redesign.md), 최신 환산기 UI·배율·EXE 검증은 [그림자·가독성 기록](docs/work/2026-09-23-unit-converter-shadow.md)을 따른다. v3.8a 정의·배율·빌드 검증은 [현재 작업 기록](docs/work/2026-09-23-v3.8a-water-conversion-plan.md)을 따른다.
- 환산기 FROM/TO·물질·온도 모드는 `ui_converter_combo.ConverterCombo`의 28px 높이·13px 글꼴·벡터 테두리/화살표·공통 목록 표현을 사용한다. FROM/TO의 닫힌 기호와 열린 전체 단위 정의는 유지한다. Qt 기본 roll 효과는 팝업을 여는 동기 호출에만 억제하고 `finally`에서 이전 전역 효과 설정을 복원한다. 클릭 직후 실제 목록 표시·임시 이미지 미생성·선택/Esc/잠금/숨김·합성 배율을 검사하며 계산·조건·기록·DB/설정은 바꾸지 않는다. 상세 계약은 [UI 계약](docs/UI_PATTERNS.md), 최신 검증/EXE는 [드롭다운 수정 기록](docs/work/2026-09-24-unit-converter-dropdown-fix.md)을 따른다.
- 날짜·시간 계산기(v3.8b)는 두 번째 미니앱으로 [날짜·시간 계약](docs/DATE_TIME_CALCULATION.md)을 따른다. A안 108px 왼쪽 메뉴·내용 480×620px/기본 외곽 528×668px이며 날짜 입력을 두 열로 정리하고 입력·결과·복사·최근 기록을 스크롤 없이 표시한다. 합산은 한 항목씩 이전/다음으로 전환하며 숨긴 항목까지 합산·검증한다. 낮은 화면은 여백을 압축하고 보조 주석을 툴팁으로 제공한다. 시간 차이/날짜 연산/근무일/기간·구간 합산을 제공한다. 원본은 정수 초, 년·월은 달력 기준 한 번 이동 후 월말 보정, 휴게는 수동 공제, 초는 임의 절삭하지 않는다. 공휴일 자료 밖에서는 제외 결과를 보류하고 명시적으로 끈 경우만 선택 요일을 제외한다. 입력·최근 12개·합산 종류별 행·창 상태는 메모리 전용, 24행 상한이며 DB v17·Export v2·salt·기존 설정·바로가기 6슬롯을 유지한다. 메인이 단일 창을 재사용하고 일정 저장 게이트·잠금/숨김 팝업 취소·초기화 성공 후 폐기를 적용한다. 최초 계산/통합 검증은 [v3.8b 기록](docs/work/2026-09-24-v3.8b-date-time-calculator.md), 최신 UI/배율/EXE 검증은 [스크롤 제거 기록](docs/work/2026-09-24-date-time-no-scroll.md)을 따른다.
- 런타임은 오프라인 전용이다. AI 법령검색·업데이트 안내의 브라우저 URL 열기만 예외다. `wmux` 명령은 사용하지 않는다.
- DB 연결은 `database._connection()`, 파일은 `with open`, 민감 본문 암호화는 `security.py`를 사용한다. `bare except`와 이유·처리 없는 `except/pass`는 금지한다.
- 시작 전 read-only 건강 검사와 보호백업 실패 시 원본을 유지하고 시작을 중단한다. 암호문이 있는 데이터셋의 salt를 새로 만들지 않는다.
- 자동백업은 WAL-safe DB snapshot·원본 salt·검증 manifest의 `.cnbak`이다. 당일 정상본은 덮어쓰지 않고 정상 일일 묶음만 5일 보존한다. 구형 DB 백업·마이그레이션 전·가져오기 전·초기화 전 보호본은 회전 삭제하지 않는다.
- PC 이동은 PIN `.enc`를 사용한다. Import는 전체 사전검증 후 한 트랜잭션으로 병합하며 기존 메모·사용 중인 바로가기를 보존하고 집중 세션 ID를 remap한다. `privacy_pin`은 Export/Import에서 제외한다.
- 스티키 종료·휴지통 이동·보기 전환은 최신 원본 저장 성공 후 진행한다. `large`에서는 미니 패널이 최신 원본이며, 숨긴 플로팅 내용으로 역덮어쓰지 않는다. 저장 실패는 종료/전환 보류와 재시도로 처리한다.
- 스티키 파일 링크는 기존 암호화 HTML의 버전 있는 내부 href에 경로·연결 환경·개별 ID·원래 밑줄만 보존한다. DB v17·Export v2·salt·설정 키·기존 메모를 일괄 변환하지 않는다. B+C 파일 라벨(옅은 배경·둥근 테두리·파일 종류 배지)과 끊김 점선/주의 아이콘은 화면 전용이며 본문·복사·Undo·저장을 바꾸지 않는다. 체크박스와 링크는 하나의 표시용 highlighter를 공유하고, 배지나 경고 문자를 문서에 삽입하지 않는다. 다른 PC는 같은 경로가 있어도 재선택 전에는 열지 않는다. 비동기 검사·파일창·메뉴는 문서 변경/잠금/숨김/폐기 때 무효화하며 외부 파일 열기는 명시적 동작과 현재 UI 수명 확인 후에만 수행한다. 상세 범위는 [UI 계약](docs/UI_PATTERNS.md)과 [데이터 계약](docs/ARCHITECTURE.md)을 따른다.
- Export도 PIN 확인 후 `_prepare_data_change()`로 진행 중 일정·현재 모드 최신 스티키 저장을 확정한 뒤 snapshot을 읽는다. 저장 실패 시 파일 선택·출력 생성/교체를 시작하지 않는다.
- 스티키 연결 버튼은 체인 모양의 번들 `link.svg`를 사용하며 주변 서식 QPushButton과 같은 테두리·배경·크기와 `NoFocus`를 유지한다. 선택한 텍스트 범위는 파일창을 열기 전에 복사해 고정하고, 선택 파일명으로 문구를 대체하지 않는다. 플로팅·large 패널의 실제 마우스 드래그→버튼→파일창 수락/취소·Undo를 검증한다.
- 가져오기는 진행 중인 일정 편집 저장 → 최신 스티키 저장 성공 후 보호백업·병합한다. 이미 열린 같은 ID의 편집기·집중 타이머는 재사용하고 `large` 패널 목록도 갱신한다.
- 초기화는 최신 저장 → 보호백업 성공 → 이전 플로팅·패널의 모든 타이머 정지와 가드 해제·객체 폐기 → DB/salt 초기화 순서다. 초기화 시도 후 실패해도 현재 DB에서 UI를 복원하며, 폐기한 객체가 새 DB에 쓰거나 다시 표시되지 않게 한다.
- PIN 잠금은 트레이 복원·지연된 위젯 표시·설정·검색·휴지통에도 적용한다. 보조 창은 숨김·비활성화하고 활성 모달/팝업은 취소한다. 잠금 중 집중 완료는 기록하되 휴식 팝업을 표시하지 않는다.
- 일정 canonical 3슬롯과 체크박스 HTML/문자 표식은 저장 호환 계약이다. 표시색·벡터 디자인 때문에 저장값을 일괄 변경하지 않는다.
- 일정 이모지는 기존 `schedules.content`의 `이모지 + ASCII 공백 한 칸` 접두 문자열로 저장한다. `ui_schedule_emoji.py`의 알려진 표식 하나만 명시적 선택으로 교체·제거하며 본문 Unicode·색상·DB v17·Export v2·salt를 유지한다. 별도 컬럼·설정 키·기존 행 일괄 갱신은 추가하지 않는다.
- 일정 인라인 편집은 입력창·이모지 버튼·팝업을 하나의 편집 영역으로 다룬다. 저장 실패 시 편집 원본을 유지하고 날짜/월/검색 이동·목록 재생성·데이터 작업·정상 종료를 보류한다. 잠금·트레이 숨김·초기화 때 팝업과 예약된 포커스 복원을 취소한다. 키보드 검사는 실제 포커스된 버튼으로 입력하며 상세 동작은 [UI 계약](docs/UI_PATTERNS.md)을 따른다.
- 미니앱 버튼은 사이드바 최상단 64×48px, 기존 바로가기 배열/DB ID 1~6과 64px 버튼은 유지한다. 80px 사이드바에서 짧은 화면은 목록만 스크롤한다. 주머니는 DB 접근/새 설정 없는 개발자 제공 앱용 실행 타일 팝업이며 열림 상태를 저장하지 않는다. 그림자와 제목 배경으로 경계를 구분하고 그림자 여백 클릭도 닫기로 처리하며 원래 버튼에 재전달하지 않는다. 예정 타일 2개는 클릭·키보드 실행·Tab 이동을 막고 실제 앱 추가 시 순서대로 대체한다. 일정 편집 저장 실패 시 열기를 보류하고, 잠금/트레이/사이드바 숨김/크기·화면 변경/초기화/종료 때 팝업과 예약 포커스를 취소한다. 단위 환산기와 날짜·시간 계산기 2개를 제공하며 사용자 앱 등록·외부 코드 로더는 범위 밖이다.
- 캘린더 이동은 크기와 무관하게 헤더의 A안 토글(검색과 더보기 사이)로 제어한다. 새 `calendar_move_enabled` 키는 기본 ON fallback, 명시적 토글 때만 저장하고 재시작/크기 전환/Export·Import에 유지한다. OFF는 본체 수동 드래그만 차단하며 개별 위젯·설정 위치 선택·화면 복구는 유지한다. 저장 실패는 이전 상태로 복원하고 잠금/트레이/크기 전환/초기화는 진행 중 드래그를 취소한다. 32px 버튼·4px 간격·좌우 104px로 기본 380px 헤더 중앙 정렬을 유지한다.
- 일정 이모지 선택 버튼은 벡터 테두리 스마일이며 입력부 색상 원과 외경 22px를 공유한다. 26px 클릭 영역·인라인 행 높이·팝업의 실제 이모지·선택/Undo·본문 Unicode 저장은 유지한다. 버튼 그림 때문에 DB/salt/기존 본문을 변환하지 않는다.
- 일정 목록의 여백은 행 레이아웃에 포함하고 `QListWidget::item` padding은 0으로 둔다. 인라인 편집기를 표시한 뒤 행 높이를 계산해 입력창과 26px 이모지 버튼 하단을 확보한다. compact/medium/large에서 실제 배치된 편집 영역이 버튼 전체를 포함하는지 검증한다.
- 캘린더 날짜 그리드와 요일 제목은 7열에 동일한 stretch를 적용한다. 일정 칩은 가로 `QSizePolicy.Ignored`로 말줄임 결과가 열 최소 너비에 역영향을 주지 않게 한다. 세로 화면에서 일정 추가·월 왕복·화면 왕복 후 실제 열 너비 차이 1px 이내와 요일 제목 정렬을 검증한다. 저장된 일정 본문·색상·DB/salt는 바꾸지 않는다.
- 공휴일 데이터는 추적 중인 `holidays.py`를 사용하고 `fetch_data.py`의 실제 API 데이터로만 갱신한다. 임의 계산 금지.
- 폰트·아이콘·이미지·SVG는 `app_paths.resource_root()`로 찾는다. 본문은 시스템 Malgun Gothic 기본, Pretendard는 D-Day 강조용이다. QSS 글꼴 크기는 정수 px만 쓴다.
- 소스 화면과 사용자 EXE의 이모지 렌더가 다르면 UI를 다시 수정하기 전에 실제 EXE의 SHA-256과 포함된 Qt DLL 버전·해시를 검증 환경과 대조한다. 표시 버전이나 소스 캡처만으로 수정 포함 여부를 판단하지 않는다. EXE 확인도 합성 데이터에서 수행한다.
- Win+D 보호는 일시 topmost pulse 후 바탕화면 바로 위 non-topmost 복귀다. 영구 topmost·WorkerW/SetParent 재부모화 금지. native hook은 해제한다.
- 설정창 800×560 무스크롤, 캘린더 크기·일정 표시·위젯 수 제한·DPI/스냅·메뉴 수명 등 세부 UI 계약은 [UI_PATTERNS.md](docs/UI_PATTERNS.md)를 따른다.
- 테스트/EXE 검증은 실행별 합성 데이터 폴더에서만 수행한다. 실사용 AppData·DB·salt 또는 기존 실행 중인 앱을 검사·정리 대상으로 쓰지 않는다.

## 저장소 (GitLab)

- **origin**: `https://gitlab.aigov.go.kr/whrhkdrh/climate-note` — 기관 내부 GitLab, visibility **Public**
- `main`이 정본이다. v3.5 시점의 부모 없는 orphan 커밋에서 시작하므로 v3.5 이전 개발 이력은 원격에 없고 로컬 `archive/local-v3.5` 브랜치에만 있다.

> 🚫 **`archive/local-v3.5`는 절대 push하지 않는다.** 이 브랜치의 첫 커밋에 `security/` 폴더가 들어 있고 그 안에 금강청 소스코드 취약점 점검 상세·요약 보고서와 CODEMIND 반론서가 있다. 저장소가 Public이므로 push하면 그대로 노출된다. `git push --all`과 `git push --mirror`는 이 브랜치까지 올리므로 **사용 금지**. push는 항상 `git push origin main`처럼 브랜치를 명시한다.

- **`security/`는 저장소에 없다.** CODEMIND 점검 원본 자료는 기관 내부 문서이므로 담당자가 저장소 외부에서 별도 관리하며 `.gitignore` 대상이다. 보안 코딩 규칙은 [`docs/CODING_STANDARDS.md`](docs/CODING_STANDARDS.md)에 자체 완결적으로 남아 있다.
- **`holidays.py`는 추적 대상이다.** 공공데이터포털 API 키 없이도 클론 직후 실행·테스트·빌드가 가능해야 한다는 결정이다. 갱신은 종전대로 `fetch_data.py`로만 하며 임의 계산은 여전히 금지다.
- 루트 `LICENSE`는 **GPLv3**다. `PySide6-Fluent-Widgets`가 GPLv3이고, 기관 내부 소스 공개와 기관 내부 EXE 배포로 제공 범위가 일치한다. 다만 SBOM·PySide6/Qt 고지·Authenticode 서명은 [릴리스 이력의 보류 과제](docs/RELEASE_HISTORY.md)에 그대로 남아 있다.
- `main`은 보호 브랜치다. push/merge는 Maintainer 이상, 강제 push는 비활성이다. 동료는 Developer 권한으로 Merge Request를 통해 기여한다.
- **빌드 산출물은 git에 커밋하지 않는다.** `dist/`는 `.gitignore` 대상이며 EXE 배포는 **GitLab Releases**(`/-/releases`)를 쓴다. EXE 하나가 약 55.6 MiB이고 PyInstaller 산출물은 델타 압축이 거의 되지 않아, 커밋하면 릴리스마다 통짜 블롭이 히스토리에 영구 누적된다(5개 릴리스면 약 300 MiB). 소스만 받으려는 사람도 전부 내려받게 되고, 나중에 빼려면 히스토리 재작성이 필요하다.
- 전환 설계와 근거: [`docs/superpowers/specs/2026-08-18-gitlab-public-migration-design.md`](docs/superpowers/specs/2026-08-18-gitlab-public-migration-design.md)
- **환경 드리프트 시 실패하는 검사**: `tests/test_packaging.py::test_requirements_lock_matches_verified_direct_dependencies`. `requirements-lock.txt`는 v3.5 기준에서 v3.7 컬러 이모지 수정용 Qt 계열 4개를 6.11.2로 갱신한 환경 기록이다. 검증 근거는 [글리프 잘림 작업 기록](docs/work/2026-09-10-schedule-emoji-glyph-clipping.md)에 남긴다. 로컬 venv 버전이 lock과 다르면 실패하며 lock을 임의로 갱신하지 않는다. 의존성 업그레이드는 lock 갱신 + 전체 재검증 + EXE 재빌드 + 검증 스냅샷 갱신을 한 묶음으로 처리한다. `pip install -r requirements-lock.txt`로 맞추면 통과한다.

## 기록 관리

- 현재 소스 버전은 **v3.8b (2026. 9. 24.)**다. 날짜·시간 계산기 입력 스크롤을 제거하고 날짜 2열·합산 항목 이전/다음 전환·작은 화면 압축을 적용했다. 계산 엔진·DB v17·Export v2·salt·설정·바로가기·Qt/lock은 유지한다. `release` **20260924-234234-5118aac61a**에서 **1,280개 테스트·새 EXE 빌드·격리 실행 3개 시나리오**, 날짜·시간 관련 125/150% 합성 배율 각각 173개를 통과했다. 포함 코드/Qt DLL 대조 후 새 EXE를 배치했으며 SHA-256은 `182C34BC719CCC01CEFA93269AF0501C84F995ADBCBC09BB0C8394D6BAE90EA2`다. 배치 시 표준 경로에 같은 이름의 EXE는 없었으며 이전 release 산출물은 유지했다. 검증 중 관측한 별도 환산기 native 메뉴 닫힘·실패 기록·최종 산출물·커밋·수동 미확인은 [스크롤 제거 기록](docs/work/2026-09-24-date-time-no-scroll.md)을 따른다. 아래 최초 구현 결과를 이번 UI 후속의 통과 근거로 사용하지 않는다.

- v3.8b 최초 구현 (2026. 9. 24.)의 기록이다. 두 번째 미니앱 날짜·시간 계산기의 A안을 추가했다. EXE는 `기후노트_v3.8b.exe`, Windows 숫자 버전은 `3.8.2.0`이며 `app_info.py`가 정본이다. DB v17·Export v2·salt·기존 설정/바로가기·Qt 6.11.2·lock을 유지한다. 당시 자동 검사·새 EXE·커밋·수동 미확인은 [v3.8b 구현 기록](docs/work/2026-09-24-v3.8b-date-time-calculator.md)을 따른다. release **20260924-181520-66630977c0**에서 **1,248개 테스트·새 EXE·격리 실행 3개 시나리오**를 통과했고 125/150% 합성 배율은 각각 141개를 통과했다. 포함 코드·SVG·Qt DLL 대조 후 dist에 배치했으며 SHA-256은 9B7604E12D2C2BA75646088F2075DCF8385B68A814E496EF3AC186976E96F2F8이다. 아래 v3.8a의 통과 수와 해시를 이번 기능의 통과 근거로 사용하지 않는다.

- 2026-09-24 환산기 드롭다운 후속은 **v3.8a를 유지**한다. FROM/TO·물질·온도 모드의 디자인과 즉시 펼침을 통일하며 DB v17·Export v2·salt·계산·설정·Qt/lock은 유지한다. `release` **20260924-144904-bd1ae56a4a**에서 **1,082개 테스트·새 EXE 빌드·격리 실행 3개 시나리오**, 125/150% 합성 배율 각각 113개를 통과했다. 공통 콤보 포함 6개 모듈·이미지/SVG·Qt 6.11.2 DLL 대조 후 `dist/기후노트_v3.8a.exe`에 배치했다. SHA-256은 `ABCF9D62DAB8E75A412765CCB9CD145E0B20F51753872D9250B5A13B759AF0FE`다. 직접 EXE 클릭은 화면 제어 도구 native pipe 연결 실패로 미실행이다. 이전 1,072개 테스트/EXE는 이번 수정 전 결과이며, 커밋·수동 미확인·현재 증거는 [드롭다운 수정 기록](docs/work/2026-09-24-unit-converter-dropdown-fix.md)을 따른다.

- 이전 소스 버전은 **v3.8a (2026. 9. 24.)**다. 수질 밀도·기체 농도 조건·온도차와 전체 단위 기준 표시를 추가했다. EXE는 `기후노트_v3.8a.exe`, Windows 숫자 버전은 `3.8.1.0`이며 `app_info.py`가 정본이다. DB v17·Export v2·salt·기존 설정·바로가기·Qt 6.11.2·lock은 유지한다. `release` **20260924-001659-ad39ce7342**에서 **1,072개 테스트·새 EXE 빌드·격리 실행 3개 시나리오**를 통과했다. 새 조건 모듈·생성 이미지·Qt DLL 대조 후 `dist/기후노트_v3.8a.exe`에 배치했으며 SHA-256은 `A0D3DE87E2455452369354DECE5FB0E4E1A465F16E28783D9244618CF8902CF3`다. 배율·빌드·커밋·수동 미확인은 [v3.8a 작업 기록](docs/work/2026-09-23-v3.8a-water-conversion-plan.md)을 따르며 아래 v3.8 결과를 현재 통과 근거로 사용하지 않는다.

- 2026-09-23 환산기 그림자·분류 가독성 후속은 **v3.8을 유지**한다. 내용 440×580px/그림자 포함 488×628px와 좁은 화면의 그림자 보정, 분류 행 28px/간격 0px/이름 13px를 적용한다. `release` **20260923-233212-6b41552457**에서 **1,028개 테스트·새 EXE 빌드·격리 실행 3개 시나리오**를 통과했고 125/150% 합성 배율은 각각 122/71개를 통과했다. 코드·생성 이미지·Qt 6.11.2 DLL을 대조했다. 표준 dist EXE는 사용 중(WinError 32)이라 원본을 보존하고 새 파일은 `dist/verified-20260923-233212/기후노트_v3.8.exe`에 제공한다. SHA-256은 `1B0FD66B1AB3BFD38B6ED0AA188D36A39F1465C53CD624A2726EE9047702F126`이다. 기존 계산·데이터·창 수명·기존 사용자 변경을 유지하며 증거·수동 미확인·커밋은 [그림자·가독성 기록](docs/work/2026-09-23-unit-converter-shadow.md)을 따른다. 아래 1,026개 테스트/주머니 EXE는 이번 후속 전 결과다.

- 2026-09-23 미니앱 주머니 개선은 **v3.8을 유지**한다. 그림자·구분되는 제목부·92px 타일 4개(환산기 1개/비활성 예정 3개)와 번들 생성 이미지를 적용한다. DB v17·Export v2·salt·바로가기 6슬롯·환산기 계산·메모리 기록·의존성을 유지한다. `release` **20260923-230703-359f295b1f**에서 **1,026개 테스트·새 EXE 빌드·격리 실행 3개 시나리오**를 통과했고, 125/150% 합성 배율은 각각 120/90개를 통과했다. 번들 코드·생성 이미지·Qt 6.11.2 DLL 대조 후 `dist/기후노트_v3.8.exe`에 배치했다. SHA-256은 `49E8FDE45DD6F0844548E999E02DB383C6344BE2639C40DFABD96CB185E05B12`다. EXE 직접 클릭은 화면 제어 도구 연결 실패로 미실행이며 실제 혼합 DPI/KVM·정상 종료·Defender는 별도다. 상세 증거·기존 EXE 보관·로컬 커밋은 [주머니 개선 기록](docs/work/2026-09-23-mini-app-pocket-redesign.md)을 따른다. 아래 9월 22일의 1,020개 테스트/EXE는 이번 UI 변경 전 결과다.

- 2026-09-22 망 전환/KVM 위치 복원 개선은 **v3.8을 유지**한다. 임시 좌표 역저장과 모니터 순번 의존을 개선했으며 `calendar_screen` 설정만 명시적 배치 때 추가한다. 당시 `release` **20260922-204654-f09bb44407**에서 **1,020개 테스트·신규 EXE 빌드·격리 EXE 3개 시나리오**를 통과했다. 새 모듈 포함 코드와 Qt DLL 대조 후 `dist/기후노트_v3.8.exe`에 배치했으며 SHA-256은 `BF726F5FD21374FFEE9DF76F6B868847B1EE4C28B0E3123CCC4190481AE173CA`다. 실제 회사 KVM·혼합 DPI·Win+D·EXE 정상 종료·Defender 등 수동 확인은 별도다. 구현·데이터 보존·산출물·2026-09-23 지침 갱신과 로컬 커밋 상태는 [복원 개선 기록](docs/work/2026-09-22-kvm-window-position-fix.md)을 따른다. 이전 9월 21일 단위 환산기 산출물을 이번 수정의 통과 근거로 사용하지 않는다.

- 이전 소스 버전은 **v3.8 (2026. 9. 21.)**다. 첫 미니앱 단위 환산기를 추가했으며 EXE는 `기후노트_v3.8.exe`, Windows 숫자 버전은 `3.8.0.0`이다. 버전 정본은 `app_info.py`이며 DB v17·Export v2·Qt 6.11.2·lock·기존 데이터 저장 계약을 유지한다. 단위 환산기 구현/계수 출처와 당시 검증은 [확대·환경 단위 기록](docs/work/2026-09-21-mini-app-environment.md)에 보존한다. 위치 복원 검증은 위 2026-09-22 기록, 최신 주머니 후속 검증과 EXE는 2026-09-23 기록을 따른다. 최초 21분류 구현 증거는 [v3.8 최초 기록](docs/work/2026-09-20-v3.8-unit-converter.md)에 보존한다. 이전 v3.7b 결과를 v3.8 통과 근거로 사용하지 않는다.

- 2026-09-20 미니앱 버튼·빈 주머니 후속은 **v3.7b를 유지**한다. 기존 바로가기 6개 데이터/관리 동작·DB v17·Export v2·salt·설정 키·의존성을 유지한다. 현재 검증/커밋/EXE 해시는 [미니앱 작업 기록](docs/work/2026-09-20-mini-app-pocket.md)을 따른다. 이전 이동 토글의 775개 테스트/EXE는 이번 기능 전 결과다.

- 2026-09-20 캘린더 이동 토글·테두리 스마일 후속은 **v3.7b를 유지**한다. 모든 크기의 이동 ON/OFF와 새 설정 키 하나를 추가하고, 스마일 외경을 색상 원과 같은 22px로 맞춘다. DB v17·Export v2·salt·기존 본문·의존성을 유지한다. 현재 검증/커밋/새 EXE 해시는 [이동 토글 작업 기록](docs/work/2026-09-20-calendar-move-toggle.md)을 따른다. 아래 755개 테스트/EXE는 이번 기능 전 결과이며 현재 통과 근거로 재사용하지 않는다.

- 2026-09-20 B+C 파일 라벨은 **버전 v3.7b를 유지**한다. [최초 라벨 기록](docs/work/2026-09-20-sticky-file-labels.md) 이후 [배지·간격 개선](docs/work/2026-09-20-sticky-link-spacing-fix.md)에서 배지 8px/최대 11px 높이·상하 inset과 정상 링크 뒤 2px 간격을 적용했다. 끊김 경고 공간은 필요한 상태에서만 표시용 layout으로 갱신하고 본문·revision·Undo·저장/IME preedit를 보존한다. AGENTS.md와 소스를 `085fd78`로 먼저 커밋한 뒤 `release` **20260920-205858-837fd234ab**에서 **755개 테스트·격리 EXE 3개 시나리오**를 통과했다. 실제 Qt 6.11.2 DLL/체인 SVG/파일 라벨 모듈 대조 후 표준 `dist/기후노트_v3.7b.exe`로 배치했으며 해시·검증·수동 미확인은 간격 개선 기록을 따른다. 이전 723개 테스트/EXE는 라벨 구현 전 결과다.
- `desgn_claude/`는 임시 디자인 작업 폴더이며 Git 추적 대상이 아니다. 프로젝트 탐색·검색·분석 시 제외하고, 사용자가 해당 폴더를 명시적으로 요청하기 전에는 내부 파일을 읽지 않는다.
- 프로젝트 초기 파악 시 과거 구현 계획·완료된 작업 기록·`output/` 결과를 일괄로 읽지 않는다. 현재 작업에 필요한 지침과 관련 자료만 선택해서 읽는다.
- [RELEASE_HISTORY.md](docs/RELEASE_HISTORY.md)에 v3.3~v3.6b 검증과 미해결 조사·보류 항목을 보존했다. 현재 검증은 하네스 보고서와 해당 작업 기록을 본다.
- 이전 소스 버전은 **v3.7b (2026. 9. 20.)**다. `app_info.py`에서 설정·업데이트 안내·빌드 메타데이터로 전달하며 EXE 이름은 `기후노트_v3.7b.exe`, Windows 숫자 버전은 `3.7.2.0`이다. 스티키 로컬 파일 링크와 Export 최신 저장 확인을 추가하며 DB v17·Export v2·암호화 키 유도·salt·설정·의존성을 유지한다. 파일 연결 계약은 [최초 구현 기록](docs/work/2026-09-20-sticky-file-links.md), 파일 라벨의 이전 소스/EXE 검증과 해시는 [배지·간격 개선 기록](docs/work/2026-09-20-sticky-link-spacing-fix.md)에 보존한다. 당시 EXE는 755개 테스트·격리 시나리오 3개와 실제 Qt/SVG/라벨 모듈 검증을 통과했다. 이동 토글·테두리 스마일의 검증은 [해당 작업 기록](docs/work/2026-09-20-calendar-move-toggle.md)에 보존하고, 이후 미니앱 주머니의 최신 상태는 [현재 작업 기록](docs/work/2026-09-20-mini-app-pocket.md)을 따른다. 이전 체인 아이콘·선택 문구 안내 빌드는 [이전 후속 기록](docs/work/2026-09-20-sticky-link-selection-fix.md)에 보존한다. 게시·push와 실제 UI 수동 확인은 별도이며 이전 산출물 결과를 재사용하지 않는다.
- v3.7은 DB v17·암호화·저장 경로·기존 설정 키를 유지하는 데이터 UI 수명·잠금 개선이다. 버전·호환성·검증 범위는 [v3.7 작업 기록](docs/work/2026-09-09-v3.7-version-commit.md)에 남긴다. 소스 검증과 새 EXE 검증·게시 여부를 구분한다.
- 일정 이모지 선택은 표시 버전 v3.7·DB v17을 유지한 후속 기능이다. 구현·중단 후 재점검·최종 검증 근거는 [일정 이모지 작업 기록](docs/work/2026-09-09-schedule-emoji-plan.md)에 남긴다. 당시 미실행이던 EXE 재빌드·격리 검증은 아래 글리프 잘림 기록에서 갱신하며, 실제 한글 IME·혼합 DPI/KVM 확인과 게시는 별도다.
- 일정 인라인 편집 이모지 하단 잘림 수정과 100/125/150% 합성 배율 검증은 [하단 잘림 작업 기록](docs/work/2026-09-10-schedule-emoji-clipping.md)에 남긴다. 소스 수정과 EXE 재빌드·게시 여부를 구분하며 실제 혼합 DPI/KVM 확인은 별도다.
- 입력창·선택 버튼의 컬러 글리프 잘림은 행 높이와 별개인 Qt Windows 캐시 문제다. Qt/PySide6 6.11.2 갱신과 재빌드 검증은 [글리프 잘림 작업 기록](docs/work/2026-09-10-schedule-emoji-glyph-clipping.md)에 남기고 [UI 계약](docs/UI_PATTERNS.md)의 비트맵 경계 검사를 유지한다.
- 2026-09-14에는 로컬 `dist/기후노트_v3.7a.exe`에 전역 Python의 Qt 6.10.2가 다시 포함된 것을 확인했다. 일반 빌드 경로를 위 명령처럼 고정하고 Qt 6.11.2로 재빌드했다. `release` 실행 `20260914-000953-2116a75e03`에서 669개 테스트와 3개 격리 EXE 시나리오를 통과했고, 기존 합성 데이터 8개 테이블의 raw/복호화 내용·ID·salt가 보존됐다. 실제 EXE의 100% large 화면에서 버튼·입력창 이모지의 우측·하단 픽셀 복원을 확인했다. 새 EXE의 해시·내부 Qt 대조·구형 EXE 보호 보관·dist 교체는 [재점검 작업 기록](docs/work/2026-09-14-schedule-emoji-rendering.md)에 남긴다. 앱 UI·저장 코드·DB v17·Export v2·버전·lock은 이번 수정에서 변경하지 않았으며 실제 한글 IME·혼합 DPI/KVM·GitLab 게시는 별도다.
- 세로 화면 large 보기의 요일 열 축소는 일정 칩의 말줄임 결과가 레이아웃 최소 너비로 되먹임되는 문제다. 수정과 기존 데이터 보존·EXE 검증은 [요일 열 너비 수정 기록](docs/work/2026-09-11-calendar-column-width-fix.md)에 남긴다. 앱 v3.7·DB v17·Export v2·Qt 6.11.2를 유지하며 실제 회사 PC 혼합 DPI/KVM 확인과 GitLab Release 게시는 별도로 구분한다.
- 설정/휴지통 특정 PC 멈춤, 임시 WAL/SHM 누적, 회사 PC 모니터 식별·혼합 DPI/KVM 실기 확인은 별도 후속 과제다.
- 라이선스·SBOM·PySide6/Qt 조건·서명 후속 과제는 증빙 없이 완료 처리하거나 삭제하지 않는다.
