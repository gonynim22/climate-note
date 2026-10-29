# 작업 기록: README 꾸미기(R2 배지·버튼·아이콘형)

작성일: 2026-10-29 / 상태: 제작·로컬 확인 완료, push는 사용자 승인 후

## 목표와 범위

- 목표: "검은 글씨에 크기만 다양한 딱딱한 매뉴얼 같다"는 사용자 의견에 따라, 디자인 캔버스의 README 시안 3개(R1 정돈형·R2 배지·버튼·아이콘형·R3 기능 카드형) 중 사용자가 고른 R2로 README를 꾸민다.
- 변경 대상: `README.md`, 새 SVG 10개(`readme/badge-*.svg` 4개, `readme/button-*.svg` 2개, `readme/icon-*.svg` 4개), 이 작업 기록.
- 데이터 영향: 없음. 제품 코드·DB·설정·의존성·EXE 변경 없음.
- 시작 상태: main `1cc388d`, 원격 main과 일치. 기존 미추적 작업 문서와 `motion/`은 커밋에서 제외한다.

## 완료 조건

- [x] GitLab이 허용하는 요소만 사용: `<p align="center">`, `<img width/height/align>`, HTML 표, `<kbd>`, `<details>`. CSS는 쓰지 않는다.
- [x] 대표 이미지 아래 배지 4개(버전 v4.5·Windows 10 · 11·오프라인 전용·GPL-3.0)와 "최신 버전 받기"(Releases)·"상세 안내"(README_detail.md) 버튼.
- [x] 소제목에 하늘색 선 아이콘(주요 기능·받기·업데이트·요구 환경 · 라이선스), 주요 기능 표, 미니앱 아이콘 줄(저장소의 기존 미니앱 SVG를 그대로 참조).
- [x] 기존 README의 사실과 링크를 모두 유지: 다른 PC로 옮기기·버전별 주의사항은 `<details>`로 접고, 라이선스·한컴 고지 문구는 원문 그대로 둔다.
- [ ] GitLab 웹에서 실제 표시 확인(push 후).

## 결정과 진행

- 2026-10-29: 배지·버튼은 글자가 든 SVG다. `<img>` 안의 SVG는 외부 글꼴을 못 쓰므로 `Segoe UI`·`Malgun Gothic` 시스템 글꼴과 가운데 정렬을 쓰고, 다음 버전에서는 `badge-version.svg`의 `v4.5` 글자만 고치면 된다(글자 폭이 크게 바뀌면 `width`·뒤 칸 폭도 함께 조정).
- 색은 미니앱 아이콘 계열(파랑 `#2563EB`·청록 `#0B7285`·보라 `#6741D9`)과 흰 글자 대비 4.5:1 이상의 초록 `#1A7A43`, 왼쪽 칸 남색 `#33476B`를 쓴다.
- 첫 줄의 `# 기후노트` 제목은 대표 이미지에 이름이 크게 들어가 있어 뺐다.
- GitLab Markdown 미리보기 API는 로그인이 필요해 쓰지 않았다. 로컬 미리보기는 `output/design/readme-r2-20261029/preview.py`(marked + GitLab 비슷한 CSS)로 그렸으며 GitLab의 실제 정화(sanitize) 결과와 다를 수 있다.

## 검증 증거

| 명령/범위 | 상태 | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| README 상대 링크·이미지 경로 존재 확인 | 통과 | 셸 확인(22개 경로) | `src`·`href`·Markdown 링크 전부 |
| `pytest tests/test_ui_licenses.py` | 통과 | 13개 통과 | 한컴 고지 문구 유지 확인 포함 |
| 로컬 미리보기 렌더 | 통과 | `output/design/readme-r2-20261029/preview-full.png` | 1000px 폭, 배지·버튼·아이콘·표·접기 시각 확인 |
| GitLab 실제 표시 | 미실행 | 해당 없음 | push 후 확인 |

## 미해결과 인계

- 남은 문제 / 수동 확인: GitLab 웹에서 `align` 가운데 정렬·소제목 아이콘 정렬·다크 모드 표시 확인.
- 변경한 정본 문서: README.
- 배포·커밋·push: 위 파일만 커밋한다. push는 사용자 승인 뒤 `git push origin main`.
