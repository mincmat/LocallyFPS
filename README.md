# LocallyFPS

Upscale your video FPS with AI, right on your machine. No cloud uploads.

Uses RIFE for frame interpolation and ffmpeg for encoding. Supports Linux, Windows, and macOS.

## What it does

- Extracts frames from your video with ffmpeg
- RIFE generates intermediate frames with AI (e.g., 24fps to 60fps)
- ffmpeg reassembles everything with audio

## Requirements

- Vulkan-capable GPU (NVIDIA, AMD, Intel)
- Python 3.8+
- ffmpeg (auto-downloaded if missing)

## Quick start

```bash
# Linux/macOS
./start.sh

# Windows
start.bat
```

Follow the menu: pick your video, choose target FPS, done.

### CLI

```bash
python fps_enhancer.py video.mp4 --target-fps 60
```

## Languages

English, Spanish, German, French, Portuguese, Russian, Arabic, Chinese, Japanese, Korean.

## License

MIT
