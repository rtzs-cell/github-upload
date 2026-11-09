#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sionna_radar.archive import utc_now, write_json, write_yaml
from sionna_radar.processing import (
    SPEED_OF_LIGHT,
    canonical_azimuth_deg,
    elevation_from_zenith,
    path_energy_from_cir,
    range_angle_histogram,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate radar observation products from a completed path run.")
    parser.add_argument("--source-run", default="R011")
    parser.add_argument("--run-id", default="R024")
    parser.add_argument("--output-root", default="outputs/sionna_radar")
    parser.add_argument("--az-center-deg", type=float, default=0.0)
    parser.add_argument("--auto-boresight", action="store_true", help="Compute azimuth center from source run look_at and receiver position.")
    parser.add_argument("--az-width-deg", type=float, default=120.0)
    parser.add_argument("--el-min-deg", type=float, default=0.0)
    parser.add_argument("--el-max-deg", type=float, default=40.0)
    parser.add_argument("--rmax-m", type=float, default=200.0)
    parser.add_argument("--range-bin-m", type=float, default=0.15)
    parser.add_argument("--angle-bin-deg", type=float, default=2.0)
    args = parser.parse_args()

    output_root = Path(args.output_root)
    source_dir = output_root / "runs" / args.source_run
    run_dir = output_root / "runs" / args.run_id
    fig_dir = run_dir / "figures"
    run_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    paths_npz = np.load(source_dir / "paths_summary.npz")
    cir_npz = np.load(source_dir / "cir.npz")
    source_metrics = json.load((source_dir / "metrics.json").open("r", encoding="utf-8"))
    source_config = yaml.safe_load((source_dir / "config.yaml").open("r", encoding="utf-8"))

    az_center_deg = args.az_center_deg
    boresight_el_deg = None
    if args.auto_boresight:
        devices = source_config.get("devices", {})
        rx_pos = np.asarray(devices.get("rx_position_m", devices.get("tx_position_m")), dtype=float)
        look_at = np.asarray(devices.get("look_at_m"), dtype=float)
        delta = look_at - rx_pos
        az_center_deg = float(np.rad2deg(np.arctan2(delta[1], delta[0])))
        horizontal = float(np.linalg.norm(delta[:2]))
        boresight_el_deg = float(np.rad2deg(np.arctan2(delta[2], horizontal)))

    tau = paths_npz["tau_s"].reshape(-1)
    valid = paths_npz["valid"].reshape(-1).astype(bool)
    theta_r = paths_npz["theta_r_rad"].reshape(-1)
    phi_r = paths_npz["phi_r_rad"].reshape(-1)
    a = cir_npz["a"]
    energy = path_energy_from_cir(a, tau.size)

    valid = valid & np.isfinite(tau) & (tau > 1e-10)
    ranges = SPEED_OF_LIGHT * tau[valid] / 2.0
    az = canonical_azimuth_deg(phi_r[valid])
    el = elevation_from_zenith(theta_r[valid])
    weights = energy[valid] if energy.size == tau.size else np.ones_like(ranges)

    az_half = args.az_width_deg / 2.0
    az_delta = (az - az_center_deg + 180.0) % 360.0 - 180.0
    fov_mask = (
        (np.abs(az_delta) <= az_half)
        & (el >= args.el_min_deg)
        & (el <= args.el_max_deg)
        & (ranges <= args.rmax_m)
    )

    # Build a lightweight PathArrays-like proxy for the existing helper.
    class Proxy:
        pass

    proxy = Proxy()
    proxy.tau_s = paths_npz["tau_s"]
    proxy.valid = paths_npz["valid"]
    proxy.theta_r_rad = paths_npz["theta_r_rad"]
    proxy.phi_r_rad = paths_npz["phi_r_rad"]
    proxy.a_cir = a

    hist, r_edges, az_edges = range_angle_histogram(
        proxy,
        rmax_m=args.rmax_m,
        range_bin_m=args.range_bin_m,
        angle_bin_deg=args.angle_bin_deg,
        min_valid_tau_s=1e-10,
    )

    np.savez_compressed(
        run_dir / "radar_observation.npz",
        range_azimuth_power=hist,
        range_edges_m=r_edges,
        azimuth_edges_deg=az_edges,
        fov_path_mask=fov_mask,
        ranges_m=ranges,
        aoa_azimuth_deg=az,
        aoa_elevation_deg=el,
        path_energy=weights,
    )

    db = 10.0 * np.log10(hist + 1e-30)
    floor = np.max(db) - 60.0 if np.any(hist > 0) else -300.0
    db = np.maximum(db, floor)
    plt.figure(figsize=(9, 5))
    plt.imshow(db, aspect="auto", extent=[az_edges[0], az_edges[-1], r_edges[-1], r_edges[0]], cmap="magma")
    plt.axvline(az_center_deg - az_half, color="cyan", linewidth=1)
    plt.axvline(az_center_deg + az_half, color="cyan", linewidth=1)
    plt.colorbar(label="Relative power (dB, clipped)")
    plt.xlabel("AoA azimuth (deg)")
    plt.ylabel("Equivalent monostatic range (m)")
    plt.title(f"{args.run_id}: radar range-azimuth observation from {args.source_run}")
    plt.tight_layout()
    plt.savefig(fig_dir / "radar_range_azimuth_observation.png", dpi=180)
    plt.close()

    metrics = {
        "run_id": args.run_id,
        "source_run": args.source_run,
        "status": "complete",
        "completed_at_utc": utc_now(),
        "purpose": "CIR/path-to-radar-observation post-processing",
        "range_bin_m": args.range_bin_m,
        "angle_bin_deg": args.angle_bin_deg,
        "fov": {
            "az_center_deg": az_center_deg,
            "boresight_el_deg": boresight_el_deg,
            "auto_boresight": bool(args.auto_boresight),
            "az_width_deg": args.az_width_deg,
            "el_min_deg": args.el_min_deg,
            "el_max_deg": args.el_max_deg,
            "rmax_m": args.rmax_m,
        },
        "path_count_total": int(valid.sum()),
        "path_count_in_fov": int(fov_mask.sum()),
        "path_fraction_in_fov": float(fov_mask.sum() / max(valid.sum(), 1)),
        "energy_total": float(np.sum(weights)),
        "energy_in_fov": float(np.sum(weights[fov_mask])),
        "energy_fraction_in_fov": float(np.sum(weights[fov_mask]) / max(float(np.sum(weights)), 1e-300)),
        "dominant_range_m": source_metrics.get("path_summary", {}).get("dominant_range_m"),
        "source_scene": source_metrics.get("scene"),
        "figure": str(fig_dir / "radar_range_azimuth_observation.png"),
    }
    config = {
        "run_id": args.run_id,
        "source_run": args.source_run,
        "source_config": source_config,
        "postprocess_args": vars(args),
    }
    write_yaml(run_dir / "config.yaml", config)
    write_json(run_dir / "metrics.json", metrics)
    write_json(run_dir / "metadata.json", {
        "run_id": args.run_id,
        "source_run": args.source_run,
        "created_at_utc": utc_now(),
        "input_files": [str(source_dir / "paths_summary.npz"), str(source_dir / "cir.npz")],
    })
    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
