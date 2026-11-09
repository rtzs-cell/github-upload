from pathlib import Path

import numpy as np

from app.core.path_layout import ensure_canonical_path_archive


def test_legacy_real_array_archive_is_upgraded_and_preserved(tmp_path: Path) -> None:
    path_count = 3
    tau = np.ones((1, 2, 1, 1, path_count), dtype=np.float32) * 1.0e-6
    valid = np.ones_like(tau, dtype=bool)
    scalar = np.zeros_like(tau)
    interactions = np.zeros((1, 1, 2, 1, 1, path_count), dtype=np.uint32)
    vertices = np.zeros((1, 1, 2, 1, 1, path_count, 3), dtype=np.float32)
    np.savez_compressed(
        tmp_path / "paths_summary.npz",
        tau_s=tau,
        valid=valid,
        theta_r_rad=scalar,
        phi_r_rad=scalar,
        theta_t_rad=scalar,
        phi_t_rad=scalar,
        doppler_hz=scalar,
        interactions=interactions,
        objects=interactions,
        vertices=vertices,
    )
    np.savez_compressed(
        tmp_path / "cir.npz",
        a=np.zeros((1, 2, 1, 1, path_count, 1), dtype=np.complex64),
        tau_s=tau,
    )

    assert ensure_canonical_path_archive(tmp_path) is True
    assert ensure_canonical_path_archive(tmp_path) is False

    with np.load(tmp_path / "paths_summary.npz", allow_pickle=False) as summary:
        assert summary["tau_s"].shape == (1, 1, path_count)
    with np.load(tmp_path / "paths_per_element.npz", allow_pickle=False) as raw:
        assert raw["tau_s"].shape == (1, 2, 1, 1, path_count)


def test_canonical_archive_accepts_cir_without_delay_array(tmp_path: Path) -> None:
    path_count = 3
    tau = np.asarray([1.0e-6, 2.0e-6, 3.0e-6], dtype=np.float32).reshape(1, 1, path_count)
    np.savez_compressed(
        tmp_path / "paths_summary.npz",
        tau_s=tau,
        valid=np.ones_like(tau, dtype=bool),
    )
    np.savez_compressed(
        tmp_path / "cir.npz",
        a=np.zeros((1, 2, 1, 1, path_count, 1), dtype=np.complex64),
    )

    assert ensure_canonical_path_archive(tmp_path) is False
    assert not (tmp_path / "paths_per_element.npz").exists()
