#!/usr/bin/env python
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sionna_radar.archive import utc_now


def main() -> int:
    output_root = Path("outputs/sionna_radar")
    runs_dir = output_root / "runs"
    report_dir = output_root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for metrics_path in sorted(runs_dir.glob("*/metrics.json")):
        with metrics_path.open("r", encoding="utf-8") as f:
            metrics = json.load(f)
        ps = metrics.get("path_summary", {})
        rows.append({
            "run_id": metrics.get("run_id"),
            "milestone": metrics.get("milestone"),
            "scene": metrics.get("scene"),
            "purpose": metrics.get("purpose"),
            "status": metrics.get("status"),
            "valid_path_count": ps.get("valid_path_count"),
            "dominant_range_m": ps.get("dominant_range_m"),
            "range_min_m": ps.get("range_min_m"),
            "range_max_m": ps.get("range_max_m"),
            "max_interaction_depth": ps.get("max_interaction_depth"),
            "specular_path_count": ps.get("specular_path_count"),
            "diffuse_path_count": ps.get("diffuse_path_count"),
            "checks": metrics.get("checks", {}),
        })

    report = report_dir / "RUN_SUMMARY.md"
    with report.open("w", encoding="utf-8") as f:
        f.write("# Sionna RT Radar Run Summary\n\n")
        f.write(f"Generated at: {utc_now()}\n\n")
        f.write("| Run | Milestone | Scene | Status | Valid Paths | Dominant Range (m) | Max Depth | Specular | Diffuse | Checks |\n")
        f.write("|---|---|---|---|---:|---:|---:|---:|---:|---|\n")
        for r in rows:
            f.write(
                f"| {r['run_id']} | {r.get('milestone')} | {r.get('scene')} | "
                f"{r.get('status')} | {r.get('valid_path_count')} | "
                f"{r.get('dominant_range_m')} | {r.get('max_interaction_depth')} | "
                f"{r.get('specular_path_count')} | {r.get('diffuse_path_count')} | "
                f"`{json.dumps(r.get('checks', {}), sort_keys=True)}` |\n"
            )

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
