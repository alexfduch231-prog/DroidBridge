"""Local probe: discover approved installed FFmpeg without embedding personal paths."""
from pathlib import Path
import shutil
import subprocess
import sys
root = Path(__file__).resolve().parents[1]
ffmpeg = shutil.which('ffmpeg')
if not ffmpeg:
    raise SystemExit('Provide installed FFmpeg on PATH or call build_windows.py --media-root explicitly')
subprocess.run([str(root / 'packaging/.venv-build/Scripts/python.exe'),
    str(root / 'packaging/build_windows.py'), '--output', str(root / 'packaging/.build/probe-01'),
    '--media-root', str(Path(ffmpeg).resolve().parents[1]),
    '--iscc', str(root / 'packaging/.build-tools/inno-7.1.1/ISCC.exe')], check=True)
