import re
import subprocess
import threading
from pathlib import Path

from . import paths
from .colors import Color
from . import config
from .console import status
from .i18n import _
from .progress import Spinner

_ENCODER_CACHE = None


def _detect_available_encoders():
    global _ENCODER_CACHE
    if _ENCODER_CACHE is not None:
        return _ENCODER_CACHE
    try:
        cmd = [str(paths.FFMPEG_BIN), "-encoders"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        _ENCODER_CACHE = [
            name for name in re.findall(r"^\s*V\S{5}\s+(\S+)", r.stdout, re.MULTILINE)
            if name != "="
        ]
        return _ENCODER_CACHE
    except Exception:
        return []


def _detect_gpu_vendors():
    from platform import get_platform
    plat = get_platform()
    vendors = set()
    for _, name, _ in plat.detect_vulkan_gpus():
        n = name.lower()
        if "nvidia" in n or "geforce" in n or "quadro" in n or "rtx" in n or "gtx" in n:
            vendors.add("nvidia")
        if "intel" in n or "uhd" in n or "iris" in n:
            vendors.add("intel")
        if "amd" in n or "radeon" in n:
            vendors.add("amd")
    for vendor, _ in plat.detect_pci_gpus():
        vendors.add(vendor)
    return vendors


def _compatible_output(codec_name, output_path):
    """Return an output path whose container can hold the chosen codec."""
    if output_path.suffix.lower() in (".mp4", ".m4v", ".mov", ".mkv"):
        return output_path
    return output_path.with_suffix(".mp4")


def _add_color_flags(cmd, info):
    """Append color metadata flags to ffmpeg command if available."""
    if info.get("color_primaries"):
        cmd += ["-color_primaries", info["color_primaries"]]
    if info.get("color_space"):
        cmd += ["-colorspace", info["color_space"]]
    if info.get("color_transfer"):
        cmd += ["-color_trc", info["color_transfer"]]
    if info.get("color_range"):
        cmd += ["-color_range", info["color_range"]]


def _pick_best_encoder(preferred="libx264"):
    from platform import get_platform
    plat = get_platform()
    encoder_presets = plat.get_encoder_presets()
    available = _detect_available_encoders()
    vendors = _detect_gpu_vendors()

    vp = config.CONFIG.get("video_preset", "")
    if vp == "custom" and preferred in available and preferred in encoder_presets:
        return encoder_presets[preferred]

    if preferred in ("libx264", "libx265") and vendors:
        hw_map = plat.get_hw_encoder_map()
        for vendor, encs in hw_map:
            if vendor in vendors:
                for name in encs:
                    if name in available:
                        return encoder_presets[name]

    if preferred in encoder_presets:
        return encoder_presets[preferred]

    for name in ("libx264", "libx265", "libopenh264", "mpeg4"):
        if name in encoder_presets and name in available:
            return encoder_presets[name]

    return encoder_presets["libx264"]


def _encoder_args(codec_name, crf, preset):
    """Return rate-control options supported by each FFmpeg encoder family."""
    if codec_name in ("libx264", "libx265"):
        return ["-crf", str(crf), "-preset", preset]
    if codec_name in ("h264_nvenc", "hevc_nvenc"):
        return ["-rc", "vbr", "-cq", str(crf), "-b:v", "0"]
    if codec_name in ("h264_vaapi", "hevc_vaapi"):
        return ["-qp", str(crf)]
    if codec_name in ("h264_qsv", "hevc_qsv"):
        return ["-global_quality", str(crf)]
    if codec_name in ("h264_videotoolbox", "hevc_videotoolbox"):
        quality = max(1, min(100, 100 - int(crf) * 3))
        return ["-q:v", str(quality)]
    if codec_name in ("h264_amf", "hevc_amf"):
        return ["-quality", "balanced", "-qp_i", str(crf), "-qp_p", str(crf)]
    if codec_name == "libopenh264":
        return ["-b:v", "8M"]
    if codec_name == "mpeg4":
        return ["-q:v", "5"]
    return ["-b:v", "8M"]


def _add_subtitle_args(cmd, output_path, info):
    subtitles = (info or {}).get("subtitle_streams", [])
    if not subtitles:
        return
    if output_path.suffix.lower() == ".mkv":
        cmd += ["-map", "1:s?", "-c:s", "copy"]
        return
    text_codecs = {"ass", "ssa", "subrip", "text", "mov_text", "webvtt"}
    compatible = [s for s in subtitles if s.get("codec") in text_codecs]
    for stream in compatible:
        cmd += ["-map", f"1:{stream['index']}?"]
    if compatible:
        cmd += ["-c:s", "mov_text"]


def _build_encode_command(
    enc, out_frames_dir, original_video, target_fps, output_path,
    has_audio, video_duration, crf, preset, info
):
    codec_name = enc["codec"]
    cmd = [
        str(paths.FFMPEG_BIN), "-y", "-threads", "auto",
        "-r", str(target_fps), "-i", str(out_frames_dir / "%08d.png"),
        "-i", str(original_video), "-map", "0:v:0",
    ]
    if has_audio:
        cmd += ["-map", "1:a?", "-c:a", "aac", "-b:a", "192k"]
    _add_subtitle_args(cmd, output_path, info)
    cmd += ["-map_metadata", "1", "-map_chapters", "1"]
    if "vaapi" in codec_name:
        render_nodes = sorted(p for p in Path("/dev/dri").glob("renderD*") if p.is_char_device())
        if not render_nodes:
            raise RuntimeError(_("VAAPI device not found, trying other encoders."))
        cmd += ["-vaapi_device", str(render_nodes[0]), "-vf", "format=nv12,hwupload"]
    cmd += ["-c:v", codec_name, *_encoder_args(codec_name, crf, preset)]
    cmd += ["-pix_fmt", enc["pix_fmt"]]
    if info:
        _add_color_flags(cmd, info)
    cmd += ["-t", str(video_duration), str(output_path)]
    return cmd


def _run_ffmpeg(cmd, video_duration, progress_cb=None, label=None):
    sp = Spinner(label or _("Encoding video")) if progress_cb is None else None
    cmd_prog = [cmd[0], "-y", "-progress", "pipe:1"] + cmd[2:]
    try:
        process = subprocess.Popen(
            cmd_prog, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
    except FileNotFoundError:
        status(_("ffmpeg not found. Install dependencies first."), "ERROR")
        return 127, "ffmpeg not found", sp

    stderr_buf = []

    def _read_stderr():
        while True:
            chunk = process.stderr.read(65536)
            if not chunk:
                break
            stderr_buf.append(chunk)
            while len(stderr_buf) > 20:
                stderr_buf.pop(0)

    stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
    stderr_thread.start()
    time_re = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")
    for line in process.stdout:
        match = time_re.search(line)
        if match:
            h, mi, sec = (int(match.group(i)) for i in range(1, 4))
            frac = match.group(4).ljust(6, "0")[:6]
            elapsed = h * 3600 + mi * 60 + sec + int(frac) / 1_000_000
            if progress_cb:
                progress_cb(min(1.0, elapsed / max(0.001, video_duration)))
            elif sp:
                sp.tick()
    process.wait()
    stderr_thread.join(timeout=3)
    return process.returncode, "".join(stderr_buf), sp


def _validate_output(output_path):
    if not output_path.is_file() or output_path.stat().st_size == 0:
        return False
    cmd = [
        str(paths.FFPROBE_BIN), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(output_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def reassemble_video(
    out_frames_dir, original_video, target_fps,
    has_audio, output_path, result_frames,
    encoder_name="libx264", crf=18, preset="medium",
    gpu_settings=None, progress_cb=None, info=None
):
    from platform import get_platform
    plat = get_platform()
    encoder_presets = plat.get_encoder_presets()

    enc = _pick_best_encoder(encoder_name)
    video_duration = result_frames / target_fps
    available = set(_detect_available_encoders())
    ordered_names = [enc["codec"], "libx264", "libx265", "libopenh264", "mpeg4"]
    ordered_names += [name for name in available if name in encoder_presets]
    candidates = []
    for name in ordered_names:
        if name in encoder_presets and name in available and name not in candidates:
            candidates.append(name)

    tail = ""
    last_spinner = None
    for index, name in enumerate(candidates):
        candidate = encoder_presets[name]
        actual_output_path = _compatible_output(name, output_path)
        try:
            cmd = _build_encode_command(
                candidate, out_frames_dir, original_video, target_fps,
                actual_output_path, has_audio, video_duration, crf, preset, info,
            )
        except RuntimeError as exc:
            tail = str(exc)
            status(tail, "WARN")
            continue
        label = _("Encoding video") if index == 0 else f"{_('Trying encoder')} {name}..."
        returncode, tail, last_spinner = _run_ffmpeg(cmd, video_duration, progress_cb, label)
        if returncode == 0 and _validate_output(actual_output_path):
            if last_spinner:
                last_spinner.ok(_("Encoding video"))
            return actual_output_path
        if progress_cb is None:
            status(f"{_('Encoder')} {name} {_('failed.')}", "WARN")

    status(f"{_('Error reassembling video:')}\n{tail[-3000:]}", "ERROR")
    return None
