# LocallyFPS

AI-powered video frame interpolation — run entirely on your machine.

LocallyFPS uses the **RIFE** (Real-Time Intermediate Flow Estimation) AI model to generate smooth, high-framerate video from any source. No cloud services, no subscriptions, no data leaving your PC.

<p align="center">
  <strong>24fps → 60fps</strong> · <strong>30fps → 120fps</strong> · <strong>any → any</strong>
</p>

---

## Features

- **AI frame interpolation** using RIFE v4.6 via ncnn + Vulkan
- **Hardware-accelerated encoding** — NVENC, VAAPI, QSV, VideoToolbox with automatic fallback
- **Cross-platform** — Linux, Windows, macOS
- **10 languages** — English, Español, Deutsch, Français, Português, Русский, العربية, 中文, 日本語, 한국어
- **Interactive TUI** with raw keyboard input on Linux
- **CLI mode** for scripting and batch processing
- **Zero dependencies to install manually** — ffmpeg and RIFE are auto-downloaded on first run
- **Encoder fallback chain** — if your preferred encoder fails, it tries alternatives automatically

---

## Quick Start

### Download

Grab the latest release for your OS from [Releases](https://github.com/mincmat/LocallyFPS/releases).

### Run

```bash
# Linux / macOS
./start.sh

# Windows
start.bat
```

That's it. The first run will download ffmpeg and the RIFE model automatically.

### Interactive Mode

You'll see a menu. Pick **Enhance video**, select your file from `videos/original/`, choose your target FPS, and go.

```
┌────────────────────────────────────────────────
│              Extracting frames...              │
│          ##########----------  25.0%           │
└────────────────────────────────────────────────
```

### CLI Mode

```bash
python fps_enhancer.py input.mp4 --target-fps 60
python fps_enhancer.py input.mkv --target-fps 120 --model rife-v4.6
python fps_enhancer.py input.mp4 --target-fps 60 --output result.mp4
```

Run `python fps_enhancer.py --help` for all options.

---

## How It Works

```
Input video
    │
    ▼
┌──────────┐    ──────────────┐    ┌───────────┐    ┌────────────
│  ffmpeg  │───▶│  RIFE (AI)   │───▶│  ffmpeg   │───▶│  Output    │
│ extract  │    │ interpolate  │    │  encode   │    │  video     │
│  frames  │    │   frames     │    │  + audio  │    │            │
└──────────┘    ──────────────┘    └───────────┘    └────────────┘
  .jpg frames      .png frames       .mp4 / .mkv
```

1. **Extract** — ffmpeg pulls every frame as JPEG
2. **Interpolate** — RIFE generates new frames between existing ones using AI
3. **Reassemble** — ffmpeg encodes the result back into a video with audio

---

## Requirements

| Component | Details |
|-----------|---------|
| **GPU** | Any Vulkan-capable GPU (NVIDIA, AMD, Intel) |
| **Vulkan driver** | NVIDIA proprietary recommended. Open-source drivers work too. |
| **Python** | 3.8+ (only stdlib + optional `tqdm`) |
| **Disk space** | Varies — the app estimates and warns before processing |
| **ffmpeg** | Auto-downloaded if not found on your system |

### GPU Support

| Vendor | Encoding | Notes |
|--------|----------|-------|
| NVIDIA | NVENC | Best performance |
| AMD | VAAPI / AMF (Windows) | Good performance |
| Intel | QSV / VAAPI | Works well for integrated GPUs |
| Apple | VideoToolbox (macOS) | Optimized for M-series chips |

---

## Configuration

Settings are stored in `config/settings.json`:

```json
{
  "language": "en",
  "encoder": "libx264",
  "crf": 16,
  "preset": "fast",
  "model": "rife-v4.6",
  "video_preset": "custom",
  "rife_threads": "2:6:6"
}
```

You can change these from the **Settings** menu or edit the file directly.

### Key settings

- **encoder** — Video encoder. `libx264` for CPU, `h264_nvenc` for NVIDIA GPU, etc.
- **crf** — Quality (lower = better, 0 = lossless). 16-23 is a good range.
- **preset** — Encoding speed vs. quality tradeoff.
- **model** — RIFE model version. `rife-v4.6` is the default and recommended.
- **rife_threads** — Thread allocation for RIFE (load:process:save).

---

## Project Structure

```
LocallyFPS/
├── fps_enhancer.py      # Entry point
├── start.sh / start.bat # Launchers
├── core/                # Application logic
│   ├── pipeline.py      # Orchestrates extract → interpolate → encode
│   ├── progress.py      # Progress bars and spinners
│   ├── wizard.py        # Interactive TUI
│   ├── extract.py       # ffmpeg frame extraction
│   ├── interpolate.py   # RIFE wrapper
│   ├── reassemble.py    # ffmpeg encoding with fallback
│   └── ...
├── platform/            # OS-specific code
│   ├── linux/
│   ├── windows/
│   └── macos/
├── languages/           # Translation files
├── models/              # RIFE AI models
├── deps/                # ffmpeg and RIFE binaries
└── videos/
    ├── original/        # Drop your videos here
    └── enhanced/        # Output goes here
```

---

## Troubleshooting

**Progress bar not showing?**
Make sure you're running in a terminal that supports ANSI colors. Most modern terminals do.

**"No Vulkan device found"**
Install or update your GPU's Vulkan driver. On Linux: `vulkaninfo` should list your GPU.

**Slow processing?**
- Use a hardware encoder (NVENC/VAAPI/QSV) instead of libx264
- Lower the target FPS
- Reduce resolution

**Out of disk space?**
The app estimates required space before starting. Extraction needs roughly `width × height × 3 × frames × 0.4` bytes.

**Model download fails?**
The RIFE model (~400MB) is downloaded from GitHub Releases. Check your internet connection or download it manually and place it in `models/rife-v4.6/`.

---

## Building from Source

```bash
git clone https://github.com/mincmat/LocallyFPS.git
cd LocallyFPS
python fps_enhancer.py
```

No `pip install` needed — the project uses only Python stdlib.

---

## License

MIT
