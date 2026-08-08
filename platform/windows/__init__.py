import ctypes
import json
import os
import re
import shutil
import subprocess
import sys

from core.colors import Color
from core.console import status
from core.gpu import classify_gpu
from core.i18n import _

try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False


ENCODER_PRESETS = {
    "libx264":    {"codec": "libx264",    "hwaccel": None,     "pix_fmt": "yuv420p"},
    "libx265":    {"codec": "libx265",    "hwaccel": None,     "pix_fmt": "yuv420p"},
    "h264_nvenc": {"codec": "h264_nvenc", "hwaccel": "cuda",   "pix_fmt": "yuv420p"},
    "hevc_nvenc": {"codec": "hevc_nvenc", "hwaccel": "cuda",   "pix_fmt": "yuv420p"},
    "h264_amf":   {"codec": "h264_amf",   "hwaccel": "d3d11va","pix_fmt": "nv12"},
    "hevc_amf":   {"codec": "hevc_amf",   "hwaccel": "d3d11va","pix_fmt": "nv12"},
    "h264_qsv":   {"codec": "h264_qsv",   "hwaccel": "qsv",    "pix_fmt": "nv12"},
    "hevc_qsv":   {"codec": "hevc_qsv",   "hwaccel": "qsv",    "pix_fmt": "nv12"},
}

HW_ENCODER_MAP = [
    ("nvidia", ["h264_nvenc", "hevc_nvenc"]),
    ("amd",    ["h264_amf", "hevc_amf"]),
    ("intel",  ["h264_qsv", "hevc_qsv"]),
]


def enable_windows_ansi():
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        for handle_id in (-11, -12):
            h = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(h, ctypes.byref(mode)):
                kernel32.SetConsoleMode(h, mode.value | 0x0004)
    except Exception:
        pass


class WindowsPlatform:
    os_name = "windows"
    bin_ext = ".exe"
    default_language = "es"

    def get_encoder_presets(self):
        return ENCODER_PRESETS

    def get_hw_encoder_map(self):
        return HW_ENCODER_MAP

    def detect_pci_gpus(self):
        return self.detect_wmi_gpus()

    def detect_wmi_gpus(self):
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, timeout=15
            )
        except Exception:
            return []
        gpus = []
        for line in result.stdout.splitlines():
            name = line.strip()
            if not name:
                continue
            low = name.lower()
            if "nvidia" in low:
                vendor = "nvidia"
            elif "amd" in low or "radeon" in low or "ati " in low:
                vendor = "amd"
            elif "intel" in low:
                vendor = "intel"
            else:
                continue
            gpus.append((vendor, name))
        return gpus

    def detect_vulkan_gpus(self):
        if shutil.which("vulkaninfo") is None:
            return []
        try:
            result = subprocess.run(["vulkaninfo", "--summary"], capture_output=True, text=True, timeout=15)
        except Exception:
            return []
        devices = []
        current_id = None
        for line in result.stdout.splitlines():
            m = re.match(r"\s*GPU(\d+)\s*:", line)
            if m:
                current_id = int(m.group(1))
                continue
            m2 = re.search(r"deviceName\s*=\s*(.+)", line)
            if m2 and current_id is not None:
                name = m2.group(1).strip()
                devices.append((current_id, name, classify_gpu(name)))
        if devices:
            return devices
        try:
            result2 = subprocess.run(["vulkaninfo", "--summary", "--json"], capture_output=True, text=True, timeout=15)
            data = json.loads(result2.stdout)
            for dev in data.get("devices", []):
                uid = dev.get("id", 0)
                name = dev.get("deviceName") or dev.get("properties", {}).get("deviceName", "Unknown")
                devices.append((uid, name, classify_gpu(name)))
        except Exception:
            pass
        return devices

    def choose_gpu_settings(self, width, height):
        devices = self.detect_vulkan_gpus()
        is_uhd_res = max(width, height) >= 3200
        cpus = os.cpu_count() or 4

        if not devices:
            wmi_gpus = self.detect_wmi_gpus()
            if wmi_gpus:
                priority = {"discrete_high": 0, "discrete": 1, "integrated": 2, "unknown": 3}
                classified = [(v, n, classify_gpu(n)) for v, n in wmi_gpus]
                classified.sort(key=lambda d: priority.get(d[2], 3))
                vendor, name, cls = classified[0]
                status(f"{_('Detected GPU')} (WMI): {name}", "INFO")
                ct = min(cpus, 8)
                if cls == "discrete_high":
                    threads = f"2:{min(ct * 2, 8)}:{min(ct, 8)}"
                elif cls == "discrete":
                    threads = f"1:{ct}:{min(ct, 4)}"
                else:
                    threads = f"1:{min(ct, 2)}:{min(ct, 2)}"
                tile_size = 0
                if is_uhd_res:
                    tile_size = 1024 if cls in ("discrete_high", "discrete") else 512
                hwaccel_map = {"nvidia": "cuda", "amd": "d3d11va", "intel": "qsv"}
                ffmpeg_gpu = {"hwaccel": hwaccel_map.get(vendor, "auto"), "hint": f" ({vendor})"}
                return {"gpu_id": None, "gpu_name": name, "threads": threads,
                        "uhd": is_uhd_res, "class": cls, "tile_size": tile_size,
                        "ffmpeg_gpu": ffmpeg_gpu}

            status(_("No GPU detected via Vulkan; using conservative settings."), "WARN")
            t = f"1:{min(cpus, 2)}:{min(cpus, 2)}"
            return {"gpu_id": None, "gpu_name": "not detected", "threads": t,
                    "uhd": is_uhd_res, "class": "unknown", "tile_size": 0,
                    "ffmpeg_gpu": {"hwaccel": "auto", "hint": ""}}

        priority = {"discrete_high": 0, "discrete": 1, "integrated": 2, "unknown": 3}
        sorted_devs = sorted(devices, key=lambda d: priority.get(d[2], 3))
        best = sorted_devs[0]
        gpu_id, name, cls = best

        ct = min(cpus, 16)
        if cls == "discrete_high":
            threads = f"2:{min(ct * 2, 16)}:{min(ct, 16)}"
        elif cls == "discrete":
            threads = f"1:{ct}:{min(ct, 4)}"
        else:
            threads = f"1:{min(ct, 2)}:{min(ct, 2)}"

        tile_size = 0
        if is_uhd_res:
            tile_size = 1024 if cls in ("discrete_high", "discrete") else 512

        ffmpeg_gpu = {"hwaccel": "auto", "hint": ""}
        multi_gpu = len(sorted_devs) > 1
        if "nvidia" in name.lower():
            ffmpeg_gpu = {"hwaccel": "cuda", "hint": " (NVIDIA)"}
        elif "amd" in name.lower() or "radeon" in name.lower():
            ffmpeg_gpu = {"hwaccel": "d3d11va", "hint": " (AMD)"}
        elif "intel" in name.lower():
            ffmpeg_gpu = {"hwaccel": "qsv", "hint": " (Intel)"}

        return {"gpu_id": gpu_id, "gpu_name": name, "threads": threads,
                "uhd": is_uhd_res, "class": cls, "tile_size": tile_size,
                "ffmpeg_gpu": ffmpeg_gpu}

    def interactive_select(self, prompt, options):
        n = len(options)
        if n == 0:
            return -1

        if not sys.stdin.isatty() or not HAS_MSVCRT:
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

        idx = 0
        max_opt = max(len(opt) for opt in options)
        max_w = max_opt + 2
        term_w = shutil.get_terminal_size().columns
        pad = " " * max(0, (term_w - max_w) // 2)
        if prompt:
            sys.stdout.write(f"\r{pad}{Color.bold(prompt)}\r\n")
        for i, opt in enumerate(options):
            sys.stdout.write(pad + " " + (">" if i == idx else " ") + " " + opt + "\r\n")
        sys.stdout.flush()
        while True:
            ch = msvcrt.getch()
            if ch == b"\x03":
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                sys.exit(130)
            if ch in (b"\x00", b"\xe0"):
                ch2 = msvcrt.getch()
                if ch2 == b"H":
                    idx = (idx - 1) % n
                elif ch2 == b"P":
                    idx = (idx + 1) % n
                sys.stdout.write(f"\x1b[{n}A")
                for i, opt in enumerate(options):
                    sys.stdout.write("\r" + pad + " " + (">" if i == idx else " ") + " " + opt + "\x1b[K\r\n")
                sys.stdout.flush()
            elif ch in (b"b", b"B"):
                idx = -1
                sys.stdout.write(f"\x1b[{n}A")
                for _ in range(n):
                    sys.stdout.write("\r\x1b[K\n")
                sys.stdout.flush()
                break
            elif ch in (b"\r", b"\n"):
                total = n + 1
                sys.stdout.write(f"\x1b[{total}A")
                for i in range(total):
                    sys.stdout.write("\r\x1b[K\x1b[B")
                sys.stdout.write(f"\x1b[{total}A")
                sys.stdout.flush()
                break
        return idx

    def interactive_select_video(self, options):
        n = len(options)
        if n == 0:
            return -1

        if not HAS_MSVCRT:
            for i, opt in enumerate(options):
                print(f"  {i+1}. {opt}")
            return -1

        idx = 0
        max_opt = max(len(opt) for opt in options)
        max_w = max_opt + 2
        term_w = shutil.get_terminal_size().columns
        pad = " " * max(0, (term_w - max_w) // 2)
        for i, opt in enumerate(options):
            sys.stdout.write(pad + " " + (">" if i == idx else " ") + " " + opt + "\r\n")
        sys.stdout.flush()
        while True:
            ch = msvcrt.getch()
            if ch == b"\x03":
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                sys.exit(130)
            if ch in (b"\x00", b"\xe0"):
                ch2 = msvcrt.getch()
                if ch2 == b"H":
                    idx = (idx - 1) % n
                elif ch2 == b"P":
                    idx = (idx + 1) % n
                sys.stdout.write(f"\x1b[{n}A")
                for i, opt in enumerate(options):
                    sys.stdout.write("\r" + pad + " " + (">" if i == idx else " ") + " " + opt + "\x1b[K\r\n")
                sys.stdout.flush()
            elif ch in (b"b", b"B"):
                idx = -1
                sys.stdout.write(f"\x1b[{n}A")
                for _ in range(n):
                    sys.stdout.write("\r\x1b[K\n")
                sys.stdout.flush()
                break
            elif ch in (b"\r", b"\n"):
                total = n
                sys.stdout.write(f"\x1b[{total}A")
                for i in range(total):
                    sys.stdout.write("\r\x1b[K\x1b[B")
                sys.stdout.write(f"\x1b[{total}A")
                sys.stdout.flush()
                break
        return idx
