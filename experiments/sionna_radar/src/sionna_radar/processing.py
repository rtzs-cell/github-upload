from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

SPEED_OF_LIGHT = 299_792_458.0

INTERACTION_NAMES = {
    0: "none",
    1: "specular",
    2: "diffuse",
    4: "refraction",
    8: "diffraction",
}

INVALID_UINT32 = np.uint32(4294967295)


@dataclass
class PathArrays:
    tau_s: np.ndarray
    valid: np.ndarray
    theta_r_rad: np.ndarray
    phi_r_rad: np.ndarray
    theta_t_rad: np.ndarray
    phi_t_rad: np.ndarray
    doppler_hz: np.ndarray
    interactions: np.ndarray
    objects: np.ndarray
    vertices: np.ndarray | None
    a_cir: np.ndarray
    tau_cir_s: np.ndarray


def cir_path_count(a_cir: np.ndarray) -> int:
    values = np.asarray(a_cir)
    if values.ndim < 2:
        raise ValueError(f"CIR array must include path and time axes, got shape {values.shape}")
    return int(values.shape[-2])


def _path_matrix(values: np.ndarray, path_count: int) -> np.ndarray:
    arr = np.asarray(values)
    if arr.size == 0:
        return np.empty((0, path_count), dtype=arr.dtype)
    candidates = [axis for axis, size in enumerate(arr.shape) if size == path_count]
    if not candidates:
        raise ValueError(f"Cannot locate {path_count} path slots in array shape {arr.shape}")
    path_axis = candidates[-1]
    return np.moveaxis(arr, path_axis, -1).reshape(-1, path_count)


def _select_path_values(values: np.ndarray, path_count: int, link_indices: np.ndarray, link_count: int) -> np.ndarray:
    matrix = _path_matrix(values, path_count)
    if matrix.shape[0] == 0:
        return np.empty(path_count, dtype=matrix.dtype)
    if matrix.shape[0] == link_count:
        rows = link_indices
    elif matrix.shape[0] == 1:
        rows = np.zeros(path_count, dtype=np.int64)
    else:
        finite = np.isfinite(matrix) if np.issubdtype(matrix.dtype, np.number) else np.ones(matrix.shape, dtype=bool)
        rows = np.argmax(finite, axis=0)
    return matrix[rows, np.arange(path_count)]


def _select_depth_paths(values: np.ndarray, path_count: int, link_indices: np.ndarray, link_count: int) -> np.ndarray:
    arr = np.asarray(values)
    if arr.size == 0:
        return arr
    candidates = [axis for axis, size in enumerate(arr.shape) if size == path_count]
    if not candidates:
        raise ValueError(f"Cannot locate {path_count} path slots in depth array shape {arr.shape}")
    moved = np.moveaxis(arr, candidates[-1], -1)
    depth = int(moved.shape[0])
    matrix = moved.reshape(depth, -1, path_count)
    rows = link_indices if matrix.shape[1] == link_count else np.zeros(path_count, dtype=np.int64)
    selected = matrix[:, rows, np.arange(path_count)]
    return selected.reshape(depth, 1, 1, path_count)


def _select_path_vertices(values: np.ndarray, path_count: int, link_indices: np.ndarray, link_count: int) -> np.ndarray | None:
    arr = np.asarray(values)
    if arr.size == 0:
        return arr
    if arr.ndim < 2 or arr.shape[-1] != 3:
        raise ValueError(f"Path vertices must end with XYZ coordinates, got shape {arr.shape}")
    candidates = [axis for axis, size in enumerate(arr.shape[:-1]) if size == path_count]
    if not candidates:
        raise ValueError(f"Cannot locate {path_count} path slots in vertex array shape {arr.shape}")
    moved = np.moveaxis(arr, candidates[-1], -2)
    depth = int(moved.shape[0])
    matrix = moved.reshape(depth, -1, path_count, 3)
    rows = link_indices if matrix.shape[1] == link_count else np.zeros(path_count, dtype=np.int64)
    selected = matrix[:, rows, np.arange(path_count), :]
    return selected.reshape(depth, 1, 1, path_count, 3)


def canonicalize_path_arrays(paths: PathArrays) -> tuple[PathArrays, bool]:
    """Collapse per-element path metadata to one representative record per CIR path slot."""
    path_count = cir_path_count(paths.a_cir)
    tau_matrix = _path_matrix(paths.tau_s, path_count)
    valid_matrix = _path_matrix(paths.valid, path_count).astype(bool)
    if tau_matrix.shape != valid_matrix.shape:
        raise ValueError(
            f"Path delay shape {paths.tau_s.shape} and validity shape {paths.valid.shape} are incompatible"
        )
    if tau_matrix.size == path_count:
        return paths, False

    eligible = valid_matrix & np.isfinite(tau_matrix) & (tau_matrix > 0.0)
    link_indices = np.argmax(eligible, axis=0).astype(np.int64)
    valid = np.any(eligible, axis=0)
    link_indices = np.where(valid, link_indices, 0)
    link_count = int(tau_matrix.shape[0])

    def scalar(values: np.ndarray) -> np.ndarray:
        return _select_path_values(values, path_count, link_indices, link_count).reshape(1, 1, path_count)

    canonical = PathArrays(
        tau_s=scalar(paths.tau_s),
        valid=valid.reshape(1, 1, path_count),
        theta_r_rad=scalar(paths.theta_r_rad),
        phi_r_rad=scalar(paths.phi_r_rad),
        theta_t_rad=scalar(paths.theta_t_rad),
        phi_t_rad=scalar(paths.phi_t_rad),
        doppler_hz=scalar(paths.doppler_hz),
        interactions=_select_depth_paths(paths.interactions, path_count, link_indices, link_count),
        objects=_select_depth_paths(paths.objects, path_count, link_indices, link_count),
        vertices=(
            None
            if paths.vertices is None
            else _select_path_vertices(paths.vertices, path_count, link_indices, link_count)
        ),
        a_cir=paths.a_cir,
        tau_cir_s=paths.tau_cir_s,
    )
    return canonical, True


def drjit_to_numpy(value: Any) -> np.ndarray:
    if hasattr(value, "numpy"):
        return value.numpy()
    return np.asarray(value)


def elevation_from_zenith(theta_rad: np.ndarray) -> np.ndarray:
    return 90.0 - np.rad2deg(theta_rad)


def canonical_azimuth_deg(phi_rad: np.ndarray) -> np.ndarray:
    deg = np.rad2deg(phi_rad)
    return (deg + 180.0) % 360.0 - 180.0


def squeeze_path_axis(arr: np.ndarray) -> np.ndarray:
    """Return a flat path vector for synthetic-array [rx, tx, path] tensors."""
    return np.asarray(arr).reshape(-1)


def path_energy_from_cir(a_cir: np.ndarray, path_count: int) -> np.ndarray:
    """Return non-coherent path energy by summing all CIR axes except paths."""
    a = np.asarray(a_cir)
    if a.size == 0 or path_count <= 0:
        return np.array([], dtype=np.float64)
    candidate_axes = [axis for axis, size in enumerate(a.shape) if size == path_count]
    if not candidate_axes:
        return np.array([], dtype=np.float64)
    path_axis = candidate_axes[-1]
    sum_axes = tuple(axis for axis in range(a.ndim) if axis != path_axis)
    return np.sum(np.abs(a) ** 2, axis=sum_axes).reshape(-1).astype(np.float64)


def path_depth(interactions: np.ndarray) -> np.ndarray:
    arr = np.asarray(interactions)
    if arr.ndim < 1:
        return np.array([], dtype=np.int64)
    depth_axis = 0
    valid_inter = arr != 0
    return valid_inter.sum(axis=depth_axis).reshape(-1).astype(np.int64)


def interaction_counts(interactions: np.ndarray) -> dict[str, int]:
    counts: dict[str, int] = {}
    vals = np.asarray(interactions).reshape(-1)
    vals = vals[vals != 0]
    for value in vals:
        name = INTERACTION_NAMES.get(int(value), f"unknown_{int(value)}")
        counts[name] = counts.get(name, 0) + 1
    return counts


def summarize_paths(paths: PathArrays, min_valid_tau_s: float = 1e-10) -> dict[str, Any]:
    tau = squeeze_path_axis(paths.tau_s)
    valid = squeeze_path_axis(paths.valid).astype(bool)
    valid = valid & np.isfinite(tau) & (tau > min_valid_tau_s)
    ranges = SPEED_OF_LIGHT * tau[valid] / 2.0

    theta_r = squeeze_path_axis(paths.theta_r_rad)[valid] if tau.size else np.array([])
    phi_r = squeeze_path_axis(paths.phi_r_rad)[valid] if tau.size else np.array([])
    theta_t = squeeze_path_axis(paths.theta_t_rad)[valid] if tau.size else np.array([])
    phi_t = squeeze_path_axis(paths.phi_t_rad)[valid] if tau.size else np.array([])
    depths_all = path_depth(paths.interactions)
    depths = depths_all[valid] if depths_all.size == valid.size else depths_all
    int_counts = interaction_counts(paths.interactions)

    energy_by_path = None
    if paths.a_cir.size:
        energy_by_path = path_energy_from_cir(paths.a_cir, tau.size)

    dominant_idx = None
    dominant_range_m = None
    if energy_by_path is not None and energy_by_path.size == tau.size and np.any(valid):
        valid_indices = np.flatnonzero(valid)
        dominant_idx = int(valid_indices[np.argmax(energy_by_path[valid])])
        dominant_range_m = float(SPEED_OF_LIGHT * tau[dominant_idx] / 2.0)
    elif ranges.size:
        dominant_idx = int(np.flatnonzero(valid)[0])
        dominant_range_m = float(ranges[0])

    summary: dict[str, Any] = {
        "path_tensor_shape": list(paths.tau_s.shape),
        "cir_shape": list(paths.a_cir.shape),
        "valid_path_count": int(valid.sum()),
        "raw_path_count": int(tau.size),
        "range_min_m": float(np.min(ranges)) if ranges.size else None,
        "range_max_m": float(np.max(ranges)) if ranges.size else None,
        "range_mean_m": float(np.mean(ranges)) if ranges.size else None,
        "dominant_path_index": dominant_idx,
        "dominant_range_m": dominant_range_m,
        "aoa_azimuth_deg_min": float(np.min(canonical_azimuth_deg(phi_r))) if phi_r.size else None,
        "aoa_azimuth_deg_max": float(np.max(canonical_azimuth_deg(phi_r))) if phi_r.size else None,
        "aoa_elevation_deg_min": float(np.min(elevation_from_zenith(theta_r))) if theta_r.size else None,
        "aoa_elevation_deg_max": float(np.max(elevation_from_zenith(theta_r))) if theta_r.size else None,
        "aod_azimuth_deg_min": float(np.min(canonical_azimuth_deg(phi_t))) if phi_t.size else None,
        "aod_azimuth_deg_max": float(np.max(canonical_azimuth_deg(phi_t))) if phi_t.size else None,
        "aod_elevation_deg_min": float(np.min(elevation_from_zenith(theta_t))) if theta_t.size else None,
        "aod_elevation_deg_max": float(np.max(elevation_from_zenith(theta_t))) if theta_t.size else None,
        "max_interaction_depth": int(np.max(depths)) if depths.size else 0,
        "interaction_counts": int_counts,
        "specular_path_count": int(int_counts.get("specular", 0)),
        "diffuse_path_count": int(int_counts.get("diffuse", 0)),
        "doppler_hz_min": float(np.min(paths.doppler_hz)) if paths.doppler_hz.size else None,
        "doppler_hz_max": float(np.max(paths.doppler_hz)) if paths.doppler_hz.size else None,
    }
    return summary


def range_angle_histogram(
    paths: PathArrays,
    rmax_m: float,
    range_bin_m: float,
    angle_bin_deg: float,
    min_valid_tau_s: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    tau = squeeze_path_axis(paths.tau_s)
    valid = squeeze_path_axis(paths.valid).astype(bool)
    valid = valid & np.isfinite(tau) & (tau > min_valid_tau_s)
    ranges = SPEED_OF_LIGHT * tau[valid] / 2.0
    az = canonical_azimuth_deg(squeeze_path_axis(paths.phi_r_rad)[valid])

    if paths.a_cir.size:
        energy = path_energy_from_cir(paths.a_cir, tau.size)
        weights = energy[valid] if energy.size == tau.size else np.ones_like(ranges)
    else:
        weights = np.ones_like(ranges)

    r_edges = np.arange(0.0, rmax_m + range_bin_m, range_bin_m)
    az_edges = np.arange(-180.0, 180.0 + angle_bin_deg, angle_bin_deg)
    hist, r_edges, az_edges = np.histogram2d(ranges, az, bins=[r_edges, az_edges], weights=weights)
    return hist, r_edges, az_edges


def save_basic_figures(run_path: Path, paths: PathArrays, config: dict[str, Any]) -> dict[str, str]:
    figs: dict[str, str] = {}
    fig_dir = run_path / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    tau = squeeze_path_axis(paths.tau_s)
    valid = squeeze_path_axis(paths.valid).astype(bool)
    min_tau = float(config.get("range_processing", {}).get("min_valid_tau_s", 1e-10))
    valid = valid & np.isfinite(tau) & (tau > min_tau)
    ranges = SPEED_OF_LIGHT * tau[valid] / 2.0

    if ranges.size:
        path = fig_dir / "range_histogram.png"
        plt.figure(figsize=(8, 4.5))
        plt.hist(ranges, bins=min(80, max(10, ranges.size)))
        plt.xlabel("Equivalent monostatic range (m)")
        plt.ylabel("Path count")
        plt.title(f"{config['run_id']} range histogram")
        plt.tight_layout()
        plt.savefig(path, dpi=160)
        plt.close()
        figs["range_histogram"] = str(path)

        path = fig_dir / "aoa_range_scatter.png"
        az = canonical_azimuth_deg(squeeze_path_axis(paths.phi_r_rad)[valid])
        el = elevation_from_zenith(squeeze_path_axis(paths.theta_r_rad)[valid])
        plt.figure(figsize=(8, 4.8))
        sc = plt.scatter(az, ranges, c=el, s=18, cmap="viridis")
        plt.colorbar(sc, label="AoA elevation (deg)")
        plt.xlabel("AoA azimuth (deg)")
        plt.ylabel("Equivalent monostatic range (m)")
        plt.title(f"{config['run_id']} path AoA/range")
        plt.tight_layout()
        plt.savefig(path, dpi=160)
        plt.close()
        figs["aoa_range_scatter"] = str(path)

    rp = config.get("range_processing", {})
    hist, r_edges, az_edges = range_angle_histogram(
        paths,
        rmax_m=float(rp.get("rmax_m", 200.0)),
        range_bin_m=float(rp.get("range_bin_m", 0.15)),
        angle_bin_deg=float(rp.get("angle_bin_deg", 2.0)),
        min_valid_tau_s=min_tau,
    )
    if np.any(hist > 0):
        path = fig_dir / "range_azimuth_map.png"
        plt.figure(figsize=(9, 5))
        db = 10.0 * np.log10(hist + 1e-30)
        floor = np.max(db) - 60.0
        db = np.maximum(db, floor)
        extent = [az_edges[0], az_edges[-1], r_edges[-1], r_edges[0]]
        plt.imshow(db, aspect="auto", extent=extent, cmap="magma")
        plt.colorbar(label="Relative power (dB, clipped)")
        plt.xlabel("AoA azimuth (deg)")
        plt.ylabel("Equivalent monostatic range (m)")
        plt.title(f"{config['run_id']} range-azimuth map")
        plt.tight_layout()
        plt.savefig(path, dpi=160)
        plt.close()
        figs["range_azimuth_map"] = str(path)

    return figs
