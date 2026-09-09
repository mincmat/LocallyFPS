"""Application resources and writable data locations.

Source checkouts remain portable for development. Frozen/installed builds use
native per-user folders so immutable packages such as AppImage and macOS .app
bundles never try to write inside themselves.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "LocallyFPS"
APP_VERSION = "4.0.0"

BASE_DIR = Path(__file__).resolve().parent.parent
RESOURCE_DIR = BASE_DIR
INSTALL_DIR = BASE_DIR
DATA_DIR = BASE_DIR
FFMPEG_BIN = None
FFPROBE_BIN = None
RIFE_BIN = None
MODELS_DIR = None
CACHE_DIR = None
CONFIG_DIR = None
VIDEOS_DIR = None
LOGS_DIR = None
DOWNLOADS_DIR = None
_FFMPEG_DIR = None
_RIFE_DIR = None
CONFIG_PATH = None
LANG_DIR = None

OS_NAME = "linux"
BIN_EXT = ""
DEFAULT_LANGUAGE = "en"
LAYOUT_MODE = "source"
IS_FROZEN = False
BUNDLED_RUNTIME = False


@dataclass
class Paths:
    base_dir: Path
    resource_dir: Path
    install_dir: Path
    data_dir: Path
    ffmpeg_bin: Path
    ffprobe_bin: Path
    rife_bin: Path
    models_dir: Path
    cache_dir: Path
    config_dir: Path
    videos_dir: Path
    logs_dir: Path
    downloads_dir: Path
    ffmpeg_dir: Path
    rife_dir: Path
    config_path: Path
    lang_dir: Path
    os_name: str
    bin_ext: str
    default_language: str
    layout_mode: str
    is_frozen: bool
    app_version: str = APP_VERSION


_INSTANCE: Paths | None = None


def get() -> Paths:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = Paths(
            base_dir=BASE_DIR,
            resource_dir=RESOURCE_DIR,
            install_dir=INSTALL_DIR,
            data_dir=DATA_DIR,
            ffmpeg_bin=FFMPEG_BIN or DATA_DIR / "deps" / "ffmpeg" / f"ffmpeg{BIN_EXT}",
            ffprobe_bin=FFPROBE_BIN or DATA_DIR / "deps" / "ffmpeg" / f"ffprobe{BIN_EXT}",
            rife_bin=RIFE_BIN or DATA_DIR / "deps" / "rife" / f"rife-ncnn-vulkan{BIN_EXT}",
            models_dir=MODELS_DIR or DATA_DIR / "models",
            cache_dir=CACHE_DIR or DATA_DIR / "cache",
            config_dir=CONFIG_DIR or DATA_DIR / "config",
            videos_dir=VIDEOS_DIR or DATA_DIR / "videos",
            logs_dir=LOGS_DIR or DATA_DIR / "logs",
            downloads_dir=DOWNLOADS_DIR or Path.home() / "Downloads",
            ffmpeg_dir=_FFMPEG_DIR or DATA_DIR / "deps" / "ffmpeg",
            rife_dir=_RIFE_DIR or DATA_DIR / "deps" / "rife",
            config_path=CONFIG_PATH or DATA_DIR / "config" / "settings.json",
            lang_dir=LANG_DIR or RESOURCE_DIR / "languages",
            os_name=OS_NAME,
            bin_ext=BIN_EXT,
            default_language=DEFAULT_LANGUAGE,
            layout_mode=LAYOUT_MODE,
            is_frozen=IS_FROZEN,
        )
    return _INSTANCE


def _detect_os(platform_name=None):
    if platform_name:
        return platform_name
    if sys.platform == "darwin":
        return "macos"
    if os.name == "nt" or sys.platform in ("win32", "cygwin"):
        return "windows"
    return "linux"


def _is_true(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _native_layout(os_name, env, home):
    if os_name == "windows":
        local = Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local")
        data = local / APP_NAME
        return data, data / "cache", data / "config", home / "Videos" / APP_NAME
    if os_name == "macos":
        support = home / "Library" / "Application Support" / APP_NAME
        return support, home / "Library" / "Caches" / APP_NAME, support / "config", home / "Movies" / APP_NAME
    data_home = Path(env.get("XDG_DATA_HOME") or home / ".local" / "share")
    cache_home = Path(env.get("XDG_CACHE_HOME") or home / ".cache")
    config_home = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
    return (
        data_home / APP_NAME,
        cache_home / APP_NAME,
        config_home / APP_NAME,
        home / "Videos" / APP_NAME,
    )


def _downloads_directory(os_name, env, home):
    """Return the real per-user Downloads folder, including localized XDG names."""
    if os_name in {"windows", "macos"}:
        return home / "Downloads"
    configured = env.get("XDG_DOWNLOAD_DIR")
    if not configured:
        config_home = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
        user_dirs = config_home / "user-dirs.dirs"
        try:
            for line in user_dirs.read_text(encoding="utf-8").splitlines():
                if line.startswith("XDG_DOWNLOAD_DIR="):
                    configured = line.split("=", 1)[1].strip().strip('"')
                    break
        except OSError:
            pass
    if configured:
        expanded = configured.replace("$HOME", str(home)).replace("${HOME}", str(home))
        return Path(expanded).expanduser()
    return home / "Downloads"


def _has_legacy_data(directory):
    """Recognize an existing v3 portable folder without changing its data."""
    return any((directory / marker).exists() for marker in (
        "config/settings.json",
        "config.json",
        "videos/original",
        "deps/ffmpeg",
        "deps/rife",
        "models/rife-v4.6",
    ))


def setup(base_dir, *, frozen=None, platform_name=None, env=None, home=None):
    global BASE_DIR, RESOURCE_DIR, INSTALL_DIR, DATA_DIR
    global FFMPEG_BIN, FFPROBE_BIN, RIFE_BIN
    global MODELS_DIR, CACHE_DIR, CONFIG_DIR, VIDEOS_DIR, LOGS_DIR, DOWNLOADS_DIR
    global _FFMPEG_DIR, _RIFE_DIR, CONFIG_PATH, LANG_DIR
    global OS_NAME, BIN_EXT, DEFAULT_LANGUAGE, LAYOUT_MODE, IS_FROZEN, BUNDLED_RUNTIME, _INSTANCE

    _INSTANCE = None
    runtime_env = dict(os.environ) if env is None else dict(env)
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else bool(frozen)
    IS_FROZEN = frozen
    OS_NAME = _detect_os(platform_name)
    BIN_EXT = ".exe" if OS_NAME == "windows" else ""
    # A fresh installation always starts in English. The onboarding selector
    # remains available before any video is processed.
    DEFAULT_LANGUAGE = "en"

    supplied_base = Path(base_dir).resolve()
    appimage = runtime_env.get("APPIMAGE") if OS_NAME == "linux" else None
    INSTALL_DIR = Path(appimage).expanduser().resolve().parent if appimage else supplied_base
    resource_hint = getattr(sys, "_MEIPASS", None) if frozen else None
    RESOURCE_DIR = Path(resource_hint).resolve() if resource_hint else supplied_base
    BASE_DIR = INSTALL_DIR

    if home is not None:
        user_home = Path(home).expanduser().resolve()
    elif OS_NAME == "windows" and runtime_env.get("USERPROFILE"):
        user_home = Path(runtime_env["USERPROFILE"]).expanduser().resolve()
    else:
        user_home = Path.home()

    explicit_home = runtime_env.get("LOCALLYFPS_HOME")
    portable_marker = INSTALL_DIR / ".locallyfps-portable"
    forced_portable = _is_true(runtime_env.get("LOCALLYFPS_PORTABLE"))
    legacy_portable = frozen and _has_legacy_data(INSTALL_DIR)

    if explicit_home:
        DATA_DIR = Path(explicit_home).expanduser().resolve()
        CACHE_DIR = DATA_DIR / "cache"
        CONFIG_DIR = DATA_DIR / "config"
        VIDEOS_DIR = DATA_DIR / "videos"
        LAYOUT_MODE = "custom"
    elif not frozen:
        DATA_DIR = supplied_base
        CACHE_DIR = DATA_DIR / "cache"
        CONFIG_DIR = DATA_DIR / "config"
        VIDEOS_DIR = DATA_DIR / "videos"
        LAYOUT_MODE = "source"
    elif forced_portable or portable_marker.exists() or legacy_portable:
        DATA_DIR = INSTALL_DIR
        CACHE_DIR = DATA_DIR / "cache"
        CONFIG_DIR = DATA_DIR / "config"
        VIDEOS_DIR = DATA_DIR / "videos"
        LAYOUT_MODE = "legacy-portable" if legacy_portable and not forced_portable else "portable"
    else:
        DATA_DIR, CACHE_DIR, CONFIG_DIR, VIDEOS_DIR = _native_layout(
            OS_NAME, runtime_env, user_home,
        )
        LAYOUT_MODE = "installed"

    bundled_deps = RESOURCE_DIR / "deps"
    bundled_models = RESOURCE_DIR / "models"
    BUNDLED_RUNTIME = bool(
        frozen
        and (bundled_deps / "ffmpeg" / f"ffmpeg{BIN_EXT}").is_file()
        and (bundled_deps / "ffmpeg" / f"ffprobe{BIN_EXT}").is_file()
        and (bundled_deps / "rife" / f"rife-ncnn-vulkan{BIN_EXT}").is_file()
        and (bundled_models / "rife-v4.6").is_dir()
    )
    runtime_root = RESOURCE_DIR if BUNDLED_RUNTIME else DATA_DIR
    _FFMPEG_DIR = runtime_root / "deps" / "ffmpeg"
    _RIFE_DIR = runtime_root / "deps" / "rife"
    FFMPEG_BIN = _FFMPEG_DIR / f"ffmpeg{BIN_EXT}"
    FFPROBE_BIN = _FFMPEG_DIR / f"ffprobe{BIN_EXT}"
    RIFE_BIN = _RIFE_DIR / f"rife-ncnn-vulkan{BIN_EXT}"
    MODELS_DIR = runtime_root / "models"
    LOGS_DIR = DATA_DIR / "logs"
    CONFIG_PATH = CONFIG_DIR / "settings.json"
    LANG_DIR = RESOURCE_DIR / "languages"
    DOWNLOADS_DIR = _downloads_directory(OS_NAME, runtime_env, user_home)


def _get_required_dirs():
    return [
        _FFMPEG_DIR,
        _RIFE_DIR,
        MODELS_DIR,
        CACHE_DIR,
        CONFIG_DIR,
        LOGS_DIR,
        VIDEOS_DIR / "original",
        VIDEOS_DIR / "enhanced",
    ]


def ensure_dirs():
    for directory in _get_required_dirs():
        directory.mkdir(parents=True, exist_ok=True)


def any_dep_missing():
    return not (
        FFMPEG_BIN.is_file()
        and FFPROBE_BIN.is_file()
        and RIFE_BIN.is_file()
        and (MODELS_DIR / "rife-v4.6").is_dir()
    )
