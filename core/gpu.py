import os
import re

from .console import status
from .i18n import _


def classify_gpu(name):
    n = name.lower()
    if any(k in n for k in ("rtx", "quadro", "tesla", "a100", "h100", "arc", "pro duo", "radeon rx")):
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


def estimate_duration(frame_count, width, height, gpu_class):
    base_rate = {"discrete_high": 12.0, "discrete": 6.0,
                 "integrated": 2.5, "unknown": 1.5}.get(gpu_class, 1.5)
    pixels = max(width * height, 1)
    scale = max(0.2, min(2073600 / pixels, 2.0))
    effective_rate = max(base_rate * scale, 0.1)
    return frame_count / effective_rate


def choose_gpu_settings(width, height):
    from platform import get_platform
    plat = get_platform()
    return plat.choose_gpu_settings(width, height)
