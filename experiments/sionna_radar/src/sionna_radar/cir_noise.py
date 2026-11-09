from __future__ import annotations

from typing import Any

import numpy as np


def inject_complex_awgn(
    coefficients: np.ndarray,
    valid: np.ndarray,
    *,
    enabled: bool = False,
    snr_db: float = 20.0,
    seed: int = 1001,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Add reproducible complex AWGN to valid CIR coefficients.

    SNR is defined as the mean valid-coefficient power divided by the mean
    complex noise power. Invalid/padded path entries remain untouched so path
    validity and array shapes stay compatible with the solver archives.
    """
    values = np.asarray(coefficients)
    if not np.iscomplexobj(values):
        raise ValueError("CIR coefficients must be complex")
    mask = np.asarray(valid, dtype=bool)
    while mask.ndim < values.ndim:
        mask = np.expand_dims(mask, axis=-1)
    try:
        mask = np.broadcast_to(mask, values.shape)
    except ValueError as exc:
        raise ValueError(f"CIR validity shape {mask.shape} does not match coefficients {values.shape}") from exc

    summary: dict[str, Any] = {
        "enabled": bool(enabled),
        "snr_db": float(snr_db),
        "seed": int(seed),
        "scope": "valid_cir_coefficients",
        "coefficient_count": int(np.count_nonzero(mask)),
        "signal_power": 0.0,
        "noise_power": 0.0,
        "realized_snr_db": None,
    }
    if not enabled:
        return values.copy(), summary
    if not np.isfinite(float(snr_db)):
        raise ValueError("CIR noise snr_db must be finite")
    if summary["coefficient_count"] == 0:
        raise ValueError("Cannot inject CIR noise: no valid coefficients")

    signal_power = float(np.mean(np.abs(values[mask]) ** 2))
    if not np.isfinite(signal_power) or signal_power <= 0.0:
        raise ValueError("Cannot inject CIR noise: valid signal power is not positive")
    noise_power = signal_power / (10.0 ** (float(snr_db) / 10.0))
    rng = np.random.default_rng(int(seed))
    noise = np.sqrt(noise_power / 2.0) * (
        rng.standard_normal(values.shape) + 1j * rng.standard_normal(values.shape)
    )
    noisy = values.astype(np.result_type(values.dtype, np.complex64), copy=True)
    noisy[mask] += noise[mask].astype(noisy.dtype, copy=False)
    summary["signal_power"] = signal_power
    summary["noise_power"] = float(noise_power)
    summary["realized_snr_db"] = float(
        10.0 * np.log10(signal_power / max(float(np.mean(np.abs(noise[mask]) ** 2)), 1e-300))
    )
    return noisy, summary
