# 06 Test and Spike Plan

This plan prevents implementation surprises by testing risky assumptions before building the full workbench.

## 1. Spike List

### Spike S0: Existing Result Loader

Question:

Can backend load C002-full campaign and expose run summaries quickly?

Test:

1. Parse `POSE_METRICS.csv`.
2. Load one run's `metadata.json`, `metrics.json`, `radar_observation.npz`.
3. Return JSON under 200 ms for metadata.

Pass:

```text
30 runs listed
one run metadata loads
no direct CIR load required
```

### Spike S1: Web Cache for One Run

Question:

Can one run be converted to web-friendly cache?

Test:

1. Build `top_paths.json` for top 500 paths.
2. Build `first_interactions.parquet`.
3. Build `range_azimuth.bin/json`.
4. Build `range_elevation.bin/json`.

Pass:

```text
cache size << cir.npz
frontend can load top paths quickly
binary spectra roundtrip exactly or within float32 tolerance
```

### Spike S2: Three.js Top Paths Rendering

Question:

Can browser render scene bbox + 500 paths + 20k interaction points?

Test:

1. Static local frontend.
2. Load one cached run.
3. Render 500 paths.
4. Render 20k points.

Pass:

```text
>= 30 FPS on dev workstation
hover/click remains responsive
```

### Spike S3: Spectrum Interaction

Question:

Can clicking a heatmap bin identify related paths?

Test:

1. Backend returns path bin indices in `top_paths.json`.
2. Frontend selects heatmap cell.
3. Matching paths are highlighted.

Pass:

```text
selected bin highlights correct subset
clearing selection restores all paths
```

### Spike S4: Single Pose Simulation

Question:

Can a web request create and run one Sionna sensing job?

Test:

1. Use low samples, e.g. 10000.
2. Submit radar pose.
3. Run on GPU0.
4. Build cache.
5. Frontend loads result.

Pass:

```text
job complete
run appears in UI
cache generated
```

### Spike S5: GPU0-3 Campaign Scheduling

Question:

Can backend run a small campaign on GPU0-3 without file corruption?

Test:

1. 4-8 tiny tasks.
2. GPU0-3 workers.
3. Check `runs_index.csv` and `POSE_METRICS.csv`.

Pass:

```text
all tasks complete
index rows match task count
no partial CSV lines
```

### Spike S6: Point Cloud Visualization

Question:

Can frontend load and display a point cloud without simulation?

Test:

1. Use a small `.ply` or generated point cloud.
2. Display with Three.js points.
3. Place radar on top.

Pass:

```text
point cloud visible
radar controls work
UI labels scene as visualization-only
simulation button disabled unless proxy/mesh exists
```

## 2. Acceptance Gates

| Gate | Required Spikes | Meaning |
|---|---|---|
| WG1 Result Browser Ready | S0, S1 | Existing data can drive UI. |
| WG2 Interactive Visualization Ready | S2, S3 | Paths/spectra linked in browser. |
| WG3 Single Simulation Ready | S4 | User can run one radar pose. |
| WG4 Campaign Ready | S5 | Multi-GPU campaign via web is reliable. |
| WG5 Point Cloud Preview Ready | S6 | Point cloud visualization is safe and clearly bounded. |

## 3. Regression Tests

### Backend Regression

1. `test_load_campaign_c002_full`
2. `test_build_cache_one_run`
3. `test_top_paths_schema`
4. `test_spectra_binary_roundtrip`
5. `test_invalid_pointcloud_scene_rejects_simulation`
6. `test_gpu_ids_restricted_to_0_1_2_3`
7. `test_job_status_lifecycle`

### Frontend Regression

1. Workbench loads without selected run.
2. Campaign list renders.
3. Run selection updates panels.
4. Layer toggles work.
5. Path hover tooltip appears.
6. Heatmap click updates selected bin.
7. Submit button disabled for visualization-only scene.
8. Large top-k warning appears above threshold.

## 4. Visual QA Checklist

For every representative run:

1. Radar marker at expected x/y/z.
2. Boresight arrow matches `look_at`.
3. FoV wedge/frustum centered on boresight.
4. Path colors match kind.
5. Specular/diffuse markers correct.
6. Range-azimuth FoV lines match `az_center +/- 60`.
7. Range-elevation FoV lines match `0` and `40`.
8. Metrics in UI match `POSE_METRICS.csv`.

## 5. Performance Budgets

| Operation | Target |
|---|---:|
| Load campaign run list | < 300 ms |
| Load run metadata | < 300 ms |
| Load top 500 paths | < 1 s |
| Load spectra | < 1 s |
| Render 500 paths | >= 30 FPS |
| Render 20k interaction points | >= 30 FPS |
| Submit single low-sample job | < 5 s overhead before worker starts |

## 6. Known Risk Burn-Down Order

1. Web cache feasibility.
2. Frontend rendering performance.
3. Spectrum-path linking.
4. Single Sionna job from API.
5. GPU0-3 scheduling from API.
6. Point cloud upload/preview.
7. Point cloud to simulation scene conversion.

Do not start Phase 4 point-cloud conversion before WG1-WG4 pass.
