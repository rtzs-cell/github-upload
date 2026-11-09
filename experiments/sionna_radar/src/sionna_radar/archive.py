from __future__ import annotations

import csv
import contextlib
import fcntl
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

import numpy as np
import yaml


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_dir(output_root: str | Path, run_id: str) -> Path:
    return Path(output_root) / "runs" / run_id


def prepare_run_dir(output_root: str | Path, run_id: str) -> Path:
    path = run_dir(output_root, run_id)
    (path / "figures").mkdir(parents=True, exist_ok=True)
    return path


def write_yaml(path: str | Path, data: dict[str, Any]) -> None:
    with Path(path).open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    with Path(path).open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


@contextlib.contextmanager
def file_lock(path: str | Path):
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def capture_environment() -> dict[str, Any]:
    modules = ["sionna", "mitsuba", "drjit", "numpy", "matplotlib", "scipy", "yaml"]
    versions: dict[str, Any] = {}
    for name in modules:
        try:
            module = __import__(name)
            versions[name] = getattr(module, "__version__", "version_attr_missing")
            versions[f"{name}_file"] = getattr(module, "__file__", None)
        except Exception as exc:  # pragma: no cover - metadata path
            versions[name] = f"import_error: {type(exc).__name__}: {exc}"

    for distribution in ("sionna-rt", "sionna"):
        try:
            versions[f"{distribution}_distribution"] = importlib_metadata.version(distribution)
        except importlib_metadata.PackageNotFoundError:
            continue

    gpu_info = None
    try:
        gpu_info = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            text=True,
            timeout=10,
        ).strip()
    except Exception as exc:  # pragma: no cover - metadata path
        gpu_info = f"nvidia-smi unavailable: {type(exc).__name__}: {exc}"

    git_status = None
    try:
        git_status = subprocess.check_output(
            ["git", "status", "--short"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=10,
        ).strip()
    except Exception as exc:  # pragma: no cover - metadata path
        git_status = f"git unavailable: {type(exc).__name__}: {exc}"

    return {
        "captured_at_utc": utc_now(),
        "python": sys.version,
        "platform": platform.platform(),
        "cwd": os.getcwd(),
        "modules": versions,
        "gpu_info": gpu_info,
        "git_status_short": git_status,
    }


def append_runs_index(output_root: str | Path, row: dict[str, Any]) -> None:
    path = Path(output_root) / "reports" / "runs_index.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "run_id",
        "milestone",
        "purpose",
        "scene",
        "status",
        "valid_path_count",
        "range_min_m",
        "range_max_m",
        "dominant_range_m",
        "diffuse_path_count",
        "specular_path_count",
        "max_interaction_depth",
        "completed_at_utc",
    ]
    with file_lock(path.with_suffix(path.suffix + ".lock")):
        exists = path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not exists:
                writer.writeheader()
            writer.writerow({k: row.get(k, "") for k in fieldnames})
