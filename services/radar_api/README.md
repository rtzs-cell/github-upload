# Radar API

FastAPI backend for the radar-only Sionna RT sensing workbench.

Current scope:

1. Register the existing C002-full radar sensing campaign as read-only.
2. Expose campaign, run, metadata, scene-object, path, interaction, and spectrum APIs.
3. Generate web-friendly caches under `outputs/radar_workbench/web_cache/`.
4. Submit radar-only Sionna RT jobs through `/api/simulations`.
5. Schedule single-pose and multi-pose campaign jobs on selected GPU IDs within GPU0-3.
6. Archive generated runs under `outputs/radar_workbench/campaigns/`.
7. Create parameterized two-building monostatic radar experiments through `/api/experiments`.
8. Generate path statistics, beamforming analysis, and downloadable result bundles through `/api/results`.
9. Never serve or load full `cir.npz` during normal browsing.

Result download endpoints:

```text
GET /api/results/{run_id}/downloads
GET /api/results/{run_id}/downloads/{artifact_id}
GET /api/results/{run_id}/downloads/analysis_bundle
GET /api/results/{run_id}/result_bundle.zip
```

The catalog reports each available file and its byte size. `analysis_bundle` omits the
large raw CIR, raw path arrays, full path CSV, and beamformed coefficient array; use
the artifact-specific endpoint when only one source or analysis file is needed.

Workbench history deletion endpoints:

```text
DELETE /api/experiments/{experiment_id}
DELETE /api/results/{run_id}
```

Deleting a draft does not delete results created from it. Deleting a local result
removes its run directory, web cache, generated bundles, and path exports without
deleting the source draft. Built-in read-only campaigns and active jobs cannot be
deleted through these endpoints.

For campaign-mode simulations, every completed pose is written atomically to the
campaign run index and exposed through `workbench_local` immediately. The job status
field `available_run_ids` lists independently downloadable runs before the remaining
poses finish.

MPC analysis produces an AoA equirectangular spectrum:

```text
analysis/mpc_panorama.npz
figures/mpc_panorama.png
figures/mpc_view_front.png
figures/mpc_view_right.png
figures/mpc_view_back.png
figures/mpc_view_left.png
```

Key output folders:

```text
outputs/radar_workbench/experiments/
outputs/radar_workbench/campaigns/
outputs/radar_workbench/result_bundles/
outputs/radar_workbench/path_exports/
outputs/radar_workbench/web_cache/
```

Run locally:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

from this directory:

```bash
cd services/radar_api
```

Live Sionna ray-tracing jobs use an external Python runner so the FastAPI environment does not need to import `sionna.rt`.

Important environment variables:

```bash
RADAR_API_PYTHON=/path/to/backend/python
RADAR_SIONNA_PYTHON=/path/to/python/with/sionna
RADAR_SIONNA_PYTHONNOUSERSITE=1
RADAR_SIONNA_RUNNER_TIMEOUT_S=3600
```

Runtime checks:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/health/sionna_runtime
```

The start script prefers the project `.venv`, or the interpreter configured by
`RADAR_SIONNA_PYTHON`. Install the pinned dependencies from
`experiments/sionna_radar/requirements-runtime.txt` and keep
`RADAR_SIONNA_PYTHONNOUSERSITE=1` to prevent user-site package mixing. Portable
installation and one-port serving are documented in `docs/DEPLOYMENT_GUIDE.md`.
