#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import yaml
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle, Wedge


MATERIAL_COLORS = {
    "brick": "#b65f46",
    "concrete": "#9fa6ad",
    "glass": "#4ba3c7",
    "marble": "#d7d2c8",
    "wood": "#a6784d",
}

KIND_COLORS = {
    "specular": "#2677bb",
    "diffuse": "#d97706",
    "mixed": "#7c3aed",
}


def load_rows(campaign_root: Path) -> list[dict[str, str]]:
    path = campaign_root / "reports" / "POSE_METRICS.csv"
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def scene_objects(run_dir: Path) -> dict[str, Any]:
    metadata = load_json(run_dir / "metadata.json")
    return metadata["scene_geometry"]["objects"]


def scene_limits(objects: dict[str, Any], margin: float = 8.0) -> tuple[float, float, float, float]:
    if "floor" in objects:
        mn = objects["floor"]["bbox_min"]
        mx = objects["floor"]["bbox_max"]
        return float(mn[0]), float(mx[0]), float(mn[1]), float(mx[1])
    xs = []
    ys = []
    for obj in objects.values():
        mn = obj["bbox_min"]
        mx = obj["bbox_max"]
        xs.extend([float(mn[0]), float(mx[0])])
        ys.extend([float(mn[1]), float(mx[1])])
    return min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin


def draw_scene(ax: plt.Axes, objects: dict[str, Any], annotate: bool = True) -> None:
    for name, obj in objects.items():
        mn = obj["bbox_min"]
        mx = obj["bbox_max"]
        x0, y0 = float(mn[0]), float(mn[1])
        w, h = float(mx[0]) - x0, float(mx[1]) - y0
        material = obj.get("material") or "unknown"
        if name == "floor":
            ax.add_patch(Rectangle((x0, y0), w, h, facecolor="#f2f3f5", edgecolor="#d1d5db", lw=0.8, zorder=0))
            continue
        color = MATERIAL_COLORS.get(material, "#b6b6b6")
        ax.add_patch(Rectangle((x0, y0), w, h, facecolor=color, edgecolor="#111827", lw=1.0, alpha=0.58, zorder=2))
        if annotate:
            cx = x0 + 0.5 * w
            cy = y0 + 0.5 * h
            ax.text(cx, cy, f"{name}\n{material}", ha="center", va="center", fontsize=7, color="#111827", zorder=3)


def add_fov(ax: plt.Axes, center: tuple[float, float], az_deg: float, width_deg: float,
            radius: float, color: str = "#2dd4bf", alpha: float = 0.14, lw: float = 1.0) -> None:
    wedge = Wedge(center, radius, az_deg - width_deg / 2.0, az_deg + width_deg / 2.0,
                  facecolor=color, edgecolor=color, alpha=alpha, lw=lw, zorder=1)
    ax.add_patch(wedge)


def add_boresight(ax: plt.Axes, center: tuple[float, float], az_deg: float,
                  length: float = 15.0, color: str = "#111827", lw: float = 1.6) -> None:
    az = math.radians(az_deg)
    dx = length * math.cos(az)
    dy = length * math.sin(az)
    ax.arrow(center[0], center[1], dx, dy, width=0.18, head_width=2.0, head_length=3.0,
             length_includes_head=True, color=color, zorder=5, alpha=0.9)


def db_clip(power: np.ndarray, dynamic_range_db: float = 60.0) -> np.ndarray:
    db = 10.0 * np.log10(power + 1e-30)
    if np.any(np.isfinite(db)):
        db = np.maximum(db, np.nanmax(db) - dynamic_range_db)
    return db


def valid_path_indices(paths: np.lib.npyio.NpzFile) -> np.ndarray:
    tau = paths["tau_s"].reshape(-1)
    valid = paths["valid"].reshape(-1).astype(bool)
    return np.flatnonzero(valid & np.isfinite(tau) & (tau > 1e-10))


def path_kind(interactions: np.ndarray) -> str:
    values = set(int(v) for v in interactions if int(v) != 0)
    if 1 in values and 2 in values:
        return "mixed"
    if 2 in values:
        return "diffuse"
    return "specular"


def select_paths(paths: np.lib.npyio.NpzFile, obs: np.lib.npyio.NpzFile,
                 max_paths: int) -> tuple[np.ndarray, np.ndarray]:
    valid_idx = valid_path_indices(paths)
    interactions = paths["interactions"].reshape(2, -1)[:, valid_idx]
    energy = obs["path_energy"]
    fov = obs["fov_path_mask"].astype(bool)
    candidates = np.flatnonzero(fov)
    if candidates.size == 0:
        candidates = np.arange(energy.size)

    parts = []
    top_all = candidates[np.argsort(energy[candidates])[-max(4, max_paths // 2):]]
    parts.append(top_all)
    diffuse_candidates = candidates[np.any(interactions[:, candidates] == 2, axis=0)]
    if diffuse_candidates.size:
        parts.append(diffuse_candidates[np.argsort(energy[diffuse_candidates])[-max(4, max_paths // 2):]])
    selected_obs = np.unique(np.concatenate(parts))
    selected_obs = selected_obs[np.argsort(energy[selected_obs])][-max_paths:]
    return selected_obs, valid_idx[selected_obs]


def path_polyline(tx_xy: tuple[float, float], rx_xy: tuple[float, float],
                  vertices: np.ndarray, interactions: np.ndarray) -> np.ndarray:
    pts: list[tuple[float, float]] = [tx_xy]
    for depth, interaction in enumerate(interactions):
        if int(interaction) == 0:
            continue
        vertex = vertices[depth]
        pts.append((float(vertex[0]), float(vertex[1])))
    pts.append(rx_xy)
    return np.asarray(pts, dtype=float)


def draw_top_paths(ax: plt.Axes, run_dir: Path, objects: dict[str, Any],
                   max_paths: int = 40, annotate: bool = True) -> dict[str, Any]:
    cfg = load_yaml(run_dir / "config.yaml")
    metrics = load_json(run_dir / "metrics.json")
    paths = np.load(run_dir / "paths_summary.npz")
    obs = np.load(run_dir / "radar_observation.npz")

    devices = cfg["devices"]
    tx = tuple(float(x) for x in devices["tx_position_m"][:2])
    rx = tuple(float(x) for x in devices["rx_position_m"][:2])
    fov = metrics["radar_observation"]["fov"]
    boresight = float(fov["az_center_deg"])

    draw_scene(ax, objects, annotate=annotate)
    add_fov(ax, rx, boresight, float(fov["az_width_deg"]), radius=45.0)
    add_boresight(ax, rx, boresight, length=18.0)

    selected_obs, selected_raw = select_paths(paths, obs, max_paths=max_paths)
    interactions = paths["interactions"].reshape(2, -1)[:, selected_raw]
    vertices = paths["vertices"].reshape(2, -1, 3)[:, selected_raw, :]
    energy = obs["path_energy"][selected_obs]
    log_energy = 10.0 * np.log10(energy + 1e-30)
    denom = max(float(np.max(log_energy) - np.min(log_energy)), 1e-9)

    segments_by_kind: dict[str, list[np.ndarray]] = {"specular": [], "diffuse": [], "mixed": []}
    linewidths_by_kind: dict[str, list[float]] = {"specular": [], "diffuse": [], "mixed": []}
    for i in range(selected_raw.size):
        kind = path_kind(interactions[:, i])
        poly = path_polyline(tx, rx, vertices[:, i, :], interactions[:, i])
        strength = (float(log_energy[i]) - float(np.min(log_energy))) / denom
        segments_by_kind[kind].append(poly)
        linewidths_by_kind[kind].append(0.4 + 2.2 * strength)
        for depth, interaction in enumerate(interactions[:, i]):
            if int(interaction) == 0:
                continue
            marker = "o" if int(interaction) == 1 else "x"
            ax.scatter(vertices[depth, i, 0], vertices[depth, i, 1], marker=marker, s=18,
                       color=KIND_COLORS[kind], zorder=7, alpha=0.85)

    for kind, segments in segments_by_kind.items():
        if not segments:
            continue
        collection = LineCollection(segments, colors=KIND_COLORS[kind],
                                    linewidths=linewidths_by_kind[kind], alpha=0.76, zorder=6)
        ax.add_collection(collection)

    ax.scatter([tx[0]], [tx[1]], marker="^", s=60, color="#111827", label="Tx", zorder=8)
    ax.scatter([rx[0]], [rx[1]], marker="s", s=52, color="#ef4444", label="Rx 16x16", zorder=8)
    xmin, xmax, ymin, ymax = scene_limits(objects)
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("Top-down echo paths")
    return {
        "selected_paths": int(selected_raw.size),
        "top_energy": float(np.max(energy)) if energy.size else 0.0,
    }


def draw_interaction_hotspots(ax: plt.Axes, run_dir: Path, objects: dict[str, Any],
                              max_points: int = 25000) -> None:
    paths = np.load(run_dir / "paths_summary.npz")
    obs = np.load(run_dir / "radar_observation.npz")
    valid_idx = valid_path_indices(paths)
    interactions = paths["interactions"].reshape(2, -1)[:, valid_idx]
    vertices = paths["vertices"].reshape(2, -1, 3)[:, valid_idx, :]
    energy = obs["path_energy"]
    fov = obs["fov_path_mask"].astype(bool)
    candidates = np.flatnonzero(fov & (interactions[0] != 0))
    if candidates.size == 0:
        candidates = np.flatnonzero(interactions[0] != 0)
    if candidates.size > max_points:
        candidates = candidates[np.argsort(energy[candidates])[-max_points:]]
    xy = vertices[0, candidates, :2]
    c = db_clip(energy[candidates])

    draw_scene(ax, objects, annotate=False)
    sc = ax.scatter(xy[:, 0], xy[:, 1], c=c, cmap="inferno", s=4, linewidths=0,
                    alpha=0.72, zorder=5)
    plt.colorbar(sc, ax=ax, fraction=0.046, pad=0.03, label="Path energy (dB, clipped)")
    xmin, xmax, ymin, ymax = scene_limits(objects)
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("First-interaction energy on buildings/ground")


def draw_range_maps(ax_az: plt.Axes, ax_el: plt.Axes, run_dir: Path) -> None:
    metrics = load_json(run_dir / "metrics.json")
    obs = np.load(run_dir / "radar_observation.npz")
    r_edges = obs["range_edges_m"]
    az_edges = obs["azimuth_edges_deg"]
    el_edges = obs["elevation_edges_deg"]
    fov = metrics["radar_observation"]["fov"]

    az_db = db_clip(obs["range_azimuth_power"])
    ax_az.imshow(az_db, aspect="auto", extent=[az_edges[0], az_edges[-1], r_edges[-1], r_edges[0]],
                 cmap="magma")
    az_half = float(fov["az_width_deg"]) / 2.0
    ax_az.axvline(float(fov["az_center_deg"]) - az_half, color="cyan", lw=1)
    ax_az.axvline(float(fov["az_center_deg"]) + az_half, color="cyan", lw=1)
    ax_az.set_xlabel("AoA azimuth (deg)")
    ax_az.set_ylabel("Range (m)")
    ax_az.set_title("Range-azimuth")

    el_db = db_clip(obs["range_elevation_power"])
    ax_el.imshow(el_db, aspect="auto", extent=[el_edges[0], el_edges[-1], r_edges[-1], r_edges[0]],
                 cmap="magma")
    ax_el.axvline(float(fov["el_min_deg"]), color="cyan", lw=1)
    ax_el.axvline(float(fov["el_max_deg"]), color="cyan", lw=1)
    ax_el.set_xlabel("AoA elevation (deg)")
    ax_el.set_ylabel("Range (m)")
    ax_el.set_title("Range-elevation")


def create_run_visuals(run_dir: Path, objects: dict[str, Any], out_dir: Path,
                       max_paths: int) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics = load_json(run_dir / "metrics.json")
    ro = metrics["radar_observation"]

    fig, ax = plt.subplots(figsize=(9, 7))
    draw_top_paths(ax, run_dir, objects, max_paths=max_paths, annotate=True)
    ax.legend(loc="upper right", fontsize=8)
    ax.set_title(f"{run_dir.name}\nTop-down echo paths")
    fig.tight_layout()
    path_trace = out_dir / "topdown_echo_paths.png"
    fig.savefig(path_trace, dpi=170)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 7))
    draw_interaction_hotspots(ax, run_dir, objects)
    ax.set_title(f"{run_dir.name}\nFirst-interaction energy")
    fig.tight_layout()
    hotspot = out_dir / "interaction_energy_hotspots.png"
    fig.savefig(hotspot, dpi=170)
    plt.close(fig)

    fig, axs = plt.subplots(2, 2, figsize=(15, 11))
    draw_top_paths(axs[0, 0], run_dir, objects, max_paths=max_paths, annotate=False)
    draw_interaction_hotspots(axs[0, 1], run_dir, objects, max_points=12000)
    draw_range_maps(axs[1, 0], axs[1, 1], run_dir)
    fig.suptitle(
        f"{run_dir.name} | FoV energy fraction={ro['energy_fraction_in_fov']:.6f} | "
        f"paths in FoV={ro['path_count_in_fov']}/{ro['path_count_total']}",
        fontsize=12,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    dashboard = out_dir / "radar_sensing_dashboard.png"
    fig.savefig(dashboard, dpi=160)
    plt.close(fig)

    return {
        "run_id": run_dir.name,
        "dashboard": str(dashboard),
        "topdown_echo_paths": str(path_trace),
        "interaction_energy_hotspots": str(hotspot),
    }


def create_campaign_overview(campaign_root: Path, rows: list[dict[str, str]],
                             objects: dict[str, Any], out_dir: Path) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    values = np.asarray([float(r["fov_energy_fraction"]) for r in rows], dtype=float)
    norm = Normalize(vmin=float(values.min()), vmax=float(values.max()))
    cmap = plt.get_cmap("viridis")

    fig, axes = plt.subplots(1, 2, figsize=(16, 7), sharex=True, sharey=True)
    for ax, boresight in zip(axes, ["BposX", "BposY"]):
        draw_scene(ax, objects, annotate=True)
        sub = [r for r in rows if r["boresight_id"] == boresight]
        for r in sub:
            x = float(r["x_m"])
            y = float(r["y_m"])
            az = float(r["boresight_az_deg"])
            value = float(r["fov_energy_fraction"])
            color = cmap(norm(value))
            add_fov(ax, (x, y), az, 120.0, radius=18.0, color=color, alpha=0.2)
            add_boresight(ax, (x, y), az, length=9.0, color=color, lw=1.4)
            ax.scatter([x], [y], s=42, color=[color], edgecolor="#111827", lw=0.6, zorder=8)
            ax.text(x + 1.2, y + 1.0, r["pose_id"], fontsize=7, zorder=9)
        xmin, xmax, ymin, ymax = scene_limits(objects)
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("x (m)")
        ax.set_title(f"{boresight}: radar pose, boresight, FoV, FoV energy")
    axes[0].set_ylabel("y (m)")
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    fig.colorbar(sm, ax=axes.ravel().tolist(), fraction=0.035, pad=0.02, label="FoV energy fraction")
    fig.suptitle("C002-full radar shooting geometry over city buildings", fontsize=13)
    out = out_dir / "campaign_pose_fov_geometry.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return str(out)


def write_report(campaign_root: Path, campaign_fig: str, visual_rows: list[dict[str, str]]) -> None:
    report = campaign_root / "visualizations" / "VISUALIZATION_REPORT.md"
    selected = []
    rows = load_rows(campaign_root)
    visual_run_ids = {v["run_id"] for v in visual_rows}
    report_rows = [r for r in rows if r["run_id"] in visual_run_ids]
    by_run = {r["run_id"]: r for r in report_rows}
    high = max(report_rows, key=lambda r: float(r["fov_energy_fraction"]))
    low = min(report_rows, key=lambda r: float(r["fov_energy_fraction"]))
    center = next((r for r in report_rows if r["pose_id"] == "Pp0_p0" and r["boresight_id"] == "BposY"), high)
    for r in [high, center, low]:
        if r["run_id"] not in selected:
            selected.append(r["run_id"])

    with report.open("w", encoding="utf-8") as f:
        f.write("# Radar Sensing Visualization Report\n\n")
        f.write("This folder visualizes radar-only self-Tx/Rx sensing measurements. No UE or communication pass is used.\n\n")
        f.write("## Campaign Overview\n\n")
        f.write(f"- Campaign pose/FoV geometry: `{Path(campaign_fig).relative_to(campaign_root)}`\n\n")
        f.write("## Per-Run Visuals\n\n")
        f.write("Each run folder contains:\n\n")
        f.write("- `radar_sensing_dashboard.png`: scene geometry, echo paths, first-interaction hotspots, range-azimuth, and range-elevation.\n")
        f.write("- `topdown_echo_paths.png`: strongest in-FoV echo paths over the building footprint.\n")
        f.write("- `interaction_energy_hotspots.png`: where returned path energy first interacts with buildings or ground.\n\n")
        f.write("## Representative Runs\n\n")
        f.write("| Role | Run | FoV Energy Fraction | Dashboard |\n")
        f.write("|---|---|---:|---|\n")
        visuals = {v["run_id"]: v for v in visual_rows}
        roles = ["highest FoV energy", "center pose +y", "lowest FoV energy"]
        for role, run_id in zip(roles, selected):
            row = by_run[run_id]
            dash = Path(visuals[run_id]["dashboard"]).relative_to(campaign_root)
            f.write(f"| {role} | `{run_id}` | {float(row['fov_energy_fraction']):.6f} | `{dash}` |\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate radar sensing visualizations for C002-full.")
    parser.add_argument("--campaign-root", default="outputs/sionna_radar_campaigns/C002_full_radar_sensing")
    parser.add_argument("--max-paths", type=int, default=44)
    parser.add_argument("--limit-runs", type=int, default=0, help="Debug: process only the first N runs; 0 means all.")
    args = parser.parse_args()

    campaign_root = Path(args.campaign_root)
    rows = load_rows(campaign_root)
    run_dirs = [Path(r["run_dir"]) for r in rows]
    if args.limit_runs > 0:
        run_dirs = run_dirs[:args.limit_runs]

    objects = scene_objects(run_dirs[0])
    out_root = campaign_root / "visualizations"
    campaign_dir = out_root / "campaign"
    per_run_root = out_root / "per_run"

    campaign_fig = create_campaign_overview(campaign_root, rows, objects, campaign_dir)
    visual_rows = []
    for run_dir in run_dirs:
        visual_rows.append(create_run_visuals(run_dir, objects, per_run_root / run_dir.name, args.max_paths))
    write_report(campaign_root, campaign_fig, visual_rows)
    print(json.dumps({
        "campaign_root": str(campaign_root),
        "visualization_root": str(out_root),
        "runs_visualized": len(visual_rows),
        "campaign_figure": campaign_fig,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
