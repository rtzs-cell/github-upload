from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def deep_update(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into a copy of ``base``."""
    merged = deepcopy(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = deep_update(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def load_runs_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_run_config(config: dict[str, Any], run_id: str) -> dict[str, Any]:
    runs = config.get("runs", {})
    if run_id not in runs:
        available = ", ".join(sorted(runs))
        raise KeyError(f"Unknown run_id={run_id}. Available runs: {available}")

    resolved = deep_update(config.get("defaults", {}), runs[run_id])
    resolved["run_id"] = run_id
    resolved["archive"] = deepcopy(config.get("archive", {}))
    return resolved


def list_run_ids(config: dict[str, Any]) -> list[str]:
    return sorted(config.get("runs", {}).keys())

