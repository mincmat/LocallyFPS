#!/bin/bash
#
# start.sh – LocallyFPS launcher.
#
# Detects python3, installs it if missing, then launches fps_enhancer.py.
# Language is selected on first run (saved to config.json).
# Use --config to open the settings menu:  ./start.sh --config
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENHANCER="$SCRIPT_DIR/fps_enhancer.py"

if [ ! -f "$ENHANCER" ]; then
    echo "No se encontró fps_enhancer.py en: $SCRIPT_DIR"
    echo "Asegurate de que start.sh y fps_enhancer.py estén en la misma carpeta."
    exit 1
fi

# python3 es el único requisito que bash necesita resolver por sí mismo;
# el resto de las dependencias (ffmpeg, rife-ncnn-vulkan, vulkan-tools, etc.)
# las verifica e instala fps_enhancer.py con tu confirmación.
if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 no está instalado en este sistema."
    read -r -p "¿Instalarlo ahora? [s/N] " resp
    case "$resp" in
        s|S|si|Si|SI|sí|Sí|y|Y|yes|YES)
            if command -v pacman >/dev/null 2>&1; then
                sudo pacman -S --needed --noconfirm python
            elif command -v apt-get >/dev/null 2>&1; then
                sudo apt-get install -y python3
            elif command -v dnf >/dev/null 2>&1; then
                sudo dnf install -y python3
            elif command -v zypper >/dev/null 2>&1; then
                sudo zypper install -y python3
            elif command -v apk >/dev/null 2>&1; then
                sudo apk add python3
            else
                echo "No se detectó un gestor de paquetes soportado (pacman/apt/dnf/zypper/apk)."
                echo "Instalá python3 manualmente y volvé a correr ./start.sh"
                exit 1
            fi
            ;;
        *)
            echo "python3 es necesario para continuar."
            exit 1
            ;;
    esac
fi

exec python3 "$ENHANCER" "$@"
