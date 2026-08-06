# LocallyFPS v2.0

**AI frame interpolation — 100% local, 100% free.**

LocallyFPS makes your videos smoother by generating new frames between the existing ones using the RIFE AI model. A 30 FPS video becomes 60 FPS — twice the smoothness. All processing happens on your computer. Nothing is uploaded.

---

## How it works

1. **Extracts** every frame of your video as JPEG images (~70% less disk space than PNG).
2. **Interpolates** — the AI (RIFE) looks at two consecutive frames and generates a brand new frame between them.
3. **Reassembles** everything into a new video with the original audio, using the best encoder available on your GPU (NVENC, VAAPI, VideoToolbox, AMF) with automatic fallback to software encoding (libx264, libx265, libopenh264, mpeg4).

---

## What you need

- **A video** (MP4, MKV, AVI, MOV, WEBM, FLV)
- **A GPU with Vulkan support** (NVIDIA, AMD, Intel, Apple Silicon). CPU-only works but is much slower.
- **Python 3** (the launcher uses your system Python or a portable runtime if present)
- **Internet on first run** — ffmpeg, rife-ncnn-vulkan and the AI model are downloaded automatically.
- **Disk space** — extracted frames are JPEG (~200 KB each at 1080p). Plan for 1-5 GB per video depending on resolution and duration.

---

## How to use it

### 1. Download

Go to the **Releases** tab and download the zip for your OS. Each zip is self-contained — extract anywhere.

### 2. First run

| OS | Launcher |
|---|---|
| Linux | `start.sh` |
| macOS | `start.command` |
| Windows | `start.bat` |

The first run asks your language, creates the folder structure, and downloads dependencies. When the main menu appears you're ready.

### 3. Place your videos

Drop videos into `videos/original/` (created next to the launcher).

### 4. Select "Enhance video"

```
   Enhance video
   Settings
   Exit
```

Use arrow keys and Enter to navigate.

### 5. Pick your video

The program lists all videos in `videos/original/` and probes the selected one for metadata.

### 6. Enter target FPS

Type digits directly — no Enter needed on Linux. Press `b` to go back.

| Original | Target | Result |
|---|---|---|
| 30 FPS | 60 | Double frames — much smoother |
| 24 FPS | 60 | Film → smooth video feel |
| 30 FPS | 120 | Ultra-smooth, more processing time |

The target must be higher than the current FPS.

### 7. Wait

A centered progress box shows the pipeline stages in one view:

```
              30fps judder test.webm

              30 fps → 60 fps



         ┌────────────────────────────────────────────────┐
         │            Extracting frames...                │
         │          ######--------------  30.0%           │
         └────────────────────────────────────────────────┘
```

### 8. Done

Enhanced videos are saved in `videos/enhanced/` as `ENHANCED_60FPS_filename.mp4`. Press `b` to return to the menu.

---

## Folder structure

```
LocallyFPS_Linux/
├── start.sh              ← launcher
├── fps_enhancer.py       ← program entry point
├── core/                 ← shared logic (pipeline, wizard, i18n, ...)
├── platform/             ← per-OS code (GPU detection, encoders, input)
│   ├── linux/
│   ├── macos/
│   └── windows/
├── languages/            ← 10 language files
├── videos/
│   ├── original/         ← put your videos here
│   └── enhanced/         ← results appear here
├── deps/
│   ├── ffmpeg/           ← downloaded on first run
│   └── rife/             ← rife-ncnn-vulkan binary
├── models/               ← RIFE AI models (rife-v4.6 default)
├── cache/                ← temporary frames (auto-cleaned)
└── config/               ← config.json
```

Each OS folder is fully self-contained — share the zip and it works.

---

## Settings

From the main menu select **Settings**:

- **Language** — 10 languages: English, Español, Deutsch, Русский, العربية, 中文, 한국어, Français, Português, 日本語
- **Advanced** — Encoder, CRF (quality), ffmpeg preset (speed vs size), RIFE model

---

## CLI mode

```bash
python3 fps_enhancer.py video.mp4 --target-fps 60
```

| Flag | Description |
|---|---|
| `--target-fps N` | Target FPS (default: 60) |
| `--model NAME` | RIFE model (default: rife-v4.6) |
| `--threads L:P:S` | Thread config load:proc:save |
| `--gpu-id N` | Vulkan GPU ID |
| `--uhd` | Force UHD mode for 4K+ |
| `--output PATH` | Custom output path |
| `--yes` | Skip confirmation |
| `--config` | Open settings menu |

---

## Benchmarks

| Video | Resolution | GPU | Time |
|---|---|---|---|
| 30s, 1080p | 1920×1080 | RTX 3060+ | 2-5 min |
| 30s, 1080p | 1920×1080 | Integrated GPU | 10-20 min |
| 5min, 4K | 3840×2160 | Good GPU | 30-60 min |
| 30s, 720p | 1280×720 | CPU only | 20-40 min |

---

## For developers

```
LocallyFPS/
├── core/                    ← shared logic (pipeline, progress, i18n, ...)
├── platform/                ← per-OS code (GPU, encoders, terminal input)
├── LocallyFPS_Linux/        ← self-contained Linux distribution
├── LocallyFPS_macOS/        ← self-contained macOS distribution
├── LocallyFPS_Windows/      ← self-contained Windows distribution
├── tests/                   ← unit tests (23)
├── build_releases.py        ← generates per-OS zips → dist/
└── .github/workflows/       ← CI/CD: auto-build on git tag push
```

- **Tests**: `python3 -m unittest discover -s tests`
- **Build**: `python3 build_releases.py` → zips in `dist/`
- **CI/CD**: pushing a `v*` tag triggers GitHub Actions, builds all 3 zips, uploads to the release.

---

## Tips

- Start with a 10-15 second clip to see results quickly.
- Action scenes and gaming footage benefit the most.
- Anime works well too.
- Slow scenes, interviews, and tutorials won't show much difference.

---

## Troubleshooting

- **"No videos found"** → put videos in `videos/original/`
- **Slow processing** → try a smaller target FPS or shorter clip
- **Encoder errors** → the program auto-falls back through multiple encoders (libx264 → libx265 → libopenh264 → mpeg4)

---

## Why LocallyFPS?

- **100% free** — no subscriptions, no credits
- **100% private** — your video never leaves your computer
- **No watermark**
- **No limits** — process as many videos as you want

---

## License

Free to use.
