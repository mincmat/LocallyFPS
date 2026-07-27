# LocallyFPS ⚡

**LocallyFPS** is a cross-platform tool that uses AI to increase video **FPS (frames per second)** through frame interpolation. It leverages the **RIFE (Real-Time Intermediate Flow Estimation)** model with GPU acceleration via Vulkan. All processing is done **locally** — no cloud dependency.

## How it works

```
Input video → Extract PNG frames → RIFE (AI) → Interpolate frames → Reassemble video → Enhanced video
```

## Features

- **AI interpolation** — Uses RIFE v4.6 (rife-ncnn-vulkan) to generate realistic intermediate frames
- **GPU support** — NVIDIA, AMD, Intel, and Apple Silicon (M1–M5)
- **Interactive wizard** — Arrow-key menu with step-by-step guidance
- **CLI mode** — For automated or batch processing
- **Cross-platform** — Linux, macOS, and Windows
- **Multi-language** — English and Spanish
- **Hardware acceleration** — NVENC, AMF, QSV, VAAPI, VideoToolbox
- **Self-contained** — Auto-downloads ffmpeg and rife-ncnn-vulkan

## Platforms

| Platform | Launcher |
|---|---|
| Linux | `LocallyFPS_Linux/start.sh` |
| macOS | `LocallyFPS_macOS/start.command` |
| Windows | `LocallyFPS_Windows/start.bat` |

## Requirements

- **Python 3.8+**
- **Vulkan-compatible GPU** (recommended for performance)
- **8 GB+ RAM** recommended
- Disk space for temporary frames

## Quick start

```bash
# Linux
cd LocallyFPS_Linux && bash start.sh

# macOS
Double-click LocallyFPS_macOS/start.command

# Windows
Double-click LocallyFPS_Windows/start.bat
```

Follow the interactive wizard:
1. Select the video file
2. Choose the target FPS
3. Adjust settings (optional)
4. Wait for processing!

## CLI (Linux/macOS)

```bash
python3 fps_enhancer.py --input video.mp4 --fps 60 --encoder libx264
```

## Configuration

Edit `config.json` to customize:
- `encoder` — Video codec (libx264, libx265, h264_nvenc, etc.)
- `crf` — Quality (lower = better, recommended 16–20)
- `preset` — Encoding speed (fast, balanced, quality)
- `model` — RIFE model (rife-v4.6, rife-v4, etc.)
- `rife_threads` — RIFE threads (e.g. `2:6:6`)

## Credits

- [RIFE](https://github.com/hzwer/ECCV2022-RIFE) — Frame interpolation algorithm
- [ncnn](https://github.com/Tencent/ncnn) — Neural network inference framework
- [rife-ncnn-vulkan](https://github.com/nihui/rife-ncnn-vulkan) — Vulkan implementation of RIFE

## License

This project is open source.
