#!/usr/bin/env python3
"""LocallyFPS self-updater — standalone, works on all versions.

Download the latest release from GitHub and replace the current installation.
Usage: python3 update.py
"""

import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen, urlretrieve

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.update_utils import (
    GITHUB_API, ASSET_MAP, parse_version, get_platform_name,
    pick_asset, create_swap_script, launch_swap, human_size,
)

REPO = "mincmat/LocallyFPS"


def _print(msg, end="\n"):
    sys.stdout.write(msg + end)
    sys.stdout.flush()


def check_latest():
    plat = get_platform_name()
    base_name = ASSET_MAP.get(plat, "")

    req = Request(f"{GITHUB_API}/latest")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "LocallyFPS-Updater")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")

    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except URLError as e:
        _print(f"Error: cannot reach GitHub ({e})")
        return None
    except json.JSONDecodeError:
        _print("Error: invalid response from GitHub API")
        return None

    tag = data.get("tag_name", "")
    if not tag:
        _print("Error: no release tag found")
        return None

    asset = pick_asset(data.get("assets", []), base_name)
    if not asset:
        _print(f"Error: no asset matching '{base_name}(_vX.Y.Z)?.zip' in release {tag}")
        return None

    return {
        "tag_name": tag,
        "download_url": asset["browser_download_url"],
        "size": asset["size"],
    }


def update(info):
    base = Path(__file__).resolve().parent
    url = info["download_url"]
    tag = info["tag_name"]
    size = human_size(info["size"])
    temp_dir = Path(tempfile.mkdtemp(prefix="lfps_update_"))
    zip_path = temp_dir / "update.zip"

    _print(f"Downloading {tag} ({size})...")
    last_pct = [-1]

    def _hook(blocks, block_size, total):
        if total <= 0:
            return
        pct = min(99, int(blocks * block_size * 100 / total))
        if pct > last_pct[0]:
            ticks = pct // 5
            bar = "#" * ticks + "-" * (20 - ticks)
            sys.stdout.write(f"\r  [{bar}] {pct}%")
            sys.stdout.flush()
            last_pct[0] = pct

    try:
        urlretrieve(url, zip_path, _hook)
        sys.stdout.write("\r  [####################] 100%\n")
        sys.stdout.flush()
    except Exception as e:
        _print(f"\nError downloading: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False

    _print(f"Extracting {tag}...")
    extract_dir = base.parent / f".{base.name}_update"

    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
    except Exception as e:
        _print(f"Error extracting: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        shutil.rmtree(extract_dir, ignore_errors=True)
        return False

    macosx = extract_dir / "__MACOSX"
    if macosx.exists():
        shutil.rmtree(macosx, ignore_errors=True)
    try:
        entries = list(extract_dir.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            inner = entries[0]
            for item in inner.iterdir():
                shutil.move(str(item), str(extract_dir / item.name))
            inner.rmdir()
    except Exception as e:
        _print(f"Error preparing extracted files: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        shutil.rmtree(extract_dir, ignore_errors=True)
        return False

    _print("Migrating your data...")
    for item in ("videos", "config.json", "config", "deps", "models"):
        src = base / item
        dst = extract_dir / item
        if src.exists():
            if dst.exists():
                if dst.is_dir():
                    shutil.rmtree(dst, ignore_errors=True)
                else:
                    dst.unlink()
            try:
                if src.is_dir():
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            except Exception:
                pass

    _print("Preparing swap...")
    script = create_swap_script(base, extract_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)

    _print(f"  Ready to update to {tag}.")
    _print(f"  Old dir: {base}")
    _print(f"  New dir: {extract_dir}")
    try:
        answer = input("  Continue? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        _print("\nCancelled.")
        shutil.rmtree(extract_dir, ignore_errors=True)
        return False

    if answer and answer not in ("y", "yes"):
        _print("Cancelled.")
        shutil.rmtree(extract_dir, ignore_errors=True)
        return False

    try:
        subp = launch_swap(script)
        if subp:
            sys.exit(0)
    except Exception as e:
        _print(f"Error launching swap: {e}")
        shutil.rmtree(extract_dir, ignore_errors=True)
        return False

    _print("Could not auto-restart. Do it manually:")
    _print(f"  1. mv {base} {base}.old")
    _print(f"  2. mv {extract_dir} {base}")
    _print(f"  3. Delete {base}.old when ready")
    return True


def main():
    _print("LocallyFPS Updater")
    _print("-" * 30)

    info = check_latest()
    if info is None:
        sys.exit(1)

    _print(f"Latest release: {info['tag_name']}")
    update(info)


if __name__ == "__main__":
    main()
