import type { RadarDraftConfig, RunMetadata, RunSummary, SceneObject } from '../api/types'

export function runToDraftConfig(run: RunSummary | null, metadata: RunMetadata | null): RadarDraftConfig {
  const devices = metadata?.metadata?.devices ?? {}
  const fov = metadata?.metrics?.radar_observation?.fov ?? {}
  const frequencyHz = Number(metadata?.metadata?.frequency_hz ?? 28e9)
  const config = metadata?.config as any
  const txPattern = String(config?.tx_array?.pattern ?? 'iso')
  const txElementPattern = String(config?.tx_array?.element_pattern ?? (txPattern === 'radar_array' ? 'tr38901' : txPattern))
  const rxPattern = String(config?.rx_array?.pattern ?? 'iso')
  return {
    scene_id: String(config?.scene ?? 'simple_street_canyon'),
    center_m: [
      Number(run?.x_m ?? 0),
      Number(run?.y_m ?? 0),
      Number(run?.z_m ?? 10),
    ],
    look_at_m: [
      Number(run?.look_x_m ?? devices.look_at_m?.[0] ?? 0),
      Number(run?.look_y_m ?? devices.look_at_m?.[1] ?? 30),
      Number(run?.look_z_m ?? devices.look_at_m?.[2] ?? 10),
    ],
    tx_rx_baseline_m: Number(config?.workbench?.tx_rx_baseline_m ?? 0.1),
    az_width_deg: Number(fov.az_width_deg ?? 120),
    el_min_deg: Number(fov.el_min_deg ?? 0),
    el_max_deg: Number(fov.el_max_deg ?? 40),
    rmax_m: Number(fov.rmax_m ?? 200),
    frequency_hz: frequencyHz,
    bandwidth_hz: Number(config?.bandwidth_hz ?? 1e9),
    max_depth: Number(config?.path_solver?.max_depth ?? 2),
    los: Boolean(config?.path_solver?.los ?? false),
    specular_reflection: Boolean(config?.path_solver?.specular_reflection ?? true),
    diffuse_reflection: Boolean(config?.path_solver?.diffuse_reflection ?? true),
    scattering_enabled: Boolean(config?.scattering?.enabled ?? true),
    scattering_coefficient: Number(config?.scattering?.coefficient ?? 0.5),
    scattering_pattern: (config?.scattering?.pattern ?? 'backscattering') as RadarDraftConfig['scattering_pattern'],
    alpha_r: Number(config?.scattering?.alpha_r ?? 20),
    alpha_i: Number(config?.scattering?.alpha_i ?? 20),
    lambda_: Number(config?.scattering?.lambda_ ?? 0.3),
    tx_rows: Number(config?.tx_array?.num_rows ?? config?.tx_array?.rows ?? 1),
    tx_cols: Number(config?.tx_array?.num_cols ?? config?.tx_array?.cols ?? 1),
    rx_rows: Number(config?.rx_array?.num_rows ?? config?.rx_array?.rows ?? 16),
    rx_cols: Number(config?.rx_array?.num_cols ?? config?.rx_array?.cols ?? 16),
    tx_pattern: (txPattern === 'radar_array' ? 'radar_array' : txPattern === 'custom_gain_grid' ? 'custom_gain_grid' : txPattern === 'tr38901' ? 'tr38901' : 'isotropic') as RadarDraftConfig['tx_pattern'],
    tx_custom_gain_json: String(config?.tx_array?.gain_grid_json ?? ''),
    tx_element_pattern: (txElementPattern === 'custom_gain_grid' ? 'custom_gain_grid' : txElementPattern === 'isotropic' || txElementPattern === 'iso' ? 'isotropic' : 'tr38901') as RadarDraftConfig['tx_element_pattern'],
    tx_element_custom_gain_json: String(config?.tx_array?.element_gain_grid_json ?? ''),
    rx_pattern: (rxPattern === 'custom_gain_grid' ? 'custom_gain_grid' : rxPattern === 'tr38901' ? 'tr38901' : 'isotropic') as RadarDraftConfig['rx_pattern'],
    rx_custom_gain_json: String(config?.rx_array?.gain_grid_json ?? ''),
    ray_sampling_mode: (config?.path_solver?.initial_ray_sampling?.mode ?? 'full_sphere') as RadarDraftConfig['ray_sampling_mode'],
    tx_power_dbm: Number(config?.tx_power_dbm ?? 30),
    tx_steering_azimuth_deg: Number(config?.beamforming?.tx_steering_azimuth_deg ?? 0),
    tx_steering_elevation_deg: Number(config?.beamforming?.tx_steering_elevation_deg ?? 0),
    tx_taper: (config?.beamforming?.tx_taper ?? 'uniform') as RadarDraftConfig['tx_taper'],
    tx_beamforming_mode: (config?.beamforming?.tx_weight_mode ?? (config?.beamforming?.tx_mode === 'custom_complex_weights' ? 'custom_complex_weights' : 'steering_vector')) as RadarDraftConfig['tx_beamforming_mode'],
    tx_custom_weights_json: String(config?.beamforming?.tx_custom_weights_json ?? ''),
    beamforming_rx_mode: (config?.beamforming?.rx_mode ?? 'uniform') as RadarDraftConfig['beamforming_rx_mode'],
    beamforming_steering_azimuth_deg: Number(config?.beamforming?.steering_azimuth_deg ?? 0),
    beamforming_steering_elevation_deg: Number(config?.beamforming?.rx_steering_elevation_deg ?? config?.beamforming?.steering_elevation_deg ?? 0),
    beamforming_custom_weights_json: String(config?.beamforming?.custom_weights_json ?? ''),
    chirp_duration_us: Number(config?.waveform?.chirp_duration_s ?? 50e-6) * 1e6,
    chirp_idle_time_us: Number(config?.waveform?.idle_time_s ?? 10e-6) * 1e6,
    num_chirps: Number(config?.waveform?.num_chirps ?? 32),
    adc_samples: Number(config?.waveform?.adc_samples ?? 0),
    noise_figure_db: Number(config?.receiver?.noise_figure_db ?? 8),
    receiver_temperature_k: Number(config?.receiver?.temperature_k ?? 290),
    cfar_pfa: Number(config?.radar_processing?.cfar_pfa ?? 1e-5),
    max_synthesis_paths: Number(config?.radar_processing?.max_synthesis_paths ?? 256),
    cir_noise_enabled: Boolean(config?.cir_noise?.enabled ?? config?.radar_processing?.cir_noise?.enabled ?? false),
    cir_noise_snr_db: Number(config?.cir_noise?.snr_db ?? config?.radar_processing?.cir_noise?.snr_db ?? 20),
    cir_noise_seed: Number(config?.cir_noise?.seed ?? config?.radar_processing?.cir_noise?.seed ?? 1001),
    samples_per_src: Number(config?.path_solver?.samples_per_src ?? 10000),
    synthetic_array: Boolean(config?.path_solver?.synthetic_array ?? true),
    seed: Number(config?.path_solver?.seed ?? run?.seed ?? 501),
    gpu_ids: [0, 1, 2, 3],
  }
}

export function experimentToDraftConfig(config: Record<string, any>): RadarDraftConfig {
  const radar = config.radar ?? {}
  const waveform = config.waveform ?? {}
  const arrays = config.arrays ?? {}
  const propagation = config.propagation ?? {}
  const scattering = config.scattering ?? {}
  const solver = config.solver ?? {}
  const analysisGate = config.analysis_gate ?? {}
  const beamforming = config.beamforming ?? {}
  const txPattern = String(arrays.tx?.pattern ?? 'radar_array')
  const txElementPattern = String(arrays.tx?.element_pattern ?? (txPattern === 'radar_array' ? 'tr38901' : txPattern))
  const rxPattern = String(arrays.rx?.pattern ?? 'iso')
  return {
    scene_id: String(config.scene?.scene_xml_path ?? config.scene?.scene_xml ?? 'simple_street_canyon'),
    center_m: vector3(radar.center_m, [0, 0, 10]),
    look_at_m: vector3(radar.look_at_m, [455, 5, 40]),
    tx_rx_baseline_m: Number(radar.tx_rx_baseline_m ?? 0.1),
    az_width_deg: Number(analysisGate.azimuth_width_deg ?? radar.azimuth_beamwidth_deg ?? 120),
    el_min_deg: Number(analysisGate.elevation_min_deg ?? 0),
    el_max_deg: Number(analysisGate.elevation_max_deg ?? 40),
    rmax_m: Number(analysisGate.range_max_m ?? radar.range_max_m ?? 900),
    frequency_hz: Number(waveform.frequency_hz ?? 28e9),
    bandwidth_hz: Number(waveform.bandwidth_hz ?? 1e9),
    max_depth: Number(propagation.max_depth ?? 2),
    los: Boolean(propagation.los ?? false),
    specular_reflection: Boolean(propagation.specular_reflection ?? true),
    diffuse_reflection: Boolean(propagation.diffuse_reflection ?? true),
    scattering_enabled: Boolean(scattering.enabled ?? true),
    scattering_coefficient: Number(scattering.coefficient ?? 0.5),
    scattering_pattern: (scattering.pattern ?? 'backscattering') as RadarDraftConfig['scattering_pattern'],
    alpha_r: Number(scattering.alpha_r ?? 20),
    alpha_i: Number(scattering.alpha_i ?? 20),
    lambda_: Number(scattering.lambda_ ?? 0.3),
    tx_rows: Number(arrays.tx?.num_rows ?? 1),
    tx_cols: Number(arrays.tx?.num_cols ?? 1),
    rx_rows: Number(arrays.rx?.num_rows ?? 16),
    rx_cols: Number(arrays.rx?.num_cols ?? 16),
    tx_pattern: (txPattern === 'radar_array' ? 'radar_array' : txPattern === 'custom_gain_grid' ? 'custom_gain_grid' : txPattern === 'tr38901' ? 'tr38901' : 'isotropic') as RadarDraftConfig['tx_pattern'],
    tx_custom_gain_json: String(arrays.tx?.gain_grid_json ?? ''),
    tx_element_pattern: (txElementPattern === 'custom_gain_grid' ? 'custom_gain_grid' : txElementPattern === 'isotropic' || txElementPattern === 'iso' ? 'isotropic' : 'tr38901') as RadarDraftConfig['tx_element_pattern'],
    tx_element_custom_gain_json: String(arrays.tx?.element_gain_grid_json ?? ''),
    rx_pattern: (rxPattern === 'custom_gain_grid' ? 'custom_gain_grid' : rxPattern === 'tr38901' ? 'tr38901' : 'isotropic') as RadarDraftConfig['rx_pattern'],
    rx_custom_gain_json: String(arrays.rx?.gain_grid_json ?? ''),
    ray_sampling_mode: (solver.initial_ray_sampling?.mode ?? 'full_sphere') as RadarDraftConfig['ray_sampling_mode'],
    tx_power_dbm: Number(waveform.tx_power_dbm ?? 30),
    tx_steering_azimuth_deg: Number(beamforming.tx_steering_azimuth_deg ?? 0),
    tx_steering_elevation_deg: Number(beamforming.tx_steering_elevation_deg ?? 0),
    tx_taper: (beamforming.tx_taper ?? 'uniform') as RadarDraftConfig['tx_taper'],
    tx_beamforming_mode: (beamforming.tx_weight_mode ?? (beamforming.tx_mode === 'custom_complex_weights' ? 'custom_complex_weights' : 'steering_vector')) as RadarDraftConfig['tx_beamforming_mode'],
    tx_custom_weights_json: String(beamforming.tx_custom_weights_json ?? ''),
    beamforming_rx_mode: (beamforming.rx_mode ?? 'steering_vector') as RadarDraftConfig['beamforming_rx_mode'],
    beamforming_steering_azimuth_deg: Number(beamforming.rx_steering_azimuth_deg ?? beamforming.steering_azimuth_deg ?? 0),
    beamforming_steering_elevation_deg: Number(beamforming.rx_steering_elevation_deg ?? beamforming.steering_elevation_deg ?? 0),
    beamforming_custom_weights_json: String(beamforming.custom_weights_json ?? ''),
    chirp_duration_us: Number(waveform.chirp_duration_s ?? 50e-6) * 1e6,
    chirp_idle_time_us: Number(waveform.idle_time_s ?? 10e-6) * 1e6,
    num_chirps: Number(waveform.num_chirps ?? 32),
    adc_samples: Number(waveform.adc_samples ?? 0),
    noise_figure_db: Number(config.receiver?.noise_figure_db ?? 8),
    receiver_temperature_k: Number(config.receiver?.temperature_k ?? 290),
    cfar_pfa: Number(config.radar_processing?.cfar_pfa ?? 1e-5),
    max_synthesis_paths: Number(config.radar_processing?.max_synthesis_paths ?? 256),
    cir_noise_enabled: Boolean(config.cir_noise?.enabled ?? config.radar_processing?.cir_noise?.enabled ?? false),
    cir_noise_snr_db: Number(config.cir_noise?.snr_db ?? config.radar_processing?.cir_noise?.snr_db ?? 20),
    cir_noise_seed: Number(config.cir_noise?.seed ?? config.radar_processing?.cir_noise?.seed ?? 1001),
    samples_per_src: Number(solver.samples_per_src ?? 500000),
    synthetic_array: Boolean(solver.synthetic_array ?? true),
    seed: Number(solver.seed ?? 501),
    gpu_ids: Array.isArray(solver.gpu_ids) ? solver.gpu_ids.map(Number) : [0, 1, 2, 3],
  }
}

export function experimentToSceneObjects(config: Record<string, any>): SceneObject[] {
  const scene = config.scene ?? {}
  const items = [
    scene.ground ? { id: 'floor', ...scene.ground } : null,
    ...(Array.isArray(scene.buildings) ? scene.buildings : []),
  ].filter(Boolean) as Array<Record<string, any>>
  return items.map((item) => {
    const center = vector3(item.center_m, [0, 0, 0])
    const size = vector3(item.size_m, [1, 1, 1])
    const rotation = vector3(item.rotation_deg, [0, 0, 0])
    const { min, max } = rotatedBoxBounds(center, size, rotation)
    const surfaceArea = 2 * (size[0] * size[1] + size[0] * size[2] + size[1] * size[2])
    return {
      object_id: String(item.id ?? 'object'),
      display_name: String(item.name ?? item.id ?? 'object'),
      material: String(item.material ?? 'concrete'),
      bbox_min: min,
      bbox_max: max,
      bbox_center: center,
      surface_area: surfaceArea,
      vertex_count: 8,
      face_count: 12,
      geometry_kind: item.model ? 'model' : 'box',
      center_m: center,
      size_m: size,
      rotation_deg: rotation,
      model: item.model,
    }
  })
}

export function draftToExperimentConfig(base: Record<string, any>, draft: RadarDraftConfig): Record<string, any> {
  const config = JSON.parse(JSON.stringify(base)) as Record<string, any>
  config.radar = {
    ...(config.radar ?? {}),
    center_m: draft.center_m,
    look_at_m: draft.look_at_m,
    tx_rx_baseline_m: draft.tx_rx_baseline_m,
    azimuth_beamwidth_deg: draft.az_width_deg,
    elevation_beamwidth_deg: draft.el_max_deg - draft.el_min_deg,
    range_max_m: draft.rmax_m,
  }
  config.waveform = {
    ...(config.waveform ?? {}),
    frequency_hz: draft.frequency_hz,
    bandwidth_hz: draft.bandwidth_hz,
    tx_power_dbm: draft.tx_power_dbm,
    chirp_duration_s: draft.chirp_duration_us * 1e-6,
    idle_time_s: draft.chirp_idle_time_us * 1e-6,
    num_chirps: draft.num_chirps,
    adc_samples: draft.adc_samples,
  }
  config.arrays = {
    ...(config.arrays ?? {}),
    tx: {
      ...(config.arrays?.tx ?? {}),
      num_rows: draft.tx_rows,
      num_cols: draft.tx_cols,
      vertical_spacing: 0.5,
      horizontal_spacing: 0.5,
      pattern: draft.tx_pattern === 'isotropic' ? 'iso' : draft.tx_pattern,
      polarization: 'V',
      gain_grid_json: draft.tx_pattern === 'custom_gain_grid' ? draft.tx_custom_gain_json : null,
      element_pattern: draft.tx_pattern === 'radar_array'
        ? (draft.tx_element_pattern === 'isotropic' ? 'iso' : draft.tx_element_pattern)
        : null,
      element_gain_grid_json: draft.tx_pattern === 'radar_array' && draft.tx_element_pattern === 'custom_gain_grid'
        ? draft.tx_element_custom_gain_json
        : null,
    },
    rx: {
      ...(config.arrays?.rx ?? {}),
      num_rows: draft.rx_rows,
      num_cols: draft.rx_cols,
      vertical_spacing: 0.5,
      horizontal_spacing: 0.5,
      pattern: draft.rx_pattern === 'isotropic' ? 'iso' : draft.rx_pattern,
      polarization: 'V',
      gain_grid_json: draft.rx_pattern === 'custom_gain_grid' ? draft.rx_custom_gain_json : null,
    },
  }
  config.beamforming = {
    ...(config.beamforming ?? {}),
    tx_mode: draft.tx_pattern === 'radar_array' || draft.tx_pattern === 'custom_gain_grid' ? 'embedded_sionna_pattern' : draft.tx_beamforming_mode,
    tx_weight_mode: draft.tx_pattern === 'custom_gain_grid' ? 'steering_vector' : draft.tx_beamforming_mode,
    tx_steering_azimuth_deg: draft.tx_steering_azimuth_deg,
    tx_steering_elevation_deg: draft.tx_steering_elevation_deg,
    tx_taper: draft.tx_taper,
    tx_custom_weights_json: draft.tx_pattern !== 'custom_gain_grid' && draft.tx_beamforming_mode === 'custom_complex_weights'
      ? draft.tx_custom_weights_json
      : null,
    rx_mode: draft.beamforming_rx_mode,
    rx_steering_azimuth_deg: draft.beamforming_steering_azimuth_deg,
    rx_steering_elevation_deg: draft.beamforming_steering_elevation_deg,
    steering_azimuth_deg: draft.beamforming_steering_azimuth_deg,
    steering_elevation_deg: draft.beamforming_steering_elevation_deg,
    custom_weights_json: draft.beamforming_custom_weights_json,
  }
  config.receiver = {
    ...(config.receiver ?? {}),
    noise_figure_db: draft.noise_figure_db,
    temperature_k: draft.receiver_temperature_k,
  }
  config.radar_processing = {
    ...(config.radar_processing ?? {}),
    cfar_pfa: draft.cfar_pfa,
    max_synthesis_paths: draft.max_synthesis_paths,
    cir_noise: {
      enabled: draft.cir_noise_enabled,
      snr_db: draft.cir_noise_snr_db,
      seed: draft.cir_noise_seed,
    },
  }
  config.propagation = {
    ...(config.propagation ?? {}),
    max_depth: draft.max_depth,
    los: draft.los,
    specular_reflection: draft.specular_reflection,
    diffuse_reflection: draft.diffuse_reflection,
  }
  config.scattering = {
    ...(config.scattering ?? {}),
    enabled: draft.scattering_enabled,
    coefficient: draft.scattering_coefficient,
    pattern: draft.scattering_pattern,
    alpha_r: draft.alpha_r,
    alpha_i: draft.alpha_i,
    lambda_: draft.lambda_,
  }
  config.solver = {
    ...(config.solver ?? {}),
    samples_per_src: draft.samples_per_src,
    synthetic_array: draft.synthetic_array,
    seed: draft.seed,
    gpu_ids: draft.gpu_ids,
    initial_ray_sampling: { mode: draft.ray_sampling_mode },
  }
  config.analysis_gate = {
    ...(config.analysis_gate ?? {}),
    azimuth_width_deg: draft.az_width_deg,
    elevation_min_deg: draft.el_min_deg,
    elevation_max_deg: draft.el_max_deg,
    range_max_m: draft.rmax_m,
  }
  return config
}

function rotatedBoxBounds(
  center: [number, number, number],
  size: [number, number, number],
  rotationDeg: [number, number, number],
) {
  const [rx, ry, rz] = rotationDeg.map((value) => value * Math.PI / 180)
  const [cx, sx] = [Math.cos(rx), Math.sin(rx)]
  const [cy, sy] = [Math.cos(ry), Math.sin(ry)]
  const [cz, sz] = [Math.cos(rz), Math.sin(rz)]
  const matrix = [
    [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
    [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
    [-sy, cy * sx, cy * cx],
  ]
  const half = size.map((value) => value / 2)
  const points: number[][] = []
  for (const x of [-half[0], half[0]]) for (const y of [-half[1], half[1]]) for (const z of [-half[2], half[2]]) {
    const local = [x, y, z]
    points.push(matrix.map((row, axis) => center[axis] + row.reduce((sum, value, index) => sum + value * local[index], 0)))
  }
  return {
    min: [0, 1, 2].map((axis) => Math.min(...points.map((point) => point[axis]))) as [number, number, number],
    max: [0, 1, 2].map((axis) => Math.max(...points.map((point) => point[axis]))) as [number, number, number],
  }
}

function vector3(value: unknown, fallback: [number, number, number]): [number, number, number] {
  if (!Array.isArray(value)) return fallback
  return [
    Number(value[0] ?? fallback[0]),
    Number(value[1] ?? fallback[1]),
    Number(value[2] ?? fallback[2]),
  ]
}

export function boresightAzimuthDeg(config: RadarDraftConfig): number {
  const dx = config.look_at_m[0] - config.center_m[0]
  const dy = config.look_at_m[1] - config.center_m[1]
  return (Math.atan2(dy, dx) * 180) / Math.PI
}

export function boresightElevationDeg(config: RadarDraftConfig): number {
  const dx = config.look_at_m[0] - config.center_m[0]
  const dy = config.look_at_m[1] - config.center_m[1]
  const dz = config.look_at_m[2] - config.center_m[2]
  const horizontal = Math.hypot(dx, dy)
  return (Math.atan2(dz, horizontal) * 180) / Math.PI
}

export function withAzimuth(config: RadarDraftConfig, azDeg: number): RadarDraftConfig {
  return withLookAngles(config, azDeg, boresightElevationDeg(config))
}

export function withElevation(config: RadarDraftConfig, elDeg: number): RadarDraftConfig {
  return withLookAngles(config, boresightAzimuthDeg(config), elDeg)
}

export function withLookAngles(config: RadarDraftConfig, azDeg: number, elDeg: number): RadarDraftConfig {
  const range = Math.hypot(
    config.look_at_m[0] - config.center_m[0],
    config.look_at_m[1] - config.center_m[1],
    config.look_at_m[2] - config.center_m[2],
  ) || 30
  const el = (elDeg * Math.PI) / 180
  const az = (azDeg * Math.PI) / 180
  const horizontal = range * Math.cos(el)
  return {
    ...config,
    look_at_m: [
      config.center_m[0] + horizontal * Math.cos(az),
      config.center_m[1] + horizontal * Math.sin(az),
      config.center_m[2] + range * Math.sin(el),
    ],
  }
}

export function configNeedsSimulation(config: RadarDraftConfig, baseline: RadarDraftConfig | null): boolean {
  if (!baseline) return false
  return JSON.stringify(config) !== JSON.stringify(baseline)
}
