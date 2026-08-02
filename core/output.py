from pathlib import Path

from . import paths
from .utils import clean_path_input


def build_default_output_name(input_path, target_fps):
    fps_label = str(int(target_fps)) if target_fps == int(target_fps) else f"{target_fps}".replace(".", "_")
    return f"ENHANCED_{fps_label}FPS_{input_path.name}"


def resolve_output_path(raw, input_path, target_fps):
    default_name = build_default_output_name(input_path, target_fps)
    raw = clean_path_input(raw)

    enhanced_dir = paths.VIDEOS_DIR / "enhanced"
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
