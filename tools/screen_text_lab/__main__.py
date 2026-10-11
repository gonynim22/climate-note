"""대규모 작업은 명시적인 subcommand에서만 시작한다."""
import argparse
import sys

from .experiments import CANDIDATES
from .recognizers import RECOGNIZERS, INPUT_PROFILES


def parser():
    cli = argparse.ArgumentParser(description="화면 글자 따기 개발용 진단 — 통상 테스트/빌드와 별도 실행")
    commands = cli.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="합성 시험 자료 생성: bootstrap 100개 / conditions 200원문×12조건")
    generate.add_argument("--profile", choices=("bootstrap", "conditions"), default="bootstrap")
    generate.add_argument("--seed", type=int, default=20261010)
    validate = commands.add_parser("validate", help="이미지·정답·분할 검증 (OCR 미실행)")
    validate.add_argument("--corpus", required=True)
    review = commands.add_parser("review", help="PNG 등록·원본 확대·정답 검토 창 (OCR 미실행)")
    review.add_argument("--corpus", help="이어서 검토할 자료 폴더; 생략하면 새 자료 등록")
    commands.add_parser('capture-kit', help='실제 CLI 캡처용 새 문구 30개·수집 안내 생성 (캡처/OCR 없음)')
    show = commands.add_parser('show-capture', help='수집 문구를 현재 터미널에 표시 (명령 예문 실행 없음)')
    show.add_argument('--kit', required=True)
    show.add_argument('--case-id', help='한 문구만 표시; 생략하면 Enter로 다음 문구')
    intake = commands.add_parser('import-captures', help='수집 PNG를 미검토 정답 초안과 등록 (OCR 없음)')
    intake.add_argument('--kit', required=True)
    intake.add_argument('--images', help='명시적으로 등록할 PNG 폴더; 기본은 수집 묶음의 captures')
    run = commands.add_parser("run", help="선택한 자료를 실제 제품 엔진으로 인식")
    run.add_argument("--corpus", required=True)
    run.add_argument("--suite", choices=("bootstrap", "standard"), default="bootstrap")
    run.add_argument("--split", choices=("dev", "holdout"), default="dev")
    run.add_argument("--candidate", choices=CANDIDATES, default="baseline")
    run.add_argument('--recognizer', choices=RECOGNIZERS, help='로컬 인식 모델 비교 (명시할 때만 공통 입력 관측)')
    run.add_argument('--input-profile', choices=INPUT_PROFILES, default='native', help='검출 영역을 고정한 입력 조건')
    run.add_argument("--threads", type=int)
    run.add_argument("--diagnose-regions", action="store_true", help="baseline과 정답 좌표 직접 인식 2조건을 비교 (별도 추가 인식)")
    run.add_argument("--diagnose-ctc", action="store_true", help="baseline 모델 출력·문자 반복 제거·beam8을 관측 (제품 결과 유지)")
    run.add_argument("--case-id", action="append", help="선택한 suite/split 안의 사례 ID (여러 번 지정 가능)")
    run.add_argument("--timeout", type=float, default=120, help="모델 로드/각 사례 시간 제한(초)")
    compare = commands.add_parser("compare", help="같은 입력/정답을 사용한 두 실행 비교")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--intersection", action="store_true", help="공통 사례만 비교하고 빠진 사례 수 표시")
    disagreement = commands.add_parser('disagreement', help='저장된 native/ink-light 판독의 경고 위치 분석 (추론 없음)')
    disagreement.add_argument('--baseline', required=True)
    disagreement.add_argument('--candidate', required=True)
    disagreement.add_argument('--benchmark', help='연결할 별도 성능 진단 실행 ID')
    timing = commands.add_parser('benchmark-disagreement', help='명시적 이중 판독 반복 성능 측정 (별도 worker)')
    timing.add_argument('--baseline', required=True)
    timing.add_argument('--candidate', required=True)
    timing.add_argument('--repeats', type=int, default=5)
    timing.add_argument('--threads', type=int, default=4)
    rules = commands.add_parser('warning-rules', help='고정 불일치 경고 조건 비교 (명시적 문자 점수 재관측)')
    rules.add_argument('--analysis', required=True)
    rules.add_argument('--threads', type=int, default=4)
    return cli


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == '_warning-features':
        if len(argv) != 2:
            return 2
        from .warning_rule_run import worker
        return worker(argv[1])
    if argv and argv[0] == '_disagreement-benchmark':
        if len(argv) != 2:
            return 2
        from .disagreement_benchmark import worker
        return worker(argv[1])
    if argv and argv[0] == "_worker":
        if len(argv) != 2:
            return 2
        from .runner import worker
        return worker(argv[1])
    args = parser().parse_args(argv)
    try:
        if args.command == "generate":
            from .generate import generate
            print(generate(args.seed, args.profile), flush=True)
        elif args.command == "validate":
            from .corpus import load_corpus
            corpus = load_corpus(args.corpus)
            from collections import Counter
            print(f"자료 검증 통과: {len(corpus.cases)}개 / {dict(Counter(case['split'] for case in corpus.cases))}")
        elif args.command == "run":
            from .runner import run
            _, code = run(args.corpus, args.suite, args.split, args.candidate, args.threads, args.timeout,
                          diagnose_regions=args.diagnose_regions, diagnose_ctc=args.diagnose_ctc, case_ids=args.case_id,
                          recognizer=args.recognizer,input_profile=args.input_profile)
            return code
        elif args.command == "review":
            from .review_ui import launch
            return launch(args.corpus)
        elif args.command == 'capture-kit':
            from .capture_kit import prepare
            print(prepare(), flush=True)
        elif args.command == 'show-capture':
            from .capture_kit import show
            show(args.kit, args.case_id)
        elif args.command == 'import-captures':
            from .capture_kit import import_captures
            print(import_captures(args.kit, args.images), flush=True)
        elif args.command == "compare":
            from .compare import compare
            print(compare(args.baseline, args.candidate, args.intersection), flush=True)
        elif args.command == 'disagreement':
            from .disagreement_report import analyze
            print(analyze(args.baseline, args.candidate, args.benchmark), flush=True)
        elif args.command == 'benchmark-disagreement':
            from .disagreement_benchmark import benchmark
            directory, code = benchmark(args.baseline, args.candidate, args.repeats, args.threads)
            print(directory, flush=True)
            return code
        elif args.command == 'warning-rules':
            from .warning_rule_run import run
            directory, code = run(args.analysis, args.threads)
            print(directory, flush=True)
            return code
    except (OSError, ValueError, ImportError) as error:
        print(f"진단 오류: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
