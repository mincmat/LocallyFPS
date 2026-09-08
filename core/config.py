import json
import math
import os
from . import paths

DEFAULT_CONFIG = {
    "language": "en",
    "onboarding_complete": False,
    "theme": "dark",
    "default_target_fps": "60",
    "output_directory": "",
    "encoder": "libx264",
    "crf": 16,
    "preset": "fast",
    "model": "rife-v4.6",
    "video_preset": "balanced",
    "encoder_mode": "auto",
}

CONFIG = dict(DEFAULT_CONFIG)


def _validated_config(data):
    """Repair user-editable settings without letting bad values reach FFmpeg."""
    value = {**DEFAULT_CONFIG, **(data if isinstance(data, dict) else {})}
    if value.get("language") not in {"en", "es", "de", "fr", "pt", "ru", "ar", "zh", "ja", "ko"}:
        value["language"] = paths.DEFAULT_LANGUAGE
    if not isinstance(value.get("onboarding_complete"), bool):
        value["onboarding_complete"] = False
    if value.get("theme") not in {"dark", "light"}:
        value["theme"] = DEFAULT_CONFIG["theme"]
    try:
        target_fps = float(value.get("default_target_fps"))
        if not math.isfinite(target_fps) or not 1 <= target_fps <= 1000:
            raise ValueError
        value["default_target_fps"] = str(int(target_fps)) if target_fps.is_integer() else str(target_fps)
    except (TypeError, ValueError):
        value["default_target_fps"] = DEFAULT_CONFIG["default_target_fps"]
    if not isinstance(value.get("output_directory"), str):
        value["output_directory"] = ""
    if not isinstance(value.get("encoder"), str) or not value["encoder"]:
        value["encoder"] = DEFAULT_CONFIG["encoder"]
    try:
        crf = float(value.get("crf"))
        if not math.isfinite(crf) or not 0 <= crf <= 51:
            raise ValueError
        value["crf"] = int(round(crf))
    except (TypeError, ValueError):
        value["crf"] = DEFAULT_CONFIG["crf"]
    valid_presets = {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow", "placebo"}
    if value.get("preset") not in valid_presets:
        value["preset"] = DEFAULT_CONFIG["preset"]
    if not isinstance(value.get("model"), str) or not value["model"].startswith("rife-"):
        value["model"] = DEFAULT_CONFIG["model"]
    if value.get("video_preset") not in {"balanced", "custom"}:
        value["video_preset"] = DEFAULT_CONFIG["video_preset"]
    if value.get("encoder_mode") not in {"auto", "manual"}:
        value["encoder_mode"] = DEFAULT_CONFIG["encoder_mode"]
    return value


def load_config():
    global CONFIG
    config_path = paths.CONFIG_PATH
    config_dir = paths.CONFIG_DIR
    try:
        old_config = config_dir.parent / "config.json"
        if not config_path.exists() and old_config.exists():
            with open(old_config) as f:
                data = json.load(f)
            CONFIG = _validated_config(data)
            save_config()
            old_config.unlink(missing_ok=True)
        elif config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
            CONFIG = _validated_config(data)
        else:
            CONFIG = dict(DEFAULT_CONFIG)
            CONFIG["language"] = paths.DEFAULT_LANGUAGE
            save_config()
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        if config_path.exists():
            corrupt = config_path.with_suffix(config_path.suffix + ".corrupt")
            try:
                os.replace(config_path, corrupt)
            except OSError:
                pass
        CONFIG = dict(DEFAULT_CONFIG)
        CONFIG["language"] = paths.DEFAULT_LANGUAGE
        save_config()


def save_config():
    try:
        paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        temporary = paths.CONFIG_PATH.with_suffix(paths.CONFIG_PATH.suffix + ".tmp")
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(CONFIG, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, paths.CONFIG_PATH)
    except OSError:
        pass
