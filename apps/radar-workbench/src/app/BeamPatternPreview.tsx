import { useEffect, useRef, useState } from 'react'
import { RadioTower, ScanSearch } from 'lucide-react'
import type { RadarDraftConfig } from '../api/types'
import { customGainDb, validateCustomGainGrid } from './customGainGrid'
import type { CustomGainGrid } from './customGainGrid'

type Complex = { re: number; im: number }
type Peak = { az: number; el: number; beamwidthAz: number }
type ElementOrder = 'row-major' | 'column-major'
type ElementPattern = 'custom_gain_grid' | 'tr38901' | 'isotropic'

function normalize(weights: Complex[]): Complex[] {
  const norm = Math.sqrt(weights.reduce((sum, item) => sum + item.re ** 2 + item.im ** 2, 0)) || 1
  return weights.map((item) => ({ re: item.re / norm, im: item.im / norm }))
}

function parseCustomWeights(raw: string, count: number): Complex[] | null {
  try {
    const values = JSON.parse(raw) as unknown[]
    if (!Array.isArray(values) || values.length !== count) return null
    return normalize(values.map((item) => {
      if (typeof item === 'number') return { re: item, im: 0 }
      if (Array.isArray(item)) return { re: Number(item[0] ?? 0), im: Number(item[1] ?? 0) }
      const value = item as { re?: number; im?: number }
      return { re: Number(value.re ?? 0), im: Number(value.im ?? 0) }
    }))
  } catch {
    return null
  }
}

function elementIndex(row: number, col: number, rows: number, cols: number, order: ElementOrder): number {
  return order === 'column-major' ? col * rows + row : row * cols + col
}

function arrayWeights(
  rows: number,
  cols: number,
  azDeg: number,
  elDeg: number,
  side: 'tx' | 'rx',
  taper = 'uniform',
  order: ElementOrder = 'row-major',
): Complex[] {
  const az = azDeg * Math.PI / 180
  const el = elDeg * Math.PI / 180
  const values: Complex[] = Array.from({ length: rows * cols }, () => ({ re: 0, im: 0 }))
  for (let row = 0; row < rows; row += 1) {
    const z = ((rows - 1) / 2 - row) * 0.5
    const rowTaper = taper === 'hann' ? Math.sin(Math.PI * (row + 1) / (rows + 1)) ** 2 : 1
    for (let col = 0; col < cols; col += 1) {
      const y = (col - (cols - 1) / 2) * 0.5
      const colTaper = taper === 'hann' ? Math.sin(Math.PI * (col + 1) / (cols + 1)) ** 2 : 1
      const phase = (side === 'tx' ? -1 : 1) * 2 * Math.PI * (y * Math.sin(az) * Math.cos(el) + z * Math.sin(el))
      const amplitude = rowTaper * colTaper
      values[elementIndex(row, col, rows, cols, order)] = {
        re: amplitude * Math.cos(phase),
        im: amplitude * Math.sin(phase),
      }
    }
  }
  return normalize(values)
}

function colorMap(value: number): [number, number, number] {
  const t = Math.max(0, Math.min(1, value))
  return [
    Math.round(22 + 232 * Math.pow(t, 0.72)),
    Math.round(30 + 130 * Math.max(0, 1 - Math.abs(t - 0.7) * 2.4)),
    Math.round(56 + 145 * (1 - t)),
  ]
}

function elementPower(pattern: ElementPattern, azDeg: number, elDeg: number, customGrid: CustomGainGrid | null): number {
  if (pattern === 'isotropic') return 1
  if (pattern === 'custom_gain_grid') return customGrid ? 10 ** (customGainDb(customGrid, azDeg, elDeg) / 10) : 0
  const av = -Math.min(12 * (elDeg / 65) ** 2, 30)
  const ah = -Math.min(12 * (azDeg / 65) ** 2, 30)
  return 10 ** ((-Math.min(-(av + ah), 30) + 8) / 10)
}

function drawResponse(
  canvas: HTMLCanvasElement,
  rows: number,
  cols: number,
  weights: Complex[],
  side: 'tx' | 'rx',
  pattern: ElementPattern,
  order: ElementOrder,
  customGrid: CustomGainGrid | null = null,
): Peak {
  const width = 181
  const height = 91
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  const image = context?.createImageData(width, height)
  if (!context || !image) return { az: 0, el: 0, beamwidthAz: 0 }
  const gains = new Float64Array(width * height)
  let maxGain = 0
  let peakIndex = 0
  for (let py = 0; py < height; py += 1) {
    const elDeg = -45 + py
    const el = elDeg * Math.PI / 180
    for (let px = 0; px < width; px += 1) {
      const azDeg = -90 + px
      const az = azDeg * Math.PI / 180
      let sumRe = 0
      let sumIm = 0
      for (let row = 0; row < rows; row += 1) {
        const z = ((rows - 1) / 2 - row) * 0.5
        for (let col = 0; col < cols; col += 1) {
          const y = (col - (cols - 1) / 2) * 0.5
          const phase = 2 * Math.PI * (y * Math.sin(az) * Math.cos(el) + z * Math.sin(el))
          const responseRe = Math.cos(phase)
          const responseIm = Math.sin(phase)
          const weight = weights[elementIndex(row, col, rows, cols, order)]
          const weightIm = side === 'rx' ? -weight.im : weight.im
          sumRe += responseRe * weight.re - responseIm * weightIm
          sumIm += responseIm * weight.re + responseRe * weightIm
        }
      }
      const gain = (sumRe ** 2 + sumIm ** 2) * elementPower(pattern, azDeg, elDeg, customGrid)
      const offset = py * width + px
      gains[offset] = gain
      if (gain > maxGain) {
        maxGain = gain
        peakIndex = offset
      }
    }
  }
  for (let index = 0; index < gains.length; index += 1) {
    const relativeDb = 10 * Math.log10(Math.max(gains[index] / Math.max(maxGain, 1e-30), 1e-4))
    const [r, g, b] = colorMap((relativeDb + 40) / 40)
    image.data[index * 4] = r
    image.data[index * 4 + 1] = g
    image.data[index * 4 + 2] = b
    image.data[index * 4 + 3] = 255
  }
  context.putImageData(image, 0, 0)
  const peakRow = Math.floor(peakIndex / width)
  const peakCol = peakIndex % width
  const cut = gains.slice(peakRow * width, (peakRow + 1) * width)
  let left = peakCol
  let right = peakCol
  while (left > 0 && cut[left] >= maxGain / 2) left -= 1
  while (right < width - 1 && cut[right] >= maxGain / 2) right += 1
  return { az: peakCol - 90, el: peakRow - 45, beamwidthAz: Math.max(0, right - left) }
}

function drawCustomResponse(canvas: HTMLCanvasElement, grid: CustomGainGrid): Peak {
  const width = 181
  const height = 91
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  const image = context?.createImageData(width, height)
  if (!context || !image) return { az: 0, el: 0, beamwidthAz: 0 }
  const gains = new Float64Array(width * height)
  let maxGain = 0
  let peakIndex = 0
  for (let py = 0; py < height; py += 1) {
    for (let px = 0; px < width; px += 1) {
      const gain = 10 ** (customGainDb(grid, px - 90, py - 45) / 10)
      const offset = py * width + px
      gains[offset] = gain
      if (gain > maxGain) {
        maxGain = gain
        peakIndex = offset
      }
    }
  }
  for (let index = 0; index < gains.length; index += 1) {
    const relativeDb = 10 * Math.log10(Math.max(gains[index] / Math.max(maxGain, 1e-30), 1e-4))
    const [r, g, b] = colorMap((relativeDb + 40) / 40)
    image.data[index * 4] = r
    image.data[index * 4 + 1] = g
    image.data[index * 4 + 2] = b
    image.data[index * 4 + 3] = 255
  }
  context.putImageData(image, 0, 0)
  const peakRow = Math.floor(peakIndex / width)
  const peakCol = peakIndex % width
  const cut = gains.slice(peakRow * width, (peakRow + 1) * width)
  let left = peakCol
  let right = peakCol
  while (left > 0 && cut[left] >= maxGain / 2) left -= 1
  while (right < width - 1 && cut[right] >= maxGain / 2) right += 1
  return { az: peakCol - 90, el: peakRow - 45, beamwidthAz: Math.max(0, right - left) }
}

function clearResponse(canvas: HTMLCanvasElement) {
  canvas.width = 181
  canvas.height = 91
  const context = canvas.getContext('2d')
  if (!context) return
  context.fillStyle = '#171b2b'
  context.fillRect(0, 0, canvas.width, canvas.height)
}

export function BeamPatternPreview({ config, side }: { config: RadarDraftConfig; side: 'tx' | 'rx' }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [peak, setPeak] = useState<Peak>({ az: 0, el: 0, beamwidthAz: 0 })
  const [valid, setValid] = useState(true)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    if (side === 'tx') {
      const rows = Math.max(1, config.tx_rows)
      const cols = Math.max(1, config.tx_cols)
      if (config.tx_pattern === 'custom_gain_grid') {
        const customGrid = validateCustomGainGrid(config.tx_custom_gain_json).grid
        if (!customGrid) {
          clearResponse(canvas)
          setValid(false)
          return
        }
        setPeak(drawCustomResponse(canvas, customGrid))
        setValid(true)
        return
      }
      const elementPattern: ElementPattern = config.tx_pattern === 'radar_array'
        ? config.tx_element_pattern
        : config.tx_pattern === 'tr38901' ? 'tr38901' : 'isotropic'
      const elementGrid = elementPattern === 'custom_gain_grid'
        ? validateCustomGainGrid(config.tx_element_custom_gain_json).grid
        : null
      if (elementPattern === 'custom_gain_grid' && !elementGrid) {
        clearResponse(canvas)
        setValid(false)
        return
      }
      const customWeights = config.tx_beamforming_mode === 'custom_complex_weights'
        ? parseCustomWeights(config.tx_custom_weights_json, rows * cols)
        : null
      if (config.tx_beamforming_mode === 'custom_complex_weights' && !customWeights) {
        clearResponse(canvas)
        setValid(false)
        return
      }
      const order: ElementOrder = config.tx_pattern === 'radar_array' ? 'row-major' : 'column-major'
      const weights = customWeights ?? arrayWeights(
        rows,
        cols,
        config.tx_steering_azimuth_deg,
        config.tx_steering_elevation_deg,
        'tx',
        config.tx_taper,
        order,
      )
      setPeak(drawResponse(canvas, rows, cols, weights, 'tx', elementPattern, order, elementGrid))
      setValid(true)
      return
    }

    const rows = Math.max(1, config.rx_rows)
    const cols = Math.max(1, config.rx_cols)
    const custom = config.beamforming_rx_mode === 'custom_complex_weights'
      ? parseCustomWeights(config.beamforming_custom_weights_json, rows * cols)
      : null
    if (config.beamforming_rx_mode === 'custom_complex_weights' && !custom) {
      clearResponse(canvas)
      setValid(false)
      return
    }
    const weights = custom ?? arrayWeights(
      rows,
      cols,
      config.beamforming_rx_mode === 'steering_vector' ? config.beamforming_steering_azimuth_deg : 0,
      config.beamforming_rx_mode === 'steering_vector' ? config.beamforming_steering_elevation_deg : 0,
      'rx',
      'uniform',
      'column-major',
    )
    const customGrid = config.rx_pattern === 'custom_gain_grid'
      ? validateCustomGainGrid(config.rx_custom_gain_json).grid
      : null
    if (config.rx_pattern === 'custom_gain_grid' && !customGrid) {
      clearResponse(canvas)
      setValid(false)
      return
    }
    setPeak(drawResponse(canvas, rows, cols, weights, 'rx', config.rx_pattern, 'column-major', customGrid))
    setValid(true)
  }, [config, side])

  const isTx = side === 'tx'
  const rows = isTx ? config.tx_rows : config.rx_rows
  const cols = isTx ? config.tx_cols : config.rx_cols

  return (
    <div className="beam-preview">
      <div className="beam-preview-panel response">
        <div className="beam-preview-title">{isTx ? <RadioTower size={14} /> : <ScanSearch size={14} />}{isTx ? '发射阵列方向图' : '接收波束响应'}</div>
        <canvas ref={canvasRef} aria-label={isTx ? '发射阵列方向图预览' : '接收阵列方向图预览'} />
        <div className="beam-preview-axis"><span>{rows} x {cols}</span><strong>{valid ? `${peak.az}° / ${peak.el}° · 3dB ${peak.beamwidthAz}°` : '权重或方向图格式无效'}</strong></div>
      </div>
    </div>
  )
}
