from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import maximum_filter, uniform_filter
import yaml

from app.core.path_layout import ensure_canonical_path_archive


SPEED_OF_LIGHT = 299_792_458.0
BOLTZMANN = 1.380649e-23


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def next_power_of_two(value: float) -> int:
    return 1 << max(0, int(math.ceil(math.log2(max(float(value), 1.0)))))


def resolve_fmcw_config(config: dict[str, Any]) -> dict[str, Any]:
    waveform = dict(config.get("waveform", {}) or {})
    receiver = dict(config.get("receiver", {}) or {})
    processing = dict(config.get("radar_processing", {}) or {})
    bandwidth_hz = float(waveform.get("bandwidth_hz", config.get("bandwidth_hz", 1e9)))
    chirp_duration_s = float(waveform.get("chirp_duration_s", 50e-6))
    idle_time_s = float(waveform.get("idle_time_s", 10e-6))
    num_chirps = int(waveform.get("num_chirps", 32))
    rmax_m = float(config.get("range_processing", {}).get("rmax_m", 200.0))
    required_samples = 1.1 * (2.0 * bandwidth_hz * rmax_m / SPEED_OF_LIGHT + 1.0)
    adc_samples = int(waveform.get("adc_samples", 0)) or next_power_of_two(required_samples)
    adc_samples = min(max(adc_samples, 256), int(processing.get("max_adc_samples", 8192)))
    if adc_samples <= 0 or num_chirps < 2 or bandwidth_hz <= 0.0 or chirp_duration_s <= 0.0:
        raise ValueError("Invalid FMCW waveform dimensions")
    return {
        "type": "fmcw",
        "bandwidth_hz": bandwidth_hz,
        "chirp_duration_s": chirp_duration_s,
        "idle_time_s": idle_time_s,
        "num_chirps": num_chirps,
        "adc_samples": adc_samples,
        "sample_rate_hz": adc_samples / chirp_duration_s,
        "chirp_slope_hz_per_s": bandwidth_hz / chirp_duration_s,
        "temperature_k": float(receiver.get("temperature_k", 290.0)),
        "noise_figure_db": float(receiver.get("noise_figure_db", 8.0)),
        "max_synthesis_paths": int(processing.get("max_synthesis_paths", 256)),
        "cfar_pfa": float(processing.get("cfar_pfa", 1e-5)),
        "seed": int(processing.get("noise_seed", config.get("path_solver", {}).get("seed", 1) + 100_003)),
        "requested_range_max_m": rmax_m,
    }


def ca_cfar_2d(power: np.ndarray, pfa: float, guard: tuple[int, int] = (1, 2), training: tuple[int, int] = (4, 8)) -> tuple[np.ndarray, np.ndarray]:
    guard_rows, guard_cols = guard
    train_rows, train_cols = training
    outer_shape = (2 * (guard_rows + train_rows) + 1, 2 * (guard_cols + train_cols) + 1)
    guard_shape = (2 * guard_rows + 1, 2 * guard_cols + 1)
    outer_count = outer_shape[0] * outer_shape[1]
    guard_count = guard_shape[0] * guard_shape[1]
    training_count = outer_count - guard_count
    outer_sum = uniform_filter(power, size=outer_shape, mode="constant") * outer_count
    guard_sum = uniform_filter(power, size=guard_shape, mode="constant") * guard_count
    noise = np.maximum((outer_sum - guard_sum) / max(training_count, 1), 1e-30)
    alpha = training_count * (float(pfa) ** (-1.0 / training_count) - 1.0)
    threshold = noise * alpha
    detections = power > threshold
    margin_r = guard_rows + train_rows
    margin_c = guard_cols + train_cols
    detections[:margin_r, :] = False
    detections[-margin_r:, :] = False
    detections[:, :margin_c] = False
    detections[:, -margin_c:] = False
    detections &= power >= maximum_filter(power, size=(3, 3), mode="constant")
    return detections, threshold


def build_fmcw_artifacts(run_dir: Path) -> dict[str, Any]:
    ensure_canonical_path_archive(run_dir)
    with (run_dir / "config.yaml").open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    fmcw = resolve_fmcw_config(config)
    paths = np.load(run_dir / "paths_summary.npz", allow_pickle=False)
    beam = np.load(run_dir / "analysis" / "beamformed_observation.npz", allow_pickle=False)
    tau = np.asarray(paths["tau_s"]).reshape(-1).astype(np.float64)
    doppler = np.asarray(paths["doppler_hz"]).reshape(-1).astype(np.float64)
    valid = np.asarray(paths["valid"]).reshape(-1).astype(bool)
    coefficient = np.asarray(beam["beamformed_path_coefficients"]).reshape(-1).astype(np.complex128)
    power = np.abs(coefficient) ** 2
    valid &= np.isfinite(tau) & (tau > 1e-10) & np.isfinite(doppler) & np.isfinite(power)

    slope = fmcw["chirp_slope_hz_per_s"]
    sample_rate = fmcw["sample_rate_hz"]
    beat_frequency = slope * tau + doppler
    valid &= (beat_frequency >= 0.0) & (beat_frequency < sample_rate)
    valid_indices = np.flatnonzero(valid)
    ranked = valid_indices[np.argsort(power[valid_indices])[::-1]]
    selected = ranked[: fmcw["max_synthesis_paths"]]
    residual = ranked[fmcw["max_synthesis_paths"] :]
    total_power = float(np.sum(power[valid_indices]))
    selected_power = float(np.sum(power[selected]))

    n_fast = fmcw["adc_samples"]
    n_slow = fmcw["num_chirps"]
    fast_time = np.arange(n_fast, dtype=np.float64) / sample_rate
    repetition_s = fmcw["chirp_duration_s"] + fmcw["idle_time_s"]
    slow_time = np.arange(n_slow, dtype=np.float64) * repetition_s
    if selected.size:
        fast_phase = np.exp(1j * 2.0 * np.pi * beat_frequency[selected, None] * fast_time[None, :])
        slow_phase = np.exp(1j * 2.0 * np.pi * doppler[selected, None] * slow_time[None, :])
        tx_power_w = 10.0 ** ((float(config.get("tx_power_dbm", 30.0)) - 30.0) / 10.0)
        weighted_fast = coefficient[selected, None] * math.sqrt(tx_power_w) * fast_phase
        signal = slow_phase.T @ weighted_fast
    else:
        signal = np.zeros((n_slow, n_fast), dtype=np.complex128)

    noise_power_w = (
        BOLTZMANN
        * fmcw["temperature_k"]
        * sample_rate
        * 10.0 ** (fmcw["noise_figure_db"] / 10.0)
    )
    rng = np.random.default_rng(fmcw["seed"])
    noise = math.sqrt(noise_power_w / 2.0) * (
        rng.standard_normal(signal.shape) + 1j * rng.standard_normal(signal.shape)
    )
    signal += noise

    fast_window = np.hanning(n_fast).astype(np.float64)
    slow_window = np.hanning(n_slow).astype(np.float64)
    windowed = signal * slow_window[:, None] * fast_window[None, :]
    spectrum = np.fft.fft(windowed, axis=1) / max(float(np.sum(fast_window)), 1e-12)
    spectrum = np.fft.fftshift(np.fft.fft(spectrum, axis=0), axes=0) / max(float(np.sum(slow_window)), 1e-12)
    if residual.size:
        range_bins = np.rint(beat_frequency[residual] * n_fast / sample_rate).astype(np.int64) % n_fast
        doppler_unshifted = np.rint(doppler[residual] * n_slow * repetition_s).astype(np.int64) % n_slow
        doppler_bins = (doppler_unshifted + n_slow // 2) % n_slow
        tx_power_w = 10.0 ** ((float(config.get("tx_power_dbm", 30.0)) - 30.0) / 10.0)
        np.add.at(
            spectrum,
            (doppler_bins, range_bins),
            coefficient[residual] * math.sqrt(tx_power_w),
        )
    spectrum_power = np.abs(spectrum) ** 2

    range_axis = SPEED_OF_LIGHT * np.arange(n_fast, dtype=np.float64) / (2.0 * fmcw["bandwidth_hz"])
    wavelength = SPEED_OF_LIGHT / float(config.get("frequency_hz", 28e9))
    doppler_axis = np.fft.fftshift(np.fft.fftfreq(n_slow, d=repetition_s))
    velocity_axis = wavelength * doppler_axis / 2.0
    range_mask = range_axis <= fmcw["requested_range_max_m"]
    range_axis = range_axis[range_mask]
    spectrum_power = spectrum_power[:, range_mask]
    detections, threshold = ca_cfar_2d(spectrum_power, fmcw["cfar_pfa"])

    detection_indices = np.argwhere(detections)
    if detection_indices.size:
        detection_indices = detection_indices[
            np.argsort(spectrum_power[detection_indices[:, 0], detection_indices[:, 1]])[::-1]
        ][:200]
    detection_rows = [
        {
            "range_m": float(range_axis[col]),
            "velocity_mps": float(velocity_axis[row]),
            "power": float(spectrum_power[row, col]),
            "power_dbw": float(10.0 * np.log10(max(float(spectrum_power[row, col]), 1e-30))),
            "threshold_dbw": float(10.0 * np.log10(max(float(threshold[row, col]), 1e-30))),
        }
        for row, col in detection_indices
    ]

    analysis_dir = run_dir / "analysis"
    figures_dir = run_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    npz_path = analysis_dir / "fmcw_range_doppler.npz"
    np.savez_compressed(
        npz_path,
        range_axis_m=range_axis.astype(np.float32),
        velocity_axis_mps=velocity_axis.astype(np.float32),
        range_doppler_power=spectrum_power.astype(np.float32),
        cfar_threshold=threshold.astype(np.float32),
        cfar_detection_mask=detections,
    )

    figure_path = figures_dir / "fmcw_range_doppler.png"
    relative_db = 10.0 * np.log10(np.maximum(spectrum_power, 1e-30))
    peak_db = float(np.max(relative_db)) if relative_db.size else 0.0
    fig, ax = plt.subplots(figsize=(10.0, 5.2), constrained_layout=True)
    image = ax.imshow(
        np.maximum(relative_db, peak_db - 70.0),
        origin="lower",
        aspect="auto",
        extent=[float(range_axis[0]), float(range_axis[-1]), float(velocity_axis[0]), float(velocity_axis[-1])],
        cmap="magma",
    )
    if detection_indices.size:
        ax.scatter(
            [range_axis[col] for row, col in detection_indices],
            [velocity_axis[row] for row, col in detection_indices],
            s=18,
            facecolors="none",
            edgecolors="cyan",
            linewidths=0.8,
        )
    ax.set_xlabel("Range (m)")
    ax.set_ylabel("Radial velocity (m/s)")
    ax.set_title("FMCW range-Doppler response and CA-CFAR detections")
    fig.colorbar(image, ax=ax, label="Power (dBW, 70 dB display range)")
    fig.savefig(figure_path, dpi=160)
    plt.close(fig)

    summary = {
        "schema_version": "0.2.0",
        "run_id": run_dir.name,
        "created_at_utc": utc_now(),
        "model": "hybrid complex FMCW synthesis from Sionna RT paths",
        "synthesis_method": {
            "strong_paths": "exact discrete dechirped fast/slow-time samples",
            "remaining_paths": "coherent nearest-bin range-Doppler projection",
        },
        "waveform": fmcw,
        "range_resolution_m": SPEED_OF_LIGHT / (2.0 * fmcw["bandwidth_hz"]),
        "unambiguous_range_m": SPEED_OF_LIGHT * n_fast / (2.0 * fmcw["bandwidth_hz"]),
        "velocity_resolution_mps": wavelength / (2.0 * n_slow * repetition_s),
        "unambiguous_velocity_mps": wavelength / (4.0 * repetition_s),
        "thermal_noise_power_per_complex_sample_w": noise_power_w,
        "valid_path_count": int(valid_indices.size),
        "synthesized_path_count": int(valid_indices.size),
        "synthesized_path_power_fraction": 1.0 if valid_indices.size else 0.0,
        "exact_time_domain_path_count": int(selected.size),
        "exact_time_domain_path_power_fraction": float(selected_power / max(total_power, 1e-300)),
        "fft_gridded_path_count": int(residual.size),
        "cfar": {
            "method": "2D CA-CFAR",
            "pfa": fmcw["cfar_pfa"],
            "detection_count": int(len(detection_rows)),
            "detections": detection_rows,
        },
        "files": {
            "range_doppler": str(npz_path),
            "range_doppler_figure": str(figure_path),
        },
    }
    summary_path = analysis_dir / "fmcw_summary.json"
    summary["files"]["summary"] = str(summary_path)
    write_json(summary_path, summary)
    return {"summary": summary, "files": summary["files"]}
