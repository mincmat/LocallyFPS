#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
VERSION="$($PYTHON -c 'from core.paths import APP_VERSION; print(APP_VERSION)')"
ARCH="${ARCH:-x86_64}"
BUILD_ROOT="$ROOT/build/appimage"
APPDIR="$BUILD_ROOT/LocallyFPS.AppDir"
OUTPUT="$ROOT/dist/LocallyFPS-v${VERSION}-${ARCH}.AppImage"
APPIMAGETOOL="${APPIMAGETOOL:-$ROOT/build/tools/appimagetool-${ARCH}.AppImage}"

rm -rf "$APPDIR" "$ROOT/build/LocallyFPS" "$ROOT/dist/LocallyFPS"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/metainfo" "$APPDIR/usr/share/icons/hicolor/scalable/apps" "$(dirname "$APPIMAGETOOL")" "$ROOT/dist"

$PYTHON -m PyInstaller --noconfirm --clean --windowed --onedir \
  --name LocallyFPS \
  --add-data "$ROOT/languages:languages" \
  --add-data "$ROOT/packaging/locallyfps.svg:packaging" \
  --hidden-import platforms.linux \
  --hidden-import platforms.windows \
  --hidden-import platforms.macos \
  --distpath "$ROOT/dist" --workpath "$ROOT/build/LocallyFPS" \
  --specpath "$ROOT/build/LocallyFPS" \
  "$ROOT/locallyfps_gui.py"

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

ARCH="$ARCH" "$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "$OUTPUT"
chmod +x "$OUTPUT"
echo "$OUTPUT"
