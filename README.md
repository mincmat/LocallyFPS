# LocallyFPS ⚡

**Make your videos look smoother with AI frame interpolation.**

LocallyFPS takes a video and creates new frames between the existing ones using artificial intelligence (RIFE model). A 30 FPS video becomes 60 FPS — twice the smoothness.

All processing happens **on your computer**. Nothing is uploaded to the cloud.

---

## How it works

1. Extracts every frame of your video as images (PNG files).
2. Uses AI (RIFE) to generate **new in-between frames** — for example, it looks at frame 1 and frame 2, then creates a brand new frame 1.5 that fits naturally between them.
3. Reassembles everything into a new video file with the original audio.

---

## What you need

- **A video file** (MP4, MKV, AVI, MOV, WEBM, or FLV)
- **A graphics card with Vulkan support** (most NVIDIA, AMD, Intel, and Apple Silicon GPUs work). It can run without one but will be much slower.
- **Python 3**
- **Patience** — processing video takes time. A short clip can take minutes; longer videos can take hours.

---

## How to use it

### 1. Download your version

Go to the **Releases** tab and download the zip for your operating system (e.g. `LocallyFPS_Linux.zip`), or clone/download the whole repo and use your OS folder. Each release zip is self-contained — you don't need anything else.

### 2. Place your video

Put your video file inside the `videos/original/` folder (create it if missing).

### 3. Run the launcher

| Your OS | File to run |
|---|---|
| Linux | `start.sh` (double-click or run in terminal) |
| macOS | `start.command` (double-click) |
| Windows | `start.bat` (double-click) |

The first time you run it, it will:
1. Ask you to pick a language (English or Spanish).
2. Install dependencies like `ffmpeg` and `rife-ncnn-vulkan` automatically.

### 3. Select "Enhance video"

```
  ▸ Enhance video
    Settings
    Exit
```

Use **↑** and **↓** then **Enter** to select.

### 4. Pick your video

The program shows all videos found in `videos/original/`. Select the one you want.

### 5. Enter the target FPS

Type a number and press Enter. Common options:

| Original FPS | Target FPS | Result |
|---|---|---|
| 30 FPS | 60 | Doubles the frames — much smoother |
| 24 FPS (film) | 60 | Makes movies look like modern video |
| 30 FPS | 120 | Very smooth, needs more processing |

### 6. Confirm and wait

The program will show a summary and ask for confirmation. Then it starts working:

```
Extracting frames...  ████████████████░░░░  (progress bar)
Interpolating frames.. ████████████████████  (progress bar)
Encoding video...     [✓]
```

### 7. Find your enhanced video

The result is saved in `videos/enhanced/` with a name like `ENHANCED_60FPS_filename.mp4`.

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

From the main menu, select **Settings** to change:

- **Language** — Switch between English and Spanish
- **Encoder** — Video codec (`libx264`, `libx265`, `h264_nvenc` for NVIDIA, etc.)
- **CRF** — Quality (lower = better quality, bigger file). Default: 16, Range: 0-51
- **ffmpeg preset** — Encoding speed vs file size (`fast`, `medium`, `slow`, etc.)
- **Model** — RIFE AI model version (`rife-v4.6` is the default)

These are already set to sensible defaults — you can ignore them and it works fine.

---

## CLI mode (advanced)

```bash
python3 fps_enhancer.py --input videos/original/myvideo.mp4 --target-fps 60
```

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
- **Build release zips**: `python3 build_releases.py` (outputs to `dist/`)
- Each release zip bundles the wrapper, `core/`, `platform/`, languages and launcher — fully self-contained for its OS.

---

## Tips

- **Test with a short clip first** (10-15 seconds) to see if you like the result.
- **Gaming videos and action scenes** benefit the most from interpolation.
- **Anime** also works well.
- **Tutorials, interviews, or slow scenes** won't show much difference.

---

## Why use this instead of an online tool?

- **100% free** — no subscriptions or credits
- **100% private** — your video never leaves your computer
- **No watermark** — clean output
- **No limits** — process as many videos as you want

---

## License

Free to use.
