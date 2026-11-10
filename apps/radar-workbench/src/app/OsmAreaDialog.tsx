import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Globe2, Hand, MapPin, Scan, X } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import type { PointerEvent } from 'react'
import type { OsmBounds } from '../api/types'

const SHANGHAI_CENTER: [number, number] = [31.2304, 121.4737]
export type SceneImportMode = 'merge' | 'replace'

const tileUrl = import.meta.env.VITE_OSM_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const attribution = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>'
const streetZoom = 17

function toBounds({ south, west, north, east }: OsmBounds) {
  return L.latLngBounds([south, west], [north, east])
}

function toSelection(bounds: L.LatLngBounds): OsmBounds {
  return {
    south: bounds.getSouth(),
    west: bounds.getWest(),
    north: bounds.getNorth(),
    east: bounds.getEast(),
  }
}

function selectionSize({ south, west, north, east }: OsmBounds) {
  const midLatitude = (south + north) * Math.PI / 360
  return {
    width: (east - west) * 111_320 * Math.cos(midLatitude),
    height: (north - south) * 110_540,
  }
}

function formatDistance(meters: number) {
  return meters < 1000 ? `${Math.round(meters)} m` : `${(meters / 1000).toFixed(2)} km`
}

export default function OsmAreaDialog({ center, previousBounds, importMode, onModeChange, onImport, onClose }: {
  center: [number, number]
  previousBounds: OsmBounds | null
  importMode: SceneImportMode
  onModeChange: (mode: SceneImportMode) => void
  onImport: (bounds: OsmBounds) => Promise<void>
  onClose: () => void
}) {
  const titleId = useId()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const mapElement = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const tilesRef = useRef<L.TileLayer | null>(null)
  const rectangle = useRef<L.Rectangle | null>(null)
  const drag = useRef<{ id: number; start: L.Point } | null>(null)
  const [drawing, setDrawing] = useState(false)
  const [selection, setSelection] = useState<OsmBounds | null>(null)
  const [tileError, setTileError] = useState(false)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const dialog = dialogRef.current!
    const container = mapElement.current!
    dialog.showModal()
    const map = L.map(container, {
      zoomControl: false,
      boxZoom: false,
      minZoom: 2,
      maxZoom: 19,
      maxBounds: [[-85.051, -180], [85.051, 180]],
      maxBoundsViscosity: 1,
    }).setView(center, streetZoom)
    mapRef.current = map
    if (previousBounds) {
      const bounds = toBounds(previousBounds)
      L.rectangle(bounds, { interactive: false, color: '#185e76', fill: false, weight: 2, dashArray: '7 5' }).addTo(map)
      map.fitBounds(bounds, { padding: [38, 38], maxZoom: streetZoom })
    }
    const tiles = L.tileLayer(tileUrl, { attribution, noWrap: true, maxZoom: 19 })
    let failedTile = false
    tiles.on('loading', () => { failedTile = false })
    tiles.on('tileerror', () => { failedTile = true })
    tiles.on('load', () => setTileError(failedTile))
    tiles.addTo(map)
    tilesRef.current = tiles
    map.attributionControl.setPrefix(false)
    L.control.zoom({ zoomInTitle: '放大地图', zoomOutTitle: '缩小地图' }).addTo(map)
    L.control.scale({ imperial: false, maxWidth: 100 }).addTo(map)
    const resize = new ResizeObserver(() => map.invalidateSize({ pan: false }))
    resize.observe(container)
    return () => {
      resize.disconnect()
      map.remove()
      mapRef.current = null
      tilesRef.current = null
      rectangle.current = null
      dialog.close()
    }
  }, [center, previousBounds])

  function showRectangle(bounds: L.LatLngBounds | null) {
    const map = mapRef.current
    if (!map) return
    if (bounds && rectangle.current) {
      rectangle.current.setBounds(bounds)
    } else if (bounds) {
      rectangle.current = L.rectangle(bounds, { interactive: false, color: '#00695b', weight: 2, fillOpacity: 0.16 }).addTo(map)
    } else {
      rectangle.current?.remove()
      rectangle.current = null
    }
  }

  function choose(bounds: L.LatLngBounds | null) {
    drag.current = null
    setError(null)
    setDrawing(false)
    setSelection(bounds ? toSelection(bounds) : null)
    showRectangle(bounds)
  }

  function pointerPoint(event: PointerEvent<HTMLDivElement>, map: L.Map) {
    const point = map.mouseEventToContainerPoint(event.nativeEvent)
    const size = map.getSize()
    return L.point(Math.min(size.x, Math.max(0, point.x)), Math.min(size.y, Math.max(0, point.y)))
  }

  function drawRectangle(event: PointerEvent<HTMLDivElement>, finished: boolean) {
    const map = mapRef.current
    const start = drag.current
    if (!map || !start || start.id !== event.pointerId) return
    const end = pointerPoint(event, map)
    const bounds = L.latLngBounds(map.containerPointToLatLng(start.start), map.containerPointToLatLng(end))
    if (!finished) {
      showRectangle(bounds)
      return
    }
    if (Math.abs(end.x - start.start.x) >= 4 && Math.abs(end.y - start.start.y) >= 4) {
      choose(bounds)
    } else {
      drag.current = null
      showRectangle(selection ? toBounds(selection) : null)
      setError('请按住地图拖出一个矩形。')
    }
  }

  const size = selection && selectionSize(selection)
  const rangeError = selection && size && (
    selection.west < -180 || selection.east > 180
      ? '请在同一侧经度范围内重新框选。'
      : Math.max(size.width, size.height) > 5000
        ? '框选范围的宽和高各限 5 km。请放大地图后重新框选。'
        : null
  )

  async function importSelection() {
    if (!selection || rangeError || importing) return
    setError(null)
    setImporting(true)
    try {
      await onImport(selection)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setImporting(false)
    }
  }

  return <dialog ref={dialogRef} className="osm-dialog" aria-labelledby={titleId} onCancel={(event) => {
    event.preventDefault()
    if (!importing) onClose()
  }}>
    <div className="osm-dialog-content">
      <header className="osm-dialog-header">
        <div><h2 id={titleId}>在 OpenStreetMap 上选街区</h2><p>移动地图找到街区，放大后沿街道框选建筑。</p></div>
        <button type="button" className="icon-button" aria-label="关闭地图" disabled={importing} onClick={onClose}><X size={18} /></button>
      </header>
      <div className="osm-dialog-toolbar">
        <button type="button" className="secondary-action" aria-pressed={!drawing} disabled={importing} onClick={() => setDrawing(false)}><Hand size={15} />移动地图</button>
        <button type="button" className="secondary-action" aria-pressed={drawing} disabled={importing} onClick={() => { setError(null); setDrawing(true) }}><Scan size={15} />画矩形</button>
        <button type="button" className="secondary-action osm-recenter" disabled={importing} onClick={() => mapRef.current?.setView(SHANGHAI_CENTER, streetZoom)}><MapPin size={15} />上海人民广场</button>
      </div>
      <div className="osm-map-frame">
        <div ref={mapElement} className="osm-map" aria-label="OpenStreetMap 街区地图" />
        {drawing && <div className="osm-map-draw" onPointerDown={(event) => {
          const map = mapRef.current
          if (!map || event.button !== 0 || !event.isPrimary) return
          event.currentTarget.setPointerCapture(event.pointerId)
          drag.current = { id: event.pointerId, start: pointerPoint(event, map) }
        }} onPointerMove={(event) => drawRectangle(event, false)} onPointerUp={(event) => drawRectangle(event, true)} onLostPointerCapture={() => {
          if (!drag.current) return
          drag.current = null
          showRectangle(selection ? toBounds(selection) : null)
        }} />}
        {importing && <div className="osm-map-busy" />}
      </div>
      <div className="osm-selection-status" aria-live="polite">
        <strong>{size ? `已框选 ${formatDistance(size.width)} × ${formatDistance(size.height)}` : drawing ? '在地图上拖出一个矩形' : '等待选择街区'}</strong>
        <div className="osm-selection-actions">
          <button type="button" className="compact-text-button" disabled={importing} onClick={() => choose(mapRef.current?.getBounds() ?? null)}>使用当前视野</button>
          {selection && <button type="button" className="compact-text-button" disabled={importing} onClick={() => choose(null)}>清除框选</button>}
        </div>
        {selection
          ? <small>南 {selection.south.toFixed(6)} · 西 {selection.west.toFixed(6)} · 北 {selection.north.toFixed(6)} · 东 {selection.east.toFixed(6)}</small>
          : previousBounds && <small>蓝色虚线标记上次查询范围</small>}
      </div>
      {tileError && <div className="osm-map-warning" role="status">部分底图未加载。<button type="button" className="compact-text-button" onClick={() => tilesRef.current?.redraw()}>重试底图</button></div>}
      {(error || rangeError) && <div className="error-banner" role="alert">{error || rangeError}</div>}
      <footer className="osm-dialog-footer">
        <label className="field"><span>导入方式</span><select value={importMode} disabled={importing} onChange={(event) => onModeChange(event.target.value as SceneImportMode)}>
          <option value="merge">追加到当前场景</option>
          <option value="replace">替换当前建筑</option>
        </select></label>
        <button type="button" className="primary-action" disabled={!selection || Boolean(rangeError) || drawing || importing} onClick={() => void importSelection()}><Globe2 size={16} />{importing ? '正在获取建筑…' : '导入建筑'}</button>
      </footer>
    </div>
  </dialog>
}
