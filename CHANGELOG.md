# Changelog

## 3.0.1 - 2026-09-06

- Fixed stream probing so audio and subtitle tracks are detected and preserved instead of silently dropped.
- Normalized presentation timestamps before frame extraction so VFR sources keep their duration and audio sync.
- Correctly tagged HDR10/HLG tone-mapped output as SDR BT.709 instead of copying contradictory HDR metadata.
- Replaced the unsafe PNG disk estimate with a conservative estimate covering both source and generated frames.
- Added exact frame-count, FPS, duration, audio-track and decodability validation before accepting an export.
- Made exports atomic so a failed encode cannot destroy an existing output file.
- Added safe handling for lower target rates, invalid/non-finite FPS values, odd frame dimensions and non-square pixels.
- Preserved image-based subtitles by automatically switching incompatible MP4 output to MKV.
- Added an end-to-end safe-backend test and made CI install FFmpeg instead of silently skipping media tests.
- Forced the safe optical-flow backend for AMD Vulkan GPUs on Linux after confirming delayed RIFE corruption on RADV.
- Distributed RIFE preflight validation across the entire source instead of checking only the opening frame pair.
- Added a preflight check that detects corrupt or duplicated RIFE output before processing a full video.
- Added automatic motion-compensated FFmpeg interpolation when a Vulkan driver produces invalid RIFE frames.
- Preserved the exact target frame count and duration when the safe fallback is used.
- Fixed HEVC HDR10/HLG tone mapping and 10-bit input conversion.
- Switched intermediate extraction from lossy JPEG to lossless PNG.
- Added encoder-specific rate control for NVENC, VAAPI, QSV, VideoToolbox and AMF.
- Added automatic fallback and ffprobe validation of completed exports.
- Improved VFR detection and preserved all audio tracks, metadata, chapters and compatible subtitles.
- Added safe archive extraction and SHA-256 verification for application updates.
- Added cross-platform automated tests and release packaging.
- Added the MIT license file.
