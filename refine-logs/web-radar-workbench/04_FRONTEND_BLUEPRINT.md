# 04 Frontend Blueprint

## 1. Frontend Stack

Recommended:

```text
React 18/19
TypeScript
Vite
Three.js via @react-three/fiber
@react-three/drei for controls/gizmos
Plotly.js or ECharts for spectra
TanStack Query for API state
Zustand for local interaction state
```

## 2. Main Layout

No landing page. First screen is the workbench.

```text
TopBar
  Scene selector | Campaign selector | Run button | Job status

LeftSidebar
  Scene layers
  Run list
  Filters

CenterViewport
  3D/2D scene viewer

RightInspector
  Radar params
  Propagation params
  Selected path/object details

BottomPanel
  Range-azimuth
  Range-elevation
  CIR
  Metrics
  Logs
```

## 3. Component Tree

```text
App
  WorkbenchLayout
    TopBar
      SceneSelector
      CampaignSelector
      JobStatusBadge
      RunButton
    LeftSidebar
      LayerPanel
      RunList
      PathFilters
    CenterViewport
      ViewModeTabs
      SceneCanvas
        PointCloudLayer
        MeshLayer
        BuildingBBoxLayer
        RadarPoseLayer
        FoVLayer
        PathLayer
        InteractionPointLayer
        SelectionHighlightLayer
    RightInspector
      RadarPoseEditor
      AntennaEditor
      PropagationEditor
      ScatteringEditor
      ObservationEditor
      SelectedEntityPanel
    BottomPanel
      SpectrumTabs
        RangeAzimuthPanel
        RangeElevationPanel
        CIRPanel
      MetricsTable
      JobLogs
```

## 4. State Model

Use two stores:

### Server State

Managed by TanStack Query:

```text
scenes
campaigns
runs
run metadata
top paths
interaction points
spectra
job status
```

### UI State

Managed by Zustand:

```ts
type WorkbenchState = {
  selectedSceneId: string | null
  selectedCampaignId: string | null
  selectedRunId: string | null
  selectedPathId: number | null
  selectedSpectrumBin: { kind: 'az' | 'el'; rangeIdx: number; angleIdx: number } | null
  viewMode: '3d' | 'topdown'
  visibleLayers: {
    pointCloud: boolean
    mesh: boolean
    bbox: boolean
    radar: boolean
    fov: boolean
    paths: boolean
    interactions: boolean
    hotspots: boolean
  }
  pathFilters: {
    kind: 'all' | 'specular' | 'diffuse' | 'mixed'
    inFovOnly: boolean
    topK: number
    minEnergyDb: number | null
    depth: 1 | 2 | null
  }
  draftRadarConfig: RadarConfig
}
```

## 5. 3D Scene Layers

### BuildingBBoxLayer

Input:

```ts
SceneObject[]
```

Render:

1. Box geometry from bbox min/max.
2. Material color from object material.
3. Optional labels.

### RadarPoseLayer

Render:

1. Tx marker.
2. Rx marker.
3. Rx array plane glyph.
4. Boresight arrow.
5. Draggable gizmo in edit mode.

### FoVLayer

3D frustum approximation:

1. Azimuth width: 120 deg default.
2. Elevation min/max: 0-40 deg.
3. Range length: `rmax_m` or display-limited length.

2D top-down:

1. Wedge sector.
2. Boresight arrow.

### PathLayer

Input:

```ts
TopPath[]
```

Render:

1. Polyline through Tx, interaction vertices, Rx.
2. Color by kind.
3. Width by normalized log energy.
4. Hover tooltip.
5. Click selection.

Never render all 175k paths by default.

### InteractionPointLayer

Input:

```ts
InteractionPoint[]
```

Render:

1. Specular marker: circle.
2. Diffuse marker: cross or point sprite.
3. Color/size by energy.
4. Optional object grouping.

## 6. Spectra Panels

### RangeAzimuthPanel

Render heatmap from:

```text
range_azimuth.bin + metadata
```

Interactions:

1. Hover shows range/azimuth/power.
2. Click bin sets `selectedSpectrumBin`.
3. Selected bin filters/highlights paths contributing to bin.
4. Cyan FoV boundary lines.

### RangeElevationPanel

Same as range-azimuth, with elevation axis and 0/40 deg FoV lines.

## 7. Radar Parameter Editors

### RadarPoseEditor

Controls:

1. Numeric x/y/z.
2. Numeric look-at x/y/z.
3. Azimuth/elevation display.
4. Baseline offset.
5. `Reset to selected run`.
6. `Use current view direction`.

### PropagationEditor

Controls:

1. Frequency presets: 28/60/77 GHz.
2. Bandwidth.
3. Max depth.
4. LoS toggle with warning.
5. Specular/diffuse toggles.

### ScatteringEditor

Controls:

1. coefficient.
2. pattern.
3. alpha_r.
4. alpha_i.
5. lambda.

### ComputeEditor

Controls:

1. samples_per_src.
2. seed.
3. GPU IDs, default `[0,1,2,3]`.
4. output campaign name.

## 8. Frontend Bug-Prevention Rules

1. Do not allow run submission if selected scene is not simulation-ready.
2. Warn if FoV is postprocess-only.
3. Warn if `samples_per_src` is high.
4. Do not request full CIR unless user explicitly clicks advanced download.
5. Path rendering must degrade gracefully if top paths cache is missing.
6. All units must be shown in labels.
7. Pose edits should not overwrite completed run configs; they create draft config.

## 9. MVP Acceptance Criteria

Phase 0/1 frontend is accepted when:

1. Loads existing C002-full campaign.
2. Displays 30 runs in list.
3. Selecting a run updates scene, metrics, and spectra.
4. 3D or top-down view displays radar pose, FoV, and top paths.
5. Range-azimuth and range-elevation display correctly.
6. Path hover shows at least path ID, range, energy, kind.
7. No browser tab crash with topK=500.
