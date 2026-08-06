import re
import shutil
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


class PipelineBar:
    """Single centered progress bar with box-drawing borders."""

    def __init__(self, width=20, box_width=50, header=None, enabled=None):
        self.width = width
        self._box_w = box_width
        self._inner = box_width - 2
        self._enabled = enabled if enabled is not None else sys.stdout.isatty()
        self._last = -1
        if not self._enabled:
            return
        term = shutil.get_terminal_size()
        self._term_w = term.columns
        self._box_pad = " " * max(0, (self._term_w - self._box_w) // 2)
        header_lines = header or []
        h_total = len(header_lines) + (1 if header_lines else 0)
        rows = max(1, (term.lines - (h_total + 4)) // 2 - 1)
        sys.stdout.write("\033[2J\033[H\033[3J")
        sys.stdout.write("\n" * rows)
        if header_lines:
            for line in header_lines:
                clean = re.sub(r'\033\[[0-9;]*m', '', line)
                pad = max(0, (self._term_w - len(clean)) // 2)
                sys.stdout.write(" " * pad + line + "\n")
            sys.stdout.write("\n" * 5)
        self._top_line = "┌" + "─" * self._inner + "┐"
        self._bot_line = "└" + "─" * self._inner + "┘"
        mid = "│" + " " * self._inner + "│"
        sys.stdout.write(f"{self._box_pad}{self._top_line}\n")
        sys.stdout.write(f"{self._box_pad}{mid}\n")
        sys.stdout.write(f"{self._box_pad}{mid}\n")
        sys.stdout.write(f"{self._box_pad}{self._bot_line}\n")
        sys.stdout.flush()

    def update(self, pct, label=None):
        if not self._enabled:
            return
        pct = max(0.0, min(1.0, pct))
        if abs(pct - self._last) < 0.001:
            return
        self._last = pct

        if label:
            clean = re.sub(r'\033\[[0-9;]*m', '', label)
            lp = max(0, (self._inner - len(clean)) // 2)
            label_line = "│" + " " * lp + label + " " * (self._inner - lp - len(clean)) + "│"
        else:
            label_line = "│" + " " * self._inner + "│"

        filled = int(self.width * pct)
        bar = "#" * filled + "-" * (self.width - filled)
        pct_str = f" {pct * 100:5.1f}%"
        bl = (self._inner - self.width - 7) // 2
        tail = self._inner - self.width - 7 - bl
        bar_line = "│" + " " * bl + bar + pct_str + " " * tail + "│"

        sys.stdout.write(f"\x1b[4A\r{self._box_pad}{self._top_line}\x1b[K\n"
                         f"{self._box_pad}{label_line}\x1b[K\n"
                         f"{self._box_pad}{bar_line}\x1b[K\n"
                         f"{self._box_pad}{self._bot_line}\x1b[K\n")
        sys.stdout.flush()

    def close(self):
        if self._enabled:
            sys.stdout.write("\r\n")
            sys.stdout.flush()


class Spinner:
    _CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, msg, enabled=None):
        self.msg = msg
        self._enabled = enabled if enabled is not None else sys.stdout.isatty()
        self._done = False
        self._idx = 0
        self._chars = Spinner._CHARS
        self._start = time.time()
        self._pad = " " * max(0, (shutil.get_terminal_size().columns - len(msg) - 4) // 2)
        if self._enabled:
            sys.stdout.write(f"\r{self._pad}{self.msg} ")
            sys.stdout.flush()

    def tick(self):
        if not self._enabled or self._done:
            return
        self._idx = (self._idx + 1) % len(self._chars)
        sys.stdout.write(f"\r{self._pad}{self.msg} {self._chars[self._idx]} ")
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
                sys.stdout.write(f"\r{self._pad}{check} {final} {Color.dim(f'({format_duration(elapsed)})')}\n")
            else:
                sys.stdout.write(f"\r{self._pad}{check} {final}\n")
            sys.stdout.flush()
