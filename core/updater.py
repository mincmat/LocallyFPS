import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from . import paths
from .colors import Color
from .console import status, ask_yes_no
from .i18n import _

GITHUB_API = "https://api.github.com/repos/mincmat/LocallyFPS/releases"
CURRENT_VERSION = paths.APP_VERSION


def _parse_version(tag):
    tag = tag.lstrip("v").strip()
    try:
        return tuple(int(x) for x in tag.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _get_platform_asset_name():
    if sys.platform.startswith("linux"):
        return "LocallyFPS_Linux.zip"
    elif sys.platform == "darwin":
        return "LocallyFPS_macOS.zip"
    elif sys.platform == "win32":
        return "LocallyFPS_Windows.zip"
    return None


def check_for_updates():
    try:
        req = urllib.request.Request(
            f"{GITHUB_API}/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "LocallyFPS-Updater"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    latest_tag = data.get("tag_name", "")
    if not latest_tag:
        return None

    current = _parse_version(CURRENT_VERSION)
    latest = _parse_version(latest_tag)
    if latest <= current:
        return None

    asset_name = _get_platform_asset_name()
    if not asset_name:
        return None

    assets = data.get("assets", [])
    download_url = None
    for asset in assets:
        if asset.get("name") == asset_name:
            download_url = asset.get("browser_download_url")
            break

    if not download_url:
        return None

    return (latest_tag, download_url)


def _download_with_progress(url, dest, progress_cb=None):
    def report(block_num, block_size, total_size):
        if progress_cb and total_size > 0:
            progress_cb(min(1.0, block_num * block_size / total_size))

    try:
        urllib.request.urlretrieve(url, dest, report)
        return dest
    except Exception:
        if os.path.exists(dest):
            os.unlink(dest)
        raise


def _prepare_update(zip_path):
    current_dir = paths.BASE_DIR
    parent = current_dir.parent
    zip_file = zipfile.ZipFile(zip_path)
    zip_name = [n for n in zip_file.namelist() if "/" in n and not n.startswith("__MACOSX")]
    if zip_name:
        zip_top = zip_name[0].split("/")[0]
    else:
        zip_top = None

    update_dir = parent / f"{current_dir.name}_update"
    if update_dir.exists():
        shutil.rmtree(update_dir)
    update_dir.mkdir(parents=True)

    zip_file.extractall(update_dir)
    zip_file.close()

    if zip_top and zip_top != ".":
        inner = update_dir / zip_top
        if inner.is_dir():
            for item in inner.iterdir():
                shutil.move(str(item), str(update_dir / item.name))
            inner.rmdir()

    videos_dir = current_dir / "videos"
    if videos_dir.is_dir():
        dst_videos = update_dir / "videos"
        if dst_videos.exists():
            shutil.rmtree(dst_videos)
        shutil.copytree(str(videos_dir), str(dst_videos))

    config_src = current_dir / "config.json"
    if config_src.exists():
        shutil.copy2(str(config_src), str(update_dir / "config.json"))

    config_dir = current_dir / "config"
    if config_dir.is_dir():
        dst_config = update_dir / "config"
        if not dst_config.exists():
            shutil.copytree(str(config_dir), str(dst_config), dirs_exist_ok=True)

    deps_dir = current_dir / "deps"
    if deps_dir.is_dir():
        dst_deps = update_dir / "deps"
        if not dst_deps.exists():
            shutil.copytree(str(deps_dir), str(dst_deps), dirs_exist_ok=True)

    models_dir = current_dir / "models"
    if models_dir.is_dir():
        dst_models = update_dir / "models"
        if not dst_models.exists():
            shutil.copytree(str(models_dir), str(dst_models), dirs_exist_ok=True)

    return update_dir


def _create_swap_script(current_dir, update_dir, parent_dir):
    old_name = current_dir.name
    new_name = update_dir.name

    if sys.platform == "win32":
        script_content = (
            f'@echo off\r\n'
            f'timeout /t 2 /nobreak >nul\r\n'
            f'rmdir /s /q "{old_name}.old" 2>nul\r\n'
            f'move /Y "{old_name}" "{old_name}.old"\r\n'
            f'move /Y "{new_name}" "{old_name}"\r\n'
            f'rmdir /s /q "{old_name}.old" 2>nul\r\n'
            f'\r\n'
            f'echo ==========================================\r\n'
            f'echo  LocallyFPS updated successfully!\r\n'
            f'echo  Run start.bat to launch the new version.\r\n'
            f'echo ==========================================\r\n'
            f'pause\r\n'
        )
        script_path = parent_dir / "_update_locallyfps.bat"
        script_path.write_text(script_content, encoding="ascii")
    else:
        script_content = (
            "#!/bin/bash\n"
            f'cd "{parent_dir}"\n'
            f'sleep 2\n'
            f'rm -rf "{old_name}.old" 2>/dev/null\n'
            f'mv "{old_name}" "{old_name}.old"\n'
            f'mv "{new_name}" "{old_name}"\n'
            f'rm -rf "{old_name}.old" 2>/dev/null\n'
            f'echo\n'
            f'echo "=========================================="\n'
            f'echo " LocallyFPS updated successfully!"\n'
            f'echo " Run start.sh to launch the new version."\n'
            f'echo "=========================================="\n'
        )
        script_path = parent_dir / "_update_locallyfps.sh"
        script_path.write_text(script_content)
        script_path.chmod(0o755)

    return script_path


def run_updater():
    result = check_for_updates()
    if result is None:
        print(f"\n  {Color.ok(_('You are running the latest version.'))}")
        print(f"  {Color.dim('v' + CURRENT_VERSION)}\n")
        input(f"  {Color.dim(_('Press Enter to continue...'))}")
        return

    version, url = result

    print()
    print(f"  {Color.accent_bold(f'{_('Version')} {version} {_('is available!')}')}")
    print(f"  {Color.dim(f'{_('Current version:')} v{CURRENT_VERSION}')}")
    print(f"  {Color.dim(f'{_('This will download the latest version and migrate your videos.')}')}")
    print()

    if not ask_yes_no(_("Download and install the update?"), default=True):
        return

    from .progress import Spinner
    import re

    tmp = Path(tempfile.gettempdir()) / f"locallyfps_update_{os.getpid()}.zip"

    sp = Spinner(_("Downloading update..."))
    try:
        _download_with_progress(url, str(tmp))
    except Exception as e:
        sp.ok(_("Download failed"), show_time=False)
        print(f"  {Color.warn(str(e))}")
        if tmp.exists():
            tmp.unlink()
        input(f"\n  {Color.dim(_('Press Enter to continue...'))}")
        return
    sp.ok(_("Download complete"), show_time=False)

    sp = Spinner(_("Installing update..."))
    try:
        update_dir = _prepare_update(tmp)
        sp.ok(_("Installation complete"), show_time=False)
    except Exception as e:
        sp.ok(_("Installation failed"), show_time=False)
        print(f"  {Color.warn(str(e))}")
        if tmp.exists():
            tmp.unlink()
        input(f"\n  {Color.dim(_('Press Enter to continue...'))}")
        return
    finally:
        if tmp.exists():
            tmp.unlink()

    current_dir = paths.BASE_DIR
    parent_dir = current_dir.parent
    script_path = _create_swap_script(current_dir, update_dir, parent_dir)

    restart_msg = _("Applying update and restarting...")
    print()
    print(f"  {Color.ok_bold(_('Update ready!'))}")
    print(f"  {Color.dim(restart_msg)}")

    sys.stdout.flush()
    if sys.platform == "win32":
        subprocess.Popen(
            ["cmd", "/c", "start", str(script_path)],
            cwd=str(parent_dir),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        subprocess.Popen(
            [str(script_path)],
            cwd=str(parent_dir),
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    sys.exit(0)
