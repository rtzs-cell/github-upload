import { Activity, BarChart3, Building2, Radio, Sigma } from 'lucide-react'
import type { ReactNode } from 'react'
import type { RunMetadata, RunSummary, SceneObject, SpectrumMetadata, TopPath } from '../api/types'

type SpectrumState = {
  metadata: SpectrumMetadata
  values: Float32Array
}

type BarItem = {
  label: string
  value: number
  color?: string
}

const pathKindLabels: Record<TopPath['kind'], string> = {
  specular: '镜面反射',
  diffuse: '漫反射',
  mixed: '混合反射',
  unknown: '未分类',
}

const pathKindColors: Record<TopPath['kind'], string> = {
  specular: '#1f78b4',
  diffuse: '#c46f22',
  mixed: '#7750a6',
  unknown: '#7c8b91',
}

function formatDb(value: number) {
  return `${(10 * Math.log10(Math.max(value, 1e-30))).toFixed(1)} dB`
}

function formatOptionalDb(value: number) {
  return value > 0 ? formatDb(value) : '无'
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

function formatNumber(value: number) {
  return Number.isFinite(value) ? value.toLocaleString('en-US') : '0'
}

function boresightLabel(value: string) {
  if (value === 'BposX') return '主视轴 X'
  if (value === 'BposY') return '主视轴 Y'
  return value
}

function MetricTile({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="metric-tile">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <em>{detail}</em>}
    </div>
  )
}

function PanelTitle({ icon, title, note }: { icon: ReactNode; title: string; note?: string }) {
  return (
    <div className="analysis-title">
      <div>
        {icon}
        <span>{title}</span>
      </div>
      {note && <small>{note}</small>}
    </div>
  )
}

function BarChart({ items, valueFormatter = formatNumber }: { items: BarItem[]; valueFormatter?: (value: number) => string }) {
  const max = Math.max(...items.map((item) => item.value), 1e-30)
  return (
    <div className="bar-chart">
      {items.map((item, index) => (
        <div className="bar-row" key={`${item.label}-${index}`}>
          <span>{item.label}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${Math.max(2, (item.value / max) * 100)}%`, background: item.color ?? '#0d6d5f' }} />
          </div>
          <em>{valueFormatter(item.value)}</em>
        </div>
      ))}
    </div>
  )
}

function LineChart({ values }: { values: number[] }) {
  const width = 420
  const height = 130
  const max = Math.max(...values, 1e-30)
  const points = values
    .map((value, idx) => {
      const x = values.length <= 1 ? 0 : (idx / (values.length - 1)) * width
      const y = height - (value / max) * (height - 10) - 5
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
  return (
    <svg className="line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="距离像曲线">
      <polyline points={points} />
    </svg>
  )
}

function CdfChart({ values }: { values: number[] }) {
  const sorted = values.filter((value) => value > 0).sort((a, b) => b - a)
  const total = sorted.reduce((sum, value) => sum + value, 0) || 1
  let cumulative = 0
  const cdf = sorted.map((value) => {
    cumulative += value
    return cumulative / total
  })
  const width = 420
  const height = 130
  const points = cdf
    .map((value, idx) => {
      const x = cdf.length <= 1 ? 0 : (idx / (cdf.length - 1)) * width
      const y = height - value * (height - 10) - 5
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
  return (
    <svg className="line-chart cdf-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="累计能量曲线">
      <polyline points={points} />
    </svg>
  )
}

function rangeProfile(spectrum: SpectrumState | null) {
  if (!spectrum) return { values: [], peakRangeM: 0 }
  const [rows, cols] = spectrum.metadata.shape
  const values: number[] = []
  let peakIndex = 0
  let peakValue = 0
  for (let row = 0; row < rows; row += 1) {
    let sum = 0
    for (let col = 0; col < cols; col += 1) sum += spectrum.values[row * cols + col]
    values.push(sum)
    if (sum > peakValue) {
      peakValue = sum
      peakIndex = row
    }
  }
  const stride = Math.max(1, Math.ceil(values.length / 160))
  const sampled = values.filter((_, idx) => idx % stride === 0)
  return {
    values: sampled,
    peakRangeM: spectrum.metadata.range_edges_m[Math.min(peakIndex, spectrum.metadata.range_edges_m.length - 1)] ?? 0,
  }
}

function histogram(values: number[], binCount: number, minValue?: number, maxValue?: number): BarItem[] {
  if (!values.length) return []
  const min = minValue ?? Math.min(...values)
  const max = maxValue ?? Math.max(...values)
  const width = Math.max((max - min) / binCount, 1e-9)
  const bins = Array.from({ length: binCount }, (_, idx) => ({
    start: min + idx * width,
    end: min + (idx + 1) * width,
    count: 0,
  }))
  for (const value of values) {
    const idx = Math.max(0, Math.min(binCount - 1, Math.floor((value - min) / width)))
    bins[idx].count += 1
  }
  return bins.map((bin) => ({
    label: `${bin.start.toFixed(0)}-${bin.end.toFixed(0)}`,
    value: bin.count,
  }))
}

function objectEnergy(paths: TopPath[], objects: SceneObject[]) {
  const labels = new Map(objects.map((object) => [
    object.object_id,
    object.display_name ?? object.object_id.replace(/^mesh-/, '').replace(/[_-]+/g, ' '),
  ]))
  const energy = new Map<string, number>()
  for (const path of paths) {
    const objectIds = Array.from(
      new Set(path.interactions.map((interaction) => interaction.object_id).filter((id): id is string => Boolean(id))),
    )
    if (!objectIds.length) continue
    const share = path.energy / objectIds.length
    for (const objectId of objectIds) {
      energy.set(objectId, (energy.get(objectId) ?? 0) + share)
    }
  }
  return Array.from(energy.entries())
    .map(([objectId, value]) => ({ label: labels.get(objectId) ?? objectId, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8)
}

export function RadarStatisticsPanel({
  selectedRun,
  metadata,
  paths,
  objects,
  rangeAzimuth,
  runs,
}: {
  selectedRun: RunSummary | null
  metadata: RunMetadata | null
  paths: TopPath[]
  objects: SceneObject[]
  rangeAzimuth: SpectrumState | null
  runs: RunSummary[]
}) {
  const observation = metadata?.metrics?.radar_observation ?? {}
  const pathSummary = metadata?.metrics?.path_summary ?? {}
  const profile = rangeProfile(rangeAzimuth)
  const energyTotal = Number(observation.energy_total ?? 0)
  const energyInFov = Number(observation.energy_in_fov ?? 0)
  const fovEnergyFraction = Number(observation.energy_fraction_in_fov ?? selectedRun?.fov_energy_fraction ?? 0)
  const totalPathCount = Number(observation.path_count_total ?? selectedRun?.valid_path_count ?? 0)
  const fovPathCount = Number(observation.path_count_in_fov ?? 0)
  const dominantRange = Number(pathSummary.dominant_range_m ?? selectedRun?.dominant_range_m ?? 0)
  const maxDepth = Number(pathSummary.max_interaction_depth ?? selectedRun?.max_interaction_depth ?? 0)

  const energyByKind = (Object.keys(pathKindLabels) as TopPath['kind'][]).map((kind) => ({
    label: pathKindLabels[kind],
    value: paths.filter((path) => path.kind === kind).reduce((sum, path) => sum + path.energy, 0),
    color: pathKindColors[kind],
  }))
  const countByDepth = Array.from(
    paths.reduce((counts, path) => counts.set(path.depth, (counts.get(path.depth) ?? 0) + 1), new Map<number, number>()),
  )
    .sort(([a], [b]) => a - b)
    .map(([depth, value]) => ({ label: `${depth} 次交互`, value }))
  const rangeBins = histogram(paths.map((path) => path.range_m), 8, 0, selectedRun?.range_max_m || undefined)
  const azimuthBins = histogram(paths.map((path) => path.aoa_azimuth_deg), 8, -180, 180)
  const objectBars = objectEnergy(paths, objects)
  const campaignBars = runs
    .slice()
    .sort((a, b) => b.fov_energy_fraction - a.fov_energy_fraction)
    .slice(0, 10)
    .map((run, index) => ({
      label: `测点 ${index + 1} · ${boresightLabel(run.boresight_id)}`,
      value: run.fov_energy_fraction,
      color: run.run_id === selectedRun?.run_id ? '#0d6d5f' : '#71939a',
    }))

  return (
    <section className="statistics-section">
      <div className="section-heading-large">
        <Activity size={18} />
        <div>
          <strong>雷达统计分析</strong>
          <span>基于当前测量记录、主要传播路径和距离-角度谱</span>
        </div>
      </div>
      <div className="metrics-grid radar-metrics">
        <MetricTile label="有效路径总数" value={formatNumber(totalPathCount)} detail={`分析范围内 ${formatNumber(fovPathCount)}`} />
        <MetricTile label="分析范围内能量占比" value={formatPercent(fovEnergyFraction)} detail={`能量 ${formatDb(energyInFov)}`} />
        <MetricTile label="主峰距离" value={`${dominantRange.toFixed(2)} m`} detail={`距离像峰值 ${profile.peakRangeM.toFixed(2)} m`} />
        <MetricTile label="最大交互阶数" value={`${maxDepth.toFixed(0)} 次`} detail={`总能量 ${formatDb(energyTotal)}`} />
      </div>

      <div className="analysis-grid">
        <div className="analysis-panel wide">
          <PanelTitle icon={<Radio size={15} />} title="距离像" note="距离维功率积分" />
          <LineChart values={profile.values} />
          <div className="chart-caption">横轴为距离采样点，纵轴为归一化回波功率。</div>
        </div>
        <div className="analysis-panel">
          <PanelTitle icon={<BarChart3 size={15} />} title="传播机制能量占比" note="主要路径集合" />
          <BarChart items={energyByKind} valueFormatter={formatOptionalDb} />
        </div>
        <div className="analysis-panel">
          <PanelTitle icon={<BarChart3 size={15} />} title="交互阶数分布" note="路径数量" />
          <BarChart items={countByDepth} />
        </div>
        <div className="analysis-panel">
          <PanelTitle icon={<BarChart3 size={15} />} title="路径距离分布" note="单位：m" />
          <BarChart items={rangeBins} />
        </div>
        <div className="analysis-panel">
          <PanelTitle icon={<BarChart3 size={15} />} title="到达方位角分布" note="单位：度" />
          <BarChart items={azimuthBins} />
        </div>
        <div className="analysis-panel">
          <PanelTitle icon={<Building2 size={15} />} title="建筑物回波能量贡献" note="按路径能量分摊" />
          <BarChart items={objectBars} valueFormatter={formatOptionalDb} />
        </div>
        <div className="analysis-panel wide">
          <PanelTitle icon={<Sigma size={15} />} title="累计能量曲线" note="强路径排序后的累计贡献" />
          <CdfChart values={paths.map((path) => path.energy)} />
          <div className="chart-caption">曲线上升越快，说明少数强路径主导回波能量。</div>
        </div>
        <div className="analysis-panel wide">
          <PanelTitle icon={<BarChart3 size={15} />} title="多次测量分析范围内能量占比" note="当前记录以蓝色标记" />
          <BarChart items={campaignBars} valueFormatter={(value) => `${(value * 100).toFixed(1)}%`} />
        </div>
      </div>
    </section>
  )
}
