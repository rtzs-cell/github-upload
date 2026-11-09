# 10 Risk Register

**Purpose**: Keep implementation risks explicit, testable, and separated from feature wishes.

## 1. Risk Severity Key

| Level | Meaning |
|---|---|
| Critical | Can invalidate the workbench or the radar-only research conclusion. |
| High | Can block a phase or create misleading visualizations. |
| Medium | Can slow implementation or reduce usability. |
| Low | Annoying but locally fixable. |

## 2. Active Risks

| ID | Severity | Risk | Trigger | Mitigation | Gate |
|---|---|---|---|---|---|
| R01 | Critical | Scope drifts into BS-UE communication | API/UI adds UE or comm channel workflow | Radar-only schemas; no UE entities in MVP | Review API before P2/P5 |
| R02 | Critical | FoV postprocessing mistaken for physical beam | UI calls FoV mask a sector antenna result | Label postprocess FoV; separate C004-sector | UI copy check |
| R03 | High | Browser downloads full CIR | Frontend links `cir.npz` as default artifact | `available_artifacts.cir=false`; advanced download only | Network QA |
| R04 | High | Path/object mapping wrong | Numeric Sionna object IDs not mapped to names | Build explicit mapping; convert sentinel to unknown | Cache tests |
| R05 | High | Heatmap/path linking wrong | Missing bin indices or transposed spectra | Store bin indices and axis metadata | Roundtrip tests |
| R06 | High | GPU worker imports Sionna before CUDA mask | Worker sees wrong GPU or all GPUs | Set env before import in child process | GPU smoke test |
| R07 | High | Concurrent campaign writes corrupt CSV | Four workers append simultaneously | File lock or per-task records then merge | C002-lite web smoke |
| R08 | High | Point cloud presented as simulation-ready | Upload workflow enables Run for point cloud | Backend rejects `simulation_ready=false` | API validation test |
| R09 | Medium | Top-k hides important diffuse paths | Energy top-k dominated by specular paths | Include optional diffuse quota and filters | Visual QA |
| R10 | Medium | Static scene range-Doppler misinterpreted | Doppler tab displays zeros as result | Hide or label no-motion Doppler | UI QA |
| R11 | Medium | Cache schema changes break frontend | Unversioned JSON changes | `schema_version`, typed frontend models | Schema test |
| R12 | Medium | Large point cloud freezes UI | Renderer loads all points at once | Size limits, downsample, LOD | P7 spike |
| R13 | Medium | New runs overwrite old outputs | Non-unique run IDs | timestamp/job/campaign namespace | Job tests |
| R14 | Medium | Radar baseline orientation inaccurate | Tx/Rx offset fixed in y direction | Implement boresight-perpendicular baseline before paper-grade runs | P5 validation |
| R15 | Low | Missing optional packages block MVP | `zarr`, `laspy`, `open3d` absent | Keep optional and deferred | Dependency check |

## 3. Highest-Priority Burn-Down

1. R03: prove browser never requests `cir.npz`.
2. R04: prove path/object mapping is stable.
3. R05: prove heatmap bins link to paths correctly.
4. R06/R07: prove GPU0-3 worker scheduling is isolated and file-safe.
5. R08: prove point cloud cannot accidentally run Sionna.

## 4. Review Gates

Before merging Phase 0:

```text
R01, R03 checked
```

Before merging Phase 1:

```text
R02, R04, R05, R09, R10 checked
```

Before enabling live simulation:

```text
R06, R07, R13, R14 checked
```

Before enabling point cloud upload:

```text
R08, R12, R15 checked
```
