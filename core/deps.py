import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from . import paths
from .console import status, ask_yes_no
from .i18n import _
from .progress import DownloadProgress
from .urls import RIFE_RELEASE_URLS, FFMPEG_RELEASE_URLS


def download_and_extract(url, dest_dir, description="Downloading"):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "archive.zip"
        status(f"{_('Downloading')} {description}...")
        dl = DownloadProgress(_("Downloading"))
        try:
            urllib.request.urlretrieve(url, zip_path, reporthook=dl)
        except Exception as exc:
            status(f"{_('Download failed:')} {exc}", "ERROR")
            return False
        finally:
            dl.close()
        status(_("Extracting..."))
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dest_dir)
    return True


def ensure_ffmpeg(auto_yes=False):
    ffmpeg_bin = paths.FFMPEG_BIN
    ffprobe_bin = paths.FFPROBE_BIN
    if ffmpeg_bin.is_file() and ffprobe_bin.is_file():
        return True
    sys_ffmpeg = shutil.which(f"ffmpeg{paths.BIN_EXT}") or shutil.which("ffmpeg")
    sys_ffprobe = shutil.which(f"ffprobe{paths.BIN_EXT}") or shutil.which("ffprobe")
    if sys_ffmpeg and sys_ffprobe:
        paths.FFMPEG_BIN = Path(sys_ffmpeg)
        paths.FFPROBE_BIN = Path(sys_ffprobe)
        return True
    status(_("ffmpeg/ffprobe not found locally or on system."), "WARN")
    url = FFMPEG_RELEASE_URLS.get(paths.OS_NAME)
    if url and (auto_yes or ask_yes_no(_("Download ffmpeg now?"), default=True)):
        return download_and_extract(url, paths._FFMPEG_DIR, "ffmpeg")
    status(
        _("ffmpeg must be placed manually in:") + f"\n  {paths._FFMPEG_DIR}\n"
        + _("Download from: https://johnvansickle.com/ffmpeg/"),
        "ERROR"
    )
    import sys
    sys.exit(1)


def ensure_rife(auto_yes=False):
    rife_bin = paths.RIFE_BIN
    if rife_bin.is_file():
        rife_bin.chmod(0o755)
        return True
    sys_rife = shutil.which(f"rife-ncnn-vulkan{paths.BIN_EXT}") or shutil.which("rife-ncnn-vulkan")
    if sys_rife:
        paths.RIFE_BIN = Path(sys_rife)
        return True
    status(_("rife-ncnn-vulkan not found locally or on system."), "WARN")
    url = RIFE_RELEASE_URLS.get(paths.OS_NAME)
    if url and (auto_yes or ask_yes_no(_("Download rife-ncnn-vulkan now? (~400 MB)"), default=True)):
        ok = download_and_extract(url, paths._RIFE_DIR, "rife-ncnn-vulkan")
        if not ok:
            status(_("Could not download rife-ncnn-vulkan."), "ERROR")
            import sys
            sys.exit(1)
        if rife_bin.is_file():
            rife_bin.chmod(0o755)
            return True
        for f in paths._RIFE_DIR.rglob(f"rife-ncnn-vulkan{paths.BIN_EXT}"):
            f.chmod(0o755)
            shutil.move(str(f), str(rife_bin))
            break
        if rife_bin.is_file():
            rife_bin.chmod(0o755)
            return True
    status(
        _("rife-ncnn-vulkan must be placed manually in:") + f"\n  {rife_bin}\n"
        + _("Download from: https://github.com/nihui/rife-ncnn-vulkan/releases"),
        "ERROR"
    )
    import sys
    sys.exit(1)
