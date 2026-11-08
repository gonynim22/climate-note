# 작업 기록: 화면 글자 따기 쪽 전체 메모리

작성일: 2026-11-08 / 상태: 구현·검증 끝, push 완료

## 목표와 범위

- 목표: A4 한 쪽을 고를 때의 메모리를 줄인다. 판독 결과와 속도는 그대로 둔다(사용자 결정 2026-11-07 "정확도는 포기 못해").
- 변경 대상: `screen_text/engine.py`(모델 세션 실행 방식, `resize_bilinear`, `_detect`), `tests/test_screen_text_engine.py`, 계약 문서 `docs/SCREEN_TEXT.md`.
- 데이터 영향: 없음. DB·설정·Export는 바꾸지 않는다.
- 제외 범위: 모델 교체, 영역 크기 상한(별도 선택지), 판독이 달라지는 최적화.
- 시작 시 사용자 변경: `docs/SCREEN_TEXT.md` 5~6행에 사용자가 일부러 커밋하지 않은 두 줄이 있다. 이 작업을 커밋할 때도 그 두 줄은 빼고 올린다.

## 완료 조건

- [x] 인식이 끝난 뒤 onnxruntime이 붙잡는 메모리를 돌려준다(시험 `test_every_model_run_gives_back_its_working_memory`).
- [x] 위치 찾기 세션은 아레나 없이 돌고, 아레나가 없는 세션에도 엔진이 멈추지 않는다(`test_text_finder_takes_memory_straight_from_the_system`, `test_engine_reads_when_sessions_have_no_memory_arena`).
- [x] `resize_bilinear`가 전체 크기 임시 배열을 만들지 않고 값은 비트 단위로 같다(`test_resize_bilinear_does_not_build_full_size_temporaries`, `test_resize_bilinear_values_do_not_change` 5가지).
- [x] 위치 찾기 모델이 도는 동안 모델 입력만 쥔다(`test_detect_holds_only_the_model_input_while_the_model_runs`).
- [x] 판독이 바뀌지 않음: 평가 자료 24종 15,889장 판독·격자·상자 모두 같음, 캐시 없는 실제 모델 104장 같음.
- [x] `verify.py quick --tests` 글자 따기 시험 전체 통과.
- [ ] 필요한 수동 확인: 업무 PC에서 쪽 전체를 읽을 때의 메모리(작업 관리자). 배포 EXE는 `release`로 다시 만든다.

## 결정과 진행

- 2026-11-08: 사용자가 'Rust로 짜면 메모리가 주냐'고 물어 A4 한 쪽(`cond kma-p024-clean100-full0`, 793×1121)을 단계별로 쟀다. 파이썬과 numpy 27MB, onnxruntime을 불러온 뒤 54MB, 모델 세션 105MB, 인식 중 최대 작업집합 730MB, 끝난 뒤에도 710MB였다. onnxruntime과 numpy는 이미 C/C++이라 Rust로는 크게 줄지 않는다고 답했고 사용자가 이 작업을 골랐다.
- 모델 실행 옵션 비교(같은 쪽, 새 프로세스, 각 두 번):

  | 설정 | 최대 작업집합 | 끝난 뒤 | 최대 커밋 | 시간 |
  |---|---|---|---|---|
  | 처음(아레나 켬) | 730MB | 710MB | 1,280MB | 2.90초 |
  | 실행마다 돌려줌(`memory.enable_memory_arena_shrinkage=cpu:0`) | 678MB | 220MB | 1,172MB | 2.84초 |
  | 아레나 끔(`enable_cpu_mem_arena=False`, 두 모델 모두) | 575MB | 119MB | 930MB | 5.0초 |
  | CPU 공급자 `arena_extend_strategy=kSameAsRequested` | 733MB | 713MB | - | 2.78초 |

  아레나를 모두 끄면 인식 모델의 작은 실행이 많아 1.7배 느려졌다. `kSameAsRequested`는 공급자 옵션으로는 효과가 없었다. RapidOCR은 기본값으로 아레나를 끈다(대조 측정의 메모리 차이 일부).
- 최대가 어디서 생기는지(`scripts/mem_steps.py`): 2배로 키운 이미지(1920×1408)를 위치 찾기 모델에 넣는 한 번의 실행이다(실행 전 349MB → 670MB). 그 실행은 0.28초뿐이고 시간 대부분은 인식 모델(쪽당 21번 실행)이다. 그래서 위치 찾기만 아레나를 끄고 인식은 아레나+돌려줌으로 나눴다.
- numpy 쪽(`scripts/np_peak.py`, tracemalloc): 모델 밖 메모리 최대가 366MB였다. `resize_bilinear`가 2배 이미지 전체를 float32로 바꾸고, 가중치가 float32−int32 계산으로 float64가 되어 전체 크기 float64 임시 배열을 여러 장 만들었다. 위치 찾기 모델이 도는 동안에도 줄인 이미지(float64 61MB)와 캔버스(31MB)를 쥐고 있었다. 줄 묶음(32줄)마다 같은 식으로 계산하고 다 쓴 배열을 모델 실행 전에 놓아 366→107MB가 됐다. uint8을 실수로 바꾸는 값은 그대로라 결과가 비트 단위로 같다(정수 배 평균 경로는 전처럼 float32로 바꿔 평균한다).
- 띠로 나눠 위치 찾기(버림): 겹침을 256px로 늘려도 이진화가 바뀐 화소가 수천 개 남았다(`scripts/strip_probe.py`). 경계만이 아니라 맵 전체가 달라진다. 모델의 SE 블록이 이미지 전체를 평균 내기 때문이다.
- 함정: 아레나가 없는 세션에 `memory.enable_memory_arena_shrinkage`를 주면 onnxruntime이 `InvalidArgument`로 실행을 거부한다. 메모리를 아끼려고 아레나를 끄는 변경이 글자 따기를 통째로 멈추지 않게, 세션 옵션에 아레나가 있을 때만 준다(시험으로 고정).
- TDD: 시험 5개(값 비교 5가지 포함)를 먼저 쓰고 고치기 전에 실패함을 봤다(`{None} == {'cpu:0'}`, `InvalidArgument`, 임시 배열 362MB > 78MB, 모델 실행 중 77MB > 26MB, `{'det': True}`). 첫 시험은 위치 찾기에 아레나가 없어진 뒤 '아레나를 둔 세션의 실행'으로 고쳐 썼고, 돌려 달라는 옵션을 빼 보는 변이 확인에서 실패함을 다시 봤다.
- 최종(같은 쪽, `scripts/mem_parts.py`·`mem_detarena.py`): 한 번 읽을 때 최대 작업집합 454MB, 최대 커밋 834MB, 끝난 뒤 185MB, 2.81초. 한 프로세스에서 두 번 읽으면 최대 630MB, 끝난 뒤 195MB. 150% 쪽(`goesan-p001-dpi150-full0`)은 한 번 409MB, 두 번 587MB. 판독 해시는 처음과 같다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `verify.py quick --tests tests/test_screen_text*.py` | 통과(1,409) | `output/harness/20261108-130822-a0951cb7e8` | 글자 따기 시험 파일 전체(랩 도구 포함) |
| 평가 자료 24종 판독 비교 | 같음(15,889/15,889, 격자·상자도 같음, 예외 0) | `output/screen_text_lab/analysis-20261106/results/<자료>__m2.json` | 코드 사본 `snap/m2`, 기준 `r4`. 모델 캐시가 모두 맞았다(모델 입력이 비트 단위로 같다) |
| 캐시 없는 실제 모델 판독 비교 | 같음(104/104) | `results/<자료>__m2nc.json` | xls·hwp·cond hold·e5·tskew 표본 |
| 단계별 메모리 | 완료 | `scripts/mem_parts.py`, `mem_steps.py`, `mem_detarena.py`, `np_peak.py` | 위 표 |
| `release` | 미실행 | | 배포 때 PowerShell에서 |

## 미해결과 인계

- 남은 문제: 한 프로세스에서 두 번째로 읽을 때 최대가 약 630MB로 첫 번째(454MB)보다 크다. 첫 실행 뒤 남는 약 80MB 위에 다음 위치 찾기 계산이 얹힌다. 2배 위치 찾기 한 번의 계산(약 320MB)은 판독을 바꾸지 않고는 줄이지 못했다.
- 결과 이름 주의: `results/marks__m2.json`은 11-07의 다른 실험 결과였다. `marks__m2_old20261107.json`으로 이름을 바꿔 보존하고 다시 돌렸다.
- 변경한 정본 문서: [화면 글자 따기 계약](../SCREEN_TEXT.md)의 알려진 한계에 메모리 항목.
- 다음 행동: 사용자 결정(커밋 여부, 다음 선택지: 영역 크기별 측정·`「 」`).
- 배포·커밋·push 여부: 사용자 "커밋만"으로 로컬 커밋, 2026-11-08 저녁 사용자 요청으로 원격 위로 다시 쌓아 GitLab→GitHub push(`4c92402`). 2026-11-08 release `20261108-231658-2695187d46` EXE에 들어갔고 사용자가 GitLab Release v4.8을 게시했다(태그 `v4.8` → `d814155`, GitHub 태그도 같음)
