# 03 API Contracts

## 1. API Principles

1. Frontend never reads arbitrary filesystem paths directly.
2. Backend exposes scene/campaign/run IDs and validates all paths.
3. Large arrays should be served as binary or pre-computed images/textures.
4. Long-running Sionna jobs are asynchronous.
5. All simulation endpoints are radar sensing only by default.

## 2. Scene Endpoints

### `GET /api/scenes`

Returns scene list.

Response:

```json
{
  "scenes": [
    {
      "scene_id": "scene_simple_street_canyon_builtin",
      "display_name": "Simple Street Canyon",
      "source_type": "builtin",
      "simulation_ready": true,
      "has_pointcloud": false,
      "has_mesh": true,
      "bounds": {"min": [-94, -61, -1], "max": [93, 61, 51]}
    }
  ]
}
```

### `GET /api/scenes/{scene_id}/objects`

Returns bbox/material objects for visualization.

### `POST /api/scenes/upload`

Upload point cloud or mesh.

MVP rule:

| File Type | MVP |
|---|---|
| `.json` bbox/proxy | supported |
| `.ply` point cloud | optional visualization-only |
| `.obj/.glb` mesh | optional visualization-only |
| `.las/.laz` | defer until `laspy` installed |

### `POST /api/scenes/{scene_id}/convert`

Converts visualization scene into simulation-ready proxy/mesh.

MVP response can be:

```json
{
  "status": "not_implemented",
  "reason": "Point-cloud-to-Mitsuba conversion is Phase 4"
}
```

## 3. Campaign Endpoints

### `GET /api/campaigns`

Returns known campaign roots, including existing outputs:

```json
{
  "campaigns": [
    {
      "campaign_id": "c002_full_existing",
      "display_name": "C002 Full Radar Sensing",
      "root": "outputs/sionna_radar_campaigns/C002_full_radar_sensing",
      "run_count": 30,
      "readonly": true
    }
  ]
}
```

### `GET /api/campaigns/{campaign_id}/runs`

Returns run summaries from `POSE_METRICS.csv`.

### `GET /api/campaigns/{campaign_id}/summary`

Returns summary metrics and heatmap-ready arrays.

## 4. Run/Result Endpoints

### `GET /api/results/{run_id}/metadata`

Returns:

```json
{
  "run_id": "...",
  "config": {},
  "metrics": {},
  "scene_objects": {},
  "available_artifacts": {
    "top_paths": true,
    "first_interactions": true,
    "range_azimuth": true,
    "range_elevation": true,
    "cir": false
  }
}
```

### `GET /api/results/{run_id}/paths`

Query parameters:

| Parameter | Default | Meaning |
|---|---:|---|
| `top_k` | 500 | Max paths to return |
| `kind` | `all` | `all/specular/diffuse/mixed` |
| `in_fov` | true | Only paths in FoV |
| `min_energy_db` | null | Optional threshold |
| `depth` | null | 1 or 2 |

### `GET /api/results/{run_id}/interactions`

Query parameters:

| Parameter | Default |
|---|---:|
| `mode` | `first` |
| `top_k` | 20000 |
| `in_fov` | true |
| `kind` | `all` |

### `GET /api/results/{run_id}/range_azimuth`

Options:

```http
GET /api/results/{run_id}/range_azimuth?format=json
GET /api/results/{run_id}/range_azimuth?format=binary
GET /api/results/{run_id}/range_azimuth?format=png
```

MVP can start with JSON metadata + base64/PNG, then move to binary.

### `GET /api/results/{run_id}/range_elevation`

Same as range-azimuth.

## 5. Simulation Endpoints

### `POST /api/simulations`

Creates a job.

Request:

```json
{
  "scene_id": "scene_simple_street_canyon_builtin",
  "mode": "single_pose",
  "gpu_ids": [0, 1, 2, 3],
  "radar": {
    "center_m": [0.0, 0.0, 10.0],
    "look_at_m": [0.0, 30.0, 10.0],
    "tx_rx_baseline_m": 0.1,
    "tx_array": {"rows": 1, "cols": 1},
    "rx_array": {"rows": 16, "cols": 16}
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
    "lambda_": 0.3
  },
  "observation": {
    "az_width_deg": 120.0,
    "el_min_deg": 0.0,
    "el_max_deg": 40.0,
    "rmax_m": 200.0,
    "range_bin_m": 0.15,
    "angle_bin_deg": 2.0
  },
  "compute": {
    "samples_per_src": 500000,
    "seed": 501
  }
}
```

Response:

```json
{
  "job_id": "job_20260701_091122_abcd",
  "status": "queued",
  "status_url": "/api/simulations/job_20260701_091122_abcd"
}
```

### `GET /api/simulations/{job_id}`

Returns `status.json`.

### `GET /api/simulations/{job_id}/events`

Use Server-Sent Events or WebSocket for live progress.

Event example:

```json
{
  "type": "task_complete",
  "job_id": "job_...",
  "gpu_id": 2,
  "run_id": "WEB_...",
  "completed_tasks": 12,
  "total_tasks": 30,
  "elapsed_s": 18.4
}
```

### `POST /api/simulations/{job_id}/cancel`

Cancellation behavior:

1. Mark status as `cancelling`.
2. Stop queued tasks.
3. Let currently running Sionna task finish or terminate worker based on policy.
4. Mark final status `cancelled`.

## 6. Error Response Contract

All API errors:

```json
{
  "error": {
    "code": "INVALID_RADAR_CONFIG",
    "message": "Radar z must be above ground.",
    "details": {
      "field": "radar.center_m[2]",
      "value": -1.0
    }
  }
}
```

Common error codes:

| Code | Meaning |
|---|---|
| `SCENE_NOT_SIMULATION_READY` | Point cloud lacks mesh/proxy scene |
| `INVALID_RADAR_CONFIG` | Pose/FoV/frequency invalid |
| `GPU_UNAVAILABLE` | Requested GPU not available |
| `JOB_NOT_FOUND` | Unknown job |
| `RUN_NOT_FOUND` | Unknown run |
| `CACHE_NOT_READY` | Result exists but web cache missing |
| `SIONNA_RUN_FAILED` | Worker failed during simulation |

## 7. Validation Rules

Backend must reject:

1. `los=true` by default for radar sensing unless advanced override is explicitly enabled.
2. `rx_array` not 16x16 if user selected baseline experiment mode.
3. `max_depth > 4` without warning, because runtime can explode.
4. `samples_per_src > 2e6` without explicit high-cost confirmation.
5. GPU IDs outside allowed set `[0,1,2,3]` for this deployment.
6. Scene without simulation-ready geometry for simulation requests.
