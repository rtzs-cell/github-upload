# 16 Two-Building Radar Workbench Implementation Log

**Date**: 2026-07-05
**Scope**: Two-building monostatic radar experiment workflow, professionalized UI terminology, path statistics, result bundles, and Rx digital beamforming analysis.

## Implemented

### Backend

Added:

```text
services/radar_api/app/api/experiments.py
services/radar_api/app/core/two_building_scene.py
services/radar_api/app/core/path_statistics.py
services/radar_api/app/core/beamforming.py
services/radar_api/app/core/sionna_runtime.py
experiments/sionna_radar/scripts/run_config_json.py
services/radar_api/tests/test_experiments_and_bundles.py
```

Updated:

```text
services/radar_api/app/api/results.py
services/radar_api/app/main.py
services/radar_api/app/schemas.py
services/radar_api/app/workers/simulation_worker.py
services/radar_api/README.md
```

Capabilities:

1. `POST /api/experiments` creates an immutable two-building experiment draft.
2. Each experiment draft writes:
   - `experiment_manifest.json`
   - `input/experiment_config.json`
   - `input/scene_config.json`
   - `input/beamforming_config.json`
   - `input/analysis_config.json`
   - `scene/two_buildings.xml`
   - `scene/meshes/floor.ply`
   - `scene/meshes/building_A.ply`
   - `scene/meshes/building_B.ply`
3. The generated XML follows the same Mitsuba/Sionna scene style as Sionna built-in scenes: PLY shapes plus `mat-itu_*` material references.
4. Simulation submission now keeps beamforming configuration inside `config.yaml`.
5. `/api/results/{run_id}/path_statistics` writes:
   - `analysis/path_statistics.json`
   - `analysis/paths.csv`
   - `analysis/building_path_statistics.csv`
6. `/api/results/{run_id}/beamforming` reads `cir.npz`, applies Rx complex weights, and writes:
   - `analysis/beamforming_summary.json`
   - `analysis/beamformed_paths.csv`
   - `analysis/beamformed_observation.npz`
7. `/api/results/{run_id}/result_bundle.zip` downloads raw/config/analysis/figure artifacts as one archive.
8. Live Sionna execution now uses an external Sionna Python runner:
   - API process: FastAPI, job scheduling, postprocessing, web cache, result APIs.
   - Sionna process: `experiments/sionna_radar/scripts/run_config_json.py`.
   - Configured through `RADAR_SIONNA_PYTHON`.
9. The Sionna runner supports both newer `PathSolver` and older `scene.compute_paths()` APIs.
10. Web cache generation no longer assumes exactly two interaction depths.

### Frontend

Updated:

```text
apps/radar-workbench/src/api/client.ts
apps/radar-workbench/src/api/types.ts
apps/radar-workbench/src/app/App.tsx
apps/radar-workbench/src/app/FovDragControl.tsx
apps/radar-workbench/src/app/RadarEditor.tsx
apps/radar-workbench/src/app/Scene3D.tsx
apps/radar-workbench/src/app/radarConfig.ts
apps/radar-workbench/src/styles/globals.css
apps/radar-workbench/README.md
```

Capabilities:

1. Left panel now separates experiment drafts from existing result sources.
2. Clicking a two-building experiment draft loads its saved configuration and generated two-building scene.
3. Running a draft uses the generated `scene/two_buildings.xml`, not a hard-coded built-in street scene.
4. The 3D scene camera and ground grid now adapt to far-range 400-500 m building positions.
5. The direction/width drag control supports up to 1000 m analysis range.
6. Visible UI text uses professional Chinese radar terms:
   - `角域分析门限`
   - `接收阵列数字波束成形`
   - `单站雷达`
   - `传播路径`
7. UI avoids calling postprocessed angle/range gating a physical beam.
8. Result view includes:
   - valid path count
   - analysis-gate path count
   - second-interaction path count
   - object path statistics
   - result ZIP download
   - on-demand Rx beamforming analysis generation

## Output Organization

```text
outputs/radar_workbench/experiments/
  exp_.../
    experiment_manifest.json
    input/
    scene/

outputs/radar_workbench/campaigns/
  job_.../
    campaign_manifest.json
    pose_manifest.json
    reports/
    runs/

outputs/radar_workbench/result_bundles/
  *_result_bundle.zip

outputs/radar_workbench/path_exports/
  paths_.../

outputs/radar_workbench/web_cache/
  <run_id>/
```

## Verification

Backend:

```text
python -m pytest services/radar_api/tests -q
17 passed
```

Frontend:

```text
npm -C apps/radar-workbench run build
tsc + vite build passed
```

Manual API verification:

```text
GET /api/results/MM_C002full_Pp0_p0_BposY_S501_N500k/beamforming?rx_mode=uniform
status: 200
rx_mode: uniform
rx_weight_count: 256
top_paths: 20
```

Generated scene XML load verification:

```text
PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES=-1 \
  /home/Users_Work_Space/zsfang/anaconda3/envs/tensorflow215/bin/python

rt.load_scene(".../scene/two_buildings.xml") -> ok
objects: building_A, building_B, floor
```

The runner now supports both Sionna signatures:

```text
load_scene(path, merge_shapes=False)
load_scene(path)
```

The runner now supports both Sionna path APIs:

```text
sionna.rt.PathSolver(...)(scene, ...)
scene.compute_paths(...)
```

Runtime environment check:

```text
/home/Users_Work_Space/plzheng/miniconda3/envs/demo_raised/bin/python
  PYTHONNOUSERSITE=1 -> no module named sionna
  with user site-packages -> import sionna.rt timed out in 60 s

/home/Users_Work_Space/zsfang/anaconda3/envs/tensorflow215/bin/python
  PYTHONNOUSERSITE=1 -> generated XML loads successfully
  missing backend packages: fastapi, uvicorn, pydantic, pandas, pyarrow
```

Resolution: the API no longer needs to import Sionna inside the FastAPI Python environment. It launches the configured external Sionna Python for ray tracing, then performs radar observation postprocessing and cache generation in the API environment.

Runtime probe:

```text
probe_sionna_runtime -> available: True
RADAR_SIONNA_PYTHON: /home/Users_Work_Space/zsfang/anaconda3/envs/tensorflow215/bin/python
```

Tiny live Sionna verification:

```text
scene: generated two_buildings.xml
samples_per_src: 8
max_depth: 2
mode: external Sionna Python, CPU-isolated for low-risk verification
run_id: WEB_tiny_full_worker_verify2
status: complete
valid_path_count: 1
artifacts: paths_summary.npz, cir.npz, radar_observation.npz, web_cache
```

Tiny GPU0 Sionna verification:

```text
scene: generated two_buildings.xml
samples_per_src: 8
max_depth: 2
mode: external Sionna Python, CUDA_VISIBLE_DEVICES=0
run_id: WEB_tiny_gpu0_worker_verify
status: complete
valid_path_count: 1
artifacts: paths_summary.npz, cir.npz, radar_observation.npz, web_cache
```

## Remaining Engineering Notes

1. The generated two-building scene is now executable by the Sionna runner because `scene_id` is an actual XML file path.
2. Physical antenna direction patterns remain separate from postprocessed angle/range analysis gates.
3. Custom Rx beamforming weights can be saved as JSON and postprocessed from CIR. The browser does not yet provide a 256-element matrix editor beyond the JSON field.
4. Existing C002 data remains available for comparison, but new two-building experiments are represented as first-class experiment drafts.
