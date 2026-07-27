#!/bin/bash
#
# start.command – LocallyFPS launcher for macOS.
#
# Double-click this file in Finder to start the interactive wizard.
# You can also run it from Terminal:  ./start.command [options]
#
# Detects Python 3 (via Homebrew or bundled), installs it if missing,
# then launches fps_enhancer.py. Language is selected on first run.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENHANCER="$SCRIPT_DIR/fps_enhancer.py"

if [ ! -f "$ENHANCER" ]; then
    echo "Error: fps_enhancer.py not found in $SCRIPT_DIR"
    echo "Make sure start.command and fps_enhancer.py are in the same folder."
    exit 1
fi

# ------------------------------------------------------------------------- #
# Python detection (prefer Homebrew, then system, then install)
# ------------------------------------------------------------------------- #

# Check for python3 from Homebrew first
BREW_PYTHON=""
if command -v brew >/dev/null 2>&1; then
    BREW_PREFIX=$(brew --prefix 2>/dev/null || echo "/usr/local")
    if [ -x "$BREW_PREFIX/bin/python3" ]; then
        BREW_PYTHON="$BREW_PREFIX/bin/python3"
    fi
fi

PYTHON=""
if [ -n "$BREW_PYTHON" ]; then
    PYTHON="$BREW_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif [ -x "/usr/bin/python3" ]; then
    # macOS may bundle python3 (Xcode CLT or newer macOS)
    PYTHON="/usr/bin/python3"
fi

if [ -z "$PYTHON" ]; then
    echo "Python 3 is not installed on this system."

    # Try using osascript for a GUI dialog when double-clicked
    if [ -z "$TERM" ] || [ "$TERM" = "dumb" ]; then
        osascript -e 'tell app "System Events" to display dialog "LocallyFPS needs Python 3.\n\nInstall Homebrew and Python 3 now?" buttons {"Cancel", "Install"} default button "Install" with icon caution' >/dev/null 2>&1
        RESPONSE=$?
    else
        read -r -p "Install Homebrew and Python 3 now? [y/N] " RESPONSE_LINE
        case "$RESPONSE_LINE" in
            y|Y|yes|YES) RESPONSE=0 ;;
            *) RESPONSE=1 ;;
        esac
    fi

    if [ "$RESPONSE" -eq 0 ]; then
        if ! command -v brew >/dev/null 2>&1; then
            echo "Installing Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || {
                echo "Failed to install Homebrew. Install it manually from https://brew.sh"
                exit 1
            }
            # Add brew to PATH for this session
            if [ -x "/opt/homebrew/bin/brew" ]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [ -x "/usr/local/bin/brew" ]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
        fi
        echo "Installing Python 3 via Homebrew..."
        brew install python3
        PYTHON="python3"
    else
        echo "Python 3 is required to continue."
        echo "Install Homebrew from https://brew.sh and then run: brew install python3"
        exit 1
    fi
fi

# ------------------------------------------------------------------------- #
# Ensure required pip packages (tqdm for progress bars)
# ------------------------------------------------------------------------- #

if ! "$PYTHON" -c "import tqdm" 2>/dev/null; then
    echo "Installing tqdm for progress bars..."
    "$PYTHON" -m pip install tqdm -q 2>/dev/null || true
fi

# ------------------------------------------------------------------------- #
# Launch
# ------------------------------------------------------------------------- #

exec "$PYTHON" "$ENHANCER" "$@"
