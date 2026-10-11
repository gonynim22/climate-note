"""Convert a fixed Paddle export in a dedicated ABI-compatible environment."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

from .contracts import sha256


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--export-result", type=Path)
    args = parser.parse_args()
    import paddle2onnx
    import onnx

    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    graph, parameters = args.model_dir / "inference.json", args.model_dir / "inference.pdiparams"
    result = {"status": "running", "paddle": importlib.metadata.version("paddlepaddle"),
              "paddle2onnx": importlib.metadata.version("paddle2onnx"),
              "graph": {"path": str(graph.resolve()), "sha256": sha256(graph)},
              "parameters": {"path": str(parameters.resolve()), "sha256": sha256(parameters)},
              "opset_version": 14, "enable_onnx_checker": True, "optimize_tool": None,
              "producer_sha256": sha256(Path(__file__))}
    if args.export_result is not None:
        export = json.loads(args.export_result.read_text(encoding="utf-8"))
        if export["status"] not in {"exported_untrained", "exported_trained", "exported_initialized", "exported_diagnostic"}:
            raise ValueError("Export is incomplete")
        by_name = {item["file"]: item["sha256"] for item in export["export"]}
        if by_name.get(graph.name) != sha256(graph) or by_name.get(parameters.name) != sha256(parameters):
            raise ValueError("Export files changed")
        result["export_result"] = {"path": str(args.export_result.resolve()), "sha256": sha256(args.export_result)}
    paddle2onnx.export(model_filename=str(graph), params_filename=str(parameters),
                      save_file=str(args.output), opset_version=14, enable_onnx_checker=True,
                      optimize_tool=None)
    model = onnx.load(str(args.output))
    onnx.checker.check_model(model)
    result.update({"status": "converted", "output": {"path": str(args.output.resolve()),
                   "sha256": sha256(args.output), "size": args.output.stat().st_size}})
    args.output.with_suffix(".conversion.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
