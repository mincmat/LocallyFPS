import json
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
import os
from pathlib import Path

from . import paths
from .colors import Color
from .console import status, ask_yes_no
from .i18n import _
from .update_utils import (
    GITHUB_API, get_platform_name, pick_platform_asset,
    create_swap_script, create_appimage_swap_script,
    launch_swap, human_size, version_key,
)
from .deps import safe_extract_zip

CURRENT_VERSION = paths.APP_VERSION


class UpdateCheckError(RuntimeError):
    """Raised when update availability could not be determined reliably."""


def _latest_release():
    try:
        req = urllib.request.Request(
            f"{GITHUB_API}/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "LocallyFPS-Updater"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise UpdateCheckError(
            _("Could not connect to GitHub to check for updates.")
        ) from exc


def _checksum_asset(assets):
    return next((a for a in assets if a.get("name") == "SHA256SUMS.txt"), None)


def _appimage_asset(assets):
    """Find the Linux AppImage published for the release, if any."""
    matches = [
        asset for asset in assets
        if asset.get("name", "").lower().endswith(".appimage")
        and "locallyfps" in asset.get("name", "").lower()
    ]
    return matches[0] if len(matches) == 1 else None


def _current_appimage():
    candidate = os.environ.get("APPIMAGE")
    if not candidate:
        return None
    path = Path(candidate).expanduser().resolve()
    return path if path.suffix.lower() == ".appimage" and path.is_file() else None


def check_for_updates_detailed():
    """Return a verified-installation update description for the current app.

    The check itself does not download or modify anything.  An AppImage is only
    selected when LocallyFPS is actually running from an AppImage; otherwise
    the established portable archive is reported as a manual download.
    """
    data = _latest_release()
    latest_tag = data.get("tag_name", "")
    if not latest_tag:
        raise UpdateCheckError(_("GitHub returned a release without a version tag."))
    current, latest = version_key(CURRENT_VERSION), version_key(latest_tag)
    if current is None or latest is None:
        raise UpdateCheckError(_("The latest release has an unsupported version format."))
    if latest <= current:
        return None

    assets = data.get("assets", [])
    checksum = _checksum_asset(assets)
    platform_name = get_platform_name()
    appimage = _current_appimage() if platform_name == "linux" else None
    asset = _appimage_asset(assets) if appimage else None
    installable = bool(asset and checksum and appimage)
    if asset is None:
        asset = pick_platform_asset(assets, platform_name)
    if not asset:
        raise UpdateCheckError(_("The latest release has no download for this platform."))

    return {
        "version": latest_tag,
        "asset_name": asset.get("name", ""),
        "download_url": asset.get("browser_download_url", ""),
        "checksum_url": checksum.get("browser_download_url", "") if checksum else "",
        "size": int(asset.get("size") or 0),
        "kind": "appimage" if asset.get("name", "").lower().endswith(".appimage") else "archive",
        "installable": installable,
        "manual_url": data.get("html_url", "https://github.com/mincmat/LocallyFPS/releases/latest"),
    }


def check_for_updates():
    data = _latest_release()

    latest_tag = data.get("tag_name", "")
    if not latest_tag:
        raise UpdateCheckError(_("GitHub returned a release without a version tag."))

    current = version_key(CURRENT_VERSION)
    latest = version_key(latest_tag)
    if current is None or latest is None:
        raise UpdateCheckError(
            _("The latest release has an unsupported version format.")
        )
    if latest <= current:
        return None

    platform_name = get_platform_name()
    if not platform_name:
        raise UpdateCheckError(_("Updates are not available for this platform."))

    asset = pick_platform_asset(data.get("assets", []), platform_name)
    if not asset:
        raise UpdateCheckError(
            _("The latest release has no download for this platform.")
        )

    checksum_asset = next(
        (a for a in data.get("assets", []) if a.get("name") == "SHA256SUMS.txt"), None
    )
    return (
        latest_tag, asset.get("browser_download_url"), asset.get("name"),
        checksum_asset.get("browser_download_url") if checksum_asset else None,
    )


def _verified_download(url, destination, asset_name, checksum_url, progress_cb=None):
    """Download an update and insist on the release SHA-256 before staging it."""
    if not url or not checksum_url:
        raise UpdateCheckError("The release is missing a required SHA-256 checksum.")
    try:
        _download_with_progress(url, str(destination), progress_cb)
        req = urllib.request.Request(checksum_url, headers={"User-Agent": "LocallyFPS-Updater"})
        with urllib.request.urlopen(req, timeout=15) as response:
            sums = response.read().decode("utf-8").splitlines()
        expected = next(
            line.split()[0] for line in sums
            if len(line.split()) >= 2 and line.split()[-1].lstrip("*") == asset_name
        )
        digest = hashlib.sha256(Path(destination).read_bytes()).hexdigest()
        if digest.lower() != expected.lower():
            raise UpdateCheckError("The update checksum did not match the GitHub release.")
        return Path(destination)
    except Exception:
        Path(destination).unlink(missing_ok=True)
        raise


def stage_appimage_update(update, progress_cb=None):
    """Download and verify an AppImage beside the running AppImage.

    This only stages the update.  The caller launches the generated helper and
    exits after the user has explicitly approved the installation.
    """
    current = _current_appimage()
    if not current or not update.get("installable") or update.get("kind") != "appimage":
        raise UpdateCheckError("This installation cannot update itself safely.")
    if not os.access(current.parent, os.W_OK):
        raise UpdateCheckError("LocallyFPS cannot write beside this AppImage.")
    staged = current.with_name(f".{current.name}.download")
    _verified_download(
        update["download_url"], staged, update["asset_name"], update["checksum_url"], progress_cb,
    )
    try:
        return create_appimage_swap_script(current, staged, os.getpid())
    except Exception:
        staged.unlink(missing_ok=True)
        raise


def _download_with_progress(url, dest, progress_cb=None):
    def report(block_num, block_size, total_size):
        if progress_cb and total_size > 0:
            progress_cb(min(1.0, block_num * block_size / total_size))

    try:
        urllib.request.urlretrieve(url, dest, report)
        return dest
    except Exception:
        if __import__("os").path.exists(dest):
            __import__("os").unlink(dest)
        raise


def _verify_release_checksum(zip_path, asset_name, checksum_url):
    if not checksum_url:
        status(_("Release has no checksum file; update cancelled."), "ERROR")
        return False
    try:
        req = urllib.request.Request(checksum_url, headers={"User-Agent": "LocallyFPS-Updater"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            lines = resp.read().decode("utf-8").splitlines()
        expected = next(
            line.split()[0] for line in lines
            if len(line.split()) >= 2 and line.split()[-1].lstrip("*") == asset_name
        )
    except Exception:
        status(_("Could not verify the update checksum."), "ERROR")
        return False
    digest = hashlib.sha256(Path(zip_path).read_bytes()).hexdigest()
    if digest.lower() != expected.lower():
        status(_("Update checksum mismatch; update cancelled."), "ERROR")
        return False
    return True


def _prepare_update(zip_path):
    current_dir = paths.BASE_DIR
    parent = current_dir.parent
    zip_file = zipfile.ZipFile(zip_path)
    zip_name = [n for n in zip_file.namelist() if "/" in n and not n.startswith("__MACOSX")]
    zip_top = zip_name[0].split("/")[0] if zip_name else None

    update_dir = parent / f"{current_dir.name}_update"
    if update_dir.exists():
        shutil.rmtree(update_dir)
    update_dir.mkdir(parents=True)

    safe_extract_zip(zip_file, update_dir)
    zip_file.close()

    if zip_top and zip_top != ".":
        inner = update_dir / zip_top
        if inner.is_dir():
            for item in inner.iterdir():
                shutil.move(str(item), str(update_dir / item.name))
            inner.rmdir()

    for launcher in ("start.sh", "start.command"):
        launcher_path = update_dir / launcher
        if launcher_path.is_file():
            launcher_path.chmod(launcher_path.stat().st_mode | 0o111)

    for item in ("videos", "config.json", "config", "deps", "models"):
        src = current_dir / item
        dst = update_dir / item
        if src.exists():
            if dst.exists():
                if dst.is_dir():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
            try:
                if src.is_dir():
                    shutil.copytree(str(src), str(dst))
                else:
                    shutil.copy2(str(src), str(dst))
            except Exception as exc:
                raise RuntimeError(
                    f"{_('Could not migrate user data:')} {src.name}: {exc}"
                ) from exc

    return update_dir


def run_updater():
    if paths.IS_FROZEN and paths.LAYOUT_MODE in {"installed", "custom"}:
        status(
            _("Automatic updates are not enabled for installed beta builds yet."),
            "WARN",
        )
        status(_("Download the next beta from GitHub Releases."), "INFO")
        if sys.stdin.isatty():
            input(f"\n  {Color.dim(_('Press Enter to continue...'))}")
        return
    try:
        result = check_for_updates()
    except UpdateCheckError as exc:
        status(str(exc), "ERROR")
        input(f"\n  {Color.dim(_('Press Enter to continue...'))}")
        return
    if result is None:
        term = shutil.get_terminal_size()
        msg_ok = Color.ok(_('You are running the latest version.'))
        msg_ver = Color.dim('v' + CURRENT_VERSION)
        msg_enter = Color.dim(_('Press Enter to continue...'))
        clean_ok = re.sub(r'\033\[[0-9;]*m', '', msg_ok)
        clean_ver = re.sub(r'\033\[[0-9;]*m', '', msg_ver)
        clean_enter = re.sub(r'\033\[[0-9;]*m', '', msg_enter)
        pad_ok = max(0, (term.columns - len(clean_ok)) // 2)
        pad_ver = max(0, (term.columns - len(clean_ver)) // 2)
        pad_enter = max(0, (term.columns - len(clean_enter)) // 2)
        print(f"\n\n\n")
        print(f"{' ' * pad_ok}{msg_ok}")
        print(f"{' ' * pad_ver}{msg_ver}\n")
        input(f"{' ' * pad_enter}{msg_enter}")
        return

    version, url, asset_name, checksum_url = result

    available_msg = f"{_('Version')} {version} {_('is available!')}"
    current_msg = f"{_('Current version:')} v{CURRENT_VERSION}"
    migration_msg = _("This will download the latest version and migrate your videos.")
    print()
    print(f"  {Color.accent_bold(available_msg)}")
    print(f"  {Color.dim(current_msg)}")
    print(f"  {Color.dim(migration_msg)}")
    print()

    if not ask_yes_no(_("Download and install the update?"), default=True):
        return

    from .progress import Spinner

    tmp = Path(tempfile.gettempdir()) / f"locallyfps_update_{__import__('os').getpid()}.zip"

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

    if not _verify_release_checksum(tmp, asset_name, checksum_url):
        tmp.unlink(missing_ok=True)
        input(f"\n  {Color.dim(_('Press Enter to continue...'))}")
        return

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

    script_path = create_swap_script(paths.BASE_DIR, update_dir)

    restart_msg = _("Applying update and restarting...")
    print()
    print(f"  {Color.ok_bold(_('Update ready!'))}")
    print(f"  {Color.dim(restart_msg)}")

    sys.stdout.flush()
    launch_swap(script_path)
    sys.exit(0)
