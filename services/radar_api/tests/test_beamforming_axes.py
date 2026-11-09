from pathlib import Path
import sys

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SIONNA_SRC = REPO_ROOT / "experiments" / "sionna_radar" / "src"
if str(SIONNA_SRC) not in sys.path:
    sys.path.insert(0, str(SIONNA_SRC))

from app.core.beamforming import (
    build_beamforming_artifacts,
    infer_cir_axes,
    steering_pattern,
    steering_weights,
)


def write_minimal_run(run_dir: Path, a: np.ndarray) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "rx_array": {"num_rows": 1, "num_cols": 2, "horizontal_spacing": 0.5, "vertical_spacing": 0.5},
        "tx_array": {"num_rows": 1, "num_cols": 1, "horizontal_spacing": 0.5, "vertical_spacing": 0.5},
    }
    (run_dir / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    np.savez_compressed(run_dir / "cir.npz", a=a)
    np.savez_compressed(
        run_dir / "paths_summary.npz",
        tau_s=np.asarray([1.0e-6, 2.0e-6, 3.0e-6], dtype=np.float32).reshape(1, 1, 3),
        valid=np.asarray([True, True, True]).reshape(1, 1, 3),
    )
    np.savez_compressed(
        run_dir / "radar_observation.npz",
        path_energy=np.asarray([2.0, 2.0, 4.0], dtype=np.float32),
        fov_path_mask=np.asarray([True, False, True]),
    )


def test_infer_cir_axes_for_legacy_shape() -> None:
    a = np.zeros((1, 2, 1, 1, 3, 1), dtype=np.complex64)
    axes = infer_cir_axes(a, path_count=3, rx_count=2, tx_count=1)
    assert axes == {"path_axis": 4, "rx_axis": 1, "tx_axis": 3}


def test_infer_cir_axes_for_worker_shape() -> None:
    a = np.zeros((1, 1, 2, 1, 1, 3, 1), dtype=np.complex64)
    axes = infer_cir_axes(a, path_count=3, rx_count=2, tx_count=1)
    assert axes == {"path_axis": 5, "rx_axis": 2, "tx_axis": 4}


def test_rx_steering_weights_use_sionna_column_major_order() -> None:
    rows = 2
    cols = 3
    spacing_y = 0.4
    spacing_z = 0.6
    az_deg = 23.0
    el_deg = -11.0

    weights = steering_weights(rows, cols, az_deg, el_deg, spacing_y, spacing_z)

    col_idx = np.arange(cols, dtype=np.float32) - (cols - 1) / 2.0
    row_idx = (rows - 1) / 2.0 - np.arange(rows, dtype=np.float32)
    yy, zz = np.meshgrid(col_idx * spacing_y, row_idx * spacing_z)
    az = np.deg2rad(az_deg)
    el = np.deg2rad(el_deg)
    phase = 2.0 * np.pi * (yy * np.sin(az) * np.cos(el) + zz * np.sin(el))
    expected = np.exp(1j * phase).reshape(-1, order="F").astype(np.complex64)
    expected /= np.linalg.norm(expected)
    row_major = np.exp(1j * phase).reshape(-1).astype(np.complex64) / np.sqrt(rows * cols)

    np.testing.assert_allclose(weights, expected, atol=1e-6)
    assert not np.allclose(weights, row_major)


def test_rx_pattern_uses_same_column_major_weight_order() -> None:
    rows = 2
    cols = 3
    az_deg = 17.0
    el_deg = 9.0
    weights = steering_weights(rows, cols, az_deg, el_deg, 0.5, 0.5)

    az_grid, el_grid, gain = steering_pattern(
        rows,
        cols,
        weights,
        0.5,
        0.5,
        azimuth_grid_deg=np.asarray([az_deg - 1.0, az_deg, az_deg + 1.0]),
        elevation_grid_deg=np.asarray([el_deg - 1.0, el_deg, el_deg + 1.0]),
    )

    peak = np.unravel_index(int(np.argmax(gain)), gain.shape)
    assert az_grid[peak[1]] == az_deg
    assert el_grid[peak[0]] == el_deg


def test_beamforming_power_from_legacy_shape(tmp_path: Path) -> None:
    a = np.zeros((1, 2, 1, 1, 3, 1), dtype=np.complex64)
    a[0, :, 0, 0, 0, 0] = [1.0 + 0j, 1.0 + 0j]
    a[0, :, 0, 0, 1, 0] = [1.0 + 0j, -1.0 + 0j]
    a[0, :, 0, 0, 2, 0] = [2.0 + 0j, 0.0 + 0j]
    write_minimal_run(tmp_path, a)

    result = build_beamforming_artifacts(tmp_path, {"rx_mode": "uniform"})
    data = np.load(result["files"]["beamformed_observation"], allow_pickle=False)

    np.testing.assert_allclose(data["beamformed_path_power"], [2.0, 0.0, 2.0], atol=1e-6)
    assert data["rx_weight_layout"].item() == "column-major"


def test_beamforming_power_from_worker_shape(tmp_path: Path) -> None:
    a = np.zeros((1, 1, 2, 1, 1, 3, 1), dtype=np.complex64)
    a[0, 0, :, 0, 0, 0, 0] = [1.0 + 0j, 1.0 + 0j]
    a[0, 0, :, 0, 0, 1, 0] = [1.0 + 0j, -1.0 + 0j]
    a[0, 0, :, 0, 0, 2, 0] = [2.0 + 0j, 0.0 + 0j]
    write_minimal_run(tmp_path, a)

    result = build_beamforming_artifacts(tmp_path, {"rx_mode": "uniform"})
    data = np.load(result["files"]["beamformed_observation"], allow_pickle=False)

    np.testing.assert_allclose(data["beamformed_path_power"], [2.0, 0.0, 2.0], atol=1e-6)


def test_tx_combining_uses_w_not_conjugate_w(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    config = {
        "rx_array": {"num_rows": 1, "num_cols": 1, "horizontal_spacing": 0.5, "vertical_spacing": 0.5},
        "tx_array": {"num_rows": 1, "num_cols": 2, "horizontal_spacing": 0.5, "vertical_spacing": 0.5},
        "beamforming": {
            "rx_mode": "uniform",
            "tx_mode": "custom_complex_weights",
            "tx_custom_weights_json": '[[1, 0], [0, 1]]',
        },
    }
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    a = np.zeros((1, 1, 1, 2, 2, 1), dtype=np.complex64)
    a[0, 0, 0, :, 0, 0] = [1.0 + 0j, 0.0 + 1j]
    a[0, 0, 0, :, 1, 0] = [1.0 + 0j, 0.0 - 1j]
    np.savez_compressed(tmp_path / "cir.npz", a=a)
    np.savez_compressed(
        tmp_path / "paths_summary.npz",
        tau_s=np.asarray([1e-6, 2e-6], dtype=np.float32).reshape(1, 1, 2),
        valid=np.asarray([True, True]).reshape(1, 1, 2),
    )
    np.savez_compressed(
        tmp_path / "radar_observation.npz",
        path_energy=np.ones(2, dtype=np.float32),
        fov_path_mask=np.ones(2, dtype=bool),
    )

    result = build_beamforming_artifacts(tmp_path)
    data = np.load(result["files"]["beamformed_observation"], allow_pickle=False)
    np.testing.assert_allclose(data["beamformed_path_power"], [0.0, 2.0], atol=1e-6)
