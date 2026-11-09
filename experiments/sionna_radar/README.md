# Sionna RT Urban Monostatic Radar Simulation Archive

This directory contains the reproducible execution scaffold for the
Sionna RT city monostatic radar propagation experiments described in
`refine-logs/EXPERIMENT_PLAN.md`.

## Directory Layout

```text
experiments/sionna_radar/
  README.md
  configs/
    runs.yaml                 # Planned run definitions.
  scripts/
    run_experiment.py         # Execute one Run ID.
    summarize_runs.py         # Build archive-level summary tables.
  src/sionna_radar/
    archive.py                # Run directories, metadata, serialization.
    config.py                 # YAML loading and run configuration helpers.
    processing.py             # Path/CIR metrics and radar-map processing.
    runner.py                 # Sionna RT experiment execution.

outputs/sionna_radar/
  runs/<RUN_ID>/
    config.yaml
    metadata.json
    metrics.json
    paths_summary.npz
    cir.npz
    figures/
  reports/
    RUN_SUMMARY.md
    runs_index.csv
```

## Current Scope

The runner focuses on the planned MUST-RUN claims:

- single-platform monostatic/SIMO geometry with Tx 1x1 and Rx 16x16;
- LoS-disabled self-leakage handling;
- depth-1/depth-2 reflected and scattered path extraction;
- 28 GHz main setting;
- diffuse scattering with `BackscatteringPattern`;
- conversion from Sionna paths/CIR to simple range-angle evidence.

It intentionally does not claim calibrated absolute RCS, radar hardware
leakage, Doppler for static scenes, or full sensor-chain behavior.

## Typical Commands

Run a single experiment:

```bash
python experiments/sionna_radar/scripts/run_experiment.py --run-id R003
```

Run all fast sanity experiments:

```bash
python experiments/sionna_radar/scripts/run_experiment.py --run-id R001
python experiments/sionna_radar/scripts/run_experiment.py --run-id R003
python experiments/sionna_radar/scripts/run_experiment.py --run-id R004
python experiments/sionna_radar/scripts/run_experiment.py --run-id R006
python experiments/sionna_radar/scripts/run_experiment.py --run-id R007
```

Summarize completed runs:

```bash
python experiments/sionna_radar/scripts/summarize_runs.py
```

