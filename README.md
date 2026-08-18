# 기후노트

Windows 바탕화면에서 쓰는 **오프라인 전용** 캘린더·메모·위젯 앱입니다.
일정과 메모를 하드웨어 바인딩 암호화로 로컬에만 저장하며, 외부 서버로 아무것도 보내지 않습니다.

현재 버전 **v3.6** (2026. 8. 18.)

---

## 주요 기능

- **캘린더** — 기본·중간·크게 3단계 크기. 중간/크게에서는 날짜 칸에 일정이 색상 칩으로 표시됩니다
- **스티키 노트** — 서식·할 일 체크박스를 지원하는 바탕화면 메모. 닫으면 휴지통으로 이동해 복구할 수 있습니다
- **D-Day 위젯** — 최대 5개. 진한 커버색 카드로 남은 날짜를 표시합니다
- **집중 모드** — 포모도로 타이머 1개. 집중·휴식 세션을 기록합니다
- **바로가기 사이드바** — 자주 쓰는 파일·폴더 6개를 등록해 바로 실행합니다
- **전역 검색** — 일정과 메모를 한 번에 찾습니다
- **Privacy Lock** — PC 절전 해제나 Windows 잠금 해제 시 PIN을 요구합니다
- **바탕화면 고정** — `Win+D`(바탕화면 보기)를 눌러도 기후노트가 남습니다
- **트레이 상주** — 창을 닫아도 트레이에 남으며 `Ctrl+Shift+H`로 즉시 숨기고 꺼낼 수 있습니다

공휴일·음력 데이터는 앱에 내장되어 있어 인터넷 연결 없이 동작합니다.

---

## 요구 환경

- Windows 10 이상 (Windows 11 권장)
- Python 3.13 (개발·검증에 사용한 버전. 최소 지원 버전은 별도로 정해두지 않았습니다)

이 앱은 Windows 전용입니다. `winreg`, `msvcrt`, Win32 API를 직접 사용하므로 다른 OS에서는 동작하지 않습니다.

---

## 설치와 실행

```bash
git clone <이 저장소 주소>
cd MyDesktopCalendar

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
python main.py
```

정확한 버전을 재현하려면 `requirements.txt` 대신 `requirements-lock.txt`를 사용합니다.

`.env` 파일은 필요하지 않습니다. 공휴일 데이터(`holidays.py`)가 저장소에 포함되어 있어
API 키 없이 실행·테스트·빌드가 모두 가능합니다.

---

## 테스트

```bash
python -m pytest tests -q                            # 전체
python -m pytest tests/test_stress.py --timeout=120  # 스트레스만
```

DB·암호화·UI·보안·스트레스를 포함한 500개 이상의 테스트가 있습니다.
테스트는 임시 폴더에 격리된 DB와 암호화 키를 사용하므로 실제 사용자 데이터에 영향을 주지 않습니다.

---

## 빌드

```bash
python build_app.py     # 또는 build.bat
```

PyInstaller 단일 실행 파일이 `dist/기후노트_v3.5.exe`로 생성됩니다.
파일명의 버전은 `app_info.py`의 `APP_VERSION`을 따릅니다.

---

## 프로젝트 구조

| 파일 | 역할 |
|---|---|
| `main.py` | 진입점. 단일 인스턴스 잠금, DB 초기화, 트레이, 전역 단축키 |
| `database.py` | SQLite CRUD, 스키마 마이그레이션, 백업, Export/Import |
| `security.py` | 키 유도, Fernet 암복호화, 경로 검증, 감사 로그 |
| `ui_main.py` | 메인 캘린더 창, 위젯 배치와 자동 정렬 |
| `ui_sticky.py` · `ui_dday.py` · `ui_focus.py` | 스티키 노트 · D-Day · 집중 모드 위젯 |
| `ui_settings.py` · `ui_search.py` · `ui_trash.py` | 설정 · 전역 검색 · 휴지통 창 |
| `show_desktop_guard.py` | `Win+D` 이후에도 창을 유지하는 Win32 레이어 제어 |
| `holidays.py` | 공휴일·음력 데이터 (생성물, `fetch_data.py`로만 갱신) |
| `diagnostics/` | 특정 PC 멈춤 현상 진단 도구 |

`large` 모드에서는 오른쪽에 일정·D-Day·집중·스티키 미니 패널이 나타나고,
떠 있던 위젯은 숨겨진 뒤 패널과 동기화됩니다.

---

## 데이터 저장 위치

```
%LOCALAPPDATA%\MyDesktopCalendar\
  calendar.db      SQLite 데이터베이스
  .salt            암호화 키 유도용 salt
  backups/         자동 백업 (.cnbak)
  error.log        오류 로그
```

데이터는 **PC와 Windows 계정에 묶여 있습니다.** 하드웨어 정보와 사용자명으로 키를 유도하기 때문에
`calendar.db`만 다른 PC로 옮기면 열리지 않습니다. PC를 옮길 때는 설정의 **내보내기/가져오기**를 사용하세요.

---

## 개발 참여

코드를 고치기 전에 **[`AGENTS.md`](AGENTS.md)를 반드시 읽어주세요.** 이 프로젝트의 규칙이 모두 여기 있습니다.

특히 다음 두 가지는 예외 없이 지켜야 합니다.

- **기존 사용자 데이터는 반드시 보존됩니다.** 스키마 변경은 `ALTER TABLE ... ADD COLUMN`만 허용하며
  테이블·컬럼 삭제와 재생성은 금지입니다. 데이터가 바뀌는 기능에는 왕복 검증 테스트를 함께 추가합니다.
- **보안 코딩 규칙**([`docs/CODING_STANDARDS.md`](docs/CODING_STANDARDS.md))을 따릅니다.
  `bare except` 금지, `except` + `pass` 단독 금지, 파일은 `with open`, DB는 `_connection()` 사용.

| 문서 | 내용 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | 개발 규칙, 모듈 상세, UI 제약, 릴리스 검증 기록 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 데이터 흐름, 보안, DB 스키마 |
| [`docs/UI_PATTERNS.md`](docs/UI_PATTERNS.md) | UI 컴포넌트 패턴과 색상 |
| [`docs/TESTING.md`](docs/TESTING.md) | 테스트 구조와 보안 점검 이력 |
| [`docs/CODING_STANDARDS.md`](docs/CODING_STANDARDS.md) | 행안부 CODEMIND 5개 보안 규칙 |

---

## 라이선스

이 프로젝트는 **GNU General Public License v3.0**을 따릅니다. 전문은 [`LICENSE`](LICENSE)를 참조하세요.

UI 프레임워크로 사용하는 `PySide6-Fluent-Widgets`가 GPLv3이므로, 이를 사용하는 기후노트도
같은 조건으로 배포됩니다.

번들된 제3자 구성요소와 각 라이선스 원문은 [`licenses/`](licenses/)에 있습니다.

만든이: 기후에너지환경부 보문산불주먹
