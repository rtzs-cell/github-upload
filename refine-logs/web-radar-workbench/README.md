# Web Radar/ISAC Workbench Implementation Blueprint

**Date**: 2026-07-01  
**Scope**: Build a web workbench for radar-only Sionna RT sensing simulation, visualization, and GPU0-3 execution.

This folder decomposes the web workbench plan into implementation-ready documents. It is designed to prevent late-stage confusion about files, APIs, data formats, GPU jobs, and visualization semantics.

## Document Map

| File | Purpose |
|---|---|
| `00_SYSTEM_OVERVIEW.md` | System architecture, user workflows, hard boundaries. |
| `01_REPOSITORY_AND_ARTIFACTS.md` | Exact folder layout, generated artifacts, naming rules, cleanup policy. |
| `02_DATA_CONTRACTS.md` | Scene, run, path, spectrum, and web-cache schemas. |
| `03_API_CONTRACTS.md` | FastAPI endpoint contracts and request/response examples. |
| `04_FRONTEND_BLUEPRINT.md` | UI layout, components, Three.js layers, state model, interactions. |
| `05_BACKEND_GPU_BLUEPRINT.md` | Backend modules, GPU0-3 worker model, job lifecycle, failure handling. |
| `06_TEST_AND_SPIKE_PLAN.md` | Spikes, tests, acceptance gates, bug-prevention checklist. |
| `07_IMPLEMENTATION_MILESTONES.md` | Phased implementation order and done criteria. |
| `08_PREIMPLEMENTATION_PROBES.md` | Real-data probes for schemas, sizes, dependencies, and GPU0-3 status. |
| `09_IMPLEMENTATION_RUNBOOK.md` | Step-by-step build order with gates, commands, tests, and artifact targets. |
| `10_RISK_REGISTER.md` | Active implementation risks and phase-specific review gates. |
| `11_ARTIFACT_INVENTORY.md` | Primary/derived/ephemeral artifact inventory and archival policy. |
| `12_PHASE_TASK_MATRIX.md` | Auditable task matrix for every implementation phase. |
| `probes/c002_full_probe_summary.json` | Machine-readable summary of the C002-full probe. |

## Core Decision Summary

1. **MVP starts as a result browser**, not as a full point-cloud-to-Sionna converter.
2. **Point clouds are visualization assets first**. Sionna RT simulation needs mesh/proxy geometry.
3. **Do not stream `cir.npz` to the browser**. It can be hundreds of MB per run.
4. **Generate web-friendly caches** from `paths_summary.npz` and `radar_observation.npz`.
5. **Use GPU0,1,2,3 via one worker process per GPU**, reusing the already tested parallel strategy.
6. **Keep radar sensing separate from communication**. No UE workflow is included in this workbench unless explicitly added later.

## Recommended First Build Target

Build Phase 0 + Phase 1 first:

```text
Existing C002-full result browser
  -> load run list and metrics
  -> show 3D/2D city geometry
  -> show radar pose, FoV, selected top paths, interaction points
  -> show range-azimuth/range-elevation heatmaps
  -> link path selection and spectrum selection
```

Only after this works reliably should the app submit new Sionna simulations.

## Implementation Control Flow

Use the documents in this order when implementing:

```text
08_PREIMPLEMENTATION_PROBES.md
  -> confirms what is already true in the existing C002-full data

09_IMPLEMENTATION_RUNBOOK.md
  -> defines the phase-by-phase execution order

10_RISK_REGISTER.md
  -> checks whether a phase is allowed to proceed

11_ARTIFACT_INVENTORY.md
  -> ensures files are written to the correct archival location

12_PHASE_TASK_MATRIX.md
  -> tracks phase tasks, tests, and stop conditions by ID
```

The older one-file plan `refine-logs/WEB_RADAR_ISAC_UI_PLAN.md` is retained as historical background. This folder is the implementation source of truth.
