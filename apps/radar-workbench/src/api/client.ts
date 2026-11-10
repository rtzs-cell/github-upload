import type {
  AnalysisArtifactsResponse,
  DownloadCatalogResponse,
  CampaignSummary,
  BeamformingResponse,
  ExperimentResponse,
  ExperimentSummary,
  JobStatusResponse,
  InteractionsResponse,
  ImportedModelAsset,
  PathExportRequest,
  PathExportResponse,
  PathStatisticsResponse,
  RadarDraftConfig,
  RadarSimulationRequest,
  ResultBundleResponse,
  RunMetadata,
  RunSummary,
  SceneImportResult,
  SceneObject,
  ScenePresetCatalog,
  SpectrumMetadata,
  SimulationJobResponse,
  SionnaRuntime,
  TopPathsResponse,
} from './types'

const API_BASE = (import.meta.env.VITE_RADAR_API_BASE ?? '').replace(/\/$/, '')

function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path))
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`${response.status} ${response.statusText}: ${detail}`)
  }
  return response.json() as Promise<T>
}

export function figureUrl(runId: string, figureName: string): string {
  return apiUrl(`/api/results/${encodeURIComponent(runId)}/figures/${figureName}`)
}

export function resultBundleUrl(runId: string): string {
  return apiUrl(`/api/results/${encodeURIComponent(runId)}/result_bundle.zip`)
}

export function downloadUrl(path: string): string {
  return apiUrl(path)
}

export async function fetchExperiments(): Promise<ExperimentSummary[]> {
  const data = await request<{ experiments: ExperimentSummary[] }>('/api/experiments')
  return data.experiments
}

export async function fetchExperiment(experimentId: string): Promise<ExperimentResponse> {
  return request<ExperimentResponse>(`/api/experiments/${encodeURIComponent(experimentId)}`)
}

export async function deleteExperiment(experimentId: string): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>(`/api/experiments/${encodeURIComponent(experimentId)}`, {
    method: 'DELETE',
  })
}

export async function createExperiment(config: Record<string, unknown> = {}): Promise<ExperimentResponse> {
  return requestJson<ExperimentResponse>('/api/experiments', {
    method: 'POST',
    body: JSON.stringify({ config }),
  })
}

export async function fetchScenePresets(): Promise<ScenePresetCatalog> {
  return request<ScenePresetCatalog>('/api/experiments/presets')
}

export async function updateExperiment(experimentId: string, config: Record<string, any>): Promise<ExperimentResponse> {
  return requestJson<ExperimentResponse>(`/api/experiments/${encodeURIComponent(experimentId)}`, {
    method: 'PUT',
    body: JSON.stringify({ config }),
  })
}

export async function fetchExperimentOsm(
  experimentId: string,
  payload: { latitude: number; longitude: number; radius_km: number },
): Promise<SceneImportResult> {
  const path = '/api/experiments/' + encodeURIComponent(experimentId) + '/scene-fetch/osm'
  return requestJson<SceneImportResult>(path, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function fetchExperimentOsmBbox(
  experimentId: string,
  payload: { south: number; west: number; north: number; east: number },
): Promise<SceneImportResult> {
  const path = '/api/experiments/' + encodeURIComponent(experimentId) + '/scene-fetch/osm-bbox'
  return requestJson<SceneImportResult>(path, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function importExperimentScene(experimentId: string, file: File): Promise<SceneImportResult> {
  const path = '/api/experiments/' + encodeURIComponent(experimentId) + '/scene-imports?filename=' + encodeURIComponent(file.name)
  const response = await fetch(apiUrl(path), {
    method: 'POST',
    headers: { 'content-type': 'application/octet-stream' },
    body: file,
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(String(response.status) + ' ' + response.statusText + ': ' + detail)
  }
  return response.json() as Promise<SceneImportResult>
}

export async function uploadExperimentModel(experimentId: string, file: File): Promise<ImportedModelAsset> {
  const response = await fetch(apiUrl(`/api/experiments/${encodeURIComponent(experimentId)}/models?filename=${encodeURIComponent(file.name)}`), {
    method: 'POST',
    headers: { 'content-type': 'application/octet-stream' },
    body: file,
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`${response.status} ${response.statusText}: ${detail}`)
  }
  return response.json() as Promise<ImportedModelAsset>
}

export async function renameExperiment(experimentId: string, name: string): Promise<ExperimentResponse> {
  return requestJson<ExperimentResponse>(`/api/experiments/${encodeURIComponent(experimentId)}/name`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  })
}

export async function fetchCampaigns(): Promise<CampaignSummary[]> {
  const data = await request<{ campaigns: CampaignSummary[] }>('/api/campaigns')
  return data.campaigns
}

export async function fetchSionnaRuntime(): Promise<SionnaRuntime> {
  return request<SionnaRuntime>('/api/health/sionna_runtime')
}

export async function fetchRuns(campaignId: string): Promise<RunSummary[]> {
  const data = await request<{ campaign_id: string; runs: RunSummary[] }>(
    `/api/campaigns/${encodeURIComponent(campaignId)}/runs`,
  )
  return data.runs
}

export async function fetchRunMetadata(runId: string): Promise<RunMetadata> {
  return request<RunMetadata>(`/api/results/${encodeURIComponent(runId)}/metadata`)
}

export async function deleteResult(runId: string): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>(`/api/results/${encodeURIComponent(runId)}`, {
    method: 'DELETE',
  })
}

export async function renameResult(runId: string, name: string): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>(`/api/results/${encodeURIComponent(runId)}/name`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  })
}

export async function fetchSceneObjects(runId: string): Promise<SceneObject[]> {
  const data = await request<{ run_id: string; objects: SceneObject[] }>(
    `/api/results/${encodeURIComponent(runId)}/scene_objects`,
  )
  return data.objects
}

export async function fetchTopPaths(runId: string, topK = 500, inAnalysisGate = false): Promise<TopPathsResponse> {
  const params = new URLSearchParams({
    top_k: String(topK),
    in_fov: String(inAnalysisGate),
  })
  return request<TopPathsResponse>(`/api/results/${encodeURIComponent(runId)}/paths?${params.toString()}`)
}

export async function savePathExport(runId: string, payload: PathExportRequest): Promise<PathExportResponse> {
  return requestJson<PathExportResponse>(`/api/results/${encodeURIComponent(runId)}/path_exports`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function fetchInteractions(runId: string, topK = 2000, inAnalysisGate = false): Promise<InteractionsResponse> {
  const params = new URLSearchParams({
    top_k: String(topK),
    in_fov: String(inAnalysisGate),
  })
  return request<InteractionsResponse>(
    `/api/results/${encodeURIComponent(runId)}/interactions?${params.toString()}`,
  )
}

export async function fetchPathStatistics(runId: string): Promise<PathStatisticsResponse> {
  return request<PathStatisticsResponse>(`/api/results/${encodeURIComponent(runId)}/path_statistics`)
}

export async function fetchMpcAnalysis(runId: string): Promise<AnalysisArtifactsResponse> {
  return request<AnalysisArtifactsResponse>(`/api/results/${encodeURIComponent(runId)}/mpc_analysis`)
}

export async function fetchFmcwAnalysis(runId: string): Promise<AnalysisArtifactsResponse> {
  return request<AnalysisArtifactsResponse>(`/api/results/${encodeURIComponent(runId)}/fmcw`)
}

export async function fetchResultBundle(runId: string): Promise<ResultBundleResponse> {
  return request<ResultBundleResponse>(`/api/results/${encodeURIComponent(runId)}/result_bundle`)
}

export async function fetchDownloadCatalog(runId: string): Promise<DownloadCatalogResponse> {
  return request<DownloadCatalogResponse>(`/api/results/${encodeURIComponent(runId)}/downloads`)
}

export async function fetchBeamforming(
  runId: string,
  rxMode?: string,
  steeringAzimuthDeg?: number,
  steeringElevationDeg?: number,
): Promise<BeamformingResponse> {
  const params = new URLSearchParams()
  if (rxMode) params.set('rx_mode', rxMode)
  if (typeof steeringAzimuthDeg === 'number') params.set('steering_azimuth_deg', String(steeringAzimuthDeg))
  if (typeof steeringElevationDeg === 'number') params.set('steering_elevation_deg', String(steeringElevationDeg))
  return request<BeamformingResponse>(
    `/api/results/${encodeURIComponent(runId)}/beamforming${params.size ? `?${params.toString()}` : ''}`,
  )
}

export async function fetchSpectrum(kind: 'range_azimuth' | 'range_elevation', runId: string) {
  const metadata = await request<SpectrumMetadata>(
    `/api/results/${encodeURIComponent(runId)}/${kind}`,
  )
  const response = await fetch(apiUrl(metadata.array_url))
  if (!response.ok) {
    throw new Error(`Failed to load ${kind} array`)
  }
  const buffer = await response.arrayBuffer()
  return {
    metadata,
    values: new Float32Array(buffer),
  }
}

export async function submitSimulation(request: RadarSimulationRequest): Promise<SimulationJobResponse> {
  return requestJson<SimulationJobResponse>('/api/simulations', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export async function fetchJob(jobId: string): Promise<JobStatusResponse> {
  return requestJson<JobStatusResponse>(`/api/simulations/${encodeURIComponent(jobId)}`)
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    headers: {
      'content-type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`${response.status} ${response.statusText}: ${detail}`)
  }
  return response.json() as Promise<T>
}
