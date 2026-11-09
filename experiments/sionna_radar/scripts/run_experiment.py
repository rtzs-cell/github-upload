#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sionna_radar.config import list_run_ids, load_runs_config, resolve_run_config
from sionna_radar.runner import run_experiment


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Sionna RT radar archive experiment.")
    parser.add_argument("--config", default=str(ROOT / "configs" / "runs.yaml"))
    parser.add_argument("--run-id", action="append", help="Run ID to execute. Can be repeated.")
    parser.add_argument("--list", action="store_true", help="List configured run IDs.")
    args = parser.parse_args()

    cfg = load_runs_config(args.config)
    if args.list:
        for run_id in list_run_ids(cfg):
            print(run_id)
        return 0
    if not args.run_id:
        parser.error("--run-id is required unless --list is used")

    for run_id in args.run_id:
        run_cfg = resolve_run_config(cfg, run_id)
        metrics = run_experiment(run_cfg)
        summary = metrics.get("path_summary", {})
        print(
            f"{run_id}: status={metrics.get('status')} "
            f"valid_paths={summary.get('valid_path_count')} "
            f"dominant_range_m={summary.get('dominant_range_m')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

