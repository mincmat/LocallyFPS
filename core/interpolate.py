import os
import math
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

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


def _mean_absolute_difference(first, second, sample_limit=100_000):
    """Return a cheap RGB byte-distance using a bounded, uniform sample."""
    if not first or len(first) != len(second):
        return float("inf")
    step = max(1, len(first) // sample_limit)
    indexes = range(0, len(first), step)
    return sum(abs(first[i] - second[i]) for i in indexes) / len(indexes)


def _interpolated_frame_is_plausible(first, second, middle):
    """Reject obvious GPU corruption and silent duplicate-frame output."""
    source_delta = _mean_absolute_difference(first, second)
    first_delta = _mean_absolute_difference(first, middle)
    second_delta = _mean_absolute_difference(second, middle)
    nearest_source = min(first_delta, second_delta)
    if source_delta > 2.0 and nearest_source < source_delta * 0.01:
        return False
    return nearest_source <= max(40.0, source_delta * 3.0 + 10.0)


def _decode_rgb_frame(frame_path):
    try:
        result = subprocess.run(
            [
                str(paths.FFMPEG_BIN), "-v", "error", "-i", str(frame_path),
                "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
            ],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 and result.stdout else None


def _gpu_requires_safe_fallback(gpu_name):
    """Avoid a known RIFE/ncnn corruption path on Linux AMD Vulkan drivers."""
    if not sys.platform.startswith("linux") or not gpu_name:
        return False
    name = gpu_name.lower()
    return any(marker in name for marker in ("amd", "radeon", "renoir", "vega"))


def _validation_pair_indexes(frame_count, sample_count=5):
    """Spread validation pairs across the source instead of trusting its intro."""
    if frame_count < 2:
        return []
    last = frame_count - 2
    if last == 0:
        return [0]
    return sorted({round(last * i / (sample_count - 1)) for i in range(sample_count)})


def _validate_generated_sequence(out_frames_dir, expected_count, sample_count=9):
    """Require a complete, contiguous and decodable generated frame sequence."""
    frames = sorted(Path(out_frames_dir).glob("*.png"))
    if len(frames) != expected_count or not frames:
        return False
    for index, frame in enumerate(frames, 1):
        if frame.name != f"{index:08d}.png":
            return False
    last = len(frames) - 1
    indexes = sorted({round(last * i / max(1, sample_count - 1)) for i in range(sample_count)})
    decoded_size = None
    for index in indexes:
        decoded = _decode_rgb_frame(frames[index])
        if not decoded:
            return False
        if decoded_size is None:
            decoded_size = len(decoded)
        elif len(decoded) != decoded_size:
            return False
    return True


def _validate_rife_backend(in_frames_dir, model, gpu_id, uhd=False):
    """Interpolate distributed frame pairs before committing to a long run."""
    inputs = sorted(Path(in_frames_dir).glob("*.png"))
    if len(inputs) < 2:
        return False
    with tempfile.TemporaryDirectory(prefix="locallyfps_rife_check_") as temp:
        probe_output = Path(temp) / "interpolated.png"
        for index in _validation_pair_indexes(len(inputs)):
            cmd = [
                str(paths.RIFE_BIN),
                "-0", str(inputs[index]), "-1", str(inputs[index + 1]),
                "-o", str(probe_output),
                "-m", str(paths.MODELS_DIR / model),
                "-g", str(gpu_id),
            ]
            if uhd:
                cmd.append("-u")
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            except (OSError, subprocess.SubprocessError):
                return False
            if result.returncode != 0 or not probe_output.is_file():
                return False
            first = _decode_rgb_frame(inputs[index])
            second = _decode_rgb_frame(inputs[index + 1])
            middle = _decode_rgb_frame(probe_output)
            if first is None or second is None or middle is None:
                return False
            if not _interpolated_frame_is_plausible(first, second, middle):
                return False
        return True


def _detect_scene_cuts(in_frames_dir, source_fps, source_frame_count, threshold=0.30):
    """Return zero-based source indexes that start a new scene."""
    duration = source_frame_count / max(source_fps, 0.001)
    cmd = [
        str(paths.FFMPEG_BIN), "-hide_banner", "-v", "info",
        "-framerate", f"{source_fps:.12g}", "-start_number", "1",
        "-i", str(Path(in_frames_dir) / "%08d.png"),
        "-vf", f"select='gt(scene,{threshold})',metadata=print",
        "-an", "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=max(60.0, min(3600.0, duration * 0.5)),
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    if result.returncode != 0:
        return set()
    cuts = {int(value) for value in re.findall(r"frame:\d+\s+pts:(\d+)", result.stderr)}
    return {index for index in cuts if 0 < index < source_frame_count}


def _repair_scene_cut_frames(in_frames_dir, out_frames_dir, source_count, target_count, cuts):
    """Never retain an AI blend whose interpolation interval crosses a cut."""
    repaired = 0
    for cut in sorted(cuts):
        left = cut - 1
        first_output = max(0, math.floor(left * target_count / source_count))
        last_output = min(target_count - 1, math.ceil(cut * target_count / source_count))
        for output_index in range(first_output, last_output + 1):
            position = output_index * source_count / target_count
            if not (left < position < cut):
                continue
            source_index = left if position - left < 0.5 else cut
            source = Path(in_frames_dir) / f"{source_index + 1:08d}.png"
            target = Path(out_frames_dir) / f"{output_index + 1:08d}.png"
            if source.is_file() and target.is_file():
                shutil.copy2(source, target)
                repaired += 1
    return repaired


def _build_ffmpeg_fallback_command(
    in_frames_dir, out_frames_dir, source_fps, target_fps, target_frame_count
):
    """Build a stable motion-compensated fallback for broken Vulkan drivers."""
    fps = f"{target_fps:.12g}"
    source_rate = f"{source_fps:.12g}"
    tail_padding = f"{3.0 / max(source_fps, 0.001):.12g}"
    motion_filter = (
        f"tpad=stop_mode=clone:stop_duration={tail_padding},"
        f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=obmc:"
        "me_mode=bilat:vsbmc=0"
    )
    return [
        str(paths.FFMPEG_BIN), "-y", "-hide_banner", "-loglevel", "error", "-xerror",
        "-framerate", source_rate, "-start_number", "1",
        "-i", str(Path(in_frames_dir) / "%08d.png"),
        "-vf", motion_filter,
        "-frames:v", str(target_frame_count),
        "-compression_level", "1", str(Path(out_frames_dir) / "%08d.png"),
    ]


def run_interpolation(
    in_frames_dir, out_frames_dir, model, threads,
    source_frame_count, source_fps, target_fps,
    gpu_id=None, gpu_name=None, uhd=False, rife_cpu=False,
    progress_cb=None
):
    supports_n = _model_supports_custom_frame_count(model)
    if supports_n:
        target_frame_count = max(1, round(source_frame_count * (target_fps / source_fps)))
        actual_output_fps = source_fps * (target_frame_count / source_frame_count)
    else:
        target_frame_count = source_frame_count * 2
        actual_output_fps = source_fps * 2
        if abs(actual_output_fps - target_fps) > 0.01:
            status(f"{_('Model')} '{model}' {_('only supports 2x frame rate.')}", "WARN")
            status(f"{_('Output will be at')} {actual_output_fps:.3f} fps {_('instead.')}", "WARN")

    selected_gpu = -1 if rife_cpu else (gpu_id if gpu_id is not None else 0)
    use_ffmpeg_fallback = False
    scene_cuts = set()
    if target_fps <= source_fps:
        status(_("Target FPS is not higher than the source; using safe FFmpeg conversion."), "WARN")
        use_ffmpeg_fallback = True
    elif selected_gpu != -1 and _gpu_requires_safe_fallback(gpu_name):
        status(
            _("AMD Vulkan on Linux is using the safe optical-flow backend to prevent corrupt frames."),
            "WARN",
        )
        use_ffmpeg_fallback = True
    elif not _validate_rife_backend(in_frames_dir, model, selected_gpu, uhd=uhd):
        if selected_gpu == -1:
            status(_("RIFE output validation failed on CPU; using safe optical-flow fallback."), "WARN")
        else:
            status(
                _("GPU interpolation produced invalid frames; using safe optical-flow fallback."),
                "WARN",
            )
        use_ffmpeg_fallback = True

    if use_ffmpeg_fallback:
        status(
            _("Using FFmpeg motion interpolation. It will be slower but avoids corrupt frames."),
            "WARN",
        )
        cmd = _build_ffmpeg_fallback_command(
            in_frames_dir, out_frames_dir, source_fps, target_fps,
            target_frame_count,
        )
        actual_output_fps = target_fps
    elif rife_cpu:
        status(_("Integrated GPU cannot handle this resolution; using CPU instead."), "WARN")
        status(_("This will be slower. A dedicated GPU is recommended for large videos."), "WARN")
        cpu_threads = f"1:{min(os.cpu_count() or 4, 4)}:{min(os.cpu_count() or 4, 4)}"
        cmd = [
            str(paths.RIFE_BIN),
            "-i", str(in_frames_dir),
            "-o", str(out_frames_dir),
            "-m", str(paths.MODELS_DIR / model),
            "-j", cpu_threads,
            "-g", str(selected_gpu),
        ]
    else:
        cmd = [
            str(paths.RIFE_BIN),
            "-i", str(in_frames_dir),
            "-o", str(out_frames_dir),
            "-m", str(paths.MODELS_DIR / model),
            "-j", threads,
        ]
        cmd += ["-g", str(selected_gpu)]
    if not use_ffmpeg_fallback:
        scene_cuts = _detect_scene_cuts(
            in_frames_dir, source_fps, source_frame_count,
        )
    if supports_n and not use_ffmpeg_fallback:
        cmd += ["-n", str(target_frame_count)]
    if uhd and not use_ffmpeg_fallback:
        cmd += ["-u"]

    desc = _("Interpolating")
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    except FileNotFoundError:
        status(_("Interpolation engine not found. Install dependencies first."), "ERROR")
        return 0

    stop_event = threading.Event()
    if progress_cb:
        watcher = threading.Thread(
            target=_watch_progress_cb, args=(out_frames_dir, target_frame_count, stop_event, progress_cb, "*.png"), daemon=True
        )
    elif HAS_TQDM:
        pbar = tqdm(total=target_frame_count, desc=Color.bold(desc), unit="frame", bar_format="{l_bar}{bar:30}{r_bar}")
        watcher = threading.Thread(
            target=_watch_progress_proc, args=(out_frames_dir, target_frame_count, stop_event, pbar, "*.png"), daemon=True
        )
    else:
        pbar = ProgressBar(total=target_frame_count, desc=desc, unit="frame", width=35)
        watcher = threading.Thread(
            target=_watch_progress_proc, args=(out_frames_dir, target_frame_count, stop_event, pbar, "*.png"), daemon=True
        )
    watcher.start()

    output_lines = []
    for line in process.stdout:
        output_lines.append(line.rstrip())

    process.wait()
    if process.stdout:
        process.stdout.close()
    stop_event.set()
    watcher.join()
    if not progress_cb:
        pbar.close()

    if process.returncode != 0:
        status(_("Interpolation completed with error."), "ERROR")
        for line in output_lines[-20:]:
            status(f"    {line}", "ERROR")
        return 0

    if not use_ffmpeg_fallback and scene_cuts:
        repaired = _repair_scene_cut_frames(
            in_frames_dir, out_frames_dir, source_frame_count,
            target_frame_count, scene_cuts,
        )
        if repaired:
            status(
                f"{_('Protected scene changes')}: {len(scene_cuts)}",
                "INFO",
            )

    result_frames = count_files(out_frames_dir, "*.png")
    if not _validate_generated_sequence(out_frames_dir, target_frame_count):
        status(
            _("Interpolation output is incomplete, non-contiguous, or undecodable."),
            "ERROR",
        )
        return 0
    if not progress_cb:
        print(f"{Color.ok(_('[✓]'))} {_('Interpolation complete:')} {Color.bold(str(result_frames))} {_('frames generated')}", flush=True)
    return actual_output_fps
