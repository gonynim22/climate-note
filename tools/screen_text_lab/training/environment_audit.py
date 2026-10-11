"""Check an isolated environment against exact wheel URL/hash installation locks."""

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse

from packaging.utils import canonicalize_name, parse_wheel_filename

from .contracts import sha256


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--locks", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expected = {}
    for path in args.locks:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            package, rest = line.split(" @ ", 1)
            url, digest = rest.split(" --hash=sha256:", 1)
            wheel_name, version, _, _ = parse_wheel_filename(unquote(Path(urlparse(url).path).name))
            if canonicalize_name(package) != wheel_name:
                raise ValueError("Wheel URL package differs from lock name")
            expected[canonicalize_name(package)] = {"version": str(version), "url": url, "sha256": digest}
    installed = {}
    issues = []
    for distribution in importlib.metadata.distributions():
        name = canonicalize_name(distribution.metadata["Name"])
        direct = distribution.read_text("direct_url.json")
        record = {"version": distribution.version, "direct_url": json.loads(direct) if direct else None}
        installed[name] = record
        if name == "pip":  # CPython ensurepip bootstrap; separately recorded version.
            continue
        wanted = expected.get(name)
        if wanted is None:
            issues.append(f"Unlisted installed package: {name}")
        elif record["version"] != wanted["version"] or not record["direct_url"]:
            issues.append(f"Version/provenance mismatch: {name}")
        elif (record["direct_url"].get("url") != wanted["url"] or
              record["direct_url"].get("archive_info", {}).get("hashes", {}).get("sha256") != wanted["sha256"]):
            issues.append(f"Wheel URL/hash mismatch: {name}")
    issues.extend(f"Missing locked package: {name}" for name in expected if name not in installed)
    result = {"status": "passed" if not issues else "failed", "python": sys.version,
              "executable": sys.executable, "locks": {str(path.resolve()): sha256(path) for path in args.locks},
              "expected_packages": len(expected), "installed": installed, "issues": issues}
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "expected_packages", "issues")}), flush=True)
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
