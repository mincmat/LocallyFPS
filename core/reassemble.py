import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import paths
from .colors import Color
from . import config
from .console import status
from .i18n import _
from .progress import DownloadProgress, PipelineBar, Spinner

_ENCODER_CACHE = None


def _detect_available_encoders():
    global _ENCODER_CACHE
    if _ENCODER_CACHE is not None:
        return _ENCODER_CACHE
    try:
        cmd = [str(paths.FFMPEG_BIN), "-encoders"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        _ENCODER_CACHE = re.findall(r"^\s*V.{5}\s+(\S+)", r.stdout, re.MULTILINE)
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
    if codec_name in ("libopenh264", "mpeg4", "libx264", "libx265"):
        return output_path.with_suffix(".mp4")
    return output_path


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
    if vp == "custom" and preferred in available:
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
    ffmpeg_hw = (gpu_settings or {}).get("ffmpeg_gpu", {}).get("hwaccel") or enc["hwaccel"]

    cmd = [str(paths.FFMPEG_BIN), "-y"]
    if ffmpeg_hw and "vaapi" not in ffmpeg_hw:
        cmd += ["-hwaccel", ffmpeg_hw, "-threads", "auto"]
    else:
        cmd += ["-threads", "auto"]
    cmd += ["-r", str(target_fps), "-i", str(out_frames_dir / "%08d.png")]

    if has_audio:
        cmd += ["-i", str(original_video)]

    cmd += ["-map", "0:v:0"]
    if has_audio:
        cmd += ["-map", "1:a:0"]

    if "vaapi" in enc["codec"]:
        render_nodes = sorted(p for p in Path("/dev/dri").glob("renderD*") if p.is_char_device())
        if render_nodes:
            cmd += ["-vaapi_device", str(render_nodes[0])]
            cmd += ["-vf", "format=rgb24,format=nv12,hwupload"]
        else:
            status(_("VAAPI device not found, trying other encoders."), "WARN")
            candidates = []
            av = _detect_available_encoders()
            for n in ("libx264", "libx265", "libopenh264", "mpeg4"):
                if n in encoder_presets and n in av:
                    candidates.append(n)
            for n in av:
                if n in encoder_presets and n not in candidates:
                    candidates.append(n)
            if candidates:
                enc = encoder_presets[candidates[0]]
            ffmpeg_hw = None
    actual_output_path = _compatible_output(enc["codec"], output_path)
    cmd += ["-c:v", enc["codec"]]
    codec_name = enc["codec"]
    if codec_name in ("libx264", "libx265"):
        cmd += ["-crf", str(crf), "-preset", preset]
    elif codec_name == "libopenh264":
        cmd += ["-b:v", "8M"]
    elif codec_name == "mpeg4":
        cmd += ["-q:v", "5"]
    else:
        cmd += ["-cq", str(crf)]
    cmd += ["-pix_fmt", enc["pix_fmt"]]
    if info:
        _add_color_flags(cmd, info)
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-t", str(video_duration)]
    cmd += [str(actual_output_path)]

    sp = Spinner(_("Encoding video")) if progress_cb is None else None
    cmd_prog = [str(paths.FFMPEG_BIN), "-y", "-progress", "pipe:1"] + cmd[2:]
    try:
        process = subprocess.Popen(cmd_prog, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    except FileNotFoundError:
        status(_("ffmpeg not found. Install dependencies first."), "ERROR")
        return None
    time_re = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")

    stderr_buf = []
    stderr_lock = threading.Lock()
    def _read_stderr():
        while True:
            chunk = process.stderr.read(65536)
            if not chunk:
                break
            with stderr_lock:
                stderr_buf.append(chunk)
                while len(stderr_buf) > 20:
                    stderr_buf.pop(0)
    stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
    stderr_thread.start()

    time_elapsed = 0
    spinner_timeout = 10
    last_update = time.time()
    for line in process.stdout:
        m = time_re.search(line)
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            frac = m.group(4).ljust(6, "0")[:6]
            time_elapsed = h * 3600 + mi * 60 + s + int(frac) / 1000000
            if progress_cb:
                progress_cb(min(1.0, time_elapsed / max(0.001, video_duration)))
            elif sp:
                sp.tick()
            while time.time() - last_update > spinner_timeout:
                if sp:
                    sp.tick()
                last_update = time.time()

    process.wait()
    stderr_thread.join(timeout=3)

    if process.returncode != 0 and enc["codec"] != "libx264":
        tail = "".join(stderr_buf)
        available = _detect_available_encoders()
        candidates = ["libx264", "libx265", "libopenh264", "mpeg4"]
        for n in available:
            if n in encoder_presets and n not in candidates:
                candidates.append(n)
        if not candidates:
            status(f"{_('No usable encoder found.')}\n{tail[-2000:]}", "ERROR")
            sys.exit(1)

        for fb_name in candidates:
            enc = encoder_presets[fb_name]
            ffmpeg_hw = None
            actual_output_path = _compatible_output(enc["codec"], output_path)
            cmd = [str(paths.FFMPEG_BIN), "-y", "-threads", "auto",
                   "-r", str(target_fps), "-i", str(out_frames_dir / "%08d.png")]
            if has_audio:
                cmd += ["-i", str(original_video)]
            cmd += ["-map", "0:v:0"]
            if has_audio:
                cmd += ["-map", "1:a:0"]
            cmd += ["-c:v", enc["codec"]]
            codec_name = enc["codec"]
            if codec_name in ("libx264", "libx265"):
                cmd += ["-vf", "format=yuv420p", "-crf", str(crf), "-preset", preset]
            elif codec_name == "libopenh264":
                cmd += ["-vf", "format=yuv420p", "-b:v", "8M"]
            elif codec_name == "mpeg4":
                cmd += ["-vf", "format=yuv420p", "-q:v", "5"]
            else:
                cmd += ["-crf", str(crf), "-preset", preset, "-pix_fmt", enc["pix_fmt"]]
            if info:
                _add_color_flags(cmd, info)
            if has_audio:
                cmd += ["-c:a", "aac", "-b:a", "192k"]
            cmd += ["-t", str(video_duration), str(actual_output_path)]
            sp = Spinner(_(f"Trying encoder {fb_name}...")) if progress_cb is None else None
            cmd_prog = [str(paths.FFMPEG_BIN), "-y", "-progress", "pipe:1"] + cmd[2:]
            try:
                process = subprocess.Popen(cmd_prog, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            except FileNotFoundError:
                status(_("ffmpeg not found. Install dependencies first."), "ERROR")
                return None
            stderr_buf = []
            stderr_lock = threading.Lock()
            def _read_stderr2():
                while True:
                    chunk = process.stderr.read(65536)
                    if not chunk:
                        break
                    with stderr_lock:
                        stderr_buf.append(chunk)
                        while len(stderr_buf) > 20:
                            stderr_buf.pop(0)
            stderr_thread = threading.Thread(target=_read_stderr2, daemon=True)
            stderr_thread.start()
            for line in process.stdout:
                m = time_re.search(line)
                if m:
                    h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    frac = m.group(4).ljust(6, "0")[:6]
                    time_elapsed = h * 3600 + mi * 60 + s + int(frac) / 1000000
                    if progress_cb:
                        progress_cb(min(1.0, time_elapsed / max(0.001, video_duration)))
                    elif sp:
                        sp.tick()
                    while time.time() - last_update > spinner_timeout:
                        if sp:
                            sp.tick()
                        last_update = time.time()
            process.wait()
            stderr_thread.join(timeout=3)
            if process.returncode == 0:
                break
            if progress_cb is None:
                status(_(f"Encoder {fb_name} failed."), "WARN")
            tail = "".join(stderr_buf)

    if process.returncode != 0:
        status(f"{_('Error reassembling video:')}\n{tail[-3000:]}", "ERROR")
        sys.exit(1)

    if sp:
        sp.ok(_("Encoding video"))
    return actual_output_path
