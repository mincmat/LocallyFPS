import sys
import time

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

from .colors import Color
from .utils import format_duration


class ProgressBar:
    def __init__(self, total, desc="", unit="", width=40):
        self.total = total
        self.desc = desc
        self.unit = unit
        self.width = width
        self.current = 0
        self.start_time = time.time()
        self._enabled = sys.stdout.isatty()

    def update(self, n=1):
        self.current += n
        self._draw()

    def _draw(self):
        if not self._enabled:
            return
        elapsed = time.time() - self.start_time
        pct = self.current / self.total if self.total else 0
        filled = int(self.width * pct)
        bar = "█" * filled + "░" * (self.width - filled)
        eta = (elapsed / max(pct, 0.001) - elapsed) if pct > 0 else 0
        if eta >= 3600:
            eta_str = f"{eta/3600:.0f}h{eta%3600/60:.0f}m"
        elif eta >= 60:
            eta_str = f"{eta/60:.0f}min{eta%60:.0f}s"
        else:
            eta_str = f"{eta:.0f}s"
        sys.stdout.write(
            f"\r{Color.bold(self.desc)}: |{bar}| "
            f"{self.current}/{self.total} ({pct*100:.1f}%) "
            f"ETA {eta_str}  "
        )
        sys.stdout.flush()

    def close(self):
        if self._enabled:
            self._draw()
            sys.stdout.write("\n")
            sys.stdout.flush()


class DownloadProgress:
    def __init__(self, desc="Downloading"):
        self.desc = desc
        self.pbar = None
        self._has_tqdm = HAS_TQDM

    def __call__(self, block_num, block_size, total_size):
        if self.pbar is None:
            if self._has_tqdm:
                self.pbar = tqdm(total=total_size, unit='B', unit_scale=True, desc=self.desc)
            else:
                self.pbar = ProgressBar(total=total_size, desc=self.desc, unit="B")
        downloaded = block_num * block_size
        if downloaded > total_size:
            downloaded = total_size
        if self._has_tqdm:
            self.pbar.update(downloaded - self.pbar.n)
        else:
            self.pbar.current = downloaded
            self.pbar._draw()

    def close(self):
        if self.pbar:
            self.pbar.close()


class Spinner:
    _CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, msg, enabled=None):
        self.msg = msg
        self._enabled = enabled if enabled is not None else sys.stdout.isatty()
        self._done = False
        self._idx = 0
        self._chars = Spinner._CHARS
        self._start = time.time()
        if self._enabled:
            sys.stdout.write(f"\r{self.msg} ")
            sys.stdout.flush()

    def tick(self):
        if not self._enabled or self._done:
            return
        self._idx = (self._idx + 1) % len(self._chars)
        sys.stdout.write(f"\r{self.msg} {self._chars[self._idx]} ")
        sys.stdout.flush()

    def ok(self, msg=None, show_time=True):
        if self._done:
            return
        self._done = True
        if self._enabled:
            check = Color.ok("[✓]")
            final = msg or self.msg
            if show_time:
                elapsed = time.time() - self._start
                sys.stdout.write(f"\r{check} {final} {Color.dim(f'({format_duration(elapsed)})')}\n")
            else:
                sys.stdout.write(f"\r{check} {final}\n")
            sys.stdout.flush()
