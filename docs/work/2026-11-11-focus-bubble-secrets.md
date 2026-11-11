# 작업 기록: 집중 위젯 응원 문구 고르기를 secrets로

작성일: 2026-11-11 / 상태: 구현·자동 검증 완료, 로컬 커밋(push 전)

## 목표와 범위

- 목표: 기관 소스 점검이 지적한 `random` 사용을 없앤다(점검 원본은 저장소 밖). 지적된 곳은 집중 위젯 토마토 말풍선의 응원 문구 고르기이고 보안 용도가 아니다.
- 변경 대상: `src/ui_focus.py`(import와 고르기 한 줄), `tests/test_ui_focus.py`·`tests/test_ui_holiday_theme_focus.py`(바꿔 끼우는 대상 이름), `tests/test_security_scan_rules.py`(재발 방지), `docs/CODING_STANDARDS.md` 7절, `AGENTS.md` 한 줄.
- 데이터 영향: 없다. 바뀐 줄은 DB·암호화·salt·설정 키를 읽거나 쓰지 않는다. `database.py`·`security.py`는 고치지 않았다.
- 제외 범위: 같은 점검의 다른 지적 대응(코드 변경 없음, 저장소 밖에서 관리), `tests/`·`tools/`가 합성 자료를 만들 때 쓰는 seed 있는 `random`.
- 시작 시 사용자 변경: 다른 세션의 미추적 작업 기록과 `motion/`. 건드리지 않았다.

## 완료 조건

- [x] 구현할 동작과 유지할 계약: 말풍선은 전처럼 22개 문구 가운데 하나를 무작위로 보인다. `secrets`는 Python용 OpenSSL을 막은 프로세스에서도 동작한다.
- [x] 관련 자동 검사: `quick --tests`(아래 표).
- [ ] 필요한 수동 확인: 따로 없다(화면 동작이 같다). v4.9 최종 release와 교대 실행에서 함께 본다.

## 결정과 진행

- 2026-11-11: 점검에 낸 코드에서 `random`을 쓰는 곳은 `ui_focus.py` 한 곳(import 4줄, 사용 739줄)뿐이었다. `secrets.choice`는 같은 균등 선택이고, `ssl`·`_ssl`·`_hashlib`를 막은 프로세스에서도 동작했다(`hmac`이 내장 비교 함수로 대신한다, 직접 확인).
- 재발 방지 테스트를 먼저 써서 `src/ui_focus.py:4` 하나로 실패하는 것을 본 뒤 고쳤다. 검사 범위는 점검에 내는 코드(루트 스크립트·`src/`·`screen_text/`)다. `tests/`·`tools/`는 합성 자료를 다시 만들려고 seed 있는 `random`을 쓰므로 뺐다.
- 규칙은 [보안 코딩](../CODING_STANDARDS.md) 7절과 `AGENTS.md`에 남겼다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| 새 검사만 먼저(RED) | 실패(의도) | 직접 실행 | `assert ['src/ui_focus.py:4'] == []`, 나머지 3개 통과 |
| 관련 pytest 4개 파일 | 통과 | 직접 실행 | 130 통과 |
| `verify.py quick --tests tests/test_security_scan_rules.py tests/test_ui_focus.py tests/test_ui_holiday_theme_focus.py tests/test_packaging.py` | 통과 | `output/harness/20261111-205902-ad41291780/summary.md` | 354 통과. 커밋 전 작업본 |
| `release`·교대 실행 | 미실행 | | v4.9 마무리 때 |

## 미해결과 인계

- 남은 문제 / 수동 확인: 없다. EXE에서의 확인은 v4.9 최종 release에 맡긴다.
- 변경한 정본 문서: `AGENTS.md`, `docs/CODING_STANDARDS.md`.
- 다음 행동: push(사용자 승인 뒤). 점검의 다른 지적은 저장소 밖에서 대응한다.
- 배포·커밋·push 여부: 사용자 승인으로 로컬 커밋했다. push와 배포는 하지 않았다.
