# LocallyFPS

LocallyFPS is a desktop application for increasing a video's frame rate locally. It uses RIFE through ncnn/Vulkan when the detected device produces valid frames and falls back to FFmpeg motion interpolation when that path is unavailable or unsafe.

Videos never leave the computer. The graphical interface is maintained in English and neutral Spanish.

## Main features

- Drag-and-drop video list and independent processing queue.
- Target presets for 60, 120 and 240 FPS, plus a custom value.
- Preview, percentage, current stage, remaining queue and cancellation.
- Preserves audio tracks, compatible subtitles, metadata and chapters.
- Handles VFR input, interlaced video, rotation, unusual aspect ratios and HDR-to-SDR conversion.
- Validates generated frames and the final file before reporting success.
- Uses crash-safe checkpoints and never overwrites an existing export.
- Defaults to the localized Downloads directory in `interpoled_locallyfps`; this can be changed in Settings.
- Light and dark themes, with dark as the default.

## Official packages

Release candidates and tagged releases are built for these primary platforms:

| Platform | Package | Architecture |
|---|---|---|
| Linux | AppImage | x86_64 |
| Windows | Installer (`setup.exe`) | x64 |
| macOS | DMG | Apple Silicon / arm64 |

Official packages contain FFmpeg, FFprobe, `rife-ncnn-vulkan` and the RIFE v4.6 model. They do not require a dependency download during the first setup. Exact upstream versions and SHA-256 hashes are pinned in [`packaging/runtime_manifest.json`](packaging/runtime_manifest.json).

Unsigned development candidates may still trigger Windows SmartScreen or macOS Gatekeeper. Production signing and Apple notarization require the project's signing certificates.

## Running a package

### Linux

```bash
chmod +x LocallyFPS-v4.0.0-x86_64.AppImage
./LocallyFPS-v4.0.0-x86_64.AppImage
```

### Windows

Run the installer. Settings, cache and working files are stored in your Windows user profile.

### macOS

Open the DMG, drag LocallyFPS to Applications, then open it from Applications.

## Writable data

Installed packages keep settings and temporary files outside the read-only application:

| Platform | Application data | Cache |
|---|---|---|
| Linux | `$XDG_DATA_HOME/LocallyFPS` | `$XDG_CACHE_HOME/LocallyFPS` |
| Windows | `%LOCALAPPDATA%\LocallyFPS` | `%LOCALAPPDATA%\LocallyFPS\cache` |
| macOS | `~/Library/Application Support/LocallyFPS` | `~/Library/Caches/LocallyFPS` |

Set `LOCALLYFPS_HOME` to choose a custom writable root.

## Source development

Python 3.10 or newer is supported.

```bash
git clone https://github.com/mincmat/LocallyFPS.git
cd LocallyFPS
python -m venv .venv
python -m pip install -r requirements-gui.txt
python locallyfps_gui.py
```

Source checkouts can download missing FFmpeg and RIFE components during initial setup. The legacy command-line interface remains available through `fps_enhancer.py`.

## Tests

```bash
python -m compileall -q .
python -m unittest discover -s tests -v
```

The release workflow additionally runs two tests against every frozen package:

1. Verifies bundled FFmpeg, FFprobe, RIFE, the model and the filters required by the pipeline.
2. Generates a real video, interpolates it from 24 to 48 FPS, validates the frame count and decodes the completed output.

`tools/qualify_media.py` generates a broader compatibility matrix covering landscape, portrait, square, 23.976/25/29.97/30/59.94 FPS, multiple audio tracks, VP9/WebM, HEVC 10-bit, interlaced and VFR input.

## Reproducible packaging

Prepare the verified runtime first:

```bash
python packaging/prepare_runtime.py \
  --platform linux-x86_64 \
  --output build/runtime-linux-x86_64
```

Supported runtime identifiers are `linux-x86_64`, `windows-x86_64` and `macos-arm64`. A runtime must be prepared on the target operating system before freezing the GUI.

Linux AppImage:

```bash
PYTHON=.venv/bin/python \
RUNTIME_DIR="$PWD/build/runtime-linux-x86_64" \
packaging/build_appimage.sh
```

Windows and macOS application bundle:

```bash
python packaging/build_gui.py \
  --runtime-dir build/runtime-PLATFORM \
  --dist-dir dist
```

The `release-candidate` GitHub Actions workflow performs the complete build, package and real-media validation on native runners. Manual runs upload private workflow artifacts; pushing a matching `v*` tag publishes the verified files and `SHA256SUMS.txt`.

## Runtime sources and licensing

LocallyFPS is MIT licensed. Official packages also contain separately licensed third-party executables; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and the license files included beside those binaries.
