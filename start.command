#!/usr/bin/env bash
#
# start.command – LocallyFPS portable launcher (macOS).
# Double-click this file in Finder to launch.
#

set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENHANCER="$BASE_DIR/fps_enhancer.py"
LOCAL_PYTHON="$BASE_DIR/runtime/bin/python"

if [ ! -f "$ENHANCER" ]; then
    echo "Error: fps_enhancer.py not found in $BASE_DIR"
    echo "Make sure start.command and fps_enhancer.py are in the same folder."
    exit 1
fi

if [ -f "$LOCAL_PYTHON" ]; then
    PYTHON="$LOCAL_PYTHON"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    echo "No Python runtime found."
    echo "Install Python 3 or extract a portable runtime to: $LOCAL_PYTHON"
    exit 1
fi

mkdir -p "$BASE_DIR"/{deps/ffmpeg,deps/rife,models,cache,config,videos/original,videos/enhanced}

chmod +x "$BASE_DIR/deps/ffmpeg/ffmpeg" "$BASE_DIR/deps/ffmpeg/ffprobe" "$BASE_DIR/deps/rife/rife-ncnn-vulkan" 2>/dev/null || true

exec "$PYTHON" "$ENHANCER" "$@"
