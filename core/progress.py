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
from .i18n import _
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

    @staticmethod
    def _fmt_size(n):
        if n < 0:
            return "0B"
        for unit in ("B", "KB", "MB", "GB"):
            if abs(n) < 1024:
                return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
            n /= 1024
        return f"{n:.1f}TB"

    def _draw(self):
        if not self._enabled:
            return
        elapsed = time.time() - self.start_time
        pct = self.current / self.total if self.total else 0
        pct = max(0.0, min(1.0, pct))
        filled = int(self.width * pct)
        bar = "█" * filled + "░" * (self.width - filled)
        if elapsed < 3.0 or pct < 0.02:
            eta_str = _("Calculating...")
        else:
            eta = max(0, round(elapsed / pct - elapsed))
            eta_str = format_duration(eta)
        if self.unit.lower() in ("b", "byte", "bytes"):
            progress = f"{self._fmt_size(self.current)}/{self._fmt_size(self.total)}"
        else:
            # The activity label already says these are frames; keep the count
            # compact and language-neutral in the stdlib fallback UI.
            suffix = "" if self.unit.lower() in ("", "frame", "frames") else f" {self.unit}"
            progress = f"{self.current}/{self.total}{suffix}"
        sys.stdout.write(
            f"\r{Color.bold(self.desc)}: |{bar}| "
            f"{progress} ({pct*100:.1f}%) "
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
    """Single centered progress bar with box-drawing borders.
    Uses absolute cursor positioning for robustness.
    Includes smart ETA using EWMA (Exponential Weighted Moving Average)."""

    def __init__(self, width=20, box_width=50, header=None, enabled=None):
        self.width = width
        self._box_w = box_width
        self._inner = box_width - 2
        self._enabled = enabled if enabled is not None else sys.stdout.isatty()
        self._last = -1
        self._start_time = time.time()
        self._history = []  # [(time, progress), ...]
        self._ewma_rate = None  # frames per second (EWMA smoothed)
        self._alpha = 0.3  # EWMA smoothing factor
        if not self._enabled:
            return
        term = shutil.get_terminal_size()
        self._term_w = term.columns
        self._term_h = term.lines
        self._box_pad = " " * max(0, (self._term_w - self._box_w) // 2)
        self._box_col = len(self._box_pad)
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
        empty = "│" + " " * self._inner + "│"
        self._box_row = rows + h_total + 5
        sys.stdout.write(f"{self._box_pad}{self._top_line}\n")
        sys.stdout.write(f"{self._box_pad}{empty}\n")
        sys.stdout.write(f"{self._box_pad}{empty}\n")
        sys.stdout.write(f"{self._box_pad}{empty}\n")
        sys.stdout.write(f"{self._box_pad}{empty}\n")
        sys.stdout.write(f"{self._box_pad}{empty}\n")
        sys.stdout.write(f"{self._box_pad}{self._bot_line}\n")
        sys.stdout.flush()

    def _calc_eta(self, pct):
        """Calculate ETA using EWMA-smoothed processing rate."""
        now = time.time()
        elapsed = now - self._start_time

        # Need at least 3 seconds and 2% progress for stable ETA
        if elapsed < 3.0 or pct < 0.02:
            return None

        # Record this data point
        self._history.append((now, pct))

        # Keep only last 10 data points for responsiveness
        if len(self._history) > 10:
            self._history = self._history[-10:]

        # Calculate rate using EWMA
        if len(self._history) >= 2:
            t0, p0 = self._history[0]
            t1, p1 = self._history[-1]
            dt = t1 - t0
            dp = p1 - p0
            if dt > 0 and dp > 0:
                instant_rate = dp / dt  # progress per second
                if self._ewma_rate is None:
                    self._ewma_rate = instant_rate
                else:
                    self._ewma_rate = self._alpha * instant_rate + (1 - self._alpha) * self._ewma_rate

        if self._ewma_rate and self._ewma_rate > 0:
            remaining = (1.0 - pct) / self._ewma_rate
            return remaining
        return None

    def _fmt_eta(self, seconds):
        """Format seconds into human-readable ETA."""
        if seconds is None or seconds < 0:
            return ""
        if seconds < 60:
            return f"ETA {seconds:.0f}s"
        elif seconds < 3600:
            m = int(seconds // 60)
            s = int(seconds % 60)
            return f"ETA {m}m {s:02d}s"
        else:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            return f"ETA {h}h {m:02d}m"

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

        # Calculate ETA
        eta_secs = self._calc_eta(pct)
        eta_str = self._fmt_eta(eta_secs)

        # Bar line: just bar + percentage
        filled = int(self.width * pct)
        bar = "█" * filled + "░" * (self.width - filled)
        pct_str = f" {pct * 100:5.1f}%"
        bar_content = f"{bar}{pct_str}"
        blen = len(bar_content)
        if blen < self._inner:
            bl = (self._inner - blen) // 2
            tail = self._inner - bl - blen
        else:
            bl = 0
            tail = 0
            bar_content = bar_content[:self._inner]
        bar_line = "│" + " " * bl + bar_content + " " * tail + "│"

        # ETA line: centered below bar
        if eta_str:
            eta_display = eta_str
        else:
            eta_display = Color.dim(_("Calculating..."))

        empty = "│" + " " * self._inner + "│"
        # Move cursor to bottom border row, write it, then write ETA on next line
        sys.stdout.write(f"\033[{self._box_row};1H"
                         f"{self._box_pad}{self._top_line}\x1b[K\n"
                         f"{self._box_pad}{empty}\x1b[K\n"
                         f"{self._box_pad}{label_line}\x1b[K\n"
                         f"{self._box_pad}{empty}\x1b[K\n"
                         f"{self._box_pad}{bar_line}\x1b[K\n"
                         f"{self._box_pad}{empty}\x1b[K\n"
                         f"{self._box_pad}{self._bot_line}\x1b[K\n")
        # ETA outside the box, two lines below bottom border
        eta_clean = re.sub(r'\033\[[0-9;]*m', '', eta_display)
        ep = max(0, (self._term_w - len(eta_clean)) // 2)
        sys.stdout.write(f"\r\033[K\n"
                         f"\r\033[K"
                         f"{' ' * ep}{eta_display}\n")
        sys.stdout.flush()
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


class DependencyBar:
    """Centered box progress bar for dependency downloads.
    Appears inline without clearing the screen."""

    def __init__(self, title="Installing dependencies", box_width=52, bar_width=20, enabled=None):
        self._box_w = box_width
        self._inner = box_width - 2
        self._bar_w = bar_width
        self._enabled = enabled if enabled is not None else sys.stdout.isatty()
        self._last_pct = -1
        self._start = time.time()
        self._closed = False
        if not self._enabled:
            return
        term = shutil.get_terminal_size()
        self._term_w = term.columns
        self._box_pad = " " * max(0, (self._term_w - self._box_w) // 2)
        self._top = "┌" + "─" * self._inner + "┐"
        self._bot = "└" + "─" * self._inner + "┘"
        ct = re.sub(r'\033\[[0-9;]*m', '', title)
        tp = max(0, (self._inner - len(ct)) // 2)
        self._title = "│" + " " * tp + title + " " * (self._inner - tp - len(ct)) + "│"
        empty = "│" + " " * self._inner + "│"
        sys.stdout.write(f"{self._box_pad}{self._top}\n")
        sys.stdout.write(f"{self._box_pad}{empty}\n")
        sys.stdout.write(f"{self._box_pad}{self._title}\n")
        sys.stdout.write(f"{self._box_pad}{empty}\n")
        sys.stdout.write(f"{self._box_pad}{empty}\n")
        sys.stdout.write(f"{self._box_pad}{empty}\n")
        sys.stdout.write(f"{self._box_pad}{self._bot}\n")
        # 7 rows total. Cursor at row 8.
        # Row 5 = bar placeholder. update/ok/fail: \033[3A → row 5, write 3 rows.
        sys.stdout.flush()

    def _fmt_size(self, n):
        if n < 0:
            return "0B"
        for unit in ("B", "KB", "MB", "GB"):
            if abs(n) < 1024:
                return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
            n /= 1024
        return f"{n:.1f}TB"

    def update(self, pct, label=None, downloaded=None, total=None):
        if not self._enabled or self._closed:
            return
        pct = max(0.0, min(1.0, pct))
        if abs(pct - self._last_pct) < 0.005 and label is None:
            return
        self._last_pct = pct

        if label:
            clean = re.sub(r'\033\[[0-9;]*m', '', label)
            lp = max(0, (self._inner - len(clean)) // 2)
            label_line = "│" + " " * lp + label + " " * (self._inner - lp - len(clean)) + "│"
        else:
            label_line = "│" + " " * self._inner + "│"

        filled = int(self._bar_w * pct)
        bar = "█" * filled + "░" * (self._bar_w - filled)
        if downloaded is not None and total is not None and total > 0:
            size_str = f"{self._fmt_size(downloaded)}/{self._fmt_size(total)}"
            pct_str = f" {pct*100:5.1f}%"
            info = f" {size_str}{pct_str}"
        else:
            info = f" {pct*100:5.1f}%"
        bar_content = bar + info
        blen = len(bar_content)
        if blen < self._inner:
            bl = (self._inner - blen) // 2
            tail = self._inner - bl - blen
        else:
            bl = 0
            tail = 0
            bar_content = bar_content[:self._inner]
        bar_line = "│" + " " * bl + bar_content + " " * tail + "│"

        empty = "│" + " " * self._inner + "│"
        sys.stdout.write("\033[3A")
        sys.stdout.write(f"{self._box_pad}{bar_line}\x1b[K\n")
        sys.stdout.write(f"{self._box_pad}{empty}\x1b[K\n")
        sys.stdout.write(f"{self._box_pad}{self._bot}\x1b[K\n")
        sys.stdout.flush()

    def ok(self, msg=None):
        if self._closed:
            return
        self._closed = True
        if not self._enabled:
            return
        elapsed = time.time() - self._start
        final = msg or "Done"
        clean = re.sub(r'\033\[[0-9;]*m', '', final)
        lp = max(0, (self._inner - len(clean) - 4) // 2)
        check = Color.ok("[✓]")
        rp = max(0, self._inner - lp - len(clean) - 4)
        line = "│" + " " * lp + check + " " + final + " " * rp + "│"
        empty = "│" + " " * self._inner + "│"
        sys.stdout.write("\033[3A")
        sys.stdout.write(f"{self._box_pad}{line}\x1b[K\n")
        sys.stdout.write(f"{self._box_pad}{empty}\x1b[K\n")
        sys.stdout.write(f"{self._box_pad}{self._bot}\x1b[K\n")
        sys.stdout.flush()

    def fail(self, msg=None):
        if self._closed:
            return
        self._closed = True
        if not self._enabled:
            return
        final = msg or "Failed"
        clean = re.sub(r'\033\[[0-9;]*m', '', final)
        lp = max(0, (self._inner - len(clean) - 4) // 2)
        cross = Color.error("[✗]")
        rp = max(0, self._inner - lp - len(clean) - 4)
        line = "│" + " " * lp + cross + " " + final + " " * rp + "│"
        empty = "│" + " " * self._inner + "│"
        sys.stdout.write("\033[3A")
        sys.stdout.write(f"{self._box_pad}{line}\x1b[K\n")
        sys.stdout.write(f"{self._box_pad}{empty}\x1b[K\n")
        sys.stdout.write(f"{self._box_pad}{self._bot}\x1b[K\n")
        sys.stdout.flush()
