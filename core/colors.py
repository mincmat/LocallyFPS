import os
import sys


class Color:
    _ENABLED = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

    if _ENABLED:
        RESET = "\033[0m"
        BOLD = "\033[1m"
        DIM = "\033[2m"
        RED = "\033[31m"
        GREEN = "\033[32m"
        YELLOW = "\033[33m"
        CYAN = "\033[36m"
        MAGENTA = "\033[35m"
        GRAY = "\033[90m"
        ACCENT = "\033[38;5;214m"
    else:
        RESET = BOLD = DIM = RED = GREEN = YELLOW = CYAN = MAGENTA = GRAY = ACCENT = ""

    @classmethod
    def info(cls, t):
        return f"{cls.CYAN}{t}{cls.RESET}"

    @classmethod
    def ok(cls, t):
        return f"{cls.GREEN}{t}{cls.RESET}"

    @classmethod
    def warn(cls, t):
        return f"{cls.YELLOW}{t}{cls.RESET}"

    @classmethod
    def error(cls, t):
        return f"{cls.RED}{t}{cls.RESET}"

    @classmethod
    def bold(cls, t):
        return f"{cls.BOLD}{t}{cls.RESET}"

    @classmethod
    def dim(cls, t):
        return f"{cls.DIM}{t}{cls.RESET}"

    @classmethod
    def magenta(cls, t):
        return f"{cls.MAGENTA}{t}{cls.RESET}"

    @classmethod
    def gray(cls, t):
        return f"{cls.GRAY}{t}{cls.RESET}"

    @classmethod
    def accent(cls, t):
        return f"{cls.ACCENT}{t}{cls.RESET}"

    @classmethod
    def ok_bold(cls, t):
        if cls._ENABLED:
            return f"\033[1;32m{t}\033[0m"
        return t

    @classmethod
    def accent_bold(cls, t):
        if cls._ENABLED:
            return f"\033[1;38;5;214m{t}\033[0m"
        return t
