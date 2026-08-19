# Architecture Reference

## Data Flow & Security

- **Single Instance**: `msvcrt.locking` on `.lock` file prevents duplicate instances from corrupting the DB.
- **Encryption**: Hardware-derived key (MAC + Username) + PBKDF2HMAC (200k iterations) → Fernet (AES-128). Common derivation logic in `_derive_fernet_key()`. Fernet instance is **cached** at module level; cache is invalidated on Factory Reset.
- **Path Validation**: `security.validate_app_path()` shared between `security.py` and `database.py` to prevent path traversal.
- **SQLite**: WAL journal mode + 5s busy timeout. All DB functions use `@contextmanager _connection()` — no manual try/finally.
- **Privacy Lock**: If enabled, locks the app (PIN entry required) on PC resume (`WM_POWERBROADCAST / PBT_APMRESUMESUSPEND`) OR Windows session unlock (`WM_WTSSESSION_CHANGE / WTS_SESSION_UNLOCK`). Constants defined at module level. `nativeEvent` wrapped in try-except for PySide6 version safety.
- **Backups**: Database is backed up daily upon launch to `backups/` (retains last 5 copies).
- **Maintenance**: SQLite `VACUUM` remains available as an internal DB optimization helper.
- **Audit Logging**: "앱 종료" fires exactly once via `app.aboutToQuit` signal in `main.py`.
- **Graceful Shutdown**: `aboutToQuit` calls `main_window.save_all_sticky_notes()` before audit log, ensuring no data loss on normal quit.
- **Startup Path Refresh**: `_refresh_startup_path()` in `main.py` — on every launch, if auto-start is enabled, updates the registry to the current exe path. Prevents broken auto-start after exe relocation or version update.
- **Screen Change Restore**: `screenAdded`/`screenRemoved`/`geometryChanged` signals with 500ms debounce. On trigger, the calendar's size is recomputed for the destination screen with `_calendar_scale_geometry()` before positioning — `medium`/`large` scale with screen size, so clamping coordinates alone leaves a landscape-sized window overflowing a portrait monitor. Sticky notes/D-Day/focus widgets are restored to DB-saved positions and clamped to the nearest monitor. The calendar uses `calendar_position_mode`: existing users default to corner placement, while a completed header drag opts into persisted free coordinates.
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
- **Output**: `dist/기후노트_v3.4.exe` (single-file, no console, UPX-compressed, icon: `icon/icon_fixed_256.ico`)
- **Version Source**: UI footer and build output name both read `APP_VERSION` from `app_info.py`.

```bash
python build_app.py   # OR
build.bat
```
