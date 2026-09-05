import shutil
import sys
import time

from . import paths
from .colors import Color
from .config import CONFIG, DEFAULT_CONFIG
from .console import status
from .extract import extract_frames, count_files
from .i18n import _
from .interpolate import run_interpolation
from .models import install_model
from .reassemble import reassemble_video
from .temp import TempManager
from .disk import estimate_frame_storage

PRESETS = {
    "balanced": {"encoder": "libx264", "ffmpeg_preset": "veryfast", "crf": 20,
                 "model": "rife-v4.6", "threads": "1:4:4"},
}


def run_pipeline(info, target_fps, output_path, gpu_settings, model=None, interactive=False):
    start_time = time.time()
    user_model = model is not None
    if model is None:
        model = CONFIG.get("model", DEFAULT_CONFIG["model"])
    vp = CONFIG.get("video_preset")
    config_rife_threads = CONFIG.get("rife_threads")
    if vp and vp in PRESETS:
        pv = PRESETS[vp]
        if not user_model:
            model = pv.get("model", model)
        rife_threads = config_rife_threads or pv.get("threads") or gpu_settings["threads"]
        rife_tile_size = pv.get("tile_size") or gpu_settings.get("tile_size", 0)
    else:
        rife_threads = config_rife_threads or gpu_settings["threads"]
        rife_tile_size = gpu_settings.get("tile_size", 0)
    model_dir = paths.MODELS_DIR / model
    if not model_dir.is_dir():
        status(f"{_('Model')} {model} {_('not found. Downloading...')}")
        if not install_model(model):
            status(f"{_('Model')} {model} {_('is required but could not be installed.')}", "ERROR")
            return False

    w = max(info.get("width", 1920), 1920)
    h = max(info.get("height", 1080), 1080)
    fc = max(info.get("frame_count", 18000) or int(info.get("fps", 30) * info.get("duration", 600)), 100)
    estimated = estimate_frame_storage(w, h, fc)
    tmp = TempManager(estimated_bytes=estimated)

    if interactive:
        from .progress import PipelineBar
        from .utils import format_fps
        name = info['path'].name
        header = [
            Color.bold(name),
            "",
            Color.accent_bold(f"{format_fps(info['fps'])} fps → {format_fps(target_fps)} fps"),
        ]
        pbar = PipelineBar(header=header)
        pb = pbar.update
    else:
        pbar = None
        pb = None

    frame_count = extract_frames(
        info["path"], tmp.in_frames_dir, info, gpu_settings,
        progress_cb=(lambda f: pb(f * 0.30, _("Extracting frames..."))) if pb else None,
    )

    actual_fps = run_interpolation(
        in_frames_dir=tmp.in_frames_dir,
        out_frames_dir=tmp.out_frames_dir,
        model=model,
        threads=rife_threads,
        source_frame_count=frame_count,
        source_fps=info["fps"],
        target_fps=target_fps,
        gpu_id=gpu_settings["gpu_id"],
        uhd=gpu_settings["uhd"],
        tile_size=rife_tile_size,
        rife_cpu=gpu_settings.get("rife_cpu", False),
        progress_cb=(lambda f: pb(0.30 + f * 0.55, _("Interpolating..."))) if pb else None,
    )

    result_frames = count_files(tmp.out_frames_dir, "*.png")
    final_output_path = reassemble_video(
        out_frames_dir=tmp.out_frames_dir,
        original_video=info["path"],
        target_fps=actual_fps,
        has_audio=info["has_audio"],
        output_path=output_path,
        result_frames=result_frames,
        encoder_name=CONFIG.get("encoder", DEFAULT_CONFIG["encoder"]),
        crf=CONFIG.get("crf", DEFAULT_CONFIG["crf"]),
        preset=CONFIG.get("preset", DEFAULT_CONFIG["preset"]),
        gpu_settings=gpu_settings,
        progress_cb=(lambda f: pb(0.85 + f * 0.15, _("Encoding video..."))) if pb else None,
        info=info,
    )

    if pbar:
        pbar.close()
    tmp.cleanup()
    from .utils import format_duration
    elapsed = time.time() - start_time
    if pbar:
        _show_success_screen(final_output_path, elapsed)
    else:
        status(
            f"{_('Video exported successfully in')} {format_duration(elapsed)} "
            f"{_('saved to:')} {final_output_path}",
            "OK",
        )
    return True


def _show_success_screen(output_path, elapsed):
    from .utils import format_duration
    term_w = shutil.get_terminal_size().columns
    term_h = shutil.get_terminal_size().lines
    line1 = f"{_('Video exported successfully in')} {format_duration(elapsed)}"
    line2 = f"{_('saved to:')} {output_path}"
    hint = _("Press b to return to the menu")
    vpad = max(0, term_h // 2 - 3)
    sys.stdout.write("\033[2J\033[H\033[3J" + "\n" * vpad)
    for line, color_fn in ((line1, Color.ok_bold), (line2, Color.dim), (hint, Color.dim)):
        pad = min(60, max(0, (term_w - len(line)) // 2))
        sys.stdout.write(" " * pad + color_fn(line) + "\n")
    sys.stdout.flush()
    _wait_for_b()


def _wait_for_b():
    if not (sys.platform.startswith("linux") and sys.stdin.isatty()):
        return
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch in ("b", "B"):
                break
            if ch == "\x03":
                termios.tcsetattr(fd, termios.TCSANOW, old)
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                sys.exit(130)
    except KeyboardInterrupt:
        sys.stdout.write("\r\n")
        sys.stdout.flush()
        sys.exit(130)
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, old)
    sys.stdout.write("\r\n")
    sys.stdout.flush()
