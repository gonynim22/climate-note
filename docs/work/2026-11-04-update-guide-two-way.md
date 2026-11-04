# 작업 기록: 앱 업데이트 안내창 두 갈래(온나라 / GitLab)

작성일: 2026-11-04 / 상태: 구현·자동 검사 완료, 커밋·EXE 반영 대기

## 목표와 범위

- 목표: GitLab·GitHub 공개 저장소가 생겨, '앱 업데이트' 안내창에서 받는 곳을 크게 두 갈래로 고르게 한다. 온나라를 고르면 v4.6 안내 문구를 그대로 보여 주고, GitLab을 고르면 브라우저로 외부 주소를 연다(사용자 지시).
- 변경 대상: `src/ui_update.py`(안내창 전체 교체), `tests/test_ui_update.py`(신규), `tests/test_ui.py`(옛 안내창 테스트 2개 제거), `docs/UI_PATTERNS.md`·`docs/ARCHITECTURE.md`.
- 데이터 영향: 없음. DB·설정·암호화·Export를 읽거나 쓰지 않는다.
- 제외 범위: 새 버전 자동 감지(앱이 네트워크에 접속하는 기능, 오프라인 전용 계약 변경 필요 — 사용자 결정 대기), 버전 번호·EXE 빌드.
- 시작 시 사용자 변경: 추적 파일 변경 없음(미추적 작업 기록들은 그대로 둠).

## 완료 조건

- [x] 첫 화면: 좌우 타일 '온나라 시스템에서 받기'(공공기관 업무망, 연한 초록)·'GitLab에서 받기'(외부 인터넷망, 연한 파랑), 닫기
- [x] 온나라 → 같은 창에서 v4.6과 같은 안내 문구(제목·강조·5단계·현재 앱 버전), '받는 곳 다시 고르기'로 복귀, 브라우저 열지 않음
- [x] GitLab → 기본 브라우저로 `…/-/releases/permalink/latest`를 열고 창 닫기(앱은 접속하지 않음)
- [x] 관련 자동 검사: `quick --tests tests/test_ui_update.py tests/test_ui.py`
- [ ] 수동 확인: 실제 EXE에서 더보기 › 앱 업데이트 → 두 타일 마우스 올림·누름, 키보드 Tab/Enter/Esc, PIN 잠금 때 닫힘, 중간·크게 크기

## 결정과 진행

- 2026-11-04: 첫 시안(A 카드형·B 좌우 타일·C 남색 머리띠)을 Claude Design 캔버스 「기후노트 앱 업데이트 안내창」(https://claude.ai/artifact/6CqTGa7jfa5pxaFqo7mDeU)에 실제 캘린더 위에 그려 비교. 사용자가 B안 선택 → "버튼 색을 달리, 너무 하얗다" → "연하게, 서로 다른 색감" → 초록·파랑 연한 판으로 확정. 온나라 안내도 B안 모양(번호 동그라미·강조색은 온나라 초록).
- 주소 `/-/releases/permalink/latest`는 302로 `/-/releases/v4.6`에 이동함을 확인. Release의 `기후노트_v4.6.zip` 안에는 `기후노트_v4.6.exe` 하나뿐.
- 구현: qfluentwidgets `MaskDialogBase`(바탕 막 `rgba(1,20,48,44%)`, 그림자) 위에 카드 직접 구성. 두 화면은 한 대화상자 안에서 보이기만 바꾸고 높이를 내용에 맞춘다. 아이콘은 코드 안 선 SVG를 `QSvgRenderer`로 2배 밀도 렌더.
- 실제 렌더에서 `QWidget#centerWidget QLabel {background: transparent}` 규칙이 개별 꼬리표·번호 동그라미 바탕을 덮어 안 보이던 문제를 발견해 그 규칙을 지움. 같은 회귀를 막으려고 테스트가 실제 그려진 픽셀 색을 확인한다.
- 옛 `UPDATE_GUIDE_URL`(온나라 지식 홈)은 단추가 없어 쓰이지 않던 값이라 제거. UI 문서의 "아래 단추로 온나라 주소를 연다"는 사실과 달라 함께 고침.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `tools/verify.py quick --tests tests/test_ui_update.py tests/test_ui.py` | 통과(322개) | `20261104-204045-6c432ed597` / [summary.md](../../output/harness/20261104-204045-6c432ed597/summary.md) | 합성 데이터, 종료 코드 0 |
| 실제 앱 코드 렌더(기본·크게, 첫 화면·온나라·복귀) | 확인 | `output/design/update-guide-20261104/impl_*.png` | `render_impl.py`, 합성 데이터·화면 밖 렌더 |
| 실제 EXE 수동 확인 | 미실행 | | 다음 release 빌드 뒤 |

## 미해결과 인계

- 남은 문제 / 수동 확인: 위 수동 확인 항목. 이미 배포한 v4.6 EXE의 안내창은 바뀌지 않는다.
- 변경한 정본 문서: [UI 계약](../UI_PATTERNS.md) Update Guide, [아키텍처](../ARCHITECTURE.md) 모듈 표·오프라인 예외.
- 다음 행동: 커밋·push 여부와 반영할 버전(EXE) 결정. 자동 감지 기능은 사용자가 "설정에서 인터넷 접속을 켠 PC만"으로 결정했고 화면 ①~⑤ 확정, 설계 문서 [2026-11-04-update-check-design.md](../superpowers/specs/2026-11-04-update-check-design.md) 작성(사용자 승인 대기) → 승인되면 구현 계획(writing-plans)부터.
- 배포·커밋·push 여부: 수행하지 않음
