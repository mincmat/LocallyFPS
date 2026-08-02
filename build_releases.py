#!/usr/bin/env python3
"""
build_releases.py - Builds self-contained per-OS release zips for LocallyFPS.

Each zip contains everything a user needs for their OS:
wrapper + core/ + platform/ + languages/ + launcher + default config.
Deps (ffmpeg, rife, models) are downloaded at first run, as before.

Usage:
    python3 build_releases.py            # build all three zips into dist/
    python3 build_releases.py linux      # build only the Linux zip
"""

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

PLATFORMS = {
    "linux": {
        "src": ROOT / "LocallyFPS_Linux",
        "launcher": "start.sh",
    },
    "macos": {
        "src": ROOT / "LocallyFPS_macOS",
        "launcher": "start.command",
    },
    "windows": {
        "src": ROOT / "LocallyFPS_Windows",
        "launcher": "start.bat",
    },
}

# Files/folders never included in a release zip
EXCLUDED = {
    "__pycache__",
    "cache",
    "deps",
    "models",
    "runtime",
    "videos",
    ".gitkeep",
    "config.json",
}

# Top-level shared dirs to bundle into every zip (stored under a per-OS top folder)
SHARED_DIRS = ["core", "platform"]


def _excluded(name: str) -> bool:
    return any(name == ex or name.endswith(f"/{ex}") for ex in EXCLUDED)


def _add_dir(zf: zipfile.ZipFile, src: Path, arc_prefix: str) -> int:
    count = 0
    for p in sorted(src.rglob("*")):
        if _excluded(p.name):
            continue
        if p.is_dir():
            continue
        rel = p.relative_to(src)
        zf.write(p, f"{arc_prefix}/{rel}")
        count += 1
    return count


def build_one(os_name: str) -> Path:
    info = PLATFORMS[os_name]
    src = info["src"]
    top = f"LocallyFPS_{os_name.capitalize()}" if os_name != "macos" else "LocallyFPS_macOS"

    DIST.mkdir(exist_ok=True)
    out = DIST / f"{top}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        total = 0

        # 1. The wrapper and launcher
        wrapper = src / "fps_enhancer.py"
        zf.write(wrapper, f"{top}/fps_enhancer.py")
        total += 1
        launcher = src / info["launcher"]
        if launcher.exists():
            zf.write(launcher, f"{top}/{info['launcher']}")
            total += 1

        # 2. Shared core/ and platform/
        for shared in SHARED_DIRS:
            total += _add_dir(zf, ROOT / shared, f"{top}/{shared}")

        # 3. languages/ (canonical copy lives in core/languages)
        lang_dir = ROOT / "core" / "languages"
        if lang_dir.exists():
            for p in sorted(lang_dir.glob("*.json")):
                zf.write(p, f"{top}/languages/{p.name}")
                total += 1

        # 4. Default config (without user-specific settings.json)
        cfg = src / "config.json"
        if cfg.exists():
            zf.write(cfg, f"{top}/config.json")
            total += 1

        print(f"  {out.name}: {total} files")
    return out


def main() -> None:
    targets = sys.argv[1:] or list(PLATFORMS)
    print(f"Building releases into {DIST}")
    for t in targets:
        if t not in PLATFORMS:
            print(f"Unknown platform: {t}")
            sys.exit(1)
        build_one(t)
    print("Done.")


if __name__ == "__main__":
    main()
