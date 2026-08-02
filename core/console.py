import sys
from .colors import Color
from .config import CONFIG
from .i18n import _


def status(msg, level="INFO"):
    c = {"INFO": (Color.info, "[*]"), "OK": (Color.ok, "[✓]"),
         "WARN": (Color.warn, "[!]"), "ERROR": (Color.error, "[x]")}
    cf, pr = c.get(level, (Color.info, "[*]"))
    print(f"{cf(_(pr))} {cf(msg)}", flush=True)


def _yes_words():
    lang = CONFIG.get("language", "en")
    return ("y", "yes", "sí", "si", "s") if lang == "es" else ("y", "yes")


def _no_words():
    lang = CONFIG.get("language", "en")
    return ("n", "no") if lang == "es" else ("n", "no")


def ask_yes_no(question, default=False):
    lang = CONFIG.get("language", "en")
    if lang == "es":
        sfx = f" {Color.bold('[S/n]')} " if default else f" {Color.bold('[s/N]')} "
        hint = _("Respond y (yes) or n (no).")
    else:
        sfx = f" {Color.bold('[Y/n]')} " if default else f" {Color.bold('[y/N]')} "
        hint = _("Respond y (yes) or n (no).")
    while True:
        try:
            resp = input(f"{Color.magenta('?')} {_(question)}{Color.dim(sfx)}").strip().lower()
        except EOFError:
            print()
            return default
        if not resp:
            return default
        if resp in _yes_words():
            return True
        if resp in _no_words():
            return False
        print(f"{Color.warn(_(hint))}")
