# 02 Data Contracts

## 1. Scene Manifest

File:

```text
outputs/radar_workbench/scenes/<scene_id>/scene_manifest.json
```

Schema:

```json
{
  "schema_version": "0.1.0",
  "scene_id": "scene_simple_street_canyon_builtin",
  "display_name": "Simple Street Canyon",
  "created_at_utc": "2026-07-01T00:00:00+00:00",
  "source_type": "builtin|pointcloud|mesh|proxy",
  "sionna_scene": {
    "available": true,
    "scene_name_or_path": "simple_street_canyon",
    "format": "builtin|mitsuba_xml"
  },
  "visual_assets": {
    "pointcloud": null,
    "mesh": null,
    "bbox": "processed/proxy_buildings.json"
  },
  "coordinate_system": {
    "units": "m",
    "up_axis": "z",
    "notes": "Sionna/Mitsuba scene coordinates"
  },
  "materials": ["brick", "concrete", "glass", "marble", "wood"],
  "bounds": {
    "min": [-93.97, -60.33, -0.03],
    "max": [92.43, 60.81, 50.94]
  }
}
```

## 2. Building/Object Geometry

File:

```text
scene_objects.json
```

Schema:

```json
{
  "objects": [
    {
      "object_id": "building_4",
      "kind": "building",
      "material": "marble",
      "bbox_min": [-15.119, 9.572, -0.031],
      "bbox_max": [16.002, 37.458, 50.944],
      "bbox_center": [0.442, 23.515, 25.457],
      "surface_area": 7751.53,
      "vertex_count": 1234,
      "face_count": 5678
    }
  ]
}
```

## 3. Radar Config

Schema:

```json
{
  "radar": {
    "center_m": [0.0, 0.0, 10.0],
    "tx_position_m": [0.0, -0.05, 10.0],
    "rx_position_m": [0.0, 0.05, 10.0],
    "look_at_m": [0.0, 30.0, 10.0],
    "tx_array": {"rows": 1, "cols": 1, "spacing_lambda": 0.5},
    "rx_array": {"rows": 16, "cols": 16, "spacing_lambda": 0.5}
  },
  "fov": {
    "az_center_deg": 90.0,
    "az_width_deg": 120.0,
    "el_min_deg": 0.0,
    "el_max_deg": 40.0
  },
  "propagation": {
    "frequency_hz": 28000000000.0,
    "bandwidth_hz": 1000000000.0,
    "max_depth": 2,
    "los": false,
    "specular_reflection": true,
    "diffuse_reflection": true
  },
  "scattering": {
    "enabled": true,
    "coefficient": 0.5,
    "pattern": "backscattering",
    "alpha_r": 20,
    "alpha_i": 20,
    "lambda": 0.3
  }
}
```

## 4. Run Summary

Frontend run list should not parse all run folders. Backend should return:

```json
{
  "run_id": "MM_C002full_Pp0_p0_BposY_S501_N500k",
  "pose_id": "Pp0_p0",
  "boresight_id": "BposY",
  "x_m": 0.0,
  "y_m": 0.0,
  "z_m": 10.0,
  "boresight_az_deg": 90.0,
  "boresight_el_deg": 0.0,
  "valid_path_count": 175423,
  "dominant_range_m": 9.5716,
  "fov_energy_fraction": 0.35585,
  "energy_in_fov": 2.149e-7,
  "status": "complete"
}
```

## 5. Top Paths Cache

File:

```text
web_cache/<run_id>/top_paths.json
```

Do not include every path. Use top-k plus optional sampled diffuse paths.

Schema:

```json
{
  "schema_version": "0.1.0",
  "run_id": "MM_C002full_Pp0_p0_BposY_S501_N500k",
  "selection": {
    "mode": "top_energy_in_fov",
    "top_k": 500,
    "include_diffuse_tail": true
  },
  "paths": [
    {
      "path_id": 64824,
      "kind": "specular|diffuse|mixed",
      "depth": 1,
      "range_m": 9.5716,
      "delay_s": 6.385e-8,
      "energy": 8.96e-8,
      "aoa_azimuth_deg": 90.0,
      "aoa_elevation_deg": 0.0,
      "aod_azimuth_deg": 90.0,
      "aod_elevation_deg": 0.0,
      "in_fov": true,
      "interactions": [
        {
          "depth_index": 0,
          "type": "specular",
          "object_id": "building_4",
          "position_m": [0.0, 9.5716, 10.0]
        }
      ],
      "polyline_m": [
        [0.0, -0.05, 10.0],
        [0.0, 9.5716, 10.0],
        [0.0, 0.05, 10.0]
      ]
    }
  ]
}
```

## 6. Interaction Points Cache

File:

```text
web_cache/<run_id>/first_interactions.parquet
```

Columns:

| Column | Type |
|---|---|
| `path_id` | int64 |
| `depth_index` | int16 |
| `interaction_type` | string |
| `object_id` | string |
| `x_m`, `y_m`, `z_m` | float32 |
| `range_m` | float32 |
| `energy` | float32 |
| `energy_db` | float32 |
| `in_fov` | bool |

For frontend map display, backend should provide filtered endpoints:

```http
GET /api/results/{run_id}/interactions?mode=first&top_k=20000
```

## 7. Spectra Cache

Recommended lightweight metadata + binary array:

```text
range_azimuth.json
range_azimuth.bin
range_elevation.json
range_elevation.bin
```

Metadata:

```json
{
  "array_file": "range_azimuth.bin",
  "dtype": "float32",
  "shape": [1334, 180],
  "layout": "row-major",
  "range_edges_m": [0.0, 0.15, "..."],
  "angle_edges_deg": [-180.0, -178.0, "..."],
  "scale": "linear_power",
  "recommended_display": {
    "scale": "db",
    "dynamic_range_db": 60
  }
}
```

Reason:

1. JSON for full spectra is too verbose.
2. Float32 binary is easy to load and convert to texture.
3. Metadata keeps axes explicit.

## 8. Job Status

File:

```text
outputs/radar_workbench/jobs/<job_id>/status.json
```

Schema:

```json
{
  "job_id": "job_20260701_091122_abcd",
  "status": "queued|running|complete|failed|cancelled",
  "created_at_utc": "...",
  "started_at_utc": "...",
  "completed_at_utc": null,
  "progress": {
    "total_tasks": 30,
    "completed_tasks": 17,
    "failed_tasks": 0
  },
  "gpu_ids": [0, 1, 2, 3],
  "current_tasks": [
    {"gpu_id": 0, "run_id": "WEB_...", "status": "running"}
  ],
  "result": {
    "campaign_id": "camp_...",
    "output_root": "outputs/radar_workbench/campaigns/camp_..."
  },
  "error": null
}
```
