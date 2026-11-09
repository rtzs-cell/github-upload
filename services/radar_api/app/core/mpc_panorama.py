from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.spatial.transform import Rotation


IMAGE_SCALE = 3
APERTURE_ROWS = 8
APERTURE_COLS = 8
SPACING_LAMBDA = 0.5
DYNAMIC_RANGE_DB = 40.0
PEAK_PERCENTILE = 99.5
VIEW_AZIMUTHS_DEG = (0, 90, 180, -90)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def beamwidth_sigma_pixels(elements: int) -> float:
    hpbw_rad = 0.886 / max(elements * SPACING_LAMBDA, 1e-6)
    return max(np.rad2deg(hpbw_rad) / 2.3548200450309493 * IMAGE_SCALE, 0.5)


def first_element_path_data(run_dir: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with np.load(run_dir / "paths_summary.npz", allow_pickle=False) as paths:
        valid = np.asarray(paths["valid"]).reshape(-1).astype(bool)
        theta_deg = np.rad2deg(np.asarray(paths["theta_r_rad"]).reshape(-1))
        phi_deg = np.rad2deg(np.asarray(paths["phi_r_rad"]).reshape(-1))
    with np.load(run_dir / "cir.npz", allow_pickle=False) as cir:
        coefficients = np.asarray(cir["a"])
        if coefficients.ndim == 6:
            amplitudes = np.abs(coefficients[0, 0, 0, 0, :, 0])
        elif coefficients.ndim == 5:
            amplitudes = np.abs(coefficients[0, 0, 0, 0, :])
        else:
            raise ValueError(f"Unsupported CIR coefficient shape: {coefficients.shape}")
    count = min(valid.size, theta_deg.size, phi_deg.size, amplitudes.size)
    keep = valid[:count] & np.isfinite(theta_deg[:count]) & np.isfinite(phi_deg[:count]) & np.isfinite(amplitudes[:count]) & (amplitudes[:count] > 0)
    return theta_deg[:count][keep], phi_deg[:count][keep], amplitudes[:count][keep].astype(np.float64)


def render_raw_panorama(theta_deg: np.ndarray, phi_deg: np.ndarray, amplitudes: np.ndarray) -> tuple[np.ndarray, dict[str, float]]:
    n_phi = 360 * IMAGE_SCALE
    n_theta = 180 * IMAGE_SCALE
    impulses = np.zeros((n_phi, n_theta), dtype=np.float64)
    phi_idx = np.trunc(-phi_deg + 180.0).astype(np.int64) * IMAGE_SCALE
    theta_idx = np.trunc(theta_deg).astype(np.int64) * IMAGE_SCALE
    inside = (phi_idx >= 0) & (phi_idx < n_phi) & (theta_idx >= 0) & (theta_idx < n_theta)
    np.add.at(impulses, (phi_idx[inside], theta_idx[inside]), amplitudes[inside])
    sigma_phi = beamwidth_sigma_pixels(APERTURE_COLS)
    sigma_theta = beamwidth_sigma_pixels(APERTURE_ROWS)
    radius_phi = (int(3.0 * sigma_phi) | 1) // 2
    radius_theta = (int(3.0 * sigma_theta) | 1) // 2
    linear = gaussian_filter(
        impulses,
        sigma=(sigma_phi, sigma_theta),
        mode=("constant", "constant"),
        radius=(radius_phi, radius_theta),
    )
    nonzero = linear > 0
    raw_db = np.full_like(linear, -100.0, dtype=np.float64)
    if np.any(nonzero):
        raw_db[nonzero] = 10.0 * np.log10(linear[nonzero])
        raw_db[~nonzero] = float(np.min(raw_db[nonzero]) - 10.0)
    return raw_db.T.astype(np.float32), {
        "azimuth_sigma_px": sigma_phi,
        "zenith_sigma_px": sigma_theta,
        "azimuth_radius_px": radius_phi,
        "zenith_radius_px": radius_theta,
    }


def normalize_panorama(raw_db: np.ndarray) -> tuple[np.ndarray, float, float]:
    upper = float(np.percentile(raw_db, PEAK_PERCENTILE))
    lower = upper - DYNAMIC_RANGE_DB
    normalized = np.clip((raw_db - lower) / max(upper - lower, 1e-12), 0.0, 1.0)
    return normalized.astype(np.float32), lower, upper


def perspective_view(rgb: np.ndarray, azimuth_deg: float, fov_deg: float = 90.0, height: int = 200, width: int = 300) -> np.ndarray:
    focal = 0.5 * width / np.tan(0.5 * np.deg2rad(fov_deg))
    x, y = np.meshgrid(np.arange(width), np.arange(height))
    vectors = np.stack(((x - (width - 1) / 2.0) / focal, (y - (height - 1) / 2.0) / focal, np.ones_like(x)), axis=-1)
    first = Rotation.from_rotvec(np.array([0.0, 1.0, 0.0]) * np.deg2rad(-azimuth_deg))
    axis = first.apply(np.array([1.0, 0.0, 0.0]))
    rotation = Rotation.from_rotvec(axis * 0.0) * first
    vectors = rotation.apply(vectors.reshape(-1, 3)).reshape(height, width, 3)
    vectors /= np.linalg.norm(vectors, axis=-1, keepdims=True)
    longitude = np.arctan2(vectors[..., 0], vectors[..., 2])
    latitude = np.arcsin(vectors[..., 1])
    map_x = (longitude / (2.0 * np.pi) + 0.5) * (rgb.shape[1] - 1)
    map_y = (latitude / np.pi + 0.5) * (rgb.shape[0] - 1)
    channels = [map_coordinates(rgb[..., index], [map_y, map_x], order=3, mode="wrap") for index in range(3)]
    return np.clip(np.stack(channels, axis=-1), 0, 255).astype(np.uint8)


def build_mpc_panorama_artifacts(run_dir: Path) -> dict[str, Any]:
    analysis_dir = run_dir / "analysis"
    figures_dir = run_dir / "figures"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    theta, phi, amplitudes = first_element_path_data(run_dir)
    raw_db, kernel = render_raw_panorama(theta, phi, amplitudes)
    normalized, lower_db, upper_db = normalize_panorama(raw_db)
    rgb = (plt.get_cmap("jet")(normalized)[..., :3] * 255.0).astype(np.uint8)

    array_path = analysis_dir / "mpc_panorama.npz"
    panorama_path = figures_dir / "mpc_panorama.png"
    summary_path = analysis_dir / "mpc_panorama_summary.json"
    np.savez_compressed(
        array_path,
        raw_db=raw_db,
        normalized=normalized,
        azimuth_deg=np.linspace(-180.0, 180.0, raw_db.shape[1], endpoint=False, dtype=np.float32),
        zenith_deg=np.linspace(0.0, 180.0, raw_db.shape[0], endpoint=False, dtype=np.float32),
    )
    Image.fromarray(rgb).save(panorama_path)
    view_files: dict[str, str] = {}
    for label, azimuth in zip(("front", "right", "back", "left"), VIEW_AZIMUTHS_DEG):
        path = figures_dir / f"mpc_view_{label}.png"
        Image.fromarray(perspective_view(rgb, azimuth)).save(path)
        view_files[label] = str(path)

    summary = {
        "schema_version": "1.2.0",
        "created_at_utc": utc_now(),
        "run_id": run_dir.name,
        "definition": "AoA equirectangular MPC spectrum",
        "path_count": int(amplitudes.size),
        "coefficient_selection": "rx=0, rx_ant=0, tx=0, tx_ant=0",
        "path_weight": "abs(a_p)",
        "db_transform": "10*log10(smoothed amplitude)",
        "pixel_mapping": {"x": "(180-phi_deg)*3", "y": "theta_deg*3", "theta_convention": "zenith angle"},
        "panorama_shape": list(raw_db.shape),
        "kernel": {
            "type": "aperture_hpbw_gaussian",
            "rows": APERTURE_ROWS,
            "cols": APERTURE_COLS,
            "spacing_lambda": SPACING_LAMBDA,
            "window": "rect",
            **kernel,
        },
        "normalization": {
            "mode": "per_panorama_peak_dynamic_range",
            "peak_percentile": PEAK_PERCENTILE,
            "dynamic_range_db": DYNAMIC_RANGE_DB,
            "lower_db": lower_db,
            "upper_db": upper_db,
        },
        "perspective_views": {"fov_deg": 90.0, "width": 300, "height": 200, "azimuth_deg": dict(zip(("front", "right", "back", "left"), VIEW_AZIMUTHS_DEG))},
        "files": {"mpc_panorama_array": str(array_path), "mpc_panorama": str(panorama_path), "mpc_panorama_summary": str(summary_path), **{f"mpc_view_{key}": value for key, value in view_files.items()}},
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return {"summary": summary, "files": summary["files"]}
