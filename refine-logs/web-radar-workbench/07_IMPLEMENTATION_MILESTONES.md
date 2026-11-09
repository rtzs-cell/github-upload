# 07 Implementation Milestones

Implementation must follow:

```text
08_PREIMPLEMENTATION_PROBES.md
09_IMPLEMENTATION_RUNBOOK.md
10_RISK_REGISTER.md
11_ARTIFACT_INVENTORY.md
```

The milestones below define product phases; the runbook defines exact execution tasks and stop/go gates.

## Phase 0: Read-Only Result Browser

Goal:

View existing C002-full data in a browser without running new simulations.

Deliverables:

```text
services/radar_api/
  GET /api/campaigns
  GET /api/campaigns/{campaign_id}/runs
  GET /api/results/{run_id}/metadata

apps/radar-workbench/
  campaign selector
  run list
  metrics panel
  static figure viewer
```

Done Criteria:

1. C002-full appears as a campaign.
2. 30 runs appear.
3. Selecting a run shows metrics and existing PNGs.
4. Browser never downloads `cir.npz`.

## Phase 1: Web Cache and Interactive Geometry

Goal:

Render paths, interactions, and spectra as interactive data, not just PNGs.

Deliverables:

```text
services/radar_api/app/core/web_cache.py
GET /api/results/{run_id}/paths
GET /api/results/{run_id}/interactions
GET /api/results/{run_id}/range_azimuth
GET /api/results/{run_id}/range_elevation

frontend:
  Three.js bbox layer
  radar pose/FoV layer
  path layer
  interaction point layer
  spectra heatmaps
```

Done Criteria:

1. One run cache generated.
2. Top 500 paths render.
3. First interaction points render.
4. Range-azimuth/elevation heatmaps render.
5. Hover and click selection works.

## Phase 2: Single-Pose Simulation

Goal:

Submit one radar pose from the web UI and run Sionna.

Deliverables:

```text
POST /api/simulations
GET /api/simulations/{job_id}
single-task GPU worker
job status panel
```

Done Criteria:

1. User can edit radar pose and parameters.
2. Backend validates config.
3. Job runs on GPU0 by default or selected GPU.
4. Result is archived.
5. Web cache is generated.
6. Result appears in UI.

## Phase 3: Multi-Pose Campaign Simulation

Goal:

Submit pose manifest/sweep and run on GPU0-3.

Deliverables:

```text
campaign editor
pose manifest upload
GPU0-3 scheduler
progress events
campaign summary
```

Done Criteria:

1. 4-GPU smoke test passes.
2. C002-lite style campaign can run from web.
3. `POSE_METRICS.csv` and `runs_index.csv` valid.
4. Partial progress visible.
5. Failed task reports clear error.

## Phase 4: Point Cloud Preview

Goal:

Load point cloud as a visualization layer.

Deliverables:

```text
POST /api/scenes/upload
point cloud preview layer
visualization-only scene manifest
```

Done Criteria:

1. Small point cloud loads.
2. Radar can be placed in point cloud view.
3. UI clearly labels simulation as disabled unless mesh/proxy exists.

## Phase 5: Scene Conversion

Goal:

Convert point cloud/mesh/proxy into Sionna-ready scene.

Deliverables:

```text
proxy building generator
material assignment UI
Mitsuba XML export
scene validation run
```

Done Criteria:

1. Converted scene loads in Sionna.
2. Metadata reports objects/materials.
3. One low-sample radar run completes.
4. Visual scene and Sionna scene coordinate frames align.

## Phase 6: Advanced Studies

Goal:

Support research sweeps.

Features:

1. frequency sweep 28/60/77 GHz.
2. scattering coefficient sweep.
3. boresight sweep.
4. sector antenna pattern experiment.
5. high-sample repeatability runs.

Done Criteria:

1. Sweep manifests saved.
2. Results comparable in UI.
3. Exportable report generated.

## Recommended Immediate Next Step

Start with Phase 0 and Phase 1:

1. Create backend `radar_api`.
2. Register existing C002-full campaign as read-only.
3. Implement one-run cache generator.
4. Build frontend workbench shell.
5. Render C002-full existing data interactively.

This path avoids the hardest unsolved problem, point-cloud-to-Sionna conversion, until the visualization and result pipeline are stable.

## Stop Rules

Stop implementation and fix the current phase if any of these happen:

1. The frontend requests `cir.npz` during normal browsing.
2. A UI or API introduces UE/communication entities.
3. A point-cloud-only scene can submit a Sionna simulation job.
4. Heatmap axes do not match `range_edges_m`, `azimuth_edges_deg`, or `elevation_edges_deg`.
5. GPU IDs outside `[0,1,2,3]` are accepted by the scheduler.
6. Web-generated artifacts are written into the existing read-only C002-full output folder.
