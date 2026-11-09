export type CampaignSummary = {
  campaign_id: string
  display_name: string
  root: string
  run_count: number
  readonly: boolean
  created_at_utc: string | null
  source_experiment_id: string | null
}

export type SionnaRuntime = {
  available: boolean
  python: string | null
  python_exists: boolean
  python_no_user_site: boolean
  versions: {
    sionna_rt: string
    mitsuba: string
    drjit: string
    module_path: string
    path_solver_available: boolean
  } | null
  error?: string
}

export type RunSummary = {
  run_id: string
  pose_id: string
  boresight_id: string
  x_m: number
  y_m: number
  z_m: number
  look_x_m: number
  look_y_m: number
  look_z_m: number
  boresight_az_deg: number
  boresight_el_deg: number
  valid_path_count: number
  dominant_range_m: number
  range_max_m: number
  fov_energy_fraction: number
  fov_path_fraction: number
  energy_in_fov: number
  max_interaction_depth: number
  samples_per_src: number
  seed: number
  status: string
  campaign_id: string | null
  created_at_utc: string | null
  source_experiment_id: string | null
  display_name: string | null
}

export type MaterialPreset = {
  label: string
  description: string
}

export type ScenePreset = {
  id: string
  label: string
  description: string
}

export type ScenePresetCatalog = {
  materials: Record<string, MaterialPreset>
  scenes: ScenePreset[]
}

export type RunMetadata = {
  run_id: string
  config: Record<string, unknown>
  metadata: Record<string, any>
  metrics: Record<string, any>
  available_artifacts: {
    top_paths: boolean
    first_interactions: boolean
    range_azimuth: boolean
    range_elevation: boolean
    cir: boolean
  }
}

export type SceneObject = {
  object_id: string
  display_name?: string
  material: string
  bbox_min: [number, number, number]
  bbox_max: [number, number, number]
  bbox_center: [number, number, number]
  surface_area: number
  vertex_count: number
  face_count: number
  geometry_kind?: 'box' | 'model'
  center_m?: [number, number, number]
  size_m?: [number, number, number]
  rotation_deg?: [number, number, number]
  model?: ImportedModelAsset & {
    source_bbox_min: [number, number, number]
    source_bbox_max: [number, number, number]
  }
}

export type SceneImportResult = {
  source_type: 'osm' | 'geojson' | 'custom'
  source_key: string
  original_filename: string
  source_path: string
  origin: { latitude: number; longitude: number }
  object_count: number
  warnings: string[]
  buildings: Array<Record<string, any>>
  scene_patch?: Record<string, any>
}

export type ImportedModelAsset = {
  asset_id: string
  original_filename: string
  format: 'obj' | 'ply'
  source_path: string
  preview_url: string
  size_bytes: number
}

export type TopPath = {
  path_id: number
  kind: 'specular' | 'diffuse' | 'mixed' | 'unknown'
  depth: number
  range_m: number
  delay_s: number
  energy: number
  aoa_azimuth_deg: number
  aoa_elevation_deg: number
  aod_azimuth_deg: number | null
  aod_elevation_deg: number | null
  in_fov: boolean
  range_bin_idx: number | null
  azimuth_bin_idx: number | null
  elevation_bin_idx: number | null
  interactions: Array<{
    depth_index: number
    type: string
    object_id: string | null
    position_m: [number, number, number]
  }>
  polyline_m: Array<[number, number, number]>
}

export type TopPathsResponse = {
  schema_version: string
  run_id: string
  selection: Record<string, unknown>
  paths: TopPath[]
}

export type PathExportRequest = {
  draft_config: RadarDraftConfig
  top_k: number
  kind: 'all' | 'specular' | 'diffuse' | 'mixed' | 'unknown'
  in_fov: boolean
  note?: string
}

export type PathExportResponse = {
  export_id: string
  run_id: string
  root: string
  path_count: number
  files: Record<string, string>
}

export type SpectrumMetadata = {
  run_id: string
  kind: 'range_azimuth' | 'range_elevation'
  dtype: 'float32'
  shape: [number, number]
  layout: 'row-major'
  array_url: string
  range_edges_m: number[]
  angle_edges_deg: number[]
  angle_label: string
  scale: string
  recommended_display: {
    scale: string
    dynamic_range_db: number
  }
}

export type InteractionsResponse = {
  run_id: string
  columns: string[]
  interactions: Array<Record<string, number | string | boolean | null>>
}

export type ExperimentSummary = {
  schema_version: string
  experiment_id: string
  name: string
  created_at_utc: string
  status: string
  root: string
  files: Record<string, string>
}

export type ExperimentResponse = {
  manifest: ExperimentSummary
  config: Record<string, any>
}

export type PathStatisticsResponse = {
  summary: Record<string, any>
  files: Record<string, string>
}

export type ResultBundleResponse = {
  run_id: string
  bundle_path: string
}

export type DownloadArtifact = {
  artifact_id: string
  label: string
  category: 'bundle' | 'config' | 'raw' | 'table' | 'analysis' | string
  description: string
  size_bytes: number | null
  generated: boolean
  download_url: string
}

export type DownloadCatalogResponse = {
  run_id: string
  artifacts: DownloadArtifact[]
}

export type BeamformingResponse = {
  summary: Record<string, any>
  files: Record<string, string>
}

export type AnalysisArtifactsResponse = {
  summary: Record<string, any>
  files: Record<string, string>
}

export type RadarDraftConfig = {
  scene_id: string
  center_m: [number, number, number]
  look_at_m: [number, number, number]
  tx_rx_baseline_m: number
  az_width_deg: number
  el_min_deg: number
  el_max_deg: number
  rmax_m: number
  frequency_hz: number
  bandwidth_hz: number
  max_depth: number
  los: boolean
  specular_reflection: boolean
  diffuse_reflection: boolean
  scattering_enabled: boolean
  scattering_coefficient: number
  scattering_pattern: 'backscattering' | 'lambertian' | 'directive'
  alpha_r: number
  alpha_i: number
  lambda_: number
  tx_rows: number
  tx_cols: number
  rx_rows: number
  rx_cols: number
  tx_pattern: 'radar_array' | 'custom_gain_grid' | 'tr38901' | 'isotropic'
  tx_custom_gain_json: string
  tx_element_pattern: 'custom_gain_grid' | 'tr38901' | 'isotropic'
  tx_element_custom_gain_json: string
  rx_pattern: 'custom_gain_grid' | 'tr38901' | 'isotropic'
  rx_custom_gain_json: string
  ray_sampling_mode: 'full_sphere' | 'analysis_sector'
  tx_power_dbm: number
  tx_steering_azimuth_deg: number
  tx_steering_elevation_deg: number
  tx_taper: 'uniform' | 'hann'
  tx_beamforming_mode: 'steering_vector' | 'custom_complex_weights'
  tx_custom_weights_json: string
  beamforming_rx_mode: 'disabled' | 'uniform' | 'steering_vector' | 'custom_complex_weights'
  beamforming_steering_azimuth_deg: number
  beamforming_steering_elevation_deg: number
  beamforming_custom_weights_json: string
  chirp_duration_us: number
  chirp_idle_time_us: number
  num_chirps: number
  adc_samples: number
  noise_figure_db: number
  receiver_temperature_k: number
  cfar_pfa: number
  max_synthesis_paths: number
  cir_noise_enabled: boolean
  cir_noise_snr_db: number
  cir_noise_seed: number
  samples_per_src: number
  synthetic_array: boolean
  seed: number
  gpu_ids: number[]
}

export type SimulationStatus = 'idle' | 'draft_changed' | 'ready_to_run' | 'queued' | 'running' | 'complete' | 'failed'

export type RadarSimulationRequest = {
  scene_id: string
  scene_geometry?: Record<string, unknown> | null
  source_experiment_id?: string | null
  display_name?: string | null
  mode: 'single_pose' | 'campaign'
  poses?: Array<{
    center_m: [number, number, number]
    look_at_m: [number, number, number]
    tx_rx_baseline_m?: number
  }>
  radar: {
    center_m: [number, number, number]
    look_at_m: [number, number, number]
    tx_rx_baseline_m: number
    az_width_deg: number
    el_min_deg: number
    el_max_deg: number
    rmax_m: number
    range_bin_m: number
    angle_bin_deg: number
  }
  propagation: {
    frequency_hz: number
    bandwidth_hz: number
  }
  waveform: {
    tx_power_dbm: number
    chirp_duration_s: number
    idle_time_s: number
    num_chirps: number
    adc_samples: number
  }
  receiver: {
    noise_figure_db: number
    temperature_k: number
  }
  radar_processing: {
    cfar_pfa: number
    max_synthesis_paths: number
  }
  scattering: {
    enabled: boolean
    coefficient: number
    pattern: 'backscattering' | 'lambertian' | 'directive'
    alpha_r: number
    alpha_i: number
    lambda_: number
  }
  tx_array: {
    num_rows: number
    num_cols: number
    vertical_spacing: number
    horizontal_spacing: number
    pattern: string
    polarization: string
    gain_grid_json?: string | null
    element_pattern?: string | null
    element_gain_grid_json?: string | null
  }
  rx_array: {
    num_rows: number
    num_cols: number
    vertical_spacing: number
    horizontal_spacing: number
    pattern: string
    polarization: string
    gain_grid_json?: string | null
  }
  path_solver: {
    max_depth: number
    max_num_paths_per_src: number
    samples_per_src: number
    synthetic_array: boolean
    los: boolean
    specular_reflection: boolean
    diffuse_reflection: boolean
    refraction: boolean
    diffraction: boolean
    edge_diffraction: boolean
    seed: number
    initial_ray_sampling: {
      mode: 'full_sphere' | 'analysis_sector'
    }
  }
  observation: Record<string, unknown>
  compute: {
    samples_per_src: number
    seed: number
  }
  cir_noise?: {
    enabled: boolean
    snr_db: number
    seed: number
  }
  gpu_ids: number[]
}

export type SimulationJobResponse = {
  job_id: string
  status: string
  status_url: string
}

export type JobStatusResponse = {
  job_id: string
  status: string
  created_at_utc: string
  started_at_utc: string | null
  completed_at_utc: string | null
  progress: { total_tasks: number; completed_tasks: number; failed_tasks: number }
  gpu_ids: number[]
  current_tasks: Array<Record<string, unknown>>
  available_run_ids: string[]
  result: Record<string, unknown> | null
  error: string | null
}
