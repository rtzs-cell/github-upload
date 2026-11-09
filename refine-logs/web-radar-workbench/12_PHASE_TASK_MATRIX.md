# 12 Phase Task Matrix

**Purpose**: Convert the architecture and runbook into an implementation checklist that can be audited phase by phase.

## 1. Matrix Overview

| Phase | Primary Goal | Input | Output | Must Pass |
|---|---|---|---|---|
| P0 | Repo skeleton | existing workspace | app/service folders | import/build smoke |
| P1 | Read-only backend | C002-full CSV/JSON | campaign and run APIs | 30 runs listed |
| P2 | Web cache | one representative run | web cache folder | no CIR read |
| P3 | Read-only frontend | P1 APIs, static PNGs | usable browser | run selection works |
| P4 | Interactive visualization | P2 caches | linked paths/spectra | 500 paths + heatmaps |
| P5 | Single simulation | validated API request | one web-generated run | job complete |
| P6 | GPU0-3 campaign | pose manifest | multi-run campaign | no CSV corruption |
| P7 | Point-cloud preview | small point cloud | visual layer | simulation disabled |
| P8 | Mesh/proxy conversion | point cloud/proxy | Sionna-ready scene | low-sample run passes |

## 2. P0: Repository Skeleton

Tasks:

| Task ID | Task | Output | Test |
|---|---|---|---|
| P0-T1 | Create backend folder | `services/radar_api/` | Python import smoke |
| P0-T2 | Create frontend folder | `apps/radar-workbench/` | `npm` install/build smoke |
| P0-T3 | Create output root | `outputs/radar_workbench/` | folder existence |
| P0-T4 | Add READMEs | backend/frontend README | docs present |

Failure means:

```text
Do not start backend API or frontend UI until project roots are stable.
```

## 3. P1: Read-Only Backend

Tasks:

| Task ID | Task | Output | Test |
|---|---|---|---|
| P1-T1 | Register C002-full | campaign registry entry | `GET /api/campaigns` |
| P1-T2 | Parse `POSE_METRICS.csv` | run summary list | 30 rows |
| P1-T3 | Resolve run ID to folder | in-memory index | representative run found |
| P1-T4 | Load metadata/metrics | JSON endpoint | no NPZ/CIR access |
| P1-T5 | Add health endpoint | `/api/health` | status ok |

Required response fields:

```text
run_id
pose_id
boresight_id
x_m, y_m, z_m
look_x_m, look_y_m, look_z_m
boresight_az_deg
boresight_el_deg
valid_path_count
dominant_range_m
fov_energy_fraction
energy_in_fov
status
```

Stop if:

```text
run_count != 30
metadata endpoint loads cir.npz
unknown run_id resolves to a path
```

## 4. P2: Web Cache

Tasks:

| Task ID | Task | Output | Test |
|---|---|---|---|
| P2-T1 | Extract scene objects | `scene_objects.json` | 7 objects for representative run |
| P2-T2 | Extract radar pose | `radar_pose.json` | Tx/Rx/look-at match metadata |
| P2-T3 | Select top paths | `top_paths.json` | <= 500 paths |
| P2-T4 | Extract interactions | `first_interactions.parquet` | required columns present |
| P2-T5 | Write spectra binaries | `range_*.bin/json` | shape/edges match |
| P2-T6 | Write manifest | `manifest.json` | source files recorded |

Stop if:

```text
object sentinel 4294967295 leaks as a valid object id
spectra shape does not match edge counts
cache generator requires cir.npz
top_paths.json exceeds expected size by large margin without explanation
```

## 5. P3: Read-Only Frontend

Tasks:

| Task ID | Task | Output | Test |
|---|---|---|---|
| P3-T1 | Workbench shell | top/left/center/right/bottom layout | opens without selected run |
| P3-T2 | Campaign selector | C002-full option | campaign loads |
| P3-T3 | Run list | 30 selectable rows | selection updates state |
| P3-T4 | Metrics panel | selected run metrics | values match CSV |
| P3-T5 | Static figure panel | existing PNGs | images load |

Stop if:

```text
first screen is a landing page instead of the workbench
run selection mutates completed run config
browser requests full CIR during ordinary browsing
```

## 6. P4: Interactive Visualization

Tasks:

| Task ID | Task | Output | Test |
|---|---|---|---|
| P4-T1 | Building bbox layer | material-colored boxes | bbox matches metadata |
| P4-T2 | Radar pose layer | Tx/Rx/boresight glyphs | positions match metadata |
| P4-T3 | FoV layer | sector/frustum | 120 deg azimuth, 0-40 deg elevation |
| P4-T4 | Path layer | top paths | hover/click works |
| P4-T5 | Interaction layer | first interaction points | energy coloring works |
| P4-T6 | Spectrum panels | range-azimuth/elevation heatmaps | axes match metadata |
| P4-T7 | Linked selection | path <-> bin highlighting | selected IDs match |

Stop if:

```text
heatmap is transposed
FoV boundary is centered on wrong boresight
path coordinates do not align with building geometry
UI labels postprocessed FoV as a physical antenna beam
```

## 7. P5: Single-Pose Simulation

Tasks:

| Task ID | Task | Output | Test |
|---|---|---|---|
| P5-T1 | Pydantic request schema | validated request | invalid configs rejected |
| P5-T2 | Config builder | Sionna run config | matches existing format |
| P5-T3 | Job store | job/status/task files | lifecycle transitions |
| P5-T4 | Single GPU worker | one low-sample run | GPU0 smoke pass |
| P5-T5 | Postprocess and cache | run + web cache | result appears in UI |

Stop if:

```text
scene is not simulation-ready
requested GPU not in [0,1,2,3]
job output writes into read-only C002-full folder
```

## 8. P6: GPU0-3 Campaign

Tasks:

| Task ID | Task | Output | Test |
|---|---|---|---|
| P6-T1 | Task manifest expansion | per-pose tasks | count correct |
| P6-T2 | Scheduler | GPU assignment | one worker per GPU |
| P6-T3 | Event stream | progress events | frontend updates |
| P6-T4 | Locked reporting | CSV/report outputs | no corruption |
| P6-T5 | Partial failure handling | failed task status | completed runs preserved |

Stop if:

```text
same GPU receives concurrent workers by default
CSV rows are missing or duplicated
failed task deletes successful artifacts
```

## 9. P7: Point-Cloud Preview

Tasks:

| Task ID | Task | Output | Test |
|---|---|---|---|
| P7-T1 | Upload manifest | scene entry | source_type=pointcloud |
| P7-T2 | Preview parser | point layer | small file visible |
| P7-T3 | Radar placement | draft pose | controls work |
| P7-T4 | Simulation lockout | disabled Run button | backend also rejects |

Stop if:

```text
point cloud can be submitted to Sionna without mesh/proxy
UI suggests point cloud alone is a radio scene
```

## 10. P8: Mesh/Proxy Conversion

Tasks:

| Task ID | Task | Output | Test |
|---|---|---|---|
| P8-T1 | Proxy generation | building boxes/mesh | coordinates align |
| P8-T2 | Material assignment | material map | Sionna materials valid |
| P8-T3 | Mitsuba export | XML scene | load_scene works |
| P8-T4 | Validation run | low-sample radar result | paths plausible |
| P8-T5 | UI enablement | simulation_ready=true | Run allowed |

Stop if:

```text
visual scene and Sionna scene coordinate frames disagree
materials are missing or defaulted silently
low-sample run returns no plausible paths
```

## 11. Phase Completion Record

When finishing each phase, append a short record to the tracker:

```text
phase id
date/time UTC
commit or file snapshot if available
tests run
artifacts generated
known remaining risks
```
