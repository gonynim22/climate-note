"""python -m tools.screen_text_lab.datasets generate — 수동 개발 전용."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="OCR 합성 학습 자료 pilot 생성/검증")
    sub = parser.add_subparsers(dest="command", required=True)
    generate_parser = sub.add_parser("generate", help="새 train400/selection100 synthetic crop 버전 생성; final 제외")
    generate_parser.add_argument("--source-plan", type=Path, help="직접 작성한 train/selection 원문 JSON; 렌더 전 누출 감사")
    generate_parser.add_argument("--steps-map", type=Path, help="실제 모델의 observed_width_steps와 model_sha256 JSON")
    validate = sub.add_parser("validate", help="명시한 자료의 이미지/좌표/원문 검사")
    validate.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "generate":
        from .build import generate
        root = Path(__file__).resolve().parents[3]
        plan = None
        if args.source_plan is not None:
            with open(args.source_plan, encoding="utf-8") as stream:
                plan = json.load(stream)
        step_values, step_provenance = None, None
        if args.steps_map is not None:
            from .audit import sha256
            with open(args.steps_map, encoding="utf-8") as stream:
                measured = json.load(stream)
            if measured.get("height") != 48 or not measured.get("model_sha256"):
                raise ValueError("CTC 실측 모델 해시와 높이48이 필요합니다")
            step_values = measured["observed_width_steps"]
            if not all(str(width).isdigit() and type(steps) is int and steps > 0 for width, steps in step_values.items()):
                raise ValueError("CTC 실측 폭/단계 값이 잘못되었습니다")
            step_provenance = {"path": str(args.steps_map.resolve()), "sha256": sha256(args.steps_map),
                               "model_sha256": measured["model_sha256"]}
        # datasets 패키지는 프로젝트/tools/screen_text_lab/datasets에 있다.
        directory, result = generate(root / "output/screen_text_lab/training_data", root / "screen_text/models/dict.txt",
                                     run_root=root / "output/harness", source_plan=plan,
                                     steps_map=step_values, steps_provenance=step_provenance)
        print(directory)
        print(result["status"])
        return 1 if result["status"].startswith("failed") else 0
    from .audit import validate_manifest
    manifest = validate_manifest(args.directory)
    print(f"validated {manifest['dataset_id']}: {len(manifest['cases'])} images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
