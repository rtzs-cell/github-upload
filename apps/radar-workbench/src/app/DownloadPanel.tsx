import { Archive, Download, FileArchive, FileChartColumn, FileJson, Radio } from 'lucide-react'
import type { DownloadArtifact } from '../api/types'
import { downloadUrl } from '../api/client'

function formatBytes(value: number | null): string {
  if (value === null) return '按需生成'
  if (value < 1024) return `${value} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let size = value / 1024
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size >= 100 ? size.toFixed(0) : size >= 10 ? size.toFixed(1) : size.toFixed(2)} ${units[unit]}`
}

function artifactIcon(category: string) {
  if (category === 'raw') return <Radio size={16} />
  if (category === 'table') return <FileChartColumn size={16} />
  if (category === 'config') return <FileJson size={16} />
  return <FileArchive size={16} />
}

export function DownloadPanel({ artifacts }: { artifacts: DownloadArtifact[] }) {
  const bundles = artifacts.filter((item) => item.category === 'bundle')
  const files = artifacts.filter((item) => item.category !== 'bundle')
  return (
    <section className="download-panel">
      <div className="panel-heading"><Archive size={16} /><span>结果下载</span></div>
      <div className="download-bundles">
        {bundles.map((item) => (
          <a key={item.artifact_id} href={downloadUrl(item.download_url)} className={item.artifact_id === 'analysis_bundle' ? 'primary-download' : 'secondary-download'}>
            <Download size={16} />
            <span><strong>{item.label}</strong><em>{item.description}</em></span>
          </a>
        ))}
      </div>
      <div className="download-file-list">
        {files.map((item) => (
          <a key={item.artifact_id} href={downloadUrl(item.download_url)}>
            {artifactIcon(item.category)}
            <span><strong>{item.label}</strong><em>{item.description}</em></span>
            <small>{formatBytes(item.size_bytes)}</small>
            <Download size={15} />
          </a>
        ))}
      </div>
    </section>
  )
}
