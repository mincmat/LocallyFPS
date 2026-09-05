# Changelog

## 3.1 - 2026-09-05

- Fixed HEVC HDR10/HLG tone mapping and 10-bit input conversion.
- Switched intermediate extraction from lossy JPEG to lossless PNG.
- Added encoder-specific rate control for NVENC, VAAPI, QSV, VideoToolbox and AMF.
- Added automatic fallback and ffprobe validation of completed exports.
- Improved VFR detection and preserved all audio tracks, metadata, chapters and compatible subtitles.
- Added safe archive extraction and SHA-256 verification for application updates.
- Added cross-platform automated tests and release packaging.
- Added the MIT license file.
