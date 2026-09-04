import json
import subprocess

from . import paths
from .colors import Color
from .console import status
from .i18n import _
from .utils import format_duration, format_fps, human_size


def _parse_fps(rate_str):
    try:
        num, den = rate_str.split("/")
        return float(num) / float(den) if float(den) != 0 else 0.0
    except (ValueError, AttributeError, ZeroDivisionError):
        return 0.0


def _count_frames_real(video_path):
    cmd = [
        str(paths.FFPROBE_BIN), "-v", "error",
        "-select_streams", "v:0",
        "-count_frames",
        "-show_entries", "stream=nb_read_frames",
        "-of", "csv=p=0",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        return 0
    try:
        return int(result.stdout.strip())
    except (ValueError, TypeError):
        return 0
    try:
        return int(result.stdout.strip())
    except (ValueError, TypeError):
        return 0


def probe_video_file(path):
    if not path.is_file():
        return None

    cmd = [
        str(paths.FFPROBE_BIN), "-v", "error",
        "-select_streams", "v:0",
        "-show_format", "-show_streams",
        "-of", "json",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        status(_("ffmpeg/ffprobe not found. Install dependencies first."), "ERROR")
        return None
    if result.returncode != 0:
        return None
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        status(_("ffmpeg/ffprobe not found. Install dependencies first."), "ERROR")
        return None
    if result.returncode != 0:
        return None

    try:
        data = json.loads(result.stdout)
        streams = data.get("streams") or []
        if not streams:
            return None
        stream = streams[0]
        fmt = data.get("format", {})

        fps = _parse_fps(stream.get("r_frame_rate", ""))
        if fps <= 0:
            fps = _parse_fps(stream.get("avg_frame_rate", ""))
        if fps <= 0:
            fps = 30.0
            status(_("Detected FPS as 0 (VFR or unusual format). Assuming 30 fps."), "WARN")

        try:
            nb = stream.get("nb_frames")
            if nb and nb != "N/A":
                frame_count = int(nb)
            else:
                duration = float(fmt.get("duration", 0.0) or 0.0)
                frame_count = int(fps * duration) if duration > 0 else 0
        except (ValueError, TypeError):
            frame_count = 0

        duration = float(fmt.get("duration", 0.0) or 0.0)
        if frame_count <= 0 and duration > 0:
            frame_count = int(fps * duration)
        if frame_count <= 0:
            status(_("Counting frames (this may take a while)..."), "INFO")
            frame_count = _count_frames_real(path)
            if frame_count > 0:
                fps = frame_count / duration if duration > 0 else fps

        audio_cmd = [
            str(paths.FFPROBE_BIN), "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=index", "-of", "csv=p=0", str(path),
        ]
        try:
            audio_result = subprocess.run(audio_cmd, capture_output=True, text=True)
        except FileNotFoundError:
            audio_tracks = []
        else:
            audio_tracks = [t for t in audio_result.stdout.strip().split("\n") if t.strip()]

        return {
            "path": path,
            "extension": path.suffix.lower() or "(no extension)",
            "container": fmt.get("format_long_name", "unknown"),
            "codec": stream.get("codec_name", "unknown"),
            "width": int(stream.get("width", 0)),
            "height": int(stream.get("height", 0)),
            "fps": fps,
            "frame_count": frame_count,
            "duration": duration,
            "size_bytes": int(fmt.get("size", 0) or 0),
            "has_audio": len(audio_tracks) > 0,
            "audio_tracks": len(audio_tracks),
        }
    except (KeyError, IndexError, ValueError, json.JSONDecodeError):
        return None


def print_video_metadata(info):
    print()
    status(f"{_('Valid video:')} {Color.bold(info['path'].name)}", "OK")
    print(f"    {Color.dim(_('Container'))}  : {info['container']} ({info['extension']})")
    print(f"    {Color.dim(_('Codec'))}       : {info['codec']}")
    w = info['width']
    h = info['height']
    print(f"    {Color.dim(_('Resolution'))}  : {Color.bold(f'{w}x{h}')}")
    print(f"    {Color.dim(_('Current FPS'))}  : {format_fps(info['fps'])}")
    print(f"    {Color.dim(_('Duration'))}    : {format_duration(info['duration'])}")
    print(f"    {Color.dim(_('Size'))}      : {human_size(info['size_bytes'])}")
    audio_str = f"{_('yes')} ({info['audio_tracks']} {_('tracks')})" if info['has_audio'] else _("no")
    print(f"    {Color.dim(_('Audio'))}       : {audio_str}")
    print()
