# 작업 기록: 단위 환산기 리디자인 3안

작성일: 2026-09-24 / 상태: 조사·3안 제작·전체 25분류 확장·검증 완료

## 목표와 범위

- 웹의 실제 계산기·단위 변환 도구 디자인을 분석하고 구조가 다른 시안 3개를 비교 가능한 형태로 제공한다.
- 변경 대상: 이 작업 기록과 `output/unit-converter-redesign-20260924/`의 시안·참고 분석·검증 결과.
- 데이터 영향: 없음. 앱 런타임·DB·설정·버전·EXE를 변경하지 않는 디자인 검토 단계다.
- 시작 상태: HEAD `e9604c8`. 기존 `.gitignore`, AGENTS.md, RELEASE_HISTORY.md와 미추적 기존 작업 기록 3개를 보존한다.

## 완료 조건

- [x] 실제 웹 참고 자료와 화면을 확인하고 채택/제외 이유를 기록한다.
- [x] A 결과 중심, B 작업 도구, C 노트형의 서로 다른 3개 시안을 만든다.
- [x] 실제 앱과 같은 25분류·182개 단위를 세 시안에 동일하게 제공한다.
- [x] 전체 분류 전환, 값/조건 입력, 기록 복원을 눌러볼 수 있게 한다.
- [x] 렌더·좁은 화면·주요 상호작용을 확인하고 결과/제약을 기록한다.

## 결정과 진행

- 세 안의 창을 기존 앱과 같은 440×580px로 고정하고, 작은 화면에서는 폭만 줄인다. 전체 분류를 넣은 상태의 화면 밀도와 스크롤을 비교한다.
- 실제 UI의 조건 요약·근사 표시·최근 기록 조건 복원·오프라인 계약을 유지하는 방향으로 제안한다.
- 최초 수질·기체·온도 3분류 시안에 대해 사용자가 같은 단위 수로 비교하기를 요청했다. `unit_converter.py`에서 카탈로그를 직접 추출해 세 안 모두 25분류·182개 단위의 ID·명칭·기호·순서·계수·기본 선택·주의사항을 공유한다.
- A/C는 그룹별 전체 분류 선택 메뉴, B는 전체 25분류의 28px 행/13px 글꼴 목록이다. 상단 공통 선택기로 세 안의 분류·입력값·입출력 단위를 함께 맞춘다. 초기 선택은 길이 10cm → inch로 통일한다.
- 참고: [Raycast](https://manual.raycast.com/calculator), [Soulver](https://soulver.app/), [Numi](https://numi.app/), [Windows Calculator](https://github.com/microsoft/calculator).
- Raycast/Soulver/Windows 공식 화면을 직접 확인했다. Numi는 공식 문서만 분석 근거로 사용하고 영상 화면을 확인했다고 주장하지 않는다. 관찰/적용 판단은 [분석](../../output/unit-converter-redesign-20260924/reference-analysis.md)에 구분했다.
- [3안 비교](../../output/unit-converter-redesign-20260924/index.html), [비교 이미지](../../output/unit-converter-redesign-20260924/comparison.png), [사용 설명](../../output/unit-converter-redesign-20260924/README.md)을 제공한다. A를 기본 방향으로 추천하며 B는 잦은 분류 전환, C는 반복 계산 비교가 장점이다.
- 시안의 계산/최근 12개 기록은 브라우저 메모리 전용이다. 긴 목록·조건·기록은 창 내부에서 스크롤한다. 공용 계산 모델은 전체 선형/비선형 환산, 밀도·기체·온도차 조건을 포함하며 Python 정본과 대조했다. 실제 Qt 앱 반영은 디자인 선택 후 별도다.

## 검증 증거

| 범위 | 상태 | 실행 ID / 경로 | 유의사항 |
|---|---|---|---|
| 전체 단위 계산 대조 | 통과: 1,666개 | `20260924-converter-designs-full-catalogue` / [model-parity.json](../../output/unit-converter-redesign-20260924/model-parity.json) | 성공 1,624·예상 오류 42개 일치 |
| 전체 분류 UI·밝은/어두운 비교·320px 조건 입력 | 통과 | [summary.md](../../output/unit-converter-redesign-20260924/qa-full/summary.md), [입력 해시](../../output/unit-converter-redesign-20260924/qa-full/result.json) | Qt WebEngine DOM 이벤트/렌더 검사. 앱 release·실제 Qt 앱/DPI 수동 검사와 구분 |
| 최초 3분류 시안 | 이전 결과: 43개 | `20260924-converter-designs` / [summary.md](../../output/unit-converter-redesign-20260924/qa/summary.md) | 전체 단위 확장의 현재 통과 근거로 재사용하지 않음 |

## 미해결과 인계

- 세 안을 사용자가 비교한 뒤 최종 앱 구현 범위를 정한다.
- 앱 빌드·커밋·push·게시: 이번 디자인 검토 단계에서 수행하지 않는다.
