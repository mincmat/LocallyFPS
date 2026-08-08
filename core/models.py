import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from . import paths
from .console import status
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


def install_model(model_name):
    models_dir = paths.MODELS_DIR
    model_dir = models_dir / model_name
    if model_dir.is_dir():
        return True
    status(f"{_('Downloading model')} {model_name}...")
    os_name = paths.OS_NAME
    url = RIFE_RELEASE_URLS.get(os_name)
    if not url:
        status(_("No download URL for models on this platform."), "ERROR")
        return False
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "rife.zip"
        dl = DownloadProgress(_("Downloading"))
        try:
            urllib.request.urlretrieve(url, zip_path, reporthook=dl)
        except Exception as exc:
            status(f"{_('Download failed:')} {exc}", "ERROR")
            return False
        finally:
            dl.close()
        extract_dir = Path(tmpdir) / "extracted"
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
        source_dir = subdirs[0] if subdirs else extract_dir
        model_src = source_dir / model_name
        if not model_src.is_dir():
            status(f"{_('Model')} {model_name} {_('not found in release archive.')}", "ERROR")
            return False
        models_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(model_src, model_dir, dirs_exist_ok=True)
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
