#!/usr/bin/env python3
"""LocallyFPS self-updater — standalone, works on all versions.

Download the latest release from GitHub and replace the current installation.
Usage: python3 update.py
"""

import json
import os
import platform
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen, urlretrieve

REPO = "mincmat/LocallyFPS"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"

ASSET_MAP = {
    "linux": "LocallyFPS_Linux.zip",
    "macos": "LocallyFPS_macOS.zip",
    "windows": "LocallyFPS_Windows.zip",
}


def _platform():
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform in ("win32", "cygwin"):
        return "windows"
    sys.exit("Unsupported platform: " + sys.platform)


def _print(msg, end="\n"):
    sys.stdout.write(msg + end)
    sys.stdout.flush()


def check_latest():
    """Return {"tag_name": str, "download_url": str, "size": int} or None."""
    plat = _platform()
    asset_name = ASSET_MAP.get(plat, "")

    req = Request(API_URL)
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

    for asset in data.get("assets", []):
        if asset.get("name") == asset_name:
            return {
                "tag_name": tag,
                "download_url": asset["browser_download_url"],
                "size": asset["size"],
            }

    _print(f"Error: no asset matching '{asset_name}' in release {tag}")
    return None


def _human_size(size_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def update(info):
    """Download, extract, prepare swap, and self-destruct to swap."""
    plat = _platform()
    base = Path(__file__).resolve().parent
    url = info["download_url"]
    tag = info["tag_name"]
    size = _human_size(info["size"])
    temp_dir = Path(tempfile.mkdtemp(prefix="lfps_update_"))
    zip_path = temp_dir / "update.zip"

    _print(f"Downloading {tag} ({size})...")
    sys.stdout.write("  [")
    sys.stdout.flush()
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
    script = _create_swap_script(plat, base, extract_dir)
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
        subp = _launch_swap(script, base, extract_dir)
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


def _create_swap_script(plat, old_dir, new_dir):
    if plat == "windows":
        script = old_dir / "_lfps_swap.bat"
        bat = (
            f"@echo off\r\n"
            f"ping -n 2 127.0.0.1 >nul\r\n"
            f"rmdir /s /q \"{old_dir}.old\" 2>nul\r\n"
            f"move \"{old_dir}\" \"{old_dir}.old\"\r\n"
            f"move \"{new_dir}\" \"{old_dir}\"\r\n"
            f'start "" "cmd" /k echo Update complete! You can now run start.bat.\r\n'
            f"del \"%~f0\"\r\n"
        )
        with open(script, "w", newline="\r\n") as f:
            f.write(bat)
        return script

    script = old_dir / "_lfps_swap.sh"
    sh = (
        "#!/usr/bin/env bash\n"
        "sleep 1\n"
        f'rm -rf "{old_dir}.old"\n'
        f'mv "{old_dir}" "{old_dir}.old"\n'
        f'mv "{new_dir}" "{old_dir}"\n'
        'echo "Update complete! You can now run start.sh or start.command."\n'
        f'rm -f "{script}"\n'
    )
    with open(script, "w") as f:
        f.write(sh)
    os.chmod(script, 0o755)
    return script


def _launch_swap(script, old_dir, new_dir):
    import subprocess

    if sys.platform in ("win32", "cygwin"):
        return subprocess.Popen(
            ["cmd", "/c", str(script)],
            cwd=str(old_dir.parent),
            creationflags=0x00000008 if hasattr(subprocess, 'DETACHED_PROCESS') else 0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    else:
        return subprocess.Popen(
            ["bash", str(script)],
            cwd=str(old_dir.parent),
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )


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
