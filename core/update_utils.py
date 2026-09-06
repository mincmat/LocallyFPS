"""Shared utilities for self-updater (used by core/updater.py and update.py)."""

import os
import re
import shlex
import sys
from pathlib import Path

GITHUB_API = "https://api.github.com/repos/mincmat/LocallyFPS/releases"
ASSET_MAP = {
    "linux": "LocallyFPS_Linux",
    "macos": "LocallyFPS_macOS",
    "windows": "LocallyFPS_Windows",
}


def parse_version(tag):
    tag = tag.lstrip("v").strip()
    m = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", tag)
    if m:
        major, minor, patch = m.groups()
        return int(major), int(minor), int(patch or 0)
    return (0, 0, 0)


def get_platform_name():
    if sys.platform.startswith("linux"):
        return "linux"
    elif sys.platform == "darwin":
        return "macos"
    elif sys.platform in ("win32", "cygwin"):
        return "windows"
    return None


def get_platform_base_name():
    plat = get_platform_name()
    return ASSET_MAP.get(plat) if plat else None


def pick_asset(assets, base_name):
    pattern = re.compile(
        r"^" + re.escape(base_name) + r"(_v\d+(?:\.\d+)*)?\.zip$", re.IGNORECASE
    )
    matches = [a for a in assets if pattern.match(a.get("name", ""))]
    if not matches:
        return None

    def version_key(asset):
        m = re.search(r"_v(\d+(?:\.\d+)*)\.zip$", asset.get("name", ""), re.IGNORECASE)
        if m:
            try:
                return tuple(int(x) for x in m.group(1).split("."))
            except ValueError:
                pass
        return ()

    return max(matches, key=version_key)


def create_swap_script(old_dir, new_dir):
    parent_dir = old_dir.parent
    old_name = old_dir.name
    new_name = new_dir.name

    if sys.platform == "win32":
        script_path = parent_dir / "_lfps_swap.bat"
        content = (
            f"@echo off\r\n"
            f"ping -n 2 127.0.0.1 >nul\r\n"
            f'rmdir /s /q "{old_name}.old" 2>nul\r\n'
            f'move /Y "{old_name}" "{old_name}.old"\r\n'
            f'if errorlevel 1 exit /b 1\r\n'
            f'move /Y "{new_name}" "{old_name}"\r\n'
            f'if errorlevel 1 (\r\n'
            f'  move /Y "{old_name}.old" "{old_name}"\r\n'
            f'  exit /b 1\r\n'
            f')\r\n'
            f'start "" "cmd" /k echo Update complete! Run start.bat.\r\n'
            f'del "%~f0"\r\n'
        )
        script_path.write_text(content, encoding="ascii")
    else:
        script_path = parent_dir / "_lfps_swap.sh"
        old_q = shlex.quote(old_name)
        new_q = shlex.quote(new_name)
        backup_q = shlex.quote(old_name + ".old")
        script_q = shlex.quote(str(script_path))
        launcher = "start.command" if sys.platform == "darwin" else "start.sh"
        content = (
            "#!/usr/bin/env bash\nset -u\n"
            "sleep 1\n"
            f'if [ -e {backup_q} ]; then rm -rf -- {backup_q}; fi\n'
            f'if ! mv -- {old_q} {backup_q}; then exit 1; fi\n'
            f'if ! mv -- {new_q} {old_q}; then\n'
            f'  mv -- {backup_q} {old_q}\n'
            f'  exit 1\n'
            f'fi\n'
            f'echo "Update complete! Run {launcher}."\n'
            f'rm -f -- {script_q}\n'
        )
        script_path.write_text(content)
        os.chmod(script_path, 0o755)

    return script_path


def launch_swap(script_path):
    if sys.platform in ("win32", "cygwin"):
        return __import__("subprocess").Popen(
            ["cmd", "/c", str(script_path)],
            cwd=str(script_path.parent),
            creationflags=0x00000008 if hasattr(__import__("subprocess"), "DETACHED_PROCESS") else 0,
            stdout=__import__("subprocess").DEVNULL,
            stderr=__import__("subprocess").DEVNULL,
            close_fds=True,
        )
    else:
        return __import__("subprocess").Popen(
            ["bash", str(script_path)],
            cwd=str(script_path.parent),
            start_new_session=True,
            stdout=__import__("subprocess").DEVNULL,
            stderr=__import__("subprocess").DEVNULL,
            close_fds=True,
        )


def human_size(size_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
