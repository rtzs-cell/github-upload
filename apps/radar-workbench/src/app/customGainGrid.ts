export type CustomGainGrid = {
  azimuth: number[]
  elevation: number[]
  gainDb: number[][]
  outsideGainDb: number
}

export type CustomGainGridValidation = {
  grid: CustomGainGrid | null
  error: string | null
}

export const DEFAULT_CUSTOM_GAIN_GRID = '{"azimuth_deg":[-60,0,60],"elevation_deg":[-20,0,20],"gain_db":[[-35,-15,-35],[-18,8,-18],[-35,-15,-35]],"outside_gain_db":-60}'

function finiteNumbers(value: unknown): number[] | null {
  if (!Array.isArray(value)) return null
  const numbers = value.map(Number)
  return numbers.every(Number.isFinite) ? numbers : null
}

function regularStep(values: number[]): number | null {
  const step = values[1] - values[0]
  if (!(step > 0)) return null
  for (let index = 2; index < values.length; index += 1) {
    const current = values[index] - values[index - 1]
    const tolerance = 1e-6 * Math.max(1, Math.abs(step), Math.abs(current))
    if (current <= 0 || Math.abs(current - step) > tolerance) return null
  }
  return step
}

export function validateCustomGainGrid(raw: string): CustomGainGridValidation {
  if (!raw.trim()) return { grid: null, error: '请输入增益网格 JSON。' }
  try {
    const value = JSON.parse(raw) as Record<string, unknown>
    if (!value || Array.isArray(value) || typeof value !== 'object') {
      return { grid: null, error: '顶层必须是 JSON 对象。' }
    }
    const azimuth = finiteNumbers(value.azimuth_deg)
    const elevation = finiteNumbers(value.elevation_deg)
    if (!azimuth || !elevation) return { grid: null, error: '方位角和俯仰角坐标必须是有限数值数组。' }
    if (azimuth.length < 2 || elevation.length < 2) return { grid: null, error: '方位角和俯仰角均至少需要两个采样点。' }
    if (azimuth.length > 721 || elevation.length > 361) return { grid: null, error: '网格上限为 721 个方位角点和 361 个俯仰角点。' }
    if (regularStep(azimuth) === null || regularStep(elevation) === null) {
      return { grid: null, error: '方位角和俯仰角坐标必须严格递增且等间隔。' }
    }
    if (!Array.isArray(value.gain_db) || value.gain_db.length !== elevation.length) {
      return { grid: null, error: `gain_db 必须包含 ${elevation.length} 行，对应全部俯仰角。` }
    }
    const gainDb = value.gain_db.map(finiteNumbers)
    if (gainDb.some((row) => row === null || row.length !== azimuth.length)) {
      return { grid: null, error: `gain_db 每行必须包含 ${azimuth.length} 项，对应全部方位角。` }
    }
    const outsideGainDb = Number(value.outside_gain_db ?? -80)
    if (!Number.isFinite(outsideGainDb)) return { grid: null, error: 'outside_gain_db 必须是有限数值。' }
    return {
      grid: { azimuth, elevation, gainDb: gainDb as number[][], outsideGainDb },
      error: null,
    }
  } catch {
    return { grid: null, error: 'JSON 语法无效。' }
  }
}

export function customGainDb(grid: CustomGainGrid, azimuthDeg: number, elevationDeg: number): number {
  const azimuthStep = grid.azimuth[1] - grid.azimuth[0]
  const elevationStep = grid.elevation[1] - grid.elevation[0]
  const x = (azimuthDeg - grid.azimuth[0]) / azimuthStep
  const y = (elevationDeg - grid.elevation[0]) / elevationStep
  if (x < 0 || y < 0 || x > grid.azimuth.length - 1 || y > grid.elevation.length - 1) return grid.outsideGainDb
  const x0 = Math.min(Math.floor(x), grid.azimuth.length - 2)
  const y0 = Math.min(Math.floor(y), grid.elevation.length - 2)
  const wx = x - x0
  const wy = y - y0
  return grid.gainDb[y0][x0] * (1 - wx) * (1 - wy)
    + grid.gainDb[y0][x0 + 1] * wx * (1 - wy)
    + grid.gainDb[y0 + 1][x0] * (1 - wx) * wy
    + grid.gainDb[y0 + 1][x0 + 1] * wx * wy
}
