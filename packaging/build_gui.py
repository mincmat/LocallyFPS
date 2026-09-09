#!/usr/bin/env python3
"""Build the frozen graphical application with its verified offline runtime."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _data_arg(source, destination):
    return f"{source}{os.pathsep}{destination}"


def _render_icon(destination):
    from PySide6.QtCore import QRectF, QSize
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    image = QImage(QSize(1024, 1024), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer = QSvgRenderer(str(ROOT / "packaging" / "locallyfps.svg"))
    if not renderer.isValid():
        raise RuntimeError("Could not render the application icon")
    renderer.render(painter, QRectF(0, 0, 1024, 1024))
    painter.end()
    if not image.save(str(destination), "PNG"):
        raise RuntimeError("Could not save the application icon")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--work-dir", type=Path, default=ROOT / "build" / "pyinstaller")
    parser.add_argument("--spec-dir", type=Path, default=ROOT / "build" / "spec")
    args = parser.parse_args()
    runtime = args.runtime_dir.resolve()
    dist_dir = args.dist_dir.resolve()
    work_dir = args.work_dir.resolve()
    spec_dir = args.spec_dir.resolve()
    required = (
        runtime / "deps" / "ffmpeg",
        runtime / "deps" / "rife",
        runtime / "models" / "rife-v4.6",
    )
    if not all(item.exists() for item in required):
        raise SystemExit(f"Runtime is incomplete: {runtime}")
    dist_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    spec_dir.mkdir(parents=True, exist_ok=True)
    icon = work_dir / "locallyfps.png"
    _render_icon(icon)
    from PIL import Image
    with Image.open(icon) as source_icon:
        source_icon.save(
            work_dir / "locallyfps.ico", format="ICO",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    for target in (dist_dir / "LocallyFPS", dist_dir / "LocallyFPS.app"):
        if target.exists():
            shutil.rmtree(target)
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", "LocallyFPS", "--icon", str(icon),
        "--add-data", _data_arg(ROOT / "languages", "languages"),
        "--add-data", _data_arg(ROOT / "packaging" / "locallyfps.svg", "packaging"),
        "--add-data", _data_arg(ROOT / "packaging" / "settings.svg", "packaging"),
        "--add-data", _data_arg(ROOT / "THIRD_PARTY_NOTICES.md", "."),
        "--add-data", _data_arg(runtime / "deps", "deps"),
        "--add-data", _data_arg(runtime / "models", "models"),
        "--add-data", _data_arg(runtime / "runtime.json", "."),
        "--hidden-import", "platforms.linux",
        "--hidden-import", "platforms.windows",
        "--hidden-import", "platforms.macos",
        "--distpath", str(dist_dir), "--workpath", str(work_dir),
        "--specpath", str(spec_dir), str(ROOT / "locallyfps_gui.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
