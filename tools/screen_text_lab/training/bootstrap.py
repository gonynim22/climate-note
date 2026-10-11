"""Acquire an isolated official CPython runtime and pinned PaddleOCR source."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

REVISION = "dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf"


def download(url: str, destination: Path) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)
    with urllib.request.urlopen(url, timeout=120) as response:
        with destination.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
    with destination.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"url": url, "path": str(destination), "size": destination.stat().st_size,
            "sha256": digest}


def extract(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    if root.exists():
        raise FileExistsError(root)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            if not (root / member.filename).resolve().is_relative_to(root):
                raise ValueError("Archive member escapes destination")
        bundle.extractall(root)


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    allowed = Path("output/screen_text_lab/training").resolve()
    if not root.is_relative_to(allowed):
        raise ValueError("Bootstrap must stay under output/screen_text_lab/training")
    root.mkdir(parents=True, exist_ok=True)
    assets = []
    python_url = "https://api.nuget.org/v3-flatcontainer/python/3.12.10/python.3.12.10.nupkg"
    package = root / "downloads/python.3.12.10.nupkg"
    assets.append(download(python_url, package))
    # The NuGet package carries a repository signature; the response hash is also
    # retained when the feed offers it. The downloaded bytes are always pinned.
    extract(package, root / "cpython312")
    source = root / "downloads/paddleocr.zip"
    assets.append(download(f"https://codeload.github.com/PaddlePaddle/PaddleOCR/zip/{REVISION}", source))
    extract(source, root / "source")
    (root / "bootstrap.json").write_text(json.dumps({"revision": REVISION, "assets": assets}, indent=2), encoding="utf-8")
    print(json.dumps({"python": str(root / "cpython312/tools/python.exe"), "assets": assets}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
