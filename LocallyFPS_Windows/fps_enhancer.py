#!/usr/bin/env python3
"""
LocallyFPS - Windows wrapper
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

sys.path.insert(0, str(HERE))

from core import init
init(HERE)

from platform.windows import enable_windows_ansi
enable_windows_ansi()

from core.wizard import main

if __name__ == "__main__":
    main()
