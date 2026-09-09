#!/usr/bin/env python3
"""Create a minimal, verified offline runtime for a release package."""

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from urllib.parse import urlparse
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "packaging" / "runtime_manifest.json"


def _digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def _download(spec, cache, name):
    suffix = Path(urlparse(spec["url"]).path).suffix or ".bin"
    destination = cache / f"{name}-{spec['sha256'][:12]}{suffix}"
    if destination.is_file() and _digest(destination) == spec["sha256"]:
        return destination
    destination.unlink(missing_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    partial.unlink(missing_ok=True)
    request = urllib.request.Request(spec["url"], headers={"User-Agent": "LocallyFPS-Packager"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        actual = _digest(partial)
        if actual != spec["sha256"]:
            raise RuntimeError(f"SHA-256 mismatch for {name}: {actual}")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
    return destination


def _copy_zip_member(archive, suffix, destination):
    with zipfile.ZipFile(archive) as bundle:
        matches = [item for item in bundle.infolist() if item.filename.endswith(suffix) and not item.is_dir()]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one ZIP member ending in {suffix}, found {len(matches)}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with bundle.open(matches[0]) as source, destination.open("wb") as target:
            shutil.copyfileobj(source, target)


def _copy_tar_member(archive, suffix, destination):
    with tarfile.open(archive, "r:xz") as bundle:
        matches = [item for item in bundle.getmembers() if item.isfile() and item.name.endswith(suffix)]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one TAR member ending in {suffix}, found {len(matches)}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = bundle.extractfile(matches[0])
        if source is None:
            raise RuntimeError(f"Could not read {matches[0].name}")
        with source, destination.open("wb") as target:
            shutil.copyfileobj(source, target)


def _prepare_ffmpeg(platform_id, spec, cache, stage):
    target = stage / "deps" / "ffmpeg"
    target.mkdir(parents=True, exist_ok=True)
    extension = ".exe" if platform_id.startswith("windows") else ""
    if spec["kind"] == "files":
        for name in ("ffmpeg", "ffprobe"):
            shutil.copy2(_download(spec[name], cache, name), target / name)
        shutil.copy2(_download(spec["license"], cache, "ffmpeg-license"), target / "LICENSE.txt")
    else:
        archive = _download(spec, cache, "ffmpeg")
        copy_member = _copy_zip_member if spec["kind"] == "zip" else _copy_tar_member
        for name in ("ffmpeg", "ffprobe"):
            copy_member(archive, f"/bin/{name}{extension}", target / f"{name}{extension}")
        copy_member(archive, "/LICENSE.txt", target / "LICENSE.txt")
    for binary in target.glob("ff*"):
        if binary.name != "LICENSE.txt":
            binary.chmod(0o755)


def _prepare_rife(platform_id, spec, cache, stage):
    archive = _download(spec, cache, "rife")
    extension = ".exe" if platform_id.startswith("windows") else ""
    rife_target = stage / "deps" / "rife"
    model_target = stage / "models" / "rife-v4.6"
    _copy_zip_member(archive, f"{spec['root']}/rife-ncnn-vulkan{extension}", rife_target / f"rife-ncnn-vulkan{extension}")
    _copy_zip_member(archive, f"{spec['root']}/LICENSE", rife_target / "LICENSE.txt")
    for name in ("flownet.bin", "flownet.param"):
        _copy_zip_member(archive, f"{spec['root']}/rife-v4.6/{name}", model_target / name)
    if platform_id.startswith("windows"):
        _copy_zip_member(archive, f"{spec['root']}/vcomp140.dll", rife_target / "vcomp140.dll")
    (rife_target / f"rife-ncnn-vulkan{extension}").chmod(0o755)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=("linux-x86_64", "windows-x86_64", "macos-arm64"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "build" / "download-cache")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    output = args.output.resolve()
    cache = args.cache_dir.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="locallyfps-runtime-", dir=output.parent) as temp:
        stage = Path(temp) / "runtime"
        _prepare_ffmpeg(args.platform, manifest["ffmpeg"][args.platform], cache, stage)
        _prepare_rife(args.platform, manifest["rife"][args.platform], cache, stage)
        details = {
            "runtime_revision": manifest["runtime_revision"],
            "platform": args.platform,
            "ffmpeg": manifest["ffmpeg"][args.platform]["version"],
            "rife": manifest["rife"]["version"],
        }
        (stage / "runtime.json").write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
        if output.exists():
            shutil.rmtree(output)
        shutil.move(stage, output)
    print(output)


if __name__ == "__main__":
    main()
