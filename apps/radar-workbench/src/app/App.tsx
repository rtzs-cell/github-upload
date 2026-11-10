import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import {
  Activity,
  BarChart3,
  BookOpen,
  Cpu,
  Crosshair,
  Database,
  Building2,
  Eye,
  Layers,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Pencil,
  RadioTower,
  RefreshCw,
  Route,
  SlidersHorizontal,
  Trash2,
  Waypoints,
} from 'lucide-react'
import {
  createExperiment,
  deleteExperiment,
  deleteResult,
  fetchBeamforming,
  fetchCampaigns,
  fetchExperiment,
  fetchExperiments,
  fetchDownloadCatalog,
  fetchFmcwAnalysis,
  fetchJob,
  fetchInteractions,
  fetchMpcAnalysis,
  fetchPathStatistics,
  fetchRunMetadata,
  fetchRuns,
  fetchSceneObjects,
  fetchScenePresets,
  fetchSpectrum,
  fetchSionnaRuntime,
  fetchTopPaths,
  figureUrl,
  savePathExport,
  renameExperiment,
  renameResult,
  submitSimulation,
  updateExperiment,
  uploadExperimentModel,
  importExperimentScene,
  fetchExperimentOsm,
  fetchExperimentOsmBbox,
} from '../api/client'
import type {
  CampaignSummary,
  BeamformingResponse,
  ExperimentResponse,
  ExperimentSummary,
  InteractionsResponse,
  RadarDraftConfig,
  JobStatusResponse,
  PathStatisticsResponse,
  RunMetadata,
  RunSummary,
  SceneObject,
  SpectrumMetadata,
  SionnaRuntime,
  TopPath,
  AnalysisArtifactsResponse,
  DownloadArtifact,
  ScenePresetCatalog,
} from '../api/types'
import { configNeedsSimulation, draftToExperimentConfig, runToDraftConfig } from './radarConfig'
import { experimentToDraftConfig, experimentToSceneObjects } from './radarConfig'
import { RadarEditor } from './RadarEditor'
import { RadarStatisticsPanel } from './RadarStatisticsPanel'
import { PathInspector } from './PathInspector'
import type { PathKindFilter } from './PathInspector'
import { Scene3D } from './Scene3D'
import { DownloadPanel } from './DownloadPanel'
import { knowledgeTopics } from './knowledgeTopics'
import type { KnowledgeTopic } from './knowledgeTopics'
import { cloneSceneConfig, SceneGeometryEditor } from './SceneGeometryEditor'

const KnowledgeCenter = lazy(() => import('./KnowledgeCenter').then((module) => ({ default: module.KnowledgeCenter })))

type SpectrumState = {
  metadata: SpectrumMetadata
  values: Float32Array
}

const defaultDraft = (run: RunSummary | null, metadata: RunMetadata | null): RadarDraftConfig =>
  runToDraftConfig(run, metadata)

const formatDb = (value: number) => `${(10 * Math.log10(Math.max(value, 1e-30))).toFixed(1)} dB`

const materialLabels: Record<string, string> = {
  glass: '玻璃',
  brick: '砖墙',
  marble: '石材',
  wood: '木材',
  concrete: '混凝土',
}

const jobStatusLabels: Record<string, string> = {
  queued: '排队中',
  running: '运行中',
  complete: '已完成',
  failed: '失败',
}

const txModeLabels: Record<string, string> = {
  embedded_sionna_pattern: '阵列方向图加权',
  embedded_sionna_custom_weights: '自定义复权重方向图',
  steering_vector: '导向矢量加权',
  custom_complex_weights: '自定义复权重',
  uniform: '等幅同相加权',
  disabled: '未启用',
}

const rxModeLabels: Record<string, string> = {
  steering_vector: '导向矢量波束形成',
  uniform: '等幅同相合成',
  custom_complex_weights: '自定义复权重',
  disabled: '未启用',
}

function campaignLabel(campaign: CampaignSummary) {
  if (campaign.campaign_id === 'c002_full_existing') return '内置示例结果（只读）'
  if (campaign.campaign_id === 'workbench_local') return '我的仿真结果（可删除）'
  if (campaign.created_at_utc) {
    const date = new Date(campaign.created_at_utc)
    if (!Number.isNaN(date.getTime())) {
      return `${date.toLocaleDateString('zh-CN')} ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
    }
  }
  const match = campaign.campaign_id.match(/^job_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})/)
  if (match) return `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]}`
  return campaign.display_name
}

function boresightLabel(value: string) {
  if (value === 'BposX') return '主视轴 X'
  if (value === 'BposY') return '主视轴 Y'
  return '指定观测方向'
}

function readableDate(value: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return `${date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })} ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
}

function experimentLabel(experiment: ExperimentSummary) {
  if (experiment.name === '两楼远距单站雷达路径统计实验') {
    return `建筑场景方案 · ${readableDate(experiment.created_at_utc)}`
  }
  return experiment.name.replace('草稿', '方案')
}

function runLabel(run: RunSummary) {
  const created = readableDate(run.created_at_utc)
  if (created) return `雷达仿真结果 · ${created}`
  return `示例测量 · ${boresightLabel(run.boresight_id)}`
}

function resultSubject(experimentName: string) {
  const subject = experimentName.split(' · ')[0].replace(/实验方案|方案/g, '').trim()
  return !subject || subject.startsWith('未命名') ? '未命名仿真结果' : subject
}

function readableObjectLabel(object: SceneObject) {
  return object.display_name ?? object.object_id.replace(/^mesh-/, '').replace(/[_-]+/g, ' ')
}

function sourcedRunLabel(run: RunSummary, experimentNames: Map<string, string>) {
  if (run.display_name) return run.display_name
  if (!run.source_experiment_id) return runLabel(run)
  const source = experimentNames.get(run.source_experiment_id)
  if (!source) return runLabel(run)
  const created = readableDate(run.created_at_utc)
  const subject = resultSubject(source)
  return created ? `${subject} · ${created}` : subject
}

function compactCount(value: number) {
  if (value >= 10_000) return `${(value / 10_000).toLocaleString('zh-CN', { maximumFractionDigits: 1 })}万`
  return value.toLocaleString('zh-CN')
}

function SpectrumCanvas({ spectrum, title }: { spectrum: SpectrumState | null; title: string }) {
  const [hover, setHover] = useState<{ range: string; angle: string; value: string } | null>(null)
  const rows = spectrum?.metadata.shape[0] ?? 0
  const cols = spectrum?.metadata.shape[1] ?? 0
  const canvasId = `canvas-${title.replace(/\s+/g, '-').toLowerCase()}`

  useEffect(() => {
    setHover(null)
  }, [spectrum])

  const paint = (canvas: HTMLCanvasElement | null) => {
    if (!canvas || !spectrum || !rows || !cols) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const img = ctx.createImageData(cols, rows)
    let max = 0
    for (const v of spectrum.values) max = Math.max(max, v)
    const floorDb = -60
    for (let i = 0; i < rows * cols; i += 1) {
      const db = 10 * Math.log10(Math.max(spectrum.values[i] / Math.max(max, 1e-30), 1e-30))
      const t = Math.max(0, Math.min(1, (db - floorDb) / -floorDb))
      const off = i * 4
      img.data[off] = Math.round(24 + 210 * t)
      img.data[off + 1] = Math.round(35 + 120 * Math.sin(t * Math.PI))
      img.data[off + 2] = Math.round(55 + 160 * (1 - t))
      img.data[off + 3] = 255
    }
    canvas.width = cols
    canvas.height = rows
    ctx.putImageData(img, 0, 0)
  }

  useEffect(() => {
    if (!spectrum) return
    paint(document.getElementById(canvasId) as HTMLCanvasElement | null)
  }, [canvasId, cols, rows, spectrum])

  if (!spectrum) {
    return <div className="empty-panel">谱图数据未加载</div>
  }

  return (
    <div className="spectrum-card">
      <div className="panel-heading">
        <Layers size={16} />
        <span>{title}</span>
      </div>
      <canvas
        id={canvasId}
        className="spectrum-canvas"
        onMouseMove={(event) => {
          const rect = (event.currentTarget as HTMLCanvasElement).getBoundingClientRect()
          const x = Math.floor(((event.clientX - rect.left) / rect.width) * cols)
          const y = Math.floor(((event.clientY - rect.top) / rect.height) * rows)
          if (x < 0 || y < 0 || x >= cols || y >= rows) return
          const idx = y * cols + x
          const value = spectrum.values[idx]
          const range = spectrum.metadata.range_edges_m[Math.min(y, spectrum.metadata.range_edges_m.length - 1)]
          const angle = spectrum.metadata.angle_edges_deg[Math.min(x, spectrum.metadata.angle_edges_deg.length - 1)]
          setHover({
            range: `${range.toFixed(2)} m`,
            angle: `${angle.toFixed(1)} 度`,
            value: `${formatDb(value)}`,
          })
        }}
        onMouseLeave={() => setHover(null)}
      />
      <div className="axis-row">
        <span>{spectrum.metadata.angle_edges_deg[0]?.toFixed(0)} 度</span>
        <span>距离 0-{(spectrum.metadata.range_edges_m.at(-1) ?? 0).toFixed(0)} m</span>
        <span>{spectrum.metadata.angle_edges_deg.at(-1)?.toFixed(0)} 度</span>
      </div>
      {hover && (
        <div className="hover-chip">
          {hover.range} | {hover.angle} | {hover.value}
        </div>
      )}
    </div>
  )
}

export function App() {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([])
  const [selectedExperimentId, setSelectedExperimentId] = useState<string | null>(null)
  const [selectedExperiment, setSelectedExperiment] = useState<ExperimentResponse | null>(null)
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([])
  const [selectedCampaignId, setSelectedCampaignId] = useState('workbench_local')
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [metadata, setMetadata] = useState<RunMetadata | null>(null)
  const [objects, setObjects] = useState<SceneObject[]>([])
  const [paths, setPaths] = useState<TopPath[]>([])
  const [interactions, setInteractions] = useState<InteractionsResponse | null>(null)
  const [pathStatistics, setPathStatistics] = useState<PathStatisticsResponse | null>(null)
  const [mpcAnalysis, setMpcAnalysis] = useState<AnalysisArtifactsResponse | null>(null)
  const [beamforming, setBeamforming] = useState<BeamformingResponse | null>(null)
  const [fmcwAnalysis, setFmcwAnalysis] = useState<AnalysisArtifactsResponse | null>(null)
  const [downloadArtifacts, setDownloadArtifacts] = useState<DownloadArtifact[]>([])
  const [rangeAzimuth, setRangeAzimuth] = useState<SpectrumState | null>(null)
  const [rangeElevation, setRangeElevation] = useState<SpectrumState | null>(null)
  const [draft, setDraft] = useState<RadarDraftConfig | null>(null)
  const [baseline, setBaseline] = useState<RadarDraftConfig | null>(null)
  const [draftUndoStack, setDraftUndoStack] = useState<RadarDraftConfig[]>([])
  const [draftRedoStack, setDraftRedoStack] = useState<RadarDraftConfig[]>([])
  const [job, setJob] = useState<JobStatusResponse | null>(null)
  const [loadedJobRunId, setLoadedJobRunId] = useState<string | null>(null)
  const [pathExportRoot, setPathExportRoot] = useState<string | null>(null)
  const [savingPaths, setSavingPaths] = useState(false)
  const [savingRadarConfig, setSavingRadarConfig] = useState(false)
  const [creatingExperiment, setCreatingExperiment] = useState(false)
  const [deletingItemId, setDeletingItemId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [runtime, setRuntime] = useState<SionnaRuntime | null>(null)
  const [sourceTab, setSourceTab] = useState<'experiments' | 'runs' | 'knowledge'>('runs')
  const [knowledgeTopic, setKnowledgeTopic] = useState<KnowledgeTopic>('start')
  const [inspectorTab, setInspectorTab] = useState<'parameters' | 'scene' | 'paths'>('parameters')
  const [leftPanelOpen, setLeftPanelOpen] = useState(true)
  const [rightPanelOpen, setRightPanelOpen] = useState(true)
  const [analysisTab, setAnalysisTab] = useState<'overview' | 'radar' | 'mpc' | 'beamforming' | 'spectra'>('overview')
  const [selectedPathId, setSelectedPathId] = useState<number | null>(null)
  const [pathKindFilter, setPathKindFilter] = useState<PathKindFilter>('all')
  const [gateOnly, setGateOnly] = useState(false)
  const [scenePresets, setScenePresets] = useState<ScenePresetCatalog>({ materials: {}, scenes: [] })
  const [selectedScenePreset, setSelectedScenePreset] = useState('empty')
  const [savingScene, setSavingScene] = useState(false)
  const [renameTarget, setRenameTarget] = useState<{ kind: 'experiment' | 'result'; id: string; name: string } | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [leftPanelWidth, setLeftPanelWidth] = useState(() => Math.max(260, Number(localStorage.getItem('radar-left-width')) || 280))
  const [rightPanelWidth, setRightPanelWidth] = useState(() => Number(localStorage.getItem('radar-right-width')) || 350)
  const [sceneHeight, setSceneHeight] = useState(() => Number(localStorage.getItem('radar-scene-height')) || 520)
  const [sceneEditConfig, setSceneEditConfig] = useState<Record<string, any> | null>(null)
  const [selectedSceneObjectId, setSelectedSceneObjectId] = useState<string | null>(null)
  const [sceneUndoStack, setSceneUndoStack] = useState<Record<string, any>[]>([])
  const [sceneRedoStack, setSceneRedoStack] = useState<Record<string, any>[]>([])

  useEffect(() => {
    if (!notice) return undefined
    const timer = window.setTimeout(() => setNotice(null), 4000)
    return () => window.clearTimeout(timer)
  }, [notice])

  const selectedRun = useMemo(
    () => runs.find((run) => run.run_id === selectedRunId) ?? null,
    [runs, selectedRunId],
  )
  const visibleExperiments = useMemo(
    () => experiments.filter((experiment) => {
      const name = experiment.name.toLowerCase()
      return !name.startsWith('pytest') && !name.startsWith('tiny')
    }),
    [experiments],
  )
  const resultCampaigns = useMemo(
    () => campaigns.filter((campaign) => ['c002_full_existing', 'workbench_local'].includes(campaign.campaign_id)),
    [campaigns],
  )
  const selectedCampaign = useMemo(
    () => resultCampaigns.find((campaign) => campaign.campaign_id === selectedCampaignId) ?? null,
    [resultCampaigns, selectedCampaignId],
  )
  const totalResultCount = useMemo(
    () => resultCampaigns.find((campaign) => campaign.campaign_id === 'workbench_local')?.run_count ?? 0,
    [resultCampaigns],
  )
  const filteredPaths = useMemo(
    () => paths.filter((path) => (pathKindFilter === 'all' || path.kind === pathKindFilter) && (!gateOnly || path.in_fov)),
    [gateOnly, pathKindFilter, paths],
  )
  const selectedPath = useMemo(
    () => paths.find((path) => path.path_id === selectedPathId) ?? null,
    [paths, selectedPathId],
  )
  useEffect(() => {
    if (selectedSceneObjectId && !objects.some((item) => item.object_id === selectedSceneObjectId)) {
      setSelectedSceneObjectId(null)
    }
  }, [objects, selectedSceneObjectId])
  const scenePaths = useMemo(() => selectedPath ? [selectedPath] : [], [selectedPath])
  const experimentNames = useMemo(
    () => new Map(experiments.map((experiment) => [experiment.experiment_id, experimentLabel(experiment)])),
    [experiments],
  )

  const selectPath = (pathId: number) => {
    setSelectedPathId(pathId)
    setInspectorTab('paths')
    setRightPanelOpen(true)
  }

  const commitSceneEdit = (next: Record<string, any>) => {
    const sceneSourceChanged = Boolean(
      next.scene?.source?.type
      && JSON.stringify(sceneEditConfig?.scene?.source ?? null) !== JSON.stringify(next.scene.source),
    )
    if (sceneEditConfig && JSON.stringify(sceneEditConfig.scene) !== JSON.stringify(next.scene)) {
      setSceneUndoStack((items) => [...items, cloneSceneConfig(sceneEditConfig)].slice(-50))
      setSceneRedoStack([])
    }
    setSceneEditConfig(next)
    setObjects(experimentToSceneObjects(next))
    if (sceneSourceChanged && Array.isArray(next.radar?.look_at_m)) {
      setDraft((current) => current ? { ...current, look_at_m: next.radar.look_at_m } : current)
    }
  }

  const undoSceneEdit = () => {
    const previous = sceneUndoStack.at(-1)
    if (!previous || !sceneEditConfig) return
    setSceneUndoStack((items) => items.slice(0, -1))
    setSceneRedoStack((items) => [cloneSceneConfig(sceneEditConfig), ...items].slice(0, 50))
    setSceneEditConfig(cloneSceneConfig(previous))
    setObjects(experimentToSceneObjects(previous))
  }

  const redoSceneEdit = () => {
    const next = sceneRedoStack[0]
    if (!next || !sceneEditConfig) return
    setSceneRedoStack((items) => items.slice(1))
    setSceneUndoStack((items) => [...items, cloneSceneConfig(sceneEditConfig)].slice(-50))
    setSceneEditConfig(cloneSceneConfig(next))
    setObjects(experimentToSceneObjects(next))
  }

  const clearDraftHistory = () => {
    setDraftUndoStack([])
    setDraftRedoStack([])
  }

  const cloneDraftConfig = (config: RadarDraftConfig): RadarDraftConfig => JSON.parse(JSON.stringify(config)) as RadarDraftConfig

  const commitDraftEdit = (next: RadarDraftConfig) => {
    if (draft && JSON.stringify(draft) !== JSON.stringify(next)) {
      setDraftUndoStack((items) => [...items, cloneDraftConfig(draft)].slice(-50))
      setDraftRedoStack([])
    }
    setDraft(next)
  }

  const undoDraftEdit = () => {
    const previous = draftUndoStack.at(-1)
    if (!previous || !draft) return
    setDraftUndoStack((items) => items.slice(0, -1))
    setDraftRedoStack((items) => [cloneDraftConfig(draft), ...items].slice(0, 50))
    setDraft(cloneDraftConfig(previous))
  }

  const redoDraftEdit = () => {
    const next = draftRedoStack[0]
    if (!next || !draft) return
    setDraftRedoStack((items) => items.slice(1))
    setDraftUndoStack((items) => [...items, cloneDraftConfig(draft)].slice(-50))
    setDraft(cloneDraftConfig(next))
  }

  const loadCampaigns = () =>
    fetchCampaigns()
      .then((items) => {
        setCampaigns(items)
        return items
      })
      .catch((err) => {
            setError(err.message)
        return []
      })

  const loadExperiments = () =>
    fetchExperiments()
      .then((items) => {
        setExperiments(items)
        return items
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err))
        return []
      })

  useEffect(() => {
    fetchSionnaRuntime()
      .then(setRuntime)
      .catch(() => setRuntime(null))
    fetchScenePresets().then((items) => {
      setScenePresets(items)
      if (items.scenes.length && !items.scenes.some((item) => item.id === selectedScenePreset)) setSelectedScenePreset(items.scenes[0].id)
    }).catch((err) => setError(err instanceof Error ? err.message : String(err)))
    loadExperiments()
    loadCampaigns().then((items) => {
      if (!items.find((item) => item.campaign_id === selectedCampaignId) && items[0]) {
        setSelectedCampaignId(items[0].campaign_id)
      }
    })
  }, [])

  useEffect(() => {
    if (!selectedCampaignId) return
    let cancelled = false
    setRuns([])
    setSelectedRunId(null)
    fetchRuns(selectedCampaignId)
      .then((items) => {
        if (cancelled) return
        setRuns(items)
        setSelectedRunId((current) => items.some((item) => item.run_id === current) ? current : items[0]?.run_id ?? null)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => { cancelled = true }
  }, [selectedCampaignId])

  useEffect(() => {
    if (!selectedRunId) return
    let cancelled = false
    const runId = selectedRunId
    setSelectedExperimentId(null)
    setSelectedExperiment(null)
    setPathExportRoot(null)
    setPathStatistics(null)
    setMpcAnalysis(null)
    setBeamforming(null)
    setFmcwAnalysis(null)
    setDownloadArtifacts([])
    setSelectedPathId(null)
    setRangeAzimuth(null)
    setRangeElevation(null)
    setMetadata(null)
    setObjects([])
    setSceneEditConfig(null)
    setSelectedSceneObjectId(null)
    setSceneUndoStack([])
    setSceneRedoStack([])
    setPaths([])
    setInteractions(null)
    setDraft(null)
    setBaseline(null)
    clearDraftHistory()
    setLoading(true)
    Promise.all([
      fetchRunMetadata(selectedRunId),
      fetchSceneObjects(selectedRunId),
      fetchTopPaths(selectedRunId, 1200, false),
      fetchInteractions(selectedRunId, 20000, false),
    ])
      .then(([meta, sceneObjects, topPaths, firstInteractions]) => {
        if (cancelled) return
        setMetadata(meta)
        setObjects(sceneObjects)
        setPaths(topPaths.paths)
        setInteractions(firstInteractions)
        setBeamforming(null)
        const nextDraft = defaultDraft(selectedRun, meta)
        setDraft(nextDraft)
        setBaseline(nextDraft)
        clearDraftHistory()
        setLoading(false)

        Promise.all([
          fetchPathStatistics(runId),
          fetchMpcAnalysis(runId),
          fetchSpectrum('range_azimuth', runId),
          fetchSpectrum('range_elevation', runId),
        ])
          .then(([stats, mpc, az, el]) => {
            if (cancelled) return
            setPathStatistics(stats)
            setMpcAnalysis(mpc)
            setRangeAzimuth(az)
            setRangeElevation(el)
            fetchDownloadCatalog(runId).then((downloads) => {
              if (!cancelled) setDownloadArtifacts(downloads.artifacts)
            })
          })
          .catch((err) => {
            if (!cancelled) setError(`部分分析结果加载失败：${err instanceof Error ? err.message : String(err)}`)
          })

      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedRunId])

  useEffect(() => {
    if (analysisTab !== 'radar' || !selectedRunId || fmcwAnalysis) return
    let cancelled = false
    fetchFmcwAnalysis(selectedRunId)
      .then((response) => {
        if (!cancelled) {
          setFmcwAnalysis(response)
          fetchDownloadCatalog(selectedRunId).then((downloads) => setDownloadArtifacts(downloads.artifacts))
        }
      })
      .catch((err) => {
        if (!cancelled) setError(`FMCW 结果加载失败：${err instanceof Error ? err.message : String(err)}`)
      })
    return () => { cancelled = true }
  }, [analysisTab, selectedRunId, fmcwAnalysis])

  useEffect(() => {
    if (analysisTab !== 'beamforming' || !selectedRunId || beamforming) return
    let cancelled = false
    fetchBeamforming(selectedRunId)
      .then((response) => {
        if (!cancelled) {
          setBeamforming(response)
          fetchDownloadCatalog(selectedRunId).then((downloads) => setDownloadArtifacts(downloads.artifacts))
        }
      })
      .catch((err) => {
        if (!cancelled) setError(`波束结果加载失败：${err instanceof Error ? err.message : String(err)}`)
      })
    return () => { cancelled = true }
  }, [analysisTab, selectedRunId, beamforming])

  useEffect(() => {
    if (!selectedExperimentId) return
    setLoading(true)
    fetchExperiment(selectedExperimentId)
      .then((response) => {
        const nextDraft = experimentToDraftConfig(response.config)
        setSelectedExperiment(response)
        setSelectedRunId(null)
        setMetadata(null)
        setPaths([])
        setInteractions(null)
        setPathStatistics(null)
        setMpcAnalysis(null)
        setBeamforming(null)
        setFmcwAnalysis(null)
        setSelectedPathId(null)
        setRangeAzimuth(null)
        setRangeElevation(null)
        setObjects(experimentToSceneObjects(response.config))
        setSceneEditConfig(cloneSceneConfig(response.config))
        setSelectedSceneObjectId(null)
        setSceneUndoStack([])
        setSceneRedoStack([])
        setDraft(nextDraft)
        setBaseline(nextDraft)
        clearDraftHistory()
        setPathExportRoot(null)
        setError(null)
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [selectedExperimentId])

  useEffect(() => {
    if (!job || job.status !== 'running' && job.status !== 'queued') return
    let cancelled = false
    const timer = window.setInterval(() => {
      fetchJob(job.job_id)
        .then((next) => {
          if (cancelled) return
          setJob(next)
          if (next.status === 'complete') {
            setError(null)
          } else if (next.status === 'failed') {
            setError(next.error ?? '仿真任务执行失败。')
          }
        })
        .catch((err) => {
          if (!cancelled) setError(err instanceof Error ? err.message : String(err))
        })
    }, 1500)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [job])

  useEffect(() => {
    const completed = job?.progress.completed_tasks ?? 0
    if (!completed) return
    loadCampaigns()
    if (selectedCampaignId === 'workbench_local') {
      fetchRuns('workbench_local').then((items) => {
        setRuns(items)
        setSelectedRunId((current) => current && items.some((item) => item.run_id === current) ? current : items[0]?.run_id ?? null)
      }).catch((err) => setError(err instanceof Error ? err.message : String(err)))
    }
  }, [job?.progress.completed_tasks])

  useEffect(() => {
    const result = job?.result as { campaign_id?: string; run_id?: string } | null
    if (!job || job.status !== 'complete' || !result?.campaign_id || !result?.run_id) return
    if (loadedJobRunId === result.run_id) return
    setLoadedJobRunId(result.run_id)
    setSourceTab('runs')
    loadCampaigns().then(() => {
      setSelectedCampaignId('workbench_local')
      setSelectedRunId(result.run_id!)
      setNotice('仿真完成，结果已加入结果库。')
    })
  }, [job, loadedJobRunId])

  const needsSimulation = draft ? configNeedsSimulation(draft, baseline) : false
  const jobActive = job?.status === 'running' || job?.status === 'queued'
  const statusText = jobActive
    ? job.status === 'running'
      ? `任务运行中 · ${job.progress.completed_tasks}/${job.progress.total_tasks} 可下载`
      : `任务${jobStatusLabels[job.status] ?? job.status}`
    : loading
      ? '正在加载'
      : needsSimulation
        ? '参数已修改'
        : selectedExperiment
          ? '实验方案'
        : selectedCampaignId === 'c002_full_existing'
          ? '只读基准结果'
          : '仿真结果'
  const contextText = selectedExperiment
    ? `方案 · ${experimentLabel(selectedExperiment.manifest)}`
    : selectedRun
      ? `结果 · ${sourcedRunLabel(selectedRun, experimentNames)}`
      : '未选择工作项'

  const shellClass = [
    'app-shell',
    sourceTab === 'knowledge' ? 'knowledge-mode' : '',
    leftPanelOpen ? '' : 'left-collapsed',
    rightPanelOpen ? '' : 'right-collapsed',
  ].filter(Boolean).join(' ')

  const beginResize = (kind: 'left' | 'right' | 'scene', startValue: number) => (event: React.PointerEvent) => {
    if (window.innerWidth <= 1180) return
    event.preventDefault()
    const startX = event.clientX
    const startY = event.clientY
    const move = (moveEvent: PointerEvent) => {
      if (kind === 'left') setLeftPanelWidth(Math.min(420, Math.max(260, startValue + moveEvent.clientX - startX)))
      if (kind === 'right') setRightPanelWidth(Math.min(560, Math.max(300, startValue - moveEvent.clientX + startX)))
      if (kind === 'scene') setSceneHeight(Math.min(800, Math.max(320, startValue + moveEvent.clientY - startY)))
    }
    const end = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', end)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', end)
  }

  useEffect(() => { localStorage.setItem('radar-left-width', String(leftPanelWidth)) }, [leftPanelWidth])
  useEffect(() => { localStorage.setItem('radar-right-width', String(rightPanelWidth)) }, [rightPanelWidth])
  useEffect(() => { localStorage.setItem('radar-scene-height', String(sceneHeight)) }, [sceneHeight])

  return (
    <div className={shellClass} style={{ '--left-panel-width': `${leftPanelWidth}px`, '--right-panel-width': `${rightPanelWidth}px` } as React.CSSProperties}>
      <header className="topbar">
        <button
          type="button"
          className="icon-button panel-toggle"
          onClick={() => setLeftPanelOpen((open) => !open)}
          title={leftPanelOpen ? '收起数据导航' : '展开数据导航'}
        >
          {leftPanelOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
        </button>
        <div className="brand">
          <RadioTower size={22} />
          <div>
            <strong>城市雷达感知仿真平台</strong>
            <span>{contextText}</span>
          </div>
        </div>
        <button type="button" className="icon-button" onClick={() => selectedRunId && window.location.reload()} title="重新加载">
          <RefreshCw size={17} />
        </button>
        <div
          className={`runtime-badge ${runtime?.available ? 'available' : 'unavailable'}`}
          title={runtime?.available ? 'Sionna RT 路径求解器可用' : 'Sionna RT 路径求解器不可用'}
        >
          <Cpu size={14} />
          <span>Sionna RT {runtime?.versions?.sionna_rt ?? '检查中'}</span>
        </div>
        <div className="status-pill">{statusText}</div>
        <button
          type="button"
          className="icon-button panel-toggle"
          onClick={() => setRightPanelOpen((open) => !open)}
          title={rightPanelOpen ? '收起参数检查器' : '展开参数检查器'}
        >
          {rightPanelOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
        </button>
      </header>

      <aside className={`left-panel ${leftPanelOpen ? '' : 'panel-hidden'}`}>
        <div className="panel-heading">
          <Database size={16} />
          <span>工作区</span>
        </div>
        <div className="segmented-tabs source-tabs" role="tablist" aria-label="数据源类型">
          <button type="button" className={sourceTab === 'experiments' ? 'active' : ''} onClick={() => setSourceTab('experiments')}>
            实验方案 <span>{visibleExperiments.length}</span>
          </button>
          <button type="button" className={sourceTab === 'runs' ? 'active' : ''} onClick={() => setSourceTab('runs')}>
            仿真结果 <span>{totalResultCount}</span>
          </button>
          <button type="button" className={sourceTab === 'knowledge' ? 'active' : ''} onClick={() => setSourceTab('knowledge')}>
            术语教程
          </button>
        </div>
        {sourceTab === 'knowledge' ? (
          <nav className="knowledge-nav" aria-label="术语教程目录">
            {knowledgeTopics.map((item) => <button type="button" key={item.id} className={knowledgeTopic === item.id ? 'active' : ''} onClick={() => setKnowledgeTopic(item.id)}><BookOpen size={14} /><span>{item.label}</span></button>)}
          </nav>
        ) : sourceTab === 'experiments' ? (
          <>
            <label className="field scene-preset-picker"><span>场景起点</span><select value={selectedScenePreset} onChange={(event) => setSelectedScenePreset(event.target.value)}>
              {scenePresets.scenes.map((preset) => <option key={preset.id} value={preset.id}>{preset.label} · {preset.description}</option>)}
            </select></label>
            <button
              type="button"
              className="primary-action full-width"
              disabled={creatingExperiment}
              onClick={() => {
                setCreatingExperiment(true)
                createExperiment({ scene_preset: selectedScenePreset })
                  .then((resp) => {
                    setNotice('实验方案已创建。')
                    setSelectedExperimentId(resp.manifest.experiment_id)
                    return loadExperiments()
                  })
                  .catch((err) => setError(err instanceof Error ? err.message : String(err)))
                  .finally(() => setCreatingExperiment(false))
              }}
            >
              <Plus size={16} />
              {creatingExperiment ? '正在创建' : '新建实验方案'}
            </button>
            <div className="experiment-list navigator-list">
              {visibleExperiments.map((experiment) => (
                <div className="history-row" key={experiment.experiment_id}>
                  <button
                    type="button"
                    className={`experiment-row ${experiment.experiment_id === selectedExperimentId ? 'selected' : ''}`}
                    onClick={() => setSelectedExperimentId(experiment.experiment_id)}
                    title={experimentLabel(experiment)}
                  >
                    <strong>{experimentLabel(experiment)}</strong>
                    <span>{readableDate(experiment.created_at_utc)}</span>
                  </button>
                  <button type="button" className="history-edit" title="修改方案名称" onClick={() => { setRenameTarget({ kind: 'experiment', id: experiment.experiment_id, name: experimentLabel(experiment) }); setRenameValue(experimentLabel(experiment)) }}><Pencil size={14} /></button>
                  <button
                    type="button"
                    className="history-delete"
                    disabled={deletingItemId === experiment.experiment_id}
                    title="删除实验方案"
                    onClick={() => {
                      if (!window.confirm(`删除“${experimentLabel(experiment)}”？\n\n只删除实验方案，已经生成的仿真结果会保留。`)) return
                      setDeletingItemId(experiment.experiment_id)
                      deleteExperiment(experiment.experiment_id)
                        .then(() => {
                          if (selectedExperimentId === experiment.experiment_id) {
                            setSelectedExperimentId(null)
                            setSelectedExperiment(null)
                            setDraft(null)
                            setBaseline(null)
                            clearDraftHistory()
                          }
                          setNotice(`已删除实验方案“${experimentLabel(experiment)}”。`)
                          return loadExperiments()
                        })
                        .catch((err) => setError(err instanceof Error ? err.message : String(err)))
                        .finally(() => setDeletingItemId(null))
                    }}
                  ><Trash2 size={15} /></button>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="result-browser">
            <label className="field result-set-picker">
              <span>结果库</span>
              <select value={selectedCampaignId} onChange={(event) => setSelectedCampaignId(event.target.value)}>
                {resultCampaigns.map((campaign) => (
                  <option key={campaign.campaign_id} value={campaign.campaign_id}>
                    {campaignLabel(campaign)} · {campaign.run_count} 条
                  </option>
                ))}
              </select>
            </label>
            {selectedCampaign && (
              <div className="result-set-summary">
                <strong>{selectedCampaign.readonly ? '只读基准数据' : '本地仿真结果'}</strong>
                <span>{selectedCampaign.readonly ? '示例数据，不提供删除' : '由当前工作台生成，可逐条删除'}</span>
              </div>
            )}
            <div className="navigator-section-heading">
              <span>结果列表</span>
              <em>{runs.length}</em>
            </div>
            <div className="run-list navigator-list">
              {runs.map((run) => (
                <div className="history-row" key={run.run_id}>
                  <button
                    type="button"
                    className={`run-row ${run.run_id === selectedRunId ? 'selected' : ''}`}
                    onClick={() => setSelectedRunId(run.run_id)}
                    title={sourcedRunLabel(run, experimentNames)}
                  >
                    <strong>{sourcedRunLabel(run, experimentNames)}</strong>
                    <em>{(run.fov_energy_fraction * 100).toFixed(2)}%</em>
                    <span>位置 ({run.x_m.toFixed(1)}, {run.y_m.toFixed(1)}, {run.z_m.toFixed(1)}) m · {compactCount(run.samples_per_src)} 条射线</span>
                    <small>{boresightLabel(run.boresight_id)}{run.source_experiment_id ? ` · 来源：${experimentNames.get(run.source_experiment_id) ?? '来源方案已删除'}` : ' · 示例测点'}</small>
                  </button>
                  {run.campaign_id !== 'c002_full_existing' && (
                    <><button type="button" className="history-edit" title="修改结果名称" onClick={() => { const name = sourcedRunLabel(run, experimentNames); setRenameTarget({ kind: 'result', id: run.run_id, name }); setRenameValue(name) }}><Pencil size={14} /></button><button
                      type="button"
                      className="history-delete"
                      disabled={deletingItemId === run.run_id}
                      title="删除仿真结果"
                      onClick={() => {
                        if (!window.confirm(`删除“${runLabel(run)}”？\n\n将删除该结果、分析缓存和下载包；来源方案不会删除。此操作不能撤销。`)) return
                        setDeletingItemId(run.run_id)
                        deleteResult(run.run_id)
                          .then(() => {
                            if (selectedRunId === run.run_id) setSelectedRunId(null)
                            setNotice(`已删除仿真结果“${runLabel(run)}”。`)
                            return Promise.all([loadCampaigns(), fetchRuns(selectedCampaignId)])
                          })
                          .then(([, items]) => {
                            setRuns(items)
                            setSelectedRunId((current) => items.some((item) => item.run_id === current) ? current : items[0]?.run_id ?? null)
                          })
                          .catch((err) => setError(err instanceof Error ? err.message : String(err)))
                          .finally(() => setDeletingItemId(null))
                      }}
                    ><Trash2 size={15} /></button></>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </aside>

      {leftPanelOpen && sourceTab !== 'knowledge' && <div className="panel-resizer left-resizer" onPointerDown={beginResize('left', leftPanelWidth)} title="拖动调整工作区宽度" />}
      {rightPanelOpen && sourceTab !== 'knowledge' && <div className="panel-resizer right-resizer" onPointerDown={beginResize('right', rightPanelWidth)} title="拖动调整检查器宽度" />}

      <main className="center-panel">
        {sourceTab === 'knowledge' ? <Suspense fallback={<div className="empty-panel">正在加载教程</div>}><KnowledgeCenter topic={knowledgeTopic} /></Suspense> : <>
        {error && <div className="error-banner">{error}</div>}
        {notice && <div className="notice-banner">{notice}</div>}
        {draft && (<div className="scene-resize-wrap" style={{ '--scene-height': `${sceneHeight}px` } as React.CSSProperties}>
          <Scene3D
            objects={objects}
            paths={scenePaths}
            config={draft}
            viewKey={selectedRunId ?? (selectedExperimentId ?? draft.scene_id) + ':' + (sceneEditConfig?.scene?.source?.source_path ?? sceneEditConfig?.scene?.kind ?? '')}
            selectedPathId={selectedPathId}
            onPathSelect={selectPath}
            selectedObjectId={selectedSceneObjectId}
            editableObjects={Boolean(selectedExperiment && sceneEditConfig)}
            onObjectSelect={(objectId) => {
              setSelectedSceneObjectId(objectId)
              if (objectId) {
                setInspectorTab(selectedExperiment ? 'scene' : 'paths')
                setRightPanelOpen(true)
              }
            }}
            onObjectTransform={(objectId, centerM, sizeM, rotationDeg) => {
              if (!sceneEditConfig) return
              const next = cloneSceneConfig(sceneEditConfig)
              const building = next.scene?.buildings?.find((item: any) => item.id === objectId)
              if (!building) return
              building.center_m = centerM
              building.size_m = sizeM
              building.rotation_deg = rotationDeg
              commitSceneEdit(next)
            }}
            onConfigChange={(next) => {
              commitDraftEdit(next)
              setError(null)
            }}
          />
          <div className="scene-height-resizer" onPointerDown={beginResize('scene', sceneHeight)} title="拖动调整三维场景高度" />
        </div>)}
        <div className="scene-caption">
          {selectedPath ? `当前路径 #${selectedPath.path_id} / 已载入 ${paths.length.toLocaleString()}` : `未选路径 / 已载入 ${paths.length.toLocaleString()}`}
        </div>
        <section className="result-workspace">
          <div className="segmented-tabs analysis-tabs" role="tablist" aria-label="雷达结果视图">
            <button type="button" className={analysisTab === 'overview' ? 'active' : ''} onClick={() => setAnalysisTab('overview')}><Activity size={14} />概览</button>
            <button type="button" className={analysisTab === 'radar' ? 'active' : ''} onClick={() => setAnalysisTab('radar')}><RadioTower size={14} />雷达回波</button>
            <button type="button" className={analysisTab === 'mpc' ? 'active' : ''} onClick={() => setAnalysisTab('mpc')}><Waypoints size={14} />MPC</button>
            <button type="button" className={analysisTab === 'beamforming' ? 'active' : ''} onClick={() => setAnalysisTab('beamforming')}><Crosshair size={14} />波束成形</button>
            <button type="button" className={analysisTab === 'spectra' ? 'active' : ''} onClick={() => setAnalysisTab('spectra')}><BarChart3 size={14} />距离角谱</button>
          </div>

          {analysisTab === 'overview' && (
            <>
              <RadarStatisticsPanel selectedRun={selectedRun} metadata={metadata} paths={paths} objects={objects} rangeAzimuth={rangeAzimuth} runs={runs} />
              {selectedRun && pathStatistics && (
                <>
                <div className="overview-methods">
                  <div className="statistics-definition-table">
                    <div><strong>有效传播路径</strong><span>时延有限且大于 0 的 PathSolver 输出</span><em>{Number(pathStatistics.summary.valid_path_count ?? 0).toLocaleString()}</em></div>
                    <div><strong>分析范围内路径</strong><span>同时满足到达角方位、到达角俯仰和距离范围</span><em>{Number(pathStatistics.summary.analysis_gate_path_count ?? 0).toLocaleString()}</em></div>
                    <div><strong>初始射线采样</strong><span>{String(metadata?.metadata?.initial_ray_sampling?.mode ?? 'full_sphere') === 'analysis_sector' ? '候选方向限制在分析方位与俯仰扇区' : '候选方向覆盖完整球面'}</span><em>{String(metadata?.metadata?.initial_ray_sampling?.mode ?? 'full_sphere') === 'analysis_sector' ? `${Number(metadata?.metadata?.initial_ray_sampling?.solid_angle_sr ?? 0).toFixed(4)} sr` : '4π sr'}</em></div>
                    <div><strong>二阶交互路径</strong><span>与场景对象发生两次反射或散射交互</span><em>{Number(pathStatistics.summary.path_count_by_depth?.['2'] ?? 0).toLocaleString()}</em></div>
                    <div><strong>总路径能量</strong><span>当前观测中所有有效路径能量之和</span><em>{formatDb(Number(pathStatistics.summary.total_energy ?? 0))}</em></div>
                  </div>
                </div>
                <DownloadPanel artifacts={downloadArtifacts} />
                </>
              )}
            </>
          )}

          {analysisTab === 'mpc' && (
            <div className="result-tab-panel">
              {selectedRun && mpcAnalysis ? (
                <>
                  <div className="metrics-grid radar-metrics">
                    <div className="metric-tile"><span>投影路径</span><strong>{Number(mpcAnalysis.summary.mpc_panorama?.path_count ?? 0).toLocaleString()}</strong><em>第 0 个收发阵元对</em></div>
                    <div className="metric-tile"><span>全景分辨率</span><strong>{Number(mpcAnalysis.summary.mpc_panorama?.panorama_shape?.[1] ?? 0)} × {Number(mpcAnalysis.summary.mpc_panorama?.panorama_shape?.[0] ?? 0)}</strong><em>方位 × 天顶角</em></div>
                    <div className="metric-tile"><span>等效接收孔径</span><strong>{Number(mpcAnalysis.summary.mpc_panorama?.kernel?.rows ?? 0)} × {Number(mpcAnalysis.summary.mpc_panorama?.kernel?.cols ?? 0)}</strong><em>阵元间距 {Number(mpcAnalysis.summary.mpc_panorama?.kernel?.spacing_lambda ?? 0)}λ · 矩形阵列</em></div>
                    <div className="metric-tile"><span>显示动态范围</span><strong>{Number(mpcAnalysis.summary.mpc_panorama?.normalization?.dynamic_range_db ?? 0).toFixed(0)} dB</strong><em>P{Number(mpcAnalysis.summary.mpc_panorama?.normalization?.peak_percentile ?? 0)} 峰值</em></div>
                  </div>
                  <div className="mpc-panorama">
                    <div className="panel-heading"><Waypoints size={15} /><span>多径分量到达角全景（MPC AoA）</span></div>
                    <img src={figureUrl(selectedRun.run_id, 'mpc_panorama.png')} alt="MPC AoA 360度全景图" />
                    <code>x=(180°-φ)×3，y=θ×3；像素权重 |aₚ|；显示值 10log₁₀(核平滑后的幅值)</code>
                  </div>
                  <div className="mpc-view-grid">
                    {[['front', '前视 0°'], ['right', '右视 90°'], ['back', '后视 180°'], ['left', '左视 -90°']].map(([key, label]) => (
                      <figure key={key}><img src={figureUrl(selectedRun.run_id, `mpc_view_${key}.png`)} alt={`MPC ${label}`} /><figcaption>{label} · FOV 90°</figcaption></figure>
                    ))}
                  </div>
                  <div className="path-analysis-heading"><strong>传播路径补充分析</strong><span>以下是逐路径数据，不是 MPC 全景图本身</span></div>
                  <div className="mpc-layout">
                    <div className="mpc-figure"><img src={figureUrl(selectedRun.run_id, 'analysis_gate_mpc.png')} alt="传播路径距离角度分析" /></div>
                    <div className="gate-diagnostics">
                      <div className="diagnostic-row"><span>全部有效路径</span><strong>{Number(mpcAnalysis.summary.valid_path_count ?? 0).toLocaleString()}</strong></div>
                      <div className="diagnostic-row"><span>分析范围内路径</span><strong>{Number(mpcAnalysis.summary.analysis_gate_path_count ?? 0).toLocaleString()}</strong></div>
                      <div className="diagnostic-row"><span>分析范围内能量占比</span><strong>{(Number(mpcAnalysis.summary.analysis_gate_energy_fraction ?? 0) * 100).toFixed(3)}%</strong></div>
                    </div>
                  </div>
                  <div className="mpc-path-strip">
                    {paths.filter((path) => path.in_fov).slice(0, 12).map((path) => (
                      <button type="button" key={path.path_id} onClick={() => selectPath(path.path_id)}><strong>#{path.path_id}</strong><span>{path.range_m.toFixed(2)} m</span><em>{formatDb(path.energy)}</em></button>
                    ))}
                  </div>
                </>
              ) : <div className="empty-panel">{selectedRun ? 'MPC 全景正在生成或加载' : '实验方案尚未运行，没有 MPC 结果'}</div>}
            </div>
          )}

          {analysisTab === 'radar' && (
            <div className="result-tab-panel">
              {selectedRun && fmcwAnalysis ? (
                <>
                  <div className="metrics-grid radar-metrics">
                    <div className="metric-tile"><span>距离分辨率</span><strong>{Number(fmcwAnalysis.summary.range_resolution_m ?? 0).toFixed(3)} m</strong><em>{Number(fmcwAnalysis.summary.waveform?.bandwidth_hz ?? 0) / 1e9} GHz 带宽</em></div>
                    <div className="metric-tile"><span>速度分辨率</span><strong>{Number(fmcwAnalysis.summary.velocity_resolution_mps ?? 0).toFixed(3)} m/s</strong><em>{Number(fmcwAnalysis.summary.waveform?.num_chirps ?? 0)} chirps</em></div>
                    <div className="metric-tile"><span>回波合成功率覆盖率</span><strong>{(Number(fmcwAnalysis.summary.synthesized_path_power_fraction ?? 0) * 100).toFixed(2)}%</strong><em>{Number(fmcwAnalysis.summary.exact_time_domain_path_count ?? 0)} 条精确时域路径 + {Number(fmcwAnalysis.summary.fft_gridded_path_count ?? 0)} 条频域栅格路径</em></div>
                    <div className="metric-tile"><span>CA-CFAR 检测单元数</span><strong>{Number(fmcwAnalysis.summary.cfar?.detection_count ?? 0)}</strong><em>目标虚警概率 {Number(fmcwAnalysis.summary.cfar?.pfa ?? 0).toExponential(1)}</em></div>
                  </div>
                  <div className="analysis-figure inline-figure radar-response-figure">
                    <img src={figureUrl(selectedRun.run_id, 'fmcw_range_doppler.png')} alt="FMCW 距离多普勒响应与 CFAR 检测" />
                  </div>
                </>
              ) : <div className="empty-panel">{selectedRun ? '正在生成 FMCW 距离-多普勒结果' : '实验方案尚未运行，没有雷达回波结果'}</div>}
            </div>
          )}

          {analysisTab === 'beamforming' && draft && (
            <div className="result-tab-panel">
              {selectedRun && beamforming && (
                <>
                  <div className="metrics-grid radar-metrics beam-metrics">
                    <div className="metric-tile"><span>发射阵列加权</span><strong>{txModeLabels[String(beamforming.summary.tx_mode)] ?? '其他加权方式'}</strong><em>{Number(beamforming.summary.tx_aperture_element_count ?? 1)} 个阵元</em></div>
                    <div className="metric-tile"><span>接收波束形成</span><strong>{rxModeLabels[String(beamforming.summary.rx_mode)] ?? '其他合成方式'}</strong><em>{Number(beamforming.summary.rx_weight_count ?? 0)} 个复权重</em></div>
                    <div className="metric-tile"><span>相干合成功率</span><strong>{formatDb(Number(beamforming.summary.beamformed_power_total ?? 0))}</strong><em>所有有效路径</em></div>
                    <div className="metric-tile"><span>非相干功率</span><strong>{formatDb(Number(beamforming.summary.noncoherent_power_total ?? 0))}</strong><em>阵元功率直接求和</em></div>
                    <div className="metric-tile"><span>最强合成路径</span><strong>#{beamforming.summary.top_paths?.[0]?.path_id ?? '-'}</strong><em>{Number(beamforming.summary.top_paths?.[0]?.range_m ?? 0).toFixed(2)} m</em></div>
                  </div>
                  <div className="beam-result-grid">
                    <img src={figureUrl(selectedRun.run_id, 'tx_radiation_pattern.png')} alt="Tx 孔径相位与物理发射方向图" />
                    <img src={figureUrl(selectedRun.run_id, 'rx_steering_pattern.png')} alt="Rx 权重相位与阵列响应" />
                    <div className="beam-path-table">
                      <div className="panel-heading"><Route size={15} /><span>波束成形后最强路径</span></div>
                      {beamforming.summary.top_paths?.slice(0, 10).map((item: any) => (
                        <button type="button" key={item.path_id} onClick={() => selectPath(Number(item.path_id))}><span>#{item.path_id}</span><strong>{Number(item.range_m).toFixed(2)} m</strong><em>{Number(item.beamformed_power_db).toFixed(2)} dB</em></button>
                      ))}
                    </div>
                  </div>
                </>
              )}
              {selectedRun && !beamforming && <div className="empty-panel">正在加载波束形成结果</div>}
              {!selectedRun && <div className="empty-panel">实验方案尚未运行，没有波束结果</div>}
            </div>
          )}

          {analysisTab === 'spectra' && (
            <div className="result-tab-panel"><section className="figure-grid"><SpectrumCanvas spectrum={rangeAzimuth} title="距离-方位角谱" /><SpectrumCanvas spectrum={rangeElevation} title="距离-俯仰角谱" /></section></div>
          )}
        </section>
        </>}
      </main>

      <aside className={`right-panel ${rightPanelOpen && sourceTab !== 'knowledge' ? '' : 'panel-hidden'}`}>
        <div className="segmented-tabs inspector-tabs" role="tablist" aria-label="检查器视图">
          <button type="button" className={inspectorTab === 'parameters' ? 'active' : ''} onClick={() => setInspectorTab('parameters')}>
            <SlidersHorizontal size={14} />
            雷达参数
          </button>
          <button type="button" className={inspectorTab === 'scene' ? 'active' : ''} onClick={() => setInspectorTab('scene')} disabled={!selectedExperiment}>
            <Building2 size={14} />
            场景几何
          </button>
          <button type="button" className={inspectorTab === 'paths' ? 'active' : ''} onClick={() => setInspectorTab('paths')}>
            <Route size={14} />
            路径与对象
          </button>
        </div>
        {inspectorTab === 'parameters' && draft && (
          <RadarEditor
            config={draft}
            baseline={baseline}
            status={jobActive ? (job?.status as 'queued' | 'running') : needsSimulation ? 'draft_changed' : 'ready_to_run'}
            sourceLabel={selectedRun ? `结果 · ${sourcedRunLabel(selectedRun, experimentNames)}` : selectedExperiment ? `实验方案 · ${experimentLabel(selectedExperiment.manifest)}` : '新配置'}
            canUndo={draftUndoStack.length > 0}
            canRedo={draftRedoStack.length > 0}
            onChange={(next) => {
              commitDraftEdit(next)
              setError(null)
            }}
            onUndo={undoDraftEdit}
            onRedo={redoDraftEdit}
            onReset={() => {
              if (baseline) commitDraftEdit(cloneDraftConfig(baseline))
            }}
            onSaveConfig={selectedExperiment ? () => {
              if (!draft || !selectedExperiment) return
              setSavingRadarConfig(true)
              setError(null)
              const nextConfig = draftToExperimentConfig(sceneEditConfig ?? selectedExperiment.config, draft)
              updateExperiment(selectedExperiment.manifest.experiment_id, nextConfig)
                .then((response) => {
                  const nextDraft = experimentToDraftConfig(response.config)
                  setSelectedExperiment(response)
                  setSceneEditConfig(cloneSceneConfig(response.config))
                  setObjects(experimentToSceneObjects(response.config))
                  setDraft(nextDraft)
                  setBaseline(nextDraft)
                  clearDraftHistory()
                  setNotice('雷达参数已保存到实验方案，已有仿真结果保持不变。')
                  return loadExperiments()
                })
                .catch((err) => setError(err instanceof Error ? err.message : String(err)))
                .finally(() => setSavingRadarConfig(false))
            } : undefined}
            savingConfig={savingRadarConfig}
            onSavePaths={() => {
              if (!selectedRunId || !draft) return
              if (needsSimulation) {
                setError('雷达参数已修改，请先运行仿真，再保存对应的传播路径。')
                return
              }
              setSavingPaths(true)
              savePathExport(selectedRunId, {
                draft_config: draft,
                top_k: 1000,
                kind: 'all',
                in_fov: true,
                note: '路径数据与当前仿真参数对应，分析范围标记表示路径同时满足方位、俯仰和距离筛选条件。',
              })
                .then((resp) => {
                  setPathExportRoot(resp.root)
                  setNotice(`已保存 ${resp.path_count} 条传播路径。`)
                })
                .catch((err) => setError(err instanceof Error ? err.message : String(err)))
                .finally(() => setSavingPaths(false))
            }}
            savingPaths={savingPaths}
            onSubmit={() => {
              if (!draft || jobActive) return
              setLoading(true)
              setError(null)
              setLoadedJobRunId(null)
              const request = {
                scene_id: draft.scene_id,
                scene_geometry: selectedExperiment?.config.scene ?? null,
                source_experiment_id: selectedExperimentId || String((metadata?.config as any)?.workbench?.source_experiment_id ?? '') || null,
                display_name: selectedExperiment?.manifest.name
                  ? `${resultSubject(selectedExperiment.manifest.name)} · ${readableDate(new Date().toISOString())}`
                  : `雷达仿真结果 · ${readableDate(new Date().toISOString())}`,
                mode: 'single_pose' as const,
                radar: {
                  center_m: draft.center_m,
                  look_at_m: draft.look_at_m,
                  tx_rx_baseline_m: draft.tx_rx_baseline_m,
                  az_width_deg: draft.az_width_deg,
                  el_min_deg: draft.el_min_deg,
                  el_max_deg: draft.el_max_deg,
                  rmax_m: draft.rmax_m,
                  range_bin_m: 0.15,
                  angle_bin_deg: 2.0,
                },
                propagation: {
                  frequency_hz: draft.frequency_hz,
                  bandwidth_hz: draft.bandwidth_hz,
                },
                waveform: {
                  tx_power_dbm: draft.tx_power_dbm,
                  chirp_duration_s: draft.chirp_duration_us * 1e-6,
                  idle_time_s: draft.chirp_idle_time_us * 1e-6,
                  num_chirps: draft.num_chirps,
                  adc_samples: draft.adc_samples,
                },
                receiver: {
                  noise_figure_db: draft.noise_figure_db,
                  temperature_k: draft.receiver_temperature_k,
                },
                radar_processing: {
                  cfar_pfa: draft.cfar_pfa,
                  max_synthesis_paths: draft.max_synthesis_paths,
                },
                cir_noise: {
                  enabled: draft.cir_noise_enabled,
                  snr_db: draft.cir_noise_snr_db,
                  seed: draft.cir_noise_seed,
                },
                scattering: {
                  enabled: draft.scattering_enabled,
                  coefficient: draft.scattering_coefficient,
                  pattern: draft.scattering_pattern,
                  alpha_r: draft.alpha_r,
                  alpha_i: draft.alpha_i,
                  lambda_: draft.lambda_,
                },
                tx_array: {
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
                rx_array: {
                  num_rows: draft.rx_rows,
                  num_cols: draft.rx_cols,
                  vertical_spacing: 0.5,
                  horizontal_spacing: 0.5,
                  pattern: draft.rx_pattern === 'isotropic' ? 'iso' : draft.rx_pattern,
                  polarization: 'V',
                  gain_grid_json: draft.rx_pattern === 'custom_gain_grid' ? draft.rx_custom_gain_json : null,
                },
                path_solver: {
                  max_depth: draft.max_depth,
                  max_num_paths_per_src: 1_000_000,
                  samples_per_src: draft.samples_per_src,
                  synthetic_array: draft.synthetic_array,
                  los: draft.los,
                  specular_reflection: draft.specular_reflection,
                  diffuse_reflection: draft.diffuse_reflection,
                  refraction: false,
                  diffraction: false,
                  edge_diffraction: false,
                  seed: draft.seed,
                  initial_ray_sampling: {
                    mode: draft.ray_sampling_mode,
                  },
                },
                observation: {
                  beamforming: {
                    tx_mode: draft.tx_pattern === 'radar_array' || draft.tx_pattern === 'custom_gain_grid' ? 'embedded_sionna_pattern' : draft.tx_beamforming_mode,
                    tx_weight_mode: draft.tx_pattern === 'custom_gain_grid' ? 'steering_vector' : draft.tx_beamforming_mode,
                    tx_steering_azimuth_deg: draft.tx_steering_azimuth_deg,
                    tx_steering_elevation_deg: draft.tx_steering_elevation_deg,
                    tx_taper: draft.tx_taper,
                    tx_custom_weights_json: draft.tx_pattern !== 'custom_gain_grid' && draft.tx_beamforming_mode === 'custom_complex_weights' ? draft.tx_custom_weights_json : null,
                    rx_mode: draft.beamforming_rx_mode,
                    rx_steering_azimuth_deg: draft.beamforming_steering_azimuth_deg,
                    rx_steering_elevation_deg: draft.beamforming_steering_elevation_deg,
                    steering_azimuth_deg: draft.beamforming_steering_azimuth_deg,
                    steering_elevation_deg: draft.beamforming_steering_elevation_deg,
                    custom_weights_json: draft.beamforming_custom_weights_json,
                  },
                },
                compute: {
                  samples_per_src: draft.samples_per_src,
                  seed: draft.seed,
                },
                gpu_ids: draft.gpu_ids,
              }
              submitSimulation(request)
                .then((resp) => {
                  setLoadedJobRunId(null)
                  setJob({
                    job_id: resp.job_id,
                    status: resp.status,
                    created_at_utc: '',
                    started_at_utc: null,
                    completed_at_utc: null,
                    progress: { total_tasks: 1, completed_tasks: 0, failed_tasks: 0 },
                    gpu_ids: draft.gpu_ids,
                    current_tasks: [],
                    available_run_ids: [],
                    result: null,
                    error: null,
                  })
                  setNotice('仿真任务已提交。')
                })
                .catch((err) => setError(err instanceof Error ? err.message : String(err)))
                .finally(() => setLoading(false))
            }}
          />
        )}
        {inspectorTab === 'scene' && selectedExperiment && sceneEditConfig && (
          <SceneGeometryEditor
            config={sceneEditConfig}
            baseline={selectedExperiment.config}
            materials={scenePresets.materials}
            saving={savingScene}
            selectedObjectId={selectedSceneObjectId}
            canUndo={sceneUndoStack.length > 0}
            canRedo={sceneRedoStack.length > 0}
            onSelect={setSelectedSceneObjectId}
            onChange={commitSceneEdit}
            onUndo={undoSceneEdit}
            onRedo={redoSceneEdit}
            onReset={() => {
              const next = cloneSceneConfig(selectedExperiment.config)
              commitSceneEdit(next)
              setSelectedSceneObjectId(null)
            }}
            onSave={(next) => {
              setSavingScene(true)
              updateExperiment(selectedExperiment.manifest.experiment_id, next)
                .then((response) => {
                  const nextDraft = experimentToDraftConfig(response.config)
                  setSelectedExperiment(response)
                  setSceneEditConfig(cloneSceneConfig(response.config))
                  setSceneUndoStack([])
                  setSceneRedoStack([])
                  setObjects(experimentToSceneObjects(response.config))
                  setDraft(nextDraft)
                  setBaseline(nextDraft)
                  clearDraftHistory()
                  setNotice('场景已保存为新版本，已有仿真结果保持不变。')
                  return loadExperiments()
                })
                .catch((err) => setError(err instanceof Error ? err.message : String(err)))
                .finally(() => setSavingScene(false))
            }}
            onImportModel={(file) => uploadExperimentModel(selectedExperiment.manifest.experiment_id, file)}
            onImportScene={(file) => importExperimentScene(selectedExperiment.manifest.experiment_id, file)}
            onFetchOsm={(payload) => fetchExperimentOsm(selectedExperiment.manifest.experiment_id, payload)}
            onFetchOsmBbox={(payload) => fetchExperimentOsmBbox(selectedExperiment.manifest.experiment_id, payload)}
          />
        )}
        {inspectorTab === 'paths' && (
          <div className="inspector-results">
            <PathInspector
              paths={paths}
              filteredPaths={filteredPaths}
              selectedPath={selectedPath}
              kindFilter={pathKindFilter}
              gateOnly={gateOnly}
              onKindFilterChange={setPathKindFilter}
              onGateOnlyChange={setGateOnly}
              onSelect={selectPath}
              objects={objects}
            />
            <div className="panel-heading spaced">
              <Eye size={16} />
              <span>场景对象</span>
            </div>
            <div className="object-list">
              {objects.map((object) => (
                <button type="button" className={`object-row ${selectedSceneObjectId === object.object_id ? 'selected' : ''}`} key={object.object_id} onClick={() => setSelectedSceneObjectId(object.object_id)}>
                  <span>{readableObjectLabel(object)}</span>
                  <em>{materialLabels[object.material] ?? object.material}</em>
                </button>
              ))}
            </div>
            <div className="cache-note">
              <span>已加载主要交互点 {interactions?.interactions.length ?? 0} 个；完整信道冲激响应（CIR）可在结果下载中获取</span>
            </div>
            {pathExportRoot && <div className="cache-note"><span>传播路径已保存</span></div>}
            {job && (
              <div className="cache-note">
                <span>仿真状态：{jobStatusLabels[job.status] ?? '未知状态'}</span>
              </div>
            )}
            {metadata && (
              <div className="cache-note">
                <span>载频 {(Number(metadata.metadata.frequency_hz) / 1e9).toFixed(1)} GHz</span>
              </div>
            )}
          </div>
        )}
      </aside>
      {renameTarget && <div className="dialog-backdrop" role="presentation" onMouseDown={() => setRenameTarget(null)}>
        <form className="rename-dialog" onMouseDown={(event) => event.stopPropagation()} onSubmit={(event) => {
          event.preventDefault()
          const name = renameValue.trim()
          if (!name) return
          const action = renameTarget.kind === 'experiment' ? renameExperiment(renameTarget.id, name) : renameResult(renameTarget.id, name)
          action.then(() => {
            if (renameTarget.kind === 'experiment') return loadExperiments().then(() => {
              if (selectedExperimentId === renameTarget.id) setSelectedExperiment((current) => current ? { ...current, manifest: { ...current.manifest, name }, config: { ...current.config, name } } : current)
            })
            return fetchRuns(selectedCampaignId).then(setRuns)
          }).then(() => { setRenameTarget(null); setNotice('名称已更新。') }).catch((err) => setError(err instanceof Error ? err.message : String(err)))
        }}>
          <h2>{renameTarget.kind === 'experiment' ? '修改方案名称' : '修改结果名称'}</h2>
          <label className="field"><span>显示名称</span><input autoFocus maxLength={120} value={renameValue} onChange={(event) => setRenameValue(event.target.value)} /></label>
          <div className="dialog-actions"><button type="button" className="secondary-action" onClick={() => setRenameTarget(null)}>取消</button><button type="submit" className="primary-action" disabled={!renameValue.trim()}>保存</button></div>
        </form>
      </div>}
    </div>
  )
}
