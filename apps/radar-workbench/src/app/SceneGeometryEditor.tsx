import { ChevronLeft, ChevronRight, Copy, Download, FileJson, Globe2, Map, Plus, Redo2, RotateCcw, Save, Search, Trash2, Undo2, Upload } from 'lucide-react'
import { lazy, Suspense, useLayoutEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import type { ImportedModelAsset, MaterialPreset, OsmBounds, SceneImportResult } from '../api/types'
import type { SceneImportMode } from './OsmAreaDialog'

const OsmAreaDialog = lazy(() => import('./OsmAreaDialog'))
const PAGE_SIZE = 12
const METERS_PER_DEGREE_LATITUDE = 110_540
const METERS_PER_DEGREE_LONGITUDE = 111_320

type GeoOrigin = SceneImportResult['origin']

type Building = {
  id: string
  name?: string
  center_m: [number, number, number]
  size_m: [number, number, number]
  rotation_deg: [number, number, number]
  material: string
  geometry_kind?: 'box' | 'model' | 'extruded_polygon'
  footprint_m?: Array<[number, number]>
  source?: { type?: string; id?: string }
  model?: ImportedModelAsset & {
    source_bbox_min: [number, number, number]
    source_bbox_max: [number, number, number]
  }
}

const materialColors: Record<string, string> = {
  concrete: '#89989b', brick: '#b45f4d', glass: '#4d9bb5', marble: '#a8a9b0', wood: '#9b794d', metal: '#5f696d',
}

export function cloneSceneConfig(config: Record<string, any>) {
  return JSON.parse(JSON.stringify(config)) as Record<string, any>
}

async function readModelBounds(file: File): Promise<{ min: [number, number, number]; max: [number, number, number] }> {
  const extension = file.name.split('.').pop()?.toLowerCase()
  const bounds = new THREE.Box3()
  if (extension === 'obj') {
    const object = new OBJLoader().parse(await file.text())
    bounds.setFromObject(object)
  } else if (extension === 'ply') {
    const geometry = new PLYLoader().parse(await file.arrayBuffer())
    geometry.computeBoundingBox()
    if (geometry.boundingBox) bounds.copy(geometry.boundingBox)
  } else {
    throw new Error('仅支持 OBJ 和 PLY 模型')
  }
  if (bounds.isEmpty()) throw new Error('模型不包含可用顶点')
  return {
    min: [bounds.min.x, bounds.min.y, bounds.min.z],
    max: [bounds.max.x, bounds.max.y, bounds.max.z],
  }
}

function vector(value: unknown, fallback: [number, number, number]): [number, number, number] {
  if (!Array.isArray(value)) return fallback
  return [Number(value[0] ?? fallback[0]), Number(value[1] ?? fallback[1]), Number(value[2] ?? fallback[2])]
}

function buildingLabel(building: Building, index: number) {
  const name = building.name?.trim()
  return name && name !== 'yes' ? name : `建筑 ${building.source?.id || index + 1}`
}

function sceneGeoOrigin(scene?: Record<string, any>): GeoOrigin | undefined {
  const source = scene?.source
  const origin = scene?.geographic_origin ?? (source?.type === 'osm' || source?.type === 'geojson' ? source.origin : undefined)
  if (origin && Number.isFinite(origin.latitude) && Number.isFinite(origin.longitude)) return origin
}

function alignImportedBuildings(buildings: Building[], from: GeoOrigin, to: GeoOrigin) {
  const longitudeScale = (latitude: number) => METERS_PER_DEGREE_LONGITUDE * Math.cos(latitude * Math.PI / 180)
  const xScale = longitudeScale(to.latitude) / longitudeScale(from.latitude)
  const dx = (from.longitude - to.longitude) * longitudeScale(to.latitude)
  const dy = (from.latitude - to.latitude) * METERS_PER_DEGREE_LATITUDE
  for (const building of buildings) {
    building.center_m[0] = building.center_m[0] * xScale + dx
    building.center_m[1] += dy
    building.size_m[0] *= xScale
    building.footprint_m = building.footprint_m?.map(([x, y]) => [x * xScale, y])
  }
}

function osmError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error)
  if (/No building polygons found/i.test(message)) return '这个范围内没有查到可导入的 OSM 建筑。请调整选区后重试。'
  if (/HTTP 429/i.test(message)) return 'OSM 建筑服务请求过多。请稍后重试。'
  if (/HTTP 5\d\d|timed out|timeout/i.test(message)) return 'OSM 建筑服务暂时无法响应。请重试或缩小选区。'
  if (/Overpass request failed|Failed to fetch/i.test(message)) return '未能获取 OSM 建筑。请重试，或从本地导入 OSM 文件。'
  return message
}

export function SceneGeometryEditor({ config, baseline, materials, saving, selectedObjectId, canUndo, canRedo, onChange, onSelect, onUndo, onRedo, onReset, onSave, onImportModel, onImportScene, onFetchOsm, onFetchOsmBbox }: {
  config: Record<string, any>
  baseline: Record<string, any>
  materials: Record<string, MaterialPreset>
  saving: boolean
  selectedObjectId: string | null
  canUndo: boolean
  canRedo: boolean
  onChange: (config: Record<string, any>) => void
  onSelect: (objectId: string | null) => void
  onUndo: () => void
  onRedo: () => void
  onReset: () => void
  onSave: (config: Record<string, any>) => Promise<void>
  onImportModel: (file: File) => Promise<ImportedModelAsset>
  onImportScene: (file: File) => Promise<SceneImportResult>
  onFetchOsm: (payload: { latitude: number; longitude: number; radius_km: number }) => Promise<SceneImportResult>
  onFetchOsmBbox: (payload: OsmBounds) => Promise<SceneImportResult>
}) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const sceneInputRef = useRef<HTMLInputElement>(null)
  const mapInputRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)
  const [fetchingOsm, setFetchingOsm] = useState(false)
  const [osmLatitude, setOsmLatitude] = useState('31.2304')
  const [osmLongitude, setOsmLongitude] = useState('121.4737')
  const [osmRadiusKm, setOsmRadiusKm] = useState('1')
  const [mapOpen, setMapOpen] = useState(false)
  const [importMode, setImportMode] = useState<SceneImportMode>('merge')
  const [lastImport, setLastImport] = useState<SceneImportResult | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const dirty = useMemo(() => JSON.stringify(config.scene) !== JSON.stringify(baseline.scene), [baseline.scene, config.scene])
  const buildings = (config.scene?.buildings ?? []) as Building[]
  const source = config.scene?.source
  const busy = saving || importing || fetchingOsm
  const selectedIndex = buildings.findIndex((item) => item.id === selectedObjectId)
  const selectedBuilding = buildings[selectedIndex]
  const query = search.trim().toLowerCase()
  const matchingBuildings = useMemo(() => buildings.map((building, index) => ({
    building, label: buildingLabel(building, index),
  })).filter(({ building, label }) => label.toLowerCase().includes(query) || String(building.source?.id ?? '').toLowerCase().includes(query)), [buildings, query])
  const pageCount = Math.max(1, Math.ceil(matchingBuildings.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount - 1)
  const origin = sceneGeoOrigin(config.scene)
  const mapView = useMemo(() => {
    const center: [number, number] = origin ? [origin.latitude, origin.longitude] : [31.2304, 121.4737]
    const coords = source?.query_bounds
    const previousBounds = Array.isArray(coords) && coords.length === 4 && coords.every(Number.isFinite)
      ? { south: coords[0], west: coords[1], north: coords[2], east: coords[3] } : null
    return { center, previousBounds }
  }, [origin, source])
  const editor = useRef<{ config: typeof config; onChange: typeof onChange } | null>(null)
  useLayoutEffect(() => {
    editor.current = { config, onChange }
    return () => { editor.current = null }
  }, [config, onChange])

  const change = (mutate: (next: Record<string, any>) => void) => {
    if (!editor.current) return
    const next = cloneSceneConfig(editor.current.config)
    mutate(next)
    editor.current.onChange(next)
  }
  const updateVector = (index: number, key: 'center_m' | 'size_m', axis: number, value: number) => change((next) => {
    const building = next.scene.buildings[index] as Building
    const normalized = key === 'size_m' ? Math.max(0.1, value) : value
    building[key][axis] = normalized
    if (axis === 2) {
      building.center_m[2] = Math.max(building.center_m[2], building.size_m[2] / 2)
    }
  })
  const updateRotation = (index: number, axis: number, value: number) => change((next) => {
    const building = next.scene.buildings[index] as Building
    building.rotation_deg = vector(building.rotation_deg, [0, 0, 0])
    building.rotation_deg[axis] = value
  })
  const uniqueId = (prefix = 'building') => {
    const current = (editor.current?.config.scene?.buildings ?? []) as Building[]
    const ids = new Set(current.map((item) => item.id))
    let index = current.length + 1
    while (ids.has(`${prefix}_${index}`)) index += 1
    return `${prefix}_${index}`
  }

  const exportScene = () => {
    const payload = {
      export_kind: 'radar_workbench_scene',
      schema_version: '0.2.0',
      exported_at_utc: new Date().toISOString(),
      scene: cloneSceneConfig(config.scene),
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${String(config.name ?? 'radar-scene').replace(/[^a-zA-Z0-9_.-]+/g, '_')}.scene.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const normalizeImportedBuildings = (items: Array<Record<string, any>>) => {
    const current = (editor.current?.config.scene?.buildings ?? []) as Building[]
    const ids = new Set(importMode === 'merge' ? current.map((item) => item.id) : [])
    return items.map<Building>((item, index) => {
      const baseId = String(item.id ?? ('imported_' + (index + 1)))
      let id = baseId
      let suffix = 2
      while (ids.has(id)) id = baseId + '_' + suffix++
      ids.add(id)
      const center = vector(item.center_m, [0, 0, 6])
      const size = vector(item.size_m, [10, 10, 12]).map((value) => Math.max(0.1, value)) as [number, number, number]
      return {
        ...item,
        id,
        name: String(item.name ?? id),
        center_m: [center[0], center[1], Math.max(center[2], size[2] / 2)] as [number, number, number],
        size_m: size,
        rotation_deg: vector(item.rotation_deg, [0, 0, 0]),
        material: String(item.material ?? 'concrete'),
        geometry_kind: item.model ? 'model' : Array.isArray(item.footprint_m) ? 'extruded_polygon' : 'box',
        footprint_m: Array.isArray(item.footprint_m) ? item.footprint_m : undefined,
      }
    })
  }

  const applyImportedBuildings = (result: SceneImportResult) => {
    if (!editor.current) return
    const currentScene = editor.current.config.scene
    const currentBuildings: Building[] = currentScene.buildings ?? []
    const merging = importMode === 'merge'
    const geographicImport = result.source_type === 'osm' || result.source_type === 'geojson'
    const importedOrigin = geographicImport ? result.origin : sceneGeoOrigin(result.scene_patch)
    const existingOrigin = merging ? sceneGeoOrigin(currentScene) : undefined
    const existingOsmIds = new Set(merging ? currentBuildings
      .filter((building) => building.source?.type === 'osm' && building.source.id)
      .map((building) => String(building.source?.id)) : [])
    const newBuildings = result.source_type === 'osm'
      ? result.buildings.filter((building) => !existingOsmIds.has(String(building.source?.id)))
      : result.buildings
    const importedBuildings = normalizeImportedBuildings(newBuildings)
    if (!importedBuildings.length) {
      throw new Error(result.object_count
        ? '这些 OSM 建筑已在当前场景中。要单独查看这块街区，请选择「替换当前建筑」。'
        : '导入文件没有可用建筑。')
    }
    if (geographicImport && existingOrigin) alignImportedBuildings(importedBuildings, result.origin, existingOrigin)
    change((next) => {
      next.scene = {
        ...next.scene,
        ...(merging ? {} : result.scene_patch ?? {}),
        kind: merging ? 'hybrid' : result.source_type,
        geographic_origin: existingOrigin ?? importedOrigin,
        source: {
          ...(next.scene.source ?? {}),
          type: result.source_type,
          filename: result.original_filename,
          source_path: result.source_path,
          origin: result.origin,
          object_count: importedBuildings.length,
          query_bounds: result.fetch_request?.bbox,
        },
        buildings: merging ? [...currentBuildings, ...importedBuildings] : importedBuildings,
      }
      if ((!merging || !currentBuildings.length) && next.radar) {
        next.radar.look_at_m = importedBuildings.reduce(
          (sum, item) => [sum[0] + item.center_m[0], sum[1] + item.center_m[1], sum[2] + item.center_m[2]],
          [0, 0, 0],
        ).map((value) => value / importedBuildings.length)
      }
    })
    setLastImport({ ...result, object_count: importedBuildings.length })
    setSearch('')
    setPage(0)
    onSelect(null)
  }

  const importSceneData = async (file: File) => {
    setImporting(true)
    setImportError(null)
    try {
      const result = await onImportScene(file)
      applyImportedBuildings(result)
    } catch (error) {
      setImportError(error instanceof Error ? error.message : String(error))
    } finally {
      setImporting(false)
      if (mapInputRef.current) mapInputRef.current.value = ''
    }
  }

  const fetchOsm = async () => {
    setImportError(null)
    const latitude = Number(osmLatitude)
    const longitude = Number(osmLongitude)
    const radiusKm = Number(osmRadiusKm)
    if (!osmLatitude || !osmLongitude || ![latitude, longitude, radiusKm].every(Number.isFinite)
        || Math.abs(latitude) > 90 || Math.abs(longitude) > 180 || radiusKm <= 0 || radiusKm > 5) {
      setImportError('请输入有效经纬度，半径须大于 0 且不超过 5 km。')
      return
    }
    setFetchingOsm(true)
    try {
      applyImportedBuildings(await onFetchOsm({ latitude, longitude, radius_km: radiusKm }))
    } catch (error) {
      setImportError(osmError(error))
    } finally {
      setFetchingOsm(false)
    }
  }

  const importMapArea = async (bounds: OsmBounds) => {
    setImportError(null)
    try {
      applyImportedBuildings(await onFetchOsmBbox(bounds))
      setMapOpen(false)
    } catch (error) {
      throw new Error(osmError(error))
    }
  }

  const importScene = async (file: File) => {
    setImporting(true)
    setImportError(null)
    try {
      const parsed = JSON.parse(await file.text()) as Record<string, any>
      const imported = (parsed.scene && typeof parsed.scene === 'object' ? parsed.scene : parsed) as Record<string, any>
      if (!Array.isArray(imported.buildings)) throw new Error('场景 JSON 必须包含 buildings 数组')
      const normalizedBuildings = imported.buildings.map((item, index) => {
        const center = vector(item.center_m, [100, 0, 15])
        const size = vector(item.size_m, [30, 30, 30]).map((value) => Math.max(0.1, value)) as [number, number, number]
        const rotation = vector(item.rotation_deg, [0, 0, 0])
        return {
          ...item,
          id: String(item.id ?? `building_${index + 1}`),
          name: String(item.name ?? item.id ?? `建筑 ${index + 1}`),
          center_m: [center[0], center[1], Math.max(center[2], size[2] / 2)] as [number, number, number],
          size_m: size,
          rotation_deg: rotation,
          material: String(item.material ?? 'concrete'),
          geometry_kind: item.model ? 'model' : Array.isArray(item.footprint_m) ? 'extruded_polygon' : 'box',
          footprint_m: Array.isArray(item.footprint_m) ? item.footprint_m : undefined,
        }
      })
      const result = {
        source_type: 'custom' as const,
        source_key: 'custom-json',
        original_filename: file.name,
        source_path: '',
        origin: { latitude: 0, longitude: 0 },
        object_count: normalizedBuildings.length,
        warnings: [],
        buildings: normalizedBuildings,
        scene_patch: imported,
      }
      applyImportedBuildings(result)
    } catch (error) {
      setImportError(error instanceof Error ? error.message : String(error))
    } finally {
      setImporting(false)
      if (sceneInputRef.current) sceneInputRef.current.value = ''
    }
  }

  const importModel = async (file: File) => {
    setImporting(true)
    setImportError(null)
    try {
      const bounds = await readModelBounds(file)
      const asset = await onImportModel(file)
      if (!editor.current) return
      const sourceSize = bounds.max.map((value, axis) => Math.max(value - bounds.min[axis], 1e-6)) as [number, number, number]
      const normalization = 40 / Math.max(...sourceSize)
      const size = sourceSize.map((value) => Math.max(0.1, Number((value * normalization).toFixed(3)))) as [number, number, number]
      const id = uniqueId('model')
      change((next) => {
        next.scene.buildings.push({
          id,
          name: file.name.replace(/\.[^.]+$/, ''),
          center_m: [100, 0, size[2] / 2],
          size_m: size,
          rotation_deg: [0, 0, 0],
          material: 'concrete',
          geometry_kind: 'model',
          model: { ...asset, source_bbox_min: bounds.min, source_bbox_max: bounds.max },
        })
      })
      onSelect(id)
    } catch (error) {
      setImportError(error instanceof Error ? error.message : String(error))
    } finally {
      setImporting(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const saveScene = async () => {
    setSaveError(null)
    try {
      await onSave(config)
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : String(error))
    }
  }

  const importModeField = <label className="field">
    <span>导入方式</span>
    <select value={importMode} onChange={(event) => setImportMode(event.target.value as SceneImportMode)}>
      <option value="merge">追加到当前场景</option>
      <option value="replace">替换当前建筑</option>
    </select>
  </label>
  const activeImport = lastImport && lastImport.source_path === source?.source_path ? lastImport : null

  return <div className="scene-editor">
    <div className="scene-editor-header">
      <div className="scene-editor-heading"><h2>场景几何</h2><span>{buildings.length.toLocaleString('zh-CN')} 个建筑</span></div>
      <div className="scene-editor-actions">
        <button type="button" className="icon-button" disabled={!canUndo || busy} onClick={onUndo} aria-label="撤销场景修改" title="撤销场景修改"><Undo2 size={15} /></button>
        <button type="button" className="icon-button" disabled={!canRedo || busy} onClick={onRedo} aria-label="重做场景修改" title="重做场景修改"><Redo2 size={15} /></button>
        <button type="button" className="icon-button" disabled={!dirty || busy} onClick={() => { onReset(); setSaveError(null) }} aria-label="恢复已保存场景" title="恢复已保存场景"><RotateCcw size={15} /></button>
        <button type="button" className="primary-action" disabled={!dirty || busy} onClick={() => void saveScene()}><Save size={15} />{saving ? '正在保存…' : '保存场景'}</button>
      </div>
      <div className={`simulation-state ${dirty ? 'changed' : 'synced'}`} role="status">{dirty ? '有未保存的场景修改' : '场景已保存'}</div>
      {saveError && dirty && <div className="error-banner" role="alert">保存失败。{saveError}</div>}
    </div>
    <fieldset className="scene-editor-fields" disabled={busy}>
      <section className="scene-editor-section scene-import-card" aria-label="导入建筑">
        <div className="scene-editor-heading"><strong>导入建筑</strong></div>
        <button type="button" className="primary-action full-width" onClick={() => setMapOpen(true)}><Map size={16} />在地图上框选</button>
        <details className="scene-editor-disclosure">
          <summary>按坐标和半径获取</summary>
          {importModeField}
          <div className="online-import-grid">
            <label className="field"><span>中心纬度</span><input type="number" min="-90" max="90" step="any" value={osmLatitude} onChange={(event) => setOsmLatitude(event.target.value)} /></label>
            <label className="field"><span>中心经度</span><input type="number" min="-180" max="180" step="any" value={osmLongitude} onChange={(event) => setOsmLongitude(event.target.value)} /></label>
            <label className="field"><span>半径（km）</span><input type="number" min="0.1" max="5" step="any" value={osmRadiusKm} onChange={(event) => setOsmRadiusKm(event.target.value)} /></label>
          </div>
          <button type="button" className="secondary-action full-width" onClick={() => void fetchOsm()}><Globe2 size={15} />{fetchingOsm ? '正在获取建筑…' : '按半径导入'}</button>
        </details>
        <details className="scene-editor-disclosure">
          <summary>本地文件与导出</summary>
          {importModeField}
          <input ref={mapInputRef} type="file" accept=".osm,.xml,.geojson,.json" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void importSceneData(file) }} />
          <button type="button" className="secondary-action full-width" onClick={() => mapInputRef.current?.click()}><Globe2 size={15} />导入 OSM / GeoJSON</button>
          <input ref={fileInputRef} type="file" accept=".obj,.ply" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void importModel(file) }} />
          <button type="button" className="secondary-action full-width" onClick={() => fileInputRef.current?.click()}><Upload size={15} />导入 3D 模型</button>
          <input ref={sceneInputRef} type="file" accept=".json,.scene.json" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void importScene(file) }} />
          <button type="button" className="secondary-action full-width" onClick={() => sceneInputRef.current?.click()}><FileJson size={15} />导入自定义场景 JSON</button>
          <button type="button" className="secondary-action full-width" onClick={exportScene}><Download size={15} />导出场景 JSON</button>
        </details>
        {importing && <p className="scene-import-help" role="status">正在导入本地文件…</p>}
        {importError && <div className="error-banner" role="alert">{importError}</div>}
        {activeImport && <div className="scene-import-summary" role="status">
          <strong>已导入 {activeImport.object_count.toLocaleString('zh-CN')} 个建筑</strong>
          {dirty && <span>在三维视图中检查建筑，确认后点击「保存场景」。</span>}
          {activeImport.warnings.length > 0 && <span className="warning-text">{activeImport.warnings.length} 个对象被跳过</span>}
        </div>}
      </section>
      <section className="scene-editor-section scene-building-section" aria-label="建筑列表">
        <div className="scene-editor-heading">
          <strong>建筑列表</strong>
          <button type="button" className="secondary-action" onClick={() => {
            const id = uniqueId()
            change((next) => { next.scene.buildings.push({ id, name: `新建筑 ${buildings.length + 1}`, center_m: [100, 0, 15], size_m: [30, 30, 30], rotation_deg: [0, 0, 0], material: 'concrete', geometry_kind: 'box' }) })
            onSelect(id)
          }}><Plus size={14} />新增</button>
        </div>
        {buildings.length > 0 ? <>
          <label className="scene-building-search"><Search size={15} /><input type="search" aria-label="搜索建筑" placeholder="搜索建筑名或 OSM 编号" value={search} onChange={(event) => { setSearch(event.target.value); setPage(0) }} /></label>
          {matchingBuildings.length ? <div className="building-editor-list">
            {matchingBuildings.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE).map(({ building, label }) =>
              <button type="button" className="scene-building-row" key={building.id} aria-pressed={building.id === selectedObjectId} onClick={() => onSelect(building.id)}>
                <span className="material-swatch" style={{ backgroundColor: materialColors[building.material] ?? '#89989b' }} />
                <span className="scene-building-name" title={label}>{label}</span>
                <span className="scene-building-height">{Number(Number(building.size_m[2]).toFixed(1))} m</span>
              </button>)}
          </div> : <p className="scene-import-help">没有匹配的建筑。</p>}
          {pageCount > 1 && <div className="scene-building-pages" aria-label="建筑列表分页">
            <button type="button" className="icon-button" aria-label="上一页建筑" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={15} /></button>
            <span>{currentPage + 1} / {pageCount} 页</span>
            <button type="button" className="icon-button" aria-label="下一页建筑" disabled={currentPage + 1 === pageCount} onClick={() => setPage(currentPage + 1)}><ChevronRight size={15} /></button>
          </div>}
        </> : <p className="scene-import-help">场景中还没有建筑。可以从地图导入，或添加一栋自定义建筑。</p>}
      </section>
      {selectedBuilding && <section className="building-editor selected" aria-label="所选建筑参数">
        <div className="scene-editor-heading"><strong>所选建筑</strong>{selectedBuilding.source?.type === 'osm' && selectedBuilding.source.id && <span>OSM {selectedBuilding.source.id}</span>}</div>
        <div className="building-editor-title">
          <input aria-label="建筑名称" value={selectedBuilding.name ?? selectedBuilding.id} onChange={(event) => change((next) => { next.scene.buildings[selectedIndex].name = event.target.value })} />
          <button type="button" className="compact-icon" aria-label="复制建筑" title="复制建筑" onClick={() => {
            const copyId = uniqueId()
            change((next) => {
              const copy = cloneSceneConfig(next.scene.buildings[selectedIndex]) as Building
              copy.id = copyId
              copy.name = `${buildingLabel(selectedBuilding, selectedIndex)} 副本`
              copy.center_m[1] += copy.size_m[1] + 5
              next.scene.buildings.splice(selectedIndex + 1, 0, copy)
            })
            onSelect(copyId)
          }}><Copy size={14} /></button>
          <button type="button" className="compact-icon danger" aria-label="删除建筑" title="删除建筑" onClick={() => {
            change((next) => { next.scene.buildings.splice(selectedIndex, 1) })
            onSelect(null)
          }}><Trash2 size={14} /></button>
        </div>
        <label className="field"><span>材质</span><select value={selectedBuilding.material} onChange={(event) => change((next) => { next.scene.buildings[selectedIndex].material = event.target.value })}>
          {Object.entries(materials).map(([id, item]) => <option key={id} value={id}>{item.label} · {item.description}</option>)}
        </select></label>
        <div className="geometry-field-group"><span>中心坐标（m）</span><div className="vector-fields">{['X', 'Y', 'Z'].map((axis, index) => <label key={axis}><span>{axis}</span><input aria-label={`中心坐标 ${axis}`} type="number" step="any" value={selectedBuilding.center_m[index]} onChange={(event) => updateVector(selectedIndex, 'center_m', index, Number(event.target.value))} /></label>)}</div></div>
        <div className="geometry-field-group"><span>长宽高（m）</span><div className="vector-fields">{['X', 'Y', 'Z'].map((axis, index) => <label key={axis}><span>{axis}</span><input aria-label={`尺寸 ${axis}`} type="number" min="0.1" step="any" value={selectedBuilding.size_m[index]} onChange={(event) => updateVector(selectedIndex, 'size_m', index, Number(event.target.value))} /></label>)}</div></div>
        <div className="geometry-field-group"><span>旋转角（°）</span><div className="vector-fields">{['X', 'Y', 'Z'].map((axis, index) => <label key={axis}><span>{axis}</span><input aria-label={`旋转角 ${axis}`} type="number" step="any" value={vector(selectedBuilding.rotation_deg, [0, 0, 0])[index]} onChange={(event) => updateRotation(selectedIndex, index, Number(event.target.value))} /></label>)}</div></div>
      </section>}
      {config.scene?.ground && <details className="scene-editor-section scene-editor-disclosure">
        <summary>地面设置</summary>
        <label className="field"><span>地面材质</span><select value={config.scene.ground.material ?? 'concrete'} onChange={(event) => change((next) => { next.scene.ground.material = event.target.value })}>
          {Object.entries(materials).map(([id, item]) => <option key={id} value={id}>{item.label}</option>)}
        </select></label>
      </details>}
    </fieldset>
    {mapOpen && <Suspense fallback={<p className="scene-import-help" role="status">正在打开地图…</p>}>
      <OsmAreaDialog center={mapView.center} previousBounds={mapView.previousBounds} importMode={importMode} onModeChange={setImportMode} onImport={importMapArea} onClose={() => setMapOpen(false)} />
    </Suspense>}
  </div>
}
