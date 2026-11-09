#!/usr/bin/env python
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path


def ensure_src_path() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: run_config_json.py <config.json> <metrics.json>", file=sys.stderr)
        return 2
    ensure_src_path()
    from sionna_radar.runner import run_experiment

    config_path = Path(sys.argv[1])
    metrics_path = Path(sys.argv[2])
    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)
    metrics = run_experiment(config)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception:  # pragma: no cover - external runner diagnostic path
        traceback.print_exc()
        exit_code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
