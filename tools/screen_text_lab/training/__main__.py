"""Manual development commands; never called by the application or harness."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_parser.add_argument("--product", type=Path, default=Path("screen_text/models/rec.onnx"))
    prepare_parser.add_argument("--dictionary", type=Path, default=Path("screen_text/models/dict.txt"))
    prepare_parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/malgun.ttf"))
    steps_parser = sub.add_parser("measure-steps")
    steps_parser.add_argument("--requested", type=Path, required=True)
    steps_parser.add_argument("--product", type=Path, default=Path("screen_text/models/rec.onnx"))
    steps_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        from .prepare import prepare
        prepare(args.output, args.product, args.dictionary, args.font)
    elif args.command == "measure-steps":
        from .prepare import measure_steps
        measure_steps(args.requested, args.product, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
