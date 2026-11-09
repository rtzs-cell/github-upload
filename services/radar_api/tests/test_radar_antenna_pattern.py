from pathlib import Path
import sys

import numpy as np
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SIONNA_SRC = REPO_ROOT / "experiments" / "sionna_radar" / "src"
if str(SIONNA_SRC) not in sys.path:
    sys.path.insert(0, str(SIONNA_SRC))

from sionna_radar.antenna_patterns import CUSTOM_GAIN_PATTERN, RADAR_ARRAY_PATTERN, numpy_custom_gain_field, numpy_radar_array_field, parse_complex_weights, parse_custom_gain_grid
from sionna_radar.runner import configure_arrays
from app.core.beamforming import build_tx_pattern_artifacts
from app.schemas import ArrayConfig


class RecordingPlanarArray:
    def __init__(self, *, num_rows: int, num_cols: int, pattern: str, **kwargs) -> None:
        self.array_size = num_rows * num_cols
        self.normalized_positions = np.zeros((self.array_size, 3), dtype=np.float64)
        self.pattern = pattern
        self.pattern_kwargs = kwargs


class ArrayScene:
    tx_array: RecordingPlanarArray
    rx_array: RecordingPlanarArray


def test_array_config_validates_custom_element_grid_fields() -> None:
    gain_grid_json = """{
        "azimuth_deg": [-10, 10],
        "elevation_deg": [-5, 5],
        "gain_db": [[0, -3], [-6, -9]]
    }"""
    tx = ArrayConfig(
        num_rows=2,
        num_cols=2,
        pattern=RADAR_ARRAY_PATTERN,
        element_pattern=CUSTOM_GAIN_PATTERN,
        element_gain_grid_json=gain_grid_json,
    )
    rx = ArrayConfig(
        num_rows=4,
        num_cols=4,
        pattern=CUSTOM_GAIN_PATTERN,
        gain_grid_json=gain_grid_json,
    )
    assert tx.element_pattern == CUSTOM_GAIN_PATTERN
    assert rx.pattern == CUSTOM_GAIN_PATTERN

    with pytest.raises(ValueError, match="element_gain_grid_json"):
        ArrayConfig(num_rows=2, num_cols=2, pattern=RADAR_ARRAY_PATTERN, element_pattern=CUSTOM_GAIN_PATTERN)


def test_radar_array_pattern_peaks_at_steering_direction() -> None:
    az = np.linspace(-40.0, 40.0, 321)
    el = np.zeros_like(az)
    field = numpy_radar_array_field(
        az,
        el,
        rows=8,
        cols=8,
        steering_azimuth_deg=12.0,
        steering_elevation_deg=0.0,
    )
    peak_az = float(az[int(np.argmax(np.abs(field) ** 2))])
    assert abs(peak_az - 12.0) <= 0.5


def test_hann_taper_reduces_far_sidelobe() -> None:
    az = np.asarray([0.0, 25.0])
    el = np.zeros_like(az)
    uniform = np.abs(numpy_radar_array_field(az, el, rows=8, cols=16, taper="uniform")) ** 2
    hann = np.abs(numpy_radar_array_field(az, el, rows=8, cols=16, taper="hann")) ** 2
    assert hann[1] / hann[0] < uniform[1] / uniform[0]


def test_custom_gain_grid_interpolates_db_values() -> None:
    raw = {
        "azimuth_deg": [-10.0, 0.0, 10.0],
        "elevation_deg": [-10.0, 0.0, 10.0],
        "gain_db": [[-20.0, -10.0, -20.0], [-10.0, 10.0, -10.0], [-20.0, -10.0, -20.0]],
        "outside_gain_db": -60.0,
    }
    grid = parse_custom_gain_grid(raw)
    assert grid["gain_db"].shape == (3, 3)
    field = numpy_custom_gain_field(np.asarray([0.0, 5.0, 40.0]), np.asarray([0.0, 0.0, 0.0]), raw)
    gain_db = 20.0 * np.log10(np.maximum(np.abs(field), 1e-12))
    assert np.allclose(gain_db, [10.0, 0.0, -60.0])


def test_configure_radar_array_does_not_forward_gain_grid_json() -> None:
    scene = ArrayScene()
    config = {
        "tx_array": {
            "num_rows": 2,
            "num_cols": 3,
            "vertical_spacing": 0.5,
            "horizontal_spacing": 0.5,
            "pattern": RADAR_ARRAY_PATTERN,
            "polarization": "V",
            "gain_grid_json": None,
        },
        "rx_array": {
            "num_rows": 1,
            "num_cols": 1,
            "pattern": "iso",
            "polarization": "V",
            "gain_grid_json": None,
            "element_pattern": None,
            "element_gain_grid_json": None,
        },
        "beamforming": {},
    }

    summary = configure_arrays(scene, config, {"PlanarArray": RecordingPlanarArray})

    assert "gain_grid_json" not in scene.tx_array.pattern_kwargs
    assert "gain_grid_json" not in scene.rx_array.pattern_kwargs
    assert "element_pattern" not in scene.rx_array.pattern_kwargs
    assert "element_gain_grid_json" not in scene.rx_array.pattern_kwargs
    assert summary["tx_array_size"] == 1
    assert summary["tx_aperture_size"] == 6


def test_configure_custom_gain_array_forwards_gain_grid_to_pattern() -> None:
    scene = ArrayScene()
    gain_grid_json = """{
        "azimuth_deg": [-10, 10],
        "elevation_deg": [-5, 5],
        "gain_db": [[0, -3], [-6, -9]]
    }"""
    config = {
        "tx_array": {
            "num_rows": 2,
            "num_cols": 2,
            "pattern": CUSTOM_GAIN_PATTERN,
            "polarization": "V",
            "gain_grid_json": gain_grid_json,
        },
        "rx_array": {"num_rows": 1, "num_cols": 1, "pattern": "iso", "polarization": "V", "gain_grid_json": None},
    }

    summary = configure_arrays(scene, config, {"PlanarArray": RecordingPlanarArray})

    assert scene.tx_array.pattern_kwargs["gain_grid_json"] == gain_grid_json
    assert summary["tx_array_size"] == 1
    assert summary["tx_aperture_size"] == 4


def test_configure_custom_rx_element_factor_preserves_array_dimensions() -> None:
    scene = ArrayScene()
    gain_grid_json = """{
        "azimuth_deg": [-10, 10],
        "elevation_deg": [-5, 5],
        "gain_db": [[0, -3], [-6, -9]]
    }"""
    config = {
        "tx_array": {"num_rows": 1, "num_cols": 1, "pattern": "iso", "polarization": "V"},
        "rx_array": {
            "num_rows": 4,
            "num_cols": 8,
            "pattern": CUSTOM_GAIN_PATTERN,
            "polarization": "V",
            "gain_grid_json": gain_grid_json,
        },
    }

    summary = configure_arrays(scene, config, {"PlanarArray": RecordingPlanarArray})

    assert scene.rx_array.pattern_kwargs["gain_grid_json"] == gain_grid_json
    assert summary["rx_array_size"] == 32


def test_configure_radar_array_forwards_custom_tx_element_factor() -> None:
    scene = ArrayScene()
    gain_grid_json = """{
        "azimuth_deg": [-10, 10],
        "elevation_deg": [-5, 5],
        "gain_db": [[0, -3], [-6, -9]]
    }"""
    config = {
        "tx_array": {
            "num_rows": 2,
            "num_cols": 3,
            "pattern": RADAR_ARRAY_PATTERN,
            "polarization": "V",
            "element_pattern": CUSTOM_GAIN_PATTERN,
            "element_gain_grid_json": gain_grid_json,
        },
        "rx_array": {"num_rows": 1, "num_cols": 1, "pattern": "iso", "polarization": "V"},
        "beamforming": {},
    }

    summary = configure_arrays(scene, config, {"PlanarArray": RecordingPlanarArray})

    assert scene.tx_array.pattern_kwargs["element_pattern"] == CUSTOM_GAIN_PATTERN
    assert scene.tx_array.pattern_kwargs["element_gain_grid_json"] == gain_grid_json
    assert summary["tx_array_size"] == 1
    assert summary["tx_aperture_size"] == 6
    assert summary["tx_element_pattern"] == CUSTOM_GAIN_PATTERN


def test_custom_tx_complex_weights_control_main_lobe() -> None:
    phase = np.pi / 4.0
    weights = [[np.cos(phase), np.sin(phase)], [np.cos(phase), -np.sin(phase)]]
    az = np.linspace(-60.0, 60.0, 481)
    field = numpy_radar_array_field(
        az,
        np.zeros_like(az),
        rows=1,
        cols=2,
        include_element_pattern=False,
        custom_weights_json=weights,
    )
    peak_az = float(az[int(np.argmax(np.abs(field) ** 2))])
    assert abs(peak_az - 30.0) <= 0.5


def test_complex_weights_accept_supported_formats_and_normalize() -> None:
    weights = parse_complex_weights('[1, [0, 1], {"re": -1, "im": 0}]', 3, "Tx")
    assert weights.shape == (3,)
    assert np.isclose(np.linalg.norm(weights), 1.0)


def test_tx_pattern_artifact_preserves_custom_weight_phase(tmp_path: Path) -> None:
    config = {
        "tx_array": {"num_rows": 1, "num_cols": 2, "pattern": "radar_array"},
        "beamforming": {
            "tx_weight_mode": "custom_complex_weights",
            "tx_custom_weights_json": "[[1, 0], [0, 1]]",
        },
    }
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")

    files = build_tx_pattern_artifacts(tmp_path, config)
    artifact = np.load(files["tx_radiation_pattern"], allow_pickle=False)

    np.testing.assert_allclose(artifact["aperture_weight_amplitude"], [[2**-0.5, 2**-0.5]], atol=1e-6)
    np.testing.assert_allclose(artifact["aperture_weight_phase_rad"], [[0.0, np.pi / 2.0]], atol=1e-6)


def test_tx_pattern_artifact_exports_custom_element_factor(tmp_path: Path) -> None:
    gain_grid_json = """{
        "azimuth_deg": [-90, 0, 90],
        "elevation_deg": [-45, 0, 45],
        "gain_db": [[-30, 0, -30], [-30, 6, -30], [-30, 0, -30]],
        "outside_gain_db": -60
    }"""
    config = {
        "tx_array": {
            "num_rows": 2,
            "num_cols": 2,
            "pattern": "radar_array",
            "element_pattern": "custom_gain_grid",
            "element_gain_grid_json": gain_grid_json,
        },
        "beamforming": {"tx_weight_mode": "steering_vector"},
    }

    files = build_tx_pattern_artifacts(tmp_path, config)
    element = np.load(files["tx_element_pattern"], allow_pickle=False)
    radiation = np.load(files["tx_radiation_pattern"], allow_pickle=False)

    assert str(element["pattern"]) == "custom_gain_grid"
    assert str(element["gain_grid_json"]) == gain_grid_json
    assert str(radiation["pattern_mode"]) == "element_factor_times_array_factor"
    assert str(radiation["element_pattern"]) == "custom_gain_grid"
