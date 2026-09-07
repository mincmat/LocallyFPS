import os
import sys

_platform_instance = None


def get_platform():
    global _platform_instance
    if _platform_instance is not None:
        return _platform_instance

    if sys.platform == "darwin":
        from .macos import MacOSPlatform
        _platform_instance = MacOSPlatform()
    elif os.name == "nt":
        from .windows import WindowsPlatform
        _platform_instance = WindowsPlatform()
    else:
        from .linux import LinuxPlatform
        _platform_instance = LinuxPlatform()
    return _platform_instance


def reset_platform():
    global _platform_instance
    _platform_instance = None
