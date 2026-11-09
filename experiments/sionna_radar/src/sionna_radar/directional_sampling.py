from __future__ import annotations

from contextlib import contextmanager
import importlib
import math
from typing import Any, Iterator

import numpy as np


FULL_SPHERE_MODE = "full_sphere"
ANALYSIS_SECTOR_MODE = "analysis_sector"


def sector_solid_angle_sr(azimuth_width_deg: float, elevation_min_deg: float, elevation_max_deg: float) -> float:
    width_rad = math.radians(float(azimuth_width_deg))
    el_min_rad = math.radians(float(elevation_min_deg))
    el_max_rad = math.radians(float(elevation_max_deg))
    return width_rad * (math.sin(el_max_rad) - math.sin(el_min_rad))


def validate_sampling_config(config: dict[str, Any]) -> dict[str, Any]:
    mode = str(config.get("mode", FULL_SPHERE_MODE))
    if mode not in {FULL_SPHERE_MODE, ANALYSIS_SECTOR_MODE}:
        raise ValueError(f"Unknown initial ray sampling mode: {mode}")
    if mode == FULL_SPHERE_MODE:
        return {
            "mode": mode,
            "solid_angle_sr": 4.0 * math.pi,
            "solid_angle_fraction": 1.0,
            "diffuse_amplitude_correction": 1.0,
        }

    azimuth_width_deg = float(config.get("azimuth_width_deg", 360.0))
    elevation_min_deg = float(config.get("elevation_min_deg", -90.0))
    elevation_max_deg = float(config.get("elevation_max_deg", 90.0))
    if not 0.0 < azimuth_width_deg <= 360.0:
        raise ValueError("Directional azimuth width must be in (0, 360] degrees")
    if not -90.0 <= elevation_min_deg < elevation_max_deg <= 90.0:
        raise ValueError("Directional elevation bounds must satisfy -90 <= min < max <= 90")
    solid_angle = sector_solid_angle_sr(azimuth_width_deg, elevation_min_deg, elevation_max_deg)
    fraction = solid_angle / (4.0 * math.pi)
    return {
        "mode": mode,
        "azimuth_center_deg": float(config.get("azimuth_center_deg", 0.0)),
        "azimuth_width_deg": azimuth_width_deg,
        "elevation_min_deg": elevation_min_deg,
        "elevation_max_deg": elevation_max_deg,
        "solid_angle_sr": solid_angle,
        "solid_angle_fraction": fraction,
        "diffuse_amplitude_correction": math.sqrt(fraction),
    }


def sector_directions(
    num_samples: int,
    azimuth_center_deg: float,
    azimuth_width_deg: float,
    elevation_min_deg: float,
    elevation_max_deg: float,
) -> np.ndarray:
    if num_samples < 1:
        raise ValueError("num_samples must be positive")
    summary = validate_sampling_config(
        {
            "mode": ANALYSIS_SECTOR_MODE,
            "azimuth_center_deg": azimuth_center_deg,
            "azimuth_width_deg": azimuth_width_deg,
            "elevation_min_deg": elevation_min_deg,
            "elevation_max_deg": elevation_max_deg,
        }
    )
    indices = np.arange(num_samples, dtype=np.float64)
    golden_ratio = (1.0 + math.sqrt(5.0)) / 2.0
    az_fraction = np.mod(indices / golden_ratio, 1.0)
    azimuth = math.radians(summary["azimuth_center_deg"] - summary["azimuth_width_deg"] / 2.0)
    azimuth += az_fraction * math.radians(summary["azimuth_width_deg"])

    sin_min = math.sin(math.radians(summary["elevation_min_deg"]))
    sin_max = math.sin(math.radians(summary["elevation_max_deg"]))
    sin_elevation = sin_min + ((indices + 0.5) / num_samples) * (sin_max - sin_min)
    elevation = np.arcsin(np.clip(sin_elevation, -1.0, 1.0))
    cos_elevation = np.cos(elevation)
    return np.column_stack(
        (
            cos_elevation * np.cos(azimuth),
            cos_elevation * np.sin(azimuth),
            np.sin(elevation),
        )
    ).astype(np.float32)


@contextmanager
def initial_ray_sampling(config: dict[str, Any]) -> Iterator[dict[str, Any]]:
    summary = validate_sampling_config(config)
    if summary["mode"] == FULL_SPHERE_MODE:
        yield summary
        return

    candidate_module = importlib.import_module("sionna.rt.path_solvers.sb_candidate_generator")
    original_spawn = candidate_module.spawn_ray_from_sources

    def spawn_sector_rays(_lattice: Any, samples_per_src: int, src_positions: Any) -> Any:
        import drjit as dr
        import mitsuba as mi

        directions = sector_directions(
            samples_per_src,
            summary["azimuth_center_deg"],
            summary["azimuth_width_deg"],
            summary["elevation_min_deg"],
            summary["elevation_max_deg"],
        )
        k_world = mi.Vector3f(directions[:, 0], directions[:, 1], directions[:, 2])
        num_sources = dr.shape(src_positions)[1]
        k_world = dr.tile(k_world, num_sources)
        origins = dr.repeat(src_positions, samples_per_src)
        ray = mi.Ray3f(o=origins, d=k_world)
        ray.time = dr.zeros(mi.Float, dr.width(k_world))
        return ray

    candidate_module.spawn_ray_from_sources = spawn_sector_rays
    try:
        yield summary
    finally:
        candidate_module.spawn_ray_from_sources = original_spawn


def correct_diffuse_cir_amplitudes(
    a_cir: np.ndarray,
    interactions: np.ndarray,
    path_count: int,
    sampling_summary: dict[str, Any],
) -> np.ndarray:
    values = np.asarray(a_cir)
    if sampling_summary.get("mode") != ANALYSIS_SECTOR_MODE or values.size == 0 or path_count < 1:
        return values
    candidate_axes = [axis for axis, size in enumerate(values.shape) if size == path_count]
    if not candidate_axes:
        raise ValueError(f"Cannot locate path axis in CIR shape {values.shape} for {path_count} paths")
    path_axis = candidate_axes[-1]
    interaction_values = np.asarray(interactions).reshape(-1, path_count)
    has_diffuse = np.any(interaction_values == 2, axis=0)
    correction = float(sampling_summary["diffuse_amplitude_correction"])
    scale_dtype = values.real.dtype if np.issubdtype(values.dtype, np.complexfloating) else values.dtype
    path_scale = np.where(has_diffuse, correction, 1.0).astype(scale_dtype, copy=False)
    broadcast_shape = [1] * values.ndim
    broadcast_shape[path_axis] = path_count
    return np.asarray(values * path_scale.reshape(broadcast_shape), dtype=values.dtype)
