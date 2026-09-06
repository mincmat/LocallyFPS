import sys
from .colors import Color
from . import config
from .i18n import _


def _safe_print(value="", **kwargs):
    """Print without crashing on legacy consoles with narrow encodings."""
    try:
        print(value, **kwargs)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        compatible = str(value).encode(encoding, errors="replace").decode(encoding)
        print(compatible, **kwargs)


def status(msg, level="INFO"):
    c = {"INFO": (Color.info, "[*]"), "OK": (Color.ok, "[✓]"),
         "WARN": (Color.warn, "[!]"), "ERROR": (Color.error, "[x]")}
    cf, pr = c.get(level, (Color.info, "[*]"))
    _safe_print(f"{cf(_(pr))} {cf(msg)}", flush=True)


def _yes_words():
    lang = config.CONFIG.get("language", "en")
    return ("y", "yes", "sí", "si", "s") if lang == "es" else ("y", "yes")


def _no_words():
    lang = config.CONFIG.get("language", "en")
    return ("n", "no") if lang == "es" else ("n", "no")


def ask_yes_no(question, default=False):
    lang = config.CONFIG.get("language", "en")
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
            _safe_print()
            return default
        if not resp:
            return default
        if resp in _yes_words():
            return True
        if resp in _no_words():
            return False
        _safe_print(f"{Color.warn(_(hint))}")
