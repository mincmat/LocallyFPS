import os
import re
import shutil
import subprocess
import sys

from core.colors import Color
from core.console import status
from core.gpu import classify_gpu
from core.i18n import _


ENCODER_PRESETS = {
    "libx264":      {"codec": "libx264",      "hwaccel": None,   "pix_fmt": "yuv420p"},
    "libx265":      {"codec": "libx265",      "hwaccel": None,   "pix_fmt": "yuv420p"},
    "libopenh264":  {"codec": "libopenh264",  "hwaccel": None,   "pix_fmt": "yuv420p"},
    "mpeg4":        {"codec": "mpeg4",        "hwaccel": None,   "pix_fmt": "yuv420p"},
    "h264_nvenc":   {"codec": "h264_nvenc",   "hwaccel": "cuda", "pix_fmt": "yuv420p"},
    "hevc_nvenc":   {"codec": "hevc_nvenc",   "hwaccel": "cuda", "pix_fmt": "yuv420p"},
    "h264_qsv":     {"codec": "h264_qsv",     "hwaccel": "qsv",  "pix_fmt": "nv12"},
    "hevc_qsv":     {"codec": "hevc_qsv",     "hwaccel": "qsv",  "pix_fmt": "nv12"},
}

HW_ENCODER_MAP = [
    ("nvidia", ["h264_nvenc", "hevc_nvenc"]),
    ("intel",  ["h264_qsv", "hevc_qsv"]),
]


class WindowsPlatform:
    os_name = "windows"
    bin_ext = ".exe"
    default_language = "es"

    def get_encoder_presets(self):
        return ENCODER_PRESETS

    def get_hw_encoder_map(self):
        return HW_ENCODER_MAP

    def detect_pci_gpus(self):
        # Try PowerShell first, fall back to wmic
        for cmd in [
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
            ["wmic", "path", "win32_VideoController", "get", "name"],
        ]:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            except Exception:
                continue
            gpus = []
            for line in result.stdout.splitlines():
                name = line.strip()
                if not name or name.lower() in ("name", "---"):
                    continue
                low = name.lower()
                if "nvidia" in low or "geforce" in low or "quadro" in low:
                    vendor = "nvidia"
                elif "amd" in low or "radeon" in low:
                    vendor = "amd"
                elif "intel" in low:
                    vendor = "intel"
                else:
                    continue
                gpus.append((vendor, name))
            if gpus:
                return gpus
        return []

    def detect_vulkan_gpus(self):
        if shutil.which("vulkaninfo") is None:
            return []
        try:
            result = subprocess.run(
                ["vulkaninfo", "--summary"],
                capture_output=True, text=True, timeout=15,
            )
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
        real_devices = [d for d in devices if "llvmpipe" not in d[1].lower()]
        if real_devices:
            return real_devices
        try:
            import json
            result2 = subprocess.run(
                ["vulkaninfo", "--summary", "--json"],
                capture_output=True, text=True, timeout=15,
            )
            data = json.loads(result2.stdout)
            for dev in data.get("devices", []):
                uid = dev.get("id", 0)
                name = dev.get("deviceName") or dev.get("properties", {}).get("deviceName", "Unknown")
                devices.append((uid, name, classify_gpu(name)))
        except Exception:
            pass
        return [d for d in devices if "llvmpipe" not in d[1].lower()]

    def choose_gpu_settings(self, width, height):
        devices = self.detect_vulkan_gpus()
        max_dim = max(width, height)
        is_uhd_res = max_dim >= 3200
        cpus = os.cpu_count() or 4

        if not devices:
            status(_("No GPU detected via Vulkan; using conservative settings."), "WARN")
            t = f"1:{min(cpus, 2)}:{min(cpus, 2)}"
            rife_cpu = max_dim >= 2560
            return {"gpu_id": None, "gpu_name": "not detected", "threads": t,
                    "uhd": False, "rife_cpu": rife_cpu, "class": "unknown", "tile_size": 0,
                    "ffmpeg_gpu": {"hwaccel": "auto", "hint": ""}}

        priority = {"discrete_high": 0, "discrete": 1, "integrated": 2, "unknown": 3}
        sorted_devs = sorted(devices, key=lambda d: priority.get(d[2], 3))
        best = sorted_devs[0]
        gpu_id, name, cls = best

        is_dedicated = cls in ("discrete_high", "discrete")

        ct = min(cpus, 16)
        if cls == "discrete_high":
            threads = f"2:{min(ct * 2, 16)}:{min(ct, 16)}"
        elif cls == "discrete":
            threads = f"1:{ct}:{min(ct, 4)}"
        else:
            threads = f"1:{min(ct, 2)}:{min(ct, 2)}"

        tile_size = 0
        if is_uhd_res:
            if cls == "discrete_high":
                tile_size = 1024
            elif cls == "discrete":
                tile_size = 512
            elif cls == "integrated":
                tile_size = 256

        uhd = is_uhd_res and is_dedicated
        rife_cpu = (not is_dedicated) and max_dim >= 2560

        ffmpeg_gpu = {"hwaccel": "auto", "hint": ""}
        if "nvidia" in name.lower():
            ffmpeg_gpu = {"hwaccel": "cuda", "hint": " (NVIDIA)"}

        return {"gpu_id": gpu_id, "gpu_name": name, "threads": threads,
                "uhd": uhd, "rife_cpu": rife_cpu, "class": cls, "tile_size": tile_size,
                "ffmpeg_gpu": ffmpeg_gpu}

    def interactive_select(self, prompt, options, disabled=None):
        n = len(options)
        if n == 0:
            return -1
        disabled = disabled or set()
        selectable = [(i, opt) for i, opt in enumerate(options) if i not in disabled]
        if not selectable:
            return -1

        print(f"\n{Color.bold(prompt)}")
        for idx, (i, opt) in enumerate(selectable):
            print(f"  {idx + 1}. {opt}")
        while True:
            try:
                resp = input(f"{Color.magenta('>')} ").strip()
                if resp:
                    idx = int(resp) - 1
                    if 0 <= idx < len(selectable):
                        return selectable[idx][0]
            except (ValueError, EOFError):
                pass
            print(f"{Color.warn(_('Enter a number between'))} 1 {_('and')} {len(selectable)}.")

    def interactive_select_video(self, options, hint=None):
        n = len(options)
        if n == 0:
            return -1

        print()
        for i, opt in enumerate(options):
            print(f"  {i + 1}. {opt}")
        if hint:
            print(f"\n  {Color.dim(hint)}")
        while True:
            try:
                resp = input(f"{Color.magenta('>')} ").strip()
                if resp:
                    idx = int(resp) - 1
                    if 0 <= idx < n:
                        return idx
            except (ValueError, EOFError):
                pass
            print(f"{Color.warn(_('Enter a number between'))} 1 {_('and')} {n}.")
