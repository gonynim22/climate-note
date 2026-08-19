# AGENTS.md

App display name: **기후노트** | Internal path: `MyDesktopCalendar` | Version: **v3.6** (2026.8.18)

> ✅ **v3.6 산출물 검증 완료(2026-08-18).** 앱 런타임 코드는 v3.5와 동일하며, 변경분은 표시 버전·제3자 라이선스 고지·저장소 정비다. 전체 테스트 518건, 격리 신규 설치, v3.5 데이터 업데이트 시나리오, Defender 검사를 통과했다. 상세는 아래 "v3.6 Release Verification Snapshot"을 본다. **배포 방식은 GitLab Releases를 사용하고 `dist/`를 git에 커밋하지 않는다**(EXE 55.6 MiB가 릴리스마다 히스토리에 영구 누적되기 때문).

> ✅ **v3.5 배포 진행 결정(2026-08-15).** 설정 하단 버전 문구와 앱 메타데이터를 v3.5로 올렸으며, 정상 종료 전 스티키 저장 게이트·바로가기 인라인 관리·시작 전 데이터 건강 검사·DB와 `.salt`를 한 파일로 묶는 자동백업을 포함한다. **DB 스키마와 암호화 방식은 v3.4의 v17을 그대로 유지하며 기존 행을 일괄 수정하지 않는다.** 기술 검증 결과를 바탕으로 현 산출물의 배포를 진행한다.

> ⚠️ **라이선스 정비는 해결된 것이 아니라 명시적으로 보류한 후속 과제다.** `PySide6-Fluent-Widgets 1.11.1`의 GPLv3 준수 배포 또는 별도 상용 라이선스 확보, PySide6/Qt 고지·소스 제공 조건, 실제 번들 기준 SBOM을 아래 체크리스트대로 정리해야 한다. 이 기록을 삭제하거나 "완료"로 바꾸려면 근거 문서·산출물·해시를 함께 남긴다.

> ✅ **v3.4는 2026-08-04 정식 버전으로 확정됐다.** v3.3 릴리스 후보의 변경분(**D-Day Cover Tint 리디자인 + Pretendard 번들·캘린더 자유 이동·일정 3슬롯 표시색 설정·스티키 벡터 체크박스**)에 v3.4 변경분(**large 모드 캘린더 드래그 비활성·`바탕화면 고정` 명칭 및 데스크톱 바로 위 z-order 고정·large 일정 칩 가독성 개선**)을 합친 버전이다. `manual.qmd`와 온나라 업데이트 안내 초안도 v3.4 기준으로 갱신했다.

> ✅ **2026-08-06 v3.4 정식 산출물 재검증 완료.** 전체 테스트 467개, PyInstaller 산출물의 격리 실행·신규 v17 DB 무결성·필수 리소스·Windows 버전 정보와 Windows Defender 검사를 통과했다. 2026-08-04에 확인한 실제 Win32 z-order와 동일 DPI 듀얼 모니터 결과도 유지한다. 외부 게시 전 운영 확인 항목은 실제 Win+D 직후 Explorer/브라우저 전환, 음수 좌표·혼합 DPI 다중 모니터 육안 확인, **2026-08-05 접수된 특정 PC의 설정/휴지통 멈춤 원인 분리**, QFluentWidgets 배포 라이선스 경로 확정과 필요 시 Authenticode 서명이다.

## Source of Truth

This file is the project source of truth for Codex and other coding agents.

`CLAUDE.md` is only a compatibility pointer to this file. Keep durable project instructions here.

## 저장소 (GitLab)

- **origin**: `https://gitlab.aigov.go.kr/whrhkdrh/climate-note` — 기관 내부 GitLab, visibility **Public**
- `main`이 정본이다. v3.5 시점의 부모 없는 orphan 커밋에서 시작하므로 v3.5 이전 개발 이력은 원격에 없고 로컬 `archive/local-v3.5` 브랜치에만 있다.

> 🚫 **`archive/local-v3.5`는 절대 push하지 않는다.** 이 브랜치의 첫 커밋에 `security/` 폴더가 들어 있고 그 안에 금강청 소스코드 취약점 점검 상세·요약 보고서와 CODEMIND 반론서가 있다. 저장소가 Public이므로 push하면 그대로 노출된다. `git push --all`과 `git push --mirror`는 이 브랜치까지 올리므로 **사용 금지**. push는 항상 `git push origin main`처럼 브랜치를 명시한다.

- **`security/`는 저장소에 없다.** CODEMIND 점검 원본 자료는 기관 내부 문서이므로 담당자가 저장소 외부에서 별도 관리하며 `.gitignore` 대상이다. 보안 코딩 규칙은 [`docs/CODING_STANDARDS.md`](docs/CODING_STANDARDS.md)에 자체 완결적으로 남아 있다.
- **`holidays.py`는 추적 대상이다.** 공공데이터포털 API 키 없이도 클론 직후 실행·테스트·빌드가 가능해야 한다는 결정이다. 갱신은 종전대로 `fetch_data.py`로만 하며 임의 계산은 여전히 금지다.
- 루트 `LICENSE`는 **GPLv3**다. `PySide6-Fluent-Widgets`가 GPLv3이고, 기관 내부 소스 공개와 기관 내부 EXE 배포로 제공 범위가 일치한다. 다만 SBOM·PySide6/Qt 고지·Authenticode 서명은 아래 "Deferred Release Work"에 그대로 남아 있다.
- `main`은 보호 브랜치다. push/merge는 Maintainer 이상, 강제 push는 비활성이다. 동료는 Developer 권한으로 Merge Request를 통해 기여한다.
- **빌드 산출물은 git에 커밋하지 않는다.** `dist/`는 `.gitignore` 대상이며 EXE 배포는 **GitLab Releases**(`/-/releases`)를 쓴다. EXE 하나가 약 55.6 MiB이고 PyInstaller 산출물은 델타 압축이 거의 되지 않아, 커밋하면 릴리스마다 통짜 블롭이 히스토리에 영구 누적된다(5개 릴리스면 약 300 MiB). 소스만 받으려는 사람도 전부 내려받게 되고, 나중에 빼려면 히스토리 재작성이 필요하다.
- 전환 설계와 근거: [`docs/superpowers/specs/2026-08-18-gitlab-public-migration-design.md`](docs/superpowers/specs/2026-08-18-gitlab-public-migration-design.md)
- **알려진 테스트 실패 1건**: `tests/test_packaging.py::test_requirements_lock_matches_verified_direct_dependencies`. `requirements-lock.txt`는 v3.5 EXE를 만든 검증 버전 기록이므로 로컬 venv가 그보다 새 버전으로 드리프트하면 실패한다. lock 파일을 임의로 갱신하지 않는다. 의존성 업그레이드는 lock 갱신 + 전체 재검증 + EXE 재빌드 + 검증 스냅샷 갱신을 한 묶음으로 처리한다. `pip install -r requirements-lock.txt`로 맞추면 통과한다.

## Commands

```bash
python main.py                                           # 실행
pip install -r requirements.txt                          # 의존성 설치 (pytest-qt 포함)
python -m pytest tests -q                                # 전체 테스트 실행 (DB/UI/보안/스트레스)
python build_app.py                                      # 빌드 → dist/기후노트_v3.6.exe
```

## 핵심 개발 원칙

> **기존 사용자 데이터는 반드시 그대로 보존되어야 한다.**

- 스키마 변경: `ALTER TABLE ... ADD COLUMN`만 허용. DROP/RECREATE 금지. `migrate()` 버전 번호 올리기.
- 마이그레이션: 멱등성 보장 (`IF NOT EXISTS` 또는 `try/except sqlite3.OperationalError`).
- 암호화 변경: 기존 데이터 복호화 → 재암호화 경로 제공. 자동 삭제 금지.
- 설정 변경: 기존 `app_settings` 키 삭제 금지. 새 키 추가 + 기본값 fallback 처리.
- 데이터 변경 기능 추가 시: `tests/`에 왕복 검증 테스트 필수.

## Module Map

| File | Role |
|---|---|
| `app_info.py` | App metadata single source: display name, version, release date, author, versioned exe name |
| `main.py` | Entry point: single-instance lock, app font/theme init, DB init(`inspect_startup_data_health()`→v3.5 최초 보호백업→마이그레이션 전 snapshot→`migrate()`→일일 자동백업 순서, 사전 검사·백업 실패 시 fail-closed), tray, Boss Key (Ctrl+Shift+H). 격리 EXE smoke에서만 `CLIMATENOTE_SKIP_STARTUP_REFRESH=1`로 시작프로그램 경로 갱신을 막는다 |
| `app_paths.py` | 번들 리소스 루트 단일 출처. `resource_root()`는 frozen이면 `sys._MEIPASS`, 소스 실행이면 프로젝트 루트를 돌려준다. 폰트·아이콘·이미지·SVG 경로는 모두 이 함수를 거치며 `Path(__file__).parent`로 다시 만들지 않는다(`tests/test_app_paths.py`가 가드). 이 파일이 경로 기준점이므로 하위 폴더로 옮기면 `_SOURCE_ROOT`를 함께 고쳐야 한다 |
| `app_fonts.py` | App font resolution: Malgun Gothic default, installed system font keys, Font Awesome icon font loading |
| `security.py` | Hardware key derivation (`_derive_fernet_key`), path validation, Fernet encrypt/decrypt (cached), 기존 `.salt` 엄격 읽기와 신규 데이터셋 salt 원자 생성, audit log |
| `show_desktop_guard.py` | `ShowDesktopKeeper(QObject)` — 감시 창을 Win+D('바탕화면 보기')와 Win+M(모두 최소화)에서 유지하며 평상시에는 **바탕화면 바로 위의 non-topmost 레이어**에 둔다. `SetWinEventHook(EVENT_SYSTEM_FOREGROUND)`로 셸의 실제 바탕화면(`GetShellWindow`, 또는 동일 셸 PID의 `Progman`/`WorkerW`) 진입을 감지하면 `HWND_TOPMOST`로 350ms만 승격한다. 이후 `GetWindow(GW_HWNDPREV)`로 데스크톱 앞의 첫 일반 창을 찾고 `SetWindowPos`로 감시 창들을 그 창과 데스크톱 사이에 삽입한다. 탐색기·브라우저 등 다른 창이 foreground가 되면 pulse를 즉시 취소하고 같은 데스크톱 레이어로 재고정한다. Win+M/실제 최소화는 `WindowStateChange`→`singleShot(0)` 복원. 재부모화 없음. hook callback 강한 참조·`UnhookWinEvent` 해제·64비트 HWND ctypes 선언 필수 |
| `database.py` | SQLite CRUD + schema migration (v17); `@contextmanager _connection()`과 read-only 건강 검사; 일정 원본 3슬롯과 10색 표시 팔레트; `SETTING_CALENDAR_POSITION_MODE`; WAL-safe `Connection.backup()` snapshot·`.salt`·hash manifest를 묶은 검증형 `.cnbak` 자동백업(당일 정상본 불변, 최근 5일)과 비회전 v3.5/가져오기/초기화 전 보호본; 기존 DB-only 마이그레이션 snapshot 보존; Export v2 단일 read snapshot·엄격 복호화; Import 전체 사전검증·단일 트랜잭션·집중 세션 ID remap·기존 메모/바로가기 보존(`privacy_pin` 제외); 스티키 휴지통; `enforce_widget_limits()`는 집중 1개·D-Day 5개 상한 초과분을 삭제 없이 `is_open=0` 정리 |
| `holidays.py` | Offline Korean holiday/lunar data (생성물, gitignore). `KOREAN_HOLIDAYS` (2025-2027), `LUNAR_MAPPING` (2025-2050). 함수: `get_holiday`, `is_holiday`, `get_lunar_date`, `holiday_last_year`. **`fetch_data.py`로만 갱신** (임의 계산 금지). |
| `fetch_data.py` | 공공데이터포털 API로 `holidays.py` 재생성 (실제 API 데이터만, 임의 계산 없음). `verify_holiday_data(hol)` 로 재생성 후 커버리지 검증. 갱신 절차: 백업 → `python fetch_data.py` → `verify_holiday_data` 통과 확인 → 실패 시 백업 복구. |
| `ui_main.py` | Main window: frameless; compact/medium에서 헤더 배경·연월 라벨 드래그 이동(대상 화면 DPI 기준 5mm 전역 격자), `large`에서는 드래그 비활성; 자유 좌표 복원·화면 이탈 clamp·타겟 모니터/최근접 모서리 동기화; Privacy Lock; AI 법령검색바; 전체 창 투명도 broadcast; compact/medium/large 캘린더와 확장 3열 reflow; Shortcut Sidebar 6슬롯(빈 슬롯 클릭 파일/폴더 등록, 등록 슬롯 우클릭 이름 변경·경로 재지정·삭제, 끊긴 경로 클릭 복구); 스티키/D-Day/집중 모드 자동정렬. 자동정렬은 저장된 모서리가 아니라 **캘린더의 실제 화면·최근접 모서리**를 기준으로 한다. 시작 시 `enforce_widget_limits()`를 1회 호출하고 정리분이 있으면 모달 안내. `large` 스케일에서는 우측 컬럼을 `[일정 → D-Day 미니 → 집중 미니 → 스티키 미니]` 4구획으로 구성하며, 플로팅 스티키/D-Day/집중을 숨기고 패널과 동기화한다. 이탈 시 패널 저장 후 DB→플로팅 재로드/복원. 정상 종료 전에는 현재 모드의 최신 스티키 원본을 모두 강제 저장하고 하나라도 실패하면 종료를 보류한다. 초기 표시 전 사이드바 경계는 설정값 기준으로 `sidebarActive`/`expanded` dynamic prop을 맞춘다. `CalendarDayButton`은 compact 3행/expanded 일정 칩 2모드이며, large 일정 칩은 13px 글꼴·22px 높이·3px 간격을 사용하고 일정 raw 슬롯은 `schedule_display_color()`로 표시색만 치환한다. 공휴일 날짜는 빨강(`#D32F2F`), 공휴일명은 하단 패널(`holiday_info_label`)에 표시. 헤더 월 네비(`< 연월 >`)는 좌우 stretch 대칭 중앙 정렬. 미니 D-Day 삭제·집중 미니 종료 배선; Win+D 데스크톱 레이어 고정용 ShowDesktopKeeper 소유(메인+모든 플로팅 위젯 가드), 설정 토글 실시간 반영 |
| `ui_search.py` | Global keyword search: Notion-스타일 `QTableWidget`, 일정은 사용자 팔레트색의 `■` 배지, 메모는 📝 배지, 실시간 결과 정렬 |
| `ui_settings.py` | Settings(**시안 A · Fluent 정돈형**): 800x560 무스크롤 5개 섹션 패널 2열(화면 표시/위젯·도구/데이터/보안/시스템). 각 패널은 흰 배경 + 쿨그레이 라운드(11px, `#D7DAE2`) 카드(`_SettingsPanel`)이며, **밝은 헤더 바(`panelHeaderBar` `#F6F6F6` + 라운드 상단/좌우/하단 경계 `#D7DAE2`) 안에 블루 섹션 아이콘(`FIF`, `#2563EB`) + 진한 굵은 `StrongBodyLabel`(`panelHeader`, `#1A1A1E`)**. `_SettingsPanel` 본문은 마우스 hover 시 배경/테두리 색이 진해지는 애니메이션을 만들지 않는다. 행은 `_add_row`로 라벨-좌(고정폭)/컨트롤-우 + 행간 1px 구분선(`#F2F3F6`). 모니터/화면 위치는 **별도 두 행**(콤보 / 4모서리 2×2 그리드 `posGrid`). 전체 투명도, 캘린더 크기(`CalendarSizePicker`), 일정 색상(`ScheduleColorPicker`: 3개 원형 슬롯, 각 10색 메뉴, 중복색 비활성), 앱 글꼴, 저장 폴더(폴더 버튼만), Export/Import. 일정 색상 `RoundMenu.exec()`는 비동기이므로 즉시 삭제하지 않고 `closedSignal` 뒤 `deleteLater()`로 정리한다. 암호화 Export는 같은 폴더 임시파일+`fsync`+`os.replace`로 저장하여 실패 시 기존 파일을 보존하고, Import 직후 팔레트와 런타임 설정을 다시 불러온다. 가져오기·Factory Reset은 현재 DB+salt 보호본 생성이 성공해야 진행한다. 토글·슬라이더는 텍스트 없는 단일 블루. 상단 큰 '설정' 제목은 두지 않으며, 섹션 헤더 글자는 `setTextColor(#1A1A1E)`+`setFont(Bold)`로 고정, 하단 크레딧은 한 줄, 모니터 콤보 폭 210, '화면 위치' 높이 60. **데이터 초기화는 PIN 없이 확인 팝업만 거쳐 실행**. "시스템"의 `바탕화면 고정` 토글은 Win+D 보호와 데스크톱 바로 위 레이어 고정을 실시간 on/off 한다. |
| `ui_update.py` | Shared update guide dialog: 현재 앱 버전 표시, 온나라 커뮤니티 업데이트 게시물 확인 절차, 온나라 지식 홈 URL 버튼 |
| `ui_sticky.py` | Sticky notes: frameless, draggable, resizable, HTML format, auto-save (타겟 모니터 기반 자동 5mm 정렬). 할 일은 저장 호환용 Font Awesome `\uf0c8`/`\uf14a` 및 레거시 `☐`/`☑` 문자를 **그대로 보존**하되 `QSyntaxHighlighter`로 기본 글리프만 숨기고 `_TodoTextEdit.paintEvent()`에서 15px 라운드 벡터 체크박스를 그린다. 약 22px 히트박스·hover·클릭 토글·Enter 연속/탈출·체크 토글 1회 Undo를 제공하고, 체크 시 본문만 dim+취소선 처리한다. 닫기/휴지통 이동 및 정상 종료 전에 최신 편집을 강제 저장하며, 저장 실패 시 작업을 중단하고 2초 자동 저장 타이머를 재가동한다. 서식 공용 함수 + `StickyFormatToolbar`, 닫기 확인은 parent 없는 top-level `Dialog` 사용 |
| `ui_sticky_panel.py` | `large` 모드 우측 컬럼의 편집 가능한 미니 스티키 패널(`StickyMiniCard`/`StickySidePanel`). `_TodoTextEdit`·`STICKY_HEADER_COLORS` 재사용, 공용 서식 툴바, 포커스 카드 추적, 카드별 X(휴지통 soft-delete), `note_trashed` 전파, 배경색 변경. `large` 정상 종료 시 패널 카드가 단일 최신 원본이며 `save_all()`은 모든 카드 저장을 시도한 뒤 전체 성공 여부를 반환한다. |
| `ui_trash.py` | 스티키 노트 휴지통 창: 삭제된 노트 목록(색상/미리보기/삭제시각), 복구(`restore_requested` 시그널 → 메인이 원위치 재생성)/영구삭제/휴지통 비우기. 확인 팝업만(PIN 없음) |
| `ui_dday.py` | D-Day widgets: 카드 본체 220x95(창은 그림자 여백 `SHADOW_MARGIN`만큼 큼), color picker, double-click edit, 1-min auto-refresh. **Cover Tint**(진한 커버색+흰 타이포): `DDAY_COVER_COLORS`/`dday_cover_color`(구 파스텔 매핑)/`_dday_font`(Pretendard)/`_CoverIconButton`(흰 X) 정의처 |
| `ui_dday_panel.py` | `large` 모드 우측 컬럼의 편집 가능한 미니 D-Day 패널(`DDayMiniCard`/`DDaySidePanel`). **3열 그리드**(스크롤 없음, 최대 5개=2행), 카드별 X(`delete_requested`)로 영구 삭제, 더블클릭 편집 요청·1분 갱신. |
| `ui_focus.py` | Focus Mode widgets: 1개만 생성/표시, ambient/glance 상태만 제공, 생성 시 목표/짧은 집중·깊은 집중·몰입 블록 모드 설정 후 즉시 시작, 더블클릭 편집 패널 없음, 진행률 원형 링, 기본 배경 그라데이션(`#FFFFFF`→`#EEF6FF`→`#DDE8FF`), ambient 우측 `tomato_mini.png`, hover 시 상세 정보(모드·`MM:SS` 남은 시간·다음 휴식 `HH:MM AM/PM`) + 투명 배경의 50px `tomato.png`, hover 토마토 클릭 시 외곽 배경 없는 3초 응원 말풍선, 큰 토마토 기본 툴팁 없음, 집중 완료 후 휴식 시작 버튼 알림, 세션 기록 저장 |
| `ui_focus_panel.py` | `large` 모드 우측 컬럼의 집중 미니 패널(`FocusMiniCard`/`FocusSidePanel`). 숨긴 플로팅 집중창의 `FocusTimer`를 매초 미러링, 카드 X(`close_requested`)로 세션 종료. |
| `resources/images/tomato.png` / `tomato_mini.png` | Focus Mode 장식 이미지. `tomato_mini.png`는 ambient 전용이며 hover 시 숨고, `tomato.png`는 hover Glance 전용이다. 두 이미지 모두 흰 배경은 투명 처리되어야 한다. `build.spec` datas의 `('resources', 'resources')`로 통째로 번들되므로 개별 항목을 다시 추가하지 않는다. 경로는 `ui_focus._IMAGE_DIR`이 단일 출처다 |
| `popup_border_fix.py` | Win11 DWM 창 테두리가 `RoundMenu`(콤보 드롭다운 포함) 그림자 여백 창 외곽에 "메뉴보다 넓은 박스"로 그려지는 문제 우회. 앱 레벨 이벤트 필터가 메뉴 Show 시 `DwmSetWindowAttribute(DWMWA_BORDER_COLOR, COLOR_NONE)` 적용. Qt 쪽 완화(그림자/여백/QSS)로는 제거 불가(OS가 그리는 선) — 실측 확인 |
| `build_app.py` | PyInstaller build script. 출력 exe 이름은 `app_info.py`의 `APP_DISPLAY_NAME`/`APP_VERSION` 기반 |

## Key Constraints

- **오프라인 전용**: 외부 API 호출 없음. 공휴일/음력 데이터 내장 필수. (예외: AI 법령검색 및 업데이트 안내는 브라우저 URL 오픈)
- **wmux 금지**: 이 프로젝트에서 `wmux browser` 등 wmux CLI 명령은 호출하지 않는다. 웹 브라우징이 필요하면 `WebFetch`/`WebSearch` 도구를 사용한다. 전역 CLAUDE.md의 wmux 지침은 이 프로젝트에 적용하지 않는다.
- **DB 연결**: 반드시 `database.py`의 `_connection()` 컨텍스트 매니저 사용. 직접 `sqlite3.connect()` 금지.
- **파일 열기**: 반드시 `with open(...) as f:` 사용.
- **암호화**: 모든 민감 데이터는 `security.py`의 Fernet 함수 경유. 평문 저장 금지.
- **앱 글꼴**: 기본 본문 폰트는 Windows 시스템 폰트 `Malgun Gothic`이다. 설정 키는 `SETTING_APP_FONT = "app_font"`이며, 적용은 앱 시작 시 `app_fonts.apply_app_font()` 경유. 설정창에서 변경하면 저장만 하고 재시작 안내를 표시한다.
- **앱 버전**: 표시 버전과 빌드 exe 파일명은 `app_info.py`의 `APP_VERSION`을 단일 출처로 사용한다. 빌드 스크립트가 `AGENTS.md`를 파싱하지 않는다.
- **v3.5 시작 데이터 건강 검사**: DB를 쓰기 전에 read-only 연결로 SQLite `integrity_check`, 지원 스키마와 암호화 대상 6개 컬럼의 전수 복호화를 검사한다. DB가 있는데 암호문을 열 수 없거나 `.salt`가 누락·손상됐으면 새 DB/salt/백업을 만들지 않고 메인 창 생성 전에 중단한다. UI는 데이터 폴더 열기와 종료만 제공하며 원인을 PC·계정·salt 중 하나로 단정하지 않는다. 진짜 신규 설치는 DB·salt·WAL/SHM·기존 백업이 모두 없을 때뿐이다.
- **v3.5 자동백업 묶음**: 같은 PC·같은 Windows 사용자 복구용 `backups/calendar_auto_YYYYMMDD_*.cnbak`은 정확히 `calendar.db`(WAL-safe snapshot), `.salt`(원본 32 bytes), `manifest.json`(형식/버전/크기/SHA-256/schema/key-check) 3개만 담는다. 임시 묶음을 완전 검증한 뒤 같은 볼륨에서 `os.replace`로 게시하고, 당일 첫 정상본은 덮어쓰지 않으며 검증된 일일 묶음만 최근 5일 보존한다. 기존 `calendar_backup_*.db`와 `calendar_pre_v17_*.db`, 비회전 보호본은 자동 회전에서 절대 삭제하지 않는다. 새 salt 생성은 보호할 암호문이 0개임을 건강 검사가 확인한 데이터셋에만 허용한다. 이 묶음은 PC 이동용이 아니며 PC 이동은 기존 PIN `.enc` 내보내기/가져오기를 사용한다.
- **v3.5 비회전 보호본**: 기존 v3.4 DB는 첫 v3.5 실행에서 `calendar_pre_v35_*.cnbak`으로 한 번 보존한다. 가져오기와 Factory Reset 직전에는 각각 `calendar_before_import_*.cnbak`, `calendar_before_reset_*.cnbak`을 만들며 실패하면 해당 작업을 시작하지 않는다. 실행 중 live DB와 salt를 두 파일로 직접 교체하는 복원 UI는 금지한다. 안전한 복원은 앱 시작 전 검증·rollback·재개 가능한 journal을 갖춘 별도 절차로만 추가한다.
- **체크박스 저장 호환**: 스티키 노트 할 일의 DB/HTML 표식은 Font Awesome `\uf0c8`/`\uf14a`를 유지하고 `☐`/`☑`도 계속 읽는다. 화면에서는 표식을 투명하게 하이라이트한 뒤 벡터 체크박스를 덧그리므로 앱 글꼴·HTML 저장값·텍스트 왕복이 바뀌면 안 된다.
- **폰트 번들**: 앱 본문 폰트는 번들하지 않는다. `fonts/`에는 스티키 노트 체크박스용 Font Awesome 파일과 **D-Day Cover Tint용 Pretendard 정적 4굵기**(`Pretendard-Medium/SemiBold/Bold/ExtraBold.ttf`, 패밀리 `Pretendard`)를 둔다. Pretendard는 본문 폰트가 아니라 **UI 강조용**이며 `app_fonts.load_ui_fonts()`로 로드한다(미로드 시 Malgun 폴백). 서드파티 번들이지만 사용자 승인으로 예외 적용.
- **번들 리소스 경로**: 폰트·아이콘·이미지·Fluent SVG 경로는 반드시 `app_paths.resource_root()`를 기준으로 만든다. `Path(__file__).parent`로 리소스 경로를 조립하지 않는다. PyInstaller는 번들 모듈의 `__file__`을 `_MEIPASS/<이름>.pyc`로 잡으므로 `.parent`가 `_MEIPASS`와 같아지는 것은 **.py 파일이 번들 루트에 있을 때만** 성립한다. 모듈을 하위 폴더로 옮기면 소스 실행과 테스트는 통과하면서 EXE에서만 리소스를 잃는다. `tests/test_app_paths.py`가 frozen 분기와 이 패턴 재발을 검사한다.
- **폰트 크기**: QSS의 `font-size`는 정수 `px`만 사용한다. 소수점 픽셀 크기는 Windows Qt 렌더링에서 흐림을 만들 수 있다.
- **설정 위험 버튼**: `Factory Reset`은 `factoryResetButton` + `FIF.DELETE`(소프트 danger: 배경 `#FEF2F2`/테두리 `#F0C2C2`/글자 `#DC2626`, hover 시 `#DC2626` 채움), `앱 종료`는 `quitAppButton` + `FIF.POWER_BUTTON`(다크 `#1F2937`) 사용. 아이콘과 텍스트가 겹치지 않도록 왼쪽 padding과 최소 폭을 유지한다. **테스트 고정값**: factoryReset QSS는 `border-radius: 6px` + `padding: 5px 14px 5px 34px` + minWidth≥152, quit QSS는 `border-radius: 6px` + `padding: 5px 12px 5px 32px` + minWidth≥112를 유지한다(QSS에 `#28a745`/`#dc3545` 금지).
- **설정창 레이아웃(시안 A)**: `ScrollArea` 없이 800x560 고정/최소 크기를 유지하며, 레이아웃 최소 크기가 800×560을 넘지 않아야 한다(긴 저작권 라벨은 `setWordWrap(True)`+`QSizePolicy.Maximum`으로 창 폭을 강제하지 않게 한다). 5개 섹션(화면 표시/위젯·도구/데이터/보안/시스템)을 각각 **테두리 카드**(`_SettingsPanel`: 흰 배경 + 라운드 11px `#D7DAE2` 테두리, hover 배경/테두리 변화 없음, `_make_panel`)로 감싸 2열 배치한다. 헤더는 **밝은 바**(`panelHeaderBar` `#F6F6F6` + 라운드 상단/좌우/하단 경계 `#D7DAE2`) 안에 **블루 섹션 아이콘 + 진한 굵은 `StrongBodyLabel`**(`panelHeader`, `#1A1A1E`)로 두며, **딥 네이비(`#01295F`) 풀 바로 되돌리지 않는다**. 섹션 헤더 텍스트는 반드시 `StrongBodyLabel`(섹션명)이어야 한다(테스트 의존). 모든 컨트롤은 스크롤 없이 보여야 한다. 각 행은 `_add_row`로 `라벨-좌(고정폭) / 컨트롤-우`(우측 정렬 레일) + 행간 1px 구분선(`#F2F3F6`, 섹션 마지막 행은 `divider=False`). 모니터와 화면 위치는 **별도 두 행**으로 분리한다(콤보 / 4모서리 2×2 `posGrid`). 화면 위치는 4모서리(top/bottom × left/right)만 지원하며 `_position_btns`는 항상 4개. 카드 보조 설명은 넣지 않고 라벨은 짧게 쓴다. **캘린더 크기**는 콤보가 아니라 `CalendarSizePicker`(동일 크기 모니터 외곽 + 내부 앱 블록 크기로 `compact`/`medium`/`large` 표현, 선택 시 외곽·테두리·블록·캡션 블루 강조, `QFrame`+QSS, 외부 이미지 없음; `scaleChanged(str)` → `_on_scale_changed(scale)` → `SETTING_CALENDAR_SCALE` 저장)다.
- **전역 블루 액센트**: `main.py`에서 `setThemeColor(QColor("#2563EB"))`로 토글(`SwitchButton`)·슬라이더·포인트색을 단일 블루로 통일한다. 시스템 테마 자동 전환(`_check_theme`) 후에도 재적용한다. 집중모드 `#FF5A45`, 공휴일 `#D32F2F`, 오늘 남색 등 **명시 색상은 테마색과 무관**하므로 영향받지 않는다.
- **정상 종료 스티키 저장 게이트**: 트레이 `종료`와 설정의 `앱 종료`는 `MainCalendarWindow.prepare_for_quit()`을 먼저 호출한다. compact/medium에서는 등록된 플로팅 스티키를 표시 여부와 무관하게 모두 저장하고, `large`에서는 최신 편집 원본인 `StickySidePanel`만 저장해 숨은 구버전 플로팅 HTML의 역덮어쓰기를 막는다. 하나라도 실패하거나 패널 모드에서 패널이 없으면 fail-closed로 종료하지 않고 오류를 표시한다. compact/medium↔large 소유권 전환도 현재 원본 저장과 DB 재로드가 모두 성공한 뒤에만 완료하며 실패 시 기존 원본을 유지한다. 실패한 창/카드는 2초 저장 타이머를 다시 시작한다. 강제 프로세스 종료·전원 차단은 보장 범위 밖이다.
- **바로가기 인라인 관리**: 6개 슬롯의 DB 행과 스키마는 유지한다. 빈 슬롯 좌클릭은 파일/폴더 선택, 등록 슬롯 좌클릭은 실행, 우클릭은 이름 변경·경로 재지정·삭제를 제공한다. 끊긴 경로 좌클릭은 재지정 메뉴를 열고, 재지정은 사용자 표시 이름을 보존한다. 파일/폴더 드래그 등록과 기존 X 삭제도 계속 지원한다.
- **캘린더 셀 구조(2-모드)**: `CalendarDayButton`은 `mode`(`compact`/`expanded`)를 가진다. compact는 `[날짜 숫자 / 색상 심볼(■) / 총 일정 수]` 3행이며 개수 0이면 빈칸이다. expanded는 날짜 숫자와 일정 칩 스택을 표시하며, 셀 높이에 맞춰 칩 개수를 계산하고 넘치면 `+N 더`를 표시한다. medium 칩은 10px/16px/2px(글꼴/높이/간격), large 칩은 13px/22px/3px를 사용하고 실제 적용 폰트 메트릭으로 말줄임한다. 일정 추가·삭제·수정 시 `_refresh_cell_for_date()`로 해당 셀만 즉석 갱신한다.
- **일정 3슬롯 표시 팔레트**: `schedules.color`에는 기존 canonical 3색(`#FFD166`/`#4CC9F0`/`#FF6B6B`)만 슬롯 식별자로 계속 저장한다. 설정의 10색 후보는 `schedule_color_1/2/3`에 **표시색만** 저장하며 세 슬롯은 서로 다른 색이어야 한다. 렌더링은 `schedule_display_color()`를 거치고, 기존/가져온 미지의 색은 원문 그대로 표시한다. 팔레트 변경을 이유로 기존 `schedules` 행을 UPDATE하지 않는다.
- **캘린더 자유 이동**: 헤더 배경과 연월 라벨만 드래그 영역이며 내비게이션·검색·설정 버튼 입력을 가로채지 않는다. `QApplication.startDragDistance()` 이상 움직여야 드래그로 인정하므로 단순 클릭은 위치 모드를 바꾸지 않는다. 드래그 중에는 포인터가 있는 대상 화면의 물리 DPI로 5mm 픽셀 간격을 계산해 전역 x/y 격자에 즉시 스냅한다. 첫 드래그 완료 시 목적지 화면 기준으로 medium/large 크기를 다시 계산하고, 음수 좌표를 포함해 작업 영역 안의 가장 가까운 유효 5mm 격자로 확정한 다음 `calendar_x/y`, 대상 화면, 최근접 모서리를 저장하고 `calendar_position_mode="free"`로 전환한다. v17 기본은 `"corner"`라 기존 사용자의 과거 좌표는 자동 적용하지 않는다. 자유 위치에서 크기를 바꿀 때는 새 창 중심이 아니라 저장된 대상 화면을 우선한다. 화면 추가/제거/해상도·스케일·사이드바 변경 시 **목적지 화면 기준으로 크기를 다시 계산한 뒤** 좌표를 작업 영역 안으로 보정하고, 설정에서 모니터/화면 위치를 선택하면 `"corner"`로 복귀한다.
- **전체 투명도**: `SETTING_APP_OPACITY="app_opacity"`(기본 `"100"`, 범위 30~100). `MainCalendarWindow._apply_app_opacity()`가 메인과 스티키/D-Day/집중 위젯에 `setWindowOpacity`를 일괄 적용하며 새 위젯에도 현재값을 적용한다.
- **바탕화면 고정(Win+D)**: 기존 설정 키 `SETTING_KEEP_ON_SHOW_DESKTOP="keep_on_show_desktop"`(기본 `"1"`)는 데이터 호환을 위해 유지한다. Win+D는 바탕화면 셸 창을 z-order 앞으로 올리므로 최소화 복원만으로는 막을 수 없다. `ShowDesktopKeeper`는 셸 바탕화면이 foreground가 될 때만 메인+플로팅 창을 `HWND_TOPMOST`로 350ms pulse한다. pulse 종료 후에는 먼저 `HWND_NOTOPMOST`로 내리고, `GetWindow(desktop, GW_HWNDPREV)`로 감시 창을 제외한 데스크톱 앞의 첫 창을 찾아 그 창 뒤·데스크톱 앞에 삽입한다. 결과 순서는 **바탕화면 아이콘 < 기후노트 < 탐색기·브라우저 등 일반 창**이어야 한다. 다른 창이 foreground가 되면 pulse를 취소하고 같은 데스크톱 레이어로 즉시 재고정한다. Win+M은 `WindowStateChange` 복원으로 별도 방어한다. **영구 topmost 및 WorkerW/SetParent 재부모화 금지**. 토글 OFF는 타이머 취소+즉시 demote, 앱 종료/객체 파괴 시 native hook을 반드시 해제한다.
- **모니터 구성 변경 시 크기 재계산**: `medium`/`large`는 화면 크기에 비례하는 스케일이므로, 모니터가 바뀔 때 좌표만 clamp하면 안 된다. `_clamp_calendar_xy()`는 `max(0, 화면폭 - 창폭)`을 쓰기 때문에 창이 화면보다 넓으면 좌측 정렬만 하고 초과분을 처리하지 못한다. `_on_screen_changed()`와 `_finish_calendar_drag()`는 **둘 다** `_calendar_scale_geometry(scale, 목적지화면)`으로 크기를 먼저 다시 구한 뒤 좌표를 정한다. KVM 본체 전환으로 가로↔세로 모니터가 끊겼다 붙는 환경에서 실제로 재현된 결함이다(가로 기준 1880×1040 창이 세로 1080×1920 모니터에 그대로 남아 우측과 설정 버튼이 화면 밖으로 나감). `tests/test_ui_screen_change.py`가 양방향을 검사한다.
- **확장 캘린더**: `SETTING_CALENDAR_SCALE="calendar_scale"`(`compact`/`medium`/`large`, 기본 `compact`). 확장 시 좌측 바로가기 6슬롯, 가운데 큰 달력, 우측 일정 패널의 3열로 재배치하며 compact 복귀 시 일정 패널을 달력 하단으로 되돌린다. `large` 스케일에서는 우측 컬럼을 `[일정 → D-Day(미니) → 집중(미니, 라이브 미러) → 스티키(미니)]` 4구획으로 구성한다. 세 패널은 large에서 항상 존재하고 빈 상태를 컴팩트하게 표시한다. 진입 시 플로팅 스티키/D-Day/집중을 숨기며, 집중은 살아 있는 플로팅 창의 타이머를 미니 카드가 매초 미러링한다. 이탈 시 패널 저장 후 DB 최신값을 플로팅 창에 재로드/복원한다.
- **사이드바/캘린더 경계**: 앱 최초 표시 전에는 `self.sidebar.isVisible()`로 사이드바 활성 여부를 판단하지 않는다. 부모 창이 아직 숨겨져 있으면 Qt가 자식 위젯을 false로 보고 `sidebarActive`가 어긋날 수 있으므로, 저장된 사이드바 설정값을 기준으로 `sidebarActive`와 `expanded` dynamic prop을 적용한다.
- **구분선 색·두께**: 구조 구분선(사이드바 우측선, 캘린더 섹션·일정 패널·미니 패널 테두리, 캘린더 내부 가로선)은 모두 **중립 쿨 그레이 `rgba(206, 210, 216, ...)`(`#CED2D8`)** 단일 색을 쓴다. 파란기 도는 페리윙클(`rgba(180,190,220,...)`)로 되돌리지 않는다. 불투명도만 위치별로 다르다(사이드바 150 / 패널·섹션 테두리 180 / 캘린더 내부 가로선 120). **테두리 이중화(2px) 금지**: 테두리 있는 두 면이 맞붙는 쪽은 한쪽 테두리를 제거해 이음새를 1px로 유지한다 — expanded `calendarSection`은 `border-left/right:none`, `large` 우측 컬럼에서 세로로 쌓이는 `[일정 → D-Day → 집중 → 스티키]` 중 **아래 3개 패널(`ddaySidePanel`/`focusSidePanel`/`stickySidePanel`)은 `border-top:none`**(위 패널의 아래 테두리 하나만 남김). 단, 콘텐츠 강조 테두리(스티키/D-Day 미니 카드의 노트 고유색, 집중 카드 `rgba(255,90,69,90)`)는 구분선이 아니므로 이 규칙에서 제외한다.
- **팝업 메뉴 DWM 테두리**: Win11에서 `RoundMenu` 계열 팝업 주위에 생기는 넓은 사각 테두리는 **OS(DWM)가 그리는 창 테두리**다(그림자 여백 때문에 창이 메뉴보다 커서 도드라짐). `popup_border_fix.install_popup_border_fix(app)`가 main에서 설치되어 자동 우회한다. **Qt 쪽 수정(그림자 제거/여백 축소/메뉴 QSS)으로는 지워지지 않으니 재시도하지 말 것**(실측 확인됨).
- **설정창 위치**: 달력이 화면 끝 코너에 있으면 설정창이 화면 밖으로 열려 우측 컬럼이 잘릴 수 있다. `_on_settings`가 표시 후 `QTimer.singleShot(0, ...)`으로 `_clamp_window_to_screen()`을 호출해 작업 영역 안으로 이동시킨다.
- **설정창 높이 = 560 필수**: 창 높이가 레이아웃 최소치(시스템 3행 기준 546px)보다 작으면 우측 컬럼 행들이 세로 압축되어 고정높이(34px) 버튼이 행 구분선을 침범해 '겹쳐 보인다'. 무스크롤 고정 창에 행을 추가할 땐 `layout().minimumSize()` ≤ 창 높이를 실측 확인할 것(v3.1a에서 520→560 정정).
- **DB 마이그레이션**: 현재 `user_version=17`. v13→v14는 `app_opacity`/`calendar_scale`, v14→v15는 바로가기 6번째 슬롯, v15→v16은 `keep_on_show_desktop`, v16→v17은 `schedule_color_1/2/3`과 `calendar_position_mode`를 각각 `INSERT OR IGNORE`로 추가한다. v16→v17은 테이블/컬럼/기존 일정 행/암호문을 수정하지 않는다. Export/Import는 `app_settings`를 포함하되 `privacy_pin`은 제외한다.
- **마이그레이션 전 백업**: `main._initialize_database()`는 read-only 건강 검사와 v3.5 최초 보호본, `backup_before_migration()`이 모두 성공한 뒤에만 `migrate()`를 호출한다. 구 DB는 `Connection.backup()`으로 `backups/calendar_pre_v17_v{version}.db`에 최신 snapshot을 만들고 `quick_check`와 버전을 확인한 뒤 원자 교체한다. 백업 생성·검증·교체가 실패하면 기존 snapshot과 원본 DB를 보존한 채 시작/마이그레이션을 중단한다. raw 파일 복사로 WAL DB를 백업하지 않는다.
- **Export/Import 무손상 규칙**: Export v2는 명시적 read transaction의 한 snapshot에서 읽고 민감 필드 하나라도 복호화하지 못하면 파일 생성을 중단한다. Import는 모든 구조·타입·범위·참조를 DB write 전에 검증하고 한 transaction으로 병합한다. 같은 날짜의 기존 메모와 비어 있지 않은 바로가기 슬롯은 덮어쓰지 않으며, focus `source_id`를 새 ID로 remap한다. 레거시 focus session은 무관한 현행 위젯에 연결하지 않는다. 일정/위젯은 안정적인 원본 ID가 없어 동일 파일 반복 Import 시 중복될 수 있으므로 성공 안내에 이를 명시한다.
- **공휴일 표시**: 공휴일 날짜 숫자는 빨강(`#D32F2F`), 음력 표시 설정과 무관하게 항상. 오늘 셀은 남색 배경+흰 숫자로 우선. 공휴일명은 선택 시 하단 `holiday_info_label`(빨강)에 항상 표시. `_show_lunar` 설정은 이제 하단 음력 텍스트만 제어한다.
- **오늘 재동기화(자정 롤오버)**: 오늘 날짜(`_today`)는 `__init__`에서 1회 계산되므로, **트레이 상주 앱**(`setQuitOnLastWindowClosed(False)`)이 자정을 넘기면 캘린더가 어제에 박제된다(과거: '오늘' 버튼을 눌러야만 갱신). `toggle_visibility` show 시 `_sync_to_today_if_changed()`가 날짜 변경을 감지하면 `_on_today()`로 오늘 이동(같은 날이면 보던 달 유지). 표시 중 자정 넘김은 30초 주기 타이머에 연결된 `_check_day_rollover()`가 오늘 하이라이트만 갱신(보던 달·선택 유지). **숨김 상태에서는 롤오버를 소비하지 않아** `_today`가 어제로 남고 다음 show에서 이동이 트리거된다. `_on_today()`는 `_today`도 함께 갱신한다.
- **공휴일 데이터**: `holidays.py`는 생성물이며 **`fetch_data.py`로만 갱신**한다. 미래 연도를 코드로 임의 계산·추정해 채우면 안 된다. API가 제공하는 범위(현재 2025-2027)만 사용. `holiday_last_year()` 함수가 만료 알림 기준 연도를 반환하므로 생성 시 반드시 포함해야 한다.
- **삭제 정책**: 스티키 노트 닫기는 `db.trash_sticky_note()`로 **휴지통 이동(soft-delete)**한다(즉시 삭제 아님). 닫기 확인 팝업은 스티키 창을 parent로 둔 `MessageBox`가 아니라 parent 없는 top-level `Dialog`로 띄워 작은 스티키 내부에서 잘리지 않게 한다. 휴지통(우측 메뉴 → 휴지통, `ui_trash.py`)에서 `restore_sticky_note()`로 원위치 복구, `purge_sticky_note()`로 개별 영구삭제, `empty_sticky_trash()`로 전체 비우기. 휴지통은 `STICKY_TRASH_LIMIT(=50)`개로 제한되어 초과 시 오래된 것부터 자동 영구삭제(`_enforce_trash_cap`, 로그 기록). 영구삭제/비우기는 확인 팝업만(PIN 불필요). 백업(Export/Import)에 휴지통 항목 포함. D-Day/집중 모드/일정 휴지통은 미구현(단, `large` 모드 미니 패널에서 D-Day는 카드 X로 즉시 영구 삭제, 집중은 카드 X로 세션 종료 — 둘 다 확인 팝업 경유).
- **스티키 미니 패널**: large 우측 `StickySidePanel`의 공용 툴바(굵게·할 일·텍스트 색상·배경 색상)는 포커스된 카드에만 작용한다(툴바 버튼 `NoFocus`). 카드별 X는 `trash_sticky_note()`로 휴지통 soft-delete 후 `note_trashed`를 전파해 메인의 숨겨진 플로팅 창 레지스트리를 정리한다.
- **자동정렬**: `ui_main.py`의 `_on_arrange_sticky_notes()`는 스티키/D-Day/집중 모드 위젯을 함께 정렬한다. 자유 이동 뒤에는 저장된 모서리 설정이 아니라 캘린더 중심이 속한 실제 화면과 최근접 모서리를 기준으로 빈 공간을 계산한다. 우측 모서리 배치에서는 스냅 반올림 때문에 캘린더의 우측 여백이 줄어들지 않도록 `_snap_not_past_right()` / `_right_aligned_grid_x()`를 사용한다.
- **집중 모드 UI**: 기본 Ambient는 남은 시간을 숨기고 목표·진행률%·얇은 원형 링·흰 배경이 제거된 투명 `tomato_mini.png`만 표시한다. 기본 배경은 `#FFFFFF` → `#EEF6FF` → `#DDE8FF` 대각선 그라데이션이며 포인트 색은 `#FF5A45`이다. Hover Glance는 같은 폭에서 세로만 늘리고, mini 토마토는 숨기며, 왼쪽에는 모드·남은 시간(`MM:SS`)·다음 휴식(`HH:MM AM/PM`)을, 오른쪽 아래에는 흰 배경이 제거된 투명 `tomato.png`를 `TOMATO_IMAGE_SIZE = 50`으로 표시한다. Hover Glance의 큰 토마토를 클릭하면 22개 응원 문구 중 하나를 랜덤으로 고른 말풍선을 토마토 아래에 3초간 표시하되, 말풍선 창 외곽은 투명해야 한다. 큰 토마토에는 Qt 기본 툴팁을 달지 않는다. 위젯 창 크기는 `AMBIENT_SIZE`/`GLANCE_SIZE`로 고정한다. Hover Glance에 `진행률` 행은 두지 않는다. 더블클릭 편집 패널은 제공하지 않으며, 설정을 바꾸려면 종료 후 새로 만든다.
- **집중 모드 위젯 제한**: 집중 모드 위젯은 1개만 생성/표시한다. `enforce_widget_limits()`가 앱 시작 시 최신(id 큰) 1개만 남기고 초과분은 데이터 보존 상태로 `is_open=0` 정리한다. 정리분이 있으면 모달 경고를 띄운다. 생성 제한 카운트는 `isVisible()`이 아니라 등록 딕셔너리 기준이다.
- **D-Day 위젯 제한**: D-Day 위젯은 최대 5개만 생성/표시한다. `enforce_widget_limits()`가 앱 시작 시 최신(id 큰) 5개만 남기고 초과분은 삭제 없이 `is_open=0` 정리한다. 생성 제한 카운트는 `isVisible()`이 아니라 등록 딕셔너리 기준이다.
- **D-Day Cover Tint(디자인)**: D-Day 플로팅 위젯(`ui_dday.py`)과 large 미니 카드(`ui_dday_panel.py`)는 **진한 커버색 단색 배경 + 전부 흰 타이포**다. 팔레트 `DDAY_COVER_COLORS`(sky `#46679C` 기본 / yellow `#A8801F` / mint `#2E8F6E` / pink `#B25C8B`)는 **스티키 전용 `STICKY_COLORS`/`STICKY_HEADER_COLORS`와 분리**한다(공유 상수 오염 금지). DB에 저장된 구 파스텔 색은 `dday_cover_color()`가 커버색으로 매핑해 렌더한다(저장값 변경 없이 표시만 매핑, 데이터 보존). 카운트는 색이 아니라 **표기+명도**로 상태 구분: 미래 `D-N`·당일 `D-Day`는 흰색(`#FFFFFF`), 지남 `D+N`은 `rgba(255,255,255,140)`(공백 없는 표기). 플로팅 위젯은 **소프트 드롭 섀도우 + 옅은 흰 헤어라인(`rgba(255,255,255,HAIRLINE_ALPHA)`)으로 배경에서 분리**(창을 `SHADOW_MARGIN`만큼 키워 그림자 여백 확보, 좌표 규약은 창 좌표 그대로 유지, 불변식 `SHADOW_MARGIN ≥ SHADOW_BLUR + SHADOW_OFFSET_Y`). 미니 카드(`ui_dday_panel.py`)는 흰 패널 위라 대비 문제가 없어 종전대로 **테두리 없음** 유지. radius 18(플로팅)/12(미니), 좌하단 큰 카운트·우하단 날짜 구도. 카운트/이름/날짜 폰트는 **Pretendard**를 `_dday_font()`로 `QFont` 픽셀 크기·굵기 직접 지정(QSS font-size/weight 미사용, 미로드 시 Malgun 폴백). 닫기 X는 커버 위 가독을 위해 흰색을 직접 그리는 `_CoverIconButton`. large 우측 컬럼의 `ddaySidePanel` **패널 컨테이너**는 스택 이음새 규칙(흰 배경·`border-top:none`·무radius)을 그대로 유지하고 **미니 카드에만** 커버 틴트를 적용한다.
- **집중 모드 세션**: 집중 완료 시 소리 없이 위젯 색만 미세하게 바꾸고 `집중 모드 완료, N분 휴식하시겠습니까?` 버튼 알림을 띄운다. `휴식 시작` 수락 시 break phase로 진입하고, `건너뛰기`면 완료 상태로 남긴다.
- **집중 모드 모드명**: 사용자 표시에는 `25/5` 같은 축약 숫자를 쓰지 않는다. `짧은 집중 (25분 집중/5분 휴식, 포모도로)`, `깊은 집중 (50분 집중/10분 휴식)`, `몰입 블록 (75분 집중/15분 휴식)` 형식을 유지한다.
- **집중 모드 저장**: `focus_widgets.goal`과 `focus_sessions.goal`은 암호화 저장한다. `focus_sessions`는 완료 기록과 회고 필드(`focus_rating`, `distraction`)를 담는다.

## Known Investigation: 특정 PC 설정/휴지통 멈춤 (2026-08-05)

- **확인된 제보**: 대부분의 PC는 정상이지만 특정 PC의 기본 모드에서 더보기의 `설정` 또는 `휴지통`을 누르면 잠깐 로딩 커서가 나온 뒤 기후노트 입력이 멈춘다. 같은 더보기 메뉴의 `앱 업데이트`는 정상이며 `%LOCALAPPDATA%\MyDesktopCalendar\error.log`에는 기록이 없다.
- **배제된 설명**: 설정창이 뒤나 화면 밖에 열렸다는 사실만으로 메인 창 입력이 막히지는 않는다. 같은 메뉴의 업데이트 창이 열리므로 `RoundMenu` 전체나 일반 top-level 창 생성 문제로도 단정하지 않는다.
- **현재 가설(미확정)**: 설정과 휴지통이 공통으로 GUI 스레드에서 수행하는 동기 DB 조회/WAL 잠금이 1순위 공통 후보다. 설정에는 별도로 `available_system_fonts()` → `QFontDatabase.families()` 전체 열거가 있어 손상·충돌 글꼴 또는 Windows Font Cache 정지도 후보지만, 이것만으로 휴지통 멈춤까지 설명할 수는 없다.
- **진단 원칙**: import 직전/생성자 진입/DB 조회 전후/글꼴 열거 전후/show 완료를 파일에 먼저 `flush`+`fsync`하여 마지막 통과 지점을 남긴다. 원인이 확인되기 전에는 글꼴만 고치고 전체 문제가 해결됐다고 판단하지 않는다.
- **사용자 조치 순서**: 글꼴 열거에서만 멈추면 최근 설치 글꼴 제거 → `제어판 > 모양 및 개인 설정 > 글꼴 > 글꼴 설정`의 기본값 복원 → 재부팅 → Windows Font Cache 초기화 순으로 점검한다. DB 단계에서 멈추면 앱 완전 종료·중복 프로세스·보안 프로그램의 DB 잠금을 먼저 확인한다.

## v3.6 Release Verification Snapshot

검증일: **2026-08-18**

- 앱 런타임 코드는 v3.5와 동일하다. v3.5 대비 변경분은 표시 버전(`app_info.py`), 제3자 라이선스 고지, 저장소 정비뿐이며 DB 스키마·암호화·UI 동작은 그대로다. 현재 `user_version=17` 유지.
- 전체 테스트: `518 passed`, 실패 0건. 외부 QFluentWidgets의 SciPy deprecated import 경고 1건만 존재. venv는 `requirements-lock.txt`와 8개 직접 의존성이 모두 일치한다.
- 빌드 산출물: `dist/기후노트_v3.6.exe`, 58,279,798 bytes, SHA-256 `C6763B023DBCDAB26CFA7D2800DADD98277FFE1201A641423F930220A1BAF6FB`. Windows File/Product Version `3.6.0.0`, OriginalFilename `기후노트_v3.6.exe`, Authenticode `NotSigned`.
- 번들 구성: PyInstaller `Analysis-00.toc` 기준 736개 항목, 원본 152.4 MB. 폰트·아이콘·Fluent SVG·토마토 이미지·라이선스가 모두 포함됐고 이번에 추가한 `LGPL-3.0.txt`와 `cryptography-LICENSE{,.APACHE,.BSD}.txt`도 들어갔다.
- 신규 설치 격리 실행: 별도 임시 `LOCALAPPDATA`와 `CLIMATENOTE_SKIP_STARTUP_REFRESH=1`에서 프로세스가 정상 응답했다. 신규 DB는 `user_version=17`, `integrity_check=ok`, FK 위반 0건, `.salt` 32 bytes, 검증 통과한 일일 `.cnbak` 1개, 오류 로그 0 bytes였다. `.cnbak`은 `calendar.db`·`.salt`·`manifest.json` 3개만 담았고 manifest의 SHA-256이 실제 페이로드와 일치했다.
- v3.5 데이터 업데이트 시나리오: 일정 3·메모 2·열린 스티키 1·휴지통 스티키 1·D-Day 1·집중 위젯 1·집중 세션 1·바로가기·사용자 설정을 채운 v17 데이터셋에서 EXE를 실행했다. **사용자 테이블 8개의 raw 행 해시가 전부 실행 전과 동일했고 `.salt` bytes도 동일했다.** 복호화 평문 12건(일정·메모·D-Day·집중 목표·집중 세션·바로가기·열린/휴지통 스티키·설정)이 모두 일치했다. `calendar_pre_v35_*.cnbak`과 일일 `.cnbak`이 각각 1개 생성됐고 오류 로그는 0 bytes였다.
- Windows Defender: 엔진 `1.1.26070.7`, 보안 인텔리전스 `1.457.219.0`(2026-08-18 갱신) 사용자 지정 검사에서 신규 탐지 0건.

### 이번 검증에서 확인된 문제

- **UPX가 실제로 적용되지 않는다.** `build.spec`은 `upx=True`이고 `docs/ARCHITECTURE.md`는 "UPX-compressed"라고 적었지만 UPX 실행 파일이 PATH에도 `upx_dir`에도 없어 PyInstaller가 압축을 건너뛴다. 문서와 실제가 어긋난 상태이므로, UPX를 도입하든 문서를 고치든 한쪽으로 맞춘다.
- **EXE 크기가 v3.5보다 3,495,772 bytes 작은 이유를 확정하지 못했다.** 앱 코드가 동일한데 크기가 줄었다. v3.5 EXE가 `dist/`에 남아 있지 않고 당시 빌드 TOC도 덮어써져 직접 비교가 불가능하다. 기능 검증은 모두 통과했으므로 배포를 막지는 않지만, 다음 빌드에서는 이전 산출물과 TOC를 보존해 비교할 수 있게 한다.
- **임시 WAL/SHM 파일이 정리되지 않고 누적된다.** 백업 검증용 `.backup-validate-*.db`와 `.auto-snapshot-*.db`는 삭제되지만 짝인 `-wal`/`-shm`이 남는다. 실제 사용자 폴더에서 2026-08-15 21:00(v3.5 최초 실행)부터 64개·약 1.0 MB가 쌓인 것을 확인했다. 데이터 손상은 없고 정상 파일과 백업 회전은 정상이지만, 사용자가 문제 발생 시 열어보는 폴더가 지저분해진다. v3.5부터 있는 결함이며 v3.6에서도 동일하다. 후속 버전에서 임시 DB 삭제 시 `-wal`/`-shm`을 함께 지우도록 고친다.

### 남은 수동 확인

- 실제 보이는 창에서 설정 하단 v3.6 문구와 종료·바로가기 동작 확인
- 실제 Win+D 직후 Explorer/브라우저 전환 육안 확인
- 음수 좌표·혼합 DPI 다중 모니터 육안 확인
- 2026-08-05 접수된 특정 PC의 설정/휴지통 멈춤은 여전히 미해결

## v3.5 Release Verification Snapshot

검증일: **2026-08-15** (기술 검증 완료, 배포 진행 결정; 라이선스 정비는 후속 과제로 보류)

- 전체 테스트: `518 passed`, 실패 0건. 외부 QFluentWidgets의 SciPy deprecated import 경고 1건만 존재.
- 데이터 보호 전용: `tests/test_data_safety.py` 22개 통과. 정상/누락/손상 salt, 암호화 대상 6개 테이블 전수 검사, DB+salt+manifest 묶음, 당일 정상본 불변, 최근 5일 회전, 정리 실패 격리, 비회전 보호본을 검증했다.
- v3.4 호환: v17 DB에 일정·메모·스티키·D-Day·집중 위젯/세션·바로가기·사용자 설정을 채운 뒤 v3.5 초기화를 두 번 반복해도 모든 사용자 테이블 raw 행, 암호문, ID/sequence와 `.salt` bytes가 완전히 동일했다. `calendar_pre_v35_*.cnbak`은 1개만 생성됐다.
- 시작 실패 안전성: DB/salt/암호문이 일치하지 않으면 최초 보호본·마이그레이션·일일 백업·메인 창 생성을 시작하지 않는다. 이 검사는 DB와 salt를 새로 만들거나 수정하지 않는다.
- 현재 `user_version=17` 유지. v3.5 구현은 테이블/컬럼 추가와 기존 암호문 일괄 재작성을 하지 않는다.
- 빌드 산출물: `dist/기후노트_v3.5.exe`, 61,775,570 bytes, SHA-256 `3D5971E73559AB8C4FE7FE803A41EFAD8C96D36A8A04FBD8549C710D4694BC7D`. Windows File/Product Version `3.5.0.0`, 필수 폰트·아이콘·SVG·토마토 이미지·라이선스 포함, Authenticode `NotSigned`.
- 신규 설치 격리 실행: 별도 임시 `LOCALAPPDATA`와 `CLIMATENOTE_SKIP_STARTUP_REFRESH=1`에서 EXE가 정상 응답했다. 신규 DB는 `user_version=17`, `integrity_check=ok`, FK 위반 0건, `.salt` 32 bytes, 검증 가능한 일일 `.cnbak` 1개, 오류 로그 0 bytes였다.
- v3.4 형식 업데이트 격리 실행: 암호화 대상 7행과 휴지통·바로가기·사용자 설정을 채운 v17 데이터셋에서 `calendar_pre_v35_*.cnbak`과 일일 `.cnbak`이 각각 1개 생성됐고 salt가 유지됐다. 일정·메모·D-Day·집중 위젯/세션·바로가기·설정 raw 행은 동일했다. 열린 스티키는 기존 시작 동작이 동일 HTML을 자동 저장해 Fernet token만 갱신했으며 복호화 본문은 byte-equivalent였고 실행 전 raw 행은 pre-v3.5 묶음에 보존됐다.
- 복구 리허설: 앱 종료 상태의 별도 임시 폴더에 일일 `.cnbak`의 `calendar.db`와 `.salt`만 설치한 뒤 건강 검사와 EXE 재실행을 통과했다. 일정·메모·열린/휴지통 스티키·D-Day·집중 위젯/세션·바로가기·사용자 설정을 모두 복구했고 DB `integrity_check=ok`, FK 위반 0건, 오류 로그 0 bytes였다.
- Windows Defender: 엔진 `1.1.26070.7`, 보안 인텔리전스 `1.457.172.0`(2026-08-15 갱신) 사용자 지정 검사에서 탐지 0건, 종료 코드 0.
- 의존성: `pip check` 충돌 0건. 로컬 배포 메타데이터의 `PySide6-Fluent-Widgets 1.11.1`은 `GPLv3`이다. 사용자는 2026-08-15에 라이선스 정비를 후속 과제로 보류하고 현 산출물 배포를 진행하기로 결정했다. 이는 라이선스 적합성 확인이나 준수 완료 판정이 아니다.
- 남은 수동 확인: 실제 보이는 창에서 설정 v3.5 문구·종료/바로가기 동작을 확인하고, 실제 Win+D 후 Explorer/브라우저 전환과 음수 좌표·혼합 DPI 환경을 육안 점검한다. 배포 후라도 재현 가능한 환경이 마련되면 결과를 이 문서에 추가한다.

## Deferred Release Work: 라이선스·배포 정비 (2026-08-15)

> **상태: HOLD — 후속 버전에서 반드시 재개.** 2026-08-18에 기관 내부 GitLab 소스 공개(GPLv3)와 고지 보강을 진행했으나, 이것만으로 배포 라이선스 검토가 끝난 것은 아니다. **남은 것**: PyInstaller 산출물 기준 전수 SBOM, PySide6/Qt LGPL 경로에서 수령자의 교체·재링크 가능성(one-file 배포) 판단, 기관 법무·저작권 담당 확인, Authenticode 서명. **끝난 것**: 프로젝트 최상위 `LICENSE`(GPLv3) 추가, `licenses/THIRD_PARTY_NOTICES.txt`에 PySide6/Qt·shiboken6·cryptography·pysidesix-frameless-window 항목과 원문 추가, 소스 공개 경로 확보(`origin/main`).

- **QFluentWidgets 경로 확정(둘 중 하나)**
  - GPLv3 경로: 기후노트 소스 공개 권한자를 먼저 확인하고, 앱의 적용 라이선스를 명시한다. 배포 EXE와 정확히 대응하는 전체 소스, `build.spec`/`build_app.py`, 의존성 잠금, 리소스, 빌드 안내, GPLv3 원문과 QFluentWidgets 1.11.1 대응 소스를 수령자가 EXE만큼 쉽게 받을 수 있게 제공한다.
  - 상용 경로: 저작권자로부터 `PySide6-Fluent-Widgets 1.11.1`의 Windows PyInstaller one-file, 대한민국 정부기관 업무용·무상 배포 범위를 포함하는 서면 라이선스를 확보한다. 영구 재배포, 개발자/사용자·기관 범위, 적용 버전과 업데이트, 기존 산출물 적용 여부, 필수 고지사항을 계약서·메일·영수증으로 보존한다. Pro 제품 구매가 상용 재배포권을 자동 포함한다고 가정하지 않는다.
- **PySide6/Qt 별도 확인**: LGPLv3/GPLv3 또는 Qt 상용 조건 중 적용 경로를 기록한다. 오픈소스 경로라면 PySide6/Qt 사용 사실과 라이선스 원문, 실제 사용 라이브러리의 대응 소스 획득 방법, 사용자의 교체·재링크 및 역공학 권리를 제한하지 않는 배포 방식을 문서화한다. 필요하면 one-file 배포의 재링크 가능성을 별도로 검토한다.
- **실제 산출물 기준 전수 조사**: `requirements-lock.txt` 전체가 아니라 PyInstaller `Analysis-00.toc`/최종 EXE에 실제 포함된 Python·PySide6/Qt·암호화·이미지·아이콘·폰트 구성요소로 SBOM을 만들고, 이름/버전/저작권자/라이선스/원문/소스 URL/수정 여부를 기록한다.
- **배포 고지 완성**: 2026-08-18 기준 일부 진행됐다.
  - ✅ 프로젝트 최상위 `LICENSE` — GPLv3 전문 674줄.
  - ✅ `licenses/THIRD_PARTY_NOTICES.txt` — 기존 Pretendard·Font Awesome·PySide6-Fluent-Widgets에 더해 **PySide6 6.10.2 / Qt 6.10.2(shiboken6 포함), cryptography 46.0.4, pysidesix-frameless-window 0.8.0** 항목을 추가했다.
  - ✅ `licenses/LGPL-3.0.txt` — FSF 정본(https://www.gnu.org/licenses/lgpl-3.0.txt), 7,652 bytes, SHA-256 `E3A994D82E644B03A792A930F574002658412F62407F5FEE083F2555C5F23118`. 설치 배포판 동봉 사본과 본문 일치(끝 개행만 차이) 확인.
  - ✅ `licenses/cryptography-LICENSE{,.APACHE,.BSD}.txt` — 설치 배포판 `cryptography-46.0.4.dist-info/licenses/`에서 복사.
  - ✅ 소스 공개 경로 — `origin/main`(기관 내부 GitLab Public). GPLv3 대응 소스 제공 범위가 EXE 배포 범위와 일치한다.
  - ⬜ 앱 설정에서 접근 가능한 오픈소스 고지 화면 또는 동봉 문서.
  - ⬜ 배포 EXE와 정확히 대응하는 소스 묶음(`기후노트_v3.5_소스코드.zip`) 생성 여부 결정. 소스가 GitLab에 공개되어 있으므로 별도 zip이 필요한지 함께 판단한다.
- **증빙 보존 및 완료 조건**: EXE·소스 묶음·SBOM·라이선스 문서·상용 계약(해당 시)의 SHA-256과 배포 게시 위치를 기록한다. 기관 법무/저작권 담당 확인이 필요한 배포 범위(동일 기관 내부인지, 타 기관까지 전달되는지)를 남긴다. 위 항목이 모두 충족되기 전에는 이 과제를 완료 처리하지 않는다.
- **별도 후속 항목**: 현재 EXE는 Authenticode `NotSigned`다. 기관 정책이 요구하면 코드 서명을 적용하고 서명 상태·인증서 주체·타임스탬프를 기록한다. 이는 라이선스 정비와 별개다.

## v3.4 Release Verification Snapshot

검증일: **2026-08-04**, 정식 산출물 갱신: **2026-08-06**

- 전체 테스트: `467 passed`, 실패 0건. 외부 QFluentWidgets의 SciPy deprecated import 경고 1건만 존재.
- 추가 검사: 변경 핵심 Python 파일 `py_compile` 통과, `pip check` 의존성 충돌 0건, `git diff --check` 통과.
- 격리 실행: `CLIMATENOTE_SKIP_STARTUP_REFRESH=1`과 별도 임시 `LOCALAPPDATA`에서 8월 4일 실제 UI 창을, 8월 6일 최종 빌드의 프로세스 응답 상태를 확인했다. 신규 DB는 `user_version=17`, `quick_check=ok`, FK 위반 0건, 오류 로그 0 bytes였다.
- Windows 네이티브: 실제 바탕화면 아이콘 호스트가 `Progman`의 `SHELLDLL_DefView`임을 확인했다. 임시 Qt 창 실측에서 기후노트 역할 창은 데스크톱 바로 위 rank 1, 일반 창은 rank 319로 더 위였고, 기후노트 역할 창은 non-topmost였다. 실제 Win+D 키 입력은 사용자 화면을 방해하지 않도록 자동 전송하지 않았다.
- 검증 산출물: `dist/기후노트_v3.4.exe`, 61,757,130 bytes, SHA-256 `582090BFA381C08AAA9339E4ADC360BCEFF616F2D1BB20ECCEC3366062ADD25B`. Windows File/Product Version `3.4.0.0`, 필수 폰트·이미지·라이선스와 변경 모듈 포함, Windows Defender(서명 `1.457.27.0`, 2026-08-06 갱신) 탐지 0건.
- 사용설명서: `manual.qmd`를 v3.4 기준으로 갱신하고 `output/pdf/기후노트_v3.4_사용설명서.pdf` 5페이지를 전 페이지 렌더링 확인했다. PDF 221,956 bytes, SHA-256 `D8C1CF65453BF2FCA6E2948CCAB8CEE70EA4838AEDB37E4000D2BB018A1C187E`.
- 모니터 환경: 실제 1920×1080 모니터 2대가 모두 100% 배율, 양의 좌표 `(0,0)`/`(1920,0)`로 인식됐다. 음수 좌표·150%/200% 혼합 DPI는 자동 테스트만 통과했으며 실제 장비 육안 확인은 남아 있다.
- 외부 게시 전 운영 확인: 산출물은 Authenticode `NotSigned`. PySide6-Fluent-Widgets 1.11.1의 GPLv3 준수 방식 또는 별도 상용 라이선스를 확정하고, 실제 Win+D 직후 Explorer/브라우저 전환과 혼합 DPI 다중 모니터를 육안 확인한다.
- 산출물 보존 상태: 2026-08-06 현재 `dist`에는 최종 v3.4 EXE만 있으며 아래 v3.3 EXE의 크기·해시는 역사적 검증 기록이다.

## v3.3 Release Verification Snapshot

> 이 스냅샷은 v3.4 변경 전 v3.3 릴리스 후보의 역사적 검증 기록이다. v3.4 배포 근거로 간주하지 않는다.

검증일: **2026-07-23**

- 전체 테스트: `461 passed`, 실패 0건. 외부 QFluentWidgets의 SciPy deprecated import 경고 1건만 존재.
- 추가 검사: 핵심 Python 파일 `py_compile` 통과, `pip check` 의존성 충돌 0건, 150%/200% DPI 관련 테스트 각각 통과.
- 데이터 보존: 실사용 v16 DB를 읽기 전용 확인했을 때 `quick_check=ok`, FK 위반 0건. SQLite 온라인 snapshot 복제본을 빌드 EXE로 v17까지 올린 뒤 사용자 테이블 raw 행과 기존 설정의 SHA-256이 사전 백업과 동일했다. 새로 생긴 행은 `schedule_color_1/2/3`과 `calendar_position_mode`뿐이다.
- Windows 네이티브: 메인+스티키+D-Day+집중 5개 창의 Win+D 생존과 pulse 후 non-topmost 복귀를 확인했고, Win+M 10회 반복 실패 0건, native hook 해제 성공.
- 검증 산출물: `dist/기후노트_v3.3.exe`, 61,754,273 bytes, SHA-256 `C95E9982C99ABF9A7482E585A5A3F6908CBEC9C834EDBB93D3F6788747907892`. Windows File/Product Version `3.3.0.0`, 필수 폰트·이미지·라이선스 포함, Windows Defender 탐지 0건.
- 배포 보류 항목: 산출물은 Authenticode `NotSigned`. PySide6-Fluent-Widgets 1.11.1 메타데이터는 GPLv3이므로 외부 배포 전에 GPLv3 준수 방식 또는 별도 상용 라이선스를 확정한다. `dist/소스코드`는 현재 비어 있다.
- 마지막 수동 게이트: 실제 듀얼/트리플 모니터(음수 좌표·혼합 DPI 포함)에서 드래그→재시작→크기 변경→모니터 분리, Win+D 직후 Explorer/브라우저 전환을 육안 확인한다.

## Security Coding Rules (행안부 CODEMIND 4.5)

> 상세 규칙·예제: [`docs/CODING_STANDARDS.md`](docs/CODING_STANDARDS.md)

| 규칙코드 | 핵심 준수사항 |
|---|---|
| **0011_IMPRAUTH** | PIN 필요 기능(Export/Import, 설정변경)은 `_validate_pin()` 통과 후에만 실행. 단, **데이터 초기화(Factory Reset)는 사용성 결정으로 PIN 미적용** — 확인 다이얼로그로 우발 실행만 방지 |
| **001D_ONEWAYHASH** | 해시 시 `secrets.token_bytes(32)` 이상 Salt 필수. SHA-256 단독 패스워드 저장 금지 |
| **0023_NOACTION** | `except` + `pass` 단독 금지. 로깅·알림·복구처리 중 하나 이상 필수. 불가피 시 이유 주석 |
| **0024_NOCHKERR** | `bare except:` 금지. 예외는 타입별 세분화. `except Exception:` 은 최후 수단 (로깅 필수) |
| **0026_RESLEAK** | 파일은 `with open` 필수. DB는 `_connection()` 사용. Qt 팝업은 `deleteLater()` 호출 |

## Reference Docs

| 문서 | 내용 |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Data Flow & Security, DB Schema, Build & Constraints |
| [`docs/UI_PATTERNS.md`](docs/UI_PATTERNS.md) | UI 컴포넌트 패턴, 레이아웃, 색상, IME 이슈 |
| [`docs/TESTING.md`](docs/TESTING.md) | 테스트 구조, CODEMIND 점검 이력 |
| [`docs/CODING_STANDARDS.md`](docs/CODING_STANDARDS.md) | 행안부 5개 보안 규칙 상세 (CWE, 예제 코드) |
