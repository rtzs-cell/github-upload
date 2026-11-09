import math

import numpy as np

from app.bootstrap import ensure_repo_imports
from app.config import get_settings
from app.workers.job_store import JobStore
from app.workers.simulation_worker import SimulationWorker

ensure_repo_imports()

from sionna_radar.directional_sampling import (  # noqa: E402
    correct_diffuse_cir_amplitudes,
    sector_directions,
    sector_solid_angle_sr,
    validate_sampling_config,
)


def test_sector_directions_are_unit_vectors_inside_gate() -> None:
    directions = sector_directions(2000, 30.0, 80.0, -5.0, 25.0)
    azimuth = np.rad2deg(np.arctan2(directions[:, 1], directions[:, 0]))
    elevation = np.rad2deg(np.arcsin(directions[:, 2]))
    delta = (azimuth - 30.0 + 180.0) % 360.0 - 180.0

    assert np.allclose(np.linalg.norm(directions, axis=1), 1.0, atol=1e-6)
    assert float(np.min(delta)) >= -40.0
    assert float(np.max(delta)) <= 40.0
    assert float(np.min(elevation)) >= -5.0
    assert float(np.max(elevation)) <= 25.0


def test_sector_summary_uses_spherical_solid_angle() -> None:
    summary = validate_sampling_config(
        {
            "mode": "analysis_sector",
            "azimuth_center_deg": 0.0,
            "azimuth_width_deg": 120.0,
            "elevation_min_deg": 0.0,
            "elevation_max_deg": 40.0,
        }
    )
    expected = math.radians(120.0) * math.sin(math.radians(40.0))
    assert math.isclose(sector_solid_angle_sr(120.0, 0.0, 40.0), expected)
    assert math.isclose(summary["solid_angle_sr"], expected)
    assert math.isclose(summary["diffuse_amplitude_correction"] ** 2, expected / (4.0 * math.pi))


def test_directional_sampling_only_rescales_diffuse_paths() -> None:
    a = np.ones((1, 2, 1, 1, 3, 1), dtype=np.complex64)
    interactions = np.asarray([[1, 2, 1], [0, 0, 2]], dtype=np.int64)
    summary = {
        "mode": "analysis_sector",
        "diffuse_amplitude_correction": 0.25,
    }
    corrected = correct_diffuse_cir_amplitudes(a, interactions, 3, summary)

    assert corrected.dtype == np.complex64
    assert np.allclose(corrected[..., 0, :], 1.0)
    assert np.allclose(corrected[..., 1, :], 0.25)
    assert np.allclose(corrected[..., 2, :], 0.25)


def test_worker_resolves_analysis_sector_from_radar_pose() -> None:
    settings = get_settings()
    worker = SimulationWorker(settings, JobStore(settings))
    request = {
        "scene_id": "two_buildings.xml",
        "source_experiment_id": "exp_source",
        "radar": {
            "center_m": [0.0, 0.0, 10.0],
            "look_at_m": [100.0, 0.0, 20.0],
            "tx_rx_baseline_m": 0.1,
            "az_width_deg": 60.0,
            "el_min_deg": -2.0,
            "el_max_deg": 18.0,
            "rmax_m": 500.0,
        },
        "propagation": {"frequency_hz": 28e9, "bandwidth_hz": 1e9},
        "path_solver": {
            "max_depth": 2,
            "samples_per_src": 1000,
            "seed": 7,
            "initial_ray_sampling": {"mode": "analysis_sector"},
            "synthetic_array": False,
        },
        "compute": {"samples_per_src": 1000, "seed": 7},
        "scattering": {"enabled": False},
        "tx_array": {"num_rows": 1, "num_cols": 1, "pattern": "iso", "polarization": "V"},
        "rx_array": {"num_rows": 1, "num_cols": 1, "pattern": "iso", "polarization": "V"},
        "observation": {},
    }
    config = worker.build_run_config(request, "job_test")
    sampling = config["path_solver"]["initial_ray_sampling"]

    assert sampling == {
        "mode": "analysis_sector",
        "azimuth_center_deg": 0.0,
        "azimuth_width_deg": 60.0,
        "elevation_min_deg": -2.0,
        "elevation_max_deg": 18.0,
    }
    assert config["workbench"]["source_experiment_id"] == "exp_source"
    assert config["path_solver"]["synthetic_array"] is False
