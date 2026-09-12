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
    m = re.fullmatch(
        r"(\d+)\.(\d+)(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?",
        tag,
    )
    if m:
        major, minor, patch, _prerelease = m.groups()
        return int(major), int(minor), int(patch or 0)
    return (0, 0, 0)


def version_key(tag):
    """Return a SemVer-compatible key, including prerelease ordering."""
    clean = tag.lstrip("v").strip()
    match = re.fullmatch(
        r"(\d+)\.(\d+)(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?",
        clean,
    )
    if not match:
        return None
    major, minor, patch, prerelease = match.groups()
    base = int(major), int(minor), int(patch or 0)
    if prerelease is None:
        return base + (1, ())
    identifiers = tuple(
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in prerelease.split(".")
    )
    return base + (0, identifiers)


def get_platform_name():
    if sys.platform.startswith("linux"):
        return "linux"
    elif sys.platform == "darwin":
        return "macos"
    elif sys.platform in ("win32", "cygwin"):
        return "windows"
    return None


def get_platform_base_name(platform_name=None):
    plat = platform_name or get_platform_name()
    return ASSET_MAP.get(plat) if plat else None


def pick_asset(assets, base_name):
    pattern = re.compile(
        r"^" + re.escape(base_name)
        + r"(_v\d+(?:\.\d+)*(?:-[0-9A-Za-z.-]+)?)?\.zip$",
        re.IGNORECASE,
    )
    matches = [a for a in assets if pattern.match(a.get("name", ""))]
    if not matches:
        return None

    def asset_version_key(asset):
        m = re.search(
            r"_v(\d+(?:\.\d+)*(?:-[0-9A-Za-z.-]+)?)\.zip$",
            asset.get("name", ""), re.IGNORECASE,
        )
        if m:
            return version_key(m.group(1)) or ()
        return ()

    return max(matches, key=asset_version_key)


def pick_platform_asset(assets, platform_name):
    """Prefer the user-facing v4 package, retaining compatibility with v3 ZIPs."""
    preferences = {
        "linux": (r"^LocallyFPS-v.+-x86_64\.AppImage$",),
        "windows": (
            r"^LocallyFPS-v.+-windows-x64-portable\.zip$",
        ),
        "macos": (r"^LocallyFPS-v.+-macos-arm64\.dmg$",),
    }.get(platform_name, ())
    for pattern in preferences:
        match = next(
            (asset for asset in assets if re.match(pattern, asset.get("name", ""), re.IGNORECASE)),
            None,
        )
        if match:
            return match
    base_name = ASSET_MAP.get(platform_name)
    return pick_asset(assets, base_name) if base_name else None


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
    return __import__("subprocess").Popen(
        ["bash", str(script_path)],
        cwd=str(script_path.parent),
        start_new_session=True,
        stdout=__import__("subprocess").DEVNULL,
        stderr=__import__("subprocess").DEVNULL,
        close_fds=True,
    )


def create_appimage_swap_script(appimage_path, downloaded_path, process_id):
    """Create a small detached helper that replaces an AppImage after exit.

    An AppImage cannot replace itself while it is running.  The downloaded file
    is deliberately kept next to the current AppImage, so the final move is
    atomic on normal local filesystems.  A previous verified version is kept as
    ``.previous`` for recovery instead of being deleted by the updater.
    """
    appimage = Path(appimage_path).resolve()
    downloaded = Path(downloaded_path).resolve()
    if appimage.suffix.lower() != ".appimage":
        raise ValueError("The current application is not an AppImage.")
    if not appimage.is_file() or not downloaded.is_file():
        raise ValueError("The AppImage update files are not available.")
    if appimage.parent != downloaded.parent:
        raise ValueError("The staged AppImage must be beside the current AppImage.")

    script_path = appimage.parent / f".{appimage.name}.update.sh"
    backup = appimage.with_name(appimage.name + ".previous")
    app_q = shlex.quote(str(appimage))
    download_q = shlex.quote(str(downloaded))
    backup_q = shlex.quote(str(backup))
    script_q = shlex.quote(str(script_path))
    content = (
        "#!/usr/bin/env bash\nset -eu\n"
        f"while kill -0 {int(process_id)} 2>/dev/null; do sleep 0.2; done\n"
        # Keep one known-good version.  The running AppImage is the recovery
        # point for this verified update, even if an older backup exists.
        f"rm -f -- {backup_q}\n"
        f"if ! mv -- {app_q} {backup_q}; then exit 1; fi\n"
        f"if ! mv -- {download_q} {app_q}; then\n"
        f"  mv -- {backup_q} {app_q}\n"
        "  exit 1\n"
        "fi\n"
        f"chmod +x -- {app_q}\n"
        f"nohup {app_q} >/dev/null 2>&1 &\n"
        f"rm -f -- {script_q}\n"
    )
    script_path.write_text(content, encoding="utf-8")
    os.chmod(script_path, 0o755)
    return script_path


def human_size(size_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
