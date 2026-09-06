import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_VERSION = "3.0.1"

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


@dataclass
class Paths:
    base_dir: Path
    ffmpeg_bin: Path
    ffprobe_bin: Path
    rife_bin: Path
    models_dir: Path
    cache_dir: Path
    config_dir: Path
    videos_dir: Path
    ffmpeg_dir: Path
    rife_dir: Path
    config_path: Path
    lang_dir: Path
    os_name: str
    bin_ext: str
    default_language: str
    app_version: str = APP_VERSION


_INSTANCE: Paths | None = None


def get() -> Paths:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = Paths(
            base_dir=BASE_DIR, ffmpeg_bin=FFMPEG_BIN or BASE_DIR / "deps" / "ffmpeg" / f"ffmpeg{BIN_EXT}",
            ffprobe_bin=FFPROBE_BIN or BASE_DIR / "deps" / "ffmpeg" / f"ffprobe{BIN_EXT}",
            rife_bin=RIFE_BIN or BASE_DIR / "deps" / "rife" / f"rife-ncnn-vulkan{BIN_EXT}",
            models_dir=MODELS_DIR or BASE_DIR / "models",
            cache_dir=CACHE_DIR or BASE_DIR / "cache",
            config_dir=CONFIG_DIR or BASE_DIR / "config",
            videos_dir=VIDEOS_DIR or BASE_DIR / "videos",
            ffmpeg_dir=_FFMPEG_DIR or BASE_DIR / "deps" / "ffmpeg",
            rife_dir=_RIFE_DIR or BASE_DIR / "deps" / "rife",
            config_path=CONFIG_PATH or BASE_DIR / "config" / "settings.json",
            lang_dir=LANG_DIR or BASE_DIR / "languages",
            os_name=OS_NAME, bin_ext=BIN_EXT, default_language=DEFAULT_LANGUAGE,
        )
    return _INSTANCE


def setup(base_dir):
    global BASE_DIR, FFMPEG_BIN, FFPROBE_BIN, RIFE_BIN
    global MODELS_DIR, CACHE_DIR, CONFIG_DIR, VIDEOS_DIR
    global _FFMPEG_DIR, _RIFE_DIR, CONFIG_PATH, LANG_DIR
    global OS_NAME, BIN_EXT, DEFAULT_LANGUAGE, _INSTANCE

    _INSTANCE = None
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
    return not (FFMPEG_BIN.is_file() and FFPROBE_BIN.is_file() and RIFE_BIN.is_file() and (MODELS_DIR / "rife-v4.6").is_dir())
