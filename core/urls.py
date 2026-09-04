import json
import sys
from urllib.request import Request, urlopen
from . import paths


def _fetch_latest_rife_urls():
    url = "https://api.github.com/repos/nihui/rife-ncnn-vulkan/releases/latest"
    req = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "LocallyFPS"})
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return {}
    assets = data.get("assets", [])
    mapping = {}
    for asset in assets:
        name = asset.get("name", "").lower()
        dl_url = asset.get("browser_download_url", "")
        if "ubuntu" in name and "linux" not in mapping:
            mapping["linux"] = dl_url
        elif "windows" in name and "windows" not in mapping:
            mapping["windows"] = dl_url
        elif "macos" in name and "macos" not in mapping:
            mapping["macos"] = dl_url
    return mapping


_RIFE_URLS_CACHE = None


def get_rife_release_urls():
    global _RIFE_URLS_CACHE
    if _RIFE_URLS_CACHE is None:
        _RIFE_URLS_CACHE = _fetch_latest_rife_urls()
        if not _RIFE_URLS_CACHE:
            _RIFE_URLS_CACHE = {
                "linux": "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-ubuntu.zip",
                "windows": "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-windows.zip",
                "macos": "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-macos.zip",
            }
    return _RIFE_URLS_CACHE


def get_ffmpeg_release_urls():
    return {
        "linux": None,
        "windows": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        "macos": None,
    }


RIFE_RELEASE_URLS = get_rife_release_urls
FFMPEG_RELEASE_URLS = get_ffmpeg_release_urls
