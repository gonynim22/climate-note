# 작업 기록: README 대표 이미지 새 디자인(A1 맑은 하늘)

작성일: 2026-10-29 / 상태: 제작·검증 완료, 커밋·push는 아래 기록

## 목표와 범위

- 목표: 같은 날 갱신한 대표 이미지([이전 기록](2026-10-29-readme-hero-refresh.md))의 전체 느낌이 마음에 들지 않는다는 사용자 의견에 따라, 새 디자인 시안 중 사용자가 고른 A1으로 README 첫 이미지를 바꾸고 main에 push한다.
- 변경 대상: `readme/app.png`, `README.md` 대체 텍스트, 이 작업 기록.
- 데이터 영향: 없음. 화면 사진은 이전 기록의 합성 데이터 캡처(`output/harness/20261029-readme-hero-v45-capture/`, v4.5 실제 Windows Qt 위젯, DPR 2)를 그대로 썼다.
- 제외 범위: 제품 코드·DB·salt·설정·의존성·EXE·공개 Release.
- 시작 상태: main `206b85c`, 원격 main과 일치, 추적 파일 변경 없음. 기존 미추적 작업 문서와 `motion/`은 커밋에서 제외한다.

## 완료 조건

- [x] 사용자가 고른 A1 디자인: 연한 하늘색 바탕(`#EEF5FF`)·하늘색 원(`#D3E4FC`), 기울인 크게 모드 화면과 앞에 겹친 기본 크기 화면, 아이콘·이름·슬로건·보조 문구·버전 칩.
- [x] 문구: 슬로건 "늘 보이는 곳에, 오늘 할 일", 보조 "일정 · 메모 · D-Day · 집중 모드를 바탕화면에 / 인터넷 없이, 이 PC 안에서만"(사용자 선택).
- [x] 2560×1280 원본과 README 표시 크기(1040px) 시각 확인.
- [x] 변경 범위 확인 후 세 파일만 커밋, `git push origin main`.

## 결정과 진행

- 2026-10-29: claude.ai 디자인 캔버스에서 A~E 5개 시안을 만들었다. 사용자가 E(Win+D 전후 비교)를 빼고, 슬로건은 후보 중 "늘 보이는 곳에, 오늘 할 일"을 골랐다. A(남색 무대)가 좋지만 어둡다고 해 밝은 변형 4개(A1 하늘·A2 코발트·A3 민트·A4 흰 바탕+남색 원)를 더 만들었고 A1을 확정했다.
- 제작 소스는 `output/design/readme-hero-a1-20261029/`에 보존했다(`hero.html`, 같은 폴더의 캡처·아이콘 사본, 저장소 `fonts/`의 Pretendard). `render.py`가 헤드리스 Chrome으로 1280×640 화면을 배율 2로 렌더한다.
- 이전 PNG는 `output/harness/20261029-readme-hero-a1/app-before.png`에 보존했다.

## 검증 증거

| 명령/범위 | 상태 | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| 로컬 OSV(`requirements.txt:requirements-lock.txt`) | 통과 | `output/harness/20261029-readme-hero-a1/osv.log` | 35개 패키지, 문제 없음. push 서버 검사 대비 |
| `render.py` 렌더 | 통과 | `output/design/readme-hero-a1-20261029/hero-final.png`, `preview-1040.png` | 2560×1280 RGB, Pretendard 적용·잘림 없음 시각 확인 |
| `readme/app.png` 교체 | 통과 | SHA-256 `de3d5de8b7c15006d3cce1e44cf70d24f25b4ff1ca018729e7c8aa8580e50f9c`, 326,260 bytes | 렌더 결과와 해시 일치 |
| 전체 pytest / release / 실기 확인 | 미실행 | 해당 없음 | 제품 코드·EXE 변경 없는 대표 이미지 작업 |

## 미해결과 인계

- 남은 문제 / 수동 확인: GitLab 웹에서 실제 표시 확인.
- 변경한 정본 문서: README 대표 이미지와 대체 텍스트.
- 배포·커밋·push: 사용자 승인에 따라 `README.md`, `readme/app.png`, 이 기록만 커밋하고 `git push origin main`으로 올린다. EXE 배포는 하지 않는다.
