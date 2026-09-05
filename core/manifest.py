"""Dependency manifest — tracks installed binaries with SHA-256 hashes."""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from . import paths


def _manifest_path() -> Path:
    return paths.CONFIG_DIR / "manifest.json"


def load() -> dict:
    p = _manifest_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save(data: dict):
    p = _manifest_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def is_installed(name: str) -> bool:
    return name in load()


def get_info(name: str) -> dict | None:
    return load().get(name)


def record(name: str, version: str, file_path: Path):
    sha = sha256_file(file_path)
    data = load()
    data[name] = {
        "version": version,
        "sha256": sha,
        "installed_at": datetime.now().isoformat(),
    }
    save(data)


def record_dir(name: str, version: str, dir_path: Path):
    sha = sha256_dir(dir_path)
    data = load()
    data[name] = {
        "version": version,
        "sha256": sha,
        "installed_at": datetime.now().isoformat(),
    }
    save(data)


def verify(name: str, file_path: Path) -> bool:
    info = get_info(name)
    if not info or not file_path.is_file():
        return False
    return sha256_file(file_path) == info.get("sha256", "")


def verify_dir(name: str, dir_path: Path) -> bool:
    info = get_info(name)
    if not info or not dir_path.is_dir():
        return False
    return sha256_dir(dir_path) == info.get("sha256", "")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_dir(dir_path: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(dir_path.rglob("*")):
        if p.is_file():
            h.update(p.name.encode())
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
    return h.hexdigest()
