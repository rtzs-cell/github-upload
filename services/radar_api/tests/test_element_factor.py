import numpy as np

from app.core.beamforming import steering_pattern
from sionna_radar.antenna_patterns import numpy_element_factor_field


def test_isotropic_element_factor_is_unity() -> None:
    azimuth = np.asarray([-180.0, -20.0, 0.0, 70.0])
    elevation = np.asarray([-30.0, 0.0, 20.0, 45.0])
    field = numpy_element_factor_field(azimuth, elevation, "iso")
    np.testing.assert_allclose(field, 1.0)


def test_tr38901_element_factor_rolls_off_away_from_boresight() -> None:
    field = numpy_element_factor_field(
        np.asarray([0.0, 65.0]),
        np.asarray([0.0, 0.0]),
        "tr38901",
    )
    assert abs(field[0]) > abs(field[1])


def test_rx_steering_pattern_includes_element_factor() -> None:
    azimuth, elevation, gain = steering_pattern(
        1,
        1,
        np.ones(1, dtype=np.complex64),
        0.5,
        0.5,
        element_pattern="tr38901",
    )
    zero_az = int(np.argmin(np.abs(azimuth)))
    edge_az = int(np.argmin(np.abs(azimuth - 65.0)))
    zero_el = int(np.argmin(np.abs(elevation)))
    assert gain[zero_el, zero_az] > gain[zero_el, edge_az]


def test_custom_rx_element_factor_is_applied_to_steering_pattern() -> None:
    raw = """{
        "azimuth_deg": [-90, 0, 90],
        "elevation_deg": [-45, 0, 45],
        "gain_db": [[-30, 0, -30], [-30, 0, -30], [-30, 0, -30]],
        "outside_gain_db": -60
    }"""
    azimuth, elevation, gain = steering_pattern(
        1,
        1,
        np.ones(1, dtype=np.complex64),
        0.5,
        0.5,
        element_pattern="custom_gain_grid",
        element_gain_grid_json=raw,
    )
    zero_az = int(np.argmin(np.abs(azimuth)))
    edge_az = int(np.argmin(np.abs(azimuth - 90.0)))
    zero_el = int(np.argmin(np.abs(elevation)))
    assert gain[zero_el, zero_az] > 900.0 * gain[zero_el, edge_az]
