import shutil
import tempfile
import zipfile
from pathlib import Path

from . import paths
from .console import status
from .deps import download_and_extract, sha256_file
from .i18n import _
from .progress import DownloadProgress
from .urls import RIFE_RELEASE_URLS


def list_available_rife_models():
    models_dir = paths.MODELS_DIR
    if not models_dir.is_dir():
        return ["rife-v4.6"]
    found = sorted(d.name for d in models_dir.iterdir()
                   if d.is_dir() and d.name.startswith("rife-"))
    return found if found else ["rife-v4.6"]


def _get_cached_extract_dir():
    return paths.CACHE_DIR / "rife_release_extracted"


def _ensure_rife_release_cached():
    extract_dir = _get_cached_extract_dir()
    if extract_dir.is_dir() and any(extract_dir.iterdir()):
        return extract_dir

    url = RIFE_RELEASE_URLS().get(paths.OS_NAME)
    if not url:
        status(_("No download URL for models on this platform."), "ERROR")
        return None

    paths.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_zip = paths.CACHE_DIR / "rife_release.zip"

    if not cache_zip.is_file():
        status(_("Downloading RIFE release (one-time, ~400 MB)..."), "INFO")
        dl = DownloadProgress(_("Downloading RIFE release"))
        try:
            import urllib.request
            urllib.request.urlretrieve(url, cache_zip, reporthook=dl)
        except KeyboardInterrupt:
            dl.close()
            status(_("Download cancelled."), "WARN")
            return None
        except Exception as exc:
            dl.close()
            status(f"{_('Download failed:')} {exc}", "ERROR")
            if cache_zip.exists():
                cache_zip.unlink()
            return None
        finally:
            dl.close()

    status(_("Extracting RIFE release..."), "INFO")
    extract_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(cache_zip) as zf:
            zf.extractall(extract_dir)
    except Exception as exc:
        status(f"{_('Extraction failed:')} {exc}", "ERROR")
        shutil.rmtree(extract_dir, ignore_errors=True)
        return None

    entries = list(extract_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        for item in inner.iterdir():
            shutil.move(str(item), str(extract_dir / item.name))
        inner.rmdir()

    return extract_dir


def install_model(model_name):
    from . import manifest

    model_dir = paths.MODELS_DIR / model_name
    if model_dir.is_dir():
        if manifest.is_installed(model_name):
            return True
        manifest.record_dir(model_name, model_name, model_dir)
        return True

    extract_dir = _ensure_rife_release_cached()
    if not extract_dir:
        return False

    model_src = extract_dir / model_name
    if not model_src.is_dir():
        status(f"{_('Model')} {model_name} {_('not found in release archive.')}", "ERROR")
        return False

    paths.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copytree(model_src, model_dir, dirs_exist_ok=True)
    manifest.record_dir(model_name, model_name, model_dir)
    return True


def ensure_default_model(auto_yes=False):
    from .console import ask_yes_no
    default_model = "rife-v4.6"
    model_dir = paths.MODELS_DIR / default_model
    if model_dir.is_dir():
        return
    if not auto_yes and not ask_yes_no(f"{_('Download default model')} {default_model}?", default=True):
        status(f"{_('Default model')} {default_model} {_('not installed. Interpolation will fail if the model is missing.')}", "WARN")
        return
    status(f"{_('Installing default model')} {default_model}...")
    if not install_model(default_model):
        status(f"{_('Could not install')} {default_model}. {_('Interpolation will fail if the model is missing.')}", "WARN")
