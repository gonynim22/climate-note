# Architecture Reference

## Data Flow & Security

- **Single Instance**: `msvcrt.locking` on `.lock` file prevents duplicate instances from corrupting the DB.
- **Encryption**: Hardware-derived key (MachineGuid + Windows username; MAC fallback and legacy decryption supported) + PBKDF2HMAC (200k iterations) → Fernet (AES-128). Common derivation logic in `_derive_fernet_key()`. Fernet instance is **cached** at module level; cache is invalidated on Factory Reset.
- **Path Validation**: `security.validate_app_path()` shared between `security.py` and `database.py` to prevent path traversal.
- **SQLite**: WAL journal mode + 5s busy timeout. All DB functions use `@contextmanager _connection()` — no manual try/finally.
- **Privacy Lock**: If enabled, locks the app (PIN entry required) on PC resume (`WM_POWERBROADCAST / PBT_APMRESUMESUSPEND`) OR Windows session unlock (`WM_WTSSESSION_CHANGE / WTS_SESSION_UNLOCK`). Constants defined at module level. `nativeEvent` wrapped in try-except for PySide6 version safety.
- **Backups**: Startup health inspection precedes pre-v3.5 and migration protection. Verified daily DB+salt+manifest `.cnbak` bundles retain five days; non-rotating protection and legacy snapshots are preserved.
- **Maintenance**: SQLite `VACUUM` remains available as an internal DB optimization helper.
- **Audit Logging**: "앱 종료" fires exactly once via `app.aboutToQuit` signal in `main.py`.
- **Graceful Shutdown**: Tray and Settings quit first call `prepare_for_quit()`; a pending schedule edit is committed before saving the current floating/panel sticky source. Failed schedule or sticky saves block normal exit. `aboutToQuit` records the audit event only.
- **Startup Path Refresh**: `_refresh_startup_path()` in `main.py` — on every launch, if auto-start is enabled, updates the registry to the current exe path. Prevents broken auto-start after exe relocation or version update.
- **Screen Change Restore**: `screenAdded`/`screenRemoved`/`geometryChanged` signals with 500ms debounce. On trigger, the calendar's size is recomputed for the destination screen with `_calendar_scale_geometry()` before positioning — `medium`/`large` scale with screen size, so clamping coordinates alone leaves a landscape-sized window overflowing a portrait monitor. Sticky notes/D-Day/focus widgets are restored to DB-saved positions and clamped to the nearest monitor. The calendar uses `calendar_position_mode`: existing users default to corner placement, while a completed header drag opts into persisted free coordinates.
- **Calendar Column Layout**: Calendar and weekday-header grids share equal stretch across seven columns. Schedule chips ignore horizontal size hints so elided text cannot impose a history-dependent column minimum. This is a display-only rule: it does not change schedule text/colors, settings, schema, salt or Export format. Geometry and data-preservation regressions live in `tests/test_ui_calendar_columns.py`; details are in [UI Patterns](UI_PATTERNS.md).
- **Show Desktop Layering**: guarded windows normally occupy the non-topmost layer immediately above the shell desktop. A foreground WinEvent for the shell desktop starts a 350ms topmost pulse; settling explicitly clears topmost, finds the first non-guarded predecessor of the desktop with `GetWindow(GW_HWNDPREV)`, and inserts guarded windows between that boundary and the desktop. Browser/Explorer foreground transitions cancel the pulse and re-pin the same desktop layer, so the order remains desktop icons → Climate Note → normal app windows. No WorkerW reparenting is used.

---

## Database Schema (v17)

- **schedules / memos**: Encrypted content storage. `schedules` has `color TEXT DEFAULT '#FFD166'` (plaintext, not encrypted).
- **sticky_notes**: Persisted floating notes. Default color `DEFAULT_STICKY_COLOR = "#FFFA8E"`. v12→v13 migration adds soft-delete columns `is_deleted INTEGER NOT NULL DEFAULT 0` / `deleted_at TEXT NOT NULL DEFAULT ''` (휴지통). 닫기는 `is_deleted=1`로 휴지통 이동, `get_open_sticky_notes`는 `is_deleted=0`만 조회. 휴지통은 `STICKY_TRASH_LIMIT(=50)`개로 제한.
- **dday_widgets**: D-Day countdown widgets. `name` encrypted, `target_date` plaintext. Default color `DEFAULT_DDAY_COLOR = "#C4D5FF"`.
- **focus_widgets**: Persisted focus-mode widgets. `goal` encrypted, mode/position/pin state plaintext. Modes: `25/5`, `50/10`, `75/15`.
- **focus_sessions**: Focus session review history. `goal` encrypted, mode/timestamps/elapsed/completion/rating/distraction plaintext for future statistics.
- **shortcuts**: Program shortcuts. `name` and `path` plaintext. 6 records max.
- **app_settings**: Key-Value table. Use constants from `database.py`:
  - `SETTING_PRIVACY_PIN = "privacy_pin"`
  - `SETTING_DESKTOP_MODE = "desktop_mode"`
  - `SETTING_USE_PRIVACY_LOCK = "use_privacy_lock"`
  - `SETTING_SHOW_LUNAR = "show_lunar"`
  - `SETTING_SHOW_LAW_SEARCH = "show_law_search"` (default: `"1"` = On)
  - `SETTING_SHOW_SIDEBAR = "show_sidebar"` (default: `"0"` = Off)
  - `SETTING_APP_FONT = "app_font"` (default: `"Malgun Gothic"`)
  - `SETTING_APP_OPACITY = "app_opacity"` (default: `"100"`, range: 30-100)
  - `SETTING_CALENDAR_SCALE = "calendar_scale"` (default: `"compact"`, values: compact/medium/large)
  - `SETTING_CALENDAR_X = "calendar_x"`, `SETTING_CALENDAR_Y = "calendar_y"` — 캘린더 창 위치 저장/복원
  - `SETTING_CALENDAR_POSITION_MODE = "calendar_position_mode"` (default: `"corner"`, values: corner/free)
  - `SETTING_CALENDAR_SCREEN = "calendar_screen"` — 명시적 드래그·모니터/모서리 선택 때만 저장하는 v1 JSON(화면 이름·serial·제조사·모델·저장 당시 작업 영역 원점). 기존 `target_screen` 인덱스와 전역 `calendar_x/y`는 유지한다. 키가 없거나 잘못된 경우 기존 인덱스를 사용하며 시작/화면 복구에서 새 행을 만들지 않는다.
  - `SETTING_CALENDAR_MOVE_ENABLED = "calendar_move_enabled"` (missing/invalid fallback: `"1"`, OFF: `"0"`). 사용자 토글에만 새 행을 쓰고 스키마/기존 행은 변경하지 않는다. Export v2 설정 왕복을 사용하며 Import 후 UI를 재동기화한다.
  - `SETTING_SCHEDULE_COLOR_1/2/3` — 기존 일정 슬롯 3개의 표시색
- **v13→v14**: Adds only `app_opacity` and `calendar_scale` settings via `INSERT OR IGNORE`; no table or column changes.
- **v14→v15**: Adds shortcut slot 6 via `INSERT OR IGNORE`.
- **v15→v16**: Adds `keep_on_show_desktop` via `INSERT OR IGNORE`.
- **v16→v17**: Adds only the three schedule display-color settings and `calendar_position_mode` via `INSERT OR IGNORE`. It does not alter a table, schedule row, or ciphertext.
- **Export/Import Settings**: `app_settings` is included in round-trip backups except `privacy_pin`.
- **Schedule Colors**: `SCHEDULE_COLORS = [("#FFD166","노랑"), ("#4CC9F0","파랑"), ("#FF6B6B","빨강")]` remains the canonical storage contract. Settings select three distinct display colors from `SCHEDULE_COLOR_OPTIONS` (10 colors); `schedule_display_color()` resolves a slot at render time. Palette changes never rewrite `schedules.color`, and unknown imported colors pass through unchanged.

### 스키마 변경 규칙

> 스키마를 변경할 때는 **반드시** 아래 절차를 따른다.

1. `database.py`의 목표 `PRAGMA user_version`을 올린다.
2. `migrate()` 함수 내에 기존 테이블은 `ALTER TABLE ... ADD COLUMN`, 신규 테이블은 `CREATE TABLE IF NOT EXISTS` 방식으로 추가한다.
3. 기존 테이블·컬럼을 **절대** DROP하지 않는다.
4. 마이그레이션은 멱등성 보장 (`IF NOT EXISTS` 또는 `try/except sqlite3.OperationalError`).

---

## Build & Constraints

- **Offline-Only**: No external API calls; all data (holidays, lunar) must be embedded. Exceptions: AI 법령검색 and 업데이트 안내 open external URLs in the default browser.
- **Font Bundling**: App text fonts are system fonts and are not bundled. Font Awesome files are included via `build.spec` `datas=[..., ('fonts', 'fonts')]` for sticky-note todo checkbox icons.
- **Resource Root**: `app_paths.resource_root()` is the single source for bundled asset paths — `sys._MEIPASS` when frozen, the project root from source. `app_fonts`, `fluent_icons`, `ui_focus`, and the tray icon in `main` all resolve through it, so module location never affects resource lookup. Never rebuild a resource path from `Path(__file__).parent`.
- **Focus Assets**: `resources/images/tomato_mini.png` (ambient) and `resources/images/tomato.png` (hover glance) ship inside the `resources` datas tree, so they need no per-file `build.spec` entry.
- **Qt Submodules**: Must include `QtXml`, `QtSvg`, `QtSvgWidgets`, `QtNetwork` for `qfluentwidgets`.
- **Encryption Bound**: Data is machine-bound unless exported via PIN-encrypted `.enc` files.
- **Output**: `dist/<app_info.app_exe_name()>` (single-file, no console, icon: `icon/icon_fixed_256.ico`). `upx=True` only requests UPX; compression requires an installed UPX executable. Harness release builds use isolated output directories.
- **Version Source**: UI footer and build output name both read `APP_VERSION` from `app_info.py`.
- **Build Environment**: `build.bat`은 프로젝트 `.venv\Scripts\python.exe`를 명시하고, `build_app.py`는 `tools.verify.doctor()`로 Python·lock·필수 파일을 검사한 뒤 같은 인터프리터의 PyInstaller를 `--clean`으로 실행한다. 환경 불일치나 빌드 실패는 비영 종료하며 패키지를 자동 설치하지 않는다. EXE의 표시 버전만으로 Qt 수정 포함 여부를 판단하지 않는다. 2026-09-14에는 전역 Python의 Qt 6.10.2가 들어간 v3.7a가 확인되었으므로 검증된 6.11.2 환경의 새 산출물을 사용한다.

```bash
python build_app.py   # OR
build.bat
```

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
| `holidays.py` | Offline Korean holiday/lunar data (생성물, git 추적). `KOREAN_HOLIDAYS` (2025-2027), `LUNAR_MAPPING` (2025-2050). 함수: `get_holiday`, `is_holiday`, `get_lunar_date`, `holiday_last_year`. **`fetch_data.py`로만 갱신** (임의 계산 금지). |
| `fetch_data.py` | 공공데이터포털 API로 `holidays.py` 재생성 (실제 API 데이터만, 임의 계산 없음). `verify_holiday_data(hol)` 로 재생성 후 커버리지 검증. 갱신 절차: 백업 → `python fetch_data.py` → `verify_holiday_data` 통과 확인 → 실패 시 백업 복구. |
| `ui_mini_apps.py` | DB 접근 없는 미니앱 버튼/92px 정사각형 타일 2열과 그림자 여백을 포함한 위치 계산. 240×280px 본체에 실행 타일 1개와 비활성 예정 타일 3개를 배치한다. `apps.svg`는 `fluent_icon()`으로, 생성 이미지 `resources/images/mini_apps/unit_converter_tile.png`는 `QIcon`으로 로드하며 모두 `resource_root()`와 기존 resources 번들을 사용한다. 런타임 생성/다운로드 없음. 주머니 소유/일정 저장 게이트/잠금·숨김·레이아웃 정리는 메인 창이 담당한다. 사용자 바로가기 6슬롯·DB v17·Export v2·salt·설정 키와 열림 상태 영속화에 변화 없음 |
| `unit_converter.py` / `ui_unit_converter.py` / `ui_conversion_conditions.py` | v3.8a 단위 환산기. 순수 계산 모듈(25분류·182항목·명시적 밀도/기체 조건·온도차·입력/범위 검증)과 단일 비모달 도구 창. 내용 440×580px/그림자 포함 기본 488×628px, 132px 분류 목록의 28px 행/0px 간격/13px 이름을 사용한다. 좁은 화면은 내용 최소 너비를 우선해 그림자 여백과 blur를 줄인다. 불변 `ConversionConditions`와 최근 12개는 메모리 전용이며 외부 JS/폰트/DB/설정 키를 추가하지 않는다. 주머니 실행·잠금·숨김·종료는 메인이 소유하고 초기화 성공 신호에서만 객체를 폐기한다. 정의·출처는 [단위 계약](UNIT_CONVERSION.md) |
| `ui_main.py` | Main window: frameless; compact/medium/large에서 이동 토글 ON 시 헤더 배경·연월 라벨 드래그 이동(대상 화면 DPI 기준 5mm 전역 격자), OFF는 수동 드래그만 차단; 자유 좌표 복원·화면 이탈 clamp·타겟 모니터/최근접 모서리 동기화; Privacy Lock; AI 법령검색바; 전체 창 투명도 broadcast; compact/medium/large 캘린더와 확장 3열 reflow; Shortcut Sidebar 6슬롯(빈 슬롯 클릭 파일/폴더 등록, 등록 슬롯 우클릭 이름 변경·경로 재지정·삭제, 끊긴 경로 클릭 복구); 일정 행은 오른쪽 휴지통 삭제와 더블클릭 인라인 편집을 유지하며 우클릭 `편집`·`삭제` 메뉴도 제공; 스티키/D-Day/집중 모드 자동정렬. 자동정렬은 저장된 모서리가 아니라 **캘린더의 실제 화면·최근접 모서리**를 기준으로 한다. 시작 시 `enforce_widget_limits()`를 1회 호출하고 정리분이 있으면 모달 안내. `large` 스케일에서는 우측 컬럼을 `[일정 → D-Day 미니 → 집중 미니 → 스티키 미니]` 4구획으로 구성하며, 플로팅 스티키/D-Day/집중을 숨기고 패널과 동기화한다. 이탈 시 패널 저장 후 DB→플로팅 재로드/복원. 정상 종료 전에는 현재 모드의 최신 스티키 원본을 모두 강제 저장하고 하나라도 실패하면 종료를 보류한다. 초기 표시 전 사이드바 경계는 설정값 기준으로 `sidebarActive`/`expanded` dynamic prop을 맞춘다. `CalendarDayButton`은 compact 3행/expanded 일정 칩 2모드이며, large 일정 칩은 13px 글꼴·22px 높이·3px 간격을 사용하고 일정 raw 슬롯은 `schedule_display_color()`로 표시색만 치환한다. 공휴일 날짜는 빨강(`#D32F2F`), 공휴일명은 하단 패널(`holiday_info_label`)에 표시. 헤더 월 네비(`< 연월 >`)는 좌우 stretch 대칭 중앙 정렬. 미니 D-Day 삭제·집중 미니 종료 배선; Win+D 데스크톱 레이어 고정용 ShowDesktopKeeper 소유(메인+모든 플로팅 위젯 가드), 설정 토글 실시간 반영 |
| `ui_search.py` | Global keyword search: Notion-스타일 `QTableWidget`, 일정은 사용자 팔레트색의 `■` 배지, 메모는 📝 배지, 실시간 결과 정렬 |
| `ui_schedule_emoji.py` | 일정 본문 선두 이모지 선택 도우미. 고정 16개 팔레트·전체 Unicode 접두 문자열 인식·UTF-16 범위 치환, 공용 선택 버튼·팝업, 포커스 이동을 구분하는 인라인 편집기. 기존 `schedules.content`를 단일 저장 원본으로 사용 |
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

## 데이터·빌드 상세 계약

- **KVM 화면·위치 복원(v3.8 후속)**: `screen_placement.py`가 화면 식별 정보를 캡처/검증한다. serial+제조사/모델의 유일한 일치를 우선하며, serial이 없거나 중복이면 이름과 장치 정보 조합이 유일할 때만 사용한다. 다른 serial을 가진 화면을 이름만 같다는 이유로 채택하지 않는다. 실행 중 기존 화면 객체를 계속 사용할 수 있으면 유지한다. 대상 부재/모호함은 기본 화면 임시 표시로 처리하고 선호 정보는 보존한다. 구형 인덱스 설정은 유효한 대상이 나타났을 때 메모리에서만 식별 정보를 기억한다. Import/초기화는 캐시를 다시 읽는다.
- **자동 위치 보정은 저장 아님**: 크기·작업 영역·DPI·화면 분리로 보정한 캘린더 좌표는 `calendar_x/y`에 쓰지 않는다. 같은 대상 화면의 원점이 바뀌면 저장 당시 원점과의 차이만큼 상대 위치를 옮기고 작업 영역 안으로 보정한다. 명시적 드래그/모서리·모니터 선택 때만 화면 정보와 위치를 `save_settings()`의 한 트랜잭션으로 저장한다. 스티키/D-Day/집중도 화면 변경 때 원래 DB 좌표로 복원하고 임시 clamp 좌표는 DB에 쓰지 않으며 수동 이동 저장은 유지한다. DB v17·Export v2·salt·본문 형식은 바꾸지 않는다. 구현·검증·실제 KVM 미확인은 [복원 개선 기록](work/2026-09-22-kvm-window-position-fix.md)을 따른다.

- **일정 이모지 저장**: 선택 도우미는 기존 `schedules.content` 앞에 `이모지 + ASCII 공백 한 칸`을 넣고 기존 Fernet 경로로 본문과 함께 암호화한다. DB v17·Export v2·canonical 색상 3슬롯·설정 키·salt는 유지하며 마이그레이션이나 기존 행 일괄 갱신은 하지 않는다. 알려진 선두 표식 하나만 명시적 선택 시 교체하고, 본문 안의 임의 Unicode는 보존한다. 직접 입력한 동일한 선두 표식과 도우미가 붙인 표식은 구별하지 않는다. 검색·복사·PIN Export/Import에는 이모지가 포함된 같은 본문을 사용한다.
- **일정 인라인 편집 저장**: 입력창·이모지 버튼·선택창은 하나의 편집 영역이다. 팝업을 열었다는 이유로 저장하지 않으며 편집 확정 시 시작 당시 ID·날짜에만 적용한다. 저장 실패는 편집 내용 유지와 날짜/월/검색 이동·목록 재생성·가져오기/초기화·정상 종료 보류로 처리한다. 데이터 작업 준비는 일정 편집 저장 → 현재 스티키 원본 저장 순서이며, 초기화의 객체 폐기 단계는 일정 편집과 이모지 팝업도 취소한다. 원문을 바꾸지 않은 편집과 복호화 실패 행은 다시 암호화하거나 덮어쓰지 않는다.

- **오프라인 전용**: 외부 API 호출 없음. 공휴일/음력 데이터 내장 필수. (예외: AI 법령검색 및 업데이트 안내는 브라우저 URL 오픈)
- **wmux 금지**: 이 프로젝트에서 `wmux browser` 등 wmux CLI 명령은 호출하지 않는다. 웹 브라우징이 필요하면 `WebFetch`/`WebSearch` 도구를 사용한다. 전역 CLAUDE.md의 wmux 지침은 이 프로젝트에 적용하지 않는다.
- **DB 연결**: 반드시 `database.py`의 `_connection()` 컨텍스트 매니저 사용. 직접 `sqlite3.connect()` 금지.
- **파일 열기**: 반드시 `with open(...) as f:` 사용.
- **암호화**: 모든 민감 데이터는 `security.py`의 Fernet 함수 경유. 평문 저장 금지.
- **앱 버전**: 표시 버전과 빌드 exe 파일명은 `app_info.py`의 `APP_VERSION`을 단일 출처로 사용한다. 빌드 스크립트가 `AGENTS.md`를 파싱하지 않는다.
- **v3.5 시작 데이터 건강 검사**: DB를 쓰기 전에 read-only 연결로 SQLite `integrity_check`, 지원 스키마와 암호화 대상 6개 컬럼의 전수 복호화를 검사한다. DB가 있는데 암호문을 열 수 없거나 `.salt`가 누락·손상됐으면 새 DB/salt/백업을 만들지 않고 메인 창 생성 전에 중단한다. UI는 데이터 폴더 열기와 종료만 제공하며 원인을 PC·계정·salt 중 하나로 단정하지 않는다. 진짜 신규 설치는 DB·salt·WAL/SHM·기존 백업이 모두 없을 때뿐이다.
- **v3.5 자동백업 묶음**: 같은 PC·같은 Windows 사용자 복구용 `backups/calendar_auto_YYYYMMDD_*.cnbak`은 정확히 `calendar.db`(WAL-safe snapshot), `.salt`(원본 32 bytes), `manifest.json`(형식/버전/크기/SHA-256/schema/key-check) 3개만 담는다. 임시 묶음을 완전 검증한 뒤 같은 볼륨에서 `os.replace`로 게시하고, 당일 첫 정상본은 덮어쓰지 않으며 검증된 일일 묶음만 최근 5일 보존한다. 기존 `calendar_backup_*.db`와 `calendar_pre_v17_*.db`, 비회전 보호본은 자동 회전에서 절대 삭제하지 않는다. 새 salt 생성은 보호할 암호문이 0개임을 건강 검사가 확인한 데이터셋에만 허용한다. 이 묶음은 PC 이동용이 아니며 PC 이동은 기존 PIN `.enc` 내보내기/가져오기를 사용한다.
- **v3.5 비회전 보호본**: 기존 v3.4 DB는 첫 v3.5 실행에서 `calendar_pre_v35_*.cnbak`으로 한 번 보존한다. 가져오기와 Factory Reset 직전에는 각각 `calendar_before_import_*.cnbak`, `calendar_before_reset_*.cnbak`을 만들며 실패하면 해당 작업을 시작하지 않는다. 실행 중 live DB와 salt를 두 파일로 직접 교체하는 복원 UI는 금지한다. 안전한 복원은 앱 시작 전 검증·rollback·재개 가능한 journal을 갖춘 별도 절차로만 추가한다.
- **체크박스 저장 호환**: 스티키 노트 할 일의 DB/HTML 표식은 Font Awesome `\uf0c8`/`\uf14a`를 유지하고 `☐`/`☑`도 계속 읽는다. 화면에서는 표식을 투명하게 하이라이트한 뒤 벡터 체크박스를 덧그리므로 앱 글꼴·HTML 저장값·텍스트 왕복이 바뀌면 안 된다.
- **폰트 번들**: 앱 본문 폰트는 번들하지 않는다. `fonts/`에는 스티키 노트 체크박스용 Font Awesome 파일과 **D-Day Cover Tint용 Pretendard 정적 4굵기**(`Pretendard-Medium/SemiBold/Bold/ExtraBold.ttf`, 패밀리 `Pretendard`)를 둔다. Pretendard는 본문 폰트가 아니라 **UI 강조용**이며 `app_fonts.load_ui_fonts()`로 로드한다(미로드 시 Malgun 폴백). 서드파티 번들이지만 사용자 승인으로 예외 적용.
- **번들 리소스 경로**: 폰트·아이콘·이미지·Fluent SVG 경로는 반드시 `app_paths.resource_root()`를 기준으로 만든다. `Path(__file__).parent`로 리소스 경로를 조립하지 않는다. PyInstaller는 번들 모듈의 `__file__`을 `_MEIPASS/<이름>.pyc`로 잡으므로 `.parent`가 `_MEIPASS`와 같아지는 것은 **.py 파일이 번들 루트에 있을 때만** 성립한다. 모듈을 하위 폴더로 옮기면 소스 실행과 테스트는 통과하면서 EXE에서만 리소스를 잃는다. `tests/test_app_paths.py`가 frozen 분기와 이 패턴 재발을 검사한다.
- **정상 종료 스티키 저장 게이트**: 트레이 `종료`와 설정의 `앱 종료`는 `MainCalendarWindow.prepare_for_quit()`을 먼저 호출한다. compact/medium에서는 등록된 플로팅 스티키를 표시 여부와 무관하게 모두 저장하고, `large`에서는 최신 편집 원본인 `StickySidePanel`만 저장해 숨은 구버전 플로팅 HTML의 역덮어쓰기를 막는다. 하나라도 실패하거나 패널 모드에서 패널이 없으면 fail-closed로 종료하지 않고 오류를 표시한다. compact/medium↔large 소유권 전환도 현재 원본 저장과 DB 재로드가 모두 성공한 뒤에만 완료하며 실패 시 기존 원본을 유지한다. 실패한 창/카드는 2초 저장 타이머를 다시 시작한다. 강제 프로세스 종료·전원 차단은 보장 범위 밖이다.
- **가져오기 중 편집 원본 보존**: 설정의 Import는 `prepare_for_data_change()`로 현재 모드의 최신 스티키 저장을 확정한 뒤 보호백업·병합을 수행한다. 저장 실패 시 백업·병합을 시작하지 않는다. 완료 후 `_load_open_*`는 이미 등록된 ID의 플로팅 창을 재사용하고 신규 ID만 추가한다. 기존 스티키 편집기와 진행 중 집중 타이머를 같은 ID의 새 객체로 교체하면 안 된다. large 스티키 패널은 기존 대기 편집을 보존하며 가져온 목록으로 갱신한다.
- **초기화와 위젯 수명**: 최신 스티키 저장 → 보호백업 성공 → `_discard_data_widgets()` → DB/salt 초기화 순서를 지킨다. 폐기 단계는 숨긴 미니 패널까지 포함해 모든 자식 `QTimer`를 정지하고, 플로팅 창을 `ShowDesktopKeeper.unguard()`로 해제한 뒤 `deleteLater()`한다. `close()`나 레지스트리 clear만으로는 이전 객체의 쓰기를 막을 수 없다. 초기화 시도가 실패해도 이전 객체를 재사용하지 않고 현재 DB에서 UI를 복원한다. 보호백업 이전 실패에서는 기존 객체와 집중 세션을 유지한다. 이 UI 복원은 DB/salt 파일의 자동 rollback을 의미하지 않는다.
- **잠금 중 창 수명**: PIN 잠금은 트레이 보이기/숨기기, 지연된 플로팅 표시, 설정·검색·휴지통 진입에도 적용한다. `_show_floating_widget()`는 실행 시점의 잠금·트레이·패널 상태와 현재 레지스트리 소속을 확인하므로 초기화로 폐기된 창을 다시 표시하지 않는다. 잠금 당시 보조 창은 비활성화·숨김 처리하고 활성 모달/팝업은 취소한다. 숨겼던 보조 창을 새로 만들 때 이전 객체는 폐기한다. 잠금 중 집중 자동 완료는 기록과 완료 상태만 유지하고 휴식 팝업을 열지 않는다.
- **일정 3슬롯 표시 팔레트**: `schedules.color`에는 기존 canonical 3색(`#FFD166`/`#4CC9F0`/`#FF6B6B`)만 슬롯 식별자로 계속 저장한다. 설정의 10색 후보는 `schedule_color_1/2/3`에 **표시색만** 저장하며 세 슬롯은 서로 다른 색이어야 한다. 렌더링은 `schedule_display_color()`를 거치고, 기존/가져온 미지의 색은 원문 그대로 표시한다. 팔레트 변경을 이유로 기존 `schedules` 행을 UPDATE하지 않는다.
- **DB 마이그레이션**: 현재 `user_version=17`. v13→v14는 `app_opacity`/`calendar_scale`, v14→v15는 바로가기 6번째 슬롯, v15→v16은 `keep_on_show_desktop`, v16→v17은 `schedule_color_1/2/3`과 `calendar_position_mode`를 각각 `INSERT OR IGNORE`로 추가한다. v16→v17은 테이블/컬럼/기존 일정 행/암호문을 수정하지 않는다. Export/Import는 `app_settings`를 포함하되 `privacy_pin`은 제외한다.
- **마이그레이션 전 백업**: `main._initialize_database()`는 read-only 건강 검사와 v3.5 최초 보호본, `backup_before_migration()`이 모두 성공한 뒤에만 `migrate()`를 호출한다. 구 DB는 `Connection.backup()`으로 `backups/calendar_pre_v17_v{version}.db`에 최신 snapshot을 만들고 `quick_check`와 버전을 확인한 뒤 원자 교체한다. 백업 생성·검증·교체가 실패하면 기존 snapshot과 원본 DB를 보존한 채 시작/마이그레이션을 중단한다. raw 파일 복사로 WAL DB를 백업하지 않는다.
- **Export/Import 무손상 규칙**: Export v2는 명시적 read transaction의 한 snapshot에서 읽고 민감 필드 하나라도 복호화하지 못하면 파일 생성을 중단한다. Import는 모든 구조·타입·범위·참조를 DB write 전에 검증하고 한 transaction으로 병합한다. 같은 날짜의 기존 메모와 비어 있지 않은 바로가기 슬롯은 덮어쓰지 않으며, focus `source_id`를 새 ID로 remap한다. 레거시 focus session은 무관한 현행 위젯에 연결하지 않는다. 일정/위젯은 안정적인 원본 ID가 없어 동일 파일 반복 Import 시 중복될 수 있으므로 성공 안내에 이를 명시한다.
- **공휴일 데이터**: `holidays.py`는 생성물이며 **`fetch_data.py`로만 갱신**한다. 미래 연도를 코드로 임의 계산·추정해 채우면 안 된다. API가 제공하는 범위(현재 2025-2027)만 사용. `holiday_last_year()` 함수가 만료 알림 기준 연도를 반환하므로 생성 시 반드시 포함해야 한다.
- **집중 모드 저장**: `focus_widgets.goal`과 `focus_sessions.goal`은 암호화 저장한다. `focus_sessions`는 완료 기록과 회고 필드(`focus_rating`, `distraction`)를 담는다.

## 스티키 파일 링크 저장 (v3.7b, 2026-09-20)

범위·합성 검증·수동 미확인은 [구현 기록](work/2026-09-20-sticky-file-links.md)에 남긴다. 파서/파일 검사는 `sticky_file_links.py`, 두 보기의 공용 편집은 `ui_sticky_links.FileLinkTextEdit`를 `_TodoTextEdit`가 상속한다.

- 새 링크는 기존 `sticky_notes.content` HTML의 `climatenote-file://v1?path=...&origin=...&id=...&u=...` href로 저장한다. `path`는 URL 인코딩한 로컬 절대 경로, `origin`은 연결 환경, `id`는 개별 연결 식별값, `u`는 원래 밑줄 서식이다. Qt 6.11.2가 HTML 재로드 시 anchor 밑줄을 자동 추가하므로 해제 시 `u`를 복원한다. 색·굵기·이탤릭 등 서식 run은 유지한다. 기존 Fernet 경로로 저장하며 DB v17·Export v2·설정 키·salt·키 유도·백업 구조와 기존 행을 일괄 변환하지 않는다.
- `security.file_link_origin()`은 기존 장치/사용자 ID를 링크 전용 문자열과 SHA-256으로 구분한 비밀이 아닌 환경 비교값이다. 패스워드 해시·인증·암호화 키가 아니며 재시작 비교를 위해 임의 salt를 사용하지 않는다. 키 유도/암호화 캐시/salt 생성·읽기를 호출하지 않는다. 원본 하드웨어 정보·사용자명·키·PIN·salt는 href에 담지 않는다. 다른 환경/식별 불가에서는 명시적 재연결이 필요하고 Import가 자동 승인하지 않는다.
- 링크 상태와 주의 아이콘은 화면의 파생 정보로만 유지한다. 조회/표시를 이유로 DB를 쓰거나 본문·Undo를 변경하지 않는다. 원본 연결 파일은 복사·이동·백업에 포함하지 않고 경로만 보존한다.
- B+C 파일 라벨의 확장자 배지·둥근 테두리·주의 표시는 `ui_sticky_link_labels.py`에서 처리한다. 체크박스와 공유하는 QSyntaxHighlighter의 표시용 글자 간격으로 장식 공간을 확보하고 원래 grapheme은 본래 글꼴로 그린다. 문서에는 공백·파일 종류·경고·object replacement 문자를 추가하지 않고 기존 href·서식 run만 저장한다. 배지 공간은 복사/Export/Import에 포함되지 않는다. 정상 링크 뒤에는 빈 경고 공간을 예약하지 않는다. 상태 변경은 해당 마지막 grapheme의 QTextLayout 추가 서식과 markContentsDirty로 표시 배치만 갱신하며 rehighlight/문서 revision 갱신/본문 수정 신호/자동저장을 유발하지 않는다. 같은 상태에서는 재배치하지 않으며 preedit가 있는 블록은 조합 종료 후 반영한다.
- 기존 DB/salt용 `validate_app_path()`는 완화하지 않는다. 링크 경로는 드라이브 절대 경로만 허용하고 네트워크 드라이브·UNC·실행 파일·스크립트·바로가기·재분석 지점(심볼릭 링크/정션/클라우드 자리표시자)을 거부한다. 경로 검사 작업은 최대 4개 daemon worker와 결과 큐로 분리한다. GUI는 최대 3초 후 확인 실패로 처리하고 늦은 결과는 무시한다. 확인 캐시는 10초이며 열기 직전은 다시 검사한다. OS에는 검증한 경로의 `QUrl.fromLocalFile()`만 전달한다. 내부 href/명령 문자열은 실행하지 않는다.
- 링크 추가 직후 Export에도 `_prepare_data_change()`로 현재 일정과 스티키 원본 저장을 확정한 후 snapshot을 읽는다. 저장 실패 시 파일 선택·출력 파일 생성/교체를 시작하지 않는다. `large` 단일 원본·저장 실패 보류 계약을 유지한다.
- 작업에는 편집기 인스턴스별 세대와 문서 revision을 부여한다. 숨김·잠금·초기화·문서 변경 시 파일창/메뉴를 닫고 대기 작업을 무효화한다. worker는 QWidget·DB·외부 실행기를 참조하지 않으며 폴링 타이머는 대기 작업이 있을 때만 동작한다. 같은 DB ID의 새 편집기는 이전 결과를 받지 않는다.
- 기존 자동저장은 같은 본문도 다시 암호화할 수 있다. 보존 검증에서 기능이 쓰지 않아야 하는 단계의 raw 불변과 기존 정상 저장 경로의 복호화 본문·서식 보존을 구분한다. 새 기능을 이유로 일반 저장 구조를 전면 변경하지 않는다.
