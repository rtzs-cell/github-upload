#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import math
import multiprocessing as mp
import os
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any

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
from sionna_radar.config import load_runs_config, resolve_run_config
from sionna_radar.runner import run_experiment
from sionna_radar.processing import canonical_azimuth_deg, elevation_from_zenith, path_energy_from_cir, SPEED_OF_LIGHT


BASE_RUN_ID = "R010"
BASE_CONFIG_PATH = ROOT / "configs" / "runs.yaml"
CAMPAIGN_ROOT = Path("outputs/sionna_radar_campaigns")


def boresight_from_pose(rx_position: list[float], look_at: list[float]) -> dict[str, float]:
    rx = np.asarray(rx_position, dtype=float)
    look = np.asarray(look_at, dtype=float)
    delta = look - rx
    horizontal = float(np.linalg.norm(delta[:2]))
    return {
        "az_deg": float(np.rad2deg(np.arctan2(delta[1], delta[0]))),
        "el_deg": float(np.rad2deg(np.arctan2(delta[2], horizontal))),
    }


def base_sensing_config(run_id: str, output_root: Path, tx_pos: list[float], rx_pos: list[float],
                        look_at: list[float], seed: int, samples: int,
                        purpose: str, milestone: str = "CAMPAIGN") -> dict[str, Any]:
    cfg_all = load_runs_config(BASE_CONFIG_PATH)
    cfg = resolve_run_config(cfg_all, BASE_RUN_ID)
    cfg["run_id"] = run_id
    cfg["archive"]["output_root"] = str(output_root)
    cfg["milestone"] = milestone
    cfg["purpose"] = purpose
    cfg["scene"] = "simple_street_canyon"
    cfg["devices"] = {
        "tx_position_m": tx_pos,
        "rx_position_m": rx_pos,
        "look_at_m": look_at,
    }
    cfg["path_solver"]["seed"] = seed
    cfg["path_solver"]["samples_per_src"] = samples
    cfg["path_solver"]["los"] = False
    cfg["path_solver"]["max_depth"] = 2
    cfg["path_solver"]["specular_reflection"] = True
    cfg["path_solver"]["diffuse_reflection"] = True
    cfg["scattering"] = {
        "enabled": True,
        "coefficient": 0.5,
        "pattern": "backscattering",
        "alpha_r": 20,
        "alpha_i": 20,
        "lambda_": 0.3,
    }
    return cfg


def uniform_weighted_histogram2d(x: np.ndarray, y: np.ndarray, weights: np.ndarray,
                                 x_edges: np.ndarray, y_edges: np.ndarray) -> np.ndarray:
    """Fast vectorized histogram for uniformly spaced bins."""
    nx = len(x_edges) - 1
    ny = len(y_edges) - 1
    if nx <= 0 or ny <= 0:
        return np.zeros((max(nx, 0), max(ny, 0)), dtype=float)
    dx = float(x_edges[1] - x_edges[0])
    dy = float(y_edges[1] - y_edges[0])
    x0 = float(x_edges[0])
    y0 = float(y_edges[0])
    x1 = float(x_edges[-1])
    y1 = float(y_edges[-1])
    mask = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1) & np.isfinite(x) & np.isfinite(y)
    if not np.any(mask):
        return np.zeros((nx, ny), dtype=float)
    xi = np.floor((x[mask] - x0) / dx).astype(np.int64)
    yi = np.floor((y[mask] - y0) / dy).astype(np.int64)
    xi = np.clip(xi, 0, nx - 1)
    yi = np.clip(yi, 0, ny - 1)
    flat = xi * ny + yi
    hist = np.bincount(flat, weights=weights[mask], minlength=nx * ny)
    return hist.reshape(nx, ny)


def radar_observation_from_run(run_dir: Path, run_id: str, fov: dict[str, float],
                               rmax_m: float = 200.0, range_bin_m: float = 0.15,
                               angle_bin_deg: float = 2.0) -> dict[str, Any]:
    paths = np.load(run_dir / "paths_summary.npz")
    cir = np.load(run_dir / "cir.npz")
    tau = paths["tau_s"].reshape(-1)
    valid = paths["valid"].reshape(-1).astype(bool)
    theta_r = paths["theta_r_rad"].reshape(-1)
    phi_r = paths["phi_r_rad"].reshape(-1)
    a = cir["a"]
    energy = path_energy_from_cir(a, tau.size)
    valid = valid & np.isfinite(tau) & (tau > 1e-10)
    ranges = SPEED_OF_LIGHT * tau[valid] / 2.0
    az = canonical_azimuth_deg(phi_r[valid])
    el = elevation_from_zenith(theta_r[valid])
    weights = energy[valid] if energy.size == tau.size else np.ones_like(ranges)

    az_half = fov["az_width_deg"] / 2.0
    az_delta = (az - fov["az_center_deg"] + 180.0) % 360.0 - 180.0
    fov_mask = (
        (np.abs(az_delta) <= az_half)
        & (el >= fov["el_min_deg"])
        & (el <= fov["el_max_deg"])
        & (ranges <= rmax_m)
    )

    r_edges = np.arange(0.0, rmax_m + range_bin_m, range_bin_m)
    az_edges = np.arange(-180.0, 180.0 + angle_bin_deg, angle_bin_deg)
    el_edges = np.arange(-90.0, 90.0 + angle_bin_deg, angle_bin_deg)
    hist = uniform_weighted_histogram2d(ranges, az, weights, r_edges, az_edges)
    el_hist = uniform_weighted_histogram2d(ranges, el, weights, r_edges, el_edges)
    out = run_dir / "radar_observation.npz"
    np.savez_compressed(
        out,
        range_azimuth_power=hist,
        range_elevation_power=el_hist,
        range_edges_m=r_edges,
        azimuth_edges_deg=az_edges,
        elevation_edges_deg=el_edges,
        fov_path_mask=fov_mask,
        ranges_m=ranges,
        aoa_azimuth_deg=az,
        aoa_elevation_deg=el,
        path_energy=weights,
    )

    fig_dir = run_dir / "figures"
    fig_dir.mkdir(exist_ok=True)
    az_fig = fig_dir / "campaign_range_azimuth.png"
    if np.any(hist > 0):
        db = 10.0 * np.log10(hist + 1e-30)
        db = np.maximum(db, np.max(db) - 60.0)
        plt.figure(figsize=(8.5, 4.8))
        plt.imshow(db, aspect="auto", extent=[az_edges[0], az_edges[-1], r_edges[-1], r_edges[0]], cmap="magma")
        plt.axvline(fov["az_center_deg"] - az_half, color="cyan", linewidth=1)
        plt.axvline(fov["az_center_deg"] + az_half, color="cyan", linewidth=1)
        plt.colorbar(label="Relative power (dB, clipped)")
        plt.xlabel("AoA azimuth (deg)")
        plt.ylabel("Equivalent monostatic range (m)")
        plt.title(run_id)
        plt.tight_layout()
        plt.savefig(az_fig, dpi=160)
        plt.close()

    el_fig = fig_dir / "campaign_range_elevation.png"
    if np.any(el_hist > 0):
        db = 10.0 * np.log10(el_hist + 1e-30)
        db = np.maximum(db, np.max(db) - 60.0)
        plt.figure(figsize=(8.5, 4.8))
        plt.imshow(db, aspect="auto", extent=[el_edges[0], el_edges[-1], r_edges[-1], r_edges[0]], cmap="magma")
        plt.axvline(fov["el_min_deg"], color="cyan", linewidth=1)
        plt.axvline(fov["el_max_deg"], color="cyan", linewidth=1)
        plt.colorbar(label="Relative power (dB, clipped)")
        plt.xlabel("AoA elevation (deg)")
        plt.ylabel("Equivalent monostatic range (m)")
        plt.title(run_id)
        plt.tight_layout()
        plt.savefig(el_fig, dpi=160)
        plt.close()

    metrics = {
        "radar_observation_file": str(out),
        "radar_observation_figure": str(az_fig),
        "radar_range_azimuth_figure": str(az_fig),
        "radar_range_elevation_figure": str(el_fig),
        "fov": fov,
        "path_count_total": int(valid.sum()),
        "path_count_in_fov": int(fov_mask.sum()),
        "path_fraction_in_fov": float(fov_mask.sum() / max(valid.sum(), 1)),
        "energy_total": float(np.sum(weights)),
        "energy_in_fov": float(np.sum(weights[fov_mask])),
        "energy_fraction_in_fov": float(np.sum(weights[fov_mask]) / max(float(np.sum(weights)), 1e-300)),
    }
    existing = json.load((run_dir / "metrics.json").open("r", encoding="utf-8"))
    existing["radar_observation"] = metrics
    write_json(run_dir / "metrics.json", existing)
    return metrics


def write_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fields = sorted({k for r in rows for k in r.keys()})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sensing_measurement(output_root: Path, campaign: str, pose_id: str, boresight_id: str,
                        center_pos: list[float], look_at: list[float],
                        seed: int, samples: int) -> dict[str, Any]:
    tx_pos = [center_pos[0], center_pos[1] - 0.05, center_pos[2]]
    rx_pos = [center_pos[0], center_pos[1] + 0.05, center_pos[2]]
    run_id = f"MM_{campaign}_{pose_id}_{boresight_id}_S{seed}_N{samples//1000}k"
    cfg = base_sensing_config(
        run_id=run_id,
        output_root=output_root,
        tx_pos=tx_pos,
        rx_pos=rx_pos,
        look_at=look_at,
        seed=seed,
        samples=samples,
        purpose=f"{campaign} sensing measurement {pose_id} {boresight_id}",
        milestone=campaign,
    )
    metrics = run_experiment(cfg)
    run_dir = output_root / "runs" / run_id
    bs = boresight_from_pose(rx_pos, look_at)
    fov = {
        "az_center_deg": bs["az_deg"],
        "boresight_el_deg": bs["el_deg"],
        "az_width_deg": 120.0,
        "el_min_deg": 0.0,
        "el_max_deg": 40.0,
        "rmax_m": 200.0,
    }
    radar_metrics = radar_observation_from_run(run_dir, run_id, fov)
    ps = metrics.get("path_summary", {})
    row = {
        "run_id": run_id,
        "campaign": campaign,
        "pose_id": pose_id,
        "boresight_id": boresight_id,
        "seed": seed,
        "samples_per_src": samples,
        "x_m": center_pos[0],
        "y_m": center_pos[1],
        "z_m": center_pos[2],
        "look_x_m": look_at[0],
        "look_y_m": look_at[1],
        "look_z_m": look_at[2],
        "boresight_az_deg": bs["az_deg"],
        "boresight_el_deg": bs["el_deg"],
        "valid_path_count": ps.get("valid_path_count"),
        "range_max_m": ps.get("range_max_m"),
        "dominant_range_m": ps.get("dominant_range_m"),
        "max_interaction_depth": ps.get("max_interaction_depth"),
        "fov_path_fraction": radar_metrics["path_fraction_in_fov"],
        "fov_energy_fraction": radar_metrics["energy_fraction_in_fov"],
        "energy_in_fov": radar_metrics["energy_in_fov"],
        "run_dir": str(run_dir),
    }
    return row


def c001_tasks(out: Path) -> list[dict[str, Any]]:
    center = [0.0, -1.0, 10.0]
    look = [0.0, 25.0, 10.0]
    return [
        {
            "output_root": str(out),
            "campaign": "C001",
            "pose_id": "P00",
            "boresight_id": "BposY",
            "center_pos": center,
            "look_at": look,
            "seed": seed,
            "samples": 500_000,
        }
        for seed in [101, 102, 103]
    ]


def c002_lite_tasks(out: Path) -> list[dict[str, Any]]:
    tasks = []
    for i, x in enumerate([-60.0, -30.0, 0.0, 30.0, 60.0], start=1):
        tasks.append({
            "output_root": str(out),
            "campaign": "C002lite",
            "pose_id": f"P{i:02d}",
            "boresight_id": "BposY",
            "center_pos": [x, 0.0, 10.0],
            "look_at": [x, 30.0, 10.0],
            "seed": 201,
            "samples": 500_000,
        })
    return tasks


def c002_full_tasks(out: Path, samples: int = 500_000, seed: int = 501,
                    campaign: str = "C002full") -> list[dict[str, Any]]:
    tasks = []
    for x in [-60.0, -30.0, 0.0, 30.0, 60.0]:
        for y in [-5.0, 0.0, 5.0]:
            pose_id = f"P{x:+.0f}_{y:+.0f}".replace("+", "p").replace("-", "m")
            center = [x, y, 10.0]
            boresights = [
                ("BposX", [x + 30.0, y, 10.0]),
                ("BposY", [x, y + 30.0, 10.0]),
            ]
            for boresight_id, look in boresights:
                tasks.append({
                    "output_root": str(out),
                    "campaign": campaign,
                    "pose_id": pose_id,
                    "boresight_id": boresight_id,
                    "center_pos": center,
                    "look_at": look,
                    "seed": seed,
                    "samples": samples,
                })
    return tasks


def task_run_id(task: dict[str, Any]) -> str:
    return (
        f"MM_{task['campaign']}_{task['pose_id']}_{task['boresight_id']}_"
        f"S{task['seed']}_N{int(task['samples'])//1000}k"
    )


def run_measurement_task(task: dict[str, Any]) -> dict[str, Any]:
    return sensing_measurement(
        Path(task["output_root"]),
        str(task["campaign"]),
        str(task["pose_id"]),
        str(task["boresight_id"]),
        [float(x) for x in task["center_pos"]],
        [float(x) for x in task["look_at"]],
        int(task["seed"]),
        int(task["samples"]),
    )


def worker_main(gpu_id: int, tasks: list[dict[str, Any]], queue: mp.Queue) -> None:
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    for task in tasks:
        run_id = task_run_id(task)
        started = time.monotonic()
        try:
            row = run_measurement_task(task)
            queue.put({
                "status": "ok",
                "gpu_id": gpu_id,
                "run_id": run_id,
                "elapsed_s": time.monotonic() - started,
                "row": row,
            })
        except Exception as exc:
            queue.put({
                "status": "error",
                "gpu_id": gpu_id,
                "run_id": run_id,
                "elapsed_s": time.monotonic() - started,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            })
            return


def run_tasks_parallel(tasks: list[dict[str, Any]], gpu_ids: list[int]) -> list[dict[str, Any]]:
    if not tasks:
        return []
    chunks = [[] for _ in gpu_ids]
    for i, task in enumerate(tasks):
        chunks[i % len(gpu_ids)].append(task)

    ctx = mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue()
    procs: list[mp.Process] = []
    for gpu_id, chunk in zip(gpu_ids, chunks):
        if not chunk:
            continue
        proc = ctx.Process(target=worker_main, args=(gpu_id, chunk, queue), daemon=False)
        proc.start()
        procs.append(proc)

    rows: list[dict[str, Any]] = []
    completed = 0
    expected = len(tasks)
    errors = []
    while completed < expected and not errors:
        msg = queue.get()
        completed += 1
        elapsed = float(msg.get("elapsed_s", 0.0))
        print(f"[{completed}/{expected}] gpu={msg.get('gpu_id')} {msg.get('run_id')} {msg.get('status')} elapsed={elapsed:.1f}s", flush=True)
        if msg.get("status") == "ok":
            rows.append(msg["row"])
        else:
            errors.append(msg)

    for proc in procs:
        proc.join(timeout=5)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)

    if errors:
        err = errors[0]
        raise RuntimeError(f"Parallel worker failed for {err.get('run_id')} on GPU {err.get('gpu_id')}: {err.get('error')}\n{err.get('traceback')}")

    order = {task_run_id(task): i for i, task in enumerate(tasks)}
    return sorted(rows, key=lambda r: order.get(str(r["run_id"]), 10**9))


def campaign_dir(name: str) -> Path:
    path = CAMPAIGN_ROOT / name
    (path / "reports").mkdir(parents=True, exist_ok=True)
    return path


def maybe_run_tasks(tasks: list[dict[str, Any]], gpu_ids: list[int] | None) -> list[dict[str, Any]]:
    if gpu_ids:
        return run_tasks_parallel(tasks, gpu_ids)
    return [run_measurement_task(task) for task in tasks]


def run_c001(gpu_ids: list[int] | None = None) -> None:
    out = campaign_dir("C001_repeatability")
    rows = maybe_run_tasks(c001_tasks(out), gpu_ids)
    write_rows_csv(out / "reports" / "POSE_METRICS.csv", rows)
    summarize_repeatability(out, rows)


def run_c002_lite(gpu_ids: list[int] | None = None) -> None:
    out = campaign_dir("C002_spatial_survey")
    rows = maybe_run_tasks(c002_lite_tasks(out), gpu_ids)
    write_rows_csv(out / "reports" / "POSE_METRICS.csv", rows)
    summarize_spatial(out, rows)


def run_c002_full(gpu_ids: list[int] | None = None) -> None:
    out = campaign_dir("C002_full_radar_sensing")
    rows = maybe_run_tasks(c002_full_tasks(out), gpu_ids)
    write_rows_csv(out / "reports" / "POSE_METRICS.csv", rows)
    summarize_spatial_full(out, rows)


def summarize_repeatability(out: Path, rows: list[dict[str, Any]]) -> None:
    vals = np.asarray([r["fov_energy_fraction"] for r in rows], dtype=float)
    paths = np.asarray([r["valid_path_count"] for r in rows], dtype=float)
    report = out / "reports" / "CAMPAIGN_SUMMARY.md"
    with report.open("w", encoding="utf-8") as f:
        f.write("# C001 Repeatability Summary\n\n")
        f.write(f"Generated at: {utc_now()}\n\n")
        f.write(f"- Runs: {len(rows)}\n")
        f.write(f"- FoV energy fraction mean/std/CV: {vals.mean():.6f} / {vals.std(ddof=0):.6f} / {vals.std(ddof=0)/max(vals.mean(),1e-300):.3f}\n")
        f.write(f"- Valid path count mean/std/CV: {paths.mean():.1f} / {paths.std(ddof=0):.1f} / {paths.std(ddof=0)/max(paths.mean(),1e-300):.3f}\n\n")
        f.write("| Run | Paths | Dominant Range | FoV Energy Fraction |\n")
        f.write("|---|---:|---:|---:|\n")
        for r in rows:
            f.write(f"| {r['run_id']} | {r['valid_path_count']} | {r['dominant_range_m']} | {r['fov_energy_fraction']:.6f} |\n")


def summarize_spatial(out: Path, rows: list[dict[str, Any]]) -> None:
    report = out / "reports" / "CAMPAIGN_SUMMARY.md"
    xs = [r["x_m"] for r in rows]
    energies = [r["energy_in_fov"] for r in rows]
    plt.figure(figsize=(7, 4))
    plt.plot(xs, energies, marker="o")
    plt.xlabel("BS x position (m)")
    plt.ylabel("FoV radar energy (relative)")
    plt.title("C002-lite spatial sensing energy")
    plt.tight_layout()
    fig = out / "reports" / "spatial_fov_energy.png"
    plt.savefig(fig, dpi=160)
    plt.close()
    with report.open("w", encoding="utf-8") as f:
        f.write("# C002-Lite Spatial Survey Summary\n\n")
        f.write(f"Generated at: {utc_now()}\n\n")
        f.write(f"Figure: `{fig}`\n\n")
        f.write("| Pose | x | Paths | Dominant Range | FoV Energy Fraction | FoV Energy |\n")
        f.write("|---|---:|---:|---:|---:|---:|\n")
        for r in rows:
            f.write(f"| {r['pose_id']} | {r['x_m']} | {r['valid_path_count']} | {r['dominant_range_m']} | {r['fov_energy_fraction']:.6f} | {r['energy_in_fov']:.3e} |\n")


def summarize_spatial_full(out: Path, rows: list[dict[str, Any]]) -> None:
    report = out / "reports" / "CAMPAIGN_SUMMARY.md"
    for boresight in ["BposX", "BposY"]:
        sub = [r for r in rows if r["boresight_id"] == boresight]
        xs = sorted(set(float(r["x_m"]) for r in sub))
        ys = sorted(set(float(r["y_m"]) for r in sub))
        grid = np.full((len(ys), len(xs)), np.nan)
        for r in sub:
            ix = xs.index(float(r["x_m"]))
            iy = ys.index(float(r["y_m"]))
            grid[iy, ix] = float(r["energy_in_fov"])
        plt.figure(figsize=(7, 4.5))
        plt.imshow(grid, origin="lower", aspect="auto", extent=[min(xs), max(xs), min(ys), max(ys)], cmap="viridis")
        plt.colorbar(label="FoV radar energy (relative)")
        plt.xlabel("x position (m)")
        plt.ylabel("y position (m)")
        plt.title(f"C002-full {boresight} FoV energy")
        plt.tight_layout()
        plt.savefig(out / "reports" / f"fov_energy_heatmap_{boresight}.png", dpi=160)
        plt.close()

    with report.open("w", encoding="utf-8") as f:
        f.write("# C002-Full Radar Sensing Survey Summary\n\n")
        f.write(f"Generated at: {utc_now()}\n\n")
        f.write("This campaign contains only monostatic/small-baseline radar sensing measurements. No UE or communication pass is used.\n\n")
        f.write("- Poses: 15\n")
        f.write("- Boresights per pose: 2 (+x, +y)\n")
        f.write("- Total radar self-Tx/Rx measurements: 30\n")
        f.write("- Samples per source: 500000\n\n")
        f.write("Figures:\n")
        f.write("- `fov_energy_heatmap_BposX.png`\n")
        f.write("- `fov_energy_heatmap_BposY.png`\n\n")
        f.write("| Pose | Boresight | x | y | Paths | Dominant Range | FoV Energy Fraction | FoV Energy | Max Depth |\n")
        f.write("|---|---|---:|---:|---:|---:|---:|---:|---:|\n")
        for r in rows:
            f.write(
                f"| {r['pose_id']} | {r['boresight_id']} | {r['x_m']} | {r['y_m']} | "
                f"{r['valid_path_count']} | {r['dominant_range_m']} | {r['fov_energy_fraction']:.6f} | "
                f"{r['energy_in_fov']:.3e} | {r['max_interaction_depth']} |\n"
            )


def main() -> int:
    global CAMPAIGN_ROOT

    parser = argparse.ArgumentParser(description="Run radar-only multi-measurement Sionna sensing campaigns.")
    parser.add_argument("--campaign", choices=["C001", "C002-lite", "C002-full", "all"], required=True)
    parser.add_argument("--clean", action="store_true", help="Remove the selected campaign output before running.")
    parser.add_argument("--campaign-root", default=str(CAMPAIGN_ROOT), help="Output root for campaign folders.")
    parser.add_argument(
        "--parallel-gpus",
        default="",
        help="Comma-separated physical GPU IDs for run-level parallelism, e.g. 0,1,2,3. Empty keeps serial execution.",
    )
    args = parser.parse_args()

    CAMPAIGN_ROOT = Path(args.campaign_root)
    gpu_ids = [int(x.strip()) for x in args.parallel_gpus.split(",") if x.strip()]
    if gpu_ids:
        print(f"Parallel GPU execution enabled on physical GPUs: {gpu_ids}", flush=True)

    selected = ["C001", "C002-lite", "C002-full"] if args.campaign == "all" else [args.campaign]
    if args.clean:
        mapping = {
            "C001": "C001_repeatability",
            "C002-lite": "C002_spatial_survey",
            "C002-full": "C002_full_radar_sensing",
        }
        for c in selected:
            path = CAMPAIGN_ROOT / mapping[c]
            if path.exists():
                shutil.rmtree(path)

    for c in selected:
        print(f"Running {c}...")
        if c == "C001":
            run_c001(gpu_ids)
        elif c == "C002-lite":
            run_c002_lite(gpu_ids)
        elif c == "C002-full":
            run_c002_full(gpu_ids)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
