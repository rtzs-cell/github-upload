import { useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import type { RadarDraftConfig } from '../api/types'
import { boresightAzimuthDeg, withAzimuth, withElevation } from './radarConfig'

type DragTarget = 'boresight' | 'left-edge' | 'right-edge' | 'elevation' | 'elevation-min' | 'elevation-max' | null

const center = 110
const radius = 86
const dialSize = 220
const elevationUiMin = -20
const elevationUiMax = 80
const minElevationSpan = 1
const elevationOrigin = { x: 34, y: 170 }
const elevationRadius = 126

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function normalizeDeg(value: number) {
  let next = ((value + 180) % 360) - 180
  if (next < -180) next += 360
  return next
}

function angleDeltaDeg(value: number, reference: number) {
  return normalizeDeg(value - reference)
}

function polarPoint(angleDeg: number, distance = radius) {
  const rad = (angleDeg * Math.PI) / 180
  return {
    x: center + distance * Math.cos(rad),
    y: center - distance * Math.sin(rad),
  }
}

function pointerAngle(event: ReactPointerEvent<SVGSVGElement>, svg: SVGSVGElement) {
  return pointerAngleFromOrigin(event, svg, center, center)
}

function pointerAngleFromOrigin(
  event: ReactPointerEvent<SVGSVGElement>,
  svg: SVGSVGElement,
  originX: number,
  originY: number,
) {
  const rect = svg.getBoundingClientRect()
  const viewX = ((event.clientX - rect.left) / rect.width) * dialSize
  const viewY = ((event.clientY - rect.top) / rect.height) * dialSize
  const x = viewX - originX
  const y = originY - viewY
  return normalizeDeg((Math.atan2(y, x) * 180) / Math.PI)
}

function formatDeg(value: number) {
  return `${value.toFixed(0)} 度`
}

function sectorPath(startDeg: number, endDeg: number) {
  const start = polarPoint(startDeg)
  const end = polarPoint(endDeg)
  return `M ${center} ${center} L ${start.x} ${start.y} A ${radius} ${radius} 0 0 0 ${end.x} ${end.y} Z`
}

function elevationPoint(angleDeg: number, distance = elevationRadius) {
  const rad = (angleDeg * Math.PI) / 180
  return {
    x: elevationOrigin.x + distance * Math.cos(rad),
    y: elevationOrigin.y - distance * Math.sin(rad),
  }
}

function elevationSectorPath(startDeg: number, endDeg: number) {
  const steps = 20
  const points = Array.from({ length: steps + 1 }, (_, idx) => {
    const angle = startDeg + ((endDeg - startDeg) * idx) / steps
    return elevationPoint(angle)
  })
  return [
    `M ${elevationOrigin.x} ${elevationOrigin.y}`,
    ...points.map((point, idx) => `${idx === 0 ? 'L' : 'L'} ${point.x} ${point.y}`),
    'Z',
  ].join(' ')
}

function orderedElevationGate(config: RadarDraftConfig) {
  const rawMin = Math.min(config.el_min_deg, config.el_max_deg)
  const rawMax = Math.max(config.el_min_deg, config.el_max_deg)
  const min = clamp(rawMin, elevationUiMin, elevationUiMax - minElevationSpan)
  const max = clamp(Math.max(rawMax, min + minElevationSpan), min + minElevationSpan, elevationUiMax)
  return { min, max }
}

function elevationGateFromCenter(centerDeg: number, spanDeg: number) {
  const span = clamp(spanDeg, minElevationSpan, elevationUiMax - elevationUiMin)
  const centerDegClamped = clamp(
    centerDeg,
    elevationUiMin + span / 2,
    elevationUiMax - span / 2,
  )
  return {
    center: centerDegClamped,
    min: centerDegClamped - span / 2,
    max: centerDegClamped + span / 2,
  }
}

function withElevationGate(config: RadarDraftConfig, minDeg: number, maxDeg: number) {
  const min = clamp(Math.min(minDeg, maxDeg), elevationUiMin, elevationUiMax - minElevationSpan)
  const max = clamp(Math.max(maxDeg, min + minElevationSpan), min + minElevationSpan, elevationUiMax)
  const centerDeg = (min + max) / 2
  return {
    ...withElevation(config, centerDeg),
    el_min_deg: min,
    el_max_deg: max,
  }
}

export function FovDragControl({
  config,
  onChange,
}: {
  config: RadarDraftConfig
  onChange: (next: RadarDraftConfig) => void
}) {
  const azSvgRef = useRef<SVGSVGElement | null>(null)
  const elSvgRef = useRef<SVGSVGElement | null>(null)
  const [dragging, setDragging] = useState<DragTarget>(null)
  const az = normalizeDeg(boresightAzimuthDeg(config))
  const elevationGate = orderedElevationGate(config)
  const elevationSpan = elevationGate.max - elevationGate.min
  const elevationCenter = (elevationGate.min + elevationGate.max) / 2
  const width = clamp(config.az_width_deg, 5, 180)
  const left = normalizeDeg(az - width / 2)
  const right = normalizeDeg(az + width / 2)
  const boresight = polarPoint(az, radius)
  const leftPoint = polarPoint(left, radius)
  const rightPoint = polarPoint(right, radius)
  const elevationBoresightPoint = elevationPoint(elevationCenter)
  const elevationMinPoint = elevationPoint(elevationGate.min)
  const elevationMaxPoint = elevationPoint(elevationGate.max)
  const arc = sectorPath(left, right)
  const elevationBackdropArc = elevationSectorPath(elevationUiMin, elevationUiMax)
  const elevationGateArc = elevationSectorPath(elevationGate.min, elevationGate.max)

  const setWidthFromEdge = (angle: number) => {
    const nextWidth = clamp(Math.abs(angleDeltaDeg(angle, az)) * 2, 5, 180)
    onChange({ ...config, az_width_deg: nextWidth })
  }

  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!dragging || !azSvgRef.current) return
    const angle = pointerAngle(event, azSvgRef.current)
    if (dragging === 'boresight') {
      onChange(withAzimuth(config, angle))
      return
    }
    if (dragging === 'left-edge' || dragging === 'right-edge') {
      setWidthFromEdge(angle)
    }
  }

  const handleElevationMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!dragging || !elSvgRef.current) return
    const angle = clamp(
      pointerAngleFromOrigin(event, elSvgRef.current, elevationOrigin.x, elevationOrigin.y),
      elevationUiMin,
      elevationUiMax,
    )
    if (dragging === 'elevation') {
      const nextGate = elevationGateFromCenter(angle, elevationSpan)
      onChange(withElevationGate(config, nextGate.min, nextGate.max))
      return
    }
    if (dragging === 'elevation-min') {
      onChange(withElevationGate(config, Math.min(angle, elevationGate.max - minElevationSpan), elevationGate.max))
      return
    }
    if (dragging === 'elevation-max') {
      onChange(withElevationGate(config, elevationGate.min, Math.max(angle, elevationGate.min + minElevationSpan)))
    }
  }

  const startDrag = (target: Exclude<DragTarget, null>, svgRef: React.RefObject<SVGSVGElement | null>) => (event: ReactPointerEvent<SVGElement>) => {
    event.preventDefault()
    setDragging(target)
    svgRef.current?.setPointerCapture(event.pointerId)
  }

  const stopDrag = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (dragging && event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    setDragging(null)
  }

  return (
    <div className="fov-drag-control">
      <svg
        ref={azSvgRef}
        viewBox="0 0 220 220"
        className="fov-dial"
        role="img"
        aria-label="雷达方位角与方位宽度拖动控制"
        onPointerMove={handlePointerMove}
        onPointerUp={stopDrag}
        onPointerCancel={stopDrag}
      >
        <circle className="fov-ring outer" cx={center} cy={center} r={radius} />
        <circle className="fov-ring inner" cx={center} cy={center} r={radius * 0.55} />
        <line className="fov-axis" x1={center - radius} y1={center} x2={center + radius} y2={center} />
        <line className="fov-axis" x1={center} y1={center - radius} x2={center} y2={center + radius} />
        <path className="fov-sector" d={arc} />
        <line className="fov-edge" x1={center} y1={center} x2={leftPoint.x} y2={leftPoint.y} />
        <line className="fov-edge" x1={center} y1={center} x2={rightPoint.x} y2={rightPoint.y} />
        <line className="fov-boresight" x1={center} y1={center} x2={boresight.x} y2={boresight.y} />
        <circle className="fov-center" cx={center} cy={center} r={5} />
        <circle className="fov-handle edge" cx={leftPoint.x} cy={leftPoint.y} r={7} onPointerDown={startDrag('left-edge', azSvgRef)}>
          <title>拖动以调整方位宽度</title>
        </circle>
        <circle className="fov-handle edge" cx={rightPoint.x} cy={rightPoint.y} r={7} onPointerDown={startDrag('right-edge', azSvgRef)}>
          <title>拖动以调整方位宽度</title>
        </circle>
        <circle className="fov-handle boresight" cx={boresight.x} cy={boresight.y} r={8} onPointerDown={startDrag('boresight', azSvgRef)}>
          <title>拖动以调整主视轴方位角</title>
        </circle>
      </svg>
      <svg
        ref={elSvgRef}
        viewBox="0 0 220 220"
        className="fov-dial"
        role="img"
        aria-label="雷达主视轴俯仰角拖动控制"
        onPointerMove={handleElevationMove}
        onPointerUp={stopDrag}
        onPointerCancel={stopDrag}
      >
        <line className="fov-axis" x1={elevationOrigin.x} y1={elevationOrigin.y} x2={elevationOrigin.x + elevationRadius + 20} y2={elevationOrigin.y} />
        <line className="fov-axis" x1={elevationOrigin.x} y1={elevationOrigin.y} x2={elevationOrigin.x} y2={elevationOrigin.y - elevationRadius - 12} />
        <path className="elevation-backdrop" d={elevationBackdropArc} />
        <path className="elevation-sector" d={elevationGateArc} />
        <line className="elevation-edge" x1={elevationOrigin.x} y1={elevationOrigin.y} x2={elevationMinPoint.x} y2={elevationMinPoint.y} />
        <line className="elevation-edge" x1={elevationOrigin.x} y1={elevationOrigin.y} x2={elevationMaxPoint.x} y2={elevationMaxPoint.y} />
        <line className="fov-boresight elevation" x1={elevationOrigin.x} y1={elevationOrigin.y} x2={elevationBoresightPoint.x} y2={elevationBoresightPoint.y} />
        <text className="dial-label" x={center} y={center + radius + 17} textAnchor="middle">俯仰</text>
        <circle className="fov-center" cx={elevationOrigin.x} cy={elevationOrigin.y} r={5} />
        <circle className="fov-handle elevation-edge" cx={elevationMinPoint.x} cy={elevationMinPoint.y} r={7} onPointerDown={startDrag('elevation-min', elSvgRef)}>
          <title>拖动以调整俯仰下界</title>
        </circle>
        <circle className="fov-handle elevation-edge" cx={elevationMaxPoint.x} cy={elevationMaxPoint.y} r={7} onPointerDown={startDrag('elevation-max', elSvgRef)}>
          <title>拖动以调整俯仰上界</title>
        </circle>
        <circle className="fov-handle elevation" cx={elevationBoresightPoint.x} cy={elevationBoresightPoint.y} r={8} onPointerDown={startDrag('elevation', elSvgRef)}>
          <title>拖动以调整主视轴俯仰角</title>
        </circle>
      </svg>
      <div className="fov-readout">
        <span>方位角 {formatDeg(az)}</span>
        <span>方位宽度 {formatDeg(width)}</span>
        <span>俯仰中心 {elevationCenter.toFixed(1)} 度</span>
        <span>俯仰下界 {formatDeg(elevationGate.min)}</span>
        <span>俯仰上界 {formatDeg(elevationGate.max)}</span>
      </div>
      <div className="range-stack">
        <label className="range-field">
          <span>方位角</span>
          <input type="range" min="-180" max="180" step="1" value={az} onChange={(event) => onChange(withAzimuth(config, Number(event.target.value)))} />
        </label>
        <label className="range-field">
          <span>方位宽度</span>
          <input type="range" min="5" max="180" step="1" value={width} onChange={(event) => onChange({ ...config, az_width_deg: Number(event.target.value) })} />
        </label>
        <label className="range-field">
          <span>俯仰中心</span>
          <input
            type="range"
            min={elevationUiMin + elevationSpan / 2}
            max={elevationUiMax - elevationSpan / 2}
            step="1"
            value={elevationCenter}
            onChange={(event) => {
              const nextGate = elevationGateFromCenter(Number(event.target.value), elevationSpan)
              onChange(withElevationGate(config, nextGate.min, nextGate.max))
            }}
          />
        </label>
        <label className="range-field">
          <span>俯仰下界</span>
          <input type="range" min={elevationUiMin} max={elevationGate.max - minElevationSpan} step="1" value={elevationGate.min} onChange={(event) => onChange({ ...config, el_min_deg: Number(event.target.value) })} />
        </label>
        <label className="range-field">
          <span>俯仰上界</span>
          <input type="range" min={elevationGate.min + minElevationSpan} max={elevationUiMax} step="1" value={elevationGate.max} onChange={(event) => onChange({ ...config, el_max_deg: Number(event.target.value) })} />
        </label>
        <label className="range-field">
          <span>最大距离</span>
          <input type="range" min="20" max="1000" step="10" value={clamp(config.rmax_m, 20, 1000)} onChange={(event) => onChange({ ...config, rmax_m: Number(event.target.value) })} />
        </label>
      </div>
    </div>
  )
}
