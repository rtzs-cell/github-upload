from pathlib import Path

import numpy as np
import yaml

from app.core.radar_signal import SPEED_OF_LIGHT, build_fmcw_artifacts


def test_fmcw_peak_matches_path_range_and_doppler(tmp_path: Path) -> None:
    target_range_m = 25.0
    target_velocity_mps = 2.0
    carrier_hz = 77e9
    wavelength = SPEED_OF_LIGHT / carrier_hz
    doppler_hz = 2.0 * target_velocity_mps / wavelength
    config = {
        "frequency_hz": carrier_hz,
        "bandwidth_hz": 150e6,
        "tx_power_dbm": 30.0,
        "range_processing": {"rmax_m": 100.0},
        "path_solver": {"seed": 7},
        "waveform": {
            "bandwidth_hz": 150e6,
            "chirp_duration_s": 50e-6,
            "idle_time_s": 10e-6,
            "num_chirps": 32,
            "adc_samples": 256,
        },
        "receiver": {"temperature_k": 0.0, "noise_figure_db": 0.0},
        "radar_processing": {"max_synthesis_paths": 1, "cfar_pfa": 1e-5},
    }
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    np.savez_compressed(
        tmp_path / "paths_summary.npz",
        tau_s=np.asarray([2.0 * target_range_m / SPEED_OF_LIGHT, 2.0 * 40.0 / SPEED_OF_LIGHT], dtype=np.float64).reshape(1, 1, 2),
        doppler_hz=np.asarray([doppler_hz, 0.0], dtype=np.float64).reshape(1, 1, 2),
        valid=np.asarray([True, True]).reshape(1, 1, 2),
    )
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    np.savez_compressed(
        analysis_dir / "beamformed_observation.npz",
        beamformed_path_coefficients=np.asarray([1e-4 + 0j, 2e-5 + 1e-5j], dtype=np.complex64),
    )

    result = build_fmcw_artifacts(tmp_path)
    data = np.load(result["files"]["range_doppler"], allow_pickle=False)
    spectrum = data["range_doppler_power"]
    peak = np.unravel_index(int(np.argmax(spectrum)), spectrum.shape)
    measured_range = float(data["range_axis_m"][peak[1]])
    measured_velocity = float(data["velocity_axis_mps"][peak[0]])

    assert abs(measured_range - target_range_m) <= result["summary"]["range_resolution_m"]
    assert abs(measured_velocity - target_velocity_mps) <= result["summary"]["velocity_resolution_mps"]
    assert result["summary"]["synthesized_path_power_fraction"] == 1.0
    assert result["summary"]["exact_time_domain_path_count"] == 1
    assert result["summary"]["fft_gridded_path_count"] == 1
    assert result["summary"]["cfar"]["detection_count"] >= 1
