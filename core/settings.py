from .colors import Color
from .config import CONFIG, save_config
from .console import status
from .i18n import _, get_language_name, LANG_CODES
from .models import install_model, list_available_rife_models
from . import paths


def _run_language_wizard():
    from platform import get_platform
    plat = get_platform()
    print()
    i = plat.interactive_select("Select language / Seleccione idioma:",
                                [get_language_name(c) for c in LANG_CODES])
    if 0 <= i < len(LANG_CODES):
        CONFIG["language"] = LANG_CODES[i]
        save_config()
        print(f"{Color.ok(_('[+]'))} Language set to: {get_language_name(LANG_CODES[i])}")
    else:
        CONFIG["language"] = "en"
        save_config()
    print()


def _run_settings():
    from platform import get_platform
    plat = get_platform()
    encoder_presets = plat.get_encoder_presets()
    expanded = False
    while True:
        options = [
            f"{_('Language')}: {get_language_name(CONFIG['language'])}",
        ]
        if expanded:
            adv_start = len(options)
            options += [
                f"{_('Encoder')}: {CONFIG['encoder']}",
                f"{_('CRF')}: {CONFIG['crf']}",
                f"{_('ffmpeg preset')}: {CONFIG['preset']}",
                f"{_('Model')}: {CONFIG['model']}",
            ]
            toggle_idx = len(options)
            options.append(f"▲ {_('Advanced')}")
        else:
            adv_start = None
            toggle_idx = len(options)
            options.append(f"{_('Advanced')} ▸")
        save_idx = len(options)
        options.append(_('Save & exit'))
        cancel_idx = len(options)
        options.append(_('Cancel'))

        i = plat.interactive_select(Color.bold(_("Settings")), options)
        if i < 0:
            break
        if i == 0:
            li = plat.interactive_select(_("Language selection"),
                                         [get_language_name(c) for c in LANG_CODES])
            if 0 <= li < len(LANG_CODES):
                CONFIG["language"] = LANG_CODES[li]
        elif expanded and adv_start is not None and i < toggle_idx:
            sub = i - adv_start
            if sub == 0:
                encoders = list(encoder_presets.keys())
                ei = plat.interactive_select(_("Encoder"), encoders)
                if 0 <= ei < len(encoders):
                    CONFIG["encoder"] = encoders[ei]
                    CONFIG["video_preset"] = "custom"
            elif sub == 1:
                print(f"\n{Color.dim(_('CRF'))} (0-51, {_('lower = better quality')}):")
                try:
                    v = input(f"{Color.magenta('>')} ").strip()
                    v = int(v)
                    if 0 <= v <= 51:
                        CONFIG["crf"] = v
                        CONFIG["video_preset"] = "custom"
                except (ValueError, EOFError):
                    pass
            elif sub == 2:
                presets = ["ultrafast", "superfast", "veryfast", "faster",
                           "fast", "medium", "slow", "slower", "veryslow", "placebo"]
                pi = plat.interactive_select(_("ffmpeg preset"), presets)
                if 0 <= pi < len(presets):
                    CONFIG["preset"] = presets[pi]
                    CONFIG["video_preset"] = "custom"
            elif sub == 3:
                available = list_available_rife_models()
                mi = plat.interactive_select(_("Model"), available)
                if 0 <= mi < len(available):
                    selected = available[mi]
                    if not (paths.MODELS_DIR / selected).is_dir():
                        status(f"{_('Model')} {selected} {_('not installed. Downloading...')}")
                        if not install_model(selected):
                            status(f"{_('Failed to download')} {selected}.", "ERROR")
                            continue
                    CONFIG["model"] = selected
                    CONFIG["video_preset"] = "custom"
        elif i == toggle_idx:
            expanded = not expanded
        elif i == save_idx:
            save_config()
            break
        elif i == cancel_idx:
            break
