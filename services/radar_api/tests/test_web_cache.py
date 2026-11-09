import json
from pathlib import Path

import numpy as np
import pandas as pd

from app.config import get_settings
from app.core.web_cache import build_web_cache


RUN_ID = "MM_C002full_Pp0_p0_BposY_S501_N500k"


def test_build_cache_one_run(tmp_path: Path) -> None:
    settings = get_settings()
    run_dir = settings.existing_campaign_root / "runs" / RUN_ID
    out_dir = build_web_cache(run_dir, tmp_path, top_k=50, diffuse_quota=10, interaction_top_k=100)

    expected = [
        "manifest.json",
        "scene_objects.json",
        "radar_pose.json",
        "top_paths.json",
        "first_interactions.parquet",
        "range_azimuth.json",
        "range_azimuth.bin",
        "range_elevation.json",
        "range_elevation.bin",
    ]
    for name in expected:
        assert (out_dir / name).exists(), name

    with (out_dir / "top_paths.json").open("r", encoding="utf-8") as f:
        top_paths = json.load(f)
    assert len(top_paths["paths"]) <= 110
    assert top_paths["selection"]["mode"] == "top_energy_global_with_gate_quota"
    assert top_paths["paths"][0]["path_id"] == 64824
    assert np.isfinite(top_paths["paths"][0]["aod_azimuth_deg"])
    assert np.isfinite(top_paths["paths"][0]["aod_elevation_deg"])
    leaked = [
        interaction.get("object_id")
        for path in top_paths["paths"]
        for interaction in path["interactions"]
        if interaction.get("object_id") == "object_4294967295"
    ]
    assert leaked == []

    interactions = pd.read_parquet(out_dir / "first_interactions.parquet")
    assert len(interactions) <= 200
    assert {"path_id", "x_m", "y_m", "z_m", "energy", "in_fov"}.issubset(interactions.columns)


def test_spectra_binary_roundtrip(tmp_path: Path) -> None:
    settings = get_settings()
    run_dir = settings.existing_campaign_root / "runs" / RUN_ID
    out_dir = build_web_cache(run_dir, tmp_path, top_k=10, diffuse_quota=0, interaction_top_k=10)

    with (out_dir / "range_azimuth.json").open("r", encoding="utf-8") as f:
        metadata = json.load(f)
    arr = np.fromfile(out_dir / "range_azimuth.bin", dtype=np.float32).reshape(metadata["shape"])
    original = np.load(run_dir / "radar_observation.npz", allow_pickle=False)["range_azimuth_power"].astype(np.float32)
    assert arr.shape == original.shape
    assert np.allclose(arr, original)
    assert len(metadata["range_edges_m"]) == arr.shape[0] + 1
    assert len(metadata["angle_edges_deg"]) == arr.shape[1] + 1


def test_build_cache_dynamic_interaction_depth(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "synthetic_depth_one"
    run_dir.mkdir(parents=True)
    metadata = {
        "run_id": "synthetic_depth_one",
        "devices": {
            "tx_position_m": [0.0, 0.0, 10.0],
            "rx_position_m": [0.1, 0.0, 10.0],
            "look_at_m": [10.0, 0.0, 10.0],
        },
        "scene_geometry": {
            "objects": {
                "building_A": {
                    "material": "itu_concrete",
                    "bbox_min": [9.0, -1.0, 0.0],
                    "bbox_max": [11.0, 1.0, 20.0],
                    "bbox_center": [10.0, 0.0, 10.0],
                    "surface_area": 100.0,
                    "vertex_count": 8,
                    "face_count": 12,
                }
            }
        },
    }
    metrics = {"run_id": "synthetic_depth_one", "radar_observation": {"fov": {}}}
    (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    np.savez_compressed(
        run_dir / "paths_summary.npz",
        tau_s=np.array([[[[1e-6]]]], dtype=np.float32),
        valid=np.array([[[[True]]]], dtype=bool),
        theta_r_rad=np.array([[[[np.pi / 2]]]], dtype=np.float32),
        phi_r_rad=np.array([[[[0.0]]]], dtype=np.float32),
        theta_t_rad=np.array([[[[np.pi / 2]]]], dtype=np.float32),
        phi_t_rad=np.array([[[[0.0]]]], dtype=np.float32),
        doppler_hz=np.array([[[[0.0]]]], dtype=np.float32),
        interactions=np.array([[[[1]]]], dtype=np.int64),
        objects=np.array([[[[1]]]], dtype=np.int64),
        vertices=np.array([[[[[10.0, 0.0, 10.0]]]]], dtype=np.float32),
    )
    np.savez_compressed(
        run_dir / "radar_observation.npz",
        range_azimuth_power=np.ones((2, 2), dtype=np.float32),
        range_elevation_power=np.ones((2, 2), dtype=np.float32),
        range_edges_m=np.array([0.0, 100.0, 200.0], dtype=np.float32),
        azimuth_edges_deg=np.array([-5.0, 0.0, 5.0], dtype=np.float32),
        elevation_edges_deg=np.array([-5.0, 0.0, 5.0], dtype=np.float32),
        fov_path_mask=np.array([True], dtype=bool),
        ranges_m=np.array([149.896], dtype=np.float32),
        aoa_azimuth_deg=np.array([0.0], dtype=np.float32),
        aoa_elevation_deg=np.array([0.0], dtype=np.float32),
        path_energy=np.array([1.0], dtype=np.float32),
    )

    out_dir = build_web_cache(run_dir, tmp_path / "cache", top_k=5, diffuse_quota=0, interaction_top_k=5)
    with (out_dir / "top_paths.json").open("r", encoding="utf-8") as f:
        top_paths = json.load(f)
    assert top_paths["paths"][0]["interactions"][0]["object_id"] == "building_A"
    interactions = pd.read_parquet(out_dir / "first_interactions.parquet")
    assert interactions.iloc[0]["object_id"] == "building_A"
