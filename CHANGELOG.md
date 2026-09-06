# Changelog

## 3.1.1 - 2026-09-05

- Added a preflight check that detects corrupt or duplicated RIFE output before processing a full video.
- Added automatic motion-compensated FFmpeg interpolation when a Vulkan driver produces invalid RIFE frames.
- Preserved the exact target frame count and duration when the safe fallback is used.

## 3.1 - 2026-09-05

- Fixed HEVC HDR10/HLG tone mapping and 10-bit input conversion.
- Switched intermediate extraction from lossy JPEG to lossless PNG.
- Added encoder-specific rate control for NVENC, VAAPI, QSV, VideoToolbox and AMF.
- Added automatic fallback and ffprobe validation of completed exports.
- Improved VFR detection and preserved all audio tracks, metadata, chapters and compatible subtitles.
- Added safe archive extraction and SHA-256 verification for application updates.
- Added cross-platform automated tests and release packaging.
- Added the MIT license file.
