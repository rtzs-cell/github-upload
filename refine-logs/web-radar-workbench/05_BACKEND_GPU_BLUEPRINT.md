# 05 Backend and GPU Blueprint

## 1. Backend Modules

```text
services/radar_api/app/
  main.py
  config.py
  schemas.py
  paths.py
  api/
    scenes.py
    campaigns.py
    runs.py
    simulations.py
    results.py
  core/
    scene_registry.py
    campaign_registry.py
    result_loader.py
    web_cache.py
    sionna_config_builder.py
  workers/
    job_store.py
    gpu_scheduler.py
    simulation_worker.py
```

## 2. Backend Responsibilities

| Module | Responsibility |
|---|---|
| `scene_registry.py` | Register builtin/uploaded scenes, return manifests. |
| `campaign_registry.py` | Locate campaign roots and parse `POSE_METRICS.csv`. |
| `result_loader.py` | Load metrics, metadata, spectra, and path arrays. |
| `web_cache.py` | Convert NPZ outputs into frontend-friendly caches. |
| `sionna_config_builder.py` | Convert API request into Sionna run config. |
| `job_store.py` | Persist job status and events. |
| `gpu_scheduler.py` | Assign tasks to GPU0-3. |
| `simulation_worker.py` | Run Sionna tasks in isolated worker process. |

## 3. GPU Execution Model

Use already validated model:

```text
GPU IDs: [0, 1, 2, 3]
one worker process per GPU
CUDA_VISIBLE_DEVICES=<gpu_id>
worker serially executes assigned tasks
main process collects events
```

Why:

1. Avoid CUDA device switching after TensorFlow/Sionna initialization.
2. Avoid oversubscribing one GPU.
3. Match tested acceleration path: C002-full 489 s -> 135 s.

## 4. Job Lifecycle

```text
queued
  -> running
    -> complete
    -> failed
    -> cancelling -> cancelled
```

### Queued

Backend validates request and writes:

```text
jobs/<job_id>/job.json
jobs/<job_id>/status.json
jobs/<job_id>/task_manifest.json
```

### Running

Scheduler:

1. Creates campaign output folder.
2. Starts workers.
3. Updates `worker_events.jsonl`.
4. Updates `status.json`.

### Complete

Postprocess:

1. Writes `POSE_METRICS.csv`.
2. Writes campaign summary.
3. Builds web cache for each run.
4. Marks job complete.

### Failed

On failure:

1. Preserve completed run directories.
2. Store traceback in `logs.txt`.
3. Mark failed task in status.
4. Frontend shows actionable error.

## 5. Simulation Request to Sionna Config

API request:

```json
{
  "radar": {
    "center_m": [x, y, z],
    "look_at_m": [lx, ly, lz],
    "tx_rx_baseline_m": 0.1
  }
}
```

Convert:

```python
tx_position_m = [x, y - baseline/2, z]
rx_position_m = [x, y + baseline/2, z]
look_at_m = [lx, ly, lz]
los = false
```

Note:

This baseline convention is simple but not orientation-aware. For full correctness, baseline should be perpendicular to boresight. Add as a Phase 2 improvement:

```text
baseline_axis = horizontal unit vector perpendicular to boresight
tx = center - baseline_axis * b/2
rx = center + baseline_axis * b/2
```

## 6. Web Cache Generation

Inputs:

```text
paths_summary.npz
radar_observation.npz
metadata.json
metrics.json
config.yaml
```

Outputs:

```text
web_cache/<run_id>/
  manifest.json
  scene_objects.json
  radar_pose.json
  top_paths.json
  first_interactions.parquet
  range_azimuth.json/bin
  range_elevation.json/bin
```

### Top Paths Algorithm

1. Load path arrays.
2. Compute valid mask.
3. Compute kind: specular/diffuse/mixed.
4. Prefer paths in FoV.
5. Select:
   - top `K_energy` by energy
   - top `K_diffuse` among diffuse paths
   - optional random/stratified sample for background
6. Store polyline and metadata.

### Interaction Cache Algorithm

1. Flatten valid paths.
2. For each interaction depth where interaction != 0:
   - store position
   - interaction type
   - object ID
   - path energy
   - in_fov
3. Save Parquet.

### Spectra Cache Algorithm

1. Load `range_azimuth_power`.
2. Convert to float32.
3. Save binary.
4. Save JSON metadata with edges and shape.
5. Repeat for range-elevation.

## 7. Backend Tests

### Unit Tests

1. Config validation.
2. Scene registry.
3. Campaign registry.
4. Top path extraction.
5. Interaction point extraction.
6. Spectra binary roundtrip.
7. API schema validation.

### Integration Tests

1. Load existing C002-full campaign.
2. Build cache for one run.
3. Serve run metadata.
4. Serve top paths.
5. Serve spectra.
6. Submit tiny simulation with low samples.
7. Submit 4-GPU smoke test with tiny campaign.

## 8. Failure Modes and Handling

| Failure | Handling |
|---|---|
| Sionna import failure | API health endpoint reports backend not simulation-ready. |
| GPU unavailable | Scheduler rejects job or removes GPU from pool. |
| Worker crash | Mark task failed; preserve partial outputs. |
| Cache build failure | Run remains valid; frontend falls back to static figures. |
| Missing `cir.npz` | Cache can still build paths/spectra if `radar_observation.npz` and `paths_summary.npz` exist. |
| Huge point cloud | Frontend LOD; backend refuses full upload above configured limit. |

## 9. Health Endpoints

```http
GET /api/health
GET /api/health/gpus
GET /api/health/storage
GET /api/health/sionna
```

Example:

```json
{
  "status": "ok",
  "gpus": [
    {"id": 0, "name": "NVIDIA H100", "available": true, "memory_used_mb": 3},
    {"id": 1, "name": "NVIDIA H100", "available": true, "memory_used_mb": 3}
  ],
  "sionna": {"importable": true}
}
```
