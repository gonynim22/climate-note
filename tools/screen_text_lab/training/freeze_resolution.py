"""Turn a pip dry-run report into exact wheel URLs with verified hashes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def freeze(report: Path, output: Path) -> None:
    data = json.loads(report.read_text(encoding="utf-8"))
    lines = ["# Isolated OCR training environment. Generated from pip resolution; not the product lock."]
    for item in sorted(data["install"], key=lambda entry: entry["metadata"]["name"].lower()):
        download = item["download_info"]
        digest = download["archive_info"]["hashes"]["sha256"]
        url = download["url"]
        if not url.startswith("https://") or ".whl" not in url:
            raise ValueError("Only exact HTTPS wheel URLs are allowed")
        lines.append(f"{item['metadata']['name']} @ {url} --hash=sha256:{digest}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Pinned {len(lines) - 1} wheels: {output}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    freeze(args.report, args.output)


if __name__ == "__main__":
    main()
