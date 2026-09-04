import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from . import paths
from .console import status, ask_yes_no
from .i18n import _
from .progress import DownloadProgress, DependencyBar
from .urls import RIFE_RELEASE_URLS, FFMPEG_RELEASE_URLS


def download_and_extract(url, dest_dir, description="Downloading", bar=None):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "archive.zip"
        if bar:
            def _hook(block_num, block_size, total_size):
                downloaded = min(block_num * block_size, total_size)
                pct = downloaded / total_size if total_size > 0 else 0
                bar.update(pct, downloaded=downloaded, total=total_size)
            try:
                urllib.request.urlretrieve(url, zip_path, reporthook=_hook)
            except KeyboardInterrupt:
                bar.fail(_("Download cancelled."))
                return False
            except Exception as exc:
                bar.fail(str(exc))
                return False
        else:
            dl = DownloadProgress(_("Downloading"))
            try:
                urllib.request.urlretrieve(url, zip_path, reporthook=dl)
            except KeyboardInterrupt:
                dl.close()
                print()
                status(_("Download cancelled."), "WARN")
                return False
            except Exception as exc:
                dl.close()
                status(f"{_('Download failed:')} {exc}", "ERROR")
                return False
            finally:
                dl.close()
        if bar:
            bar.update(1.0, label=_("Extracting..."))
        else:
            status(_("Extracting..."))
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dest_dir)
    return True


def _setup_system_paths():
    """Check system PATH for ffmpeg/ffprobe/rife and set paths if found. No prompts, no downloads."""
    if not paths.FFMPEG_BIN.is_file() or not paths.FFPROBE_BIN.is_file():
        sys_ffmpeg = shutil.which(f"ffmpeg{paths.BIN_EXT}") or shutil.which("ffmpeg")
        sys_ffprobe = shutil.which(f"ffprobe{paths.BIN_EXT}") or shutil.which("ffprobe")
        if sys_ffmpeg and sys_ffprobe:
            paths.FFMPEG_BIN = Path(sys_ffmpeg)
            paths.FFPROBE_BIN = Path(sys_ffprobe)
    if not paths.RIFE_BIN.is_file():
        sys_rife = shutil.which(f"rife-ncnn-vulkan{paths.BIN_EXT}") or shutil.which("rife-ncnn-vulkan")
        if sys_rife:
            paths.RIFE_BIN = Path(sys_rife)


def ensure_ffmpeg(auto_yes=False, bar=None):
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
    if bar:
        bar.update(0, label=_("ffmpeg/ffprobe not found, downloading..."))
    else:
        status(_("ffmpeg/ffprobe not found locally or on system."), "WARN")
    url = FFMPEG_RELEASE_URLS().get(paths.OS_NAME)
    if url and (auto_yes or ask_yes_no(_("Download ffmpeg now?"), default=True)):
        if download_and_extract(url, paths._FFMPEG_DIR, "ffmpeg", bar=bar):
            return True
        if not auto_yes:
            status(_("Could not download ffmpeg."), "ERROR")
            status(
                _("ffmpeg must be placed manually in:") + f"\n  {paths._FFMPEG_DIR}\n"
                + _("Download from: https://johnvansickle.com/ffmpeg/"),
                "ERROR"
            )
            import sys
            sys.exit(1)
        return False
    if not auto_yes:
        status(
            _("ffmpeg must be placed manually in:") + f"\n  {paths._FFMPEG_DIR}\n"
            + _("Download from: https://johnvansickle.com/ffmpeg/"),
            "ERROR"
        )
        import sys
        sys.exit(1)
    return False


def _maybe_chmod(path):
    try:
        path.chmod(0o755)
    except PermissionError:
        pass


def ensure_rife(auto_yes=False, bar=None):
    rife_bin = paths.RIFE_BIN
    if rife_bin.is_file():
        _maybe_chmod(rife_bin)
        return True
    sys_rife = shutil.which(f"rife-ncnn-vulkan{paths.BIN_EXT}") or shutil.which("rife-ncnn-vulkan")
    if sys_rife:
        paths.RIFE_BIN = Path(sys_rife)
        _maybe_chmod(Path(sys_rife))
        return True
    if bar:
        bar.update(0, label=_("rife-ncnn-vulkan not found, downloading..."))
    else:
        status(_("rife-ncnn-vulkan not found locally or on system."), "WARN")
    url = RIFE_RELEASE_URLS().get(paths.OS_NAME)
    if url and (auto_yes or ask_yes_no(_("Download rife-ncnn-vulkan now? (~400 MB)"), default=True)):
        ok = download_and_extract(url, paths._RIFE_DIR, "rife-ncnn-vulkan", bar=bar)
        if not ok:
            if not auto_yes:
                status(_("Could not download rife-ncnn-vulkan."), "ERROR")
                import sys
                sys.exit(1)
            return False
        if rife_bin.is_file():
            _maybe_chmod(rife_bin)
            return True
        for f in paths._RIFE_DIR.rglob(f"rife-ncnn-vulkan{paths.BIN_EXT}"):
            _maybe_chmod(f)
            shutil.move(str(f), str(rife_bin))
            break
        if rife_bin.is_file():
            _maybe_chmod(rife_bin)
            return True
    if not auto_yes:
        status(
            _("rife-ncnn-vulkan must be placed manually in:") + f"\n  {rife_bin}\n"
            + _("Download from: https://github.com/nihui/rife-ncnn-vulkan/releases"),
            "ERROR"
        )
        import sys
        sys.exit(1)
    return False
