# LocallyFPS

AI-powered video frame interpolation — run entirely on your machine.

LocallyFPS uses the **RIFE** (Real-Time Intermediate Flow Estimation) AI model, with a safe FFmpeg optical-flow fallback, to generate smooth, high-framerate video from FFmpeg-decodable sources. No cloud services, no subscriptions, no data leaving your PC.

<p align="center">
  <strong>24fps → 60fps</strong> · <strong>30fps → 120fps</strong> · <strong>any → any</strong>
</p>

---

## Features

- **AI frame interpolation** using RIFE v4.6 via ncnn + Vulkan
- **H.265/HEVC input support** with automatic pixel format conversion
- **HDR tone mapping** — HDR10/HLG content is tone-mapped to SDR during extraction
- **Correct color handling** — SDR metadata is preserved; tone-mapped HDR output is correctly tagged as SDR BT.709
- **Audio and subtitle preservation** — all audio tracks and compatible subtitles are retained; MKV is selected when needed
- **VFR normalization** — variable-timestamp sources are converted to a stable CFR timeline before interpolation
- **Automatic deinterlacing and rotation-aware sizing** for broadcast and phone footage
- **Scene-cut protection** — AI-generated blends across shot changes are replaced automatically
- **Hardware-accelerated encoding** — NVENC, VAAPI, QSV, VideoToolbox with automatic fallback
- **Validated GPU interpolation** — corrupt or duplicated Vulkan output is detected before a full run
- **Safe optical-flow fallback** — incompatible GPU drivers automatically use motion-compensated FFmpeg interpolation
- **Cross-platform** — Linux, Windows, macOS
- **10 languages** — English, Español, Deutsch, Français, Português, Русский, العربية, 中文, 日本語, 한국어
- **Interactive TUI** with raw keyboard input on Linux/macOS
- **CLI mode** for scripting and batch processing
- **One-command batch mode** with automatic FPS selection and safe per-file continuation
- **Guided dependency setup** — ffmpeg and RIFE are auto-downloaded on Linux/Windows; macOS uses Homebrew's feature-complete FFmpeg build
- **Encoder fallback chain** — if your preferred encoder fails, it tries alternatives automatically
- **Atomic validated exports** — existing outputs survive failures; FPS, frames, duration, audio and decoding are checked
- **SHA-256 verification** for application updates and local dependency integrity

---

## Quick Start

### Download

Grab the latest release for your OS from [Releases](https://github.com/mincmat/LocallyFPS/releases).

### Run

```bash
# Linux
./start.sh

# Windows
start.bat

# macOS (double-click in Finder, or run from Terminal)
./start.command
```

On Linux and Windows, the first run downloads ffmpeg and the RIFE model automatically.
On macOS, install the feature-complete FFmpeg build once with
`brew install ffmpeg-full`; LocallyFPS detects its keg-only path automatically.

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
python fps_enhancer.py input.mp4 --auto-fps
python fps_enhancer.py --batch videos/original --auto-fps --yes
python fps_enhancer.py input.mkv --target-fps 120 --model rife-v4.6
python fps_enhancer.py input.mp4 --target-fps 60 --output result.mp4
```

Run `python fps_enhancer.py --help` for all options.

In the interactive FPS screen, press Enter to accept the automatically recommended target.

---

## How It Works

```
Input video (H.264, H.265, etc.)
        │
        ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│    ffmpeg    │───▶│  RIFE (AI)   │───▶│    ffmpeg    │
│   extract    │    │ interpolate  │    │   encode     │
│  PNG frames  │    │  new frames  │    │  + audio     │
└──────────────┘    └──────────────┘    └──────────────┘
  .png frames         .png frames       .mp4 / .mkv
```

1. **Extract** — ffmpeg pulls every frame as lossless PNG (with automatic pixel format conversion for H.265/HEVC)
2. **Interpolate** — RIFE generates new frames between existing ones using AI
3. **Reassemble** — ffmpeg encodes the result back into a video with audio and color metadata

---

## Requirements

| Component | Details |
|-----------|---------|
| **GPU** | Optional. Vulkan enables RIFE; FFmpeg optical flow is used when RIFE is unavailable or unsafe |
| **Vulkan driver** | NVIDIA proprietary recommended. Open-source drivers work too. |
| **Python** | 3.10+ (only stdlib + optional `tqdm`) |
| **Disk space** | Varies — the app estimates and warns before processing |
| **ffmpeg** | Auto-downloaded on Linux/Windows; on macOS run `brew install ffmpeg-full` (required for safe HDR tone mapping) |

### GPU Support

| Vendor | Encoding | Notes |
|--------|----------|-------|
| NVIDIA | NVENC | Best performance |
| AMD | VAAPI / AMF (Windows) | Good performance |
| Intel | QSV / VAAPI | Works well for integrated GPUs |
| Apple | VideoToolbox (macOS) | Optimized for M-series chips |

### CPU/GPU Selection

LocallyFPS automatically selects between GPU and CPU based on your hardware:

| GPU Type | Resolution | Mode |
|----------|-----------|------|
| Dedicated (RTX, GTX, RX) | Any | GPU |
| Integrated (Intel, AMD) | < 1440p | GPU |
| Integrated (Intel, AMD) | ≥ 1440p | CPU |

Integrated GPUs use CPU for high resolutions because they share system RAM and lack the VRAM needed for large frame buffers.

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
  "video_preset": "custom"
}
```

You can change these from the **Settings** menu or edit the file directly.

### Key Settings

- **encoder** — Video encoder. `libx264` for CPU, `h264_nvenc` for NVIDIA GPU, etc.
- **crf** — Quality (lower = better, 0 = lossless). 16-23 is a good range.
- **preset** — Encoding speed vs. quality tradeoff.
- **model** — RIFE model version. `rife-v4.6` is the default and recommended.

---

## Project Structure

```
LocallyFPS/
├── fps_enhancer.py        # Entry point
├── update.py              # Standalone updater
├── start.sh / start.bat   # Launchers
├── core/                  # Application logic
│   ├── pipeline.py        # Orchestrates extract -> interpolate -> encode
│   ├── extract.py         # ffmpeg frame extraction (H.265/HDR support)
│   ├── interpolate.py     # RIFE wrapper (GPU/CPU selection)
│   ├── reassemble.py      # ffmpeg encoding with fallback + color metadata
│   ├── probe.py           # Video metadata extraction
│   ├── manifest.py        # SHA-256 dependency verification
│   ├── progress.py        # Progress bars and spinners
│   ├── wizard.py          # Interactive TUI
│   ├── deps.py            # Dependency download and install
│   ├── models.py          # RIFE model management
│   └── ...
├── platform/              # OS-specific code
│   ├── linux/             # lspci, vulkaninfo, termios
│   ├── windows/           # PowerShell, NVENC/QSV
│   └── macos/             # system_profiler, VideoToolbox
├── languages/             # Translation files (10 languages)
├── models/                # RIFE AI models
├── deps/                  # ffmpeg and RIFE binaries
└── videos/
    ├── original/          # Drop your videos here
    └── enhanced/          # Output goes here
```

---

## Supported Formats

| Input | Output |
|-------|--------|
| H.264 (AVC) | H.264 (AVC) |
| H.265 (HEVC) | H.265 (HEVC) |
| VP8/VP9 | H.264/H.265 |
| MPEG-4 | H.264/H.265 |
| AVI, MKV, MOV, WebM, FLV, WMV, MPEG-TS, MTS/M2TS, OGV, 3GP, VOB and more | MP4, MKV |

H.265/HEVC input is fully supported with automatic:
- Pixel format conversion (10-bit video to 8-bit RGB for RIFE-compatible PNG extraction)
- HDR to SDR tone mapping (PQ/HLG transfer functions)
- Correct SDR BT.709 tagging after HDR tone mapping

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
- If you have an integrated GPU, LocallyFPS will automatically use CPU for 2K+ resolutions

**Out of disk space?**
The app conservatively reserves approximately raw RGB size for both the extracted and generated PNG sequences, plus safety overhead. Highly detailed or noisy videos can require very large temporary storage.

**Model download fails?**
The RIFE model (~400MB) is downloaded from GitHub Releases. Check your internet connection or download it manually and place it in `models/rife-v4.6/`.

**H.265/HEVC video looks wrong?**
LocallyFPS automatically handles H.265 pixel format conversion. If you still see issues, try re-encoding the input to H.264 first with `ffmpeg -i input.mp4 -c:v libx264 -crf 18 output.mp4`.

**Colors look washed out or oversaturated?**
This can happen with HDR content. LocallyFPS performs automatic HDR tone mapping, but if the result looks wrong, try a different encoder or CRF value.

---

## Building from Source

```bash
git clone https://github.com/mincmat/LocallyFPS.git
cd LocallyFPS
python fps_enhancer.py
```

No `pip install` needed — the project uses only Python stdlib.

## Testing

```bash
python -m unittest discover -s tests -v
```

Every push and pull request is tested on Linux, Windows and macOS with GitHub Actions.

---

## License

MIT
