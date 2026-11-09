import { ChevronDown, Play, Redo2, RefreshCw, RotateCcw, Save, Undo2, Wifi } from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import type { RadarDraftConfig, SimulationStatus } from '../api/types'
import { BeamPatternPreview } from './BeamPatternPreview'
import { DEFAULT_CUSTOM_GAIN_GRID, validateCustomGainGrid } from './customGainGrid'
import { FovDragControl } from './FovDragControl'
import { boresightAzimuthDeg, boresightElevationDeg, withAzimuth, withElevation } from './radarConfig'

function defaultComplexWeights(count: number) {
  return JSON.stringify(Array.from({ length: Math.max(1, count) }, () => [1, 0]))
}

function NumberField({
  label,
  value,
  step = 1,
  onChange,
}: {
  label: string
  value: number
  step?: number
  onChange: (value: number) => void
}) {
  const displayValue = Number.isFinite(value)
    ? Math.abs(value) > 0 && Math.abs(value) < 0.001
      ? value.toExponential(3)
      : Number(value.toFixed(step < 0.1 ? 6 : 3))
    : 0
  return (
    <label className="field">
      <span>{label}</span>
      <input type="number" value={displayValue} step={step} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  )
}

function ToggleField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="toggle-field">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>{label}</span>
    </label>
  )
}

function EditorSection({ title, defaultOpen = false, children }: { title: string; defaultOpen?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className={`editor-section ${open ? 'open' : ''}`}>
      <button type="button" className="editor-section-toggle" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <span>{title}</span>
        <ChevronDown size={16} />
      </button>
      {open && <div className="editor-section-body">{children}</div>}
    </section>
  )
}

export function RadarEditor({
  config,
  baseline,
  status,
  sourceLabel,
  onChange,
  onReset,
  onSaveConfig,
  onSavePaths,
  onSubmit,
  savingPaths = false,
  savingConfig = false,
  canUndo = false,
  canRedo = false,
  onUndo,
  onRedo,
}: {
  config: RadarDraftConfig
  baseline: RadarDraftConfig | null
  status: SimulationStatus
  sourceLabel: string
  onChange: (next: RadarDraftConfig) => void
  onReset: () => void
  onSaveConfig?: () => void
  onSavePaths?: () => void
  onSubmit: () => void
  savingPaths?: boolean
  savingConfig?: boolean
  canUndo?: boolean
  canRedo?: boolean
  onUndo?: () => void
  onRedo?: () => void
}) {
  const update = <K extends keyof RadarDraftConfig>(key: K, value: RadarDraftConfig[K]) => {
    onChange({ ...config, [key]: value })
  }
  const updateVector = (key: 'center_m' | 'look_at_m', idx: number, value: number) => {
    const next = [...config[key]] as [number, number, number]
    next[idx] = value
    update(key, next)
  }
  const changed = baseline ? JSON.stringify(config) !== JSON.stringify(baseline) : false
  const running = status === 'running' || status === 'queued'
  const az = boresightAzimuthDeg(config)
  const el = boresightElevationDeg(config)
  const txTotalGainValidation = config.tx_pattern === 'custom_gain_grid' ? validateCustomGainGrid(config.tx_custom_gain_json) : null
  const txElementGainValidation = config.tx_pattern === 'radar_array' && config.tx_element_pattern === 'custom_gain_grid'
    ? validateCustomGainGrid(config.tx_element_custom_gain_json)
    : null
  const rxGainValidation = config.rx_pattern === 'custom_gain_grid' ? validateCustomGainGrid(config.rx_custom_gain_json) : null
  const gainGridError = txTotalGainValidation?.error ?? txElementGainValidation?.error ?? rxGainValidation?.error ?? null
  return (
    <div className="editor-stack">
      <div className={`simulation-state ${changed ? 'changed' : 'synced'}`}>
        <Wifi size={15} />
        <span>{changed ? `${sourceLabel} · 已修改` : sourceLabel}</span>
      </div>

      <EditorSection title="雷达位姿" defaultOpen>
        <div className="field-grid three">
          {['X', 'Y', 'Z'].map((axis, idx) => (
            <NumberField key={axis} label={`雷达 ${axis} 坐标（m）`} value={config.center_m[idx]} step={0.5} onChange={(v) => updateVector('center_m', idx, v)} />
          ))}
          {['X', 'Y', 'Z'].map((axis, idx) => (
            <NumberField key={`look-${axis}`} label={`指向点 ${axis} 坐标（m）`} value={config.look_at_m[idx]} step={0.5} onChange={(v) => updateVector('look_at_m', idx, v)} />
          ))}
        </div>
        <div className="field-grid two">
          <NumberField label="方位角（°）" value={az} step={1} onChange={(v) => onChange(withAzimuth(config, v))} />
          <NumberField label="俯仰角（°）" value={el} step={1} onChange={(v) => onChange(withElevation(config, v))} />
        </div>
      </EditorSection>

      <EditorSection title="方位、俯仰与距离分析范围" defaultOpen>
        <FovDragControl config={config} onChange={onChange} />
        <div className="field-grid two">
          <NumberField label="方位宽度 度" value={config.az_width_deg} onChange={(v) => update('az_width_deg', v)} />
          <NumberField label="最大距离 m" value={config.rmax_m} onChange={(v) => update('rmax_m', v)} />
          <NumberField label="最小俯仰角 度" value={config.el_min_deg} onChange={(v) => update('el_min_deg', v)} />
          <NumberField label="最大俯仰角 度" value={config.el_max_deg} onChange={(v) => update('el_max_deg', v)} />
        </div>
      </EditorSection>

      <EditorSection title="发射阵列与 FMCW 波形" defaultOpen>
        <div className="preset-row">
          {[28e9, 60e9, 77e9].map((freq) => (
            <button key={freq} type="button" className={config.frequency_hz === freq ? 'preset active' : 'preset'} onClick={() => update('frequency_hz', freq)}>
              {freq / 1e9} GHz
            </button>
          ))}
        </div>
        <div className="field-grid two">
          <NumberField label="发射功率 dBm" value={config.tx_power_dbm} step={1} onChange={(v) => update('tx_power_dbm', v)} />
          <NumberField label="带宽 GHz" value={config.bandwidth_hz / 1e9} step={0.1} onChange={(v) => update('bandwidth_hz', v * 1e9)} />
          <label className="field field-wide">
            <span>发射方向图实现</span>
            <select value={config.tx_pattern} onChange={(event) => {
              const pattern = event.target.value as RadarDraftConfig['tx_pattern']
              onChange({
                ...config,
                tx_pattern: pattern,
                tx_custom_gain_json: pattern === 'custom_gain_grid' && !config.tx_custom_gain_json.trim() ? DEFAULT_CUSTOM_GAIN_GRID : config.tx_custom_gain_json,
              })
            }}>
              <option value="radar_array">相控阵孔径</option>
              <option value="custom_gain_grid">自定义总增益（等效 1×1）</option>
              <option value="tr38901">逐阵元 3GPP</option>
              <option value="isotropic">逐阵元各向同性</option>
            </select>
          </label>
          {config.tx_pattern === 'radar_array' && (
            <label className="field field-wide">
              <span>发射单元因子</span>
              <select value={config.tx_element_pattern} onChange={(event) => {
                const pattern = event.target.value as RadarDraftConfig['tx_element_pattern']
                onChange({
                  ...config,
                  tx_element_pattern: pattern,
                  tx_element_custom_gain_json: pattern === 'custom_gain_grid' && !config.tx_element_custom_gain_json.trim()
                    ? DEFAULT_CUSTOM_GAIN_GRID
                    : config.tx_element_custom_gain_json,
                })
              }}>
                <option value="isotropic">各向同性</option>
                <option value="tr38901">3GPP 单元</option>
                <option value="custom_gain_grid">自定义增益网格</option>
              </select>
            </label>
          )}
          <NumberField label="发射阵列行数" value={config.tx_rows} onChange={(v) => update('tx_rows', Math.max(1, Math.round(v)))} />
          <NumberField label="发射阵列列数" value={config.tx_cols} onChange={(v) => update('tx_cols', Math.max(1, Math.round(v)))} />
          {config.tx_pattern !== 'custom_gain_grid' && (
            <label className="field">
              <span>发射波束权重</span>
              <select value={config.tx_beamforming_mode} onChange={(event) => {
                const mode = event.target.value as RadarDraftConfig['tx_beamforming_mode']
                onChange({
                  ...config,
                  tx_beamforming_mode: mode,
                  tx_custom_weights_json: mode === 'custom_complex_weights' && !config.tx_custom_weights_json.trim()
                    ? defaultComplexWeights(config.tx_rows * config.tx_cols)
                    : config.tx_custom_weights_json,
                })
              }}>
                <option value="steering_vector">导向角自动权重</option>
                <option value="custom_complex_weights">自定义阵元复权重</option>
              </select>
            </label>
          )}
          {config.tx_pattern !== 'custom_gain_grid' && config.tx_beamforming_mode === 'steering_vector' && (<>
            <NumberField label="发射导向方位偏角 °" value={config.tx_steering_azimuth_deg} step={1} onChange={(v) => update('tx_steering_azimuth_deg', v)} />
            <NumberField label="发射导向俯仰偏角 °" value={config.tx_steering_elevation_deg} step={1} onChange={(v) => update('tx_steering_elevation_deg', v)} />
            <label className="field">
              <span>发射孔径加权</span>
              <select value={config.tx_taper} onChange={(event) => update('tx_taper', event.target.value as RadarDraftConfig['tx_taper'])}>
                <option value="uniform">均匀</option>
                <option value="hann">Hann 低旁瓣</option>
              </select>
            </label>
          </>)}
          <NumberField label="调频周期时长 µs" value={config.chirp_duration_us} step={1} onChange={(v) => update('chirp_duration_us', v)} />
          <NumberField label="调频周期间隔 µs" value={config.chirp_idle_time_us} step={1} onChange={(v) => update('chirp_idle_time_us', v)} />
          <NumberField label="调频周期数" value={config.num_chirps} onChange={(v) => update('num_chirps', Math.max(2, Math.round(v)))} />
          <NumberField label="ADC 点数（0=自动）" value={config.adc_samples} step={256} onChange={(v) => update('adc_samples', Math.max(0, Math.round(v)))} />
        </div>
        {config.tx_pattern === 'custom_gain_grid' && (
          <div className="field custom-weights-field">
            <span>发射总增益网格（JSON，等效 1×1 辐射源）</span>
            <textarea
              value={config.tx_custom_gain_json}
              onChange={(event) => update('tx_custom_gain_json', event.target.value)}
              placeholder={DEFAULT_CUSTOM_GAIN_GRID}
            />
            <span className={txTotalGainValidation?.error ? 'field-validation invalid' : 'field-validation valid'}>
              {txTotalGainValidation?.error ?? `${txTotalGainValidation?.grid?.elevation.length} × ${txTotalGainValidation?.grid?.azimuth.length} 增益网格有效`}
            </span>
          </div>
        )}
        {config.tx_pattern === 'radar_array' && config.tx_element_pattern === 'custom_gain_grid' && (
          <div className="field custom-weights-field">
            <span>发射单元因子增益网格（JSON）</span>
            <textarea
              value={config.tx_element_custom_gain_json}
              onChange={(event) => update('tx_element_custom_gain_json', event.target.value)}
              placeholder={DEFAULT_CUSTOM_GAIN_GRID}
            />
            <span className={txElementGainValidation?.error ? 'field-validation invalid' : 'field-validation valid'}>
              {txElementGainValidation?.error ?? `${txElementGainValidation?.grid?.elevation.length} × ${txElementGainValidation?.grid?.azimuth.length} 单元因子网格有效`}
            </span>
          </div>
        )}
        {config.tx_pattern !== 'custom_gain_grid' && config.tx_beamforming_mode === 'custom_complex_weights' && (
          <div className="field custom-weights-field">
            <span>发射阵元复权重（JSON，{config.tx_pattern === 'radar_array' ? '行优先' : '列优先'}，{config.tx_rows * config.tx_cols} 项）</span>
            <textarea
              value={config.tx_custom_weights_json}
              onChange={(event) => update('tx_custom_weights_json', event.target.value)}
              placeholder='[[1,0],[0,-1],{"re":0.5,"im":0.5}]'
            />
            <button type="button" className="secondary-action compact" onClick={() => update('tx_custom_weights_json', defaultComplexWeights(config.tx_rows * config.tx_cols))}>
              <RefreshCw size={14} />重建同相权重
            </button>
          </div>
        )}
        <BeamPatternPreview config={config} side="tx" />
      </EditorSection>

      <EditorSection title="传播与散射">
        <div className="field-grid two">
          <NumberField label="最大反射阶数" value={config.max_depth} onChange={(v) => update('max_depth', Math.round(v))} />
          <NumberField label="散射系数" value={config.scattering_coefficient} step={0.05} onChange={(v) => update('scattering_coefficient', v)} />
          <NumberField label="镜面反射方向瓣宽 αᵣ" value={config.alpha_r} onChange={(v) => update('alpha_r', Math.round(v))} />
          <NumberField label="入射方向瓣宽 αᵢ" value={config.alpha_i} onChange={(v) => update('alpha_i', Math.round(v))} />
          <NumberField label="镜面反射瓣能量占比 λ" value={config.lambda_} step={0.05} onChange={(v) => update('lambda_', v)} />
          <label className="field">
            <span>散射模型</span>
            <select value={config.scattering_pattern} onChange={(event) => update('scattering_pattern', event.target.value as RadarDraftConfig['scattering_pattern'])}>
              <option value="backscattering">后向散射</option>
              <option value="lambertian">朗伯散射</option>
              <option value="directive">定向散射</option>
            </select>
          </label>
        </div>
        <div className="toggle-grid">
          <ToggleField label="直达路径（LoS）" checked={config.los} onChange={(v) => update('los', v)} />
          <ToggleField label="镜面反射" checked={config.specular_reflection} onChange={(v) => update('specular_reflection', v)} />
          <ToggleField label="漫反射" checked={config.diffuse_reflection} onChange={(v) => update('diffuse_reflection', v)} />
          <ToggleField label="散射" checked={config.scattering_enabled} onChange={(v) => update('scattering_enabled', v)} />
        </div>
      </EditorSection>

      <EditorSection title="接收阵列与信号处理" defaultOpen>
        <div className="field-grid two">
          <NumberField label="接收阵列行数" value={config.rx_rows} onChange={(v) => update('rx_rows', Math.max(1, Math.round(v)))} />
          <NumberField label="接收阵列列数" value={config.rx_cols} onChange={(v) => update('rx_cols', Math.max(1, Math.round(v)))} />
          <label className="field field-wide">
            <span>接收阵元方向图</span>
            <select value={config.rx_pattern} onChange={(event) => {
              const pattern = event.target.value as RadarDraftConfig['rx_pattern']
              onChange({
                ...config,
                rx_pattern: pattern,
                rx_custom_gain_json: pattern === 'custom_gain_grid' && !config.rx_custom_gain_json.trim()
                  ? DEFAULT_CUSTOM_GAIN_GRID
                  : config.rx_custom_gain_json,
              })
            }}>
              <option value="isotropic">各向同性</option>
              <option value="tr38901">3GPP 单元</option>
              <option value="custom_gain_grid">自定义增益网格</option>
            </select>
          </label>
          <label className="field field-wide">
            <span>接收波束形成方式</span>
            <select value={config.beamforming_rx_mode} onChange={(event) => update('beamforming_rx_mode', event.target.value as RadarDraftConfig['beamforming_rx_mode'])}>
              <option value="disabled">不进行数字合成</option>
              <option value="uniform">等幅同相合成</option>
              <option value="steering_vector">导向矢量</option>
              <option value="custom_complex_weights">自定义复权重</option>
            </select>
          </label>
          <NumberField label="接收导向方位偏角 °" value={config.beamforming_steering_azimuth_deg} step={1} onChange={(v) => update('beamforming_steering_azimuth_deg', v)} />
          <NumberField label="接收导向俯仰偏角 °" value={config.beamforming_steering_elevation_deg} step={1} onChange={(v) => update('beamforming_steering_elevation_deg', v)} />
          <NumberField label="噪声系数 dB" value={config.noise_figure_db} step={0.5} onChange={(v) => update('noise_figure_db', v)} />
          <NumberField label="接收机温度 K" value={config.receiver_temperature_k} step={5} onChange={(v) => update('receiver_temperature_k', v)} />
          <NumberField label="CFAR 目标虚警概率" value={config.cfar_pfa} step={0.00001} onChange={(v) => update('cfar_pfa', v)} />
          <NumberField label="回波合成路径上限" value={config.max_synthesis_paths} step={64} onChange={(v) => update('max_synthesis_paths', Math.max(1, Math.round(v)))} />
        </div>
        {config.rx_pattern === 'custom_gain_grid' && (
          <div className="field custom-weights-field">
            <span>接收单元因子增益网格（JSON）</span>
            <textarea
              value={config.rx_custom_gain_json}
              onChange={(event) => update('rx_custom_gain_json', event.target.value)}
              placeholder={DEFAULT_CUSTOM_GAIN_GRID}
            />
            <span className={rxGainValidation?.error ? 'field-validation invalid' : 'field-validation valid'}>
              {rxGainValidation?.error ?? `${rxGainValidation?.grid?.elevation.length} × ${rxGainValidation?.grid?.azimuth.length} 单元因子网格有效`}
            </span>
          </div>
        )}
        <div className="toggle-grid">
          <ToggleField label="对 CIR 注入复高斯白噪声" checked={config.cir_noise_enabled} onChange={(v) => update('cir_noise_enabled', v)} />
        </div>
        {config.cir_noise_enabled && (
          <div className="field-grid two">
            <NumberField label="CIR 信噪比 dB" value={config.cir_noise_snr_db} step={1} onChange={(v) => update('cir_noise_snr_db', v)} />
            <NumberField label="CIR 噪声随机种子" value={config.cir_noise_seed} step={1} onChange={(v) => update('cir_noise_seed', Math.round(v))} />
          </div>
        )}
        {config.beamforming_rx_mode === 'custom_complex_weights' && (
          <label className="field custom-weights-field">
            <span>接收阵列复权重（JSON，列优先，{config.rx_rows * config.rx_cols} 项）</span>
            <textarea
              value={config.beamforming_custom_weights_json}
              onChange={(event) => update('beamforming_custom_weights_json', event.target.value)}
              placeholder='[{"re":1,"im":0},{"re":0,"im":-1}]'
            />
          </label>
        )}
        <BeamPatternPreview config={config} side="rx" />
      </EditorSection>

      <EditorSection title="Sionna RT 路径求解">
        <div className="field-grid two">
          <label className="field">
            <span>初始射线方向采样</span>
            <select value={config.ray_sampling_mode} onChange={(event) => update('ray_sampling_mode', event.target.value as RadarDraftConfig['ray_sampling_mode'])}>
              <option value="full_sphere">Sionna 默认全空间采样</option>
              <option value="analysis_sector">限定分析扇区采样</option>
            </select>
          </label>
          <NumberField label="射线采样数" value={config.samples_per_src} step={1000} onChange={(v) => update('samples_per_src', Math.max(1, Math.round(v)))} />
          <NumberField label="随机种子" value={config.seed} onChange={(v) => update('seed', Math.round(v))} />
        </div>
        <div className="toggle-grid">
          <ToggleField label="合成阵列近似" checked={config.synthetic_array} onChange={(v) => update('synthetic_array', v)} />
        </div>
      </EditorSection>

      <div className="editor-actions">
        <button type="button" className="icon-button" onClick={onUndo} disabled={!canUndo} title="撤回上一步参数修改" aria-label="撤回上一步参数修改">
          <Undo2 size={16} />
        </button>
        <button type="button" className="icon-button" onClick={onRedo} disabled={!canRedo} title="重做参数修改" aria-label="重做参数修改">
          <Redo2 size={16} />
        </button>
        <button type="button" className="secondary-action" onClick={onReset}>
          <RotateCcw size={16} />
          恢复
        </button>
        <button type="button" className="secondary-action" onClick={onSaveConfig} disabled={!onSaveConfig || !changed || savingConfig || Boolean(gainGridError)}>
          <Save size={16} />
          {savingConfig ? '正在保存' : '保存参数'}
        </button>
        <button type="button" className="secondary-action" onClick={onSavePaths} disabled={!onSavePaths || changed || savingPaths}>
          <Save size={16} />
          {savingPaths ? '正在保存' : '保存路径'}
        </button>
        <button type="button" className="primary-action" onClick={onSubmit} disabled={running || Boolean(gainGridError)} title={gainGridError ?? undefined}>
          <Play size={16} />
          {running ? '仿真中' : gainGridError ? '请修正增益网格' : '运行雷达仿真'}
        </button>
      </div>
    </div>
  )
}
