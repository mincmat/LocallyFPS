#!/usr/bin/env python3
"""Graphical entry point for LocallyFPS 4."""

import sys
from pathlib import Path


HERE = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
sys.path.insert(0, str(HERE))

from core import init

init(HERE)

from gui.app import main


if __name__ == "__main__":
    raise SystemExit(main())
