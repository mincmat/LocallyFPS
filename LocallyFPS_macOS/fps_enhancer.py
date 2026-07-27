#!/usr/bin/env python3
"""
fps_enhancer.py – AI frame interpolation for video using rife-ncnn-vulkan.
macOS Edition — uses system_profiler, sysctl, brew, and VideoToolbox.
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
# Config
# --------------------------------------------------------------------------- #

CONFIG_DIR = Path(__file__).resolve().parent
CONFIG_PATH = CONFIG_DIR / "config.json"

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
        if CONFIG_PATH.exists():
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

LANG_DIR = CONFIG_DIR / "languages"
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
# rife-ncnn-vulkan paths (macOS)
# --------------------------------------------------------------------------- #

RIFE_RELEASE_URL = (
    "https://github.com/nihui/rife-ncnn-vulkan/releases/download/"
    "20221029/rife-ncnn-vulkan-20221029-macos.zip"
)
RIFE_INSTALL_DIR = Path("/usr/local/opt/rife-ncnn-vulkan")
RIFE_SYMLINK = Path("/usr/local/bin/rife-ncnn-vulkan")


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
# Package manager (macOS Homebrew)
# --------------------------------------------------------------------------- #

def detect_package_manager():
    if shutil.which("brew"):
        return "brew"
    return None


def install_package(pm_name, logical_pkg):
    if pm_name != "brew":
        return False
    info = {
        "install": ["brew", "install"],
        "packages": {
            "ffmpeg": "ffmpeg",
        }
    }
    real_pkg = info["packages"].get(logical_pkg)
    if not real_pkg:
        return False
    cmd = info["install"] + [real_pkg]
    status(f"{_('Running:')} \033[2m{' '.join(cmd)}\033[0m")
    result = subprocess.run(cmd)
    return result.returncode == 0


def _offer_install(pm, logical_pkg, human_name, required=True):
    if pm is None:
        status(f"{_('No supported package manager found to install')} {human_name}.",
            "ERROR" if required else "WARN")
        if required:
            sys.exit(1)
        return False
    if ask_yes_no(f"{_('Install')} \033[1m{human_name}\033[0m {_('now with')} {pm}?", default=True):
        ok = install_package(pm, logical_pkg)
        if not ok and required:
            status(f"{_('Could not install')} {human_name} {_('automatically.')}", "ERROR")
            sys.exit(1)
        return ok
    if required:
        status(f"{human_name} {_('is required to continue.')}", "ERROR")
        sys.exit(1)
    return False


def install_rife_ncnn_vulkan():
    status(_("rife-ncnn-vulkan is not installed."), "WARN")
    if not ask_yes_no(_("Download and install it now? (~400 MB)"), default=True):
        status(_("rife-ncnn-vulkan is required to continue."), "ERROR")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "rife.zip"
        status(_("Downloading rife-ncnn-vulkan (macOS release)..."))
        dl = DownloadProgress(_("Downloading"))
        try:
            urllib.request.urlretrieve(RIFE_RELEASE_URL, zip_path, reporthook=dl)
        except Exception as exc:
            status(f"{_('Download failed:')} {exc}", "ERROR")
            sys.exit(1)
        finally:
            dl.close()

        status(_("Extracting..."))
        extract_dir = Path(tmpdir) / "extracted"
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

        subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
        source_dir = subdirs[0] if subdirs else extract_dir

        status(f"{_('Installing to')} {RIFE_INSTALL_DIR}...")
        try:
            RIFE_INSTALL_DIR.mkdir(parents=True, exist_ok=True)
            for item in source_dir.iterdir():
                dest = RIFE_INSTALL_DIR / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)
            rife_bin = RIFE_INSTALL_DIR / "rife-ncnn-vulkan"
            if rife_bin.exists():
                rife_bin.chmod(0o755)
            RIFE_SYMLINK.parent.mkdir(parents=True, exist_ok=True)
            if RIFE_SYMLINK.exists() or RIFE_SYMLINK.is_symlink():
                RIFE_SYMLINK.unlink(missing_ok=True)
            RIFE_SYMLINK.symlink_to(str(rife_bin))
        except Exception as exc:
            status(f"{_('Error installing rife-ncnn-vulkan:')} {exc}", "ERROR")
            sys.exit(1)

    _cleanup_non_default_models()

    if shutil.which("rife-ncnn-vulkan") is None:
        status(_("Could not install rife-ncnn-vulkan automatically."), "ERROR")
        sys.exit(1)

    status(_("rife-ncnn-vulkan installed successfully."), "OK")


def _cleanup_non_default_models():
    default_model = "rife-v4.6"
    if not RIFE_INSTALL_DIR.is_dir():
        return
    for item in sorted(RIFE_INSTALL_DIR.iterdir()):
        if item.is_dir() and item.name.startswith("rife-") and item.name != default_model:
            shutil.rmtree(item, ignore_errors=True)


def _ensure_default_model():
    default_model = "rife-v4.6"
    model_dir = RIFE_INSTALL_DIR / default_model
    if model_dir.is_dir():
        return
    status(f"{_('Default model')} {default_model} {_('not found. Installing...')}")
    if not install_model(default_model):
        status(f"{_('Could not install')} {default_model}. {_('Interpolation will fail if the model is missing.')}", "WARN")


def install_model(model_name):
    model_dir = RIFE_INSTALL_DIR / model_name
    if model_dir.is_dir():
        return True
    status(f"{_('Downloading model')} {model_name}...")
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "rife.zip"
        dl = DownloadProgress(_("Downloading"))
        try:
            urllib.request.urlretrieve(RIFE_RELEASE_URL, zip_path, reporthook=dl)
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
        status(f"{_('Installing')} {model_name}...")
        try:
            RIFE_INSTALL_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copytree(model_src, RIFE_INSTALL_DIR / model_name, dirs_exist_ok=True)
        except Exception as exc:
            status(f"{_('Error installing model')} {model_name}: {exc}", "ERROR")
            return False
    return True


def _model_supports_custom_frame_count(model):
    return model.startswith("rife-v4")


# --------------------------------------------------------------------------- #
# Dependency orchestration (macOS)
# --------------------------------------------------------------------------- #

def ensure_dependencies():
    pm = detect_package_manager()

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        _offer_install(pm, "ffmpeg", "ffmpeg y ffprobe", required=True)

    if shutil.which("rife-ncnn-vulkan") is None:
        install_rife_ncnn_vulkan()
    else:
        _ensure_default_model()

    missing_critical = [b for b in ("ffmpeg", "ffprobe", "rife-ncnn-vulkan") if shutil.which(b) is None]
    if missing_critical:
        status(f"{_('Still missing critical dependencies:')} {', '.join(missing_critical)}", "ERROR")
        sys.exit(1)

    is_apple = detect_apple_silicon()
    if is_apple:
        status(_("Apple Silicon detected — using optimized settings."), "INFO")
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
        r = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=5)
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


def _pick_best_encoder(preferred="libx264"):
    available = _detect_available_encoders()
    vendors = _detect_gpu_vendors()

    vp = CONFIG.get("video_preset", "")
    if vp == "custom" and preferred in available:
        return ENCODER_PRESETS[preferred]

    if preferred in ("libx264", "libx265") and vendors:
        hw_map = [
            ("apple",  ["hevc_videotoolbox", "h264_videotoolbox"]),
            ("amd",    ["h264_videotoolbox", "hevc_videotoolbox"]),
            ("intel",  ["h264_videotoolbox", "hevc_videotoolbox"]),
            ("nvidia", ["h264_videotoolbox", "hevc_videotoolbox"]),
        ]
        for vendor, encs in hw_map:
            if vendor in vendors:
                for name in encs:
                    if name in available:
                        return ENCODER_PRESETS[name]

    if preferred in ENCODER_PRESETS:
        return ENCODER_PRESETS[preferred]

    return ENCODER_PRESETS["libx264"]


GPU_PRESETS = {
    "apple_silicon": {"threads": "4:4:4", "gpu_id": 0, "uhd": True,  "tile_size": 0},
    "discrete_high": {"threads": "4:4:4", "gpu_id": 0, "uhd": True,  "tile_size": 0},
    "discrete":      {"threads": "2:4:4", "gpu_id": 0, "uhd": False, "tile_size": 0},
    "integrated":    {"threads": "2:2:2", "gpu_id": 0, "uhd": False, "tile_size": 0},
    "unknown":       {"threads": "2:2:2", "gpu_id": 0, "uhd": False, "tile_size": 0},
}


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
        "ffprobe", "-v", "quiet", "-print_format", "json",
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

def _get_avail_ram():
    try:
        result = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)
        free_pages = 0
        for line in result.stdout.splitlines():
            if line.lower().startswith("pages free"):
                m = re.search(r'(\d+)', line)
                if m:
                    free_pages = int(m.group(1))
                    break
        page_size = 16384
        return free_pages * page_size
    except Exception:
        return 0


def _pick_temp_root(use_ramdisk=False, estimated_bytes=0):
    if use_ramdisk and estimated_bytes > 0:
        try:
            vol_name = f"LocallyFPS_{int(time.time())}"
            sectors = int(estimated_bytes * 2.5 / 512) + 1024
            result = subprocess.run(
                ["hdiutil", "attach", "-nomount", f"ram://{sectors}"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                device = result.stdout.strip().splitlines()[-1].strip()
                subprocess.run(
                    ["diskutil", "erasevolume", "JHFS+", vol_name, device],
                    capture_output=True, timeout=10
                )
                ram_path = Path(f"/Volumes/{vol_name}")
                if ram_path.is_dir():
                    return Path(tempfile.mkdtemp(prefix="fps_enhancer_", dir=str(ram_path))), device
        except Exception:
            pass

    tmp_path = Path("/tmp")
    if tmp_path.is_dir() and os.access(str(tmp_path), os.W_OK):
        try:
            return Path(tempfile.mkdtemp(prefix="fps_enhancer_", dir=str(tmp_path))), None
        except OSError:
            pass

    work_dir = Path.cwd() / "temp_frames"
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        return Path(tempfile.mkdtemp(prefix="fps_enhancer_", dir=str(work_dir))), None
    except OSError:
        pass

    return Path(tempfile.mkdtemp(prefix="fps_enhancer_")), None


def _detach_ramdisk(device):
    if device:
        try:
            subprocess.run(["diskutil", "eject", device], capture_output=True, timeout=10)
        except Exception:
            pass


class TempManager:
    def __init__(self, estimated_bytes=0):
        use_ramdisk = False
        self._ramdisk_device = None

        if estimated_bytes > 0:
            avail_ram = _get_avail_ram()
            needed = int(estimated_bytes * 2.5)
            if avail_ram > needed and estimated_bytes < 1 * 1024 * 1024 * 1024:
                use_ramdisk = True

        result = _pick_temp_root(use_ramdisk, estimated_bytes)
        if isinstance(result, tuple):
            self.temp_root, self._ramdisk_device = result
        else:
            self.temp_root, self._ramdisk_device = result, None

        self.in_frames_dir = self.temp_root / "in_frames"
        self.out_frames_dir = self.temp_root / "out_frames"
        self.in_frames_dir.mkdir(parents=True, exist_ok=True)
        self.out_frames_dir.mkdir(parents=True, exist_ok=True)

        if self._ramdisk_device:
            status(f"{_('\u2192 frames in RAM disk.')}", "INFO")
        else:
            status(f"{_('\u2192 frames on disk (not enough RAM).')}", "INFO")
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


def cleanup_all_temp():
    for mgr in _temp_managers:
        mgr.cleanup()


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
        "ffmpeg", "-y",
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
        "rife-ncnn-vulkan",
        "-i", str(in_frames_dir),
        "-o", str(out_frames_dir),
        "-m", model,
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
        "ffmpeg", "-y",
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
                pbar.update(current - (pbar.n if HAS_TQDM else 0))
            else:
                pbar.n = current
    process.wait()
    pbar.close()

    if process.returncode != 0:
        status(_("Reassembly failed. Check the output above."), "ERROR")
        sys.exit(1)


# --------------------------------------------------------------------------- #
# Pipeline orchestrator
# --------------------------------------------------------------------------- #

def format_duration(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


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

    model_dir = RIFE_INSTALL_DIR / model
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


# --------------------------------------------------------------------------- #
# Interactive wizard
# --------------------------------------------------------------------------- #

def _find_videos():
    p = Path.cwd() / "videos" / "original"
    if not p.is_dir():
        return []
    return sorted([f for f in p.iterdir() if f.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi", ".webm")])


def _run_language_wizard():
    langs = sorted(TRANSLATIONS.keys())
    if not langs:
        return
    if len(langs) == 1:
        CONFIG["language"] = langs[0]
        _save_config()
        return
    print(f"\n{Color.bold(_('Select language'))}\n")
    idx = _interactive_select("", [f"{Color.bold(l)} - {TRANSLATIONS[l].get('_language_name', l)}" for l in langs])
    if idx >= 0:
        CONFIG["language"] = langs[idx]
        _save_config()
    else:
        CONFIG["language"] = langs[0]
        _save_config()


def _run_settings():
    choices = [
        ("video_preset", [_("preset: fast"), _("preset: balanced"), _("preset: quality")], ["fast", "balanced", "quality"]),
        ("model", ["rife-v4.6"], ["rife-v4.6"]),
        ("encoder", [_("encoder: libx264"), _("encoder: libx265"), _("encoder: h264_videotoolbox"), _("encoder: hevc_videotoolbox")], ["libx264", "libx265", "h264_videotoolbox", "hevc_videotoolbox"]),
        ("crf", [_("CRF: 18"), _("CRF: 20"), _("CRF: 22"), _("CRF: 24")], ["18", "20", "22", "24"]),
        ("preset", [_("preset: ultrafast"), _("preset: superfast"), _("preset: veryfast"), _("preset: faster"), _("preset: fast"), _("preset: medium"), _("preset: slow"), _("preset: slower")], ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower"]),
    ]
    while True:
        print(f"\n{Color.bold(_('Settings'))}\n")
        opts = [c[0] for c in choices]
        opts.append(_("exit"))
        idx = _interactive_select("", [f"{c[0]}: {CONFIG.get(c[0], '?')}" for c in choices] + [_("exit")])
        if idx < 0 or idx >= len(choices):
            break
        key, labels, values = choices[idx]
        sub_idx = _interactive_select("", labels)
        if sub_idx >= 0:
            CONFIG[key] = values[sub_idx]
            _save_config()


def interactive_wizard():
    print(f"\n  {Color.bold(_('LocallyFPS \u2014 AI Frame Interpolation'))}")
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
    _load_config()
    _load_translations()

    is_first_run = not CONFIG_PATH.exists() or "language" not in CONFIG
    if is_first_run:
        _run_language_wizard()

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
