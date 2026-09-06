import sys

from . import paths


def _configure_stdio():
    """Keep translated output reliable on Windows and redirected consoles."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def init(base_dir):
    _configure_stdio()
    paths.setup(base_dir)
