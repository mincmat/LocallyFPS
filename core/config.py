import json
from . import paths

DEFAULT_CONFIG = {
    "language": "en",
    "encoder": "libx264",
    "crf": 16,
    "preset": "fast",
    "model": "rife-v4.6",
    "video_preset": "custom",
}

CONFIG = dict(DEFAULT_CONFIG)


def load_config():
    global CONFIG
    config_path = paths.CONFIG_PATH
    config_dir = paths.CONFIG_DIR
    try:
        old_config = config_dir.parent / "config.json"
        if not config_path.exists() and old_config.exists():
            with open(old_config) as f:
                data = json.load(f)
            CONFIG = {**DEFAULT_CONFIG, **data}
            save_config()
            old_config.unlink(missing_ok=True)
        elif config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
            CONFIG = {**DEFAULT_CONFIG, **data}
        else:
            CONFIG = dict(DEFAULT_CONFIG)
            CONFIG["language"] = paths.DEFAULT_LANGUAGE
            save_config()
    except Exception:
        CONFIG = dict(DEFAULT_CONFIG)
        CONFIG["language"] = paths.DEFAULT_LANGUAGE


def save_config():
    try:
        paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(paths.CONFIG_PATH, "w") as f:
            json.dump(CONFIG, f, indent=2)
    except OSError:
        pass
