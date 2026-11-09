from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
import subprocess
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from app.core.beamforming import build_beamforming_artifacts
from app.config import Settings
from app.bootstrap import ensure_repo_imports
from app.core.web_cache import build_web_cache
from app.core.radar_signal import build_fmcw_artifacts
from app.core.path_layout import ensure_canonical_path_archive
from app.workers.job_store import JobStore, utc_now

ensure_repo_imports()

from sionna_radar.config import load_runs_config, resolve_run_config
from sionna_radar.processing import (
    SPEED_OF_LIGHT,
    canonical_azimuth_deg,
    elevation_from_zenith,
    path_energy_from_cir,
)


POSE_METRICS_FIELDS = [
    "run_id",
    "campaign",
    "pose_id",
    "boresight_id",
    "seed",
    "samples_per_src",
    "x_m",
    "y_m",
    "z_m",
    "look_x_m",
    "look_y_m",
    "look_z_m",
    "boresight_az_deg",
    "boresight_el_deg",
    "valid_path_count",
    "range_max_m",
    "dominant_range_m",
    "max_interaction_depth",
    "fov_path_fraction",
    "fov_energy_fraction",
    "energy_in_fov",
    "run_dir",
]


def boresight_from_pose(center_m: list[float], look_at_m: list[float]) -> dict[str, float]:
    dx = float(look_at_m[0]) - float(center_m[0])
    dy = float(look_at_m[1]) - float(center_m[1])
    dz = float(look_at_m[2]) - float(center_m[2])
    horizontal = math.hypot(dx, dy)
    return {
        "az_deg": math.degrees(math.atan2(dy, dx)),
        "el_deg": math.degrees(math.atan2(dz, horizontal)),
    }


def tx_rx_from_center(
    center_m: list[float],
    look_at_m: list[float],
    baseline_m: float,
) -> tuple[list[float], list[float]]:
    center = np.asarray(center_m, dtype=float)
    look = np.asarray(look_at_m, dtype=float)
    forward = look - center
    forward_xy = forward[:2]
    norm = float(np.linalg.norm(forward_xy))
    if norm < 1e-9:
        side_xy = np.asarray([0.0, 1.0], dtype=float)
    else:
        side_xy = np.asarray([-forward_xy[1], forward_xy[0]], dtype=float) / norm
    offset = np.asarray([side_xy[0], side_xy[1], 0.0], dtype=float) * (float(baseline_m) / 2.0)
    tx = center - offset
    rx = center + offset
    return tx.astype(float).tolist(), rx.astype(float).tolist()


def uniform_weighted_histogram2d(
    x: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    x_edges: np.ndarray,
    y_edges: np.ndarray,
) -> np.ndarray:
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


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def log_tail(path: Path, max_chars: int = 6000) -> str:
    if not path.exists():
        return ""
    data = path.read_text(encoding="utf-8", errors="replace")
    return data[-max_chars:]


def run_experiment_external(run_cfg: dict[str, Any], settings: Settings, gpu_id: int | None) -> dict[str, Any]:
    python = settings.sionna_python
    if python is None or not python.exists():
        raise RuntimeError(
            "No usable Sionna RT Python is configured. Set RADAR_SIONNA_PYTHON to an environment "
            "that can import sionna.rt."
        )
    campaign_root = Path(run_cfg["archive"]["output_root"])
    run_id = str(run_cfg["run_id"])
    runner_root = campaign_root / "_runner"
    config_path = runner_root / "input" / f"{run_id}.json"
    metrics_path = runner_root / "metrics" / f"{run_id}.json"
    log_path = runner_root / "logs" / f"{run_id}.log"
    write_json(config_path, run_cfg)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    script = settings.repo_root / "experiments" / "sionna_radar" / "scripts" / "run_config_json.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(settings.repo_root / "experiments" / "sionna_radar" / "src")
    env.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    if settings.sionna_python_no_user_site:
        env["PYTHONNOUSERSITE"] = "1"
    if gpu_id is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    try:
        with log_path.open("w", encoding="utf-8") as log:
            completed = subprocess.run(
                [str(python), str(script), str(config_path), str(metrics_path)],
                cwd=str(settings.repo_root),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
                text=True,
                timeout=settings.sionna_runner_timeout_s,
            )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Sionna RT external runner timed out after {exc.timeout} s. "
            f"Log: {log_path}\n{log_tail(log_path)}"
        ) from exc
    if completed.returncode != 0:
        raise RuntimeError(
            f"Sionna RT external runner failed with exit code {completed.returncode}. "
            f"Log: {log_path}\n{log_tail(log_path)}"
        )
    if not metrics_path.exists():
        raise RuntimeError(f"Sionna RT external runner did not write metrics: {metrics_path}")
    with metrics_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def run_experiment_direct(run_cfg: dict[str, Any]) -> dict[str, Any]:
    from sionna_radar.runner import run_experiment

    return run_experiment(run_cfg)


def run_experiment_for_worker(run_cfg: dict[str, Any], settings: Settings, gpu_id: int | None) -> dict[str, Any]:
    if settings.sionna_python is not None:
        return run_experiment_external(run_cfg, settings, gpu_id)
    return run_experiment_direct(run_cfg)


def update_metrics_json(run_dir: Path, radar_metrics: dict[str, Any]) -> None:
    metrics_path = run_dir / "metrics.json"
    with metrics_path.open("r", encoding="utf-8") as f:
        existing = json.load(f)
    existing["radar_observation"] = radar_metrics
    write_json(metrics_path, existing)


def update_processing_metrics(
    run_dir: Path,
    beamforming_summary: dict[str, Any],
    fmcw_summary: dict[str, Any],
) -> None:
    metrics_path = run_dir / "metrics.json"
    with metrics_path.open("r", encoding="utf-8") as f:
        existing = json.load(f)
    existing["beamforming"] = beamforming_summary
    existing["fmcw"] = fmcw_summary
    write_json(metrics_path, existing)


def build_radar_observation(
    run_dir: Path,
    run_id: str,
    fov: dict[str, float],
    rmax_m: float,
    range_bin_m: float,
    angle_bin_deg: float,
    min_valid_tau_s: float,
    path_energy_override: np.ndarray | None = None,
    energy_model: str = "noncoherent_cir",
) -> dict[str, Any]:
    ensure_canonical_path_archive(run_dir)
    paths = np.load(run_dir / "paths_summary.npz", allow_pickle=False)
    cir = np.load(run_dir / "cir.npz", allow_pickle=False)
    tau = paths["tau_s"].reshape(-1)
    valid = paths["valid"].reshape(-1).astype(bool)
    theta_r = paths["theta_r_rad"].reshape(-1)
    phi_r = paths["phi_r_rad"].reshape(-1)
    if path_energy_override is None:
        a = cir["a"]
        energy = path_energy_from_cir(a, tau.size)
    else:
        energy = np.asarray(path_energy_override, dtype=np.float64).reshape(-1)
        if energy.size != tau.size:
            raise ValueError(f"Path-energy override has {energy.size} entries, expected {tau.size}")
    valid = valid & np.isfinite(tau) & (tau > min_valid_tau_s)
    ranges = SPEED_OF_LIGHT * tau[valid] / 2.0
    az = canonical_azimuth_deg(phi_r[valid])
    el = elevation_from_zenith(theta_r[valid])
    weights = energy[valid] if energy.size == tau.size else np.ones_like(ranges)

    az_half = float(fov["az_width_deg"]) / 2.0
    az_delta = (az - float(fov["az_center_deg"]) + 180.0) % 360.0 - 180.0
    fov_mask = (
        (np.abs(az_delta) <= az_half)
        & (el >= float(fov["el_min_deg"]))
        & (el <= float(fov["el_max_deg"]))
        & (ranges <= rmax_m)
    )

    r_edges = np.arange(0.0, rmax_m + range_bin_m, range_bin_m)
    az_edges = np.arange(-180.0, 180.0 + angle_bin_deg, angle_bin_deg)
    el_edges = np.arange(-90.0, 90.0 + angle_bin_deg, angle_bin_deg)
    hist = uniform_weighted_histogram2d(ranges, az, weights, r_edges, az_edges)
    el_hist = uniform_weighted_histogram2d(ranges, el, weights, r_edges, el_edges)

    obs_path = run_dir / "radar_observation.npz"
    np.savez_compressed(
        obs_path,
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
        plt.axvline(float(fov["az_center_deg"]) - az_half, color="cyan", linewidth=1)
        plt.axvline(float(fov["az_center_deg"]) + az_half, color="cyan", linewidth=1)
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
        plt.axvline(float(fov["el_min_deg"]), color="cyan", linewidth=1)
        plt.axvline(float(fov["el_max_deg"]), color="cyan", linewidth=1)
        plt.colorbar(label="Relative power (dB, clipped)")
        plt.xlabel("AoA elevation (deg)")
        plt.ylabel("Equivalent monostatic range (m)")
        plt.title(run_id)
        plt.tight_layout()
        plt.savefig(el_fig, dpi=160)
        plt.close()

    metrics = {
        "radar_observation_file": str(obs_path),
        "radar_observation_figure": str(az_fig),
        "radar_range_azimuth_figure": str(az_fig),
        "radar_range_elevation_figure": str(el_fig),
        "fov": fov,
        "path_count_total": int(valid.sum()),
        "path_count_in_fov": int(fov_mask.sum()),
        "path_fraction_in_fov": float(fov_mask.sum() / max(int(valid.sum()), 1)),
        "energy_total": float(np.sum(weights)),
        "energy_in_fov": float(np.sum(weights[fov_mask])),
        "energy_fraction_in_fov": float(np.sum(weights[fov_mask]) / max(float(np.sum(weights)), 1e-300)),
        "energy_model": energy_model,
        "dominant_range_m": float(ranges[int(np.argmax(weights))]) if ranges.size and weights.size else None,
    }
    update_metrics_json(run_dir, metrics)
    return metrics


def write_pose_metrics(campaign_root: Path, rows: list[dict[str, Any]]) -> None:
    reports = campaign_root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    for name in ("POSE_METRICS.csv", "runs_index.csv"):
        path = reports / name
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=POSE_METRICS_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in POSE_METRICS_FIELDS})
        temp_path.replace(path)


class SimulationWorker:
    def __init__(self, settings: Settings, job_store: JobStore):
        self.settings = settings
        self.job_store = job_store

    def build_run_config(
        self,
        request: dict[str, Any],
        job_id: str,
        task_index: int = 0,
        radar_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cfg_path = self.settings.repo_root / "experiments" / "sionna_radar" / "configs" / "runs.yaml"
        cfg = load_runs_config(cfg_path)
        run_cfg = resolve_run_config(cfg, "R010")
        radar = {**request["radar"], **(radar_override or {})}
        propagation = request["propagation"]
        compute = request.get("compute", {})
        path_solver = request.get("path_solver", {})
        scattering = request.get("scattering", {})
        tx_array = request["tx_array"]
        rx_array = request["rx_array"]
        center_m = [float(v) for v in radar["center_m"]]
        look_at_m = [float(v) for v in radar["look_at_m"]]
        baseline_m = float(radar.get("tx_rx_baseline_m", 0.1))
        tx_position_m, rx_position_m = tx_rx_from_center(center_m, look_at_m, baseline_m)
        bs = boresight_from_pose(center_m, look_at_m)

        campaign_id = job_id
        run_id = f"WEB_{job_id}" if task_index == 0 else f"WEB_{job_id}_{task_index:03d}"
        campaign_root = self.settings.workbench_output_root / "campaigns" / campaign_id
        run_cfg["run_id"] = run_id
        run_cfg["scene"] = request["scene_id"]
        run_cfg["mode"] = "path_run"
        run_cfg["milestone"] = "WEB-FULL"
        run_cfg["purpose"] = "Radar workbench sensing measurement"
        run_cfg["archive"]["output_root"] = str(campaign_root)
        run_cfg["devices"] = {
            "tx_position_m": tx_position_m,
            "rx_position_m": rx_position_m,
            "look_at_m": look_at_m,
        }
        run_cfg["frequency_hz"] = float(propagation["frequency_hz"])
        run_cfg["bandwidth_hz"] = float(propagation["bandwidth_hz"])
        run_cfg["tx_power_dbm"] = float(request.get("tx_power_dbm", request.get("waveform", {}).get("tx_power_dbm", 30.0)))
        run_cfg["tx_array"] = dict(tx_array)
        run_cfg["rx_array"] = dict(rx_array)
        run_cfg["path_solver"].update(dict(path_solver))
        run_cfg["path_solver"]["samples_per_src"] = int(
            compute.get("samples_per_src", path_solver.get("samples_per_src", 500_000))
        )
        run_cfg["path_solver"]["seed"] = int(compute.get("seed", path_solver.get("seed", 501)))
        run_cfg["path_solver"]["max_depth"] = int(path_solver.get("max_depth", 2))
        run_cfg["scattering"] = dict(scattering)
        run_cfg["fov"] = {
            "az_center_deg": bs["az_deg"],
            "boresight_el_deg": bs["el_deg"],
            "az_width_deg": float(radar.get("az_width_deg", 120.0)),
            "el_min_deg": float(radar.get("el_min_deg", 0.0)),
            "el_max_deg": float(radar.get("el_max_deg", 40.0)),
            "rmax_m": float(radar.get("rmax_m", 200.0)),
        }
        ray_sampling = dict(path_solver.get("initial_ray_sampling", {}) or {})
        if ray_sampling.get("mode") == "analysis_sector":
            ray_sampling.update(
                {
                    "azimuth_center_deg": run_cfg["fov"]["az_center_deg"],
                    "azimuth_width_deg": run_cfg["fov"]["az_width_deg"],
                    "elevation_min_deg": run_cfg["fov"]["el_min_deg"],
                    "elevation_max_deg": run_cfg["fov"]["el_max_deg"],
                }
            )
        run_cfg["path_solver"]["initial_ray_sampling"] = ray_sampling or {"mode": "full_sphere"}
        run_cfg["range_processing"] = {
            "rmax_m": float(radar.get("rmax_m", 200.0)),
            "range_bin_m": float(radar.get("range_bin_m", 0.15)),
            "angle_bin_deg": float(radar.get("angle_bin_deg", 2.0)),
            "min_valid_tau_s": float(radar.get("min_valid_tau_s", 1e-10)),
        }
        run_cfg["beamforming"] = dict(request.get("observation", {}).get("beamforming", {}))
        run_cfg["waveform"] = {
            "type": "fmcw",
            "bandwidth_hz": float(propagation["bandwidth_hz"]),
            **dict(request.get("waveform", {}) or {}),
        }
        run_cfg["receiver"] = dict(request.get("receiver", {}) or {})
        run_cfg["radar_processing"] = dict(request.get("radar_processing", {}) or {})
        run_cfg["cir_noise"] = dict(request.get("cir_noise", {}) or {})
        run_cfg["workbench"] = {
            "job_id": job_id,
            "campaign_id": campaign_id,
            "run_id": run_id,
            "task_index": task_index,
            "center_m": center_m,
            "look_at_m": look_at_m,
            "tx_rx_baseline_m": baseline_m,
            "boresight_az_deg": bs["az_deg"],
            "boresight_el_deg": bs["el_deg"],
            "source_experiment_id": request.get("source_experiment_id"),
            "scene_geometry": request.get("scene_geometry"),
        }
        return run_cfg

    def request_poses(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        if request.get("mode") == "campaign" and request.get("poses"):
            return list(request["poses"])
        return [
            {
                "center_m": request["radar"]["center_m"],
                "look_at_m": request["radar"]["look_at_m"],
            }
        ]

    def write_campaign_manifest(
        self,
        campaign_root: Path,
        job_id: str,
        run_ids: list[str],
        request: dict[str, Any],
    ) -> None:
        manifest = {
            "schema_version": "0.1.0",
            "campaign_id": job_id,
            "display_name": request.get("display_name") or f"雷达仿真 · {utc_now()[:16].replace('T', ' ')}",
            "created_at_utc": utc_now(),
            "source": "radar-workbench",
            "scene_id": request["scene_id"],
            "mode": request.get("mode", "single_pose"),
            "radar_only": True,
            "run_ids": run_ids,
            "request": request,
        }
        write_json(campaign_root / "campaign_manifest.json", manifest)
        poses = self.request_poses(request)
        write_json(
            campaign_root / "pose_manifest.json",
            {
                "schema_version": "0.1.0",
                "campaign_id": job_id,
                "poses": [
                    {
                        "run_id": run_id,
                        "center_m": pose.get("center_m", request["radar"]["center_m"]),
                        "look_at_m": pose.get("look_at_m", request["radar"]["look_at_m"]),
                    }
                    for run_id, pose in zip(run_ids, poses)
                ],
            },
        )

    def run_task(
        self,
        job_id: str,
        request: dict[str, Any],
        task_index: int = 0,
        radar_override: dict[str, Any] | None = None,
        gpu_id: int | None = None,
    ) -> dict[str, Any]:
        run_cfg = self.build_run_config(request, job_id, task_index=task_index, radar_override=radar_override)
        campaign_root = Path(run_cfg["archive"]["output_root"])
        run_id = run_cfg["run_id"]
        self.job_store.append_event(
            job_id,
            {"type": "task_start", "gpu_id": gpu_id, "task_index": task_index, "run_id": run_id},
        )
        metrics = run_experiment_for_worker(run_cfg, self.settings, gpu_id)
        run_dir = campaign_root / "runs" / run_id
        fov = run_cfg["fov"]
        range_processing = run_cfg["range_processing"]
        radar_metrics = build_radar_observation(
            run_dir,
            run_id,
            fov,
            rmax_m=float(range_processing["rmax_m"]),
            range_bin_m=float(range_processing["range_bin_m"]),
            angle_bin_deg=float(range_processing["angle_bin_deg"]),
            min_valid_tau_s=float(range_processing["min_valid_tau_s"]),
        )
        beamforming_result = build_beamforming_artifacts(run_dir)
        beamformed = np.load(beamforming_result["files"]["beamformed_observation"], allow_pickle=False)
        radar_metrics = build_radar_observation(
            run_dir,
            run_id,
            fov,
            rmax_m=float(range_processing["rmax_m"]),
            range_bin_m=float(range_processing["range_bin_m"]),
            angle_bin_deg=float(range_processing["angle_bin_deg"]),
            min_valid_tau_s=float(range_processing["min_valid_tau_s"]),
            path_energy_override=beamformed["beamformed_path_power"],
            energy_model="coherent_tx_rx_beamformed_cir",
        )
        fmcw_result = build_fmcw_artifacts(run_dir)
        update_processing_metrics(run_dir, beamforming_result["summary"], fmcw_result["summary"])
        path_summary = metrics.get("path_summary", {})
        center_m = run_cfg["workbench"]["center_m"]
        look_at_m = run_cfg["workbench"]["look_at_m"]
        row = {
            "run_id": run_id,
            "campaign": job_id,
            "pose_id": f"P_web_{task_index:03d}",
            "boresight_id": f"Baz{run_cfg['workbench']['boresight_az_deg']:.1f}",
            "seed": int(run_cfg["path_solver"]["seed"]),
            "samples_per_src": int(run_cfg["path_solver"]["samples_per_src"]),
            "x_m": center_m[0],
            "y_m": center_m[1],
            "z_m": center_m[2],
            "look_x_m": look_at_m[0],
            "look_y_m": look_at_m[1],
            "look_z_m": look_at_m[2],
            "boresight_az_deg": run_cfg["workbench"]["boresight_az_deg"],
            "boresight_el_deg": run_cfg["workbench"]["boresight_el_deg"],
            "valid_path_count": path_summary.get("valid_path_count", 0),
            "range_max_m": path_summary.get("range_max_m", 0.0),
            "dominant_range_m": radar_metrics.get("dominant_range_m") or path_summary.get("dominant_range_m", 0.0),
            "max_interaction_depth": path_summary.get("max_interaction_depth", 0),
            "fov_path_fraction": radar_metrics["path_fraction_in_fov"],
            "fov_energy_fraction": radar_metrics["energy_fraction_in_fov"],
            "energy_in_fov": radar_metrics["energy_in_fov"],
            "run_dir": str(run_dir),
        }
        cache_dir = build_web_cache(run_dir, self.settings.web_cache_root, top_k=500, diffuse_quota=100)
        result = {
            "campaign_id": job_id,
            "run_id": run_id,
            "task_index": task_index,
            "output_root": str(campaign_root),
            "run_dir": str(run_dir),
            "web_cache": str(cache_dir),
        }
        self.job_store.append_event(
            job_id,
            {"type": "task_complete", "gpu_id": gpu_id, "task_index": task_index, "run_id": run_id, "result": result},
        )
        return {"result": result, "metrics": metrics, "row": row}

    def run_single(self, job_id: str, request: dict[str, Any], gpu_id: int | None = None) -> dict[str, Any]:
        result = self.run_task(job_id, request, task_index=0, gpu_id=gpu_id)
        campaign_root = Path(result["result"]["output_root"])
        write_pose_metrics(campaign_root, [result["row"]])
        self.write_campaign_manifest(campaign_root, job_id, [result["result"]["run_id"]], request)
        return result
