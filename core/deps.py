import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from . import paths
from .console import status, ask_yes_no
from .i18n import _
from .progress import DownloadProgress, DependencyBar
from .urls import RIFE_RELEASE_URLS, FFMPEG_RELEASE_URLS

RETRY_COUNT = 3
RETRY_DELAY = 2


def _safe_archive_path(dest_dir, member_name):
    dest_dir = Path(dest_dir).resolve()
    target = (dest_dir / member_name).resolve()
    try:
        return os.path.commonpath((str(dest_dir), str(target))) == str(dest_dir)
    except ValueError:
        return False


def safe_extract_zip(zf, dest_dir):
    """Extract a ZIP after rejecting traversal and symbolic-link entries."""
    for info in zf.infolist():
        mode = info.external_attr >> 16
        if not _safe_archive_path(dest_dir, info.filename) or stat.S_ISLNK(mode):
            raise ValueError(f"Unsafe path in ZIP archive: {info.filename}")
    zf.extractall(dest_dir)


def safe_extract_tar(tf, dest_dir):
    """Extract a tar archive after rejecting links, devices and traversal."""
    for member in tf.getmembers():
        if (not _safe_archive_path(dest_dir, member.name) or member.issym()
                or member.islnk() or member.isdev()):
            raise ValueError(f"Unsafe path in tar archive: {member.name}")
    tf.extractall(dest_dir)


def sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_binary(path, expected_sha256):
    if not path.is_file():
        return False
    return sha256_file(path) == expected_sha256


def download_and_extract(url, dest_dir, description="Downloading", bar=None):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    last_err = None
    for attempt in range(RETRY_COUNT):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "archive"
            try:
                if bar:
                    def _hook(block_num, block_size, total_size):
                        downloaded = min(block_num * block_size, total_size)
                        pct = downloaded / total_size if total_size > 0 else 0
                        bar.update(pct, downloaded=downloaded, total=total_size)
                    urllib.request.urlretrieve(url, archive_path, reporthook=_hook)
                else:
                    dl = DownloadProgress(description)
                    try:
                        urllib.request.urlretrieve(url, archive_path, reporthook=dl)
                    finally:
                        dl.close()
            except KeyboardInterrupt:
                if bar:
                    bar.fail(_("Download cancelled."))
                else:
                    status(_("Download cancelled."), "WARN")
                return False
            except Exception as exc:
                last_err = exc
                if attempt < RETRY_COUNT - 1:
                    time.sleep(RETRY_DELAY * (2 ** attempt))
                    continue
                if bar:
                    bar.fail(str(exc))
                else:
                    status(f"{_('Download failed:')} {exc}", "ERROR")
                return False

            if bar:
                bar.update(1.0, label=_("Extracting..."))
            else:
                status(_("Extracting..."))
            url_lower = url.lower()
            try:
                if url_lower.endswith(".zip"):
                    with zipfile.ZipFile(archive_path) as zf:
                        safe_extract_zip(zf, dest_dir)
                elif url_lower.endswith(".tar.xz") or url_lower.endswith(".txz"):
                    with tarfile.open(archive_path, "r:xz") as tf:
                        safe_extract_tar(tf, dest_dir)
                elif url_lower.endswith(".tar.gz") or url_lower.endswith(".tgz"):
                    with tarfile.open(archive_path, "r:gz") as tf:
                        safe_extract_tar(tf, dest_dir)
                else:
                    with zipfile.ZipFile(archive_path) as zf:
                        safe_extract_zip(zf, dest_dir)
            except Exception as exc:
                last_err = exc
                if attempt < RETRY_COUNT - 1:
                    time.sleep(RETRY_DELAY * (2 ** attempt))
                    continue
                status(f"{_('Extraction failed:')} {exc}", "ERROR")
                return False
            return True
    return False


def _maybe_chmod(path):
    try:
        path.chmod(0o755)
    except PermissionError:
        pass


def _find_system_ffmpeg_pair():
    """Prefer Homebrew's feature-complete, keg-only FFmpeg on macOS."""
    candidates = []
    if paths.OS_NAME == "macos":
        brew = shutil.which("brew")
        if brew:
            try:
                result = subprocess.run(
                    [brew, "--prefix", "ffmpeg-full"], capture_output=True,
                    text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    candidates.append(Path(result.stdout.strip()) / "bin")
            except (OSError, subprocess.SubprocessError):
                pass
        candidates.extend((
            Path("/opt/homebrew/opt/ffmpeg-full/bin"),
            Path("/usr/local/opt/ffmpeg-full/bin"),
        ))
    for directory in candidates:
        ffmpeg = directory / f"ffmpeg{paths.BIN_EXT}"
        ffprobe = directory / f"ffprobe{paths.BIN_EXT}"
        if ffmpeg.is_file() and ffprobe.is_file():
            return str(ffmpeg), str(ffprobe)
    return (
        shutil.which(f"ffmpeg{paths.BIN_EXT}") or shutil.which("ffmpeg"),
        shutil.which(f"ffprobe{paths.BIN_EXT}") or shutil.which("ffprobe"),
    )


def _setup_system_paths():
    """Check system PATH for ffmpeg/ffprobe/rife and set paths if found."""
    if not paths.FFMPEG_BIN.is_file() or not paths.FFPROBE_BIN.is_file():
        sys_ffmpeg, sys_ffprobe = _find_system_ffmpeg_pair()
        if sys_ffmpeg and sys_ffprobe:
            paths.FFMPEG_BIN = Path(sys_ffmpeg)
            paths.FFPROBE_BIN = Path(sys_ffprobe)
    if not paths.RIFE_BIN.is_file():
        sys_rife = shutil.which(f"rife-ncnn-vulkan{paths.BIN_EXT}") or shutil.which("rife-ncnn-vulkan")
        if sys_rife:
            paths.RIFE_BIN = Path(sys_rife)


def _relocate_ffmpeg_binaries(base_dir):
    base_dir = Path(base_dir)
    for name in ("ffmpeg", "ffprobe"):
        target = base_dir / f"{name}{paths.BIN_EXT}"
        if target.is_file():
            _maybe_chmod(target)
            continue
        for f in base_dir.rglob(f"{name}{paths.BIN_EXT}"):
            shutil.move(str(f), str(target))
            _maybe_chmod(target)
            break


def _install_macos_ffmpeg_full(bar=None):
    brew = shutil.which("brew")
    if not brew:
        return False
    if bar:
        bar.update(0, label=_("Installing ffmpeg-full with Homebrew..."))
    else:
        status(_("Installing ffmpeg-full with Homebrew..."), "INFO")
    try:
        result = subprocess.run([brew, "install", "ffmpeg-full"], timeout=3600)
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    ffmpeg, ffprobe = _find_system_ffmpeg_pair()
    if not ffmpeg or not ffprobe:
        return False
    paths.FFMPEG_BIN = Path(ffmpeg)
    paths.FFPROBE_BIN = Path(ffprobe)
    return True


def ensure_ffmpeg(auto_yes=False, bar=None):
    from . import manifest

    ffmpeg_bin = paths.FFMPEG_BIN
    ffprobe_bin = paths.FFPROBE_BIN

    if ffmpeg_bin.is_file() and ffprobe_bin.is_file():
        integrity_failed = False
        for name, binary in (("ffmpeg", ffmpeg_bin), ("ffprobe", ffprobe_bin)):
            if manifest.is_installed(name):
                if not manifest.verify(name, binary):
                    status(f"{name} {_('failed its SHA-256 integrity check.')}", "ERROR")
                    manifest.quarantine(binary)
                    integrity_failed = True
            else:
                status(f"{name} {_('found but not in manifest, recording its SHA-256 hash.')}", "INFO")
                manifest.record(name, "local", binary)
        if not integrity_failed:
            return True

    sys_ffmpeg, sys_ffprobe = _find_system_ffmpeg_pair()
    if sys_ffmpeg and sys_ffprobe:
        paths.FFMPEG_BIN = Path(sys_ffmpeg)
        paths.FFPROBE_BIN = Path(sys_ffprobe)
        manifest.record("ffmpeg", "system", paths.FFMPEG_BIN)
        manifest.record("ffprobe", "system", paths.FFPROBE_BIN)
        return True

    if bar:
        bar.update(0, label=_("ffmpeg/ffprobe not found, downloading..."))
    else:
        status(_("ffmpeg/ffprobe not found locally or on system."), "WARN")

    url = FFMPEG_RELEASE_URLS().get(paths.OS_NAME)
    if not url:
        if paths.OS_NAME == "macos" and _install_macos_ffmpeg_full(bar=bar):
            manifest.record("ffmpeg", "homebrew-ffmpeg-full", paths.FFMPEG_BIN)
            manifest.record("ffprobe", "homebrew-ffmpeg-full", paths.FFPROBE_BIN)
            return True
        _show_manual_install_hint("ffmpeg")
        return False

    if not auto_yes and not ask_yes_no(_("Download ffmpeg now?"), default=True):
        _show_manual_install_hint("ffmpeg")
        return False

    if download_and_extract(url, paths._FFMPEG_DIR, "ffmpeg", bar=bar):
        _relocate_ffmpeg_binaries(paths._FFMPEG_DIR)
        if paths.FFMPEG_BIN.is_file():
            manifest.record("ffmpeg", "downloaded", paths.FFMPEG_BIN)
        if paths.FFPROBE_BIN.is_file():
            manifest.record("ffprobe", "downloaded", paths.FFPROBE_BIN)
        return paths.FFMPEG_BIN.is_file() and paths.FFPROBE_BIN.is_file()

    if not auto_yes:
        status(_("Could not download ffmpeg."), "ERROR")
        _show_manual_install_hint("ffmpeg")
    return False


def ensure_rife(auto_yes=False, bar=None):
    from . import manifest

    rife_bin = paths.RIFE_BIN
    if rife_bin.is_file():
        if manifest.is_installed("rife"):
            if manifest.verify("rife", rife_bin):
                return True
            status(_("RIFE failed its SHA-256 integrity check; disabling it."), "ERROR")
            manifest.quarantine(rife_bin)
        else:
            _maybe_chmod(rife_bin)
            manifest.record("rife", "local", rife_bin)
            return True

    sys_rife = shutil.which(f"rife-ncnn-vulkan{paths.BIN_EXT}") or shutil.which("rife-ncnn-vulkan")
    if sys_rife:
        paths.RIFE_BIN = Path(sys_rife)
        _maybe_chmod(Path(sys_rife))
        manifest.record("rife", "system", paths.RIFE_BIN)
        return True

    if bar:
        bar.update(0, label=_("rife-ncnn-vulkan not found, downloading..."))
    else:
        status(_("rife-ncnn-vulkan not found locally or on system."), "WARN")

    url = RIFE_RELEASE_URLS().get(paths.OS_NAME)
    if not url:
        if not auto_yes:
            _show_manual_install_hint("rife-ncnn-vulkan")
        return False

    if not auto_yes and not ask_yes_no(_("Download rife-ncnn-vulkan now? (~400 MB)"), default=True):
        _show_manual_install_hint("rife-ncnn-vulkan")
        return False

    ok = download_and_extract(url, paths._RIFE_DIR, "rife-ncnn-vulkan", bar=bar)
    if not ok:
        if not auto_yes:
            status(_("Could not download rife-ncnn-vulkan."), "ERROR")
            _show_manual_install_hint("rife-ncnn-vulkan")
        return False

    if rife_bin.is_file():
        _maybe_chmod(rife_bin)
        manifest.record("rife", "downloaded", rife_bin)
        return True

    for f in paths._RIFE_DIR.rglob(f"rife-ncnn-vulkan{paths.BIN_EXT}"):
        _maybe_chmod(f)
        shutil.move(str(f), str(rife_bin))
        break

    if rife_bin.is_file():
        _maybe_chmod(rife_bin)
        manifest.record("rife", "downloaded", rife_bin)
        return True

    if not auto_yes:
        status(
            _("rife-ncnn-vulkan must be placed manually in:") + f"\n  {rife_bin}\n"
            + _("Download from: https://github.com/nihui/rife-ncnn-vulkan/releases"),
            "ERROR",
        )
    return False


def _show_manual_install_hint(tool):
    if "ffmpeg" in tool:
        dest = paths._FFMPEG_DIR
        if paths.OS_NAME == "macos":
            hint = _("Install via: brew install ffmpeg-full")
        else:
            hint = _("Download from: https://johnvansickle.com/ffmpeg/")
    else:
        dest = paths._RIFE_DIR
        hint = _("Download from: https://github.com/nihui/rife-ncnn-vulkan/releases")
    status(
        _("{tool} must be placed manually in:").format(tool=tool) + f"\n  {dest}\n" + hint,
        "ERROR",
    )
