import time

from . import paths
from .config import CONFIG, DEFAULT_CONFIG
from .console import status
from .extract import extract_frames, count_files
from .i18n import _
from .interpolate import run_interpolation
from .models import install_model
from .progress import Spinner
from .reassemble import reassemble_video
from .temp import TempManager
from .disk import estimate_frame_storage

PRESETS = {
    "balanced": {"encoder": "libx264", "ffmpeg_preset": "veryfast", "crf": 20,
                 "model": "rife-v4.6", "threads": "1:4:4"},
}


def run_pipeline(info, target_fps, output_path, gpu_settings, model=None):
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

    sp = Spinner(_("Preparing..."))
    w = max(info.get("width", 1920), 1920)
    h = max(info.get("height", 1080), 1080)
    fc = max(info.get("frame_count", 18000) or int(info.get("fps", 30) * info.get("duration", 600)), 100)
    estimated = estimate_frame_storage(w, h, fc)
    tmp = TempManager(estimated_bytes=estimated)
    sp.ok(_("Prepared"))

    sp = Spinner(_("Extracting frames..."))
    frame_count = extract_frames(info["path"], tmp.in_frames_dir, info, gpu_settings)
    sp.ok(_("Frames extracted"))

    sp = Spinner(_("Interpolating frames..."))
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
    )

    sp = Spinner(_("Reassembling video..."))
    result_frames = count_files(tmp.out_frames_dir, "*.png")
    reassemble_video(
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
    )

    tmp.cleanup()
    from .utils import format_duration
    elapsed = time.time() - start_time
    status(
        f"{_('Video exported successfully in')} {format_duration(elapsed)} "
        f"{_('saved to:')} {output_path}",
        "OK",
    )
    return True
