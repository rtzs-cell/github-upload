# 13 Implementation Log

**Date**: 2026-07-01  
**Scope**: First runnable read-only radar result browser. This was not the full web radar sensing workbench.

> Correction: This implementation covers the P0/P1 read-only browser and cache foundation only. It does not complete the full planned workbench because live parameter editing, 3D visualization, simulation submission, and GPU0-3 scheduling were not implemented in this snapshot.

## 1. Implemented

### Offline Git Versioning

Initialized a local Git repository in:

```text
/home/DataDisk/plzheng/radar_simulate
```

Created `.gitignore` to exclude:

```text
outputs/**
node_modules/
dist/
__pycache__/
runtime logs and caches
```

Kept lightweight output placeholders:

```text
outputs/radar_workbench/.gitkeep
outputs/radar_workbench/scenes/.gitkeep
outputs/radar_workbench/campaigns/.gitkeep
outputs/radar_workbench/jobs/.gitkeep
outputs/radar_workbench/web_cache/.gitkeep
outputs/radar_workbench/logs/.gitkeep
```

### Backend

Implemented:

```text
services/radar_api/
  app/main.py
  app/api/health.py
  app/api/campaigns.py
  app/api/results.py
  app/core/campaign_registry.py
  app/core/result_loader.py
  app/core/web_cache.py
  tests/
```

Capabilities:

1. Registers existing C002-full campaign as read-only.
2. Returns 30 radar sensing runs from `POSE_METRICS.csv`.
3. Returns metadata and metrics without loading `cir.npz`.
4. Builds web cache from `paths_summary.npz` and `radar_observation.npz`.
5. Serves top paths, first interactions, scene objects, and range-angle spectra.
6. Serves existing per-run PNG figures.

### Frontend

Implemented:

```text
apps/radar-workbench/
  React + TypeScript + Vite app
  run browser
  metrics panel
  top-down scene/path SVG view
  range-azimuth and range-elevation canvas heatmaps
  existing figure viewer
```

The UI is read-only and radar-only. It does not submit simulation jobs yet, and therefore should not be treated as satisfying the complete workbench requirements.

### Scripts

Implemented:

```text
scripts/start_radar_workbench.sh
scripts/stop_radar_workbench.sh
```

## 2. Verification

Backend:

```text
/home/Users_Work_Space/plzheng/miniconda3/envs/demo_raised/bin/python -m pytest -q
9 passed
```

Frontend:

```text
npm run build
tsc + vite build passed
```

Runtime checks:

```text
GET /api/health -> ok
GET /api/campaigns -> C002 Full Radar Sensing, 30 runs
GET /api/campaigns/c002_full_existing/runs -> 30 runs
GET /api/results/MM_C002full_Pp0_p0_BposY_S501_N500k/paths?top_k=3 -> valid paths
range_azimuth binary length -> 960480 bytes, matching [1334, 180] float32
range_elevation binary length -> 480240 bytes, matching [1334, 90] float32
```

## 3. Git Commits

Inspect exact local commit hashes with:

```bash
git log --oneline --decorate
```

The staged history includes:

1. offline baseline commit.
2. read-only radar campaign backend commit.
3. radar workbench browser frontend commit.
4. implementation status and tracker commit.
5. root quick-start documentation commit.

## 4. Current URLs

Backend:

```text
http://127.0.0.1:8000
```

Frontend:

```text
http://127.0.0.1:5173
```

The start script was smoke-tested after manual dev servers were stopped:

```text
./scripts/start_radar_workbench.sh
GET /api/health -> 200
GET / -> 200
```

## 5. Known Boundaries

1. Live Sionna simulation submission is not enabled yet.
2. GPU0-3 scheduling remains the next implementation phase.
3. Point cloud upload remains visualization-only in the plan and is not implemented in this first runnable version.
4. FoV is still displayed as postprocessed FoV for existing C002 data, not as a proven physical sector antenna pattern.

## 6. Required Follow-Up For Full Completion

The full goal requires:

1. Three-dimensional scene/path/FoV/interaction visualization.
2. Radar parameter editor for pose, direction, FoV, frequency, propagation, scattering, antenna, direction pattern, and compute options.
3. Backend simulation request validation and config generation.
4. Single-pose Sionna job execution.
5. GPU0-3 campaign scheduling.
6. Automatic result archival and web cache generation.
7. UI reload of generated results.

## 7. Full Workbench Completion Update

**Date**: 2026-07-01  
**Scope**: Radar-only Sionna RT workbench core loop.

Implemented after the read-only snapshot:

1. Three.js 3D scene view with building boxes, radar Tx/Rx glyphs, boresight arrow, FoV frustum, propagation path polylines, and reflection/scattering interaction markers.
2. Radar editor for position, look-at direction, azimuth/elevation, FoV, range, carrier frequency, bandwidth, scattering model, path depth, LoS/specular/diffuse toggles, Tx/Rx array size, samples, seed, and GPU IDs.
3. `POST /api/simulations` and `GET /api/simulations/{job_id}` for asynchronous radar-only Sionna jobs.
4. Worker-side Sionna config generation with orientation-aware small-baseline Tx/Rx placement and automatic boresight/FoV center.
5. `radar_observation.npz`, `POSE_METRICS.csv`, `runs_index.csv`, `campaign_manifest.json`, `pose_manifest.json`, and web cache generation for new workbench runs.
6. GPU scheduler that uses one worker process per selected GPU and serial task chunks per GPU for campaign jobs.
7. Frontend job polling and automatic loading of completed campaign/run results.

Verified smoke jobs:

```text
job_20260701_112110_8394e5d8
  mode: single_pose
  gpu_ids: [0]
  result: complete
  run_id: WEB_job_20260701_112110_8394e5d8
  artifacts: cir.npz, paths_summary.npz, radar_observation.npz, figures, web_cache

job_20260701_113013_a6d1b876
  mode: campaign
  gpu_ids: [0, 1]
  tasks: 2 static radar poses
  result: complete
  run_ids:
    WEB_job_20260701_113013_a6d1b876
    WEB_job_20260701_113013_a6d1b876_001
  artifacts: two run directories, two web caches, two-row POSE_METRICS.csv
```

Verification commands:

```text
python -m pytest -q services/radar_api/tests
11 passed

npm -C apps/radar-workbench run build
tsc + vite build passed
```

Remaining boundaries:

1. Point-cloud upload and point-cloud-to-Sionna/Mitsuba conversion remain P7/P8 follow-up work, not part of the completed core radar workbench loop.
2. `direction_pattern=sector` is mapped to Sionna-supported `tr38901` as an approximation; strict custom sector-pattern research remains the planned C004-sector study.
3. Smoke runs used low sample counts for software verification; research-quality runs should use the planned samples/seeds from `MULTI_MEASUREMENT_ISAC_PLAN.md`.

## 8. Analysis-Gate MPC And Steering-Vector Update

**Date**: 2026-07-06  
**Scope**: Diagnose low analysis-gate path count and add radar-specific MPC / steering-vector visualizations.

Implemented:

1. Added `GET /api/results/{run_id}/mpc_analysis`, which generates:
   - `analysis/analysis_gate_mpc.csv`
   - `analysis/analysis_gate_mpc_summary.json`
   - `figures/analysis_gate_mpc.png`
2. The MPC figure shows valid paths as gray background points, analysis-gate MPCs as energy-colored points, and the azimuth/elevation/range analysis-gate boundaries in cyan.
3. The MPC summary reports single-condition and combined-condition path counts, so low gate-in count can be traced to azimuth, elevation, range, or their intersection.
4. Fixed Rx beamforming CIR axis handling. The backend now infers path, Rx antenna, and Tx antenna axes from path count and array configuration instead of assuming a single fixed CIR tensor layout.
5. `GET /api/results/{run_id}/beamforming` now also generates:
   - `analysis/rx_steering_pattern.npz`
   - `analysis/rx_steering_pattern_summary.json`
   - `figures/rx_steering_pattern.png`
6. The steering-vector figure contains the Rx weight phase map and the corresponding normalized 2D array response. It visualizes receive-side coherent combining gain, not PathSolver ray-launch concentration.
7. Result bundles now include all analysis directory files and the generated MPC figure, making browser-generated analysis downloadable.
8. Frontend integration:
   - automatically requests MPC analysis when a run is loaded;
   - displays analysis-gate screening diagnostics;
   - adds the MPC figure to the diagnostics section;
   - displays the steering-vector / array-response figure after beamforming analysis is generated.

Verification:

```text
python -m pytest services/radar_api/tests -q
24 passed

npm -C apps/radar-workbench run build
tsc + vite build passed
```

Observed on `MM_C002full_Pp0_p0_BposY_S501_N500k`:

```text
valid_path_count: 175423
analysis_gate_path_count: 18275
analysis_gate_energy_fraction: 0.3558501277652896
single-condition counts:
  range: 175423
  aoa_azimuth: 63416
  aoa_elevation: 48896
excluded counts:
  outside_range: 0
  outside_aoa_azimuth: 112007
  outside_aoa_elevation: 126527
```

Interpretation:

1. In the current implementation, the analysis gate is a postprocessing selection over Sionna-produced paths. It does not physically prevent reception of paths outside the gate.
2. If the analysis-gate MPC count is too low, the reliable workflow is to first increase candidate discovery (`samples_per_src`, multiple seeds/poses, wider initial analysis gate) and then narrow the gate based on the MPC distribution.
3. Rx steering vectors and custom weights can change coherent receive combining and the plotted array response, but they do not by themselves force Sionna PathSolver to emit more candidate rays inside a chosen cone.
