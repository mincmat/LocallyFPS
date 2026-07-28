#!/usr/bin/env python3
"""
fps_enhancer.py - AI frame interpolation for video using rife-ncnn-vulkan.

LocallyFPS (Windows) - frame interpolation tool using RIFE AI models.

Portable version — all dependencies inside the application folder.
"""

import argparse
import atexit
import ctypes
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

APP_VERSION = "1.1"
BASE_DIR = Path(__file__).resolve().parent

try:
    import readline  # pyreadline3 en Windows provee este módulo si está instalado
    HAS_READLINE = True
except ImportError:
    HAS_READLINE = False

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False


# --------------------------------------------------------------------------- #
# Portable paths
# --------------------------------------------------------------------------- #

FFMPEG_PATH = BASE_DIR / "deps" / "ffmpeg" / "ffmpeg.exe"
FFPROBE_PATH = BASE_DIR / "deps" / "ffmpeg" / "ffprobe.exe"
RIFE_PATH = BASE_DIR / "deps" / "rife" / "rife-ncnn-vulkan.exe"
MODELS_DIR = BASE_DIR / "models"
CACHE_DIR = BASE_DIR / "cache"
CONFIG_DIR = BASE_DIR / "config"
VIDEOS_DIR = BASE_DIR / "videos"

RIFE_RELEASE_URLS = {
    "linux": "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-ubuntu.zip",
    "windows": "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-windows.zip",
    "macos": "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-macos.zip",
}

FFMPEG_RELEASE_URLS = {
    "linux": None,  # TODO: add URL for Linux static ffmpeg build (e.g. johnvansickle.com)
    "windows": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    "macos": None,  # TODO: add URL for macOS static ffmpeg build
}

_REQUIRED_DIRS = [
    FFMPEG_PATH.parent, RIFE_PATH.parent,
    MODELS_DIR, CACHE_DIR, CONFIG_DIR,
    VIDEOS_DIR / "original", VIDEOS_DIR / "enhanced",
]


def _ensure_dirs():
    for d in _REQUIRED_DIRS:
        d.mkdir(parents=True, exist_ok=True)


def _any_dep_missing():
    return (
        not (FFMPEG_PATH.is_file() or shutil.which("ffmpeg") or shutil.which("ffmpeg.exe"))
        or not (FFPROBE_PATH.is_file() or shutil.which("ffprobe") or shutil.which("ffprobe.exe"))
        or not (RIFE_PATH.is_file() or shutil.which("rife-ncnn-vulkan") or shutil.which("rife-ncnn-vulkan.exe"))
        or not (MODELS_DIR / "rife-v4.6").is_dir()
    )


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

CONFIG_PATH = CONFIG_DIR / "settings.json"

DEFAULT_CONFIG = {
    "language": "es",
    "encoder": "libx264",
    "crf": 16,
    "preset": "fast",
    "model": "rife-v4.6",
    "video_preset": "custom",
}

CONFIG = dict(DEFAULT_CONFIG)


def _load_config():
    global CONFIG
    try:
        old_config = CONFIG_DIR.parent / "config.json"
        if not CONFIG_PATH.exists() and old_config.exists():
            with open(old_config) as f:
                data = json.load(f)
            CONFIG = {**DEFAULT_CONFIG, **data}
            _save_config()
            old_config.unlink(missing_ok=True)
        elif CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            CONFIG = {**DEFAULT_CONFIG, **data}
        else:
            CONFIG = dict(DEFAULT_CONFIG)
            _save_config()
    except Exception:
        CONFIG = dict(DEFAULT_CONFIG)


def _save_config():
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(CONFIG, f, indent=2)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Translation (local files, no internet)
# --------------------------------------------------------------------------- #

LANG_DIR = BASE_DIR / "languages"
TRANSLATIONS = {}

def _load_translations():
    global TRANSLATIONS
    for lang_file in sorted(LANG_DIR.glob("*.json")):
        lang_code = lang_file.stem
        try:
            with open(lang_file, encoding="utf-8") as f:
                TRANSLATIONS[lang_code] = json.load(f)
        except Exception:
            TRANSLATIONS[lang_code] = {}

def _(text):
    lang = CONFIG.get("language", "en")
    if lang in TRANSLATIONS and text in TRANSLATIONS[lang]:
        return TRANSLATIONS[lang][text]
    return text

LANGUAGE_NAMES = {
    "en": "English", "es": "Español",
}
LANG_CODES = list(LANGUAGE_NAMES.keys())


def get_language_name(code):
    return LANGUAGE_NAMES.get(code, code)


# --------------------------------------------------------------------------- #
# Windows console setup (habilita secuencias ANSI/VT100 en cmd.exe clásico)
# --------------------------------------------------------------------------- #

def _enable_windows_ansi():
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        for handle_id in (-11, -12):  # STDOUT, STDERR
            h = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(h, ctypes.byref(mode)):
                kernel32.SetConsoleMode(h, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# ANSI Colors
# --------------------------------------------------------------------------- #

class Color:
    _ENABLED = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

    if _ENABLED:
        RESET = "\033[0m"
        BOLD = "\033[1m"
        DIM = "\033[2m"
        RED = "\033[31m"
        GREEN = "\033[32m"
        YELLOW = "\033[33m"
        CYAN = "\033[36m"
        MAGENTA = "\033[35m"
        GRAY = "\033[90m"
    else:
        RESET = BOLD = DIM = RED = GREEN = YELLOW = CYAN = MAGENTA = GRAY = ""

    @classmethod
    def info(cls, t):
        return f"{cls.CYAN}{t}{cls.RESET}"
    @classmethod
    def ok(cls, t):
        return f"{cls.GREEN}{t}{cls.RESET}"
    @classmethod
    def warn(cls, t):
        return f"{cls.YELLOW}{t}{cls.RESET}"
    @classmethod
    def error(cls, t):
        return f"{cls.RED}{t}{cls.RESET}"
    @classmethod
    def bold(cls, t):
        return f"{cls.BOLD}{t}{cls.RESET}"
    @classmethod
    def dim(cls, t):
        return f"{cls.DIM}{t}{cls.RESET}"
    @classmethod
    def magenta(cls, t):
        return f"{cls.MAGENTA}{t}{cls.RESET}"
    @classmethod
    def gray(cls, t):
        return f"{cls.GRAY}{t}{cls.RESET}"


# --------------------------------------------------------------------------- #
# Progress Bar (fallback when tqdm is unavailable)
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Download Progress
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Interactive selector (arrow keys + enter) - versión Windows con msvcrt
# --------------------------------------------------------------------------- #

def _interactive_select(prompt, options):
    """Show a list with arrow-key navigation. Returns selected index."""
    n = len(options)
    if n == 0:
        return -1

    if not sys.stdin.isatty() or not HAS_MSVCRT:
        print(f"\n{Color.bold(prompt)}")
        for i, opt in enumerate(options):
            print(f"  {i+1}. {opt}")
        while True:
            try:
                resp = input(f"{Color.magenta('▸')} ").strip()
                if resp:
                    idx = int(resp) - 1
                    if 0 <= idx < n:
                        return idx
            except (ValueError, EOFError):
                pass
            print(f"{Color.warn(_('Enter a number between 1 and'))} {n}.")

    idx = 0
    sys.stdout.write(f"\r{Color.bold(prompt)}\r\n")
    for i, opt in enumerate(options):
        sys.stdout.write(f"\r  {'▸' if i == idx else ' '} {opt}\r\n")
    sys.stdout.flush()
    while True:
        ch = msvcrt.getch()
        if ch == b"\x03":
            sys.stdout.write("\r\n")
            sys.stdout.flush()
            sys.exit(130)
        if ch in (b"\x00", b"\xe0"):
            ch2 = msvcrt.getch()
            if ch2 == b"H":  # arrow up
                idx = (idx - 1) % n
            elif ch2 == b"P":  # arrow down
                idx = (idx + 1) % n
            sys.stdout.write(f"\x1b[{n}A")
            for i, opt in enumerate(options):
                sys.stdout.write(f"\r  {'▸' if i == idx else ' '} {opt}\x1b[K\r\n")
            sys.stdout.flush()
        elif ch in (b"\r", b"\n"):
            total = n + 1
            sys.stdout.write(f"\x1b[{total}A")
            for i in range(total):
                sys.stdout.write("\r\x1b[K\x1b[B")
            sys.stdout.write(f"\x1b[{total}A")
            sys.stdout.flush()
            break
    return idx


def _interactive_select_video(options):
    """Show a list with arrow-key navigation for videos. Returns selected index."""
    n = len(options)
    if n == 0:
        return -1

    if not HAS_MSVCRT:
        for i, opt in enumerate(options):
            print(f"  {i+1}. {opt}")
        return -1

    idx = 0
    for i, opt in enumerate(options):
        sys.stdout.write(f"  {'▸' if i == idx else ' '} {opt}\r\n")
    sys.stdout.flush()
    while True:
        ch = msvcrt.getch()
        if ch == b"\x03":
            sys.stdout.write("\r\n")
            sys.stdout.flush()
            sys.exit(130)
        if ch in (b"\x00", b"\xe0"):
            ch2 = msvcrt.getch()
            if ch2 == b"H":
                idx = (idx - 1) % n
            elif ch2 == b"P":
                idx = (idx + 1) % n
            sys.stdout.write(f"\x1b[{n}A")
            for i, opt in enumerate(options):
                sys.stdout.write(f"\r  {'▸' if i == idx else ' '} {opt}\x1b[K\r\n")
            sys.stdout.flush()
        elif ch in (b"\r", b"\n"):
            total = n
            sys.stdout.write(f"\x1b[{total}A")
            for i in range(total):
                sys.stdout.write("\r\x1b[K\x1b[B")
            sys.stdout.write(f"\x1b[{total}A")
            sys.stdout.flush()
            break
    return idx


# --------------------------------------------------------------------------- #
# Language selector (first run)
# --------------------------------------------------------------------------- #

def _run_language_wizard():
    print()
    i = _interactive_select("Select language / Seleccione idioma:",
                            [get_language_name(c) for c in LANG_CODES])
    if 0 <= i < len(LANG_CODES):
        CONFIG["language"] = LANG_CODES[i]
        _save_config()
        print(f"{Color.ok(_('[+]'))} Language set to: {get_language_name(LANG_CODES[i])}")
    else:
        CONFIG["language"] = "en"
        _save_config()
    print()


# --------------------------------------------------------------------------- #
# Settings menu
# --------------------------------------------------------------------------- #

def list_available_rife_models():
    if not MODELS_DIR.is_dir():
        return ["rife-v4.6"]
    found = sorted(d.name for d in MODELS_DIR.iterdir()
                    if d.is_dir() and d.name.startswith("rife-"))
    return found if found else ["rife-v4.6"]

def _run_settings():
    expanded = False
    while True:
        options = [
            f"{_('Language')}: {get_language_name(CONFIG['language'])}",
        ]
        if expanded:
            adv_start = len(options)
            options += [
                f"{_('Encoder')}: {CONFIG['encoder']}",
                f"{_('CRF')}: {CONFIG['crf']}",
                f"{_('ffmpeg preset')}: {CONFIG['preset']}",
                f"{_('Model')}: {CONFIG['model']}",
            ]
            toggle_idx = len(options)
            options.append(f"▲ {_('Advanced')}")
        else:
            adv_start = None
            toggle_idx = len(options)
            options.append(f"{_('Advanced')} ▸")
        save_idx = len(options)
        options.append(_('Save & exit'))
        cancel_idx = len(options)
        options.append(_('Cancel'))

        i = _interactive_select(Color.bold(_("Settings")), options)
        if i < 0:
            break
        if i == 0:
            li = _interactive_select(_("Language selection"),
                                     [get_language_name(c) for c in LANG_CODES])
            if 0 <= li < len(LANG_CODES):
                CONFIG["language"] = LANG_CODES[li]
        elif expanded and adv_start is not None and i < toggle_idx:
            sub = i - adv_start
            if sub == 0:
                encoders = list(ENCODER_PRESETS.keys())
                ei = _interactive_select(_("Encoder"), encoders)
                if 0 <= ei < len(encoders):
                    CONFIG["encoder"] = encoders[ei]
                    CONFIG["video_preset"] = "custom"
            elif sub == 1:
                print(f"\n{Color.dim(_('CRF'))} (0-51, {_('lower = better quality')}):")
                try:
                    v = input(f"{Color.magenta('▸')} ").strip()
                    v = int(v)
                    if 0 <= v <= 51:
                        CONFIG["crf"] = v
                        CONFIG["video_preset"] = "custom"
                except (ValueError, EOFError):
                    pass
            elif sub == 2:
                presets = ["ultrafast", "superfast", "veryfast", "faster",
                           "fast", "medium", "slow", "slower", "veryslow", "placebo"]
                pi = _interactive_select(_("ffmpeg preset"), presets)
                if 0 <= pi < len(presets):
                    CONFIG["preset"] = presets[pi]
                    CONFIG["video_preset"] = "custom"
            elif sub == 3:
                available = list_available_rife_models()
                mi = _interactive_select(_("Model"), available)
                if 0 <= mi < len(available):
                    selected = available[mi]
                    if not (MODELS_DIR / selected).is_dir():
                        status(f"{_('Model')} {selected} {_('not installed. Downloading...')}")
                        if not install_model(selected):
                            status(f"{_('Failed to download')} {selected}.", "ERROR")
                            continue
                    CONFIG["model"] = selected
                    CONFIG["video_preset"] = "custom"
        elif i == toggle_idx:
            expanded = not expanded
        elif i == save_idx:
            _save_config()
            break
        elif i == cancel_idx:
            break


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #


# Rutas resueltas en tiempo de ejecución por ensure_dependencies()
FFMPEG_BIN = None
FFPROBE_BIN = None
RIFE_BIN = None

ENCODER_PRESETS = {
    "libx264":    {"codec": "libx264",    "hwaccel": None,     "pix_fmt": "yuv420p"},
    "libx265":    {"codec": "libx265",    "hwaccel": None,     "pix_fmt": "yuv420p"},
    "h264_nvenc": {"codec": "h264_nvenc", "hwaccel": "cuda",   "pix_fmt": "yuv420p"},
    "hevc_nvenc": {"codec": "hevc_nvenc", "hwaccel": "cuda",   "pix_fmt": "yuv420p"},
    "h264_amf":   {"codec": "h264_amf",   "hwaccel": "d3d11va","pix_fmt": "nv12"},
    "hevc_amf":   {"codec": "hevc_amf",   "hwaccel": "d3d11va","pix_fmt": "nv12"},
    "h264_qsv":   {"codec": "h264_qsv",   "hwaccel": "qsv",    "pix_fmt": "nv12"},
    "hevc_qsv":   {"codec": "hevc_qsv",   "hwaccel": "qsv",    "pix_fmt": "nv12"},
}

PRESETS = {
    "balanced": {"encoder": "libx264", "ffmpeg_preset": "veryfast",  "crf": 20,
                  "model": "rife-v4.6", "threads": "1:4:4"},
}


# --------------------------------------------------------------------------- #
# Console utilities
# --------------------------------------------------------------------------- #

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


def status(msg, level="INFO"):
    c = {"INFO": (Color.info, "[*]"), "OK": (Color.ok, "[✓]"),
         "WARN": (Color.warn, "[!]"), "ERROR": (Color.error, "[x]")}
    cf, pr = c.get(level, (Color.info, "[*]"))
    print(f"{cf(_(pr))} {cf(msg)}", flush=True)


def _yes_words():
    lang = CONFIG.get("language", "en")
    return ("y", "yes", "sí", "si", "s") if lang == "es" else ("y", "yes")

def _no_words():
    lang = CONFIG.get("language", "en")
    return ("n", "no") if lang == "es" else ("n", "no")

def ask_yes_no(question, default=False):
    lang = CONFIG.get("language", "en")
    if lang == "es":
        sfx = f" {Color.bold('[S/n]')} " if default else f" {Color.bold('[s/N]')} "
        hint = _("Respond y (yes) or n (no).")
    else:
        sfx = f" {Color.bold('[Y/n]')} " if default else f" {Color.bold('[y/N]')} "
        hint = _("Respond y (yes) or n (no).")
    while True:
        try:
            resp = input(f"{Color.magenta('?')} {_(question)}{Color.dim(sfx)}").strip().lower()
        except EOFError:
            print()
            return default
        if not resp:
            return default
        if resp in _yes_words():
            return True
        if resp in _no_words():
            return False
        print(f"{Color.warn(_(hint))}")


def format_duration(seconds):
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}min"
    if m:
        return f"{m}min {s}s"
    return f"{s}s"


def format_fps(fps):
    if fps == int(fps):
        return str(int(fps))
    return f"{fps:.1f}"


def human_size(num_bytes):
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _clean_path_input(raw):
    s = raw.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"', "\u2018", "\u2019", "\u201c", "\u201d"):
        s = s[1:-1]
    return s.strip()


def _setup_path_completion():
    if not HAS_READLINE:
        return
    def completer(text, state):
        expanded = os.path.expanduser(text)
        if os.path.isdir(expanded) and not expanded.endswith(os.sep):
            expanded += os.sep
        dirname = os.path.dirname(expanded) or "."
        prefix = os.path.basename(expanded)
        try:
            entries = os.listdir(dirname)
        except OSError:
            entries = []
        matches = []
        for e in entries:
            if e.startswith(prefix):
                full = os.path.join(dirname, e)
                if os.path.isdir(full):
                    full += os.sep
                matches.append(full)
        matches.sort()
        try:
            return matches[state]
        except IndexError:
            return None
    readline.set_completer_delims(" \t\n")
    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")


# --------------------------------------------------------------------------- #
# Disk space checks
# --------------------------------------------------------------------------- #

def _check_disk_space(path, estimated_bytes):
    try:
        usage = shutil.disk_usage(path)
        if usage.free < estimated_bytes:
            status(
                f"{_('Low disk space on')} {path}: {human_size(usage.free)} {_('available,')} "
                f"{_('~')}{human_size(estimated_bytes)} {_('needed.')}",
                "WARN"
            )
            if usage.free < estimated_bytes * 0.3:
                status(_("Very low space. Aborting."), "ERROR")
                sys.exit(1)
            if not ask_yes_no(_("Continue anyway? (might fail if disk fills up)"), default=False):
                status(_("Operation cancelled."), "WARN")
                sys.exit(0)
    except OSError:
        pass


def _estimate_frame_storage(width, height, frame_count):
    return int(width * height * 3 * frame_count * 0.4)


# --------------------------------------------------------------------------- #
# Dependency management (Windows: sin sudo, sin gestores de paquetes Linux)
# --------------------------------------------------------------------------- #

def _download_and_extract(url, dest_dir, description="Downloading"):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "archive.zip"
        status(f"{_('Downloading')} {description}...")
        dl = DownloadProgress(_("Downloading"))
        try:
            urllib.request.urlretrieve(url, zip_path, reporthook=dl)
        except Exception as exc:
            status(f"{_('Download failed:')} {exc}", "ERROR")
            return False
        finally:
            dl.close()
        status(_("Extracting..."))
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dest_dir)
    return True


def _ensure_ffmpeg(auto_yes=False):
    global FFMPEG_BIN, FFPROBE_BIN
    if FFMPEG_PATH.is_file() and FFPROBE_PATH.is_file():
        FFMPEG_BIN = str(FFMPEG_PATH)
        FFPROBE_BIN = str(FFPROBE_PATH)
        return
    sys_ffmpeg = shutil.which("ffmpeg.exe") or shutil.which("ffmpeg")
    sys_ffprobe = shutil.which("ffprobe.exe") or shutil.which("ffprobe")
    if sys_ffmpeg and sys_ffprobe:
        FFMPEG_BIN = sys_ffmpeg
        FFPROBE_BIN = sys_ffprobe
        return
    status(_("ffmpeg/ffprobe not found locally or on system."), "WARN")
    url = FFMPEG_RELEASE_URLS.get("windows")
    if url and (auto_yes or ask_yes_no(_("Download ffmpeg now? (~120 MB)"), default=True)):
        ok = _download_and_extract(url, BASE_DIR / "deps" / "ffmpeg", "ffmpeg")
        if not ok:
            status(_("Could not download ffmpeg."), "ERROR")
            sys.exit(1)
        for f in (BASE_DIR / "deps" / "ffmpeg").rglob("ffmpeg.exe"):
            shutil.move(str(f), str(FFMPEG_PATH))
            break
        for f in (BASE_DIR / "deps" / "ffmpeg").rglob("ffprobe.exe"):
            shutil.move(str(f), str(FFPROBE_PATH))
            break
        if FFMPEG_PATH.is_file() and FFPROBE_PATH.is_file():
            FFMPEG_BIN = str(FFMPEG_PATH)
            FFPROBE_BIN = str(FFPROBE_PATH)
            return
    status(
        _("ffmpeg must be placed manually in:") + f"\n  {FFMPEG_PATH}\n  {FFPROBE_PATH}",
        "ERROR"
    )
    sys.exit(1)


def _ensure_rife(auto_yes=False):
    global RIFE_BIN
    if RIFE_PATH.is_file():
        RIFE_BIN = str(RIFE_PATH)
        return
    sys_rife = shutil.which("rife-ncnn-vulkan.exe") or shutil.which("rife-ncnn-vulkan")
    if sys_rife:
        RIFE_BIN = sys_rife
        return
    status(_("rife-ncnn-vulkan not found locally or on system."), "WARN")
    url = RIFE_RELEASE_URLS.get("windows")
    if url and (auto_yes or ask_yes_no(_("Download rife-ncnn-vulkan now? (~400 MB)"), default=True)):
        ok = _download_and_extract(url, BASE_DIR / "deps" / "rife", "rife-ncnn-vulkan")
        if not ok:
            status(_("Could not download rife-ncnn-vulkan."), "ERROR")
            sys.exit(1)
        for f in (BASE_DIR / "deps" / "rife").rglob("rife-ncnn-vulkan.exe"):
            shutil.move(str(f), str(RIFE_PATH))
            break
        if RIFE_PATH.is_file():
            RIFE_BIN = str(RIFE_PATH)
            return
    status(
        _("rife-ncnn-vulkan must be placed manually in:") + f"\n  {RIFE_PATH}",
        "ERROR"
    )
    sys.exit(1)


def _ensure_default_model(auto_yes=False):
    default_model = "rife-v4.6"
    model_dir = MODELS_DIR / default_model
    if model_dir.is_dir():
        return
    if not auto_yes and not ask_yes_no(f"{_('Download default model')} {default_model}?", default=True):
        status(f"{_('Default model')} {default_model} {_('not installed. Interpolation will fail if the model is missing.')}", "WARN")
        return
    status(f"{_('Installing default model')} {default_model}...")
    if not install_model(default_model):
        status(f"{_('Could not install')} {default_model}. {_('Interpolation will fail if the model is missing.')}", "WARN")


def install_model(model_name):
    model_dir = MODELS_DIR / model_name
    if model_dir.is_dir():
        return True
    status(f"{_('Downloading model')} {model_name}...")
    os_name = "windows"
    url = RIFE_RELEASE_URLS.get(os_name)
    if not url:
        status(_("No download URL for models on this platform."), "ERROR")
        return False
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "rife.zip"
        dl = DownloadProgress(_("Downloading"))
        try:
            urllib.request.urlretrieve(url, zip_path, reporthook=dl)
        except Exception as exc:
            status(f"{_('Download failed:')} {exc}", "ERROR")
            return False
        finally:
            dl.close()
        extract_dir = Path(tmpdir) / "extracted"
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
        source_dir = subdirs[0] if subdirs else extract_dir
        model_src = source_dir / model_name
        if not model_src.is_dir():
            status(f"{_('Model')} {model_name} {_('not found in release archive.')}", "ERROR")
            return False
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copytree(model_src, model_dir, dirs_exist_ok=True)
    return True


def detect_wmi_gpus():
    """Detecta GPUs vía WMI/PowerShell (reemplaza lspci de Linux)."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=15
        )
    except Exception:
        return []
    gpus = []
    for line in result.stdout.splitlines():
        name = line.strip()
        if not name:
            continue
        low = name.lower()
        if "nvidia" in low:
            vendor = "nvidia"
        elif "amd" in low or "radeon" in low or "ati " in low:
            vendor = "amd"
        elif "intel" in low:
            vendor = "intel"
        else:
            continue
        gpus.append((vendor, name))
    return gpus


def detect_vulkan_gpus():
    if shutil.which("vulkaninfo") is None:
        return []
    try:
        result = subprocess.run(["vulkaninfo", "--summary"], capture_output=True, text=True, timeout=15)
    except Exception:
        return []
    devices = []
    current_id = None
    for line in result.stdout.splitlines():
        m = re.match(r"\s*GPU(\d+)\s*:", line)
        if m:
            current_id = int(m.group(1))
            continue
        m2 = re.search(r"deviceName\s*=\s*(.+)", line)
        if m2 and current_id is not None:
            name = m2.group(1).strip()
            devices.append((current_id, name, classify_gpu(name)))
    if devices:
        return devices
    try:
        result2 = subprocess.run(["vulkaninfo", "--summary", "--json"], capture_output=True, text=True, timeout=15)
        data = json.loads(result2.stdout)
        for dev in data.get("devices", []):
            uid = dev.get("id", 0)
            name = dev.get("deviceName") or dev.get("properties", {}).get("deviceName", "Unknown")
            devices.append((uid, name, classify_gpu(name)))
    except Exception:
        pass
    return devices


def classify_gpu(name):
    n = name.lower()
    if any(k in n for k in ("rtx", "quadro", "tesla", "a100", "h100", "arc", "pro duo", "radeon rx")):
        return "discrete_high"
    if any(k in n for k in ("gtx", "geforce", "radeon pro", "radeon vii")):
        return "discrete"
    if any(k in n for k in (
        "vega", "uhd graphics", "iris", "hd graphics",
        "renoir", "cezanne", "rembrandt", "phoenix", "picasso",
        "raven", "vangogh", "aerith", "sephiroth",
        "strix", "hawk", "krackan",
        "lunar lake", "arrow lake", "battlemage",
    )):
        return "integrated"
    if re.search(r"radeon.*graphics", n):
        return "integrated"
    if any(k in n for k in ("intel", "amd", "radeon", "nvidia")):
        return "unknown"
    return "unknown"


def _check_vulkan_runtime():
    if shutil.which("vulkaninfo") is None:
        status(
            _("vulkaninfo not found (optional). GPU detection will rely on Windows device "
              "info; keep your GPU drivers up to date for best results."),
            "INFO"
        )


_DEPS_CHECKED = False

def ensure_dependencies(auto_yes=False):
    global FFMPEG_BIN, FFPROBE_BIN, RIFE_BIN, _DEPS_CHECKED
    if _DEPS_CHECKED:
        return True

    _ensure_ffmpeg(auto_yes=auto_yes)
    _ensure_rife(auto_yes=auto_yes)
    _ensure_default_model(auto_yes=auto_yes)

    if not FFMPEG_BIN:
        FFMPEG_BIN = str(FFMPEG_PATH)
    if not FFPROBE_BIN:
        FFPROBE_BIN = str(FFPROBE_PATH)
    if not RIFE_BIN:
        RIFE_BIN = str(RIFE_PATH)

    _check_vulkan_runtime()

    missing_critical = [n for n, b in (
        ("ffmpeg", FFMPEG_BIN), ("ffprobe", FFPROBE_BIN), ("rife-ncnn-vulkan", RIFE_BIN)
    ) if not b]
    if missing_critical:
        status(f"{_('Still missing critical dependencies:')} {', '.join(missing_critical)}", "ERROR")
        sys.exit(1)
    _DEPS_CHECKED = True
    return True


def choose_gpu_settings(width, height):
    devices = detect_vulkan_gpus()
    is_uhd_res = max(width, height) >= 3200
    cpus = os.cpu_count() or 4

    if not devices:
        wmi_gpus = detect_wmi_gpus()
        if wmi_gpus:
            priority = {"discrete_high": 0, "discrete": 1, "integrated": 2, "unknown": 3}
            classified = [(v, n, classify_gpu(n)) for v, n in wmi_gpus]
            classified.sort(key=lambda d: priority.get(d[2], 3))
            vendor, name, cls = classified[0]
            status(f"{_('Detected GPU')} (WMI): {name}", "INFO")
            ct = min(cpus, 8)
            if cls == "discrete_high":
                threads = f"2:{min(ct * 2, 8)}:{min(ct, 8)}"
            elif cls == "discrete":
                threads = f"1:{ct}:{min(ct, 4)}"
            else:
                threads = f"1:{min(ct, 2)}:{min(ct, 2)}"
            tile_size = 0
            if is_uhd_res:
                tile_size = 1024 if cls in ("discrete_high", "discrete") else 512
            hwaccel_map = {"nvidia": "cuda", "amd": "d3d11va", "intel": "qsv"}
            ffmpeg_gpu = {"hwaccel": hwaccel_map.get(vendor, "auto"), "hint": f" ({vendor})"}
            return {"gpu_id": None, "gpu_name": name, "threads": threads,
                    "uhd": is_uhd_res, "class": cls, "tile_size": tile_size,
                    "ffmpeg_gpu": ffmpeg_gpu}

        status(_("No GPU detected via Vulkan; using conservative settings."), "WARN")
        t = f"1:{min(cpus, 2)}:{min(cpus, 2)}"
        return {"gpu_id": None, "gpu_name": "not detected", "threads": t,
                "uhd": is_uhd_res, "class": "unknown", "tile_size": 0,
                "ffmpeg_gpu": {"hwaccel": "auto", "hint": ""}}

    priority = {"discrete_high": 0, "discrete": 1, "integrated": 2, "unknown": 3}
    sorted_devs = sorted(devices, key=lambda d: priority.get(d[2], 3))
    best = sorted_devs[0]
    gpu_id, name, cls = best

    ct = min(cpus, 16)
    if cls == "discrete_high":
        threads = f"2:{min(ct * 2, 16)}:{min(ct, 16)}"
    elif cls == "discrete":
        threads = f"1:{ct}:{min(ct, 4)}"
    else:
        threads = f"1:{min(ct, 2)}:{min(ct, 2)}"

    tile_size = 0
    if is_uhd_res:
        tile_size = 1024 if cls in ("discrete_high", "discrete") else 512

    ffmpeg_gpu = {"hwaccel": "auto", "hint": ""}
    multi_gpu = len(sorted_devs) > 1
    if "nvidia" in name.lower():
        ffmpeg_gpu = {"hwaccel": "cuda", "hint": " (NVIDIA)"}
    elif "amd" in name.lower() or "radeon" in name.lower():
        ffmpeg_gpu = {"hwaccel": "d3d11va", "hint": " (AMD)"}
    elif "intel" in name.lower():
        ffmpeg_gpu = {"hwaccel": "qsv", "hint": " (Intel)"}
    if ffmpeg_gpu["hint"]:
        prefix = _("Multi-GPU") if multi_gpu else _("RIFE on")
        status(f"{prefix}: {name}{ffmpeg_gpu['hint']}", "OK")

    return {"gpu_id": gpu_id, "gpu_name": name, "threads": threads,
            "uhd": is_uhd_res, "class": cls, "tile_size": tile_size,
            "ffmpeg_gpu": ffmpeg_gpu}


def estimate_duration(frame_count, width, height, gpu_class):
    base_rate = {"discrete_high": 12.0, "discrete": 6.0,
                 "integrated": 2.5, "unknown": 1.5}.get(gpu_class, 1.5)
    pixels = max(width * height, 1)
    scale = max(0.2, min(2073600 / pixels, 2.0))
    effective_rate = max(base_rate * scale, 0.1)
    return frame_count / effective_rate


# --------------------------------------------------------------------------- #
# Video probing
# --------------------------------------------------------------------------- #

def probe_video_file(path):
    if not path.is_file():
        return None

    cmd = [
        FFPROBE_BIN, "-v", "error",
        "-select_streams", "v:0",
        "-show_format", "-show_streams",
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None

    try:
        data = json.loads(result.stdout)
        streams = data.get("streams") or []
        if not streams:
            return None
        stream = streams[0]
        fmt = data.get("format", {})
        num, den = stream["r_frame_rate"].split("/")
        fps = (float(num) / float(den)) if float(den) != 0 else 0.0
    except (KeyError, IndexError, ValueError, json.JSONDecodeError):
        return None

    if fps <= 0:
        fps = 30.0
        status(_("Detected FPS as 0 (VFR or unusual format). Assuming 30 fps."), "WARN")

    try:
        nb = stream.get("nb_frames")
        if nb and nb != "N/A":
            frame_count = int(nb)
        else:
            frame_count = int(fps * float(fmt.get("duration", 0.0) or 0.0))
    except (ValueError, TypeError):
        frame_count = 0

    audio_cmd = [
        FFPROBE_BIN, "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index", "-of", "csv=p=0", str(path),
    ]
    audio_result = subprocess.run(audio_cmd, capture_output=True, text=True)
    audio_tracks = [t for t in audio_result.stdout.strip().split("\n") if t.strip()]

    return {
        "path": path,
        "extension": path.suffix.lower() or "(no extension)",
        "container": fmt.get("format_long_name", "unknown"),
        "codec": stream.get("codec_name", "unknown"),
        "width": int(stream.get("width", 0)),
        "height": int(stream.get("height", 0)),
        "fps": fps,
        "frame_count": frame_count,
        "duration": float(fmt.get("duration", 0.0) or 0.0),
        "size_bytes": int(fmt.get("size", 0) or 0),
        "has_audio": len(audio_tracks) > 0,
        "audio_tracks": len(audio_tracks),
    }


def print_video_metadata(info):
    print()
    status(f"{_('Valid video:')} {Color.bold(info['path'].name)}", "OK")
    print(f"    {Color.dim(_('Container'))}  : {info['container']} ({info['extension']})")
    print(f"    {Color.dim(_('Codec'))}       : {info['codec']}")
    print(f"    {Color.dim(_('Resolution'))}  : {Color.bold(f'{info['width']}x{info['height']}')}")
    print(f"    {Color.dim(_('Current FPS'))}  : {format_fps(info['fps'])}")
    print(f"    {Color.dim(_('Duration'))}    : {format_duration(info['duration'])}")
    print(f"    {Color.dim(_('Size'))}      : {human_size(info['size_bytes'])}")
    audio_str = f"{_('yes')} ({info['audio_tracks']} {_('tracks')})" if info['has_audio'] else _("no")
    print(f"    {Color.dim(_('Audio'))}       : {audio_str}")
    print()


# --------------------------------------------------------------------------- #
# Frame extraction
# --------------------------------------------------------------------------- #

def extract_frames(video_path, frames_dir, info=None, gpu_settings=None):
    if info:
        w = max(info.get("width", 1920), 1920)
        h = max(info.get("height", 1080), 1080)
        fc = max(info.get("frame_count", 18000) or int(info.get("fps", 30) * info.get("duration", 600)), 100)
        estimated = _estimate_frame_storage(w, h, fc)
        _check_disk_space(frames_dir, estimated)

    total_est = info["frame_count"] if info else 0

    cmd = [
        FFMPEG_BIN, "-y",
        "-threads", "auto",
        "-i", str(video_path),
        "-vsync", "0",
        str(frames_dir / "%08d.png"),
    ]
    if total_est:
        if HAS_TQDM:
            pbar = tqdm(total=total_est, desc=_("Extracting frames"), unit="frame", bar_format="{l_bar}{bar:30}{r_bar}")
        else:
            pbar = ProgressBar(total=total_est, desc=_("Extracting frames"), unit="frame", width=35)
        stop_event = threading.Event()
        watcher = threading.Thread(
            target=_watch_progress_proc, args=(frames_dir, total_est, stop_event, pbar), daemon=True
        )
        watcher.start()

    result = subprocess.run(cmd, capture_output=True, text=True)

    if total_est:
        stop_event.set()
        watcher.join()
        pbar.close()

    if result.returncode != 0:
        status(f"{_('Error extracting frames:')}\n{result.stderr[-2000:]}", "ERROR")
        sys.exit(1)

    extracted = _count_files(frames_dir, "*.png")
    if extracted == 0:
        status(_("No frames extracted. Aborting."), "ERROR")
        sys.exit(1)
    return extracted


def _count_files(directory, pattern="*"):
    if pattern == "*":
        return len(os.listdir(str(directory)))
    count = 0
    for _ in Path(directory).glob(pattern):
        count += 1
    return count


# --------------------------------------------------------------------------- #
# RIFE interpolation
# --------------------------------------------------------------------------- #

def _model_supports_custom_frame_count(model):
    return model.startswith("rife-v4")


def _watch_progress_proc(output_dir, target_frames, stop_event, pbar):
    last_count = 0
    while not stop_event.is_set():
        current = _count_files(output_dir, "*.png")
        if current > last_count:
            pbar.update(current - last_count)
            last_count = current
        time.sleep(0.8)
    current = _count_files(output_dir, "*.png")
    if current > last_count:
        pbar.update(current - last_count)


def run_interpolation(
    in_frames_dir, out_frames_dir, model, threads,
    source_frame_count, source_fps, target_fps,
    gpu_id=None, uhd=False, tile_size=0
):
    supports_n = _model_supports_custom_frame_count(model)
    if supports_n:
        target_frame_count = max(
            source_frame_count, round(source_frame_count * (target_fps / source_fps))
        )
        actual_output_fps = source_fps * (target_frame_count / source_frame_count)
    else:
        target_frame_count = source_frame_count * 2
        actual_output_fps = source_fps * 2
        if abs(actual_output_fps - target_fps) > 0.01:
            status(f"{_('Model')} '{model}' {_('only supports 2x frame rate.')}", "WARN")
            status(f"{_('Output will be at')} {actual_output_fps:.3f} fps {_('instead.')}", "WARN")

    cmd = [
        RIFE_BIN,
        "-i", str(in_frames_dir),
        "-o", str(out_frames_dir),
        "-m", str(MODELS_DIR / model),
        "-j", threads,
    ]
    if supports_n:
        cmd += ["-n", str(target_frame_count)]
    if gpu_id is not None:
        cmd += ["-g", str(gpu_id)]
    if uhd:
        cmd += ["-u"]
    if tile_size > 0:
        cmd += ["-t", str(tile_size)]

    desc = _("Interpolating")
    if HAS_TQDM:
        pbar = tqdm(total=target_frame_count, desc=Color.bold(desc), unit="frame", bar_format="{l_bar}{bar:30}{r_bar}")
    else:
        pbar = ProgressBar(total=target_frame_count, desc=desc, unit="frame", width=35)

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    stop_event = threading.Event()
    watcher = threading.Thread(
        target=_watch_progress_proc, args=(out_frames_dir, target_frame_count, stop_event, pbar), daemon=True
    )
    watcher.start()

    output_lines = []
    for line in process.stdout:
        output_lines.append(line.rstrip())

    process.wait()
    stop_event.set()
    watcher.join()
    pbar.close()

    if process.returncode != 0:
        status(_("RIFE completed with error."), "ERROR")
        for line in output_lines[-20:]:
            status(f"    {line}", "ERROR")
        sys.exit(1)

    result_frames = _count_files(out_frames_dir, "*.png")
    print(f"{Color.ok(_('[✓]'))} {_('Interpolation complete:')} {Color.bold(str(result_frames))} {_('frames generated')}", flush=True)
    return actual_output_fps


# --------------------------------------------------------------------------- #
# Video reassembly
# --------------------------------------------------------------------------- #

_ENCODER_CACHE = None

def _detect_available_encoders():
    global _ENCODER_CACHE
    if _ENCODER_CACHE is not None:
        return _ENCODER_CACHE
    try:
        r = subprocess.run([FFMPEG_BIN, "-encoders"], capture_output=True, text=True, timeout=5)
        _ENCODER_CACHE = re.findall(r"^\s*V.{5}\s+(\S+)", r.stdout, re.MULTILINE)
        return _ENCODER_CACHE
    except Exception:
        return []


def _detect_gpu_vendors():
    vendors = set()
    for _, name, _ in detect_vulkan_gpus():
        n = name.lower()
        if "nvidia" in n or "geforce" in n or "quadro" in n or "rtx" in n or "gtx" in n:
            vendors.add("nvidia")
        if "intel" in n or "uhd" in n or "iris" in n:
            vendors.add("intel")
        if "amd" in n or "radeon" in n:
            vendors.add("amd")
    for vendor, _ in detect_wmi_gpus():
        vendors.add(vendor)
    return vendors

def _pick_best_encoder(preferred="libx264"):
    available = _detect_available_encoders()
    vendors = _detect_gpu_vendors()

    # User explicitly chose -> respect it
    vp = CONFIG.get("video_preset", "")
    if vp == "custom" and preferred in available:
        return ENCODER_PRESETS[preferred]

    # Prefer hardware encoding matching actual GPU
    if preferred in ("libx264", "libx265") and vendors:
        hw_map = [
            ("nvidia", ["h264_nvenc", "hevc_nvenc"]),
            ("amd",    ["h264_amf", "hevc_amf"]),
            ("intel",  ["h264_qsv", "hevc_qsv"]),
        ]
        for vendor, encs in hw_map:
            if vendor in vendors:
                for name in encs:
                    if name in available:
                        return ENCODER_PRESETS[name]

    # Fallback to preferred
    if preferred in ENCODER_PRESETS:
        return ENCODER_PRESETS[preferred]

    return ENCODER_PRESETS["libx264"]


def reassemble_video(
    out_frames_dir, original_video, target_fps,
    has_audio, output_path, result_frames,
    encoder_name="libx264", crf=18, preset="medium",
    gpu_settings=None
):
    enc = _pick_best_encoder(encoder_name)
    video_duration = result_frames / target_fps
    ffmpeg_hw = (gpu_settings or {}).get("ffmpeg_gpu", {}).get("hwaccel") or enc["hwaccel"]

    cmd = [FFMPEG_BIN, "-y"]
    if ffmpeg_hw:
        cmd += ["-hwaccel", ffmpeg_hw, "-threads", "auto"]
    else:
        cmd += ["-threads", "auto"]
    cmd += ["-r", str(target_fps), "-i", str(out_frames_dir / "%08d.png")]

    if has_audio:
        cmd += ["-i", str(original_video)]

    cmd += ["-map", "0:v:0"]
    if has_audio:
        cmd += ["-map", "1:a:0"]

    cmd += ["-c:v", enc["codec"]]
    if enc["codec"] in ("libx264", "libx265"):
        cmd += ["-crf", str(crf), "-preset", preset]
    elif enc["codec"] in ("h264_amf", "hevc_amf"):
        cmd += ["-rc", "cqp", "-qp_i", str(crf), "-qp_p", str(crf)]
    else:
        cmd += ["-cq", str(crf)]
    cmd += ["-pix_fmt", enc["pix_fmt"]]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-t", str(video_duration)]
    cmd += [str(output_path)]

    sp = Spinner(_("Encoding video"))
    cmd_prog = [FFMPEG_BIN, "-y", "-progress", "pipe:1"] + cmd[2:]
    process = subprocess.Popen(cmd_prog, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    time_re = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")

    stderr_buf = []
    stderr_lock = threading.Lock()
    def _read_stderr():
        while True:
            chunk = process.stderr.read(65536)
            if not chunk:
                break
            with stderr_lock:
                stderr_buf.append(chunk)
                while len(stderr_buf) > 20:
                    stderr_buf.pop(0)
    stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
    stderr_thread.start()

    time_elapsed = 0
    spinner_timeout = 10
    last_update = time.time()
    for line in process.stdout:
        m = time_re.search(line)
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            frac = m.group(4).ljust(6, "0")[:6]
            time_elapsed = h * 3600 + mi * 60 + s + int(frac) / 1000000
            sp.tick()
            while time.time() - last_update > spinner_timeout:
                sp.tick()
                last_update = time.time()

    process.wait()
    stderr_thread.join(timeout=3)

    if process.returncode != 0 and enc["codec"] != "libx264":
        tail = "".join(stderr_buf)
        available = _detect_available_encoders()
        candidates = []
        for n in ("libx264", "libx265"):
            if n in ENCODER_PRESETS and n in available:
                candidates.append(n)
        for n in available:
            if n in ENCODER_PRESETS and n not in candidates:
                candidates.append(n)
        if not candidates:
            status(f"{_('No usable encoder found.')}\n{tail[-2000:]}", "ERROR")
            sys.exit(1)

        for fb_name in candidates:
            enc = ENCODER_PRESETS[fb_name]
            ffmpeg_hw = None
            cmd = [FFMPEG_BIN, "-y", "-threads", "auto",
                   "-r", str(target_fps), "-i", str(out_frames_dir / "%08d.png")]
            if has_audio:
                cmd += ["-i", str(original_video)]
            cmd += ["-map", "0:v:0"]
            if has_audio:
                cmd += ["-map", "1:a:0"]
            cmd += ["-c:v", enc["codec"], "-crf", str(crf), "-preset", preset,
                    "-pix_fmt", enc["pix_fmt"]]
            if has_audio:
                cmd += ["-c:a", "aac", "-b:a", "192k"]
            cmd += ["-t", str(video_duration), str(output_path)]
            sp = Spinner(_(f"Trying encoder {fb_name}..."))
            cmd_prog = [FFMPEG_BIN, "-y", "-progress", "pipe:1"] + cmd[2:]
            process = subprocess.Popen(cmd_prog, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            stderr_buf = []
            stderr_lock = threading.Lock()
            def _read_stderr2():
                while True:
                    chunk = process.stderr.read(65536)
                    if not chunk:
                        break
                    with stderr_lock:
                        stderr_buf.append(chunk)
                        while len(stderr_buf) > 20:
                            stderr_buf.pop(0)
            stderr_thread = threading.Thread(target=_read_stderr2, daemon=True)
            stderr_thread.start()
            for line in process.stdout:
                m = time_re.search(line)
                if m:
                    h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    frac = m.group(4).ljust(6, "0")[:6]
                    time_elapsed = h * 3600 + mi * 60 + s + int(frac) / 1000000
                    sp.tick()
                    while time.time() - last_update > spinner_timeout:
                        sp.tick()
                        last_update = time.time()
            process.wait()
            stderr_thread.join(timeout=3)
            if process.returncode == 0:
                break
            status(_(f"Encoder {fb_name} failed."), "WARN")
            tail = "".join(stderr_buf)

    if process.returncode != 0:
        status(f"{_('Error reassembling video:')}\n{tail[-3000:]}", "ERROR")
        sys.exit(1)

    sp.ok(_("Encoding video"))


# --------------------------------------------------------------------------- #
# Temp management (Windows: sin /proc, /dev/shm ni tmpfs; usa %TEMP%)
# --------------------------------------------------------------------------- #

_temp_managers = []


class TempManager:
    def __init__(self, estimated_bytes=0):
        cache_dir = CACHE_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)
        if estimated_bytes > 0:
            _check_disk_space(cache_dir, int(estimated_bytes * 2.5))

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




# --------------------------------------------------------------------------- #
# Output path
# --------------------------------------------------------------------------- #

def build_default_output_name(input_path, target_fps):
    fps_label = str(int(target_fps)) if target_fps == int(target_fps) else f"{target_fps}".replace(".", "_")
    return f"ENHANCED_{fps_label}FPS_{input_path.name}"


def resolve_output_path(raw, input_path, target_fps):
    default_name = build_default_output_name(input_path, target_fps)
    raw = _clean_path_input(raw)

    enhanced_dir = VIDEOS_DIR / "enhanced"
    enhanced_dir.mkdir(parents=True, exist_ok=True)

    if not raw:
        return enhanced_dir / default_name
    out_path = Path(raw).expanduser().resolve()
    if out_path.is_dir():
        return out_path / default_name
    if out_path.suffix == "":
        out_path.mkdir(parents=True, exist_ok=True)
        return out_path / default_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return out_path


# --------------------------------------------------------------------------- #
# Interactive wizard
# --------------------------------------------------------------------------- #

def prompt_for_video():
    videos_dir = VIDEOS_DIR / "original"

    if not videos_dir.exists():
        videos_dir.mkdir(parents=True, exist_ok=True)

    video_files = [f for f in videos_dir.iterdir() if f.is_file()]
    video_files = [f for f in video_files if f.suffix.lower() in ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv')]

    if not video_files:
        print(f"\n{Color.bold(_('Select video to enhance - (b to go back)'))}")
        print(f"{Color.warn(_('No videos found in videos/original/'))}")
        print(f"{Color.dim(_('Place your videos in the videos/original/ folder to process them.'))}")
        print()
        try:
            raw = input(f"{Color.magenta('▸')} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw.lower() in ("b", "back", "←"):
            return None
        return None

    video_names = [f.name for f in video_files]

    print(f"\n{Color.bold(_('Select video to enhance - (b to go back)'))}")
    print(f"{Color.dim(_('Videos in videos/original/:'))}")

    if sys.stdin.isatty() and HAS_MSVCRT:
        i = _interactive_select_video(video_names)
        if i < 0 or i >= len(video_files):
            return None
        selected_video = video_files[i]
    else:
        for i, name in enumerate(video_names, 1):
            print(f"  {i}. {name}")
        try:
            raw = input(f"{Color.magenta('▸')} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw.lower() in ("b", "back", "←"):
            return None
        try:
            i = int(raw) - 1
            if i < 0 or i >= len(video_files):
                print(f"{Color.warn(_('Enter a number between 1 and'))} {len(video_files)}.")
                return None
            selected_video = video_files[i]
        except ValueError:
            print(f"{Color.warn(_('Enter a valid number.'))}")
            return None

    sp = Spinner(_("Verifying video file..."))
    info = probe_video_file(selected_video)
    if info is None:
        sp.ok(f"{Color.warn(_('Not a processable video file.'))}")
        return None
    sp.ok(f"{Color.info(_('Video'))}: {Color.bold(selected_video.name)}, {_('FPS')}: {format_fps(info['fps'])}, {_('Resolution')}: {info['width']}x{info['height']}, {_('Duration')}: {format_duration(info['duration'])}, {_('Size')}: {human_size(info['size_bytes'])}")

    info['path'] = selected_video
    return info


def prompt_for_fps(source_fps):
    print(f"\n{Color.bold(_('Target FPS'))}")
    common = [30, 60, 120]
    while True:
        try:
            raw = input(f"{Color.magenta('▸')} ").strip().replace(",", ".")
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw.lower() in ("b", "back", "←"):
            return None
        try:
            fps = float(raw)
        except ValueError:
            print(f"{Color.warn(_('Enter a valid number.'))}")
            continue
        if fps <= 0:
            print(f"{Color.warn(_('FPS must be greater than 0.'))}")
            continue
        if fps > 240:
            if not ask_yes_no(f"{fps} {_('is very high. Are you sure?')}", default=False):
                continue
        if fps <= source_fps:
            if not ask_yes_no(
                f"{fps} {_('is not higher than the current framerate (')}{format_fps(source_fps)}). {_('Continue anyway?')}",
                default=False,
            ):
                continue
        return fps


def prompt_for_output(input_path, target_fps):
    return resolve_output_path("", input_path, target_fps)


def run_pipeline(info, target_fps, output_path, gpu_settings, model=None):
    start_time = time.time()
    user_model = model is not None
    if model is None:
        model = CONFIG.get("model", DEFAULT_CONFIG["model"])
    vp = CONFIG.get("video_preset")
    config_rife_threads = CONFIG.get("rife_threads")
    if vp and vp in PRESETS:
        pv = PRESETS[vp]
        if not user_model:
            model = pv.get("model", model)
        rife_threads = config_rife_threads or pv.get("threads") or gpu_settings["threads"]
        rife_tile_size = pv.get("tile_size") or gpu_settings.get("tile_size", 0)
    else:
        rife_threads = config_rife_threads or gpu_settings["threads"]
        rife_tile_size = gpu_settings.get("tile_size", 0)
    model_dir = MODELS_DIR / model
    if not model_dir.is_dir():
        status(f"{_('Model')} {model} {_('not found. Downloading...')}")
        if not install_model(model):
            status(f"{_('Model')} {model} {_('is required but could not be installed.')}", "ERROR")
            return False

    sp = Spinner(_("Preparing..."))
    w = max(info.get("width", 1920), 1920)
    h = max(info.get("height", 1080), 1080)
    fc = max(info.get("frame_count", 18000) or int(info.get("fps", 30) * info.get("duration", 600)), 100)
    estimated = _estimate_frame_storage(w, h, fc)
    tmp = TempManager(estimated_bytes=estimated)
    sp.ok(_("Prepared"))

    sp = Spinner(_("Extracting frames..."))
    frame_count = extract_frames(info["path"], tmp.in_frames_dir, info, gpu_settings)
    sp.ok(_("Frames extracted"))

    sp = Spinner(_("Interpolating frames..."))
    actual_fps = run_interpolation(
        in_frames_dir=tmp.in_frames_dir,
        out_frames_dir=tmp.out_frames_dir,
        model=model,
        threads=rife_threads,
        source_frame_count=frame_count,
        source_fps=info["fps"],
        target_fps=target_fps,
        gpu_id=gpu_settings["gpu_id"],
        uhd=gpu_settings["uhd"],
        tile_size=rife_tile_size,
    )

    sp = Spinner(_("Reassembling video..."))
    result_frames = _count_files(tmp.out_frames_dir, "*.png")
    reassemble_video(
        out_frames_dir=tmp.out_frames_dir,
        original_video=info["path"],
        target_fps=actual_fps,
        has_audio=info["has_audio"],
        output_path=output_path,
        result_frames=result_frames,
        encoder_name=CONFIG.get("encoder", DEFAULT_CONFIG["encoder"]),
        crf=CONFIG.get("crf", DEFAULT_CONFIG["crf"]),
        preset=CONFIG.get("preset", DEFAULT_CONFIG["preset"]),
        gpu_settings=gpu_settings,
    )

    tmp.cleanup()
    elapsed = time.time() - start_time
    status(
        f"{_('Video exported successfully in')} {format_duration(elapsed)} "
        f"{_('saved to:')} {output_path}",
        "OK",
    )
    return True


def interactive_wizard():
    print(f"\n{Color.bold(_('=== LocallyFPS'))} - v{APP_VERSION} ===\n")
    sp = Spinner(_("Checking system dependencies..."))
    ensure_dependencies()
    sp.ok(_("All dependencies ready"))

    while True:
        menu_items = [
            _("Enhance video"),
            _("Settings"),
            _("Exit"),
        ]
        i = _interactive_select("", menu_items)
        if i == 0:
            pass
        elif i == 1:
            _run_settings()
            continue
        else:
            sys.exit(0)

        info = prompt_for_video()
        if info is None:
            continue
        gpu_settings = choose_gpu_settings(info["width"], info["height"])
        target_fps = prompt_for_fps(info["fps"])
        if target_fps is None:
            continue
        output_path = prompt_for_output(info["path"], target_fps)
        if output_path is None:
            continue

        run_pipeline(info, target_fps, output_path, gpu_settings)
        print()


# --------------------------------------------------------------------------- #
# CLI mode
# --------------------------------------------------------------------------- #

def parse_args():
    parser = argparse.ArgumentParser(
        description=_("LocallyFPS – frame interpolation for video using RIFE AI models.")
    )
    parser.add_argument("input", nargs="?", type=str, help=_("Input video path"))
    parser.add_argument("--target-fps", type=float, default=60.0, help=_("Target FPS (default: 60)"))
    parser.add_argument("--model", type=str, default=None, help=_("RIFE model (default: rife-v4.6)"))
    parser.add_argument("--threads", type=str, default=None, help=_("Threads load:proc:save (default: auto based on GPU)"))
    parser.add_argument("--gpu-id", type=int, default=None, help=_("Vulkan GPU ID to use (default: auto)"))
    parser.add_argument("--uhd", action="store_true", help=_("Force UHD mode (recommended for 4K+)"))
    parser.add_argument("--output", type=str, default=None, help=_("Output path (default: ENHANCED_fpsFPS_filename)"))
    parser.add_argument("--yes", action="store_true", help=_("Skip interactive confirmation"))
    parser.add_argument("--config", action="store_true", help=_("Open settings menu"))
    return parser.parse_args()


def main_cli(args):
    if args.config:
        _run_settings()
        return

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        status(f"{_('The input file does not exist:')} {input_path}", "ERROR")
        sys.exit(1)

    ensure_dependencies()
    info = probe_video_file(input_path)
    if info is None:
        status(_("Not a processable video file."), "ERROR")
        sys.exit(1)
    print_video_metadata(info)

    gpu_settings = choose_gpu_settings(info["width"], info["height"])
    if args.threads:
        gpu_settings["threads"] = args.threads
    if args.gpu_id is not None:
        gpu_settings["gpu_id"] = args.gpu_id
    if args.uhd:
        gpu_settings["uhd"] = True

    output_path = resolve_output_path(args.output or "", input_path, args.target_fps)
    if output_path.exists() and not args.yes:
        if not ask_yes_no(f"{_('Already exists:')} {output_path.name}. {_('Overwrite?')}"):
            status(_("Output file exists. Skipped."), "WARN")
            return False

    return run_pipeline(
        info,
        args.target_fps,
        output_path,
        gpu_settings,
        model=args.model,
    )


def main():
    _enable_windows_ansi()
    _ensure_dirs()
    _load_config()
    _load_translations()
    _setup_path_completion()

    is_first_run = not CONFIG_PATH.exists() or "language" not in CONFIG
    if is_first_run:
        _run_language_wizard()

    if sys.stdout.isatty() and _any_dep_missing():
        if ask_yes_no(_("Do you want to install all missing dependencies?"), default=True):
            sp = Spinner(_("Installing dependencies..."))
            ensure_dependencies(auto_yes=True)
            sp.ok(_("All dependencies ready"))

    args = parse_args()

    if args.config:
        if not sys.stdout.isatty():
            print(_("Settings menu requires an interactive terminal."), file=sys.stderr)
            print(f"{_('Edit the config file directly:')} {CONFIG_PATH}", file=sys.stderr)
            sys.exit(1)
        _run_settings()
        return

    if args.input:
        main_cli(args)
    else:
        interactive_wizard()


if __name__ == "__main__":
    main()
