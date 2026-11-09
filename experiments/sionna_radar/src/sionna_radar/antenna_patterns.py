from __future__ import annotations

import math
import json
from typing import Any

import numpy as np


RADAR_ARRAY_PATTERN = "radar_array"
CUSTOM_GAIN_PATTERN = "custom_gain_grid"
_REGISTERED = False
_CUSTOM_REGISTERED = False


def parse_complex_weights(raw: str | list[Any], count: int, label: str = "array") -> np.ndarray:
    data = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(data, list):
        raise ValueError(f"{label} complex weights must be a JSON array")
    weights: list[complex] = []
    for item in data:
        if isinstance(item, (int, float)):
            value = complex(float(item), 0.0)
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            value = complex(float(item[0]), float(item[1]))
        elif isinstance(item, dict):
            value = complex(float(item.get("re", 0.0)), float(item.get("im", 0.0)))
        else:
            raise ValueError("complex weight items must be numbers, [re, im], or {re, im}")
        if not math.isfinite(value.real) or not math.isfinite(value.imag):
            raise ValueError("complex weights must be finite")
        weights.append(value)
    values = np.asarray(weights, dtype=np.complex128)
    if values.size != int(count):
        raise ValueError(f"complex weight count {values.size} does not match {label} element count {count}")
    norm = float(np.linalg.norm(values))
    if norm <= 0.0:
        raise ValueError("complex weights must not all be zero")
    return values / norm


def parse_custom_gain_grid(raw: str | dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(raw) if isinstance(raw, str) else dict(raw)
    azimuth = np.asarray(payload.get("azimuth_deg", []), dtype=np.float64)
    elevation = np.asarray(payload.get("elevation_deg", []), dtype=np.float64)
    gain_db = np.asarray(payload.get("gain_db", []), dtype=np.float64)
    if azimuth.ndim != 1 or elevation.ndim != 1 or azimuth.size < 2 or elevation.size < 2:
        raise ValueError("custom gain grid requires at least two azimuth and elevation samples")
    if azimuth.size > 721 or elevation.size > 361:
        raise ValueError("custom gain grid is too large")
    if gain_db.shape != (elevation.size, azimuth.size):
        raise ValueError("gain_db shape must be [len(elevation_deg)][len(azimuth_deg)]")
    if not np.all(np.isfinite(azimuth)) or not np.all(np.isfinite(elevation)) or not np.all(np.isfinite(gain_db)):
        raise ValueError("custom gain grid values must be finite")
    az_step = np.diff(azimuth)
    el_step = np.diff(elevation)
    if np.any(az_step <= 0) or np.any(el_step <= 0):
        raise ValueError("custom gain grid axes must be strictly increasing")
    if not np.allclose(az_step, az_step[0], rtol=1e-6, atol=1e-6) or not np.allclose(el_step, el_step[0], rtol=1e-6, atol=1e-6):
        raise ValueError("custom gain grid axes must use regular spacing")
    outside_gain_db = float(payload.get("outside_gain_db", -80.0))
    if not math.isfinite(outside_gain_db):
        raise ValueError("outside_gain_db must be finite")
    return {
        "azimuth_deg": azimuth,
        "elevation_deg": elevation,
        "gain_db": gain_db,
        "outside_gain_db": outside_gain_db,
        "azimuth_step_deg": float(az_step[0]),
        "elevation_step_deg": float(el_step[0]),
    }


def numpy_custom_gain_field(
    azimuth_deg: np.ndarray,
    elevation_deg: np.ndarray,
    raw: str | dict[str, Any],
) -> np.ndarray:
    grid = parse_custom_gain_grid(raw)
    az = np.asarray(azimuth_deg, dtype=np.float64)
    el = np.asarray(elevation_deg, dtype=np.float64)
    az, el = np.broadcast_arrays(az, el)
    x = (az - grid["azimuth_deg"][0]) / grid["azimuth_step_deg"]
    y = (el - grid["elevation_deg"][0]) / grid["elevation_step_deg"]
    inside = (x >= 0.0) & (x <= grid["azimuth_deg"].size - 1) & (y >= 0.0) & (y <= grid["elevation_deg"].size - 1)
    x = np.clip(x, 0.0, grid["azimuth_deg"].size - 1.000001)
    y = np.clip(y, 0.0, grid["elevation_deg"].size - 1.000001)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, grid["azimuth_deg"].size - 1)
    y1 = np.minimum(y0 + 1, grid["elevation_deg"].size - 1)
    wx = x - x0
    wy = y - y0
    values = grid["gain_db"]
    gain_db = (
        values[y0, x0] * (1.0 - wx) * (1.0 - wy)
        + values[y0, x1] * wx * (1.0 - wy)
        + values[y1, x0] * (1.0 - wx) * wy
        + values[y1, x1] * wx * wy
    )
    gain_db = np.where(inside, gain_db, grid["outside_gain_db"])
    return np.power(10.0, gain_db / 20.0).astype(np.complex128)


def _axis_taper(count: int, name: str) -> np.ndarray:
    if count < 1:
        raise ValueError("Array dimensions must be positive")
    if name == "uniform" or count == 1:
        return np.ones(count, dtype=np.float64)
    if name == "hann":
        return np.hanning(count + 2)[1:-1].astype(np.float64)
    raise ValueError(f"Unknown aperture taper: {name}")


def aperture_samples(
    rows: int,
    cols: int,
    vertical_spacing: float,
    horizontal_spacing: float,
    taper: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return Sionna PlanarArray-compatible y/z positions and amplitudes."""
    row = np.arange(rows, dtype=np.float64)
    col = np.arange(cols, dtype=np.float64)
    y, z = np.meshgrid(
        horizontal_spacing * (col - (cols - 1) / 2.0),
        vertical_spacing * ((rows - 1) / 2.0 - row),
    )
    amplitude = np.outer(_axis_taper(rows, taper), _axis_taper(cols, taper))
    amplitude /= max(float(np.linalg.norm(amplitude)), 1e-12)
    return y.reshape(-1), z.reshape(-1), amplitude.reshape(-1)


def numpy_element_factor_field(
    azimuth_deg: np.ndarray,
    elevation_deg: np.ndarray,
    pattern: str = "iso",
    gain_grid_json: str | dict[str, Any] | None = None,
) -> np.ndarray:
    """Return the complex field factor of one array element.

    The ``tr38901`` expression mirrors Sionna RT's built-in 3GPP element
    pattern.  Keeping this numerical form here lets previews and exported
    artifacts use the same element factor as the runtime pattern.
    """
    az, el = np.broadcast_arrays(
        np.asarray(azimuth_deg, dtype=np.float64),
        np.asarray(elevation_deg, dtype=np.float64),
    )
    name = str(pattern or "iso").lower()
    if name in {"iso", "isotropic"}:
        return np.ones_like(az, dtype=np.complex128)
    if name == CUSTOM_GAIN_PATTERN:
        if gain_grid_json is None:
            raise ValueError("custom_gain_grid requires gain_grid_json")
        return numpy_custom_gain_field(az, el, gain_grid_json)
    if name != "tr38901":
        raise ValueError(f"Unknown element pattern: {pattern}")

    theta = np.pi / 2.0 - np.deg2rad(el)
    wrapped_az = (np.deg2rad(az) + np.pi) % (2.0 * np.pi) - np.pi
    theta_3db = phi_3db = math.radians(65.0)
    a_v = -np.minimum(12.0 * ((theta - np.pi / 2.0) / theta_3db) ** 2, 30.0)
    a_h = -np.minimum(12.0 * (wrapped_az / phi_3db) ** 2, 30.0)
    gain_db = -np.minimum(-(a_v + a_h), 30.0) + 8.0
    return np.sqrt(np.power(10.0, gain_db / 10.0)).astype(np.complex128)


def numpy_radar_array_field(
    azimuth_deg: np.ndarray,
    elevation_deg: np.ndarray,
    *,
    rows: int,
    cols: int,
    vertical_spacing: float = 0.5,
    horizontal_spacing: float = 0.5,
    steering_azimuth_deg: float = 0.0,
    steering_elevation_deg: float = 0.0,
    taper: str = "uniform",
    include_element_pattern: bool = True,
    element_pattern: str | None = None,
    element_gain_grid_json: str | dict[str, Any] | None = None,
    custom_weights_json: str | list[Any] | None = None,
) -> np.ndarray:
    """Reference implementation used by previews and numerical tests."""
    az = np.deg2rad(np.asarray(azimuth_deg, dtype=np.float64))
    el = np.deg2rad(np.asarray(elevation_deg, dtype=np.float64))
    steer_az = math.radians(float(steering_azimuth_deg))
    steer_el = math.radians(float(steering_elevation_deg))
    y, z, amplitude = aperture_samples(rows, cols, vertical_spacing, horizontal_spacing, taper)
    if custom_weights_json is not None:
        weights = parse_complex_weights(custom_weights_json, rows * cols, "Tx")
    else:
        steering_phase = -2.0 * np.pi * (
            y * math.sin(steer_az) * math.cos(steer_el)
            + z * math.sin(steer_el)
        )
        weights = amplitude * np.exp(1j * steering_phase)
    direction_phase = 2.0 * np.pi * (
        np.sin(az)[..., None] * np.cos(el)[..., None] * y
        + np.sin(el)[..., None] * z
    )
    field = np.sum(weights * np.exp(1j * direction_phase), axis=-1)
    resolved_element_pattern = element_pattern or ("tr38901" if include_element_pattern else "iso")
    if resolved_element_pattern not in {"iso", "isotropic"}:
        field *= numpy_element_factor_field(
            np.rad2deg(az),
            np.rad2deg(el),
            pattern=resolved_element_pattern,
            gain_grid_json=element_gain_grid_json,
        )
    return field


def register_radar_array_pattern(rt: Any) -> None:
    """Register a fixed-beam phased aperture through Sionna's public API."""
    global _REGISTERED
    if _REGISTERED:
        return

    import drjit as dr
    import mitsuba as mi

    def factory(
        *,
        polarization: str,
        polarization_model: str = "tr38901_2",
        aperture_rows: int = 1,
        aperture_cols: int = 1,
        aperture_vertical_spacing: float = 0.5,
        aperture_horizontal_spacing: float = 0.5,
        steering_azimuth_deg: float = 0.0,
        steering_elevation_deg: float = 0.0,
        taper: str = "uniform",
        custom_weights_json: str | None = None,
        element_pattern: str = "tr38901",
        element_gain_grid_json: str | None = None,
    ) -> Any:
        y, z, amplitude = aperture_samples(
            int(aperture_rows),
            int(aperture_cols),
            float(aperture_vertical_spacing),
            float(aperture_horizontal_spacing),
            str(taper),
        )
        if custom_weights_json is not None:
            weights = parse_complex_weights(custom_weights_json, int(aperture_rows) * int(aperture_cols), "Tx")
        else:
            steer_az = math.radians(float(steering_azimuth_deg))
            steer_el = math.radians(float(steering_elevation_deg))
            steering_phase = -2.0 * np.pi * (
                y * math.sin(steer_az) * math.cos(steer_el)
                + z * math.sin(steer_el)
            )
            weights = amplitude * np.exp(1j * steering_phase)

        resolved_element_pattern = str(element_pattern or "tr38901").lower()
        custom_grid = None
        if resolved_element_pattern == CUSTOM_GAIN_PATTERN:
            if not element_gain_grid_json:
                raise ValueError("custom Tx element pattern requires element_gain_grid_json")
            custom_grid = parse_custom_gain_grid(element_gain_grid_json)
        elif resolved_element_pattern not in {"iso", "isotropic", "tr38901"}:
            raise ValueError(f"Unknown Tx element pattern: {element_pattern}")

        def vertical_pattern(theta: Any, phi: Any) -> Any:
            sin_theta, cos_theta = dr.sincos(theta)
            sin_phi, _ = dr.sincos(phi)
            direction_y = sin_theta * sin_phi
            direction_z = cos_theta
            real = dr.zeros(mi.Float, dr.width(theta))
            imag = dr.zeros(mi.Float, dr.width(theta))
            for pos_y, pos_z, weight in zip(y, z, weights):
                phase = dr.two_pi * (
                    float(pos_y) * direction_y
                    + float(pos_z) * direction_z
                )
                phase_sin, phase_cos = dr.sincos(phase)
                real += float(weight.real) * phase_cos - float(weight.imag) * phase_sin
                imag += float(weight.real) * phase_sin + float(weight.imag) * phase_cos

            if resolved_element_pattern in {"iso", "isotropic"}:
                element_field = dr.ones(mi.Float, dr.width(theta))
            elif resolved_element_pattern == "tr38901":
                theta_3db = phi_3db = math.radians(65.0)
                a_v = -dr.min([12.0 * ((theta - dr.pi / 2.0) / theta_3db) ** 2, 30.0])
                wrapped_phi = phi + dr.pi
                wrapped_phi -= dr.floor(wrapped_phi / (2.0 * dr.pi)) * 2.0 * dr.pi
                wrapped_phi -= dr.pi
                a_h = -dr.min([12.0 * (wrapped_phi / phi_3db) ** 2, 30.0])
                gain_db = -dr.min([-(a_v + a_h), 30.0]) + 8.0
                element_field = dr.sqrt(dr.power(10.0, gain_db / 10.0))
            else:
                assert custom_grid is not None
                az_count = int(custom_grid["azimuth_deg"].size)
                el_count = int(custom_grid["elevation_deg"].size)
                azimuth_deg = phi * (180.0 / dr.pi)
                elevation_deg = 90.0 - theta * (180.0 / dr.pi)
                x = (azimuth_deg - float(custom_grid["azimuth_deg"][0])) / float(custom_grid["azimuth_step_deg"])
                y_grid = (elevation_deg - float(custom_grid["elevation_deg"][0])) / float(custom_grid["elevation_step_deg"])
                inside = (x >= 0.0) & (x <= az_count - 1) & (y_grid >= 0.0) & (y_grid <= el_count - 1)
                x = dr.clip(x, 0.0, az_count - 1.000001)
                y_grid = dr.clip(y_grid, 0.0, el_count - 1.000001)
                x0 = dr.floor(x)
                y0 = dr.floor(y_grid)
                x1 = dr.minimum(x0 + 1.0, az_count - 1)
                y1 = dr.minimum(y0 + 1.0, el_count - 1)
                wx = x - x0
                wy = y_grid - y0
                values = mi.Float(custom_grid["gain_db"].reshape(-1).tolist())

                def sample(ix: Any, iy: Any) -> Any:
                    index = mi.UInt32(iy) * az_count + mi.UInt32(ix)
                    return dr.gather(mi.Float, values, index)

                gain_db = (
                    sample(x0, y0) * (1.0 - wx) * (1.0 - wy)
                    + sample(x1, y0) * wx * (1.0 - wy)
                    + sample(x0, y1) * (1.0 - wx) * wy
                    + sample(x1, y1) * wx * wy
                )
                gain_db = dr.select(inside, gain_db, float(custom_grid["outside_gain_db"]))
                element_field = dr.power(10.0, gain_db / 20.0)
            return mi.Complex2f(real * element_field, imag * element_field)

        return rt.PolarizedAntennaPattern(
            v_pattern=vertical_pattern,
            polarization=polarization,
            polarization_model=polarization_model,
        )

    rt.register_antenna_pattern(RADAR_ARRAY_PATTERN, factory)
    _REGISTERED = True


def register_custom_gain_pattern(rt: Any) -> None:
    """Register a regular azimuth/elevation gain grid through Sionna's public API."""
    global _CUSTOM_REGISTERED
    if _CUSTOM_REGISTERED:
        return

    import drjit as dr
    import mitsuba as mi

    def factory(
        *,
        polarization: str,
        gain_grid_json: str,
        polarization_model: str = "tr38901_2",
    ) -> Any:
        grid = parse_custom_gain_grid(gain_grid_json)
        az_count = int(grid["azimuth_deg"].size)
        el_count = int(grid["elevation_deg"].size)
        az_min = float(grid["azimuth_deg"][0])
        el_min = float(grid["elevation_deg"][0])
        az_step = float(grid["azimuth_step_deg"])
        el_step = float(grid["elevation_step_deg"])
        outside = float(grid["outside_gain_db"])
        values = mi.Float(grid["gain_db"].reshape(-1).tolist())

        def vertical_pattern(theta: Any, phi: Any) -> Any:
            azimuth_deg = phi * (180.0 / dr.pi)
            elevation_deg = 90.0 - theta * (180.0 / dr.pi)
            x = (azimuth_deg - az_min) / az_step
            y = (elevation_deg - el_min) / el_step
            inside = (x >= 0.0) & (x <= az_count - 1) & (y >= 0.0) & (y <= el_count - 1)
            x = dr.clip(x, 0.0, az_count - 1.000001)
            y = dr.clip(y, 0.0, el_count - 1.000001)
            x0 = dr.floor(x)
            y0 = dr.floor(y)
            x1 = dr.minimum(x0 + 1.0, az_count - 1)
            y1 = dr.minimum(y0 + 1.0, el_count - 1)
            wx = x - x0
            wy = y - y0

            def sample(ix: Any, iy: Any) -> Any:
                index = mi.UInt32(iy) * az_count + mi.UInt32(ix)
                return dr.gather(mi.Float, values, index)

            gain_db = (
                sample(x0, y0) * (1.0 - wx) * (1.0 - wy)
                + sample(x1, y0) * wx * (1.0 - wy)
                + sample(x0, y1) * (1.0 - wx) * wy
                + sample(x1, y1) * wx * wy
            )
            gain_db = dr.select(inside, gain_db, outside)
            field = dr.power(10.0, gain_db / 20.0)
            return mi.Complex2f(field, dr.zeros(mi.Float, dr.width(theta)))

        return rt.PolarizedAntennaPattern(
            v_pattern=vertical_pattern,
            polarization=polarization,
            polarization_model=polarization_model,
        )

    rt.register_antenna_pattern(CUSTOM_GAIN_PATTERN, factory)
    _CUSTOM_REGISTERED = True
