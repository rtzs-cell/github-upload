import { Copy, Download, FileJson, Globe2, Plus, Redo2, RotateCcw, Save, Trash2, Undo2, Upload } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import type { ImportedModelAsset, MaterialPreset, SceneImportResult } from '../api/types'

type Building = {
  id: string
  name?: string
  center_m: [number, number, number]
  size_m: [number, number, number]
  rotation_deg: [number, number, number]
  material: string
  geometry_kind?: 'box' | 'model'
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

export function SceneGeometryEditor({ config, baseline, materials, saving, selectedObjectId, canUndo, canRedo, onChange, onSelect, onUndo, onRedo, onReset, onSave, onImportModel, onImportScene }: {
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
  onSave: (config: Record<string, any>) => void
  onImportModel: (file: File) => Promise<ImportedModelAsset>
  onImportScene: (file: File) => Promise<SceneImportResult>
}) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const sceneInputRef = useRef<HTMLInputElement>(null)
  const mapInputRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)
  const [importMode, setImportMode] = useState<'merge' | 'replace'>('merge')
  const [lastImport, setLastImport] = useState<SceneImportResult | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const dirty = useMemo(() => JSON.stringify(config.scene) !== JSON.stringify(baseline.scene), [baseline.scene, config.scene])
  const buildings = (config.scene?.buildings ?? []) as Building[]

  useEffect(() => {
    if (!selectedObjectId) return
    document.querySelector(`[data-building-id="${CSS.escape(selectedObjectId)}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [selectedObjectId])

  const change = (mutate: (next: Record<string, any>) => void) => {
    const next = cloneSceneConfig(config)
    mutate(next)
    onChange(next)
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
    const ids = new Set(buildings.map((item) => item.id))
    let index = buildings.length + 1
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
    const ids = new Set(importMode === 'merge' ? buildings.map((item) => item.id) : [])
    return items.map((item, index) => {
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
        geometry_kind: item.model ? 'model' : 'box',
      }
    })
  }

  const applyImportedBuildings = (result: SceneImportResult) => {
    const importedBuildings = normalizeImportedBuildings(result.buildings)
    if (!importedBuildings.length) throw new Error('导入文件没有可用建筑')
    change((next) => {
      const currentBuildings = Array.isArray(next.scene.buildings) ? next.scene.buildings : []
      next.scene = {
        ...next.scene,
        ...(importMode === 'replace' ? (result.scene_patch ?? {}) : {}),
        kind: importMode === 'merge' ? 'hybrid' : result.source_type,
        source: {
          ...(next.scene.source ?? {}),
          type: result.source_type,
          filename: result.original_filename,
          source_path: result.source_path,
          origin: result.origin,
          object_count: result.object_count,
        },
        buildings: importMode === 'merge' ? [...currentBuildings, ...importedBuildings] : importedBuildings,
      }
      if (importMode === 'replace' && next.radar && importedBuildings.length) {
        next.radar.look_at_m = importedBuildings.reduce(
          (sum, item) => [sum[0] + item.center_m[0], sum[1] + item.center_m[1], sum[2] + item.center_m[2]],
          [0, 0, 0],
        ).map((value) => value / importedBuildings.length)
      }
    })
    setLastImport(result)
    onSelect(String(importedBuildings[0].id))
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

  const importScene = async (file: File) => {
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
          geometry_kind: item.model ? 'model' : 'box',
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
      if (sceneInputRef.current) sceneInputRef.current.value = ''
    }
  }

  const importModel = async (file: File) => {
    setImporting(true)
    setImportError(null)
    try {
      const bounds = await readModelBounds(file)
      const asset = await onImportModel(file)
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

  return <div className="scene-editor">
    <div className={`simulation-state ${dirty ? 'changed' : 'synced'}`}>
      <span>{dirty ? '场景几何已修改，尚未保存' : '场景几何已保存'}</span>
    </div>
    <section className="scene-editor-section">
      <div className="scene-editor-heading"><strong>地面</strong></div>
      <label className="field"><span>地面材质</span><select value={config.scene?.ground?.material ?? 'concrete'} onChange={(event) => change((next) => { next.scene.ground.material = event.target.value })}>
        {Object.entries(materials).map(([id, item]) => <option key={id} value={id}>{item.label}</option>)}
      </select></label>
    </section>
    <div className="scene-editor-heading"><strong>建筑几何</strong><span>{buildings.length} 个</span></div>
    <div className="scene-import-toolbar">
      <label className="field"><span>导入方式</span><select value={importMode} onChange={(event) => setImportMode(event.target.value as 'merge' | 'replace')} disabled={saving || importing}>
        <option value="merge">追加到当前场景（混合）</option>
        <option value="replace">替换当前建筑</option>
      </select></label>
      <p className="scene-import-help">OSM/GeoJSON 会按建筑面生成可编辑的仿真建筑，坐标原点取导入区域中心。</p>
    </div>
    {importError && <div className="error-banner">{importError}</div>}
    {lastImport && <div className="scene-import-summary"><strong>{lastImport.original_filename} 已导入</strong><span>{lastImport.object_count} 个建筑 · {lastImport.source_type === 'custom' ? '自定义场景' : <>原点 {lastImport.origin.latitude.toFixed(5)}, {lastImport.origin.longitude.toFixed(5)}</>}</span>{lastImport.warnings.length > 0 && <span className="warning-text">{lastImport.warnings.length} 个对象被跳过</span>}</div>}
    <div className="building-editor-list">
      {buildings.map((building, index) => <section data-building-id={building.id} className={`building-editor ${selectedObjectId === building.id ? 'selected' : ''}`} key={building.id} onClick={() => onSelect(building.id)}>
        <div className="building-editor-title">
          <span className="material-swatch" style={{ backgroundColor: materialColors[building.material] ?? '#89989b' }} />
          <input aria-label="建筑名称" value={building.name ?? building.id} onChange={(event) => change((next) => { next.scene.buildings[index].name = event.target.value })} />
          <button type="button" className="compact-icon" title="复制建筑" onClick={(event) => { event.stopPropagation(); const copyId = uniqueId(); change((next) => {
            const copy = cloneSceneConfig(next.scene.buildings[index]) as Building
            copy.id = copyId
            copy.name = `${copy.name ?? building.id} 副本`
            copy.center_m[1] += copy.size_m[1] + 5
            next.scene.buildings.splice(index + 1, 0, copy)
          }); onSelect(copyId) }}><Copy size={14} /></button>
          <button type="button" className="compact-icon danger" title="删除建筑" onClick={(event) => { event.stopPropagation(); change((next) => { next.scene.buildings.splice(index, 1) }); if (selectedObjectId === building.id) onSelect(null) }}><Trash2 size={14} /></button>
        </div>
        <label className="field"><span>材质</span><select value={building.material} onChange={(event) => change((next) => { next.scene.buildings[index].material = event.target.value })}>
          {Object.entries(materials).map(([id, item]) => <option key={id} value={id}>{item.label} · {item.description}</option>)}
        </select></label>
        <div className="geometry-field-group"><span>中心坐标 m</span><div className="vector-fields">{['X', 'Y', 'Z'].map((axis, axisIndex) => <label key={axis}><span>{axis}</span><input type="number" step="1" value={building.center_m[axisIndex]} onChange={(event) => updateVector(index, 'center_m', axisIndex, Number(event.target.value))} /></label>)}</div></div>
        <div className="geometry-field-group"><span>长宽高 m</span><div className="vector-fields">{['X', 'Y', 'Z'].map((axis, axisIndex) => <label key={axis}><span>{axis}</span><input type="number" min="0.1" step="1" value={building.size_m[axisIndex]} onChange={(event) => updateVector(index, 'size_m', axisIndex, Number(event.target.value))} /></label>)}</div></div>
        <div className="geometry-field-group"><span>旋转角 °</span><div className="vector-fields">{['X', 'Y', 'Z'].map((axis, axisIndex) => <label key={axis}><span>{axis}</span><input type="number" step="1" value={vector(building.rotation_deg, [0, 0, 0])[axisIndex]} onChange={(event) => updateRotation(index, axisIndex, Number(event.target.value))} /></label>)}</div></div>
      </section>)}
    </div>
    <button type="button" className="secondary-action full-width" onClick={() => { const id = uniqueId(); change((next) => { next.scene.buildings.push({ id, name: `新建筑 ${buildings.length + 1}`, center_m: [100, 0, 15], size_m: [30, 30, 30], rotation_deg: [0, 0, 0], material: 'concrete', geometry_kind: 'box' }) }); onSelect(id) }}><Plus size={15} />新增建筑</button>
    <input ref={fileInputRef} type="file" accept=".obj,.ply" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void importModel(file) }} />
    <button type="button" className="secondary-action full-width" disabled={importing || saving} onClick={() => fileInputRef.current?.click()}><Upload size={15} />{importing ? '正在导入' : '导入 3D 模型'}</button>
    <input ref={mapInputRef} type="file" accept=".osm,.xml,.geojson,.json" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void importSceneData(file) }} />
    <button type="button" className="secondary-action full-width" disabled={importing || saving} onClick={() => mapInputRef.current?.click()}><Globe2 size={15} />导入 OSM / GeoJSON</button>
    <input ref={sceneInputRef} type="file" accept=".json,.scene.json" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void importScene(file) }} />
    <div className="scene-io-actions">
      <button type="button" className="secondary-action" disabled={saving || importing} onClick={() => sceneInputRef.current?.click()}><FileJson size={15} />导入自定义场景 JSON</button>
      <button type="button" className="secondary-action" disabled={saving || importing} onClick={exportScene}><Download size={15} />导出场景 JSON</button>
    </div>
    <div className="scene-editor-actions">
      <button type="button" className="icon-button" disabled={!canUndo || saving} onClick={onUndo} title="撤销上一步"><Undo2 size={15} /></button>
      <button type="button" className="icon-button" disabled={!canRedo || saving} onClick={onRedo} title="重做"><Redo2 size={15} /></button>
      <button type="button" className="secondary-action" disabled={!dirty || saving} onClick={onReset}><RotateCcw size={15} />恢复已保存</button>
      <button type="button" className="primary-action" disabled={!dirty || saving} onClick={() => onSave(config)}><Save size={15} />{saving ? '保存中' : '保存场景'}</button>
    </div>
  </div>
}
