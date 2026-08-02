import json
from . import paths
from .config import CONFIG

TRANSLATIONS = {}

LANGUAGE_NAMES = {
    "en": "English", "es": "Español",
}
LANG_CODES = list(LANGUAGE_NAMES.keys())


def load_translations():
    global TRANSLATIONS
    lang_dir = paths.LANG_DIR
    if not lang_dir or not lang_dir.is_dir():
        return
    for lang_file in sorted(lang_dir.glob("*.json")):
        lang_code = lang_file.stem
        try:
            with open(lang_file, encoding="utf-8") as f:
                TRANSLATIONS[lang_code] = json.load(f)
        except Exception:
            TRANSLATIONS[lang_code] = {}


def _(text):
    lang = CONFIG.get("language", "en")
    if lang in TRANSLATIONS and text in TRANSLATIONS[lang]:
        return TRANSLATIONS[lang][text]
    return text


def get_language_name(code):
    return LANGUAGE_NAMES.get(code, code)
