from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from app.core.scene_object_mapping import object_index_map
from app.core.path_layout import ensure_canonical_path_archive


SCHEMA_VERSION = "0.5.0"
UNKNOWN_OBJECT_SENTINEL = 2**32 - 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def normalize_object_id(raw: int, mapping: dict[int, str]) -> str | None:
    value = int(raw)
    if value in (0, UNKNOWN_OBJECT_SENTINEL):
        return None
    return mapping.get(value, f"object_{value}")


def interaction_kind(values: np.ndarray) -> str:
    active = {int(v) for v in values if int(v) != 0}
    if active == {1}:
        return "specular"
    if active == {2}:
        return "diffuse"
    if active == {1, 2}:
        return "mixed"
    return "unknown"


def interaction_type(value: int) -> str:
    if int(value) == 1:
        return "specular"
    if int(value) == 2:
        return "diffuse"
    return "unknown"


def bin_index(value: float, edges: np.ndarray) -> int | None:
    idx = int(np.searchsorted(edges, value, side="right") - 1)
    if idx < 0 or idx >= len(edges) - 1:
        return None
    return idx


def reshape_depth_path(arr: np.ndarray, path_count: int) -> np.ndarray:
    values = np.asarray(arr)
    if values.size == 0:
        return np.zeros((0, path_count), dtype=np.int64)
    if values.shape[-1] == path_count:
        return values.reshape(-1, path_count)
    if values.shape[0] == path_count:
        return values.reshape(path_count, -1).T
    return values.reshape(-1, path_count)


def reshape_vertices(arr: np.ndarray, path_count: int) -> np.ndarray:
    values = np.asarray(arr)
    if values.size == 0 or values.shape[-1] != 3:
        return np.zeros((0, path_count, 3), dtype=np.float64)
    if values.shape[-2] == path_count:
        return values.reshape(-1, path_count, 3)
    if values.shape[0] == path_count:
        return values.reshape(path_count, -1, 3).transpose(1, 0, 2)
    return values.reshape(-1, path_count, 3)


def expand_observation_vector(values: np.ndarray, valid: np.ndarray, fill_value: Any) -> np.ndarray:
    arr = np.asarray(values).reshape(-1)
    if arr.size == valid.size:
        return arr
    if arr.size == int(valid.sum()):
        out = np.full(valid.size, fill_value, dtype=arr.dtype)
        out[valid] = arr
        return out
    return np.resize(arr, valid.size)


def optional_path_vector(paths_npz: np.lib.npyio.NpzFile, key: str, path_count: int) -> np.ndarray:
    """Read optional per-path metadata without making legacy archives unusable."""
    out = np.full(path_count, np.nan, dtype=np.float64)
    if key not in paths_npz.files:
        return out
    values = np.asarray(paths_npz[key], dtype=np.float64).reshape(-1)
    copy_count = min(values.size, path_count)
    out[:copy_count] = values[:copy_count]
    return out


def build_scene_objects(metadata: dict[str, Any], scene_geometry: dict[str, Any] | None = None) -> dict[str, Any]:
    objects = metadata.get("scene_geometry", {}).get("objects", {})
    configured = {}
    if scene_geometry:
        ground = scene_geometry.get("ground")
        if ground:
            configured["floor"] = {"geometry_kind": "box", **ground}
        configured.update({str(item.get("id")): item for item in scene_geometry.get("buildings", [])})
    return {
        "schema_version": SCHEMA_VERSION,
        "objects": [{"object_id": object_id, **obj, **configured.get(object_id, {})} for object_id, obj in objects.items()],
    }


def build_radar_pose(metadata: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    devices = metadata.get("devices", {})
    fov = metrics.get("radar_observation", {}).get("fov", {})
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": metadata.get("run_id"),
        "tx_position_m": devices.get("tx_position_m"),
        "rx_position_m": devices.get("rx_position_m"),
        "look_at_m": devices.get("look_at_m"),
        "tx_orientation_rad": devices.get("tx_orientation_rad"),
        "rx_orientation_rad": devices.get("rx_orientation_rad"),
        "fov": fov,
    }


def select_top_path_indices(
    valid: np.ndarray,
    fov: np.ndarray,
    energy: np.ndarray,
    interactions: np.ndarray,
    top_k: int,
    diffuse_quota: int,
) -> np.ndarray:
    selected: list[int] = []
    existing: set[int] = set()

    def append_ranked(candidates: np.ndarray, limit: int) -> None:
        if candidates.size == 0 or limit <= 0:
            return
        order = candidates[np.argsort(-energy[candidates])]
        added = 0
        for idx in order:
            idx_int = int(idx)
            if idx_int in existing:
                continue
            selected.append(idx_int)
            existing.add(idx_int)
            added += 1
            if added >= limit:
                break

    valid_idx = np.flatnonzero(valid)
    append_ranked(valid_idx, top_k)
    append_ranked(np.flatnonzero(valid & fov), top_k)
    if diffuse_quota > 0:
        diffuse_mask = np.any(interactions == 2, axis=0)
        append_ranked(np.flatnonzero(valid & diffuse_mask), diffuse_quota)
    return np.array(selected[: (2 * top_k) + diffuse_quota], dtype=np.int64)


def path_polyline(
    tx: list[float] | None,
    rx: list[float] | None,
    vertices: np.ndarray,
    interactions: np.ndarray,
) -> list[list[float]]:
    polyline: list[list[float]] = []
    if tx is not None:
        polyline.append([float(v) for v in tx])
    for depth, interaction in enumerate(interactions):
        if int(interaction) != 0:
            polyline.append([float(v) for v in vertices[depth]])
    if rx is not None:
        polyline.append([float(v) for v in rx])
    return polyline


def build_top_paths(
    run_id: str,
    metadata: dict[str, Any],
    paths_npz: np.lib.npyio.NpzFile,
    obs_npz: np.lib.npyio.NpzFile,
    top_k: int,
    diffuse_quota: int,
) -> dict[str, Any]:
    valid = paths_npz["valid"].reshape(-1).astype(bool)
    tau_s = paths_npz["tau_s"].reshape(-1)
    path_count = tau_s.size
    interactions = reshape_depth_path(paths_npz["interactions"], path_count)
    objects = reshape_depth_path(paths_npz["objects"], path_count)
    vertices = reshape_vertices(paths_npz["vertices"], path_count)
    fov = expand_observation_vector(obs_npz["fov_path_mask"], valid, False).astype(bool)
    energy = expand_observation_vector(obs_npz["path_energy"], valid, 0.0).astype(float)
    ranges = expand_observation_vector(obs_npz["ranges_m"], valid, 0.0).astype(float)
    azimuth = expand_observation_vector(obs_npz["aoa_azimuth_deg"], valid, 0.0).astype(float)
    elevation = expand_observation_vector(obs_npz["aoa_elevation_deg"], valid, 0.0).astype(float)
    phi_t = optional_path_vector(paths_npz, "phi_t_rad", path_count)
    theta_t = optional_path_vector(paths_npz, "theta_t_rad", path_count)
    aod_azimuth = (np.rad2deg(phi_t) + 180.0) % 360.0 - 180.0
    aod_elevation = 90.0 - np.rad2deg(theta_t)
    range_edges = obs_npz["range_edges_m"]
    az_edges = obs_npz["azimuth_edges_deg"]
    el_edges = obs_npz["elevation_edges_deg"]
    selected = select_top_path_indices(valid, fov, energy, interactions, top_k, diffuse_quota)
    obj_map = object_index_map(metadata)
    devices = metadata.get("devices", {})
    tx = devices.get("tx_position_m")
    rx = devices.get("rx_position_m")

    path_items: list[dict[str, Any]] = []
    for idx in selected:
        idx_int = int(idx)
        ints = []
        for depth in range(interactions.shape[0]):
            interaction = int(interactions[depth, idx_int])
            if interaction == 0:
                continue
            ints.append(
                {
                    "depth_index": depth,
                    "type": interaction_type(interaction),
                    "object_id": normalize_object_id(objects[depth, idx_int], obj_map),
                    "position_m": [float(v) for v in vertices[depth, idx_int]],
                }
            )
        item = {
            "path_id": idx_int,
            "kind": interaction_kind(interactions[:, idx_int]),
            "depth": int(np.count_nonzero(interactions[:, idx_int])),
            "range_m": float(ranges[idx_int]),
            "delay_s": float(tau_s[idx_int]),
            "energy": float(energy[idx_int]),
            "aoa_azimuth_deg": float(azimuth[idx_int]),
            "aoa_elevation_deg": float(elevation[idx_int]),
            "aod_azimuth_deg": float(aod_azimuth[idx_int]) if np.isfinite(aod_azimuth[idx_int]) else None,
            "aod_elevation_deg": float(aod_elevation[idx_int]) if np.isfinite(aod_elevation[idx_int]) else None,
            "in_fov": bool(fov[idx_int]),
            "range_bin_idx": bin_index(float(ranges[idx_int]), range_edges),
            "azimuth_bin_idx": bin_index(float(azimuth[idx_int]), az_edges),
            "elevation_bin_idx": bin_index(float(elevation[idx_int]), el_edges),
            "interactions": ints,
            "polyline_m": path_polyline(tx, rx, vertices[:, idx_int, :], interactions[:, idx_int]),
        }
        path_items.append(item)

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "selection": {
            "mode": "top_energy_global_with_gate_quota",
            "top_k": int(top_k),
            "diffuse_quota": int(diffuse_quota),
            "valid_path_count": int(valid.sum()),
            "fov_path_count": int((valid & fov).sum()),
        },
        "paths": path_items,
    }


def build_interactions_table(
    metadata: dict[str, Any],
    paths_npz: np.lib.npyio.NpzFile,
    obs_npz: np.lib.npyio.NpzFile,
    top_k: int,
) -> pd.DataFrame:
    valid = paths_npz["valid"].reshape(-1).astype(bool)
    path_count = paths_npz["tau_s"].reshape(-1).size
    interactions = reshape_depth_path(paths_npz["interactions"], path_count)
    objects = reshape_depth_path(paths_npz["objects"], path_count)
    vertices = reshape_vertices(paths_npz["vertices"], path_count)
    fov = expand_observation_vector(obs_npz["fov_path_mask"], valid, False).astype(bool)
    energy = expand_observation_vector(obs_npz["path_energy"], valid, 0.0).astype(float)
    ranges = expand_observation_vector(obs_npz["ranges_m"], valid, 0.0).astype(float)
    selected: list[int] = []
    existing: set[int] = set()

    def append_ranked(candidates: np.ndarray, limit: int) -> None:
        if candidates.size == 0 or limit <= 0:
            return
        order = candidates[np.argsort(-energy[candidates])]
        added = 0
        for idx in order:
            idx_int = int(idx)
            if idx_int in existing:
                continue
            selected.append(idx_int)
            existing.add(idx_int)
            added += 1
            if added >= limit:
                break

    has_interaction = interactions[0] != 0
    append_ranked(np.flatnonzero(valid & has_interaction), top_k)
    append_ranked(np.flatnonzero(valid & fov & has_interaction), top_k)
    candidates = np.asarray(selected, dtype=np.int64)
    obj_map = object_index_map(metadata)
    rows: list[dict[str, Any]] = []
    for idx in candidates:
        idx_int = int(idx)
        depth = 0
        raw_object = int(objects[depth, idx_int])
        object_id = normalize_object_id(raw_object, obj_map)
        point = vertices[depth, idx_int]
        e = float(energy[idx_int])
        rows.append(
            {
                "path_id": idx_int,
                "depth_index": depth,
                "interaction_type": interaction_type(int(interactions[depth, idx_int])),
                "object_id": object_id,
                "x_m": float(point[0]),
                "y_m": float(point[1]),
                "z_m": float(point[2]),
                "range_m": float(ranges[idx_int]),
                "energy": e,
                "energy_db": float(10 * np.log10(max(e, np.finfo(np.float32).tiny))),
                "in_fov": bool(fov[idx_int]),
            }
        )
    return pd.DataFrame(rows)


def write_spectrum_cache(
    out_dir: Path,
    run_id: str,
    kind: str,
    array: np.ndarray,
    range_edges: np.ndarray,
    angle_edges: np.ndarray,
    angle_label: str,
) -> None:
    arr = np.asarray(array, dtype=np.float32)
    bin_path = out_dir / f"{kind}.bin"
    arr.tofile(bin_path)
    write_json(
        out_dir / f"{kind}.json",
        {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "kind": kind,
            "array_file": bin_path.name,
            "dtype": "float32",
            "shape": list(arr.shape),
            "layout": "row-major",
            "range_edges_m": [float(v) for v in range_edges],
            "angle_edges_deg": [float(v) for v in angle_edges],
            "angle_label": angle_label,
            "scale": "linear_power",
            "recommended_display": {"scale": "db", "dynamic_range_db": 60},
        },
    )


def build_web_cache(
    run_dir: Path,
    out_root: Path,
    top_k: int = 500,
    diffuse_quota: int = 100,
    interaction_top_k: int = 20000,
) -> Path:
    ensure_canonical_path_archive(run_dir)
    run_dir = run_dir.resolve()
    run_id = run_dir.name
    out_dir = out_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    metadata = read_json(run_dir / "metadata.json")
    metrics = read_json(run_dir / "metrics.json")
    config_path = run_dir / "config.yaml"
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}
    paths_npz = np.load(run_dir / "paths_summary.npz", allow_pickle=False)
    obs_npz = np.load(run_dir / "radar_observation.npz", allow_pickle=False)

    write_json(out_dir / "scene_objects.json", build_scene_objects(metadata, config.get("workbench", {}).get("scene_geometry")))
    write_json(out_dir / "radar_pose.json", build_radar_pose(metadata, metrics))
    write_json(
        out_dir / "top_paths.json",
        build_top_paths(run_id, metadata, paths_npz, obs_npz, top_k, diffuse_quota),
    )
    interactions = build_interactions_table(metadata, paths_npz, obs_npz, interaction_top_k)
    interactions.to_parquet(out_dir / "first_interactions.parquet", index=False)
    write_spectrum_cache(
        out_dir,
        run_id,
        "range_azimuth",
        obs_npz["range_azimuth_power"],
        obs_npz["range_edges_m"],
        obs_npz["azimuth_edges_deg"],
        "azimuth_deg",
    )
    write_spectrum_cache(
        out_dir,
        run_id,
        "range_elevation",
        obs_npz["range_elevation_power"],
        obs_npz["range_edges_m"],
        obs_npz["elevation_edges_deg"],
        "elevation_deg",
    )

    source_files = {}
    for name in ["metadata.json", "metrics.json", "paths_summary.npz", "radar_observation.npz"]:
        path = run_dir / name
        source_files[name] = {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
        }
    write_json(
        out_dir / "manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "source_run_dir": str(run_dir),
            "source_files": source_files,
            "created_at_utc": utc_now(),
            "generator": "radar_api.web_cache",
            "top_k": top_k,
            "diffuse_quota": diffuse_quota,
            "interaction_top_k": interaction_top_k,
        },
    )
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Build web cache for one radar run.")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--out-root", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=500)
    parser.add_argument("--diffuse-quota", type=int, default=100)
    parser.add_argument("--interaction-top-k", type=int, default=20000)
    args = parser.parse_args()
    out_dir = build_web_cache(
        args.run_dir,
        args.out_root,
        top_k=args.top_k,
        diffuse_quota=args.diffuse_quota,
        interaction_top_k=args.interaction_top_k,
    )
    print(out_dir)


if __name__ == "__main__":
    main()
