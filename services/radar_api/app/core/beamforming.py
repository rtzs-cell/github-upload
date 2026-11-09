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
import yaml

from app.core.path_statistics import SPEED_OF_LIGHT, observation_arrays
from app.core.path_layout import ensure_canonical_path_archive
from sionna_radar.antenna_patterns import (
    CUSTOM_GAIN_PATTERN,
    RADAR_ARRAY_PATTERN,
    aperture_samples,
    numpy_element_factor_field,
    numpy_custom_gain_field,
    numpy_radar_array_field,
    parse_complex_weights,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


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


def parse_custom_weights(raw: str | None, count: int, side: str = "rx") -> np.ndarray:
    if not raw:
        raise ValueError(f"custom_complex_weights mode requires {side}_custom_weights_json")
    return parse_complex_weights(raw, count, side).astype(np.complex64)


def normalize_weights(weights: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(weights))
    if norm <= 0.0:
        raise ValueError("beamforming weights must not all be zero")
    return weights.astype(np.complex64) / norm


def flatten_sionna_planar_array(values: np.ndarray) -> np.ndarray:
    """Flatten [row, column] values in Sionna PlanarArray channel order."""
    return np.asarray(values).reshape(-1, order="F")


def steering_weights(
    rows: int,
    cols: int,
    az_deg: float,
    el_deg: float,
    spacing_y: float,
    spacing_z: float,
    *,
    side: str = "rx",
) -> np.ndarray:
    az = np.deg2rad(float(az_deg))
    el = np.deg2rad(float(el_deg))
    col_idx = np.arange(cols, dtype=np.float32) - (cols - 1) / 2.0
    row_idx = (rows - 1) / 2.0 - np.arange(rows, dtype=np.float32)
    yy, zz = np.meshgrid(col_idx * float(spacing_y), row_idx * float(spacing_z))
    phase = 2.0 * np.pi * (yy * np.sin(az) * np.cos(el) + zz * np.sin(el))
    if side == "tx":
        phase = -phase
    elif side != "rx":
        raise ValueError(f"Unknown beamforming side: {side}")
    return normalize_weights(flatten_sionna_planar_array(np.exp(1j * phase)).astype(np.complex64))


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


def infer_cir_axes(a: np.ndarray, path_count: int, rx_count: int, tx_count: int) -> dict[str, int]:
    shape = tuple(int(v) for v in a.shape)
    if a.ndim == 6 and shape[1] == rx_count and shape[3] == tx_count and shape[4] == path_count:
        return {"path_axis": 4, "rx_axis": 1, "tx_axis": 3}
    if a.ndim == 7 and shape[2] == rx_count and shape[4] == tx_count and shape[5] == path_count:
        return {"path_axis": 5, "rx_axis": 2, "tx_axis": 4}
    path_candidates = [axis for axis, size in enumerate(shape) if size == path_count]
    if not path_candidates:
        raise ValueError(f"Cannot find path axis for CIR shape {shape} and path_count={path_count}")
    path_axis = path_candidates[-1]

    rx_candidates = [axis for axis, size in enumerate(shape) if axis != path_axis and size == rx_count]
    if not rx_candidates:
        raise ValueError(f"Cannot find Rx antenna axis for CIR shape {shape} and rx_count={rx_count}")
    rx_axis = rx_candidates[-1] if rx_count > 1 else rx_candidates[0]

    tx_candidates = [
        axis
        for axis, size in enumerate(shape)
        if axis not in (path_axis, rx_axis) and size == tx_count
    ]
    if not tx_candidates:
        raise ValueError(f"Cannot find Tx antenna axis for CIR shape {shape} and tx_count={tx_count}")
    before_path = [axis for axis in tx_candidates if axis < path_axis]
    tx_axis = before_path[-1] if before_path else tx_candidates[0]
    return {"path_axis": path_axis, "rx_axis": rx_axis, "tx_axis": tx_axis}


def reorder_cir_for_combining(a: np.ndarray, axes: dict[str, int]) -> np.ndarray:
    primary = [axes["rx_axis"], axes["tx_axis"], axes["path_axis"]]
    rest = [axis for axis in range(a.ndim) if axis not in primary]
    return np.transpose(a, primary + rest)


def noncoherent_path_power(a: np.ndarray, path_axis: int) -> np.ndarray:
    sum_axes = tuple(axis for axis in range(a.ndim) if axis != path_axis)
    return np.sum(np.abs(a) ** 2, axis=sum_axes).reshape(-1).astype(np.float64)


def array_beamforming_weights(
    config: dict[str, Any],
    side: str,
    count: int,
    override: dict[str, Any] | None = None,
) -> tuple[str, np.ndarray]:
    array_cfg = config.get(f"{side}_array", {})
    bf_cfg = {**dict(config.get("beamforming", {}) or {}), **dict(override or {})}
    mode = str(bf_cfg.get(f"{side}_mode", "uniform"))
    if mode == "disabled":
        weights = np.zeros(count, dtype=np.complex64)
        weights[0] = 1.0
        return mode, weights
    if mode == "uniform":
        return mode, normalize_weights(np.ones(count, dtype=np.complex64))
    if mode == "custom_complex_weights":
        raw = bf_cfg.get(f"{side}_custom_weights_json")
        if raw is None and side == "rx":
            raw = bf_cfg.get("custom_weights_json")
        return mode, parse_custom_weights(raw, count, side)
    if mode == "steering_vector":
        rows = int(array_cfg.get("num_rows", 1))
        cols = int(array_cfg.get("num_cols", count))
        if rows * cols != count:
            rows, cols = 1, count
        az_key = f"{side}_steering_azimuth_deg"
        el_key = f"{side}_steering_elevation_deg"
        return mode, steering_weights(
            rows,
            cols,
            float(bf_cfg.get(az_key, bf_cfg.get("steering_azimuth_deg", 0.0))),
            float(bf_cfg.get(el_key, bf_cfg.get("steering_elevation_deg", 0.0))),
            float(array_cfg.get("horizontal_spacing", 0.5)),
            float(array_cfg.get("vertical_spacing", 0.5)),
            side=side,
        )
    raise ValueError(f"Unknown {side} beamforming mode: {mode}")


def beamforming_weights(config: dict[str, Any], rx_count: int, override: dict[str, Any] | None = None) -> tuple[str, np.ndarray]:
    return array_beamforming_weights(config, "rx", rx_count, override)


def steering_pattern(
    rows: int,
    cols: int,
    rx_weights: np.ndarray,
    spacing_y: float,
    spacing_z: float,
    azimuth_grid_deg: np.ndarray | None = None,
    elevation_grid_deg: np.ndarray | None = None,
    side: str = "rx",
    element_pattern: str = "iso",
    element_gain_grid_json: str | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    az_grid = np.asarray(
        azimuth_grid_deg if azimuth_grid_deg is not None else np.linspace(-180.0, 180.0, 361),
        dtype=np.float64,
    )
    el_grid = np.asarray(
        elevation_grid_deg if elevation_grid_deg is not None else np.linspace(-90.0, 90.0, 181),
        dtype=np.float64,
    )
    col_idx = np.arange(cols, dtype=np.float64) - (cols - 1) / 2.0
    row_idx = (rows - 1) / 2.0 - np.arange(rows, dtype=np.float64)
    yy, zz = np.meshgrid(col_idx * float(spacing_y), row_idx * float(spacing_z))
    y_flat = flatten_sionna_planar_array(yy)
    z_flat = flatten_sionna_planar_array(zz)
    if y_flat.size != rx_weights.size:
        raise ValueError("Steering pattern array shape does not match Rx weight count")

    az_rad = np.deg2rad(az_grid)
    gain = np.zeros((el_grid.size, az_grid.size), dtype=np.float64)
    norm = np.sqrt(float(rx_weights.size))
    for row, el_deg in enumerate(el_grid):
        el_rad = np.deg2rad(float(el_deg))
        phase = 2.0 * np.pi * (
            np.sin(az_rad)[:, None] * np.cos(el_rad) * y_flat[None, :]
            + np.sin(el_rad) * z_flat[None, :]
        )
        manifold = np.exp(1j * phase) / norm
        combining_weights = rx_weights if side == "tx" else np.conj(rx_weights)
        element_field = numpy_element_factor_field(
            az_grid,
            np.full_like(az_grid, el_deg),
            element_pattern,
            element_gain_grid_json,
        )
        gain[row, :] = np.abs(manifold @ combining_weights) ** 2 * np.abs(element_field) ** 2
    peak = max(float(np.max(gain)), 1e-300)
    gain = gain / peak
    return az_grid, el_grid, gain


def build_steering_pattern_artifacts(
    run_dir: Path,
    config: dict[str, Any],
    mode: str,
    rx_weights: np.ndarray,
    axes: dict[str, int],
) -> dict[str, str]:
    rx_cfg = config.get("rx_array", {})
    rows = int(rx_cfg.get("num_rows", 1))
    cols = int(rx_cfg.get("num_cols", rx_weights.size))
    if rows * cols != rx_weights.size:
        rows, cols = 1, int(rx_weights.size)
    spacing_y = float(rx_cfg.get("horizontal_spacing", 0.5))
    spacing_z = float(rx_cfg.get("vertical_spacing", 0.5))
    element_pattern = str(rx_cfg.get("pattern", "iso"))
    element_gain_grid_json = str(rx_cfg.get("gain_grid_json") or "") if element_pattern == CUSTOM_GAIN_PATTERN else None
    az_grid, el_grid, gain = steering_pattern(
        rows,
        cols,
        rx_weights,
        spacing_y,
        spacing_z,
        side="rx",
        element_pattern=element_pattern,
        element_gain_grid_json=element_gain_grid_json,
    )
    gain_db = 10.0 * np.log10(np.maximum(gain, 1e-12))
    az_mesh, el_mesh = np.meshgrid(az_grid, el_grid)
    element_field = numpy_element_factor_field(az_mesh, el_mesh, element_pattern, element_gain_grid_json)
    element_gain = np.abs(element_field) ** 2
    element_gain_db = 10.0 * np.log10(np.maximum(element_gain, 1e-12))
    phase = np.angle(rx_weights).reshape(rows, cols, order="F")
    amplitude = np.abs(rx_weights).reshape(rows, cols, order="F")
    peak_idx = np.unravel_index(int(np.argmax(gain)), gain.shape)

    analysis_dir = run_dir / "analysis"
    figures_dir = run_dir / "figures"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    npz_path = analysis_dir / "rx_steering_pattern.npz"
    np.savez_compressed(
        npz_path,
        azimuth_grid_deg=az_grid.astype(np.float32),
        elevation_grid_deg=el_grid.astype(np.float32),
        normalized_gain=gain.astype(np.float32),
        normalized_gain_db=gain_db.astype(np.float32),
        rx_weight_phase_rad=phase.astype(np.float32),
        rx_weight_amplitude=amplitude.astype(np.float32),
        rx_weights=rx_weights.astype(np.complex64),
        rx_weight_layout=np.asarray("column-major"),
        element_pattern=np.asarray(element_pattern),
        element_gain_grid_json=np.asarray(element_gain_grid_json or ""),
        element_factor_power=element_gain.astype(np.float32),
        element_factor_db=element_gain_db.astype(np.float32),
    )

    configure_matplotlib_font()
    fig_path = figures_dir / "rx_steering_pattern.png"
    fig, axes_obj = plt.subplots(1, 2, figsize=(12.0, 4.8), constrained_layout=True)
    im0 = axes_obj[0].imshow(phase, origin="lower", cmap="twilight", aspect="auto")
    axes_obj[0].set_title("接收阵列导向矢量相位")
    axes_obj[0].set_xlabel("阵列列索引")
    axes_obj[0].set_ylabel("阵列行索引")
    fig.colorbar(im0, ax=axes_obj[0], label="相位 (rad)")

    im1 = axes_obj[1].imshow(
        np.maximum(gain_db, -40.0),
        origin="lower",
        aspect="auto",
        extent=[float(az_grid[0]), float(az_grid[-1]), float(el_grid[0]), float(el_grid[-1])],
        cmap="magma",
    )
    axes_obj[1].scatter(
        [float(az_grid[peak_idx[1]])],
        [float(el_grid[peak_idx[0]])],
        marker="+",
        s=70,
        linewidths=1.8,
        color="cyan",
        label="主瓣峰值",
    )
    axes_obj[1].set_title("接收阵列归一化角域响应")
    axes_obj[1].set_xlabel("到达方位角 (deg)")
    axes_obj[1].set_ylabel("到达俯仰角 (deg)")
    axes_obj[1].legend(loc="upper right", fontsize=8)
    fig.colorbar(im1, ax=axes_obj[1], label="归一化增益 (dB)")
    fig.suptitle(f"Rx 数字波束成形：{mode}")
    fig.savefig(fig_path, dpi=160)
    plt.close(fig)

    element_path = analysis_dir / "rx_element_pattern.npz"
    np.savez_compressed(
        element_path,
        azimuth_grid_deg=az_grid.astype(np.float32),
        elevation_grid_deg=el_grid.astype(np.float32),
        pattern=np.asarray(element_pattern),
        gain_grid_json=np.asarray(element_gain_grid_json or ""),
        gain=element_gain.astype(np.float32),
        gain_db=element_gain_db.astype(np.float32),
    )
    element_fig_path = figures_dir / "rx_element_pattern.png"
    element_fig, element_axis = plt.subplots(1, 1, figsize=(6.4, 4.8), constrained_layout=True)
    element_image = element_axis.imshow(
        np.maximum(element_gain_db, -40.0),
        origin="lower",
        aspect="auto",
        extent=[float(az_grid[0]), float(az_grid[-1]), float(el_grid[0]), float(el_grid[-1])],
        cmap="magma",
    )
    element_axis.set_title(f"Rx element factor: {element_pattern}")
    element_axis.set_xlabel("Arrival azimuth (deg)")
    element_axis.set_ylabel("Arrival elevation (deg)")
    element_fig.colorbar(element_image, ax=element_axis, label="Element gain (dB)")
    element_fig.savefig(element_fig_path, dpi=160)
    plt.close(element_fig)

    summary_path = analysis_dir / "rx_steering_pattern_summary.json"
    summary = {
        "schema_version": "0.2.0",
        "run_id": run_dir.name,
        "created_at_utc": utc_now(),
        "rx_mode": mode,
        "rx_rows": int(rows),
        "rx_cols": int(cols),
        "rx_weight_count": int(rx_weights.size),
        "rx_weight_layout": "column-major",
        "element_pattern": element_pattern,
        "element_gain_grid_supplied": bool(element_gain_grid_json),
        "element_factor_included": True,
        "cir_axes": axes,
        "peak_azimuth_deg": float(az_grid[peak_idx[1]]),
        "peak_elevation_deg": float(el_grid[peak_idx[0]]),
        "files": {
            "rx_steering_pattern": str(npz_path),
            "rx_steering_pattern_figure": str(fig_path),
            "rx_steering_pattern_summary": str(summary_path),
            "rx_element_pattern": str(element_path),
            "rx_element_pattern_figure": str(element_fig_path),
        },
    }
    write_json(summary_path, summary)
    return summary["files"]


def build_tx_pattern_artifacts(run_dir: Path, config: dict[str, Any]) -> dict[str, str]:
    tx_cfg = dict(config.get("tx_array", {}) or {})
    bf_cfg = dict(config.get("beamforming", {}) or {})
    rows = int(tx_cfg.get("num_rows", 1))
    cols = int(tx_cfg.get("num_cols", 1))
    spacing_y = float(tx_cfg.get("horizontal_spacing", 0.5))
    spacing_z = float(tx_cfg.get("vertical_spacing", 0.5))
    steer_az = float(bf_cfg.get("tx_steering_azimuth_deg", 0.0))
    steer_el = float(bf_cfg.get("tx_steering_elevation_deg", 0.0))
    taper = str(bf_cfg.get("tx_taper", "uniform"))
    tx_weight_mode = str(bf_cfg.get("tx_weight_mode", bf_cfg.get("tx_mode", "steering_vector")))
    custom_weights_raw = bf_cfg.get("tx_custom_weights_json") if tx_weight_mode == "custom_complex_weights" else None
    az_grid = np.linspace(-90.0, 90.0, 181, dtype=np.float64)
    el_grid = np.linspace(-45.0, 45.0, 91, dtype=np.float64)
    az_mesh, el_mesh = np.meshgrid(az_grid, el_grid)
    pattern_name = str(tx_cfg.get("pattern", "iso"))
    equivalent_total_pattern = pattern_name == CUSTOM_GAIN_PATTERN
    if pattern_name == RADAR_ARRAY_PATTERN:
        element_pattern = str(tx_cfg.get("element_pattern", "tr38901"))
        element_gain_grid_json = str(tx_cfg.get("element_gain_grid_json") or "") if element_pattern == CUSTOM_GAIN_PATTERN else None
    elif equivalent_total_pattern:
        element_pattern = None
        element_gain_grid_json = None
    else:
        element_pattern = pattern_name
        element_gain_grid_json = str(tx_cfg.get("gain_grid_json") or "") if element_pattern == CUSTOM_GAIN_PATTERN else None
    if pattern_name == CUSTOM_GAIN_PATTERN:
        custom_weights_raw = None
        field = numpy_custom_gain_field(az_mesh, el_mesh, str(tx_cfg.get("gain_grid_json") or ""))
    else:
        field = numpy_radar_array_field(
            az_mesh,
            el_mesh,
            rows=rows,
            cols=cols,
            vertical_spacing=spacing_z,
            horizontal_spacing=spacing_y,
            steering_azimuth_deg=steer_az,
            steering_elevation_deg=steer_el,
            taper=taper,
            element_pattern=element_pattern,
            element_gain_grid_json=element_gain_grid_json,
            custom_weights_json=custom_weights_raw,
        )
    gain = np.abs(field) ** 2
    peak_index = np.unravel_index(int(np.argmax(gain)), gain.shape)
    normalized_gain_db = 10.0 * np.log10(np.maximum(gain / max(float(np.max(gain)), 1e-30), 1e-12))

    y, z, aperture_amplitude = aperture_samples(rows, cols, spacing_z, spacing_y, taper)
    if custom_weights_raw is not None:
        aperture_weights = parse_complex_weights(custom_weights_raw, rows * cols, "Tx")
        amplitude = np.abs(aperture_weights)
        phase = np.angle(aperture_weights)
    else:
        amplitude = aperture_amplitude
        steer_az_rad = np.deg2rad(steer_az)
        steer_el_rad = np.deg2rad(steer_el)
        phase = -2.0 * np.pi * (
            y * np.sin(steer_az_rad) * np.cos(steer_el_rad)
            + z * np.sin(steer_el_rad)
        )

    analysis_dir = run_dir / "analysis"
    figures_dir = run_dir / "figures"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    npz_path = analysis_dir / "tx_radiation_pattern.npz"
    np.savez_compressed(
        npz_path,
        azimuth_grid_deg=az_grid.astype(np.float32),
        elevation_grid_deg=el_grid.astype(np.float32),
        gain=gain.astype(np.float32),
        normalized_gain_db=normalized_gain_db.astype(np.float32),
        aperture_weight_amplitude=amplitude.reshape(rows, cols).astype(np.float32),
        aperture_weight_phase_rad=phase.reshape(rows, cols).astype(np.float32),
        pattern_mode=np.asarray("equivalent_total_gain_grid" if equivalent_total_pattern else "element_factor_times_array_factor"),
        element_pattern=np.asarray(element_pattern or "not_applicable"),
        element_gain_grid_json=np.asarray(element_gain_grid_json or ""),
    )

    figure_path = figures_dir / "tx_radiation_pattern.png"
    fig, axes_obj = plt.subplots(1, 2, figsize=(12.0, 4.8), constrained_layout=True)
    im0 = axes_obj[0].imshow(phase.reshape(rows, cols), origin="upper", cmap="twilight", aspect="auto")
    axes_obj[0].set_title("Tx aperture phase weights")
    axes_obj[0].set_xlabel("Array column")
    axes_obj[0].set_ylabel("Array row")
    fig.colorbar(im0, ax=axes_obj[0], label="Phase (rad)")
    im1 = axes_obj[1].imshow(
        np.maximum(normalized_gain_db, -40.0),
        origin="lower",
        aspect="auto",
        extent=[float(az_grid[0]), float(az_grid[-1]), float(el_grid[0]), float(el_grid[-1])],
        cmap="magma",
    )
    axes_obj[1].scatter(
        [float(az_grid[peak_index[1]])],
        [float(el_grid[peak_index[0]])],
        marker="+",
        s=70,
        linewidths=1.8,
        color="cyan",
    )
    axes_obj[1].set_title("Tx normalized radiation pattern")
    axes_obj[1].set_xlabel("Local azimuth (deg)")
    axes_obj[1].set_ylabel("Local elevation (deg)")
    fig.colorbar(im1, ax=axes_obj[1], label="Normalized gain (dB)")
    fig.savefig(figure_path, dpi=160)
    plt.close(fig)
    files = {
        "tx_radiation_pattern": str(npz_path),
        "tx_radiation_pattern_figure": str(figure_path),
    }
    if element_pattern is not None:
        element_field = numpy_element_factor_field(az_mesh, el_mesh, element_pattern, element_gain_grid_json)
        element_gain = np.abs(element_field) ** 2
        element_gain_db = 10.0 * np.log10(np.maximum(element_gain, 1e-12))
        element_path = analysis_dir / "tx_element_pattern.npz"
        np.savez_compressed(
            element_path,
            azimuth_grid_deg=az_grid.astype(np.float32),
            elevation_grid_deg=el_grid.astype(np.float32),
            pattern=np.asarray(element_pattern),
            gain_grid_json=np.asarray(element_gain_grid_json or ""),
            gain=element_gain.astype(np.float32),
            gain_db=element_gain_db.astype(np.float32),
        )
        element_figure_path = figures_dir / "tx_element_pattern.png"
        element_fig, element_axis = plt.subplots(1, 1, figsize=(6.4, 4.8), constrained_layout=True)
        element_image = element_axis.imshow(
            np.maximum(element_gain_db, -40.0),
            origin="lower",
            aspect="auto",
            extent=[float(az_grid[0]), float(az_grid[-1]), float(el_grid[0]), float(el_grid[-1])],
            cmap="magma",
        )
        element_axis.set_title(f"Tx element factor: {element_pattern}")
        element_axis.set_xlabel("Local azimuth (deg)")
        element_axis.set_ylabel("Local elevation (deg)")
        element_fig.colorbar(element_image, ax=element_axis, label="Element gain (dB)")
        element_fig.savefig(element_figure_path, dpi=160)
        plt.close(element_fig)
        files.update(
            {
                "tx_element_pattern": str(element_path),
                "tx_element_pattern_figure": str(element_figure_path),
            }
        )
    return files


def build_beamforming_artifacts(run_dir: Path, override: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure_canonical_path_archive(run_dir)
    config = read_yaml(run_dir / "config.yaml")
    cir = np.load(run_dir / "cir.npz", allow_pickle=False)
    paths = np.load(run_dir / "paths_summary.npz", allow_pickle=False)
    a = np.asarray(cir["a"])
    tau = np.asarray(paths["tau_s"]).reshape(-1).astype(np.float64)
    rx_cfg = config.get("rx_array", {})
    tx_cfg = config.get("tx_array", {})
    bf_cfg = dict(config.get("beamforming", {}) or {})
    rx_count = int(rx_cfg.get("num_rows", 1)) * int(rx_cfg.get("num_cols", 1))
    requested_tx_count = int(tx_cfg.get("num_rows", 1)) * int(tx_cfg.get("num_cols", 1))
    tx_pattern_name = str(tx_cfg.get("pattern", ""))
    tx_aperture_embedded = tx_pattern_name in {RADAR_ARRAY_PATTERN, CUSTOM_GAIN_PATTERN}
    tx_element_pattern = (
        str(tx_cfg.get("element_pattern", "tr38901"))
        if tx_pattern_name == RADAR_ARRAY_PATTERN
        else ("not_applicable" if tx_pattern_name == CUSTOM_GAIN_PATTERN else tx_pattern_name or "iso")
    )
    cir_tx_count = 1 if tx_aperture_embedded else requested_tx_count
    axes = infer_cir_axes(a, tau.size, rx_count, cir_tx_count)
    mode, rx_weights = beamforming_weights(config, rx_count, override)
    if tx_aperture_embedded:
        tx_mode = "embedded_sionna_custom_weights" if str(tx_cfg.get("pattern", "")) == RADAR_ARRAY_PATTERN and str(bf_cfg.get("tx_weight_mode", "")) == "custom_complex_weights" else "embedded_sionna_pattern"
        tx_weights = np.ones(1, dtype=np.complex64)
    else:
        tx_mode, tx_weights = array_beamforming_weights(config, "tx", cir_tx_count, override)

    ordered = reorder_cir_for_combining(a, axes)
    rx_combined = np.tensordot(np.conj(rx_weights), ordered, axes=([0], [0]))
    combined = np.tensordot(tx_weights, rx_combined, axes=([0], [0]))
    if combined.ndim == 1:
        path_power = np.abs(combined) ** 2
    else:
        path_power = np.sum(np.abs(combined) ** 2, axis=tuple(range(1, combined.ndim)))
    path_power = path_power.reshape(-1).astype(np.float64)
    noncoherent_power = noncoherent_path_power(a, axes["path_axis"])

    valid = np.asarray(paths["valid"]).reshape(-1).astype(bool) & np.isfinite(tau) & (tau > 1e-10)
    valid_indices = np.flatnonzero(valid)
    obs = observation_arrays(run_dir, valid_indices, tau.size)
    in_gate = obs["in_analysis_gate"] & valid

    ranked = valid_indices[np.argsort(path_power[valid_indices])[::-1]]
    rows = []
    for path_id in ranked[:2000]:
        power = float(path_power[path_id])
        rows.append(
            {
                "path_id": int(path_id),
                "beamformed_power": power,
                "beamformed_power_db": float(10.0 * np.log10(max(power, 1e-300))),
                "noncoherent_power": float(noncoherent_power[path_id]),
                "range_m": float(SPEED_OF_LIGHT * tau[path_id] / 2.0),
                "in_analysis_gate": bool(in_gate[path_id]),
            }
        )

    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    npz_path = analysis_dir / "beamformed_observation.npz"
    np.savez_compressed(
        npz_path,
        beamformed_path_power=path_power.astype(np.float32),
        noncoherent_path_power=noncoherent_power.astype(np.float32),
        rx_weights=rx_weights.astype(np.complex64),
        rx_weight_layout=np.asarray("column-major"),
        tx_weights=tx_weights.astype(np.complex64),
        beamformed_path_coefficients=np.asarray(combined).reshape(tau.size, -1)[:, 0].astype(np.complex64),
    )
    steering_files = build_steering_pattern_artifacts(run_dir, config, mode, rx_weights, axes)
    tx_pattern_files = build_tx_pattern_artifacts(run_dir, config)
    csv_path = analysis_dir / "beamformed_paths.csv"
    write_csv(
        csv_path,
        rows,
        ["path_id", "beamformed_power", "beamformed_power_db", "noncoherent_power", "range_m", "in_analysis_gate"],
    )
    summary = {
        "schema_version": "0.4.0",
        "run_id": run_dir.name,
        "created_at_utc": utc_now(),
        "rx_mode": mode,
        "rx_element_pattern": str(rx_cfg.get("pattern", "iso")),
        "rx_element_factor_included": True,
        "tx_mode": tx_mode,
        "tx_pattern_representation": "equivalent_total_gain_grid" if tx_pattern_name == CUSTOM_GAIN_PATTERN else "element_factor_times_array_factor",
        "tx_element_pattern": tx_element_pattern,
        "tx_element_gain_grid_supplied": bool(tx_cfg.get("element_gain_grid_json")),
        "tx_aperture_embedded_in_sionna_pattern": tx_aperture_embedded,
        "tx_aperture_element_count": requested_tx_count,
        "tx_cir_dimension": cir_tx_count,
        "rx_weight_count": int(rx_weights.size),
        "cir_axes": axes,
        "valid_path_count": int(valid.sum()),
        "analysis_gate_path_count": int(in_gate.sum()),
        "beamformed_power_total": float(np.sum(path_power[valid])),
        "noncoherent_power_total": float(np.sum(noncoherent_power[valid])),
        "top_paths": rows[:20],
        "files": {
            "beamformed_observation": str(npz_path),
            "beamformed_paths": str(csv_path),
            **steering_files,
            **tx_pattern_files,
        },
    }
    json_path = analysis_dir / "beamforming_summary.json"
    write_json(json_path, summary)
    return {"summary": summary, "files": {**summary["files"], "beamforming_summary": str(json_path)}}
