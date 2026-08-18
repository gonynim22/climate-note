"""Build the standalone ClimateNote Settings diagnostic executable."""
from pathlib import Path
import subprocess
import sys


def build() -> Path:
    root = Path(__file__).resolve().parents[1]
    script = root / "diagnostics" / "font_database_probe.py"
    target = root / "dist" / "기후노트_설정진단.exe"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--noupx",
        "--name",
        target.stem,
        "--icon",
        str(root / "icon" / "icon_fixed_256.ico"),
        "--distpath",
        str(root / "dist"),
        "--workpath",
        str(root / "build" / "font_probe"),
        "--specpath",
        str(root / "build" / "font_probe"),
        str(script),
    ]
    subprocess.check_call(command, cwd=root)
    if not target.is_file():
        raise FileNotFoundError(f"진단 EXE가 생성되지 않았습니다: {target}")
    return target


if __name__ == "__main__":
    print(build())
