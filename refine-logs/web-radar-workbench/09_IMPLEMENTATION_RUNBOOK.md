# 09 Implementation Runbook

**Purpose**: Provide a precise execution order for building the web radar sensing workbench without mixing concerns, losing artifacts, or drifting away from radar-only Sionna RT sensing.

This runbook is intentionally operational. Every phase has file targets, commands, outputs, tests, and stop/go gates.

## 1. Golden Rules

1. Keep the product radar-only by default.
2. Treat existing C002-full results as read-only ground truth for web development.
3. Build web cache before building live simulation submission.
4. Do not send full `cir.npz` to the browser.
5. Do not promise point-cloud simulation until a mesh/proxy Sionna scene exists.
6. Use GPU0-3 only for this project unless the user explicitly changes the deployment rule.
7. Each run, job, campaign, scene, and cache must have a manifest.
8. Completed run configs are immutable.
9. Every generated folder must be reproducible or clearly marked as source/primary.
10. Every API endpoint must return units in field names or metadata.

## 2. Implementation Order

```text
P0. Repository skeleton
P1. Read-only backend loader
P2. One-run web cache generator
P3. Read-only frontend result browser
P4. Interactive path/spectrum visualization
P5. Single-pose Sionna job API
P6. GPU0-3 campaign scheduler
P7. Point-cloud preview
P8. Mesh/proxy conversion for simulation
```

Do not start `P5` before `P0-P4` pass. Do not start `P8` before `P7` passes.

## 3. P0 Repository Skeleton

Create:

```text
services/radar_api/
apps/radar-workbench/
outputs/radar_workbench/
```

Backend files:

```text
services/radar_api/README.md
services/radar_api/pyproject.toml
services/radar_api/app/main.py
services/radar_api/app/config.py
services/radar_api/app/schemas.py
services/radar_api/app/paths.py
services/radar_api/app/api/__init__.py
services/radar_api/app/core/__init__.py
services/radar_api/app/workers/__init__.py
services/radar_api/tests/
```

Frontend files:

```text
apps/radar-workbench/package.json
apps/radar-workbench/vite.config.ts
apps/radar-workbench/tsconfig.json
apps/radar-workbench/index.html
apps/radar-workbench/src/main.tsx
apps/radar-workbench/src/app/App.tsx
apps/radar-workbench/src/api/client.ts
apps/radar-workbench/src/api/types.ts
apps/radar-workbench/src/styles/globals.css
```

Output folders:

```text
outputs/radar_workbench/scenes/.gitkeep
outputs/radar_workbench/campaigns/.gitkeep
outputs/radar_workbench/jobs/.gitkeep
outputs/radar_workbench/web_cache/.gitkeep
outputs/radar_workbench/logs/.gitkeep
```

Gate:

```text
backend imports
frontend dev server starts
no simulation logic yet
```

## 4. P1 Read-Only Backend Loader

Implement modules:

```text
services/radar_api/app/core/campaign_registry.py
services/radar_api/app/core/result_loader.py
services/radar_api/app/api/campaigns.py
services/radar_api/app/api/results.py
```

Register existing campaign:

```text
campaign_id: c002_full_existing
root: outputs/sionna_radar_campaigns/C002_full_radar_sensing
readonly: true
```

Endpoints:

```http
GET /api/health
GET /api/campaigns
GET /api/campaigns/{campaign_id}/runs
GET /api/results/{run_id}/metadata
```

Implementation details:

1. Use `POSE_METRICS.csv` for run listing.
2. Use an in-memory run-id to run-dir index built from CSV.
3. Refuse unknown run IDs.
4. Load `metadata.json` and `metrics.json` only for selected run.
5. Do not open `cir.npz`.

Tests:

```text
test_health_ok
test_list_campaigns_contains_c002
test_list_c002_runs_count_30
test_load_representative_metadata
test_metadata_does_not_require_cir
```

Gate:

```text
30 runs returned
representative metadata returned in under 300 ms on warm local read
available_artifacts.cir is false for default browser payload
```

## 5. P2 One-Run Web Cache Generator

Implement:

```text
services/radar_api/app/core/web_cache.py
```

CLI or internal command:

```bash
python -m services.radar_api.app.core.web_cache \
  --run-dir outputs/sionna_radar_campaigns/C002_full_radar_sensing/runs/MM_C002full_Pp0_p0_BposY_S501_N500k \
  --out-root outputs/radar_workbench/web_cache \
  --top-k 500
```

Required outputs:

```text
outputs/radar_workbench/web_cache/MM_C002full_Pp0_p0_BposY_S501_N500k/
  manifest.json
  scene_objects.json
  radar_pose.json
  top_paths.json
  first_interactions.parquet
  range_azimuth.json
  range_azimuth.bin
  range_elevation.json
  range_elevation.bin
```

Cache generation rules:

1. Flatten `valid`, `interactions`, `objects`, and `vertices` using known shapes from `08_PREIMPLEMENTATION_PROBES.md`.
2. Compute path kind:
   - interaction value `1` only: specular
   - interaction value `2` only: diffuse
   - both values: mixed
   - no interaction: unknown/direct, normally not used because `los=false`
3. Select top paths by `path_energy`, preferring `fov_path_mask == true`.
4. Include path bin indices:
   - `range_bin_idx`
   - `azimuth_bin_idx`
   - `elevation_bin_idx`
5. Convert object sentinel `4294967295` to `null`.
6. Save spectra as float32 row-major binary.
7. Store axis edges in JSON metadata.
8. Store source file mtimes or hashes in `manifest.json`.

Tests:

```text
test_build_cache_one_run_outputs_all_files
test_top_paths_count_lte_500
test_top_paths_schema_has_units
test_no_object_sentinel_leaks_to_json
test_range_azimuth_binary_roundtrip
test_range_elevation_binary_roundtrip
test_cache_manifest_source_paths
```

Gate:

```text
top_paths.json about 100-300 KB for representative run
range_azimuth.bin about 0.96 MB
range_elevation.bin about 0.48 MB
cache builds without reading cir.npz
```

## 6. P3 Read-Only Frontend Result Browser

Implement:

```text
apps/radar-workbench/src/features/campaignBrowser/
apps/radar-workbench/src/features/runViewer/
apps/radar-workbench/src/components/layout/
apps/radar-workbench/src/components/metrics/
```

First screen:

```text
Top bar: campaign selector, run status
Left: run list and filters
Center: existing PNG figure viewer
Right: metadata and metrics
Bottom: report/metrics tabs
```

Use existing static figures first:

```text
campaign_range_azimuth.png
campaign_range_elevation.png
aoa_range_scatter.png
range_histogram.png
```

Gate:

```text
opens directly to workbench
C002-full listed
30 runs listed
run selection updates metrics and figures
browser does not request cir.npz
```

## 7. P4 Interactive Path/Spectrum Visualization

Backend endpoints:

```http
GET /api/results/{run_id}/paths?top_k=500
GET /api/results/{run_id}/interactions?mode=first&top_k=20000
GET /api/results/{run_id}/range_azimuth
GET /api/results/{run_id}/range_elevation
GET /api/results/{run_id}/scene_objects
```

Frontend components:

```text
SceneCanvas
BuildingBBoxLayer
RadarPoseLayer
FoVLayer
PathLayer
InteractionPointLayer
RangeAzimuthPanel
RangeElevationPanel
SelectedEntityPanel
```

Interaction contract:

1. Hover path shows path id, range, energy, kind, depth, object names.
2. Click path highlights the corresponding heatmap bin.
3. Click heatmap bin highlights matching top paths.
4. Layer toggles do not reload data.
5. Top-k selector warns above 2000 paths.

Visual semantics:

```text
Tx marker: triangle
Rx marker: square
Boresight: arrow
FoV: transparent sector/frustum
Specular interaction: circle
Diffuse/backscatter interaction: cross or point sprite
Specular path: blue
Diffuse path: orange
Mixed path: purple
Path width/opacity: normalized log energy
```

Gate:

```text
500 paths render interactively
20k interaction points render at >= 30 FPS on dev workstation
range-azimuth and range-elevation axes match JSON metadata
FoV boundary lines match selected run config
```

## 8. P5 Single-Pose Sionna Job API

Start only after P0-P4 pass.

Implement:

```text
services/radar_api/app/api/simulations.py
services/radar_api/app/workers/job_store.py
services/radar_api/app/workers/gpu_scheduler.py
services/radar_api/app/workers/simulation_worker.py
services/radar_api/app/core/sionna_config_builder.py
```

Endpoints:

```http
POST /api/simulations
GET /api/simulations/{job_id}
GET /api/simulations/{job_id}/events
POST /api/simulations/{job_id}/cancel
```

Tiny smoke request:

```json
{
  "scene_id": "scene_simple_street_canyon_builtin",
  "mode": "single_pose",
  "gpu_ids": [0],
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
    "samples_per_src": 10000,
    "seed": 901
  }
}
```

Gate:

```text
job status moves queued -> running -> complete
run folder is archived under outputs/radar_workbench/campaigns/<campaign_id>/runs/<run_id>
web cache is built automatically
new run appears in frontend
```

## 9. P6 GPU0-3 Campaign Scheduler

Start after single-pose job passes.

Scheduler rules:

1. Allowed GPU IDs are `[0,1,2,3]`.
2. One worker process per GPU.
3. Each worker sets `CUDA_VISIBLE_DEVICES=<gpu_id>` before importing TensorFlow/Sionna.
4. Each worker executes one Sionna task at a time.
5. Workers append to job event log; shared CSV writes require locking.
6. Failed tasks do not delete successful run folders.

Smoke campaign:

```text
4 poses x 1 boresight x 10000 samples
GPU IDs: 0,1,2,3
expected complete tasks: 4/4
```

Gate:

```text
all tiny tasks complete
POSE_METRICS.csv row count equals task count
runs_index.csv row count equals task count
no partial lines or duplicate run ids
frontend progress updates
```

## 10. P7 Point-Cloud Preview

This is visualization-only at first.

Supported MVP formats:

```text
.xyz text with x y z
.ply if frontend parser is selected and tested
```

Explicit UI label:

```text
Point cloud preview only. Sionna simulation requires mesh or proxy geometry.
```

Gate:

```text
small point cloud displays
radar pose can be placed
Run button is disabled unless simulation_ready == true
```

## 11. P8 Mesh/Proxy Conversion

Start only after P7 and all simulation phases are stable.

Minimum conversion path:

```text
point cloud / footprint
  -> ground plane estimate
  -> building footprint extraction or manual proxy import
  -> extruded building boxes
  -> material assignment
  -> Mitsuba XML
  -> Sionna load_scene validation
  -> 10000-sample radar smoke run
```

Gate:

```text
converted scene loads in Sionna
scene bounds match preview coordinates
one low-sample radar run completes
paths are visually plausible against geometry
```

## 12. Daily Developer Checklist

Before coding:

```text
read this runbook
check tracker status
check GPU0-3 health if running simulation
confirm target phase
confirm expected output folder
```

During coding:

```text
keep changes phase-scoped
do not introduce communication/UE workflow
write or update tests with schema changes
do not mutate existing C002-full run artifacts
```

Before finishing a phase:

```text
run backend tests for touched modules
run frontend build/lint if frontend changed
run cache generator on representative run if cache code changed
open UI and check no request for cir.npz
update tracker and relevant docs
```

## 13. Artifact Naming Checklist

Every scene:

```text
scene_manifest.json
schema_version
scene_id
source_type
simulation_ready
coordinate_system
bounds
materials
```

Every campaign:

```text
campaign_manifest.json
pose_manifest.csv
reports/POSE_METRICS.csv
reports/runs_index.csv
runs/<run_id>/
```

Every job:

```text
job.json
status.json
task_manifest.json
worker_events.jsonl
logs.txt
```

Every cache:

```text
manifest.json
source_run_dir
source_files
schema_version
created_at_utc
generator
```

## 14. Failure Triage

| Symptom | First Check | Likely Cause | Action |
|---|---|---|---|
| Run list empty | `POSE_METRICS.csv` path | campaign root wrong | fix registry path |
| Metadata endpoint slow | server logs | accidentally loading NPZ/CIR | keep metadata endpoint JSON-only |
| Browser crashes | network payload | too many paths/points | enforce top-k and binary spectra |
| Paths off-scene | coordinate frame | tx/rx/vertices mismatch | inspect metadata devices and vertices |
| Object labels wrong | object id mapping | Sionna numeric ids not mapped | add mapping cache and unknown handling |
| Heatmap axes wrong | JSON edges | transposed array or edge mismatch | validate shape vs edge lengths |
| GPU job hangs | worker log | Sionna import/device issue | isolate worker and set CUDA before import |
| CSV corrupted | concurrent write | missing file lock | use locked append or per-task rows then merge |
| Point cloud runs simulation | UI state | visualization-only flag ignored | enforce backend `simulation_ready` check |

## 15. First Three Implementation Tasks

1. Build `services/radar_api` read-only campaign loader for C002-full.
2. Build one-run web cache generator for `MM_C002full_Pp0_p0_BposY_S501_N500k`.
3. Build `apps/radar-workbench` read-only UI showing run list, metrics, and existing figures.

These tasks give an inspectable workbench before new live simulations are exposed.
