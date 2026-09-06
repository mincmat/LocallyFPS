"""Persistent pipeline checkpoints for safe crash recovery."""

import hashlib
import json
import os
import shutil
from pathlib import Path

from . import paths


PIPELINE_SCHEMA = 1


class PipelineJob:
    def __init__(self, source, target_fps, model):
        source = Path(source).resolve()
        stat = source.stat()
        identity = {
            "schema": PIPELINE_SCHEMA,
            "source": str(source),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "target_fps": round(float(target_fps), 9),
            "model": model,
        }
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode("utf-8")
        ).hexdigest()[:20]
        self.identity = identity
        self.root = paths.CACHE_DIR / "jobs" / digest
        self.in_frames_dir = self.root / "in_frames"
        self.out_frames_dir = self.root / "out_frames"
        self.state_path = self.root / "state.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self.in_frames_dir.mkdir(exist_ok=True)
        self.out_frames_dir.mkdir(exist_ok=True)

    def load(self):
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            if value.get("identity") == self.identity:
                return value
        except (OSError, json.JSONDecodeError, TypeError):
            pass
        return {"identity": self.identity}

    def update(self, **values):
        state = self.load()
        state.update(values)
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        with open(temporary, "rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, self.state_path)

    @staticmethod
    def reset_frames(directory):
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True, exist_ok=True)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)

