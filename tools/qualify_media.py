#!/usr/bin/env python3
"""Generate and validate a compact real-media compatibility matrix.

This is intentionally separate from the fast unit suite.  It invokes the real
FFmpeg binaries, probes every generated file and can run LocallyFPS end to end
on a user-supplied sample with the GPU settings detected on that computer.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import config, init, paths


def _run(command):
    return subprocess.run(command, capture_output=True, text=True, check=True)


def _real_frame_timestamps(video):
    result = _run([
        str(paths.FFPROBE_BIN), "-v", "error", "-select_streams", "v:0",
        "-show_frames", "-show_entries", "frame=best_effort_timestamp_time",
        "-of", "json", str(video),
    ])
    frames = json.loads(result.stdout).get("frames", [])
    timestamps = [
        float(frame["best_effort_timestamp_time"])
        for frame in frames if frame.get("best_effort_timestamp_time") is not None
    ]
    return len(frames), timestamps


def _timestamps_are_vfr(timestamps):
    deltas = [
        current - previous
        for previous, current in zip(timestamps, timestamps[1:])
        if current > previous
    ]
    if len(deltas) < 2:
        return False
    baseline = sorted(deltas)[len(deltas) // 2]
    # Millisecond container time bases naturally alternate (for example,
    # 33/34 ms at 29.97 fps); that quantisation is not variable frame rate.
    tolerance = max(0.002, baseline * 0.08)
    return any(abs(delta - baseline) > tolerance for delta in deltas)


def _generate_matrix(directory):
    ffmpeg = str(paths.FFMPEG_BIN)
    common = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    cases = {
        "landscape_24_audio.mp4": [
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        ],
        "portrait_25.mov": [
            "-f", "lavfi", "-i", "testsrc2=size=180x320:rate=25:duration=1",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        ],
        "square_2997_two_audio.mkv": [
            "-f", "lavfi", "-i", "testsrc2=size=240x240:rate=30000/1001:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=880:duration=1",
            "-map", "0:v", "-map", "1:a", "-map", "2:a", "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        ],
        "webm_30.webm": [
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=330:duration=1", "-shortest",
            "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8",
            "-c:a", "libopus",
        ],
        "hevc_10bit.mkv": [
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=1",
            "-an", "-c:v", "libx265", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p10le", "-x265-params", "log-level=error",
        ],
        "interlaced_25.mp4": [
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=50:duration=1",
            "-vf", "tinterlace=mode=interleave_top", "-flags", "+ilme+ildct",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        ],
        "vfr.mkv": [
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=1.5",
            "-vf", "select=if(lt(t\\,0.75)\\,not(mod(n\\,2))\\,not(mod(n\\,3)))",
            "-fps_mode", "vfr", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        ],
        "high_rate_5994.mp4": [
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=60000/1001:duration=1",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        ],
    }
    outputs = []
    for name, arguments in cases.items():
        output = directory / name
        _run(common + arguments + [str(output)])
        outputs.append(output)
    return outputs


def _validate_input(video):
    from core.probe import probe_video_file

    info = probe_video_file(video)
    if not info:
        raise RuntimeError(f"Could not probe {video.name}")
    _run([
        str(paths.FFMPEG_BIN), "-hide_banner", "-loglevel", "error",
        "-i", str(video), "-map", "0:v:0", "-f", "null", "-",
    ])
    frame_count, timestamps = _real_frame_timestamps(video)
    return {
        "name": video.name,
        "codec": info.get("codec"),
        "size": [info.get("display_width"), info.get("display_height")],
        "fps": info.get("fps"),
        "duration": info.get("duration"),
        "frames": frame_count,
        "audio_tracks": info.get("audio_tracks", 0),
        "field_order": info.get("field_order"),
        "pixel_format": info.get("pix_fmt"),
        "vfr": _timestamps_are_vfr(timestamps),
    }


def _qualify_sample(sample, directory):
    from core.gpu import choose_gpu_settings
    from core.pipeline import run_pipeline
    from core.probe import probe_video_file

    info = probe_video_file(sample)
    if not info:
        raise RuntimeError(f"Could not probe sample: {sample}")
    target = 60.0 if info["fps"] < 60 else min(120.0, info["fps"] * 2)
    gpu = choose_gpu_settings(info["display_width"], info["display_height"])
    output = directory / f"qualified_{int(round(target))}fps.mkv"
    old_cache = paths.CACHE_DIR
    paths.CACHE_DIR = directory / "cache"
    started = time.monotonic()
    try:
        ok = run_pipeline(
            info, target, output, gpu, interactive=False,
            progress_cb=lambda _fraction, _label=None: None,
        )
    finally:
        paths.CACHE_DIR = old_cache
    if not ok:
        raise RuntimeError("The end-to-end sample failed")
    validated = _validate_input(output)
    return {
        "source": str(sample), "target_fps": target, "output": str(output),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "gpu": gpu, "validated_output": validated,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--sample", type=Path)
    args = parser.parse_args()

    init(ROOT)
    config.load_config()
    paths.ensure_dirs()
    work = args.work_dir.expanduser().resolve()
    inputs = work / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    matrix = [_validate_input(path) for path in _generate_matrix(inputs)]
    by_name = {item["name"]: item for item in matrix}
    required = {
        "landscape_24_audio.mp4": lambda item: item["audio_tracks"] == 1,
        "portrait_25.mov": lambda item: item["size"] == [180, 320],
        "square_2997_two_audio.mkv": lambda item: item["audio_tracks"] == 2,
        "webm_30.webm": lambda item: item["codec"] == "vp9",
        "hevc_10bit.mkv": lambda item: item["pixel_format"] == "yuv420p10le",
        "interlaced_25.mp4": lambda item: item["field_order"] != "progressive",
        "vfr.mkv": lambda item: item["vfr"],
        "high_rate_5994.mp4": lambda item: item["fps"] > 59,
    }
    failed = [name for name, check in required.items() if not check(by_name[name])]
    if failed:
        raise RuntimeError("Media qualification failed: " + ", ".join(failed))
    report = {"generated_inputs": matrix}
    if args.sample:
        report["end_to_end"] = _qualify_sample(args.sample.expanduser().resolve(), work)
    report_path = work / "qualification.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
