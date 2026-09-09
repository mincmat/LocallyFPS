"""Self-tests executed against the actual frozen desktop distribution."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from . import paths


def _report(payload):
    """Emit diagnostics when a console exists; Windows GUI builds have none."""
    stream = sys.stdout or getattr(sys, "__stdout__", None)
    if stream is not None:
        print(json.dumps(payload, indent=2), file=stream)


def _run(command, *, accepted=(0,)):
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode not in accepted:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"Command failed ({result.returncode}): {detail}")
    return result


def dependency_smoke_test():
    """Verify that the frozen app contains runnable, feature-complete tools."""
    required = (
        paths.FFMPEG_BIN,
        paths.FFPROBE_BIN,
        paths.RIFE_BIN,
        paths.MODELS_DIR / "rife-v4.6" / "flownet.bin",
        paths.MODELS_DIR / "rife-v4.6" / "flownet.param",
    )
    missing = [str(item) for item in required if not item.is_file()]
    if missing:
        raise RuntimeError("Missing bundled runtime files: " + ", ".join(missing))
    _run([str(paths.FFMPEG_BIN), "-version"])
    _run([str(paths.FFPROBE_BIN), "-version"])
    filters = _run([str(paths.FFMPEG_BIN), "-hide_banner", "-filters"]).stdout
    missing_filters = [name for name in ("minterpolate", "zscale", "tonemap") if name not in filters]
    if missing_filters:
        raise RuntimeError("Bundled FFmpeg lacks filters: " + ", ".join(missing_filters))
    # RIFE returns a non-zero status after printing usage on some platforms.
    rife = _run([str(paths.RIFE_BIN), "-h"], accepted=(0, 1, 255, -6))
    if "Usage" not in (rife.stdout + rife.stderr) and "rife" not in (rife.stdout + rife.stderr).lower():
        raise RuntimeError("The bundled RIFE executable did not start correctly")
    _report({
        "platform": paths.OS_NAME,
        "bundled_runtime": paths.BUNDLED_RUNTIME,
        "ffmpeg": str(paths.FFMPEG_BIN),
        "rife": str(paths.RIFE_BIN),
        "model": str(paths.MODELS_DIR / "rife-v4.6"),
    })


def pipeline_smoke_test():
    """Run a small real 24-to-48 FPS job using only packaged resources."""
    from .gpu import choose_gpu_settings
    from .pipeline import run_pipeline
    from .probe import probe_video_file

    dependency_smoke_test()
    with tempfile.TemporaryDirectory(prefix="locallyfps_packaged_test_") as temp:
        work = Path(temp)
        source = work / "source.mp4"
        output = work / "output.mkv"
        _run([
            str(paths.FFMPEG_BIN), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=24:duration=0.5",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(source),
        ])
        info = probe_video_file(source)
        if not info:
            raise RuntimeError("Could not probe generated smoke-test video")
        old_cache = paths.CACHE_DIR
        paths.CACHE_DIR = work / "cache"
        try:
            ok = run_pipeline(
                info, 48.0, output,
                choose_gpu_settings(info["display_width"], info["display_height"]),
                interactive=False,
                progress_cb=lambda _value, _label=None: None,
            )
        finally:
            paths.CACHE_DIR = old_cache
        if not ok:
            raise RuntimeError("Packaged interpolation pipeline failed")
        result = _run([
            str(paths.FFPROBE_BIN), "-v", "error", "-select_streams", "v:0",
            "-count_frames", "-show_entries", "stream=avg_frame_rate,nb_read_frames",
            "-of", "json", str(output),
        ])
        stream = json.loads(result.stdout)["streams"][0]
        if stream.get("avg_frame_rate") != "48/1" or int(stream.get("nb_read_frames", 0)) != 24:
            raise RuntimeError(f"Unexpected packaged output: {stream}")
        audio_result = _run([
            str(paths.FFPROBE_BIN), "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=codec_type", "-of", "json", str(output),
        ])
        audio_streams = json.loads(audio_result.stdout).get("streams", [])
        if len(audio_streams) != 1 or audio_streams[0].get("codec_type") != "audio":
            raise RuntimeError(f"Packaged output did not preserve one audio stream: {audio_streams}")
        _run([str(paths.FFMPEG_BIN), "-v", "error", "-i", str(output), "-f", "null", "-"])
        _report({"fps": 48, "frames": 24, "audio_streams": 1, "decoded": True})
