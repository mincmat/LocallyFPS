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


def _watch_progress_proc(output_dir, target_frames, stop_event, pbar):
    last_count = 0
    while not stop_event.is_set():
        current = count_files(output_dir, "*.jpg")
        if current > last_count:
            pbar.update(current - last_count)
            last_count = current
        import time
        time.sleep(0.8)
    current = count_files(output_dir, "*.png")
    if current > last_count:
        pbar.update(current - last_count)


def _watch_progress_cb(output_dir, target_frames, stop_event, cb):
    last_count = 0
    while not stop_event.is_set():
        current = count_files(output_dir, "*.jpg")
        if current > last_count:
            last_count = current
            cb(current / max(1, target_frames))
        import time
        time.sleep(0.8)
    current = count_files(output_dir, "*.png")
    if current > last_count:
        cb(current / max(1, target_frames))


def extract_frames(video_path, frames_dir, info=None, gpu_settings=None, progress_cb=None):
    if info:
        w = max(info.get("width", 1920), 1920)
        h = max(info.get("height", 1080), 1080)
        fc = max(info.get("frame_count", 18000) or int(info.get("fps", 30) * info.get("duration", 600)), 100)
        estimated = estimate_frame_storage(w, h, fc)
        check_disk_space(frames_dir, estimated)

    total_est = info["frame_count"] if info else 0

    cmd = [
        str(paths.FFMPEG_BIN), "-y",
        "-threads", "auto",
        "-i", str(video_path),
        "-vsync", "0",
        "-q:v", "1",
        str(frames_dir / "%08d.jpg"),
    ]
    if total_est:
        stop_event = threading.Event()
        if progress_cb:
            watcher = threading.Thread(
                target=_watch_progress_cb, args=(frames_dir, total_est, stop_event, progress_cb), daemon=True
            )
        elif HAS_TQDM:
            pbar = tqdm(total=total_est, desc=_("Extracting frames"), unit="frame", bar_format="{l_bar}{bar:30}{r_bar}")
            watcher = threading.Thread(
                target=_watch_progress_proc, args=(frames_dir, total_est, stop_event, pbar), daemon=True
            )
        else:
            pbar = ProgressBar(total=total_est, desc=_("Extracting frames"), unit="frame", width=35)
            watcher = threading.Thread(
                target=_watch_progress_proc, args=(frames_dir, total_est, stop_event, pbar), daemon=True
            )
        watcher.start()

    result = subprocess.run(cmd, capture_output=True, text=True)

    if total_est:
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
