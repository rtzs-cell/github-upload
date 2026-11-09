# 00 System Overview

## 1. Product Goal

Build a browser-based radar sensing workbench where a user can:

1. Load a city scene, point cloud, mesh, or building proxy geometry.
2. Place a monostatic/small-baseline radar platform.
3. Configure radar sensing parameters.
4. Submit Sionna RT sensing jobs to GPU0-3.
5. Visualize returned paths, reflection/scattering points, and spectra.
6. Compare how radar pose, boresight, frequency, and scattering settings change sensing utility.

The app is a research tool, not a marketing page.

## 2. Non-Negotiable Boundaries

| Boundary | Reason |
|---|---|
| Radar-only sensing by default | Current research task is radar self-Tx/Rx, not BS-to-UE communication. |
| Point cloud is not automatically a radio scene | Sionna RT needs intersectable geometry, e.g. mesh/proxy/Mitsuba scene. |
| FoV postprocessing must be labeled | Current FoV mask is not yet a true sector antenna pattern. |
| No absolute RCS claims | Current Sionna outputs support relative propagation/sensing metrics. |
| No real Doppler in static scene | Without platform/target motion, range-Doppler is not physically generated. |
| Web browser must not load full CIR by default | `cir.npz` can be hundreds of MB per run. |

## 3. System Architecture

```text
frontend React/Three.js
  |
  | HTTP/WebSocket
  v
backend FastAPI
  |
  | job queue / multiprocessing
  v
GPU workers on GPU0,1,2,3
  |
  | run Sionna RT + postprocess
  v
campaign artifact store
  |
  | web cache generator
  v
web-friendly data cache
```

## 4. Major Workflows

### Workflow A: Browse Existing C002-Full Results

1. Frontend requests campaign manifest.
2. Backend loads `POSE_METRICS.csv`.
3. User selects a run.
4. Frontend loads:
   - scene object bbox/materials
   - radar config
   - top paths
   - interaction points
   - spectra arrays or pre-rendered textures
5. User explores paths and spectra interactively.

### Workflow B: Single-Pose Simulation

1. User places radar in scene.
2. User configures frequency, FoV, scattering, `samples_per_src`.
3. Frontend posts a simulation request.
4. Backend validates request and creates a job.
5. GPU worker runs Sionna.
6. Backend generates web cache.
7. Frontend loads new result.

### Workflow C: Multi-Pose Campaign

1. User uploads or edits a pose manifest.
2. User chooses boresight sweep and solver settings.
3. Backend creates multiple run tasks.
4. GPU0-3 workers run tasks in parallel.
5. Frontend displays progress and partial results.
6. Final campaign summary and heatmaps become available.

### Workflow D: Dynamic Pose/Direction Exploration

Dynamic should initially mean cached sweep or repeated asynchronous simulation, not real-time continuous ray tracing.

Recommended behavior:

1. Dragging radar updates FoV geometry immediately.
2. Existing cached result appears instantly.
3. Missing result is marked `Needs simulation`.
4. User clicks `Run`.
5. Result becomes available after GPU job completes.

## 5. Dependencies Verified Locally

Available:

```text
Node.js 22.22.0
npm 10.9.4
Python 3.10.16
FastAPI 0.135.1
Uvicorn 0.41.0
Pydantic 2.10.6
Pandas 2.3.3
PyArrow 23.0.1
SciPy 1.15.3
scikit-learn 1.7.2
```

Missing:

```text
zarr
laspy
open3d
```

Implication:

1. Use FastAPI immediately.
2. Use PyArrow/Parquet for web cache if needed.
3. Do not depend on Open3D/laspy in MVP.
4. For point cloud upload, start with `.ply`/`.xyz` parser or frontend-only visualization; add `laspy/open3d` later.

## 6. Current Data Reality

Representative run:

```text
outputs/sionna_radar_campaigns/C002_full_radar_sensing/runs/
  MM_C002full_Pp0_p0_BposY_S501_N500k/
```

Approximate file sizes:

| File | Size |
|---|---:|
| `cir.npz` | 340 MB |
| `paths_summary.npz` | 5.3 MB |
| `radar_observation.npz` | 2.9 MB |
| `metadata.json` | 19 KB |
| `metrics.json` | 3 KB |

Therefore:

1. `metadata.json`, `metrics.json`, `radar_observation.npz`, and selected path subsets are web-friendly.
2. Full `cir.npz` is not web-friendly.
3. `paths_summary.npz` can be processed server-side into top-k paths and interaction point caches.
