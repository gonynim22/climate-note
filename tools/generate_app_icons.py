r"""원본 SVG를 앱/트레이 ICO로 변환한다(개발용, 일반 빌드에서는 실행하지 않음).

PowerShell: .\.venv\Scripts\python.exe tools/generate_app_icons.py
Edge의 SVG clipPath 렌더를 사용하고 Pillow로 premultiplied alpha 축소한다.
중간 렌더·브라우저 프로필·입출력 해시는 실행별 output/harness/ 아래에 남긴다.
"""

import argparse
import base64
from datetime import datetime
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import struct
import subprocess

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
EXE_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
TRAY_SIZES = EXE_SIZES[:7]


def write_ico(path: Path, frames: dict[int, Image.Image], sizes: tuple[int, ...]):
    """ICO 머리말을 명시해 20/24/40/48px도 PNG 항목으로 포함한다."""
    payloads = []
    entries = []
    offset = 6 + 16 * len(sizes)
    for size in sizes:
        with BytesIO() as stream:
            frames[size].save(stream, format="PNG")
            payload = stream.getvalue()
        entries.append(struct.pack(
            "<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(payload), offset
        ))
        payloads.append(payload)
        offset += len(payload)
    with open(path, "wb") as stream:
        stream.write(struct.pack("<HHH", 0, 1, len(sizes)))
        stream.write(b"".join(entries + payloads))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge", type=Path, help="별도 Microsoft Edge 실행 파일 경로")
    args = parser.parse_args()
    candidates = [Path(os.environ.get(key, "")) / "Microsoft/Edge/Application/msedge.exe"
                  for key in ("PROGRAMFILES(X86)", "PROGRAMFILES")]
    edge = args.edge or next((path for path in candidates if path.is_file()), None)
    if edge is None or not edge.is_file():
        parser.error("Microsoft Edge가 필요합니다. --edge로 실행 파일을 지정하세요.")

    source = ROOT / "icon/climate_note_style16_continents_final.svg"
    with open(source, "rb") as stream:
        svg = stream.read()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f-app-icons")
    run_dir = ROOT / "output/harness" / run_id
    run_dir.mkdir(parents=True)
    html = run_dir / "render.html"
    encoded = base64.b64encode(svg).decode("ascii")
    with open(html, "w", encoding="utf-8") as stream:
        stream.write(
            '<!doctype html><meta charset="utf-8">'
            '<style>html,body{margin:0;background:transparent;overflow:hidden}'
            'img{display:block;width:1024px;height:1024px}</style>'
            f'<img src="data:image/svg+xml;base64,{encoded}">'
        )
    rendered = run_dir / "source-1024.png"
    with open(run_dir / "edge.log", "wb") as log:
        subprocess.run([
            str(edge), "--headless=new", "--disable-gpu", "--no-first-run",
            "--no-default-browser-check", "--disable-background-networking",
            "--disable-extensions", "--hide-scrollbars", "--force-device-scale-factor=1",
            "--default-background-color=00000000", "--window-size=1024,1024",
            "--virtual-time-budget=1000", f"--user-data-dir={run_dir / 'edge-profile'}",
            f"--screenshot={rendered}", html.as_uri(),
        ], check=True, timeout=60, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW)

    with Image.open(rendered) as image:
        rgba = image.convert("RGBA")
    if rgba.size != (1024, 1024) or rgba.getchannel("A").getextrema() != (0, 255):
        raise ValueError("1024px 투명 SVG 렌더를 확인할 수 없습니다.")
    premultiplied = rgba.convert("RGBa")
    frames = {size: premultiplied.resize((size, size), Image.Resampling.LANCZOS)
              .convert("RGBA") for size in EXE_SIZES}
    icon_dir = ROOT / "icon"
    outputs = {"icon_fixed_256.ico": EXE_SIZES, "icon_fixed_32.ico": TRAY_SIZES}
    outputs.update({f"icon_fixed_{size}.ico": (size,) for size in (16, 64, 128)})
    for filename, sizes in outputs.items():
        write_ico(icon_dir / filename, frames, sizes)
    frames[256].save(icon_dir / "icon_fixed_256.png")

    result = {"run_id": run_id, "source": str(source.relative_to(ROOT)),
              "source_sha256": hashlib.sha256(svg).hexdigest(), "outputs": {}}
    for filename in (*outputs, "icon_fixed_256.png"):
        with open(icon_dir / filename, "rb") as stream:
            data = stream.read()
        result["outputs"][filename] = {
            "sizes": list(outputs.get(filename, (256,))), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    with open(run_dir / "result.json", "w", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    with open(run_dir / "summary.md", "w", encoding="utf-8") as stream:
        stream.write(f"# 앱 아이콘 변환\n\n- 실행 ID: `{run_id}`\n"
                     f"- 원본: `{result['source']}`\n"
                     f"- 원본 SHA-256: `{result['source_sha256']}`\n"
                     "- Edge 1024px 투명 렌더 → RGBa LANCZOS → PNG 항목 ICO\n\n")
        for filename, item in result["outputs"].items():
            stream.write(f"- `{filename}`: {item['sizes']}px, {item['bytes']} bytes, "
                         f"SHA-256 `{item['sha256']}`\n")
    print(f"아이콘 6개 생성 완료. 기록: {run_dir / 'summary.md'}")


if __name__ == "__main__":
    main()
