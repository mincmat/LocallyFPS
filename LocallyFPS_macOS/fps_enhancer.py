#!/usr/bin/env python3
"""
fps_enhancer.py – AI frame interpolation for video using rife-ncnn-vulkan.
macOS Edition — portable version with local dependencies.
"""

import argparse
import atexit
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
    import readline
    HAS_READLINE = True
except ImportError:
    HAS_READLINE = False

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


# --------------------------------------------------------------------------- #
# Portable paths
# --------------------------------------------------------------------------- #

FFMPEG_BIN = BASE_DIR / "deps" / "ffmpeg" / "ffmpeg"
FFPROBE_BIN = BASE_DIR / "deps" / "ffmpeg" / "ffprobe"
RIFE_BIN = BASE_DIR / "deps" / "rife" / "rife-ncnn-vulkan"
MODELS_DIR = BASE_DIR / "models"
CACHE_DIR = BASE_DIR / "cache"
CONFIG_DIR = BASE_DIR / "config"
VIDEOS_DIR = BASE_DIR / "videos"

_FFMPEG_DIR = BASE_DIR / "deps" / "ffmpeg"
_RIFE_DIR = BASE_DIR / "deps" / "rife"

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
    _FFMPEG_DIR, _RIFE_DIR,
    MODELS_DIR, CACHE_DIR, CONFIG_DIR,
    VIDEOS_DIR / "original", VIDEOS_DIR / "enhanced",
]


def _ensure_dirs():
    for d in _REQUIRED_DIRS:
        d.mkdir(parents=True, exist_ok=True)


def _any_dep_missing():
    return (
        not (FFMPEG_BIN.is_file() or shutil.which("ffmpeg"))
        or not (FFPROBE_BIN.is_file() or shutil.which("ffprobe"))
        or not (RIFE_BIN.is_file() or shutil.which("rife-ncnn-vulkan"))
        or not (MODELS_DIR / "rife-v4.6").is_dir()
    )


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

CONFIG_PATH = CONFIG_DIR / "settings.json"

DEFAULT_CONFIG = {
    "language": "en",
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
            options.append(f"\u25b2 {_('Advanced')}")
        else:
            adv_start = None
            toggle_idx = len(options)
            options.append(f"{_('Advanced')} \u25b8")
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
                    v = input(f"{Color.magenta('\u25b8')} ").strip()
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
# Color
# --------------------------------------------------------------------------- #

class Color:
    bold = "\033[1m".__add__
    dim = "\033[2m".__add__
    ok = "\033[92m".__add__
    warn = "\033[93m".__add__
    error = "\033[91m".__add__
    magenta = "\033[95m".__add__
    cyan = "\033[96m".__add__
    end = "\033[0m"

    @staticmethod
    def _tag(color, label, text):
        sys.stdout.write(f"  {color}{label}{Color.end} {text}\n")
        sys.stdout.flush()

    @staticmethod
    def ok(text, label="OK"):
        Color._tag(Color.ok, label, text)
    @staticmethod
    def warn(text, label="WARN"):
        Color._tag(Color.warn, label, text)
    @staticmethod
    def error(text, label="ERROR"):
        Color._tag(Color.error, label, text)


def status(text, level="INFO"):
    fn = {"OK": Color.ok, "WARN": Color.warn, "ERROR": Color.error}.get(level, Color.ok if level == "OK" else print)
    if level in ("OK", "WARN", "ERROR"):
        fn(text, level)
    else:
        print(f"  {text}", flush=True)


# --------------------------------------------------------------------------- #
# Progress
# --------------------------------------------------------------------------- #

class Spinner:
    _chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    def __init__(self, text=""):
        self.text = text
        self._running = False
        self._t = None
        self._start()

    def _spin(self):
        i = 0
        while self._running:
            sys.stdout.write(f"\r  {self._chars[i]} {self.text}")
            sys.stdout.flush()
            i = (i + 1) % len(self._chars)
            time.sleep(0.08)
        sys.stdout.write(f"\r{' ' * 80}\r")
        sys.stdout.flush()

    def _start(self):
        self._running = True
        self._t = threading.Thread(target=self._spin, daemon=True)
        self._t.start()

    def ok(self, text=None):
        self._running = False
        if self._t:
            self._t.join(0.5)
        sys.stdout.write(f"\r{' ' * 80}\r")
        if text is not None:
            print(f"  {Color.ok('\u2713')} {text}", flush=True)


class ProgressBar:
    def __init__(self, total, desc="", unit="item", width=35):
        self.total = total
        self.desc = desc
        self.unit = unit
        self.width = width
        self.n = 0
        self._last = 0

    def update(self, n=1):
        self.n += n
        if time.time() - self._last < 0.15:
            return
        self._last = time.time()
        self._draw()

    def _draw(self):
        pct = self.n / self.total if self.total else 0
        filled = int(self.width * pct)
        bar = "\u2588" * filled + "\u2591" * (self.width - filled)
        sys.stdout.write(f"\r  {self.desc}: |{bar}| {self.n}/{self.total} {self.unit}")
        sys.stdout.flush()

    def close(self):
        self._draw()
        sys.stdout.write("\n")
        sys.stdout.flush()


class DownloadProgress:
    def __init__(self, desc="Downloading"):
        self.desc = desc
        self._seen = 0
        self._last = 0
        self._pbar = None
        if HAS_TQDM:
            self._pbar = tqdm(desc=desc, unit="B", unit_scale=True, unit_divisor=1024, bar_format="{l_bar}{bar:20}{r_bar}")
    def __call__(self, blocks, block_size, total_size):
        self._seen += block_size
        now = time.time()
        if now - self._last < 0.2 and self._seen < total_size:
            return
        self._last = now
        if self._pbar:
            self._pbar.total = total_size
            self._pbar.update(block_size)
        else:
            pct = self._seen / total_size * 100 if total_size else 0
            sys.stdout.write(f"\r  {self.desc}: {pct:.0f}% ({self._seen / 1024 / 1024:.1f} MB)")
            sys.stdout.flush()
    def close(self):
        if self._pbar:
            self._pbar.close()
        else:
            sys.stdout.write("\n")
            sys.stdout.flush()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def ask_yes_no(prompt, default=True):
    opts = f"[{'Y' if default else 'y'}/{'n' if default else 'N'}]"
    while True:
        try:
            resp = input(f"  {Color.bold(prompt)} {opts} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if not resp:
            return default
        if resp in ("y", "yes", "s", "si", "sí"):
            return True
        if resp in ("n", "no"):
            return False


# --------------------------------------------------------------------------- #
# Interactive selection (arrow-key navigation)
# --------------------------------------------------------------------------- #

def _interactive_select(prompt, options):
    n = len(options)
    if n == 0:
        return -1

    if not sys.stdin.isatty():
        print(f"\n{Color.bold(prompt)}")
        for i, opt in enumerate(options):
            print(f"  {i+1}. {opt}")
        while True:
            try:
                resp = input(f"{Color.magenta('\u25b8')} ").strip()
                if resp:
                    idx = int(resp) - 1
                    if 0 <= idx < n:
                        return idx
            except (ValueError, EOFError):
                pass
            print(f"{Color.warn(_('Enter a number between 1 and'))} {n}.")

    import termios, tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    idx = 0
    try:
        tty.setraw(fd)
        sys.stdout.write(f"\r{Color.bold(prompt)}\r\n")
        for i, opt in enumerate(options):
            sys.stdout.write(f"\r  {'\u25b8' if i == idx else ' '} {opt}\r\n")
        sys.stdout.flush()
        while True:
            ch = sys.stdin.read(1)
            if ch == "\x03":
                termios.tcsetattr(fd, termios.TCSANOW, old)
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                sys.exit(130)
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                if seq == "[A":
                    idx = (idx - 1) % n
                elif seq == "[B":
                    idx = (idx + 1) % n
                sys.stdout.write(f"\x1b[{n}A")
                for i, opt in enumerate(options):
                    sys.stdout.write(f"\r  {'\u25b8' if i == idx else ' '} {opt}\x1b[K\r\n")
                sys.stdout.flush()
            elif ch == "\r":
                total = n + 1
                sys.stdout.write(f"\x1b[{total}A")
                for i in range(total):
                    sys.stdout.write("\r\x1b[K\x1b[B")
                sys.stdout.write(f"\x1b[{total}A")
                sys.stdout.flush()
                break
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, old)
    sys.stdout.flush()
    return idx


def _interactive_select_video(options):
    n = len(options)
    if n == 0:
        return -1

    import termios, tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    idx = 0
    try:
        tty.setraw(fd)
        for i, opt in enumerate(options):
            sys.stdout.write(f"  {'\u25b8' if i == idx else ' '} {opt}\r\n")
        sys.stdout.flush()
        while True:
            ch = sys.stdin.read(1)
            if ch == "\x03":
                termios.tcsetattr(fd, termios.TCSANOW, old)
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                sys.exit(130)
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                if seq == "[A":
                    idx = (idx - 1) % n
                elif seq == "[B":
                    idx = (idx + 1) % n
                sys.stdout.write(f"\x1b[{n}A")
                for i, opt in enumerate(options):
                    sys.stdout.write(f"\r  {'\u25b8' if i == idx else ' '} {opt}\x1b[K\r\n")
                sys.stdout.flush()
            elif ch == "\r":
                total = n
                sys.stdout.write(f"\x1b[{total}A")
                for i in range(total):
                    sys.stdout.write("\r\x1b[K\x1b[B")
                sys.stdout.write(f"\x1b[{total}A")
                sys.stdout.flush()
                break
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, old)
    sys.stdout.flush()
    return idx


# --------------------------------------------------------------------------- #
# Path completion
# --------------------------------------------------------------------------- #

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
# rife-ncnn-vulkan paths (portable)
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# macOS GPU detection
# --------------------------------------------------------------------------- #

def detect_apple_silicon():
    """Check if running on Apple Silicon (M1/M2/M3)."""
    try:
        result = subprocess.run(["sysctl", "-n", "hw.optional.arm64"], capture_output=True, text=True, timeout=5)
        return result.stdout.strip() == "1"
    except Exception:
        return False


def detect_macos_gpus():
    """Detect GPUs on macOS using system_profiler."""
    try:
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True, text=True, timeout=15
        )
        data = json.loads(result.stdout)
        gpus = []
        for gpu in data.get("SPDisplaysDataType", []):
            name = gpu.get("sppci_model", gpu.get("_name", "Unknown"))
            vendor = "unknown"
            n = name.lower()
            if "apple" in n:
                vendor = "apple"
            elif "nvidia" in n:
                vendor = "nvidia"
            elif "amd" in n or "radeon" in n:
                vendor = "amd"
            elif "intel" in n:
                vendor = "intel"
            metal_str = gpu.get("spdisplays_metal", "")
            if "apple" in metal_str.lower():
                vendor = "apple"
            gpus.append((vendor, name))
        return gpus
    except Exception:
        return []


def detect_vulkan_gpus():
    """macOS: No lspci/vulkaninfo. Use system_profiler data for RIFE."""
    gpus = detect_macos_gpus()
    devices = []
    for i, (vendor, name) in enumerate(gpus):
        klass = classify_gpu(name)
        devices.append((i, name, klass))
    return devices


def classify_gpu(name):
    n = name.lower()
    if any(k in n for k in ("apple", "m1", "m2", "m3", "m4", "m5")):
        return "apple_silicon"
    if any(k in n for k in ("rtx", "quadro", "tesla", "pro duo", "radeon rx")):
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


# --------------------------------------------------------------------------- #
# Dependency management (portable — no Homebrew)
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
    if FFMPEG_BIN.is_file() and FFPROBE_BIN.is_file():
        return True
    sys_ffmpeg = shutil.which("ffmpeg")
    sys_ffprobe = shutil.which("ffprobe")
    if sys_ffmpeg and sys_ffprobe:
        FFMPEG_BIN = Path(sys_ffmpeg)
        FFPROBE_BIN = Path(sys_ffprobe)
        return True
    status(_("ffmpeg/ffprobe not found locally or on system."), "WARN")
    url = FFMPEG_RELEASE_URLS.get("macos")
    if url and (auto_yes or ask_yes_no(_("Download ffmpeg now?"), default=True)):
        return _download_and_extract(url, _FFMPEG_DIR, "ffmpeg")
    status(
        _("ffmpeg must be placed manually in:") + f"\n  {_FFMPEG_DIR}\n"
        + _("Install with: brew install ffmpeg, then copy binaries."),
        "ERROR"
    )
    sys.exit(1)


def _ensure_rife(auto_yes=False):
    global RIFE_BIN
    if RIFE_BIN.is_file():
        RIFE_BIN.chmod(0o755)
        return True
    sys_rife = shutil.which("rife-ncnn-vulkan")
    if sys_rife:
        RIFE_BIN = Path(sys_rife)
        RIFE_BIN.chmod(0o755)
        return True
    status(_("rife-ncnn-vulkan not found locally or on system."), "WARN")
    url = RIFE_RELEASE_URLS.get("macos")
    if url and (auto_yes or ask_yes_no(_("Download rife-ncnn-vulkan now? (~400 MB)"), default=True)):
        ok = _download_and_extract(url, _RIFE_DIR, "rife-ncnn-vulkan")
        if not ok:
            status(_("Could not download rife-ncnn-vulkan."), "ERROR")
            sys.exit(1)
        if RIFE_BIN.is_file():
            RIFE_BIN.chmod(0o755)
            return True
        for f in _RIFE_DIR.rglob("rife-ncnn-vulkan"):
            f.chmod(0o755)
            shutil.move(str(f), str(RIFE_BIN))
            break
        if RIFE_BIN.is_file():
            RIFE_BIN.chmod(0o755)
            return True
    status(
        _("rife-ncnn-vulkan must be placed manually in:") + f"\n  {RIFE_BIN}\n"
        + _("Download from: https://github.com/nihui/rife-ncnn-vulkan/releases"),
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
    os_name = "macos"
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


def _model_supports_custom_frame_count(model):
    return model.startswith("rife-v4")


def list_available_rife_models():
    if not MODELS_DIR.is_dir():
        return ["rife-v4.6"]
    found = sorted(d.name for d in MODELS_DIR.iterdir()
                    if d.is_dir() and d.name.startswith("rife-"))
    return found if found else ["rife-v4.6"]


# --------------------------------------------------------------------------- #
# Dependency orchestration (portable)
# --------------------------------------------------------------------------- #

_DEPS_CHECKED = False

def ensure_dependencies(auto_yes=False):
    global _DEPS_CHECKED
    if _DEPS_CHECKED:
        return True
    _ensure_ffmpeg(auto_yes=auto_yes)
    _ensure_rife(auto_yes=auto_yes)
    _ensure_default_model(auto_yes=auto_yes)

    is_apple = detect_apple_silicon()
    if is_apple:
        status(_("Apple Silicon detected — using optimized settings."), "INFO")
    _DEPS_CHECKED = True
    return True


# --------------------------------------------------------------------------- #
# Encoders & GPU presets (macOS — VideoToolbox support)
# --------------------------------------------------------------------------- #

ENCODER_PRESETS = {
    "libx264":              {"codec": "libx264",            "hwaccel": None,          "pix_fmt": "yuv420p"},
    "libx265":              {"codec": "libx265",            "hwaccel": None,          "pix_fmt": "yuv420p"},
    "h264_videotoolbox":    {"codec": "h264_videotoolbox",  "hwaccel": "videotoolbox","pix_fmt": "nv12"},
    "hevc_videotoolbox":    {"codec": "hevc_videotoolbox",  "hwaccel": "videotoolbox","pix_fmt": "nv12"},
}

_ENCODER_CACHE = None

def _detect_available_encoders():
    global _ENCODER_CACHE
    if _ENCODER_CACHE is not None:
        return _ENCODER_CACHE
    try:
        r = subprocess.run([str(FFMPEG_BIN), "-encoders"], capture_output=True, text=True, timeout=5)
        _ENCODER_CACHE = re.findall(r"^\s*V.{5}\s+(\S+)", r.stdout, re.MULTILINE)
        return _ENCODER_CACHE
    except Exception:
        return []


def _detect_gpu_vendors():
    vendors = set()
    is_as = detect_apple_silicon()
    if is_as:
        vendors.add("apple")
    for vendor, _ in detect_macos_gpus():
        vendors.add(vendor)
    return vendors



def choose_gpu_settings(width, height):
    devices = detect_vulkan_gpus()
    is_uhd_res = max(width, height) >= 3200
    cpus = os.cpu_count() or 4

    if not devices:
        t = f"1:{min(cpus, 2)}:{min(cpus, 2)}"
        return {"gpu_id": None, "gpu_name": "not detected", "threads": t,
                "uhd": is_uhd_res, "class": "unknown", "tile_size": 0,
                "ffmpeg_gpu": {"hwaccel": "videotoolbox", "hint": ""}}

    priority = {"apple_silicon": 0, "discrete_high": 1, "discrete": 2, "integrated": 3, "unknown": 4}
    sorted_devs = sorted(devices, key=lambda d: priority.get(d[2], 4))
    best = sorted_devs[0]
    gpu_id, name, cls = best

    ct = min(cpus, 16)
    if cls == "apple_silicon":
        threads = f"4:{min(ct, 8)}:{min(ct, 4)}"
    elif cls == "discrete_high":
        threads = f"2:{min(ct * 2, 16)}:{min(ct, 8)}"
    elif cls == "discrete":
        threads = f"1:{ct}:{min(ct, 4)}"
    elif cls == "integrated":
        threads = f"1:{min(ct, 2)}:{min(ct, 2)}"
    else:
        threads = f"1:{min(ct, 2)}:{min(ct, 2)}"

    tile_size = 0
    if is_uhd_res:
        tile_size = 1024 if cls in ("apple_silicon", "discrete_high", "discrete") else 512

    ffmpeg_gpu = {"hwaccel": "videotoolbox", "hint": ""}
    if cls == "apple_silicon":
        ffmpeg_gpu["hint"] = " (Apple Silicon)"
    elif "nvidia" in name.lower():
        ffmpeg_gpu["hint"] = " (NVIDIA)"
    elif "amd" in name.lower() or "radeon" in name.lower():
        ffmpeg_gpu["hint"] = " (AMD)"
    elif "intel" in name.lower():
        ffmpeg_gpu["hint"] = " (Intel)"
    if ffmpeg_gpu["hint"]:
        status(f"{_('RIFE on')}: {name}{ffmpeg_gpu['hint']}", "OK")

    return {"gpu_id": gpu_id, "gpu_name": name, "threads": threads,
            "uhd": is_uhd_res, "class": cls, "tile_size": tile_size,
            "ffmpeg_gpu": ffmpeg_gpu}


PRESETS = {
    "fast":     {"model": "rife-v4.6", "threads": "4:4:4", "tile_size": 0},
    "balanced": {"model": "rife-v4.6", "threads": "2:4:4", "tile_size": 0},
    "quality":  {"model": "rife-v4.6", "threads": "2:2:2", "tile_size": 0},
}


# --------------------------------------------------------------------------- #
# Video probing (ffprobe)
# --------------------------------------------------------------------------- #

def probe_video(path):
    cmd = [
        str(FFPROBE_BIN), "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception as exc:
        status(f"{_('Error probing video:')} {exc}", "ERROR")
        return None

    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = None
    audio = None
    for s in streams:
        if s.get("codec_type") == "video" and video is None:
            video = s
        if s.get("codec_type") == "audio" and audio is None:
            audio = s
    if video is None:
        status(_("No video stream found."), "ERROR")
        return None

    w = video.get("width", 0)
    h = video.get("height", 0)
    fps_str = video.get("r_frame_rate", "30/1")
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 30.0
    else:
        fps = float(fps_str) or 30.0
    frame_count = int(video.get("nb_frames", 0))
    duration = float(data["format"].get("duration", 0))
    has_audio = audio is not None
    size = int(data["format"].get("size", 0))
    codec = video.get("codec_name", "unknown")

    return {
        "path": path,
        "width": w,
        "height": h,
        "fps": fps,
        "frame_count": frame_count,
        "duration": duration,
        "has_audio": has_audio,
        "size": size,
        "codec": codec,
        "name": path.name,
    }


# --------------------------------------------------------------------------- #
# Temp management (macOS — no tmpfs, use /tmp or custom RAM disk)
# --------------------------------------------------------------------------- #

_temp_managers = []


def _detach_ramdisk(device):
    if device:
        try:
            subprocess.run(["diskutil", "eject", device], capture_output=True, timeout=10)
        except Exception:
            pass


class TempManager:
    def __init__(self, estimated_bytes=0):
        self._ramdisk_device = None
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
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

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
        if self._ramdisk_device:
            _detach_ramdisk(self._ramdisk_device)


# --------------------------------------------------------------------------- #
# Frame extraction
# --------------------------------------------------------------------------- #

def _count_files(directory, pattern="*.png"):
    if not directory.is_dir():
        return 0
    return len(list(directory.glob(pattern)))


def _estimate_frame_storage(w, h, frame_count):
    bytes_per_pixel = 3
    return w * h * bytes_per_pixel * frame_count


def extract_frames(video_path, out_dir, info, gpu_settings):
    w = info.get("width", 1920)
    h = info.get("height", 1080)

    cmd = [
        str(FFMPEG_BIN), "-y",
        "-i", str(video_path),
        "-pix_fmt", "rgb24",
        "-vsync", "0",
        "-frame_parallel", "1",
        "-start_number", "0",
        f"{out_dir}/%08d.png",
    ]

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    expected = info.get("frame_count", 0)
    desc = _("Extracting frames")
    if HAS_TQDM:
        pbar = tqdm(total=expected or 0, desc=desc, unit="frame", bar_format="{l_bar}{bar:30}{r_bar}")
    else:
        pbar = ProgressBar(total=expected or 0, desc=desc, unit="frame", width=35)

    for line in process.stdout:
        m = re.search(r"frame=\s*(\d+)", line)
        if m:
            current = int(m.group(1))
            if HAS_TQDM:
                pbar.update(current - pbar.n)
            else:
                pbar.n = current

    process.wait()
    pbar.close()

    if process.returncode != 0:
        status(_("Frame extraction failed."), "ERROR")
        sys.exit(1)

    result = _count_files(out_dir)
    print(f"  {Color.ok('\u2713')} {_('Frames extracted:')} {Color.bold(str(result))}", flush=True)
    return result


# --------------------------------------------------------------------------- #
# RIFE interpolation
# --------------------------------------------------------------------------- #

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
            status(f"{_('Output will be at')} {actual_output_fps:.3f} fps", "WARN")

    cmd = [
        str(RIFE_BIN),
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
        pbar = tqdm(total=target_frame_count, desc=desc, unit="frame", bar_format="{l_bar}{bar:30}{r_bar}")
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
    print(f"{Color.ok('\u2713')} {_('Interpolation complete:')} {Color.bold(str(result_frames))} {_('frames generated')}", flush=True)
    return actual_output_fps


def _watch_progress_proc(out_dir, total, stop_event, pbar):
    last = 0
    while not stop_event.is_set():
        count = _count_files(out_dir)
        if count > last:
            diff = count - last
            if HAS_TQDM:
                pbar.update(diff)
            else:
                pbar.n = count
                pbar._draw()
            last = count
        time.sleep(0.5)


# --------------------------------------------------------------------------- #
# Video reassembly
# --------------------------------------------------------------------------- #

def reassemble_video(
    out_frames_dir, original_video, target_fps, has_audio,
    output_path, result_frames, encoder_name="libx264", crf=18,
    preset="medium", gpu_settings=None
):
    enc = ENCODER_PRESETS.get(encoder_name, ENCODER_PRESETS["libx264"])

    cmd = [
        str(FFMPEG_BIN), "-y",
        "-framerate", str(target_fps),
        "-i", f"{out_frames_dir}/%08d.png",
        "-i", str(original_video),
    ]

    if "videotoolbox" in enc["codec"]:
        cmd += ["-hwaccel", "videotoolbox"]

    if enc["hwaccel"] == "videotoolbox":
        cmd += ["-c:v", enc["codec"], "-q:v", str(crf), "-allow_sw", "1", "-pix_fmt", enc["pix_fmt"]]
    else:
        cmd += [
            "-c:v", enc["codec"],
            "-crf", str(crf),
            "-preset", preset,
            "-pix_fmt", enc["pix_fmt"],
        ]

    if has_audio:
        cmd += [
            "-map", "1:a?",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
        ]

    cmd += [str(output_path)]

    total = result_frames
    desc = _("Reassembling")
    if HAS_TQDM:
        pbar = tqdm(total=total, desc=desc, unit="frame", bar_format="{l_bar}{bar:30}{r_bar}")
    else:
        pbar = ProgressBar(total=total, desc=desc, unit="frame", width=35)

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in process.stdout:
        m = re.search(r"frame=\s*(\d+)", line)
        if m:
            current = int(m.group(1))
            if HAS_TQDM:
                pbar.update(current - pbar.n)
            else:
                pbar.n = current
    process.wait()
    pbar.close()

    if process.returncode != 0 and enc["codec"] not in ("libx264", "libx265"):
        available = _detect_available_encoders()
        fallback_name = None
        for name in ("libx264", "libx265"):
            if name in ENCODER_PRESETS and name in available:
                fallback_name = name
                break
        if fallback_name is None:
            for name in available:
                if name in ENCODER_PRESETS:
                    fallback_name = name
                    break
        if fallback_name is None:
            status(_("No usable encoder found."), "ERROR")
            sys.exit(1)
        status(f"{_('Hardware encoder')} {enc['codec']} {_('failed, falling back to')} {fallback_name}.", "WARN")
        enc = ENCODER_PRESETS[fallback_name]
        cmd = [
            str(FFMPEG_BIN), "-y",
            "-framerate", str(target_fps),
            "-i", f"{out_frames_dir}/%08d.png",
            "-i", str(original_video),
            "-c:v", enc["codec"],
            "-crf", str(crf),
            "-preset", preset,
            "-pix_fmt", enc["pix_fmt"],
        ]
        if has_audio:
            cmd += ["-map", "1:a?", "-c:a", "aac", "-b:a", "192k", "-shortest"]
        cmd += [str(output_path)]
        desc = _(f"Reassembling ({fallback_name} fallback)")
        if HAS_TQDM:
            pbar = tqdm(total=result_frames, desc=desc, unit="frame", bar_format="{l_bar}{bar:30}{r_bar}")
        else:
            pbar = ProgressBar(total=result_frames, desc=desc, unit="frame", width=35)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in process.stdout:
            m = re.search(r"frame=\s*(\d+)", line)
            if m:
                current = int(m.group(1))
                if HAS_TQDM:
                    pbar.update(current - pbar.n)
                else:
                    pbar.n = current
        process.wait()
        pbar.close()

    if process.returncode != 0:
        status(_("Reassembly failed. Check the output above."), "ERROR")
        sys.exit(1)


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


def _find_videos():
    videos_dir = VIDEOS_DIR / "original"
    videos_dir.mkdir(parents=True, exist_ok=True)
    exts = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.flv'}
    return sorted([f for f in videos_dir.iterdir() if f.is_file() and f.suffix.lower() in exts])


def run_pipeline(info, target_fps, output_path, gpu_settings, model=None):
    start_time = time.time()
    user_model = model is not None
    if model is None:
        model = CONFIG.get("model", DEFAULT_CONFIG["model"])
    rife_threads = gpu_settings["threads"]
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
    sp.ok(_("Interpolation complete"))

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
    sp.ok(_("Video reassembled"))

    tmp.cleanup()
    elapsed = time.time() - start_time
    status(
        f"{_('Video exported successfully in')} {format_duration(elapsed)} "
        f"{_('saved to:')} {output_path}",
        "OK",
    )
    return True


def interactive_wizard():
    print(f"\n  {Color.bold(_('LocallyFPS'))} - v{APP_VERSION}")
    print(f"  {_('Interactive mode')}\n")

    preset_names = {
        "fast": _("Fast"),
        "balanced": _("Balanced"),
        "quality": _("Quality"),
    }
    pkey = CONFIG.get("video_preset", "balanced")
    print(f"  {_('Preset')}: {Color.bold(preset_names.get(pkey, pkey))}")

    videos = _find_videos()
    if not videos:
        p = Path.cwd() / "videos" / "original"
        print(f"\n  {Color.warn(_('No videos found in:'))} {p}")
        print(f"  {_('Place .mp4/.mov/.mkv files there or specify one below.')}\n")
        _setup_path_completion()
        path_str = input(f"  {Color.magenta('\u25b8')} {_('Video path')}: ").strip()
        if not path_str:
            status(_("No video specified."), "ERROR")
            sys.exit(1)
        video_path = Path(path_str).expanduser().resolve()
        if not video_path.is_file():
            status(f"{_('File not found:')} {video_path}", "ERROR")
            sys.exit(1)
        videos = [video_path]
    else:
        print(f"\n  {Color.bold(_('Select a video'))}\n")
        labels = [f"{Color.bold(v.name)}  ({v.parent.name})" for v in videos]
        idx = _interactive_select_video(labels)
        if idx < 0:
            sys.exit(0)
        video_path = videos[idx]

    info = probe_video(video_path)
    if info is None:
        sys.exit(1)

    print(f"\n  {Color.bold(info['name'])}")
    print(f"  {info['width']}\u00d7{info['height']}  @ {info['fps']:.2f} fps  {info['codec']}")
    print(f"  {_('Duration:')} {format_duration(info['duration'])}")
    if info["frame_count"]:
        print(f"  {_('Frames:')} {info['frame_count']:,}")
    print()

    _setup_path_completion()
    while True:
        try:
            resp = input(f"  {Color.magenta('\u25b8')} {_('Target FPS')} [{Color.bold(str(info['fps'] * 2))}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(1)
        if not resp:
            target_fps = info["fps"] * 2
        else:
            try:
                target_fps = float(resp)
            except ValueError:
                continue
        if target_fps > info["fps"]:
            break
        print(f"  {Color.warn(_('Target FPS must be higher than source FPS'))} ({info['fps']:.2f})")

    print(f"  {_('Output FPS:')} {Color.bold(f'{target_fps:.2f}')}")

    output_dir = Path.cwd() / "videos" / "enhanced"
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = video_path.stem
    output_path = output_dir / f"{stem}_enhanced_{int(target_fps)}fps.mp4"

    print(f"  {_('Output:')} {output_path}\n")

    if not ask_yes_no(_("Start processing?"), default=True):
        print(f"  {Color.warn(_('Cancelled.'))}")
        sys.exit(0)

    gpu_settings = choose_gpu_settings(info["width"], info["height"])

    run_pipeline(info, target_fps, output_path, gpu_settings)


# --------------------------------------------------------------------------- #
# CLI mode
# --------------------------------------------------------------------------- #

def main_cli(args):
    video_path = Path(args.input).expanduser().resolve()
    if not video_path.is_file():
        status(f"{_('File not found:')} {video_path}", "ERROR")
        sys.exit(1)

    info = probe_video(video_path)
    if info is None:
        sys.exit(1)

    target_fps = args.target_fps or info["fps"] * 2
    if target_fps <= info["fps"]:
        status(f"{_('Target FPS must be higher than source FPS')} ({info['fps']:.2f})", "ERROR")
        sys.exit(1)

    output_dir = Path.cwd() / "videos" / "enhanced"
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = video_path.stem
    output_path = output_dir / f"{stem}_enhanced_{int(target_fps)}fps.mp4"

    gpu_settings = choose_gpu_settings(info["width"], info["height"])
    if args.gpu_id is not None:
        gpu_settings["gpu_id"] = args.gpu_id
    if args.uhd:
        gpu_settings["uhd"] = True
    if args.threads:
        gpu_settings["threads"] = args.threads

    model = args.model or CONFIG.get("model", DEFAULT_CONFIG["model"])
    CONFIG["encoder"] = args.encoder or CONFIG.get("encoder", DEFAULT_CONFIG["encoder"])
    CONFIG["crf"] = args.crf or CONFIG.get("crf", DEFAULT_CONFIG["crf"])
    CONFIG["preset"] = args.preset or CONFIG.get("preset", DEFAULT_CONFIG["preset"])

    run_pipeline(info, target_fps, output_path, gpu_settings, model=model)
    return True


# --------------------------------------------------------------------------- #
# Argument parser
# --------------------------------------------------------------------------- #

def parse_args():
    p = argparse.ArgumentParser(
        prog="LocallyFPS",
        description=_("AI frame interpolation for video using rife-ncnn-vulkan (macOS)"),
    )
    p.add_argument("input", nargs="?", help=_("Input video path"))
    p.add_argument("--target-fps", type=float, help=_("Desired output FPS"))
    p.add_argument("--model", default="rife-v4.6", help=_("RIFE model name"))
    p.add_argument("--gpu-id", type=int, help=_("GPU device index for RIFE"))
    p.add_argument("--uhd", action="store_true", help=_("Enable UHD mode for 4K+ videos"))
    p.add_argument("--output", help=_("Output video path"))
    p.add_argument("--yes", "-y", action="store_true", help=_("Skip confirmations"))
    p.add_argument("--config", action="store_true", help=_("Open settings menu"))
    p.add_argument("--threads", help=_("RIFE thread config (e.g. 2:4:4)"))
    p.add_argument("--encoder", default="libx264", choices=["libx264", "libx265", "h264_videotoolbox", "hevc_videotoolbox"], help=_("Video encoder"))
    p.add_argument("--crf", type=int, default=18, help=_("CRF quality (0-51)"))
    p.add_argument("--preset", default="medium", help=_("ffmpeg preset"))
    return p.parse_args()


# --------------------------------------------------------------------------- #
# main()
# --------------------------------------------------------------------------- #

def main():
    _ensure_dirs()
    _load_config()
    _load_translations()

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
