import json
import os
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


def _compatible_output(codec_name, output_path, info=None):
    """Return an output path whose container can hold the chosen codec."""
    subtitles = (info or {}).get("subtitle_streams", [])
    mp4_text_codecs = {"ass", "ssa", "subrip", "text", "mov_text", "webvtt"}
    if ((subtitles and any(s.get("codec") not in mp4_text_codecs for s in subtitles))
            or (info or {}).get("attachment_tracks", 0)):
        return output_path.with_suffix(".mkv")
    if output_path.suffix.lower() in (".mp4", ".m4v", ".mov", ".mkv"):
        return output_path
    return output_path.with_suffix(".mp4")


def _add_color_flags(cmd, info):
    """Append color metadata flags to ffmpeg command if available."""
    invalid = {None, "", "unknown", "unspecified", "reserved"}
    if info.get("color_primaries") not in invalid:
        cmd += ["-color_primaries", info["color_primaries"]]
    if info.get("color_space") not in invalid:
        cmd += ["-colorspace", info["color_space"]]
    if info.get("color_transfer") not in invalid:
        cmd += ["-color_trc", info["color_transfer"]]
    if info.get("color_range") not in invalid:
        cmd += ["-color_range", info["color_range"]]


def _output_color_info(info):
    """Describe the actual output colors after extraction/tone mapping."""
    if not info:
        return info
    if info.get("color_transfer") in ("smpte2084", "arib-std-b67"):
        normalized = dict(info)
        normalized.update({
            "color_primaries": "bt709",
            "color_space": "bt709",
            "color_transfer": "bt709",
            "color_range": "tv",
        })
        return normalized
    if info.get("color_space") in ("gbr", "rgb"):
        normalized = dict(info)
        normalized.update({
            "color_primaries": "bt709",
            "color_space": "bt709",
            "color_transfer": "bt709",
            "color_range": "tv",
        })
        return normalized
    return info


def _build_video_filter(codec_name, info=None):
    """Make encoder dimensions legal and retain non-square pixel geometry."""
    filters = ["pad=ceil(iw/2)*2:ceil(ih/2)*2"]
    sar = (info or {}).get("sample_aspect_ratio")
    if sar and re.fullmatch(r"\d+:\d+", str(sar)) and sar not in ("0:1", "1:1"):
        filters.append(f"setsar=ratio={sar.replace(':', '/')}")
    invalid = {None, "", "unknown", "unspecified", "reserved"}
    setparams = []
    if (info or {}).get("color_primaries") not in invalid:
        setparams.append(f"color_primaries={info['color_primaries']}")
    if (info or {}).get("color_transfer") not in invalid:
        setparams.append(f"color_trc={info['color_transfer']}")
    if (info or {}).get("color_space") not in invalid:
        setparams.append(f"colorspace={info['color_space']}")
    color_range = (info or {}).get("color_range")
    if color_range in ("tv", "limited"):
        setparams.append("range=limited")
    elif color_range in ("pc", "full"):
        setparams.append("range=full")
    if setparams:
        filters.append("setparams=" + ":".join(setparams))
    if "vaapi" in codec_name:
        filters += ["format=nv12", "hwupload"]
    return ",".join(filters)


def _pick_best_encoder(preferred="libx264"):
    from platform import get_platform
    plat = get_platform()
    encoder_presets = plat.get_encoder_presets()
    available = _detect_available_encoders()
    vendors = _detect_gpu_vendors()

    if (config.CONFIG.get("encoder_mode", "auto") == "manual"
            and preferred in available and preferred in encoder_presets):
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


def _add_attachment_args(cmd, output_path, info):
    if (info or {}).get("attachment_tracks", 0) and output_path.suffix.lower() == ".mkv":
        cmd += ["-map", "1:t?", "-c:t", "copy"]


def _build_encode_command(
    enc, out_frames_dir, original_video, target_fps, output_path,
    has_audio, video_duration, crf, preset, info
):
    codec_name = enc["codec"]
    cmd = [
        str(paths.FFMPEG_BIN), "-y", "-hide_banner", "-v", "error", "-xerror",
        "-threads", "auto",
        "-r", str(target_fps), "-i", str(out_frames_dir / "%08d.png"),
        "-i", str(original_video), "-map", "0:v:0",
    ]
    if has_audio:
        cmd += ["-map", "1:a?", "-c:a", "aac", "-b:a", "192k"]
    _add_subtitle_args(cmd, output_path, info)
    _add_attachment_args(cmd, output_path, info)
    cmd += ["-map_metadata", "1", "-map_chapters", "1"]
    if "vaapi" in codec_name:
        render_nodes = sorted(p for p in Path("/dev/dri").glob("renderD*") if p.is_char_device())
        if not render_nodes:
            raise RuntimeError(_("VAAPI device not found, trying other encoders."))
        cmd += ["-vaapi_device", str(render_nodes[0])]
    output_info = _output_color_info(info)
    cmd += ["-vf", _build_video_filter(codec_name, output_info)]
    cmd += ["-c:v", codec_name, *_encoder_args(codec_name, crf, preset)]
    cmd += ["-pix_fmt", enc["pix_fmt"]]
    if info:
        _add_color_flags(cmd, output_info)
    if output_path.suffix.lower() in (".mp4", ".m4v", ".mov"):
        cmd += ["-movflags", "+faststart"]
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
    stderr_thread.join()
    if process.stdout:
        process.stdout.close()
    if process.stderr:
        process.stderr.close()
    return process.returncode, "".join(stderr_buf), sp


def _validate_output(
    output_path, expected_fps=None, expected_frames=None,
    expected_duration=None, expected_audio_tracks=None,
    expected_subtitle_tracks=None, expected_attachment_tracks=None,
):
    if not output_path.is_file() or output_path.stat().st_size == 0:
        return False
    cmd = [
        str(paths.FFPROBE_BIN), "-v", "error", "-count_frames",
        "-show_streams", "-show_format", "-of", "json", str(output_path),
    ]
    try:
        timeout = max(60.0, min(7200.0, (expected_duration or 0) * 2.0))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0 or result.stderr.strip() or not result.stdout.strip():
        return False
    try:
        data = json.loads(result.stdout)
        streams = data.get("streams") or []
        video = next(s for s in streams if s.get("codec_type") == "video")
        if not video.get("codec_name"):
            return False
        if expected_frames is not None:
            count = int(video.get("nb_read_frames") or video.get("nb_frames") or 0)
            if count != int(expected_frames):
                return False
        if expected_fps is not None:
            num, den = video.get("avg_frame_rate", "0/0").split("/")
            actual_fps = float(num) / float(den) if float(den) else 0.0
            if abs(actual_fps - expected_fps) > max(0.01, expected_fps * 0.001):
                return False
        if expected_duration is not None:
            actual_duration = float((data.get("format") or {}).get("duration") or 0)
            tolerance = max(0.25, 2.0 / max(expected_fps or 1.0, 1.0))
            if abs(actual_duration - expected_duration) > tolerance:
                return False
        if expected_audio_tracks is not None:
            audio_count = sum(s.get("codec_type") == "audio" for s in streams)
            if audio_count != int(expected_audio_tracks):
                return False
        if expected_subtitle_tracks is not None:
            subtitle_count = sum(s.get("codec_type") == "subtitle" for s in streams)
            if subtitle_count != int(expected_subtitle_tracks):
                return False
        if expected_attachment_tracks is not None:
            attachment_count = sum(s.get("codec_type") == "attachment" for s in streams)
            if attachment_count != int(expected_attachment_tracks):
                return False
    except (ValueError, TypeError, KeyError, StopIteration, json.JSONDecodeError):
        return False
    return True


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
    expected_audio_tracks = (info or {}).get("audio_tracks", 0) if has_audio else 0
    expected_subtitle_tracks = len((info or {}).get("subtitle_streams", []))
    expected_attachment_tracks = (info or {}).get("attachment_tracks", 0)
    for index, name in enumerate(candidates):
        candidate = encoder_presets[name]
        actual_output_path = _compatible_output(name, output_path, info)
        staging_path = actual_output_path.with_name(
            f".{actual_output_path.stem}.locallyfps-{os.getpid()}{actual_output_path.suffix}"
        )
        staging_path.unlink(missing_ok=True)
        try:
            cmd = _build_encode_command(
                candidate, out_frames_dir, original_video, target_fps,
                staging_path, has_audio, video_duration, crf, preset, info,
            )
        except RuntimeError as exc:
            tail = str(exc)
            status(tail, "WARN")
            continue
        label = _("Encoding video") if index == 0 else f"{_('Trying encoder')} {name}..."
        returncode, tail, last_spinner = _run_ffmpeg(cmd, video_duration, progress_cb, label)
        if returncode == 0 and _validate_output(
            staging_path,
            expected_fps=target_fps,
            expected_frames=result_frames,
            expected_duration=video_duration,
            expected_audio_tracks=expected_audio_tracks,
            expected_subtitle_tracks=expected_subtitle_tracks,
            expected_attachment_tracks=expected_attachment_tracks,
        ):
            staging_path.replace(actual_output_path)
            if last_spinner:
                last_spinner.ok(_("Encoding video"))
            return actual_output_path
        staging_path.unlink(missing_ok=True)
        if progress_cb is None:
            status(f"{_('Encoder')} {name} {_('failed.')}", "WARN")

    status(f"{_('Error reassembling video:')}\n{tail[-3000:]}", "ERROR")
    return None
