from __future__ import annotations

import csv
import json
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from app.core.scene_object_mapping import object_index_map
from app.core.path_layout import ensure_canonical_path_archive


SPEED_OF_LIGHT = 299_792_458.0
UNKNOWN_OBJECT_SENTINEL = 2**32 - 1


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def normalize_object_id(raw: int, mapping: dict[int, str]) -> str | None:
    value = int(raw)
    if value in (0, UNKNOWN_OBJECT_SENTINEL):
        return None
    return mapping.get(value, f"object_{value}")


def interaction_type(value: int) -> str:
    if int(value) == 1:
        return "specular"
    if int(value) == 2:
        return "diffuse"
    if int(value) == 4:
        return "refraction"
    if int(value) == 8:
        return "diffraction"
    return "unknown"


def path_kind(interactions: np.ndarray) -> str:
    active = {interaction_type(int(value)) for value in interactions if int(value) != 0}
    if not active:
        return "direct_or_empty"
    if len(active) == 1:
        return next(iter(active))
    return "mixed"


def canonical_azimuth_deg(phi_rad: np.ndarray) -> np.ndarray:
    deg = np.rad2deg(phi_rad)
    return (deg + 180.0) % 360.0 - 180.0


def elevation_from_zenith(theta_rad: np.ndarray) -> np.ndarray:
    return 90.0 - np.rad2deg(theta_rad)


def reshape_depth_path(arr: np.ndarray, path_count: int) -> np.ndarray:
    arr = np.asarray(arr)
    if arr.size == 0:
        return np.zeros((0, path_count), dtype=np.int64)
    if arr.shape[-1] == path_count:
        return arr.reshape(-1, path_count)
    if arr.shape[0] == path_count:
        return arr.reshape(path_count, -1).T
    return arr.reshape(-1, path_count)


def flatten_path_vector(arr: np.ndarray) -> np.ndarray:
    return np.asarray(arr).reshape(-1)


def observation_arrays(run_dir: Path, valid_indices: np.ndarray, raw_count: int) -> dict[str, np.ndarray]:
    obs_path = run_dir / "radar_observation.npz"
    energy = np.ones(raw_count, dtype=np.float64)
    in_gate = np.zeros(raw_count, dtype=bool)
    if not obs_path.exists():
        return {"energy": energy, "in_analysis_gate": in_gate}
    obs = np.load(obs_path, allow_pickle=False)
    if "path_energy" in obs:
        values = obs["path_energy"].reshape(-1).astype(np.float64)
        if values.size == raw_count:
            energy = values
        elif values.size == valid_indices.size:
            energy[:] = 0.0
            energy[valid_indices] = values
    if "fov_path_mask" in obs:
        values = obs["fov_path_mask"].reshape(-1).astype(bool)
        if values.size == raw_count:
            in_gate = values
        elif values.size == valid_indices.size:
            in_gate[valid_indices] = values
    return {"energy": energy, "in_analysis_gate": in_gate}


def build_path_statistics(run_dir: Path) -> dict[str, Any]:
    ensure_canonical_path_archive(run_dir)
    metadata = read_json(run_dir / "metadata.json")
    metrics = read_json(run_dir / "metrics.json")
    paths = np.load(run_dir / "paths_summary.npz", allow_pickle=False)

    tau = flatten_path_vector(paths["tau_s"]).astype(np.float64)
    raw_count = tau.size
    valid = flatten_path_vector(paths["valid"]).astype(bool)
    valid = valid & np.isfinite(tau) & (tau > 1e-10)
    valid_indices = np.flatnonzero(valid)
    interactions = reshape_depth_path(paths["interactions"], raw_count).astype(np.int64)
    objects = reshape_depth_path(paths["objects"], raw_count).astype(np.int64)
    theta_r = flatten_path_vector(paths["theta_r_rad"])
    phi_r = flatten_path_vector(paths["phi_r_rad"])
    theta_t = flatten_path_vector(paths["theta_t_rad"])
    phi_t = flatten_path_vector(paths["phi_t_rad"])
    obs = observation_arrays(run_dir, valid_indices, raw_count)
    energy = obs["energy"]
    in_gate = obs["in_analysis_gate"] & valid
    obj_map = object_index_map(metadata)

    path_rows: list[dict[str, Any]] = []
    object_counter: dict[str, Counter] = defaultdict(Counter)
    depth_counter: Counter = Counter()
    kind_counter: Counter = Counter()
    gate_depth_counter: Counter = Counter()
    gate_kind_counter: Counter = Counter()
    touched_pairs: Counter = Counter()

    for path_id in valid_indices:
        path_interactions = interactions[:, path_id]
        path_objects = objects[:, path_id]
        active_depths = [i for i, value in enumerate(path_interactions) if int(value) != 0]
        depth = len(active_depths)
        kind = path_kind(path_interactions)
        touched_objects = []
        first_object = None
        first_type = None
        for depth_idx in active_depths:
            object_id = normalize_object_id(path_objects[depth_idx], obj_map)
            inter_type = interaction_type(int(path_interactions[depth_idx]))
            if object_id:
                touched_objects.append(object_id)
                object_counter[object_id]["touching_path_count"] += 1
                object_counter[object_id]["touching_energy"] += float(energy[path_id])
                if in_gate[path_id]:
                    object_counter[object_id]["analysis_gate_path_count"] += 1
                    object_counter[object_id]["analysis_gate_energy"] += float(energy[path_id])
            if first_object is None and object_id:
                first_object = object_id
                first_type = inter_type
        if first_object:
            object_counter[first_object]["first_interaction_path_count"] += 1
            object_counter[first_object][f"first_{first_type}_path_count"] += 1
        unique_touched = sorted(set(touched_objects))
        if len(unique_touched) >= 2:
            touched_pairs[" + ".join(unique_touched)] += 1

        depth_counter[str(depth)] += 1
        kind_counter[kind] += 1
        if in_gate[path_id]:
            gate_depth_counter[str(depth)] += 1
            gate_kind_counter[kind] += 1

        path_rows.append(
            {
                "path_id": int(path_id),
                "depth": depth,
                "kind": kind,
                "range_m": float(SPEED_OF_LIGHT * tau[path_id] / 2.0),
                "delay_s": float(tau[path_id]),
                "energy": float(energy[path_id]),
                "energy_db": float(10.0 * np.log10(max(float(energy[path_id]), 1e-300))),
                "in_analysis_gate": bool(in_gate[path_id]),
                "aoa_azimuth_deg": float(canonical_azimuth_deg(np.asarray([phi_r[path_id]]))[0]),
                "aoa_elevation_deg": float(elevation_from_zenith(np.asarray([theta_r[path_id]]))[0]),
                "aod_azimuth_deg": float(canonical_azimuth_deg(np.asarray([phi_t[path_id]]))[0]),
                "aod_elevation_deg": float(elevation_from_zenith(np.asarray([theta_t[path_id]]))[0]),
                "first_object_id": first_object,
                "touched_object_ids": ";".join(unique_touched),
            }
        )

    object_rows = []
    for object_id, counts in sorted(object_counter.items()):
        object_rows.append(
            {
                "object_id": object_id,
                "touching_path_count": int(counts["touching_path_count"]),
                "touching_energy": float(counts["touching_energy"]),
                "analysis_gate_path_count": int(counts["analysis_gate_path_count"]),
                "analysis_gate_energy": float(counts["analysis_gate_energy"]),
                "first_interaction_path_count": int(counts["first_interaction_path_count"]),
                "first_specular_path_count": int(counts["first_specular_path_count"]),
                "first_diffuse_path_count": int(counts["first_diffuse_path_count"]),
            }
        )

    summary = {
        "schema_version": "0.3.0",
        "run_id": run_dir.name,
        "created_at_utc": utc_now(),
        "source_run_dir": str(run_dir),
        "valid_path_count": int(valid.sum()),
        "raw_path_count": int(raw_count),
        "analysis_gate_path_count": int(in_gate.sum()),
        "analysis_gate_energy": float(np.sum(energy[in_gate])),
        "total_energy": float(np.sum(energy[valid])),
        "path_count_by_depth": dict(depth_counter),
        "path_count_by_kind": dict(kind_counter),
        "analysis_gate_path_count_by_depth": dict(gate_depth_counter),
        "analysis_gate_path_count_by_kind": dict(gate_kind_counter),
        "path_count_by_object_pair": dict(touched_pairs),
        "object_statistics": object_rows,
        "metrics_radar_observation": metrics.get("radar_observation", {}),
    }
    return {"summary": summary, "paths": path_rows, "objects": object_rows}


def write_statistics_artifacts(run_dir: Path) -> dict[str, str]:
    stats = build_path_statistics(run_dir)
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "path_statistics": analysis_dir / "path_statistics.json",
        "paths": analysis_dir / "paths.csv",
        "building_path_statistics": analysis_dir / "building_path_statistics.csv",
    }
    write_json(files["path_statistics"], stats["summary"])
    write_csv(
        files["paths"],
        stats["paths"],
        [
            "path_id",
            "depth",
            "kind",
            "range_m",
            "delay_s",
            "energy",
            "energy_db",
            "in_analysis_gate",
            "aoa_azimuth_deg",
            "aoa_elevation_deg",
            "aod_azimuth_deg",
            "aod_elevation_deg",
            "first_object_id",
            "touched_object_ids",
        ],
    )
    write_csv(
        files["building_path_statistics"],
        stats["objects"],
        [
            "object_id",
            "touching_path_count",
            "touching_energy",
            "analysis_gate_path_count",
            "analysis_gate_energy",
            "first_interaction_path_count",
            "first_specular_path_count",
            "first_diffuse_path_count",
        ],
    )
    return {key: str(value) for key, value in files.items()}


def build_result_bundle(run_dir: Path, bundle_root: Path) -> Path:
    files = write_statistics_artifacts(run_dir)
    from app.core.mpc_analysis import build_mpc_analysis_artifacts

    build_mpc_analysis_artifacts(run_dir)
    bundle_root.mkdir(parents=True, exist_ok=True)
    zip_path = bundle_root / f"{run_dir.name}_result_bundle.zip"
    manifest = {
        "schema_version": "0.2.0",
        "run_id": run_dir.name,
        "created_at_utc": utc_now(),
        "source_run_dir": str(run_dir),
        "included_files": [],
    }
    candidates = [
        "config.yaml",
        "metadata.json",
        "metrics.json",
        "paths_summary.npz",
        "paths_per_element.npz",
        "radar_observation.npz",
        "cir.npz",
        "cir_noiseless.npz",
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in candidates:
            path = run_dir / name
            if path.exists():
                arcname = f"raw/{name}" if path.suffix == ".npz" else f"configs/{name}"
                zf.write(path, arcname)
                manifest["included_files"].append(arcname)
        for key, value in files.items():
            path = Path(value)
            arcname = f"analysis/{path.name}"
            zf.write(path, arcname)
            manifest["included_files"].append(arcname)
        included = set(manifest["included_files"])
        analysis_dir = run_dir / "analysis"
        if analysis_dir.exists():
            for path in sorted(analysis_dir.iterdir()):
                if not path.is_file():
                    continue
                arcname = f"analysis/{path.name}"
                if arcname in included:
                    continue
                zf.write(path, arcname)
                manifest["included_files"].append(arcname)
                included.add(arcname)
        figures = run_dir / "figures"
        if figures.exists():
            for path in sorted(figures.glob("*.png")):
                arcname = f"figures/{path.name}"
                zf.write(path, arcname)
                manifest["included_files"].append(arcname)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True))
    return zip_path
