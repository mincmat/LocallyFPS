import shutil
import sys

from .console import status, ask_yes_no
from .i18n import _
from .utils import human_size


def check_disk_space(path, estimated_bytes):
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
            if not sys.stdin.isatty():
                status(_("Insufficient disk space for unattended processing. Aborting."), "ERROR")
                sys.exit(1)
            if not ask_yes_no(_("Continue anyway? (might fail if disk fills up)"), default=False):
                status(_("Operation cancelled."), "WARN")
                sys.exit(0)
    except OSError:
        pass


def estimate_frame_storage(width, height, frame_count):
    """Conservative upper estimate for lossless RGB PNG frame storage.

    PNG may barely compress noisy/grainy material, so using a small fraction of
    raw RGB is unsafe. The overhead factor also covers filesystem metadata.
    """
    width = max(1, int(width))
    height = max(1, int(height))
    frame_count = max(0, int(frame_count))
    return int(width * height * 3 * frame_count * 1.05)


def estimate_pipeline_storage(width, height, source_frames, source_fps, target_fps):
    source_frames = max(1, int(source_frames))
    if source_fps <= 0 or target_fps <= 0:
        target_frames = source_frames
    else:
        target_frames = max(1, round(source_frames * target_fps / source_fps))
    return estimate_frame_storage(width, height, source_frames + target_frames)
