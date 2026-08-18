# Testing & Security Audit Reference

## Test Suite

- **Location**: `tests/` (pytest 기반 전체 테스트)
- **구조**: `conftest.py` (격리 픽스처) + DB/보안/스트레스/UI 테스트와 `test_ui_calendar_drag.py`, `test_ui_sticky.py`, `test_show_desktop_guard.py`
- **격리 전략**: `app_dir` 픽스처가 `security.APP_DIR`, `SALT_FILE`, `database.DB_FILE` 등을 `monkeypatch`로 `tmp_path`에 패치하고 Fernet 캐시 초기화. 테스트 간 DB/암호화 키 완전 격리.
- **스트레스 커버**: 1년×3색상 1,095개 일정, 365회 메모 upsert, 10KB 메모, Export/Import 왕복, 100회 추가/삭제 사이클, 백업 회전, VACUUM 무결성
- **리소스/빌드 커버**: 번들 Fluent UI System Icons 존재 여부, 일반 SVG tint, 컬러 SVG palette 보존, `build.spec` 리소스/라이선스/QtSvg 포함, 설정창 라이선스 고지를 검증한다.
- **v3.4 무손상 커버**: v16→v17 전후 schedule raw row exact snapshot, 팔레트 설정 Export/Import 왕복, canonical 3슬롯 유지, 음수 모니터 좌표 drag/clamp, large 모드 드래그 비활성, 800×560 설정 최소 크기, sticky HTML/plain-text 불변, Win+D topmost pulse/데스크톱 레이어 재고정/hook 해제를 검증한다.
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
