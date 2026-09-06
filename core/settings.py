import os
import sys

from .colors import Color
from . import config
from .config import save_config
from .i18n import _, get_language_name, LANG_CODES
from . import paths


def _run_language_wizard():
    from platform import get_platform
    plat = get_platform()
    print()
    i = plat.interactive_select("Select language / Seleccione idioma:",
                                [get_language_name(c) for c in LANG_CODES])
    if 0 <= i < len(LANG_CODES):
        config.CONFIG["language"] = LANG_CODES[i]
        save_config()
        print(f"{Color.ok(_('[+]'))} Language set to: {get_language_name(LANG_CODES[i])}")
    else:
        config.CONFIG["language"] = "en"
        save_config()
    print()


def _run_advanced_settings():
    from platform import get_platform
    plat = get_platform()
    encoder_presets = plat.get_encoder_presets()
    while True:
        options = [
            f"{_('Encoder')}: {config.CONFIG['encoder']}",
            f"{_('CRF')}: {config.CONFIG['crf']}",
            f"{_('ffmpeg preset')}: {config.CONFIG['preset']}",
            _('Back'),
        ]
        i = plat.interactive_select(Color.bold(_("Advanced")), options)
        if i < 0 or i == 3:
            break
        if i == 0:
            encoders = list(encoder_presets.keys())
            ei = plat.interactive_select(_("Encoder"), encoders)
            if 0 <= ei < len(encoders):
                config.CONFIG["encoder"] = encoders[ei]
                config.CONFIG["encoder_mode"] = "manual"
        elif i == 1:
            print(f"\n{Color.dim(_('CRF'))} (0-51, {_('lower = better quality')}):")
            try:
                v = input(f"{Color.magenta('>')} ").strip()
                v = int(v)
                if 0 <= v <= 51:
                    config.CONFIG["crf"] = v
            except (ValueError, EOFError):
                pass
        elif i == 2:
            presets = ["ultrafast", "superfast", "veryfast", "faster",
                       "fast", "medium", "slow", "slower", "veryslow", "placebo"]
            pi = plat.interactive_select(_("ffmpeg preset"), presets)
            if 0 <= pi < len(presets):
                config.CONFIG["preset"] = presets[pi]


_SEPARATOR = "─── ─── ───"


def _run_settings():
    from platform import get_platform
    from .console import ask_yes_no
    plat = get_platform()
    original = dict(config.CONFIG)
    disabled = {2, 5}
    while True:
        options = [
            f"{_('Language')}: {get_language_name(config.CONFIG['language'])}",
            _('Advanced'),
            _SEPARATOR,
            _('Save & exit'),
            _('Discard & exit'),
            _SEPARATOR,
            _('Reset settings'),
        ]
        i = plat.interactive_select(Color.bold(_("Settings")), options, disabled=disabled)
        if i < 0:
            config.CONFIG.update(original)
            break
        if i == 0:
            li = plat.interactive_select(_("Language selection"),
                                         [get_language_name(c) for c in LANG_CODES])
            if 0 <= li < len(LANG_CODES):
                config.CONFIG["language"] = LANG_CODES[li]
        elif i == 1:
            _run_advanced_settings()
        elif i == 3:
            save_config()
            break
        elif i == 4:
            config.CONFIG.update(original)
            break
        elif i == 6:
            if ask_yes_no(_("Reset all settings to default?"), default=False):
                config.CONFIG.update(config.DEFAULT_CONFIG)
                save_config()
                if paths.CONFIG_PATH.exists():
                    paths.CONFIG_PATH.unlink()
                os.execv(sys.executable, [sys.executable] + sys.argv)
