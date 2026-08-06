import os
import sys
from pathlib import Path

APP_VERSION = "2.0"

BASE_DIR = Path(__file__).resolve().parent.parent
FFMPEG_BIN = None
FFPROBE_BIN = None
RIFE_BIN = None
MODELS_DIR = None
CACHE_DIR = None
CONFIG_DIR = None
VIDEOS_DIR = None
_FFMPEG_DIR = None
_RIFE_DIR = None
CONFIG_PATH = None
LANG_DIR = None

OS_NAME = "linux"
BIN_EXT = ""
DEFAULT_LANGUAGE = "en"


def setup(base_dir):
    global BASE_DIR, FFMPEG_BIN, FFPROBE_BIN, RIFE_BIN
    global MODELS_DIR, CACHE_DIR, CONFIG_DIR, VIDEOS_DIR
    global _FFMPEG_DIR, _RIFE_DIR, CONFIG_PATH, LANG_DIR
    global OS_NAME, BIN_EXT, DEFAULT_LANGUAGE

    BASE_DIR = Path(base_dir).resolve()

    if sys.platform == "darwin":
        OS_NAME = "macos"
        BIN_EXT = ""
        DEFAULT_LANGUAGE = "en"
    elif os.name == "nt":
        OS_NAME = "windows"
        BIN_EXT = ".exe"
        DEFAULT_LANGUAGE = "es"
    else:
        OS_NAME = "linux"
        BIN_EXT = ""
        DEFAULT_LANGUAGE = "en"

    FFMPEG_BIN = BASE_DIR / "deps" / "ffmpeg" / f"ffmpeg{BIN_EXT}"
    FFPROBE_BIN = BASE_DIR / "deps" / "ffmpeg" / f"ffprobe{BIN_EXT}"
    RIFE_BIN = BASE_DIR / "deps" / "rife" / f"rife-ncnn-vulkan{BIN_EXT}"
    MODELS_DIR = BASE_DIR / "models"
    CACHE_DIR = BASE_DIR / "cache"
    CONFIG_DIR = BASE_DIR / "config"
    VIDEOS_DIR = BASE_DIR / "videos"
    _FFMPEG_DIR = BASE_DIR / "deps" / "ffmpeg"
    _RIFE_DIR = BASE_DIR / "deps" / "rife"
    CONFIG_PATH = CONFIG_DIR / "settings.json"
    LANG_DIR = BASE_DIR / "languages"
    if not LANG_DIR.is_dir():
        LANG_DIR = BASE_DIR.parent / "core" / "languages"
    if not LANG_DIR.is_dir():
        LANG_DIR = BASE_DIR / "core" / "languages"


REQUIRED_DIRS = []


def _get_required_dirs():
    return [
        _FFMPEG_DIR, _RIFE_DIR,
        MODELS_DIR, CACHE_DIR, CONFIG_DIR,
        VIDEOS_DIR / "original", VIDEOS_DIR / "enhanced",
    ]


def ensure_dirs():
    for d in _get_required_dirs():
        d.mkdir(parents=True, exist_ok=True)


def any_dep_missing():
    import shutil
    ffmpeg_check = FFMPEG_BIN.is_file() or shutil.which(f"ffmpeg{BIN_EXT}")
    ffprobe_check = FFPROBE_BIN.is_file() or shutil.which(f"ffprobe{BIN_EXT}")
    rife_check = RIFE_BIN.is_file() or shutil.which(f"rife-ncnn-vulkan{BIN_EXT}")
    model_check = (MODELS_DIR / "rife-v4.6").is_dir()
    return not (ffmpeg_check and ffprobe_check and rife_check and model_check)
