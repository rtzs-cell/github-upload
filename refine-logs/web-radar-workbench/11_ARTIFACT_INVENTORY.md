# 11 Artifact Inventory

**Purpose**: Define exactly what files and folders should exist as the workbench is implemented, what owns them, and whether they are primary, derived, or disposable.

## 1. Artifact Classes

| Class | Meaning | Delete Policy |
|---|---|---|
| Primary | Needed to reproduce or audit a run | never delete automatically |
| Derived | Rebuildable from primary files | may delete/rebuild |
| Ephemeral | Runtime logs, temporary states | may rotate |
| External | Existing experiment output read by workbench | read-only |

## 2. Existing External Artifacts

The workbench reads these but must not mutate them:

```text
outputs/sionna_radar_campaigns/C002_full_radar_sensing/
  reports/POSE_METRICS.csv
  reports/runs_index.csv
  reports/CAMPAIGN_SUMMARY.md
  runs/<run_id>/
    config.yaml
    metadata.json
    metrics.json
    paths_summary.npz
    radar_observation.npz
    cir.npz
    figures/
```

Class:

```text
External primary
```

## 3. Workbench Source Code Artifacts

```text
services/radar_api/
apps/radar-workbench/
```

Class:

```text
Primary source
```

Required documentation:

```text
services/radar_api/README.md
apps/radar-workbench/README.md
```

## 4. Workbench Generated Output Root

```text
outputs/radar_workbench/
  scenes/
  campaigns/
  jobs/
  web_cache/
  logs/
```

This root is owned by the web workbench. Existing `outputs/sionna_radar_campaigns*` folders remain separate.

## 5. Scene Artifacts

```text
outputs/radar_workbench/scenes/<scene_id>/
  scene_manifest.json
  source/
  processed/
  thumbnails/
```

| File | Class | Owner | Notes |
|---|---|---|---|
| `scene_manifest.json` | Primary | backend | Required for every scene |
| `source/original_*` | Primary | user/backend | Uploaded source asset |
| `processed/preview_pointcloud.*` | Derived | backend | Display asset |
| `processed/proxy_buildings.json` | Primary or derived | backend | Primary if manually edited |
| `processed/mitsuba_scene.xml` | Derived | converter | Rebuildable if proxy/materials are primary |
| `thumbnails/*.png` | Derived | backend/frontend | Rebuildable |

## 6. Campaign Artifacts

```text
outputs/radar_workbench/campaigns/<campaign_id>/
  campaign_manifest.json
  pose_manifest.csv
  reports/
    CAMPAIGN_SUMMARY.md
    POSE_METRICS.csv
    runs_index.csv
  runs/
    <run_id>/
```

| File | Class | Owner | Notes |
|---|---|---|---|
| `campaign_manifest.json` | Primary | backend | Records scene, purpose, schema |
| `pose_manifest.csv` | Primary | backend/user | Defines measurement plan |
| `reports/POSE_METRICS.csv` | Derived primary | postprocessor | Audit table; do not delete |
| `reports/runs_index.csv` | Derived primary | scheduler | Audit table; do not delete |
| `reports/CAMPAIGN_SUMMARY.md` | Derived | postprocessor | Rebuildable but useful |

## 7. Run Artifacts

```text
runs/<run_id>/
  config.yaml
  metadata.json
  metrics.json
  paths_summary.npz
  radar_observation.npz
  cir.npz
  figures/
```

| File | Class | Owner | Notes |
|---|---|---|---|
| `config.yaml` | Primary | backend | Immutable after job starts |
| `metadata.json` | Primary | worker | Environment, scene, devices |
| `metrics.json` | Primary | postprocessor | Main metrics |
| `paths_summary.npz` | Primary | worker | Path geometry and interactions |
| `radar_observation.npz` | Primary | postprocessor | Range-angle maps |
| `cir.npz` | Primary large | worker | Optional lightweight archive deletion only by explicit user command |
| `figures/*.png` | Derived | postprocessor | Rebuildable |

## 8. Job Artifacts

```text
outputs/radar_workbench/jobs/<job_id>/
  job.json
  status.json
  task_manifest.json
  worker_events.jsonl
  logs.txt
```

| File | Class | Owner | Notes |
|---|---|---|---|
| `job.json` | Primary | API | Original request |
| `status.json` | Ephemeral/primary | scheduler | Current lifecycle |
| `task_manifest.json` | Primary | scheduler | Expanded tasks |
| `worker_events.jsonl` | Primary log | workers | Append-only |
| `logs.txt` | Ephemeral | workers | May rotate after archiving |

## 9. Web Cache Artifacts

```text
outputs/radar_workbench/web_cache/<run_id>/
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
```

Class:

```text
Derived
```

Delete policy:

```text
Safe to delete and rebuild if source run artifacts still exist.
```

Manifest must include:

```json
{
  "schema_version": "0.1.0",
  "run_id": "...",
  "source_run_dir": "...",
  "source_files": {
    "metadata_json": "...",
    "metrics_json": "...",
    "paths_summary_npz": "...",
    "radar_observation_npz": "..."
  },
  "created_at_utc": "...",
  "generator": "radar_api.web_cache"
}
```

## 10. Archival Bundles

For long-term archiving, create:

```text
archives/
  radar_workbench_plan_20260701/
  radar_workbench_phase0_snapshot_<timestamp>/
  radar_workbench_campaign_<campaign_id>_<timestamp>/
```

Recommended archive contents for a campaign:

```text
campaign_manifest.json
pose_manifest.csv
reports/
runs/*/config.yaml
runs/*/metadata.json
runs/*/metrics.json
runs/*/paths_summary.npz
runs/*/radar_observation.npz
web_cache/
```

Large optional:

```text
runs/*/cir.npz
```

Only include `cir.npz` when the archive is intended to preserve full channel impulse responses.

## 11. Do-Not-Mix Rule

Do not write web-generated files into:

```text
outputs/sionna_radar_campaigns/C002_full_radar_sensing/
outputs/sionna_radar_campaigns_parallel/
```

Exception:

```text
none for MVP
```

All web-generated material belongs under:

```text
outputs/radar_workbench/
```
