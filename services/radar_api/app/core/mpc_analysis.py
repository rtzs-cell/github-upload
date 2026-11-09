from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
from app.core.mpc_panorama import build_mpc_panorama_artifacts

from app.core.path_statistics import build_path_statistics, read_json


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def configure_matplotlib_font() -> None:
    for path in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ):
        font_path = Path(path)
        if font_path.exists():
            font_manager.fontManager.addfont(str(font_path))
            plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "WenQuanYi Micro Hei", "DejaVu Sans"]
            break
    plt.rcParams["axes.unicode_minus"] = False


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def azimuth_delta_deg(values: np.ndarray, center_deg: float) -> np.ndarray:
    return (values - float(center_deg) + 180.0) % 360.0 - 180.0


def circular_weighted_mean_deg(values: np.ndarray, weights: np.ndarray) -> float | None:
    if values.size == 0:
        return None
    weights = np.maximum(np.asarray(weights, dtype=np.float64), 0.0)
    if not np.any(weights > 0):
        weights = np.ones_like(values, dtype=np.float64)
    z = np.sum(weights * np.exp(1j * np.deg2rad(values)))
    if abs(z) <= 1e-30:
        return None
    return float((np.rad2deg(np.angle(z)) + 180.0) % 360.0 - 180.0)


def weighted_percentile(values: np.ndarray, weights: np.ndarray, percentile: float) -> float | None:
    if values.size == 0:
        return None
    order = np.argsort(values)
    values = values[order]
    weights = np.maximum(weights[order], 0.0)
    total = float(np.sum(weights))
    if total <= 0.0:
        return float(np.percentile(values, percentile))
    cdf = np.cumsum(weights) / total
    idx = int(np.searchsorted(cdf, percentile / 100.0, side="left"))
    idx = max(0, min(idx, values.size - 1))
    return float(values[idx])


def draw_azimuth_gate(ax: Any, center_deg: float, width_deg: float) -> None:
    half = float(width_deg) / 2.0
    left = (float(center_deg) - half + 180.0) % 360.0 - 180.0
    right = (float(center_deg) + half + 180.0) % 360.0 - 180.0
    if left <= right:
        ax.axvspan(left, right, color="#30b7c9", alpha=0.12)
        ax.axvline(left, color="#30b7c9", linewidth=1.0)
        ax.axvline(right, color="#30b7c9", linewidth=1.0)
    else:
        ax.axvspan(-180.0, right, color="#30b7c9", alpha=0.12)
        ax.axvspan(left, 180.0, color="#30b7c9", alpha=0.12)
        ax.axvline(left, color="#30b7c9", linewidth=1.0)
        ax.axvline(right, color="#30b7c9", linewidth=1.0)


def rows_to_arrays(rows: list[dict[str, Any]]) -> dict[str, np.ndarray]:
    return {
        "path_id": np.asarray([int(row["path_id"]) for row in rows], dtype=np.int64),
        "range_m": np.asarray([float(row["range_m"]) for row in rows], dtype=np.float64),
        "delay_s": np.asarray([float(row["delay_s"]) for row in rows], dtype=np.float64),
        "energy": np.asarray([float(row["energy"]) for row in rows], dtype=np.float64),
        "energy_db": np.asarray([float(row["energy_db"]) for row in rows], dtype=np.float64),
        "in_gate": np.asarray([bool(row["in_analysis_gate"]) for row in rows], dtype=bool),
        "aoa_azimuth_deg": np.asarray([float(row["aoa_azimuth_deg"]) for row in rows], dtype=np.float64),
        "aoa_elevation_deg": np.asarray([float(row["aoa_elevation_deg"]) for row in rows], dtype=np.float64),
    }


def gate_masks(arrays: dict[str, np.ndarray], fov: dict[str, Any]) -> dict[str, np.ndarray]:
    az_center = float(fov.get("az_center_deg", 0.0))
    az_width = float(fov.get("az_width_deg", 360.0))
    el_min = float(fov.get("el_min_deg", -90.0))
    el_max = float(fov.get("el_max_deg", 90.0))
    rmax = float(fov.get("rmax_m", np.inf))
    az_ok = np.abs(azimuth_delta_deg(arrays["aoa_azimuth_deg"], az_center)) <= az_width / 2.0
    el_ok = (arrays["aoa_elevation_deg"] >= el_min) & (arrays["aoa_elevation_deg"] <= el_max)
    range_ok = arrays["range_m"] <= rmax
    return {
        "azimuth": az_ok,
        "elevation": el_ok,
        "range": range_ok,
        "all": az_ok & el_ok & range_ok,
    }


def gate_summary(rows: list[dict[str, Any]], fov: dict[str, Any]) -> dict[str, Any]:
    arrays = rows_to_arrays(rows)
    masks = gate_masks(arrays, fov)
    energy = arrays["energy"]
    gate = arrays["in_gate"]
    valid_count = len(rows)
    total_energy = float(np.sum(energy))
    gate_energy = float(np.sum(energy[gate]))
    gate_out = ~gate
    strong_mask = energy >= np.percentile(energy, 90.0) if energy.size else np.array([], dtype=bool)
    suggestion_source = strong_mask if np.any(strong_mask) else np.ones_like(gate, dtype=bool)
    suggested_az = circular_weighted_mean_deg(arrays["aoa_azimuth_deg"][suggestion_source], energy[suggestion_source])
    suggested_el = weighted_percentile(arrays["aoa_elevation_deg"][suggestion_source], energy[suggestion_source], 50.0)
    strongest_idx = int(np.argmax(energy)) if energy.size else -1
    return {
        "schema_version": "0.3.0",
        "created_at_utc": utc_now(),
        "valid_path_count": int(valid_count),
        "analysis_gate_path_count": int(np.count_nonzero(gate)),
        "analysis_gate_energy": gate_energy,
        "total_energy": total_energy,
        "analysis_gate_energy_fraction": float(gate_energy / max(total_energy, 1e-300)),
        "candidate_count_by_single_condition": {
            "range": int(np.count_nonzero(masks["range"])),
            "aoa_azimuth": int(np.count_nonzero(masks["azimuth"])),
            "aoa_elevation": int(np.count_nonzero(masks["elevation"])),
        },
        "candidate_count_by_combined_condition": {
            "range_and_azimuth": int(np.count_nonzero(masks["range"] & masks["azimuth"])),
            "range_and_elevation": int(np.count_nonzero(masks["range"] & masks["elevation"])),
            "azimuth_and_elevation": int(np.count_nonzero(masks["azimuth"] & masks["elevation"])),
            "range_and_azimuth_and_elevation": int(np.count_nonzero(masks["all"])),
        },
        "excluded_path_count_by_condition": {
            "outside_range": int(np.count_nonzero(gate_out & ~masks["range"])),
            "outside_aoa_azimuth": int(np.count_nonzero(gate_out & ~masks["azimuth"])),
            "outside_aoa_elevation": int(np.count_nonzero(gate_out & ~masks["elevation"])),
        },
        "energy_weighted_strong_path_suggestion": {
            "azimuth_center_deg": suggested_az,
            "elevation_center_deg": suggested_el,
            "note": "该建议只用于调整分析门限或雷达指向，不表示 PathSolver 只向该角域发射射线。",
        },
        "strongest_path": None
        if strongest_idx < 0
        else {
            "path_id": int(arrays["path_id"][strongest_idx]),
            "range_m": float(arrays["range_m"][strongest_idx]),
            "aoa_azimuth_deg": float(arrays["aoa_azimuth_deg"][strongest_idx]),
            "aoa_elevation_deg": float(arrays["aoa_elevation_deg"][strongest_idx]),
            "energy": float(energy[strongest_idx]),
            "energy_db": float(arrays["energy_db"][strongest_idx]),
            "in_analysis_gate": bool(gate[strongest_idx]),
        },
        "analysis_gate": {
            "az_center_deg": float(fov.get("az_center_deg", 0.0)),
            "az_width_deg": float(fov.get("az_width_deg", 360.0)),
            "el_min_deg": float(fov.get("el_min_deg", -90.0)),
            "el_max_deg": float(fov.get("el_max_deg", 90.0)),
            "rmax_m": float(fov.get("rmax_m", np.inf)),
        },
    }


def select_plot_indices(energy: np.ndarray, mask: np.ndarray, limit: int) -> np.ndarray:
    idx = np.flatnonzero(mask)
    if idx.size <= limit:
        return idx
    ordered = idx[np.argsort(energy[idx])[::-1]]
    return ordered[:limit]


def marker_sizes(energy_db: np.ndarray) -> np.ndarray:
    if energy_db.size == 0:
        return np.array([], dtype=np.float64)
    high = float(np.max(energy_db))
    low = high - 50.0
    scaled = np.clip((energy_db - low) / max(high - low, 1e-9), 0.0, 1.0)
    return 12.0 + 42.0 * scaled


def write_mpc_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    sorted_rows = sorted((row for row in rows if row["in_analysis_gate"]), key=lambda item: item["energy"], reverse=True)
    max_energy = max((float(row["energy"]) for row in sorted_rows), default=0.0)
    fieldnames = [
        "path_id",
        "range_m",
        "delay_s",
        "energy",
        "energy_db",
        "relative_energy_db",
        "aoa_azimuth_deg",
        "aoa_elevation_deg",
        "aod_azimuth_deg",
        "aod_elevation_deg",
        "depth",
        "kind",
        "first_object_id",
        "touched_object_ids",
    ]
    csv_rows: list[dict[str, Any]] = []
    for row in sorted_rows:
        energy = float(row["energy"])
        csv_rows.append(
            {
                **row,
                "relative_energy_db": float(10.0 * np.log10(max(energy / max(max_energy, 1e-300), 1e-300))),
            }
        )
    write_csv(path, csv_rows, fieldnames)


def draw_mpc_figure(fig_path: Path, rows: list[dict[str, Any]], fov: dict[str, Any], run_id: str) -> None:
    configure_matplotlib_font()
    arrays = rows_to_arrays(rows)
    energy = arrays["energy"]
    energy_db = arrays["energy_db"]
    gate = arrays["in_gate"]
    background = select_plot_indices(energy, np.ones_like(gate, dtype=bool), 25000)
    gate_idx = select_plot_indices(energy, gate, 25000)
    sizes = marker_sizes(energy_db[gate_idx])

    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.8), constrained_layout=True)
    axes[0].scatter(
        arrays["aoa_azimuth_deg"][background],
        arrays["range_m"][background],
        s=4,
        color="#9aa8ad",
        alpha=0.22,
        linewidths=0,
        label="有效路径",
    )
    if gate_idx.size:
        sc0 = axes[0].scatter(
            arrays["aoa_azimuth_deg"][gate_idx],
            arrays["range_m"][gate_idx],
            c=energy_db[gate_idx],
            s=sizes,
            cmap="magma",
            alpha=0.88,
            linewidths=0,
            label="分析门限内 MPC",
        )
        fig.colorbar(sc0, ax=axes[0], label="路径能量 (dB)")
    draw_azimuth_gate(axes[0], float(fov.get("az_center_deg", 0.0)), float(fov.get("az_width_deg", 360.0)))
    axes[0].axhline(float(fov.get("rmax_m", np.nan)), color="#30b7c9", linewidth=1.0)
    axes[0].set_xlabel("到达方位角 (deg)")
    axes[0].set_ylabel("等效单站距离 (m)")
    axes[0].set_title("距离-到达方位角 MPC")
    axes[0].set_xlim(-180.0, 180.0)
    axes[0].invert_yaxis()
    axes[0].legend(loc="upper right", fontsize=8)

    axes[1].scatter(
        arrays["aoa_elevation_deg"][background],
        arrays["range_m"][background],
        s=4,
        color="#9aa8ad",
        alpha=0.22,
        linewidths=0,
    )
    if gate_idx.size:
        sc1 = axes[1].scatter(
            arrays["aoa_elevation_deg"][gate_idx],
            arrays["range_m"][gate_idx],
            c=energy_db[gate_idx],
            s=sizes,
            cmap="magma",
            alpha=0.88,
            linewidths=0,
        )
        fig.colorbar(sc1, ax=axes[1], label="路径能量 (dB)")
    axes[1].axvspan(float(fov.get("el_min_deg", -90.0)), float(fov.get("el_max_deg", 90.0)), color="#30b7c9", alpha=0.12)
    axes[1].axvline(float(fov.get("el_min_deg", -90.0)), color="#30b7c9", linewidth=1.0)
    axes[1].axvline(float(fov.get("el_max_deg", 90.0)), color="#30b7c9", linewidth=1.0)
    axes[1].axhline(float(fov.get("rmax_m", np.nan)), color="#30b7c9", linewidth=1.0)
    axes[1].set_xlabel("到达俯仰角 (deg)")
    axes[1].set_ylabel("等效单站距离 (m)")
    axes[1].set_title("距离-到达俯仰角 MPC")
    axes[1].invert_yaxis()

    if gate_idx.size:
        top = gate_idx[np.argsort(arrays["range_m"][gate_idx])][:500]
        rel_db = 10.0 * np.log10(np.maximum(energy[top] / max(float(np.max(energy[gate_idx])), 1e-300), 1e-300))
        floor = -60.0
        axes[2].vlines(arrays["range_m"][top], floor, rel_db, color="#0d6d5f", alpha=0.36, linewidth=0.8)
        axes[2].scatter(arrays["range_m"][top], rel_db, s=16, color="#0d6d5f", alpha=0.82)
        axes[2].set_ylim(floor, 2.0)
    else:
        axes[2].text(0.5, 0.5, "当前分析门限内没有有效 MPC", ha="center", va="center", transform=axes[2].transAxes)
    axes[2].set_xlabel("等效单站距离 (m)")
    axes[2].set_ylabel("相对路径能量 (dB)")
    axes[2].set_title("门限内路径能量分布")
    axes[2].grid(True, alpha=0.22)
    fig.suptitle(f"{run_id} 门限内多径分量分析")
    fig.savefig(fig_path, dpi=160)
    plt.close(fig)


def build_mpc_analysis_artifacts(run_dir: Path) -> dict[str, Any]:
    stats = build_path_statistics(run_dir)
    metrics = read_json(run_dir / "metrics.json")
    rows = stats["paths"]
    fov = dict(metrics.get("radar_observation", {}).get("fov", {}) or {})
    if "rmax_m" not in fov:
        config = {}
        cfg_path = run_dir / "config.yaml"
        if cfg_path.exists():
            import yaml

            with cfg_path.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        fov.update(config.get("fov", {}) or {})
        fov.setdefault("rmax_m", (config.get("range_processing", {}) or {}).get("rmax_m", 200.0))
    fov.setdefault("az_center_deg", 0.0)
    fov.setdefault("az_width_deg", 120.0)
    fov.setdefault("el_min_deg", 0.0)
    fov.setdefault("el_max_deg", 40.0)
    fov.setdefault("rmax_m", 200.0)

    analysis_dir = run_dir / "analysis"
    figures_dir = run_dir / "figures"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    csv_path = analysis_dir / "analysis_gate_mpc.csv"
    summary_path = analysis_dir / "analysis_gate_mpc_summary.json"
    fig_path = figures_dir / "analysis_gate_mpc.png"
    write_mpc_csv(csv_path, rows)
    draw_mpc_figure(fig_path, rows, fov, run_dir.name)
    panorama = build_mpc_panorama_artifacts(run_dir)
    summary = {
        **gate_summary(rows, fov),
        "schema_version": "1.2.0",
        "run_id": run_dir.name,
        "source_run_dir": str(run_dir),
        "files": {
            "analysis_gate_paths": str(csv_path),
            "analysis_gate_paths_figure": str(fig_path),
            **panorama["files"],
        },
        "mpc_panorama": panorama["summary"],
    }
    write_json(summary_path, summary)
    return {"summary": summary, "files": summary["files"]}
