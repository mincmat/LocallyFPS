from pathlib import Path

from . import paths
from .utils import clean_path_input


def build_default_output_name(input_path, target_fps):
    fps_label = str(int(target_fps)) if target_fps == int(target_fps) else f"{target_fps}".replace(".", "_")
    return f"ENHANCED_{fps_label}FPS_{input_path.name}"


def resolve_output_path(raw, input_path, target_fps):
    default_name = build_default_output_name(input_path, target_fps)
    raw = clean_path_input(raw)

    if not raw:
        enhanced_dir = paths.DOWNLOADS_DIR / "interpoled_locallyfps"
        enhanced_dir.mkdir(parents=True, exist_ok=True)
        return enhanced_dir / default_name
    out_path = Path(raw).expanduser().resolve()
    if out_path.is_dir():
        return out_path / default_name
    if out_path.suffix == "":
        out_path.mkdir(parents=True, exist_ok=True)
        return out_path / default_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return out_path


def unique_output_path(path):
    """Return a free sibling path so graphical runs never overwrite exports."""
    path = Path(path)
    if not path.exists():
        return path
    for number in range(2, 10_000):
        candidate = path.with_name(f"{path.stem}_{number}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError("Could not choose an unused output filename.")
