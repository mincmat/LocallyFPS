import atexit
import shutil
import signal
import sys
import tempfile
from pathlib import Path

from . import paths
from .console import status
from .disk import check_disk_space
from .i18n import _

_temp_managers = []


class TempManager:
    def __init__(self, estimated_bytes=0):
        cache_dir = paths.CACHE_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)
        if estimated_bytes > 0:
            check_disk_space(cache_dir, int(estimated_bytes * 1.5))
        self.temp_root = Path(tempfile.mkdtemp(prefix="locallyfps_", dir=str(cache_dir)))
        self.in_frames_dir = self.temp_root / "in_frames"
        self.out_frames_dir = self.temp_root / "out_frames"
        self.in_frames_dir.mkdir(parents=True, exist_ok=True)
        self.out_frames_dir.mkdir(parents=True, exist_ok=True)
        status(f"{_('Using temporary folder:')} {self.temp_root}", "INFO")
        self._cleaned = False
        _temp_managers.append(self)
        atexit.register(self.cleanup)
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except (ValueError, OSError):
            pass

    def _signal_handler(self, signum, frame):
        status(_("Interrupt received. Cleaning up..."), "WARN")
        self.cleanup()
        sys.exit(130)

    def cleanup(self):
        if self._cleaned:
            return
        self._cleaned = True
        if self.temp_root.exists():
            shutil.rmtree(self.temp_root, ignore_errors=True)
