import { Check, CircleDot, Route } from 'lucide-react'
import type { SceneObject, TopPath } from '../api/types'

export type PathKindFilter = 'all' | TopPath['kind']

const kindLabels: Record<TopPath['kind'], string> = {
  specular: '镜面反射',
  diffuse: '漫反射',
  mixed: '混合路径',
  unknown: '未分类',
}

function formatDb(value: number) {
  return `${(10 * Math.log10(Math.max(value, 1e-30))).toFixed(2)} dB`
}

function formatAngle(value: number | null | undefined) {
  return Number.isFinite(value) ? `${Number(value).toFixed(2)}°` : '无'
}

export function PathInspector({
  paths,
  filteredPaths,
  selectedPath,
  kindFilter,
  gateOnly,
  onKindFilterChange,
  onGateOnlyChange,
  onSelect,
  objects,
}: {
  paths: TopPath[]
  filteredPaths: TopPath[]
  selectedPath: TopPath | null
  kindFilter: PathKindFilter
  gateOnly: boolean
  onKindFilterChange: (value: PathKindFilter) => void
  onGateOnlyChange: (value: boolean) => void
  onSelect: (pathId: number) => void
  objects: SceneObject[]
}) {
  const objectLabels = new Map(objects.map((object) => [
    object.object_id,
    object.display_name ?? object.object_id.replace(/^mesh-/, '').replace(/[_-]+/g, ' '),
  ]))
  return (
    <div className="path-inspector">
      <div className="path-filter-grid">
        <label className="field">
          <span>传播类型</span>
          <select value={kindFilter} onChange={(event) => onKindFilterChange(event.target.value as PathKindFilter)}>
            <option value="all">全部类型</option>
            <option value="specular">镜面反射</option>
            <option value="diffuse">漫反射</option>
            <option value="mixed">混合路径</option>
            <option value="unknown">未分类</option>
          </select>
        </label>
        <label className="toggle-field path-gate-toggle">
          <input type="checkbox" checked={gateOnly} onChange={(event) => onGateOnlyChange(event.target.checked)} />
          <span>仅显示分析范围内路径</span>
        </label>
      </div>

      <div className="path-result-count">
        <span>已载入 {paths.length.toLocaleString()} 条</span>
        <strong>当前匹配 {filteredPaths.length.toLocaleString()} 条</strong>
      </div>

      <div className="path-browser" role="listbox" aria-label="传播路径列表">
        {filteredPaths.slice(0, 200).map((path) => (
          <button
            type="button"
            role="option"
            aria-selected={selectedPath?.path_id === path.path_id}
            className={`path-browser-row ${selectedPath?.path_id === path.path_id ? 'selected' : ''}`}
            key={path.path_id}
            onClick={() => onSelect(path.path_id)}
          >
            <span className="path-id">#{path.path_id}</span>
            <span className={`path-kind ${path.kind}`}>{kindLabels[path.kind]}</span>
            <strong>{path.range_m.toFixed(2)} m</strong>
            <em>{formatDb(path.energy)}</em>
            {path.in_fov && <Check size={13} aria-label="分析范围内" />}
          </button>
        ))}
      </div>

      {selectedPath ? (
        <div className="path-detail">
          <div className="path-detail-heading">
            <div><Route size={16} /><strong>路径 #{selectedPath.path_id}</strong></div>
            <span className={`path-kind ${selectedPath.kind}`}>{kindLabels[selectedPath.kind]}</span>
          </div>
          <dl className="path-detail-grid">
            <div><dt>等效单站距离</dt><dd>{selectedPath.range_m.toFixed(4)} m</dd></div>
            <div><dt>传播时延</dt><dd>{(selectedPath.delay_s * 1e9).toFixed(3)} ns</dd></div>
            <div><dt>路径能量</dt><dd>{formatDb(selectedPath.energy)}</dd></div>
            <div><dt>交互阶数</dt><dd>{selectedPath.depth}</dd></div>
            <div><dt>离开角（AoD）方位 / 俯仰</dt><dd>{formatAngle(selectedPath.aod_azimuth_deg)} / {formatAngle(selectedPath.aod_elevation_deg)}</dd></div>
            <div><dt>到达角（AoA）方位 / 俯仰</dt><dd>{formatAngle(selectedPath.aoa_azimuth_deg)} / {formatAngle(selectedPath.aoa_elevation_deg)}</dd></div>
            <div><dt>距离 / 方位 / 俯仰单元</dt><dd>{selectedPath.range_bin_idx ?? '-'} / {selectedPath.azimuth_bin_idx ?? '-'} / {selectedPath.elevation_bin_idx ?? '-'}</dd></div>
            <div><dt>分析范围</dt><dd>{selectedPath.in_fov ? '范围内' : '范围外'}</dd></div>
          </dl>
          <div className="path-sequence-title"><CircleDot size={14} />交互序列</div>
          <div className="interaction-sequence">
            {selectedPath.interactions.length ? selectedPath.interactions.map((interaction, index) => (
              <div className="interaction-step" key={`${selectedPath.path_id}-${interaction.depth_index}`}>
                <span>{index + 1}</span>
                <div>
                  <strong>{interaction.type === 'diffuse' ? '漫反射' : interaction.type === 'specular' ? '镜面反射' : interaction.type}</strong>
                  <em>{interaction.object_id ? objectLabels.get(interaction.object_id) ?? interaction.object_id.replace(/^mesh-/, '').replace(/[_-]+/g, ' ') : '未识别对象'}</em>
                  <small>
                    ({interaction.position_m.map((value) => value.toFixed(3)).join(', ')}) m
                  </small>
                </div>
              </div>
            )) : <div className="empty-panel">该路径没有场景交互点</div>}
          </div>
        </div>
      ) : (
        <div className="empty-panel">选择一条路径查看完整传播参数</div>
      )}
    </div>
  )
}
