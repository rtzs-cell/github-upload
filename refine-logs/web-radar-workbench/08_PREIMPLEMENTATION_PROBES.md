# 08 Pre-Implementation Probes

**Probe time UTC**: 2026-07-01T08:11:51Z  
**Workspace**: `/home/DataDisk/plzheng/radar_simulate`  
**Purpose**: Verify risky assumptions before implementing the web radar sensing workbench.

These probes are intentionally narrow. Their job is to prevent late discovery of incompatible file schemas, oversized browser payloads, GPU scheduling surprises, or scope drift away from radar-only sensing.

## 1. Scope Lock

The workbench remains scoped to:

```text
radar self-transmit/self-receive sensing
small-baseline monostatic approximation
urban scene propagation
Sionna RT path/CIR generation
range-azimuth and range-elevation observations
```

Out of scope unless explicitly reintroduced:

```text
UE placement
BS-to-UE communication pass
communication-channel KPI workflow
real Doppler from moving target/platform
absolute calibrated RCS claim
```

## 2. Existing Campaign Probe

Campaign root:

```text
outputs/sionna_radar_campaigns/C002_full_radar_sensing
```

Required report files:

| File | Exists | Size |
|---|---:|---:|
| `reports/POSE_METRICS.csv` | yes | 9875 bytes |
| `reports/runs_index.csv` | yes | 6857 bytes |
| `reports/CAMPAIGN_SUMMARY.md` | yes | 3752 bytes |

CSV schemas:

```text
POSE_METRICS.csv shape: 30 rows x 22 columns
runs_index.csv shape: 30 rows x 13 columns
```

`POSE_METRICS.csv` columns:

```text
boresight_az_deg
boresight_el_deg
boresight_id
campaign
dominant_range_m
energy_in_fov
fov_energy_fraction
fov_path_fraction
look_x_m
look_y_m
look_z_m
max_interaction_depth
pose_id
range_max_m
run_dir
run_id
samples_per_src
seed
valid_path_count
x_m
y_m
z_m
```

Conclusion:

1. Phase 0 can list campaigns and runs using `POSE_METRICS.csv`.
2. No full run-folder scan is required for the run list.
3. The backend can expose a fast read-only result browser before any new Sionna simulation API exists.

## 3. Representative Run Probe

Representative run:

```text
outputs/sionna_radar_campaigns/C002_full_radar_sensing/runs/
  MM_C002full_Pp0_p0_BposY_S501_N500k
```

File sizes:

| File | Approx Size |
|---|---:|
| `cir.npz` | 325 MB |
| `paths_summary.npz` | 5.1 MB |
| `radar_observation.npz` | 2.8 MB |
| `metadata.json` | 19 KB |
| `metrics.json` | 2.9 KB |

Conclusion:

1. Browser must not download `cir.npz`.
2. Browser can safely request metadata and metrics.
3. `paths_summary.npz` and `radar_observation.npz` are small enough for backend-side cache generation.

## 4. NPZ Schema Probe

### `paths_summary.npz`

| Key | Shape | Dtype | Notes |
|---|---:|---|---|
| `tau_s` | `(1, 1, 175423)` | `float32` | path delay |
| `valid` | `(1, 1, 175423)` | `bool` | valid path mask |
| `theta_r_rad` | `(1, 1, 175423)` | `float32` | receiver polar angle |
| `phi_r_rad` | `(1, 1, 175423)` | `float32` | receiver azimuth angle |
| `theta_t_rad` | `(1, 1, 175423)` | `float32` | transmitter polar angle |
| `phi_t_rad` | `(1, 1, 175423)` | `float32` | transmitter azimuth angle |
| `doppler_hz` | `(1, 1, 175423)` | `float32` | all zeros in static scene |
| `interactions` | `(2, 1, 1, 175423)` | `uint32` | depth 1/2 interaction kind |
| `objects` | `(2, 1, 1, 175423)` | `uint32` | Sionna object indices; invalid sentinel may appear |
| `vertices` | `(2, 1, 1, 175423, 3)` | `float32` | interaction vertices |

### `radar_observation.npz`

| Key | Shape | Dtype | Notes |
|---|---:|---|---|
| `range_azimuth_power` | `(1334, 180)` | `float64` | save as `float32` for web cache |
| `range_elevation_power` | `(1334, 90)` | `float64` | save as `float32` for web cache |
| `range_edges_m` | `(1335,)` | `float64` | explicit axis |
| `azimuth_edges_deg` | `(181,)` | `float64` | explicit axis |
| `elevation_edges_deg` | `(91,)` | `float64` | explicit axis |
| `fov_path_mask` | `(175423,)` | `bool` | postprocessed FoV mask |
| `ranges_m` | `(175423,)` | `float32` | path range |
| `aoa_azimuth_deg` | `(175423,)` | `float32` | AoA azimuth |
| `aoa_elevation_deg` | `(175423,)` | `float32` | AoA elevation |
| `path_energy` | `(175423,)` | `float32` | path energy |

Conclusion:

1. The data contract in `02_DATA_CONTRACTS.md` is implementable with the current files.
2. Web cache code must flatten `(1,1,N)` and `(2,1,1,N,...)` arrays carefully.
3. `doppler_hz` must be displayed as static-scene zero-Doppler metadata, not as measured motion Doppler.

## 5. Web Cache Size Probe

Using the representative run:

```text
valid paths: 175423
FoV paths: 18275
top-500 estimated JSON size: about 111 KB
top-500 range span: 9.5716 m to 53.9388 m
top-500 energy span: 1.872e-11 to 8.964e-08
top-500 depth counts: depth 1 = 498, depth 2 = 2
range_azimuth float32 binary size: 960480 bytes
range_elevation float32 binary size: 480240 bytes
```

Conclusion:

1. `top_paths.json` with 500 paths is comfortably web-friendly.
2. Binary spectra are each below 1 MB after float32 conversion.
3. First implementation can use JSON for top paths and binary for spectra.
4. Interaction points should be filtered by `top_k`, `in_fov`, and energy before being sent to the browser.

## 6. Scene Geometry Probe

`metadata.json` contains:

```text
scene_geometry.object_count = 7
scene_geometry.material_names = brick, concrete, glass, marble, wood
objects = building_1 ... building_6, floor
```

Each object includes:

```text
bbox_min
bbox_max
bbox_center
face_count
material
surface_area
vertex_count
```

Material entries include:

```text
class = ITURadioMaterial
relative_permittivity
conductivity
scattering_coefficient = 0.5
scattering_pattern = BackscatteringPattern
thickness
xpd_coefficient
```

Conclusion:

1. Phase 1 can render building bounding boxes and material colors directly from `metadata.json`.
2. Object contribution visualization is feasible, but the cache builder must map Sionna object indices to object names consistently.
3. Invalid object sentinel values such as `4294967295` must be converted to `null` or `"unknown"` in web caches.

## 7. Environment Probe

Available Python packages:

```text
fastapi: OK
uvicorn: OK
pydantic: OK
pandas: OK
pyarrow: OK
numpy: OK
scipy: OK
```

Missing optional packages:

```text
zarr: MISSING
laspy: MISSING
open3d: MISSING
```

Available frontend tooling:

```text
Node.js 22.22.0
npm 10.9.4
```

Conclusion:

1. FastAPI backend can be implemented immediately.
2. Parquet cache can be implemented immediately through PyArrow.
3. Do not make Zarr, LAS/LAZ, or Open3D mandatory in MVP.
4. Point-cloud upload should start with simple `.ply`/`.xyz` preview or remain deferred.

## 8. GPU Probe

GPU status at probe time:

| GPU | Model | Total MB | Used MB | Utilization |
|---:|---|---:|---:|---:|
| 0 | NVIDIA H100 80GB HBM3 | 81559 | 3 | 0% |
| 1 | NVIDIA H100 80GB HBM3 | 81559 | 3 | 0% |
| 2 | NVIDIA H100 80GB HBM3 | 81559 | 3 | 0% |
| 3 | NVIDIA H100 80GB HBM3 | 81559 | 3 | 0% |
| 4 | NVIDIA H100 80GB HBM3 | 81559 | 74631 | 89% |
| 5 | NVIDIA H100 80GB HBM3 | 81559 | 74061 | 100% |
| 6 | NVIDIA H100 80GB HBM3 | 81559 | 74015 | 47% |
| 7 | NVIDIA H100 80GB HBM3 | 81559 | 73775 | 99% |

Conclusion:

1. Restricting the workbench scheduler to GPU0-3 is correct for the current deployment.
2. The backend must reject GPU IDs outside `[0, 1, 2, 3]` by default.
3. Health endpoints should report current memory and utilization before accepting jobs.

## 9. Main Implementation Risks After Probes

| Risk | Evidence | Mitigation |
|---|---|---|
| Browser payload explosion | `cir.npz` is 325 MB and paths are 175k | never load full CIR by default; use web cache |
| Object index confusion | path `objects` uses numeric ids and sentinel values | add explicit object-id mapping and unknown handling |
| FoV misinterpretation | `fov_path_mask` is postprocessed | UI labels FoV as postprocess unless sector pattern run exists |
| False Doppler claim | `doppler_hz` all zeros in static scene | hide range-Doppler or label it static/no-motion |
| Point cloud overpromise | `laspy`/`open3d` missing and Sionna needs mesh/proxy | point cloud preview only in MVP |
| GPU oversubscription | GPU4-7 busy; GPU0-3 requested by user | enforce allowed GPU set and one worker per GPU |

## 10. Go / No-Go Gates

Proceed to Phase 0:

```text
GO: campaign CSVs exist and are parseable
GO: metadata and metrics are small and readable
```

Proceed to Phase 1:

```text
GO: top-500 path cache is about 111 KB
GO: spectra binary arrays are below 1 MB each
GO: scene bbox is available in metadata
```

Proceed to Phase 2:

```text
GO after implementing cache generator and read-only API
NO-GO if Phase 0/1 cannot load existing C002-full reliably
```

Proceed to point-cloud conversion:

```text
NO-GO for MVP
GO only after point-cloud preview, mesh/proxy generation, material assignment,
and one low-sample Sionna validation run all pass
```
