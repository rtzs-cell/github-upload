# 01 Repository and Artifact Layout

## 1. Target Repository Layout

Add a new app folder without disturbing existing experiment code:

```text
apps/
  radar-workbench/
    README.md
    package.json
    vite.config.ts
    tsconfig.json
    index.html
    src/
      main.tsx
      app/
        App.tsx
        routes.tsx
        store.ts
      api/
        client.ts
        types.ts
      components/
        layout/
        scene/
        radar/
        spectra/
        jobs/
        metrics/
      features/
        campaignBrowser/
        runViewer/
        radarEditor/
        simulationSubmit/
      styles/
        globals.css
```

Backend:

```text
services/
  radar_api/
    README.md
    pyproject.toml
    app/
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
      tests/
```

Shared generated outputs:

```text
outputs/
  radar_workbench/
    scenes/
    campaigns/
    jobs/
    web_cache/
    logs/
```

Keep existing experiment outputs:

```text
outputs/sionna_radar_campaigns/
outputs/sionna_radar_campaigns_parallel/
```

The web app can read these existing outputs but should write new workbench-managed results under `outputs/radar_workbench/` by default.

## 2. Workbench Output Layout

```text
outputs/radar_workbench/
  scenes/
    <scene_id>/
      scene_manifest.json
      source/
        original_pointcloud.ply
        original_mesh.obj
      processed/
        preview_pointcloud.las|ply|bin
        proxy_buildings.json
        mitsuba_scene.xml
      thumbnails/
        topdown.png
        preview.png

  campaigns/
    <campaign_id>/
      campaign_manifest.json
      pose_manifest.csv
      reports/
        CAMPAIGN_SUMMARY.md
        POSE_METRICS.csv
        runs_index.csv
      runs/
        <run_id>/
          config.yaml
          metadata.json
          metrics.json
          paths_summary.npz
          radar_observation.npz
          cir.npz
          figures/

  jobs/
    <job_id>/
      job.json
      status.json
      logs.txt
      task_manifest.json
      worker_events.jsonl

  web_cache/
    <run_id>/
      manifest.json
      scene_objects.json
      radar_pose.json
      top_paths.json
      first_interactions.parquet
      range_azimuth.json
      range_azimuth.bin
      range_elevation.json
      range_elevation.bin
      thumbnails/
        dashboard.png
        topdown_echo_paths.png
```

## 3. Naming Rules

### Scene ID

```text
scene_<short_name>_<yyyymmdd_hhmmss>
```

Examples:

```text
scene_simple_street_canyon_builtin
scene_tokyo_block_20260701_090000
```

### Campaign ID

```text
camp_<scene_id>_<purpose>_<yyyymmdd_hhmmss>
```

Example:

```text
camp_simple_street_canyon_pose_sweep_20260701_091000
```

### Run ID

Keep current stable convention:

```text
MM_<campaign>_<pose_id>_<boresight_id>_S<seed>_N<samples_k>k
```

For web-generated single pose:

```text
WEB_<scene_id>_<pose_id>_<boresight_id>_S<seed>_N<samples_k>k
```

## 4. Artifact Ownership

| Artifact | Owner | Mutability |
|---|---|---|
| `config.yaml` | backend | immutable after run starts |
| `metadata.json` | worker | immutable after completion |
| `metrics.json` | worker/postprocessor | may be extended by postprocess |
| `paths_summary.npz` | worker | immutable |
| `cir.npz` | worker | immutable |
| `radar_observation.npz` | postprocessor | immutable after generated |
| `web_cache/<run_id>` | backend cache generator | rebuildable |
| `job/status.json` | scheduler | mutable until done |
| `worker_events.jsonl` | scheduler/worker | append-only |

## 5. Cleanup Policy

Never delete:

```text
config.yaml
metadata.json
metrics.json
paths_summary.npz
radar_observation.npz
POSE_METRICS.csv
```

Optional deletion:

```text
cir.npz
```

Only if user chooses `lightweight archive`, because `cir.npz` is large.

Regenerable:

```text
figures/
web_cache/
thumbnails/
```

## 6. Versioning

Every manifest should include:

```json
{
  "schema_version": "0.1.0",
  "created_at_utc": "...",
  "generator": "radar-workbench",
  "source": "..."
}
```

If schema changes, bump `schema_version` and keep old loader compatibility where feasible.
