#!/usr/bin/env python3
"""LocallyFPS self-updater — standalone, works on all versions.

Download the latest release from GitHub and replace the current installation.
Usage: python3 update.py
"""

import json
import hashlib
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
from core.deps import safe_extract_zip

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

    checksum_asset = next(
        (a for a in data.get("assets", []) if a.get("name") == "SHA256SUMS.txt"), None
    )
    return {
        "tag_name": tag,
        "download_url": asset["browser_download_url"],
        "asset_name": asset["name"],
        "checksum_url": checksum_asset["browser_download_url"] if checksum_asset else None,
        "size": asset["size"],
    }


def _verify_checksum(zip_path, asset_name, checksum_url):
    if not checksum_url:
        _print("Error: release has no SHA256SUMS.txt; refusing unverified update")
        return False
    try:
        req = Request(checksum_url, headers={"User-Agent": "LocallyFPS-Updater"})
        with urlopen(req, timeout=15) as resp:
            lines = resp.read().decode("utf-8").splitlines()
        expected = next(
            line.split()[0] for line in lines
            if len(line.split()) >= 2 and line.split()[-1].lstrip("*") == asset_name
        )
    except Exception as exc:
        _print(f"Error verifying checksum: {exc}")
        return False
    actual = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if actual.lower() != expected.lower():
        _print("Error: update checksum mismatch")
        return False
    return True


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

    if not _verify_checksum(zip_path, info["asset_name"], info["checksum_url"]):
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False

    _print(f"Extracting {tag}...")
    extract_dir = base.parent / f".{base.name}_update"

    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            safe_extract_zip(zf, extract_dir)
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

    for launcher in ("start.sh", "start.command"):
        launcher_path = extract_dir / launcher
        if launcher_path.is_file():
            launcher_path.chmod(launcher_path.stat().st_mode | 0o111)

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
            except Exception as exc:
                _print(f"Error migrating user data '{src.name}': {exc}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                shutil.rmtree(extract_dir, ignore_errors=True)
                return False

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
