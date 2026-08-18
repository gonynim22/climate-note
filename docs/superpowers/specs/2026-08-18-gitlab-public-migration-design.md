# GitLab 공개 저장소 전환 설계

작성일: 2026-08-18 · 대상 버전: v3.5

## 1. 배경과 목적

기후노트는 지금까지 로컬 git 저장소에서만 관리됐다(커밋 7개, remote 없음).
이를 **기관 내부 GitLab**에 올려 다음 두 가지를 얻는다.

- **백업·이력관리**: 로컬 PC 유실에 대비한 원격 사본 확보
- **동료 기여·협업**: 담당자 변경·인사이동에 대비해 다른 직원이 소스를 이어받고 기여할 수 있는 상태

공개 범위는 **기관 내부 GitLab 인스턴스 내 공개**다. 인터넷 전체 공개가 아니다.

## 2. 결정 사항

| 항목 | 결정 | 근거 |
|---|---|---|
| 공개 범위 | 기관 내부 GitLab · 인스턴스 내 공개 | 외부 유출 없음. 업무메일·기관명 노출 문제 해소 |
| GitLab 히스토리 | **v3.5 스냅샷 1커밋으로 새 출발** | 사용자 결정. 기존 이력은 로컬 아카이브로 보존 |
| 로컬 히스토리 | `archive/local-v3.5` 브랜치로 보존, push 안 함 | 이력을 잃지 않으면서 GitLab은 깨끗하게 시작 |
| `security/` | 저장소에서 완전 제외 | 기관 내부 문서(취약점 점검 보고서·반론서). 담당자가 저장소 외부에서 별도 관리 |
| `CODING_STANDARDS.md` | `docs/`로 이동 | 보안 자료가 전부 외부로 나가 `security/` 폴더가 불필요해짐. `docs/`의 다른 참조 문서와 성격이 같음 |
| `holidays.py` | 저장소에 포함 (gitignore 해제) | 없으면 클론 후 `main.py`가 ImportError. 재생성에 개인 API 키 필요. 데이터는 공공데이터 |
| LICENSE | GPLv3 추가 | QFluentWidgets가 GPLv3. 기관 내부 소스 공개 + 기관 내부 EXE 배포로 제공 범위가 일치 |
| `diagnostics/` | 포함 | 설정/휴지통 멈춤이 미해결 조사 상태. 동료가 재현 PC를 만나면 즉시 사용 |
| 매뉴얼 리디자인 시안 | 제외 | v3.4 기준 미확정 초안. 매뉴얼은 v3.5로 갱신해야 하는 상태 |
| `개선사항.txt` | 제외 | v3.4 배포 공지문. 온나라 게시물로 관리 |

## 3. 저장소·브랜치 구조

```
로컬
  archive/local-v3.5   기존 7개 커밋 (security/ 포함). 로컬 전용, push 금지
  main                 orphan 브랜치. v3.5 스냅샷 1커밋

GitLab
  main                 위 main만 push. 이후 v3.5+ 개발은 이 브랜치에서
```

**orphan 브랜치를 쓰는 이유**: git push는 브랜치의 전체 히스토리를 전송한다.
기존 `main`을 그대로 push하면 첫 커밋에 포함된 `security/`가 함께 올라간다.
부모 없는 orphan 브랜치는 과거 커밋과 계보가 끊겨 있어, GitLab에는
`security/`가 처음부터 존재하지 않은 상태가 된다.

이후 개발은 `main` 하나에서만 이뤄지므로 이중 커밋 부담이 없다.

## 4. 파일 매니페스트

기준 **128개**. 현재 추적 137개에서 14개를 빼고 5개를 더한다.
여기에 이 전환 작업의 spec·plan 문서 2개가 `docs/superpowers/`에 추가되어 **최종 130개**가 된다.

| 분류 | 개수 | 내용 |
|---|---|---|
| 루트 | 36 | 소스 `*.py` 21, 빌드 6, 문서·설정·이미지 9 (`LICENSE`·`README.md`·`holidays.py` 포함) |
| `docs/` | 28 (+2) | 참조 문서 4 + `superpowers/` spec·plan 24. 이 작업의 spec·plan 2개가 더해진다 |
| `tests/` | 23 | 전체 테스트 (약 8,000줄) |
| `resources/` | 21 | Fluent UI System Icons SVG |
| `icon/` | 7 | 앱 아이콘 |
| `fonts/` | 6 | Pretendard 4 + Font Awesome 2 |
| `licenses/` | 5 | 제3자 라이선스 원문 |
| `diagnostics/` | 2 | 설정 멈춤 진단 도구 |

### 제외 (14개)

- `security/` 13개 — 취약점 점검 보고서 PDF 2, CODEMIND 예제·반론서 txt 10, `CODING_STANDARDS.md` 1(→ `docs/`로 이동)
- `개선사항.txt` 1개

### gitignore로 계속 제외

`dist/`, `build/`, `output/`, `backups/`, `*.db`, `.salt`, `.lock`, `.env`,
`audit.log`, `_review_*.py`, `_test_api.py`, `check.log`, `.venv/`, `.claude/`,
`__pycache__/`, 테스트 임시 폴더

## 5. 신규·수정 파일

### `LICENSE` (신규)
GPLv3 전문. `licenses/QFluentWidgets-LICENSE.txt`에 이미 있는 GPLv3 원문과 동일한 내용을 루트에 배치한다.

### `README.md` (신규)
저장소 첫 화면. 다음을 담는다.

- 프로젝트 소개 — 기후노트가 무엇인지, 오프라인 전용 Windows 데스크톱 앱임
- 요구 환경 — Windows, Python 버전, 주요 의존성
- 설치·실행 — `pip install -r requirements.txt` → `python main.py`
- 테스트 — `python -m pytest tests -q`
- 빌드 — `python build_app.py` → `dist/기후노트_v3.5.exe`
- 프로젝트 구조 — 모듈 역할 요약 (상세는 `AGENTS.md`로 연결)
- 기여 안내 — `AGENTS.md`의 데이터 보존 규칙·보안 코딩 규칙을 반드시 읽을 것
- 라이선스 — GPLv3, 그 이유(QFluentWidgets)

`AGENTS.md`가 이미 상세 개발 문서 역할을 하므로 README는 중복 없이 진입점 역할만 한다.

### `.env.example` (수정)
현재 내용이 실제와 다르다. `OPENAI_API_KEY`/`OTHER_SERVICE_KEY`/`DEBUG`는 이 프로젝트에서 쓰이지 않는다.
실제 사용 키는 `fetch_data.py:16`의 `LUNAR_API_KEY` 하나뿐이며, 공공데이터포털 발급 키다.
용도(`holidays.py` 재생성)와 발급처를 주석으로 명시한다.

### `.gitignore` (수정)
- `holidays.py` 항목 제거 (저장소에 포함하기로 결정)
- `security/` 추가 (담당자가 로컬에 되돌려 놓아도 커밋되지 않도록)

## 6. 실행 순서

되돌릴 수 없는 작업이 포함되므로 백업을 먼저 만든다.

1. **미러 백업** — 현재 저장소 전체를 `.git` 포함해 별도 위치에 복제. 이후 모든 단계의 되돌리기 지점
2. **작업 트리 정리** — 신규 파일 4종 작성/수정 (`LICENSE`, `README.md`, `.env.example`, `.gitignore`)
3. **기존 브랜치 보존** — 현재 `main`을 `archive/local-v3.5`로 이름 변경
4. **orphan 브랜치 생성** — 부모 없는 `main` 생성, 매니페스트 128개만 스테이징
5. **v3.5 스냅샷 커밋** — 단일 커밋
6. **검증** — 아래 기준 전부 통과 확인
7. **GitLab 연결·push** — remote 추가 후 `main`만 push. `archive/local-v3.5`는 push하지 않음

3~5단계는 사용자 승인 후 실행한다. 7단계는 외부로 나가는 작업이므로 별도 승인을 받는다.

## 7. 검증 기준

push 전에 다음을 모두 확인한다.

| # | 항목 | 통과 조건 |
|---|---|---|
| 1 | `security/` 부재 | `git log --all --diff-filter=A -- 'security/*'`가 `main`에서 0건 |
| 2 | 시크릿 부재 | `.env`, `.salt`, `*.db`, `audit.log`가 커밋에 없음 |
| 3 | 매니페스트 일치 | `security/`·`개선사항.txt`·gitignore 대상이 0건이고 `holidays.py`·`LICENSE`·`README.md`가 존재. 총계는 130 근처(작업 문서 수에 따라 변동) |
| 4 | 클론 실행 가능 | 별도 임시 폴더에 클론 → 의존성 설치 → `python main.py` 기동 |
| 5 | 테스트 통과 | 클론본에서 `python -m pytest tests -q` 통과 |
| 6 | 문서 링크 | 모든 markdown 상대 링크가 실제 파일로 해석됨 |
| 7 | 로컬 이력 보존 | `archive/local-v3.5`에 기존 7개 커밋이 그대로 존재 |

4·5번은 `holidays.py` 포함 결정이 실제로 동작하는지 확인하는 핵심 검증이다.

## 8. 되돌리기

- 1단계 미러 백업이 모든 되돌리기의 기준점이다
- `archive/local-v3.5`가 남아 있는 한 기존 이력은 언제든 복구 가능
- GitLab push 전까지는 모든 단계가 로컬에서 되돌릴 수 있다
- push 이후 되돌리기는 GitLab 저장소 삭제·재생성이 필요하므로, push는 검증 통과 후에만 한다

## 9. 범위 밖 (후속 과제)

- **매뉴얼 v3.5 갱신** — `manual.qmd`가 v3.4 기준. 리디자인 시안 2종도 함께 정리 필요
- **AGENTS.md 라이선스 항목 갱신** — 소스 공개로 GPLv3 경로가 열리므로 HOLD 상태 재검토. 단 SBOM·Qt 고지·서명은 그대로 남음
- **QFluentWidgets 버전 확인** — AGENTS.md 검증 기록은 1.11.1, 로컬 설치본은 1.11.2
- **설정/휴지통 멈춤 조사** — `diagnostics/`를 저장소에 포함하되 조사 자체는 별개 작업
- **CI 구성** — 필요해지면 이후에 논의
