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
            if not ask_yes_no(_("Continue anyway? (might fail if disk fills up)"), default=False):
                status(_("Operation cancelled."), "WARN")
                sys.exit(0)
    except OSError:
        pass


def estimate_frame_storage(width, height, frame_count):
    return int(width * height * 3 * frame_count * 0.08)
