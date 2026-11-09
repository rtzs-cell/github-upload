from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from .archive import (
    append_runs_index,
    capture_environment,
    prepare_run_dir,
    to_jsonable,
    utc_now,
    write_json,
    write_yaml,
)
from .processing import (
    PathArrays,
    canonicalize_path_arrays,
    cir_path_count,
    drjit_to_numpy,
    save_basic_figures,
    summarize_paths,
)
from .directional_sampling import correct_diffuse_cir_amplitudes, initial_ray_sampling
from .cir_noise import inject_complex_awgn
from .antenna_patterns import (
    CUSTOM_GAIN_PATTERN,
    RADAR_ARRAY_PATTERN,
    parse_complex_weights,
    parse_custom_gain_grid,
    register_custom_gain_pattern,
    register_radar_array_pattern,
)


def _import_sionna():
    import mitsuba as mi
    import sionna.rt as rt

    return {
        "mi": mi,
        "rt": rt,
        "BackscatteringPattern": getattr(rt, "BackscatteringPattern", None),
        "DirectivePattern": getattr(rt, "DirectivePattern", None),
        "LambertianPattern": getattr(rt, "LambertianPattern", None),
        "PathSolver": getattr(rt, "PathSolver", None),
        "PlanarArray": getattr(rt, "PlanarArray"),
        "Receiver": getattr(rt, "Receiver"),
        "Transmitter": getattr(rt, "Transmitter"),
        "load_scene": getattr(rt, "load_scene"),
    }


def scene_path(scene_name: str, rt_module: Any) -> str | None:
    if scene_name == "none":
        return None
    if hasattr(rt_module.scene, scene_name):
        return getattr(rt_module.scene, scene_name)
    path = Path(scene_name)
    if path.exists():
        return str(path)
    raise ValueError(f"Unknown scene '{scene_name}'")


def scene_geometry_summary(scene: Any) -> dict[str, Any]:
    objects = {}
    for name, obj in scene.objects.items():
        mesh = getattr(obj, "mi_mesh", None) or getattr(obj, "_mi_shape", None)
        if mesh is None:
            continue
        bbox = mesh.bbox()
        surface_area = mesh.surface_area()[0] if hasattr(mesh, "surface_area") else 0.0
        objects[name] = {
            "material": getattr(getattr(obj, "radio_material", None), "name", None),
            "bbox_min": [float(x) for x in bbox.min],
            "bbox_max": [float(x) for x in bbox.max],
            "bbox_center": [float(x) for x in bbox.center()],
            "surface_area": float(surface_area),
            "vertex_count": int(mesh.vertex_count()) if hasattr(mesh, "vertex_count") else 0,
            "face_count": int(mesh.face_count()) if hasattr(mesh, "face_count") else 0,
        }
    return {
        "object_count": len(scene.objects),
        "material_names": sorted(scene.radio_materials.keys()),
        "objects": objects,
    }


def scalar_float(value: Any) -> float | None:
    """Convert Python, NumPy, Mitsuba, or Dr.Jit scalar-like values to float."""
    if value is None:
        return None
    try:
        return float(value)
    except TypeError:
        arr = np.asarray(value)
        if arr.size == 0:
            return None
        return float(arr.reshape(-1)[0])


def vector_float_list(value: Any) -> list[float]:
    return [scalar_float(x) for x in value]


def make_pattern(scattering_cfg: dict[str, Any], imports: dict[str, Any]) -> Any:
    name = str(scattering_cfg.get("pattern", "lambertian")).lower()
    if name == "backscattering":
        if imports["BackscatteringPattern"] is None:
            return None
        return imports["BackscatteringPattern"](
            alpha_r=int(scattering_cfg.get("alpha_r", 20)),
            alpha_i=int(scattering_cfg.get("alpha_i", 20)),
            lambda_=float(scattering_cfg.get("lambda_", 0.3)),
        )
    if name == "directive":
        if imports["DirectivePattern"] is None:
            return None
        return imports["DirectivePattern"](
            alpha_r=int(scattering_cfg.get("alpha_r", 20)),
        )
    if name == "lambertian":
        if imports["LambertianPattern"] is None:
            return None
        return imports["LambertianPattern"]()
    raise ValueError(f"Unknown scattering pattern '{name}'")


def configure_materials(scene: Any, config: dict[str, Any], imports: dict[str, Any]) -> dict[str, Any]:
    scattering_cfg = config.get("scattering", {})
    enabled = bool(scattering_cfg.get("enabled", False))
    coeff = float(scattering_cfg.get("coefficient", 0.0)) if enabled else 0.0
    xpd = float(scattering_cfg.get("xpd_coefficient", 0.0)) if enabled else 0.0
    pattern = make_pattern(scattering_cfg, imports) if enabled else None

    material_summary = {}
    for name, mat in scene.radio_materials.items():
        if hasattr(mat, "scattering_coefficient"):
            mat.scattering_coefficient = coeff
        if hasattr(mat, "xpd_coefficient"):
            mat.xpd_coefficient = xpd
        if enabled and hasattr(mat, "scattering_pattern"):
            mat.scattering_pattern = pattern
        material_summary[name] = {
            "class": type(mat).__name__,
            "itu_type": getattr(mat, "itu_type", None),
            "relative_permittivity": scalar_float(mat.relative_permittivity) if hasattr(mat, "relative_permittivity") else None,
            "conductivity": scalar_float(mat.conductivity) if hasattr(mat, "conductivity") else None,
            "thickness": scalar_float(mat.thickness) if hasattr(mat, "thickness") else None,
            "scattering_coefficient": scalar_float(mat.scattering_coefficient) if hasattr(mat, "scattering_coefficient") else None,
            "xpd_coefficient": scalar_float(mat.xpd_coefficient) if hasattr(mat, "xpd_coefficient") else None,
            "scattering_pattern": type(getattr(mat, "scattering_pattern", None)).__name__,
        }
    return material_summary


def configure_arrays(scene: Any, config: dict[str, Any], imports: dict[str, Any]) -> dict[str, Any]:
    PlanarArray = imports["PlanarArray"]
    tx_cfg = dict(config["tx_array"])
    rx_cfg = dict(config["rx_array"])
    gain_grid_json = tx_cfg.pop("gain_grid_json", None)
    tx_element_pattern = str(tx_cfg.pop("element_pattern", "tr38901") or "tr38901")
    tx_element_gain_grid_json = tx_cfg.pop("element_gain_grid_json", None)
    rx_gain_grid_json = rx_cfg.pop("gain_grid_json", None)
    rx_cfg.pop("element_pattern", None)
    rx_cfg.pop("element_gain_grid_json", None)
    if rx_cfg.get("pattern") == CUSTOM_GAIN_PATTERN:
        if not rx_gain_grid_json:
            raise ValueError("custom_gain_grid requires rx_array.gain_grid_json")
        parse_custom_gain_grid(rx_gain_grid_json)
        rx_cfg["gain_grid_json"] = str(rx_gain_grid_json)
    requested_tx_size = int(tx_cfg["num_rows"]) * int(tx_cfg["num_cols"])
    embedded_tx_pattern = tx_cfg.get("pattern") in {RADAR_ARRAY_PATTERN, CUSTOM_GAIN_PATTERN}
    if tx_cfg.get("pattern") == RADAR_ARRAY_PATTERN:
        beamforming = dict(config.get("beamforming", {}) or {})
        tx_weight_mode = str(beamforming.get("tx_weight_mode", "steering_vector"))
        custom_weights_json = beamforming.get("tx_custom_weights_json") if tx_weight_mode == "custom_complex_weights" else None
        if custom_weights_json is not None:
            parse_complex_weights(custom_weights_json, requested_tx_size, "Tx")
        tx_cfg.update(
            {
                "aperture_rows": int(tx_cfg["num_rows"]),
                "aperture_cols": int(tx_cfg["num_cols"]),
                "aperture_vertical_spacing": float(tx_cfg.get("vertical_spacing", 0.5)),
                "aperture_horizontal_spacing": float(tx_cfg.get("horizontal_spacing", 0.5)),
                "steering_azimuth_deg": float(beamforming.get("tx_steering_azimuth_deg", 0.0)),
                "steering_elevation_deg": float(beamforming.get("tx_steering_elevation_deg", 0.0)),
                "taper": str(beamforming.get("tx_taper", "uniform")),
                "element_pattern": tx_element_pattern,
                "num_rows": 1,
                "num_cols": 1,
            }
        )
        if tx_element_pattern == CUSTOM_GAIN_PATTERN:
            if not tx_element_gain_grid_json:
                raise ValueError("custom Tx element pattern requires tx_array.element_gain_grid_json")
            parse_custom_gain_grid(tx_element_gain_grid_json)
            tx_cfg["element_gain_grid_json"] = str(tx_element_gain_grid_json)
        if custom_weights_json is not None:
            tx_cfg["custom_weights_json"] = str(custom_weights_json)
    elif tx_cfg.get("pattern") == CUSTOM_GAIN_PATTERN:
        if not gain_grid_json:
            raise ValueError("custom_gain_grid requires tx_array.gain_grid_json")
        parse_custom_gain_grid(gain_grid_json)
        tx_cfg.update({"num_rows": 1, "num_cols": 1, "gain_grid_json": str(gain_grid_json)})
    scene.tx_array = PlanarArray(**tx_cfg)
    scene.rx_array = PlanarArray(**rx_cfg)
    rx_positions = getattr(scene.rx_array, "normalized_positions", None)
    if rx_positions is None:
        rx_positions = getattr(scene.rx_array, "positions", None)
    if rx_positions is None:
        rx_positions = getattr(scene.rx_array, "rotated_positions", np.array([]))
    rx_positions_np = np.asarray(rx_positions)
    if rx_positions_np.ndim == 2 and rx_positions_np.shape[0] == 3 and rx_positions_np.shape[1] != 3:
        rx_positions_np = rx_positions_np.T
    return {
        "tx_array_size": int(scene.tx_array.array_size),
        "tx_aperture_size": requested_tx_size,
        "tx_aperture_embedded_in_pattern": bool(embedded_tx_pattern),
        "tx_element_pattern": tx_element_pattern if tx_cfg.get("pattern") == RADAR_ARRAY_PATTERN else str(tx_cfg.get("pattern", "iso")),
        "rx_array_size": int(scene.rx_array.array_size),
        "rx_normalized_positions_shape": list(rx_positions_np.shape),
        "rx_normalized_positions_first": rx_positions_np.reshape(-1, rx_positions_np.shape[-1])[:5].tolist()
        if rx_positions_np.size and rx_positions_np.ndim >= 2
        else rx_positions_np.reshape(-1)[:5].tolist(),
    }


def configure_devices(scene: Any, config: dict[str, Any], imports: dict[str, Any]) -> dict[str, Any]:
    mi = imports["mi"]
    Transmitter = imports["Transmitter"]
    Receiver = imports["Receiver"]
    devices = config.get("devices", {})
    tx_pos = devices.get("tx_position_m", [0.0, -0.05, 10.0])
    rx_pos = devices.get("rx_position_m", [0.0, 0.05, 10.0])
    look_at = devices.get("look_at_m")
    tx_look_at = devices.get("tx_look_at_m", look_at)
    rx_look_at = devices.get("rx_look_at_m", look_at)
    tx = Transmitter("tx", position=[float(x) for x in tx_pos], power_dbm=float(config.get("tx_power_dbm", 30.0)))
    rx = Receiver("rx", position=[float(x) for x in rx_pos])
    scene.add(tx)
    scene.add(rx)
    if tx_look_at is not None:
        set_device_look_at(tx, tx_pos, tx_look_at, mi)
    if rx_look_at is not None:
        set_device_look_at(rx, rx_pos, rx_look_at, mi)
    return {
        "tx_position_m": [float(x) for x in tx_pos],
        "rx_position_m": [float(x) for x in rx_pos],
        "look_at_m": [float(x) for x in look_at] if look_at is not None else None,
        "tx_look_at_m": [float(x) for x in tx_look_at] if tx_look_at is not None else None,
        "rx_look_at_m": [float(x) for x in rx_look_at] if rx_look_at is not None else None,
        "tx_orientation_rad": vector_float_list(tx.orientation),
        "rx_orientation_rad": vector_float_list(rx.orientation),
    }


def set_device_look_at(device: Any, position: list[float], target: list[float], mi: Any) -> None:
    try:
        device.look_at(mi.Point3f(*target))
        return
    except Exception:
        pass
    try:
        device.look_at([float(x) for x in target])
        return
    except Exception:
        pass
    dx = float(target[0]) - float(position[0])
    dy = float(target[1]) - float(position[1])
    dz = float(target[2]) - float(position[2])
    horizontal = float(np.hypot(dx, dy))
    alpha = float(np.arctan2(dy, dx))
    beta = float(-np.arctan2(dz, horizontal))
    device.orientation = [alpha, beta, 0.0]


def collect_path_arrays(paths: Any) -> PathArrays:
    try:
        a_cir, tau_cir = paths.cir(normalize_delays=False, out_type="numpy")
    except TypeError:
        paths.normalize_delays = False
        a_cir, tau_cir = paths.cir()
    vertices = None
    try:
        vertices = drjit_to_numpy(paths.vertices)
    except Exception:
        vertices = None
    valid = path_valid(paths)
    interactions = path_interactions(paths)
    objects = path_objects(paths)
    return PathArrays(
        tau_s=drjit_to_numpy(paths.tau),
        valid=valid,
        theta_r_rad=drjit_to_numpy(paths.theta_r),
        phi_r_rad=drjit_to_numpy(paths.phi_r),
        theta_t_rad=drjit_to_numpy(paths.theta_t),
        phi_t_rad=drjit_to_numpy(paths.phi_t),
        doppler_hz=drjit_to_numpy(paths.doppler),
        interactions=interactions,
        objects=objects,
        vertices=vertices,
        a_cir=np.asarray(a_cir),
        tau_cir_s=np.asarray(tau_cir),
    )


def path_valid(paths: Any) -> np.ndarray:
    if hasattr(paths, "valid"):
        return drjit_to_numpy(paths.valid)
    if hasattr(paths, "mask"):
        return drjit_to_numpy(paths.mask)
    tau = drjit_to_numpy(paths.tau)
    return np.isfinite(tau) & (tau > 0)


def path_type_to_interaction_code(path_type: int) -> int:
    # Newer postprocessing codes: 1 specular, 2 diffuse, 8 diffraction.
    if path_type == 1:
        return 1
    if path_type == 2:
        return 8
    if path_type == 3:
        return 2
    return 0


def path_interactions(paths: Any) -> np.ndarray:
    if hasattr(paths, "interactions"):
        return drjit_to_numpy(paths.interactions)
    objects = drjit_to_numpy(paths.objects)
    types = drjit_to_numpy(getattr(paths, "types", np.array([]))).reshape(-1)
    obj_arr = np.asarray(objects)
    if obj_arr.size == 0:
        return np.zeros_like(obj_arr, dtype=np.int64)
    reshaped_objects = obj_arr.reshape(obj_arr.shape[0], -1)
    interactions = np.zeros_like(reshaped_objects, dtype=np.int64)
    for path_idx in range(reshaped_objects.shape[1]):
        code = path_type_to_interaction_code(int(types[path_idx])) if path_idx < types.size else 0
        interactions[:, path_idx] = np.where(reshaped_objects[:, path_idx] >= 0, code, 0)
    return interactions.reshape(obj_arr.shape).astype(np.int64)


def path_objects(paths: Any) -> np.ndarray:
    raw = drjit_to_numpy(paths.objects)
    if hasattr(paths, "interactions"):
        return raw
    arr = np.asarray(raw, dtype=np.int64)
    return np.where(arr >= 0, arr + 1, 0).astype(np.int64)


def save_path_metadata(path: Path, arrays: PathArrays) -> None:
    np.savez_compressed(
        path,
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


def save_npz_outputs(
    run_path: Path,
    arrays: PathArrays,
    per_element_arrays: PathArrays | None = None,
    noiseless_arrays: PathArrays | None = None,
) -> None:
    save_path_metadata(run_path / "paths_summary.npz", arrays)
    if per_element_arrays is not None:
        save_path_metadata(run_path / "paths_per_element.npz", per_element_arrays)
    np.savez_compressed(
        run_path / "cir.npz",
        a=arrays.a_cir,
        tau_s=arrays.tau_cir_s,
    )
    if noiseless_arrays is not None:
        np.savez_compressed(
            run_path / "cir_noiseless.npz",
            a=noiseless_arrays.a_cir,
            tau_s=noiseless_arrays.tau_cir_s,
        )


def run_metadata_only(config: dict[str, Any], output_root: str | Path) -> dict[str, Any]:
    run_path = prepare_run_dir(output_root, config["run_id"])
    write_yaml(run_path / "config.yaml", config)
    metadata = capture_environment()
    metadata["run_id"] = config["run_id"]
    metadata["status"] = "complete"
    write_json(run_path / "metadata.json", metadata)
    metrics = {
        "run_id": config["run_id"],
        "status": "complete",
        "mode": config.get("mode"),
        "completed_at_utc": utc_now(),
    }
    write_json(run_path / "metrics.json", metrics)
    append_runs_index(output_root, {
        "run_id": config["run_id"],
        "milestone": config.get("milestone"),
        "purpose": config.get("purpose"),
        "scene": config.get("scene"),
        "status": "complete",
        "completed_at_utc": metrics["completed_at_utc"],
    })
    return metrics


def run_experiment(config: dict[str, Any]) -> dict[str, Any]:
    output_root = config.get("archive", {}).get("output_root", "outputs/sionna_radar")
    mode = config.get("mode", "path_run")
    if mode == "metadata_only":
        return run_metadata_only(config, output_root)

    imports = _import_sionna()
    rt = imports["rt"]
    register_radar_array_pattern(rt)
    register_custom_gain_pattern(rt)
    load_scene = imports["load_scene"]
    run_path = prepare_run_dir(output_root, config["run_id"])
    write_yaml(run_path / "config.yaml", config)

    metadata = capture_environment()
    metadata["run_id"] = config["run_id"]
    metadata["started_at_utc"] = utc_now()

    scene_name = config.get("scene", "simple_reflector")
    path = scene_path(scene_name, rt)
    if path is None:
        raise ValueError("Only metadata_only mode supports scene=none")
    try:
        scene = load_scene(path, merge_shapes=False)
    except TypeError:
        scene = load_scene(path)
    scene.frequency = float(config["frequency_hz"])
    scene.bandwidth = float(config.get("bandwidth_hz", 1e9))

    material_summary = configure_materials(scene, config, imports)
    array_summary = configure_arrays(scene, config, imports)
    device_summary = configure_devices(scene, config, imports)
    geom_summary = scene_geometry_summary(scene)

    metadata.update({
        "scene_path": path,
        "scene_geometry": geom_summary,
        "materials": material_summary,
        "arrays": array_summary,
        "devices": device_summary,
        "frequency_hz": scalar_float(scene.frequency),
        "wavelength_m": scalar_float(scene.wavelength),
    })

    if mode == "array_metadata":
        metadata["status"] = "complete"
        write_json(run_path / "metadata.json", to_jsonable(metadata))
        metrics = {
            "run_id": config["run_id"],
            "status": "complete",
            "mode": mode,
            "rx_array_size": array_summary["rx_array_size"],
            "completed_at_utc": utc_now(),
        }
        write_json(run_path / "metrics.json", metrics)
        append_runs_index(output_root, {
            "run_id": config["run_id"],
            "milestone": config.get("milestone"),
            "purpose": config.get("purpose"),
            "scene": config.get("scene"),
            "status": "complete",
            "completed_at_utc": metrics["completed_at_utc"],
        })
        return metrics

    ps_cfg = config.get("path_solver", {})
    PathSolver = imports["PathSolver"]
    if PathSolver is not None:
        solver = PathSolver()
        with initial_ray_sampling(dict(ps_cfg.get("initial_ray_sampling", {}))) as sampling_summary:
            paths = solver(
                scene,
                max_depth=int(ps_cfg.get("max_depth", 1)),
                max_num_paths_per_src=int(ps_cfg.get("max_num_paths_per_src", 1_000_000)),
                samples_per_src=int(ps_cfg.get("samples_per_src", 100_000)),
                synthetic_array=bool(ps_cfg.get("synthetic_array", True)),
                los=bool(ps_cfg.get("los", False)),
                specular_reflection=bool(ps_cfg.get("specular_reflection", True)),
                diffuse_reflection=bool(ps_cfg.get("diffuse_reflection", False)),
                refraction=bool(ps_cfg.get("refraction", False)),
                diffraction=bool(ps_cfg.get("diffraction", False)),
                edge_diffraction=bool(ps_cfg.get("edge_diffraction", False)),
                seed=int(ps_cfg.get("seed", 1)),
            )
    else:
        scene.synthetic_array = bool(ps_cfg.get("synthetic_array", True))
        paths = scene.compute_paths(
            max_depth=int(ps_cfg.get("max_depth", 1)),
            num_samples=int(ps_cfg.get("samples_per_src", 100_000)),
            los=bool(ps_cfg.get("los", False)),
            reflection=bool(ps_cfg.get("specular_reflection", True)),
            diffraction=bool(ps_cfg.get("diffraction", False)),
            scattering=bool(ps_cfg.get("diffuse_reflection", False)),
            edge_diffraction=bool(ps_cfg.get("edge_diffraction", False)),
            scat_random_phases=True,
            check_scene=True,
        )
        sampling_summary = {
            "mode": "full_sphere",
            "solid_angle_sr": float(4.0 * np.pi),
            "solid_angle_fraction": 1.0,
            "diffuse_amplitude_correction": 1.0,
        }
    per_element_arrays = collect_path_arrays(paths)
    path_count = cir_path_count(per_element_arrays.a_cir)
    per_element_arrays.a_cir = correct_diffuse_cir_amplitudes(
        per_element_arrays.a_cir,
        per_element_arrays.interactions,
        path_count,
        sampling_summary,
    )
    noise_cfg = dict(config.get("cir_noise", {}) or {})
    noiseless_per_element = replace(per_element_arrays, a_cir=per_element_arrays.a_cir.copy())
    noisy_cir, noise_summary = inject_complex_awgn(
        per_element_arrays.a_cir,
        per_element_arrays.valid,
        enabled=bool(noise_cfg.get("enabled", False)),
        snr_db=float(noise_cfg.get("snr_db", 20.0)),
        seed=int(noise_cfg.get("seed", 1001)),
    )
    per_element_arrays.a_cir = noisy_cir
    arrays, collapsed_per_element_paths = canonicalize_path_arrays(per_element_arrays)
    noiseless_arrays, _ = canonicalize_path_arrays(noiseless_per_element)
    metadata["initial_ray_sampling"] = sampling_summary
    metadata["cir_noise"] = noise_summary
    metadata["path_layout"] = {
        "cir_path_count": path_count,
        "per_element_metadata_shape": list(per_element_arrays.tau_s.shape),
        "summary_metadata_shape": list(arrays.tau_s.shape),
        "per_element_archive": "paths_per_element.npz" if collapsed_per_element_paths else None,
    }
    save_npz_outputs(
        run_path,
        arrays,
        per_element_arrays if collapsed_per_element_paths else None,
        noiseless_arrays if noise_summary["enabled"] else None,
    )

    min_tau = float(config.get("range_processing", {}).get("min_valid_tau_s", 1e-10))
    path_summary = summarize_paths(arrays, min_valid_tau_s=min_tau)
    figures = save_basic_figures(run_path, arrays, config)

    expected = config.get("expected", {})
    checks = {}
    if "dominant_range_m" in expected and path_summary["dominant_range_m"] is not None:
        err = abs(path_summary["dominant_range_m"] - float(expected["dominant_range_m"]))
        tol = float(expected.get("dominant_range_tolerance_m", 0.3))
        checks["dominant_range_error_m"] = err
        checks["dominant_range_pass"] = bool(err <= tol)
        checks["dominant_range_tolerance_m"] = tol

    metrics = {
        "run_id": config["run_id"],
        "milestone": config.get("milestone"),
        "purpose": config.get("purpose"),
        "scene": scene_name,
        "mode": mode,
        "status": "complete",
        "completed_at_utc": utc_now(),
        "path_summary": path_summary,
        "checks": checks,
        "figures": figures,
        "cir_noise": noise_summary,
    }
    metadata["status"] = "complete"
    metadata["completed_at_utc"] = metrics["completed_at_utc"]
    write_json(run_path / "metadata.json", to_jsonable(metadata))
    write_json(run_path / "metrics.json", to_jsonable(metrics))

    append_runs_index(output_root, {
        "run_id": config["run_id"],
        "milestone": config.get("milestone"),
        "purpose": config.get("purpose"),
        "scene": scene_name,
        "status": "complete",
        "valid_path_count": path_summary.get("valid_path_count"),
        "range_min_m": path_summary.get("range_min_m"),
        "range_max_m": path_summary.get("range_max_m"),
        "dominant_range_m": path_summary.get("dominant_range_m"),
        "diffuse_path_count": path_summary.get("diffuse_path_count"),
        "specular_path_count": path_summary.get("specular_path_count"),
        "max_interaction_depth": path_summary.get("max_interaction_depth"),
        "completed_at_utc": metrics["completed_at_utc"],
    })
    return metrics
