import os
import subprocess
import threading
from pathlib import Path

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

from . import paths
from .console import status
from .disk import check_disk_space, estimate_frame_storage
from .i18n import _
from .progress import ProgressBar


def count_files(directory, pattern="*"):
    if pattern == "*":
        return len(os.listdir(str(directory)))
    count = 0
    for _ in Path(directory).glob(pattern):
        count += 1
    return count


def _watch_progress_proc(output_dir, target_frames, stop_event, pbar, file_pattern="*.jpg"):
    last_count = 0
    while not stop_event.is_set():
        current = count_files(output_dir, file_pattern)
        if current > last_count:
            pbar.update(current - last_count)
            last_count = current
        import time
        time.sleep(0.8)
    current = count_files(output_dir, file_pattern)
    if current > last_count:
        pbar.update(current - last_count)


def _watch_progress_cb(output_dir, target_frames, stop_event, cb, file_pattern="*.jpg"):
    last_count = 0
    while not stop_event.is_set():
        current = count_files(output_dir, file_pattern)
        if current > last_count:
            last_count = current
            cb(current / max(1, target_frames))
        import time
        time.sleep(0.8)
    current = count_files(output_dir, file_pattern)
    if current > last_count:
        cb(current / max(1, target_frames))


def _resolve_ffmpeg_bin():
    import shutil
    if paths.FFMPEG_BIN and paths.FFMPEG_BIN.is_file():
        return str(paths.FFMPEG_BIN)
    return shutil.which("ffmpeg") or str(paths.FFMPEG_BIN)

def _get_fps_mode_args():
    """Return ffmpeg args for passthrough fps mode, compatible with FFmpeg 5-8.
    FFmpeg 7+ uses -fps_mode, older uses -vsync. Cache detection."""
    if hasattr(_get_fps_mode_args, "_cached"):
        return _get_fps_mode_args._cached
    ffmpeg_bin = _resolve_ffmpeg_bin()
    try:
        r = subprocess.run([ffmpeg_bin, "-version"], capture_output=True, text=True, timeout=3)
        ver = r.stdout + r.stderr
        import re
        m = re.search(r"ffmpeg version (\d+)", ver)
        major = int(m.group(1)) if m else 0
        # FFmpeg 7+ renamed vsync -> fps_mode
        if major >= 7:
            args = ["-fps_mode", "passthrough"]
        else:
            args = ["-vsync", "0"]
    except Exception:
        args = ["-fps_mode", "passthrough"]
    _get_fps_mode_args._cached = args
    return args


def _get_pix_fmt_filter(info):
    """Return a -vf filter string to normalize pixel format for JPEG extraction.

    HEVC Main 10 uses yuv420p10le which cannot be directly encoded to JPEG
    without quality loss or corruption. This forces conversion to yuv420p.
    For HDR content (smpte2084, arib-std-b67), adds tone mapping to SDR.
    """
    if not info:
        return "format=yuv420p"

    color_transfer = info.get("color_transfer", "")
    is_hdr = color_transfer in ("smpte2084", "arib-std-b67")

    if is_hdr:
        return (
            "zscale=t=linear:npl=100,format=gbrpf32le,"
            "zscale=p=bt709:tonemap=hable,"
            "zscale=t=bt709:range=pc,format=yuv420p"
        )
    return "format=yuv420p"


def extract_frames(video_path, frames_dir, info=None, gpu_settings=None, progress_cb=None):
    if info:
        w = max(info.get("width", 1920), 1920)
        h = max(info.get("height", 1080), 1080)
        fc = max(info.get("frame_count", 18000) or int(info.get("fps", 30) * info.get("duration", 600)), 100)
        estimated = estimate_frame_storage(w, h, fc)
        check_disk_space(frames_dir, estimated)

    total_est = info["frame_count"] if info else 0
    if not total_est and info:
        total_est = max(int(info.get("fps", 30) * info.get("duration", 60)), 100)

    ffmpeg_bin = _resolve_ffmpeg_bin()

    pix_fmt_filter = _get_pix_fmt_filter(info)

    cmd = [
        ffmpeg_bin, "-y",
        "-threads", "auto",
        "-i", str(video_path),
        *_get_fps_mode_args(),
    ]
    if pix_fmt_filter:
        cmd += ["-vf", pix_fmt_filter]
    cmd += ["-q:v", "1", str(frames_dir / "%08d.jpg")]
    stop_event = threading.Event()
    if progress_cb:
        watcher = threading.Thread(
            target=_watch_progress_cb, args=(frames_dir, total_est, stop_event, progress_cb, "*.jpg"), daemon=True
        )
        watcher.start()
    elif HAS_TQDM:
        pbar = tqdm(total=total_est, desc=_("Extracting frames"), unit="frame", bar_format="{l_bar}{bar:30}{r_bar}")
        watcher = threading.Thread(
            target=_watch_progress_proc, args=(frames_dir, total_est, stop_event, pbar, "*.jpg"), daemon=True
        )
        watcher.start()
    else:
        pbar = ProgressBar(total=total_est, desc=_("Extracting frames"), unit="frame", width=35)
        watcher = threading.Thread(
            target=_watch_progress_proc, args=(frames_dir, total_est, stop_event, pbar, "*.jpg"), daemon=True
        )
        watcher.start()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        stop_event.set()
        watcher.join()
        status(_("ffmpeg not found. Install dependencies first."), "ERROR")
        return 0

# Fallback for FFmpeg version mismatch (vsync vs fps_mode)
    if result.returncode != 0 and "Unrecognized option" in (result.stderr or ""):
        err = result.stderr.lower()
        fallback = None
        if "fps_mode" in err:
            fallback = ["-vsync", "0"]
        elif "vsync" in err:
            fallback = ["-fps_mode", "passthrough"]
        if fallback:
            cmd_fallback = [
                ffmpeg_bin, "-y",
                "-threads", "auto",
                "-i", str(video_path),
                *fallback,
            ]
            if pix_fmt_filter:
                cmd_fallback += ["-vf", pix_fmt_filter]
            cmd_fallback += ["-q:v", "1", str(frames_dir / "%08d.jpg")]
            result = subprocess.run(cmd_fallback, capture_output=True, text=True)

    stop_event.set()
    watcher.join()
    if not progress_cb:
        pbar.close()

    if result.returncode != 0:
        status(f"{_('Error extracting frames:')}\n{result.stderr[-2000:]}", "ERROR")
        import sys
        sys.exit(1)

    extracted = count_files(frames_dir, "*.jpg")
    if extracted == 0:
        status(_("No frames extracted. Aborting."), "ERROR")
        import sys
        sys.exit(1)
    return extracted
