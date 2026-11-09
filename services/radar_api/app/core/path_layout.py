from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4

import numpy as np

from sionna_radar.processing import PathArrays, canonicalize_path_arrays


def _save_path_metadata(path: Path, arrays: PathArrays) -> None:
    with path.open("wb") as f:
        np.savez_compressed(
            f,
            tau_s=arrays.tau_s,
            valid=arrays.valid,
            theta_r_rad=arrays.theta_r_rad,
            phi_r_rad=arrays.phi_r_rad,
            theta_t_rad=arrays.theta_t_rad,
            phi_t_rad=arrays.phi_t_rad,
            doppler_hz=arrays.doppler_hz,
            interactions=arrays.interactions,
            objects=arrays.objects,
            vertices=np.array([]) if arrays.vertices is None else arrays.vertices,
        )


def ensure_canonical_path_archive(run_dir: Path) -> bool:
    """Upgrade legacy per-element path summaries while retaining their raw metadata."""
    summary_path = run_dir / "paths_summary.npz"
    cir_path = run_dir / "cir.npz"
    if not summary_path.is_file() or not cir_path.is_file():
        return False

    with np.load(summary_path, allow_pickle=False) as paths, np.load(cir_path, allow_pickle=False) as cir:
        tau_s = np.asarray(paths["tau_s"])

        def path_values(name: str, fill_value: float = np.nan) -> np.ndarray:
            if name in paths.files:
                return np.asarray(paths[name])
            return np.full(tau_s.shape, fill_value, dtype=np.float32)

        arrays = PathArrays(
            tau_s=tau_s,
            valid=np.asarray(paths["valid"]),
            theta_r_rad=path_values("theta_r_rad"),
            phi_r_rad=path_values("phi_r_rad"),
            theta_t_rad=path_values("theta_t_rad"),
            phi_t_rad=path_values("phi_t_rad"),
            doppler_hz=path_values("doppler_hz", 0.0),
            interactions=(
                np.asarray(paths["interactions"])
                if "interactions" in paths.files
                else np.zeros((0, *tau_s.shape), dtype=np.uint32)
            ),
            objects=(
                np.asarray(paths["objects"])
                if "objects" in paths.files
                else np.zeros((0, *tau_s.shape), dtype=np.uint32)
            ),
            vertices=np.asarray(paths["vertices"]) if "vertices" in paths.files else None,
            a_cir=np.asarray(cir["a"]),
            tau_cir_s=np.asarray(cir["tau_s"]) if "tau_s" in cir.files else tau_s,
        )
    canonical, changed = canonicalize_path_arrays(arrays)
    if not changed:
        return False

    per_element_path = run_dir / "paths_per_element.npz"
    if not per_element_path.exists():
        shutil.copy2(summary_path, per_element_path)
    temporary = run_dir / f".paths_summary.{uuid4().hex}.npz"
    try:
        _save_path_metadata(temporary, canonical)
        os.replace(temporary, summary_path)
    finally:
        temporary.unlink(missing_ok=True)
    return True
