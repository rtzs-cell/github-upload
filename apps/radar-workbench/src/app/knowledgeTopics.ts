export type KnowledgeTopic = 'start' | 'geometry' | 'propagation' | 'array' | 'mpc' | 'fmcw' | 'paths' | 'data' | 'validation' | 'glossary'

export const knowledgeTopics: Array<{ id: KnowledgeTopic; label: string }> = [
  { id: 'start', label: '01 快速开始' },
  { id: 'geometry', label: '02 场景与几何' },
  { id: 'propagation', label: '03 传播求解' },
  { id: 'array', label: '04 阵列与波束' },
  { id: 'mpc', label: '05 MPC 空间谱' },
  { id: 'fmcw', label: '06 FMCW 处理' },
  { id: 'paths', label: '07 路径与统计' },
  { id: 'data', label: '08 任务与数据' },
  { id: 'validation', label: '09 验证排错' },
  { id: 'glossary', label: '附录 标准术语' },
]
