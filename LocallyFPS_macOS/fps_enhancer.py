#!/usr/bin/env python3
"""
LocallyFPS - macOS wrapper
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from core import init
init(HERE)

from core.wizard import main

if __name__ == "__main__":
    main()
