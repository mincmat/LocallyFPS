import subprocess
import sys
import threading

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

from . import paths
from .colors import Color
from .console import status
from .extract import count_files, _watch_progress_cb, _watch_progress_proc
from .i18n import _
from .progress import ProgressBar


def _model_supports_custom_frame_count(model):
    return model.startswith("rife-v4")


def run_interpolation(
    in_frames_dir, out_frames_dir, model, threads,
    source_frame_count, source_fps, target_fps,
    gpu_id=None, uhd=False, tile_size=0, progress_cb=None
):
    supports_n = _model_supports_custom_frame_count(model)
    if supports_n:
        target_frame_count = max(
            source_frame_count, round(source_frame_count * (target_fps / source_fps))
        )
        actual_output_fps = source_fps * (target_frame_count / source_frame_count)
    else:
        target_frame_count = source_frame_count * 2
        actual_output_fps = source_fps * 2
        if abs(actual_output_fps - target_fps) > 0.01:
            status(f"{_('Model')} '{model}' {_('only supports 2x frame rate.')}", "WARN")
            status(f"{_('Output will be at')} {actual_output_fps:.3f} fps {_('instead.')}", "WARN")

    cmd = [
        str(paths.RIFE_BIN),
        "-i", str(in_frames_dir),
        "-o", str(out_frames_dir),
        "-m", str(paths.MODELS_DIR / model),
        "-j", threads,
    ]
    if supports_n:
        cmd += ["-n", str(target_frame_count)]
    if gpu_id is not None:
        cmd += ["-g", str(gpu_id)]
    if uhd:
        cmd += ["-u"]
    if tile_size > 0:
        cmd += ["-t", str(tile_size)]

    desc = _("Interpolating")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    stop_event = threading.Event()
    if progress_cb:
        watcher = threading.Thread(
            target=_watch_progress_cb, args=(out_frames_dir, target_frame_count, stop_event, progress_cb), daemon=True
        )
    elif HAS_TQDM:
        pbar = tqdm(total=target_frame_count, desc=Color.bold(desc), unit="frame", bar_format="{l_bar}{bar:30}{r_bar}")
        watcher = threading.Thread(
            target=_watch_progress_proc, args=(out_frames_dir, target_frame_count, stop_event, pbar), daemon=True
        )
    else:
        pbar = ProgressBar(total=target_frame_count, desc=desc, unit="frame", width=35)
        watcher = threading.Thread(
            target=_watch_progress_proc, args=(out_frames_dir, target_frame_count, stop_event, pbar), daemon=True
        )
    watcher.start()

    output_lines = []
    for line in process.stdout:
        output_lines.append(line.rstrip())

    process.wait()
    stop_event.set()
    watcher.join()
    if not progress_cb:
        pbar.close()

    if process.returncode != 0:
        status(_("RIFE completed with error."), "ERROR")
        for line in output_lines[-20:]:
            status(f"    {line}", "ERROR")
        sys.exit(1)

    result_frames = count_files(out_frames_dir, "*.png")
    if not progress_cb:
        print(f"{Color.ok(_('[✓]'))} {_('Interpolation complete:')} {Color.bold(str(result_frames))} {_('frames generated')}", flush=True)
    return actual_output_fps
