#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
VERSION="$($PYTHON -c 'from core.paths import APP_VERSION; print(APP_VERSION)')"
ARCH="${ARCH:-x86_64}"
BUILD_ROOT="$ROOT/build/appimage"
APPDIR="$BUILD_ROOT/LocallyFPS.AppDir"
RUNTIME_DIR="${RUNTIME_DIR:-$ROOT/build/runtime-linux-x86_64}"
OUTPUT="$ROOT/dist/LocallyFPS-v${VERSION}-${ARCH}.AppImage"
OUTPUT_TEMP="${OUTPUT}.tmp"
APPIMAGETOOL="${APPIMAGETOOL:-$ROOT/build/tools/appimagetool-${ARCH}.AppImage}"

rm -rf "$APPDIR" "$ROOT/build/LocallyFPS" "$ROOT/dist/LocallyFPS"
rm -f "$OUTPUT_TEMP"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/metainfo" "$APPDIR/usr/share/icons/hicolor/scalable/apps" "$(dirname "$APPIMAGETOOL")" "$ROOT/dist"

if [[ ! -f "$RUNTIME_DIR/runtime.json" ]]; then
  "$PYTHON" "$ROOT/packaging/prepare_runtime.py" \
    --platform linux-x86_64 --output "$RUNTIME_DIR"
fi

"$PYTHON" "$ROOT/packaging/build_gui.py" \
  --runtime-dir "$RUNTIME_DIR" \
  --dist-dir "$ROOT/dist" \
  --work-dir "$ROOT/build/LocallyFPS" \
  --spec-dir "$ROOT/build/LocallyFPS"

cp -R "$ROOT/dist/LocallyFPS" "$APPDIR/usr/bin/LocallyFPS"
cp "$ROOT/packaging/AppRun" "$APPDIR/AppRun"
cp "$ROOT/packaging/io.github.mincmat.LocallyFPS.desktop" "$APPDIR/io.github.mincmat.LocallyFPS.desktop"
cp "$ROOT/packaging/locallyfps.svg" "$APPDIR/locallyfps.svg"
cp "$ROOT/packaging/io.github.mincmat.LocallyFPS.desktop" "$APPDIR/usr/share/applications/"
cp "$ROOT/packaging/io.github.mincmat.LocallyFPS.appdata.xml" "$APPDIR/usr/share/metainfo/"
cp "$ROOT/packaging/locallyfps.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/locallyfps.svg"
chmod +x "$APPDIR/AppRun" "$APPDIR/usr/bin/LocallyFPS/LocallyFPS"

if [[ ! -x "$APPIMAGETOOL" ]]; then
  curl -fL --retry 3 -o "$APPIMAGETOOL" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
  chmod +x "$APPIMAGETOOL"
fi

ARCH="$ARCH" "$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "$OUTPUT_TEMP"
chmod +x "$OUTPUT_TEMP"
mv -f "$OUTPUT_TEMP" "$OUTPUT"
echo "$OUTPUT"
