import json
import os
import re
import shutil
import subprocess
import sys
import termios
import tty

from core.colors import Color
from core.console import status
from core.i18n import _


ENCODER_PRESETS = {
    "libx264":              {"codec": "libx264",            "hwaccel": None,          "pix_fmt": "yuv420p"},
    "libx265":              {"codec": "libx265",            "hwaccel": None,          "pix_fmt": "yuv420p"},
    "h264_videotoolbox":    {"codec": "h264_videotoolbox",  "hwaccel": "videotoolbox","pix_fmt": "nv12"},
    "hevc_videotoolbox":    {"codec": "hevc_videotoolbox",  "hwaccel": "videotoolbox","pix_fmt": "nv12"},
}

HW_ENCODER_MAP = [
    ("apple", ["h264_videotoolbox", "hevc_videotoolbox"]),
]


def _classify_gpu_macos(name):
    n = name.lower()
    if any(k in n for k in ("apple", "m1", "m2", "m3", "m4", "m5")):
        return "apple_silicon"
    if any(k in n for k in ("rtx", "quadro", "tesla", "pro duo", "radeon rx")):
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


class MacOSPlatform:
    os_name = "macos"
    bin_ext = ""
    default_language = "en"

    def get_encoder_presets(self):
        return ENCODER_PRESETS

    def get_hw_encoder_map(self):
        return HW_ENCODER_MAP

    def detect_apple_silicon(self):
        try:
            result = subprocess.run(["sysctl", "-n", "hw.optional.arm64"], capture_output=True, text=True, timeout=5)
            return result.stdout.strip() == "1"
        except Exception:
            return False

    def detect_pci_gpus(self):
        return self.detect_macos_gpus()

    def detect_macos_gpus(self):
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                capture_output=True, text=True, timeout=15
            )
            data = json.loads(result.stdout)
            gpus = []
            for gpu in data.get("SPDisplaysDataType", []):
                name = gpu.get("sppci_model", gpu.get("_name", "Unknown"))
                vendor = "unknown"
                n = name.lower()
                if "apple" in n:
                    vendor = "apple"
                elif "nvidia" in n:
                    vendor = "nvidia"
                elif "amd" in n or "radeon" in n:
                    vendor = "amd"
                elif "intel" in n:
                    vendor = "intel"
                metal_str = gpu.get("spdisplays_metal", "")
                if "apple" in metal_str.lower():
                    vendor = "apple"
                gpus.append((vendor, name))
            return gpus
        except Exception:
            return []

    def detect_vulkan_gpus(self):
        gpus = self.detect_macos_gpus()
        devices = []
        for i, (vendor, name) in enumerate(gpus):
            klass = _classify_gpu_macos(name)
            devices.append((i, name, klass))
        return devices

    def choose_gpu_settings(self, width, height):
        devices = self.detect_vulkan_gpus()
        is_uhd_res = max(width, height) >= 3200
        cpus = os.cpu_count() or 4

        if not devices:
            t = f"1:{min(cpus, 2)}:{min(cpus, 2)}"
            return {"gpu_id": None, "gpu_name": "not detected", "threads": t,
                    "uhd": is_uhd_res, "class": "unknown", "tile_size": 0,
                    "ffmpeg_gpu": {"hwaccel": "videotoolbox", "hint": ""}}

        priority = {"apple_silicon": 0, "discrete_high": 1, "discrete": 2, "integrated": 3, "unknown": 4}
        sorted_devs = sorted(devices, key=lambda d: priority.get(d[2], 4))
        best = sorted_devs[0]
        gpu_id, name, cls = best

        ct = min(cpus, 16)
        if cls == "apple_silicon":
            threads = f"4:{min(ct, 8)}:{min(ct, 4)}"
        elif cls == "discrete_high":
            threads = f"2:{min(ct * 2, 16)}:{min(ct, 8)}"
        elif cls == "discrete":
            threads = f"1:{ct}:{min(ct, 4)}"
        elif cls == "integrated":
            threads = f"1:{min(ct, 2)}:{min(ct, 2)}"
        else:
            threads = f"1:{min(ct, 2)}:{min(ct, 2)}"

        tile_size = 0
        if is_uhd_res:
            tile_size = 1024 if cls in ("apple_silicon", "discrete_high", "discrete") else 512

        ffmpeg_gpu = {"hwaccel": "videotoolbox", "hint": ""}
        if cls == "apple_silicon":
            ffmpeg_gpu["hint"] = " (Apple Silicon)"
        elif "nvidia" in name.lower():
            ffmpeg_gpu["hint"] = " (NVIDIA)"
        elif "amd" in name.lower() or "radeon" in name.lower():
            ffmpeg_gpu["hint"] = " (AMD)"
        elif "intel" in name.lower():
            ffmpeg_gpu["hint"] = " (Intel)"
        if ffmpeg_gpu["hint"]:
            status(f"{_('RIFE on')}: {name}{ffmpeg_gpu['hint']}", "OK")

        return {"gpu_id": gpu_id, "gpu_name": name, "threads": threads,
                "uhd": is_uhd_res, "class": cls, "tile_size": tile_size,
                "ffmpeg_gpu": ffmpeg_gpu}

    def interactive_select(self, prompt, options):
        n = len(options)
        if n == 0:
            return -1

        if not sys.stdin.isatty():
            print(f"\n{Color.bold(prompt)}")
            for i, opt in enumerate(options):
                print(f"  {i+1}. {opt}")
            while True:
                try:
                    resp = input(f"{Color.magenta('>')} ").strip()
                    if resp:
                        idx = int(resp) - 1
                        if 0 <= idx < n:
                            return idx
                except (ValueError, EOFError):
                    pass
                print(f"{Color.warn(_('Enter a number between 1 and'))} {n}.")

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        idx = 0
        max_opt = max(len(opt) for opt in options)
        max_w = max_opt + 2
        term_w = shutil.get_terminal_size().columns
        pad = " " * max(0, (term_w - max_w) // 2)
        try:
            tty.setraw(fd)
            if prompt:
                sys.stdout.write("\r" + " " * max(0, (term_w - len(prompt)) // 2) + Color.bold(prompt) + "\r\n")
            for i, opt in enumerate(options):
                sys.stdout.write(pad + " " + (">" if i == idx else " ") + " " + opt + "\r\n")
            sys.stdout.flush()
            while True:
                ch = sys.stdin.read(1)
                if ch == "\x03":
                    termios.tcsetattr(fd, termios.TCSANOW, old)
                    sys.stdout.write("\r\n")
                    sys.stdout.flush()
                    sys.exit(130)
                if ch == "\x1b":
                    seq = sys.stdin.read(2)
                    if seq == "[A":
                        idx = (idx - 1) % n
                    elif seq == "[B":
                        idx = (idx + 1) % n
                    sys.stdout.write(f"\x1b[{n}A")
                    for i, opt in enumerate(options):
                        sys.stdout.write("\r" + pad + " " + (">" if i == idx else " ") + " " + opt + "\x1b[K\r\n")
                    sys.stdout.flush()
                elif ch in ("b", "B"):
                    idx = -1
                    sys.stdout.write(f"\x1b[{n}A")
                    for _ in range(n):
                        sys.stdout.write("\r\x1b[K\n")
                    sys.stdout.flush()
                    break
                elif ch == "\r":
                    total = n + 1
                    sys.stdout.write(f"\x1b[{total}A")
                    for i in range(total):
                        sys.stdout.write("\r\x1b[K\x1b[B")
                    sys.stdout.write(f"\x1b[{total}A")
                    sys.stdout.flush()
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, old)
        sys.stdout.flush()
        return idx

    def interactive_select_video(self, options):
        n = len(options)
        if n == 0:
            return -1

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        idx = 0
        max_opt = max(len(opt) for opt in options)
        max_w = max_opt + 2
        term_w = shutil.get_terminal_size().columns
        pad = " " * max(0, (term_w - max_w) // 2)
        try:
            tty.setraw(fd)
            for i, opt in enumerate(options):
                sys.stdout.write(pad + " " + (">" if i == idx else " ") + " " + opt + "\r\n")
            sys.stdout.flush()
            while True:
                ch = sys.stdin.read(1)
                if ch == "\x03":
                    termios.tcsetattr(fd, termios.TCSANOW, old)
                    sys.stdout.write("\r\n")
                    sys.stdout.flush()
                    sys.exit(130)
                if ch == "\x1b":
                    seq = sys.stdin.read(2)
                    if seq == "[A":
                        idx = (idx - 1) % n
                    elif seq == "[B":
                        idx = (idx + 1) % n
                    sys.stdout.write(f"\x1b[{n}A")
                    for i, opt in enumerate(options):
                        sys.stdout.write("\r" + pad + " " + (">" if i == idx else " ") + " " + opt + "\x1b[K\r\n")
                    sys.stdout.flush()
                elif ch in ("b", "B"):
                    idx = -1
                    sys.stdout.write(f"\x1b[{n}A")
                    for _ in range(n):
                        sys.stdout.write("\r\x1b[K\n")
                    sys.stdout.flush()
                    break
                elif ch == "\r":
                    total = n
                    sys.stdout.write(f"\x1b[{total}A")
                    for i in range(total):
                        sys.stdout.write("\r\x1b[K\x1b[B")
                    sys.stdout.write(f"\x1b[{total}A")
                    sys.stdout.flush()
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, old)
        sys.stdout.flush()
        return idx
