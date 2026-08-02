# LocallyFPS ⚡

**Make your videos look smoother with AI frame interpolation.**

LocallyFPS takes a video and creates new frames between the existing ones using artificial intelligence (RIFE model). A 30 FPS video becomes 60 FPS — twice the smoothness.

All processing happens **on your computer**. Nothing is uploaded to the cloud.

---

## How it works

1. **Extracts** every frame of your video as images (PNG files).
2. **Interpolates**: AI (RIFE) looks at two consecutive frames and generates a brand new frame between them. For 60 FPS from a 30 FPS video, it creates one new frame between each pair of originals.
3. **Reassembles** everything into a new video file with the original audio, using the best encoder available on your GPU (falling back to software encoding if needed).

---

## What you need

- **A video file** (MP4, MKV, AVI, MOV, WEBM, or FLV)
- **A graphics card with Vulkan support** (most NVIDIA, AMD, Intel, and Apple Silicon GPUs work). It can run without one but will be much slower.
- **Python 3** (the launcher tries a portable runtime if present, otherwise uses your system Python)
- **Internet on the first run only** — dependencies (ffmpeg, RIFE, the AI model) are downloaded automatically once.
- **Patience** — processing video takes time. A short clip can take minutes; longer videos can take hours.

---

## How to use it

### 1. Download your version

Go to the **Releases** tab and download the zip for your operating system (e.g. `LocallyFPS_Linux.zip`). Each release zip is self-contained — you don't need anything else. Extract it anywhere you like.

### 2. Run the launcher — first time

| Your OS | File to run |
|---|---|
| Linux | `start.sh` (double-click or run in terminal) |
| macOS | `start.command` (double-click) |
| Windows | `start.bat` (double-click) |

**Important: run the launcher first.** The first time it runs it creates the folder structure (`videos/`, `deps/`, `models/`, ...), asks you to pick a language (English or Spanish), and downloads the dependencies (ffmpeg and rife-ncnn-vulkan) plus the AI model automatically. When you see the main menu, the program is ready.

### 3. Place your videos

Drop your video files into the `videos/original/` folder (it's created automatically next to the launcher). Supported: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.flv`.

> Tip: if the program says *"No videos found in videos/original/"*, just put your videos there and run the launcher again.

### 4. Run the launcher again and select "Enhance video"

```
  ▸ Enhance video
    Settings
    Exit
```

Use **↑** and **↓** then **Enter** to select.

### 5. Pick your video

The program shows all videos found in `videos/original/`, then verifies the file and shows its details (FPS, resolution, duration, size).

### 6. Enter the target FPS

Type a number and press Enter. Common options:

| Original FPS | Target FPS | Result |
|---|---|---|
| 30 FPS | 60 | Doubles the frames — much smoother |
| 24 FPS (film) | 60 | Makes movies look like modern video |
| 30 FPS | 120 | Very smooth, needs more processing |

The target must be higher than the video's current FPS.

### 7. Confirm and wait

The program shows a summary and asks for confirmation. Then it starts working:

```
Checking system dependencies...   [✓]
Extracting frames...              ████████████████░░░░  (progress bar)
Interpolating frames...           ████████████████████  (progress bar)
Encoding video...                 [✓]
```

### 8. Find your enhanced video

The result is saved in `videos/enhanced/` with a name like `ENHANCED_60FPS_filename.mp4`.

---

## What happens inside

Here's the folder structure the launcher creates next to itself:

```
LocallyFPS_Linux/
├── start.sh              ← launcher: creates folders, picks Python, starts the app
├── fps_enhancer.py       ← the program
├── videos/
│   ├── original/         ← put your videos here
│   └── enhanced/         ← results appear here
├── deps/
│   ├── ffmpeg/           ← ffmpeg + ffprobe (downloaded on first run)
│   └── rife/             ← rife-ncnn-vulkan (downloaded on first run)
├── models/               ← RIFE AI models (rife-v4.6 by default)
├── cache/                ← temporary frames (cleaned up automatically)
├── config/               ← your settings (settings.json)
└── runtime/              ← (optional) portable Python, if you add one
```

- **First run** → asks your language and downloads anything missing (it only downloads what it can't find on your system — if you already have `ffmpeg` installed, it uses it).
- **Temporary files** → extracted and interpolated frames live in `cache/` while processing and are cleaned up when done, even if you interrupt the program.
- **The encoder** is chosen automatically for your GPU (NVENC for NVIDIA, VAAPI for AMD/Intel, VideoToolbox for Apple Silicon, AMF for Windows AMD...). If a hardware encoder fails, the program falls back to software encoding (`libx264`) automatically so you never lose hours of work.

---

## How long will it take?

| Video | Resolution | GPU | Approximate time |
|---|---|---|---|
| 30 seconds, 1080p | 1920x1080 | Good GPU (RTX 3060+) | 2-5 minutes |
| 30 seconds, 1080p | 1920x1080 | Integrated GPU | 10-20 minutes |
| 5 minutes, 4K | 3840x2160 | Good GPU | 30-60 minutes |
| 30 seconds, 720p | 1280x720 | No GPU (CPU only) | 20-40 minutes |

---

## Settings menu (optional)

From the main menu, select **Settings**. The basic menu has **Language**; press **Advanced ▸** for:

- **Encoder** — Video codec (`libx264`, `libx265`, `h264_nvenc` for NVIDIA, `h264_vaapi` for AMD/Intel Linux, `h264_videotoolbox` for Apple Silicon, etc.)
- **CRF** — Quality (lower = better quality, bigger file). Default: 20, Range: 0-51
- **ffmpeg preset** — Encoding speed vs file size (`fast`, `medium`, `slow`, etc.)
- **Model** — RIFE AI model version (`rife-v4.6` is the default; others are downloaded on demand)

These are already set to sensible defaults — you can ignore them and it works fine.

---

## CLI mode (advanced)

```bash
python3 fps_enhancer.py videos/original/myvideo.mp4 --target-fps 60
```

Useful flags:

| Flag | What it does |
|---|---|
| `--model NAME` | Use a specific RIFE model (default: rife-v4.6) |
| `--threads L:P:S` | Thread counts load:proc:save (default: auto based on GPU) |
| `--gpu-id N` | Use a specific Vulkan GPU (default: auto) |
| `--uhd` | Force UHD mode (recommended for 4K+) |
| `--output PATH` | Custom output path (default: `ENHANCED_60FPS_filename.mp4`) |
| `--yes` | Skip interactive confirmation |
| `--config` | Open the settings menu |

---

## For developers

The project uses a shared `core/` module with platform-specific code in `platform/`.

```
LocallyFPS/
├── core/                    # Shared logic (config, pipeline, wizard, ...)
├── platform/                # Per-OS code (GPU detection, encoders, terminal input)
│   ├── linux/
│   ├── macos/
│   └── windows/
├── LocallyFPS_Linux/        # Thin wrapper + launcher
├── LocallyFPS_macOS/        # Thin wrapper + launcher
├── LocallyFPS_Windows/      # Thin wrapper + launcher
├── tests/                   # Unit tests
└── build_releases.py        # Builds self-contained per-OS release zips
```

- **Run the tests**: `python3 -m unittest discover -s tests`
- **Build release zips**: `python3 build_releases.py linux` (or `macos` / `windows`) — outputs to `dist/`
- Each release zip bundles the wrapper, `core/`, `platform/`, languages and launcher — fully self-contained for its OS.

---

## Tips

- **Test with a short clip first** (10-15 seconds) to see if you like the result.
- **Gaming videos and action scenes** benefit the most from interpolation.
- **Anime** also works well.
- **Tutorials, interviews, or slow scenes** won't show much difference.

---

## Troubleshooting

- **"No videos found in videos/original/"** → put your videos in `videos/original/` and run the launcher again.
- **Dependencies are downloaded on every run** → they're saved in `deps/` and `models/` next to the launcher; keep the whole folder together.
- **Slow processing** → the program is using software rendering or a weak GPU. Try a smaller target FPS or a shorter clip.

---

## Why use this instead of an online tool?

- **100% free** — no subscriptions or credits
- **100% private** — your video never leaves your computer
- **No watermark** — clean output
- **No limits** — process as many videos as you want

---

## License

Free to use.
