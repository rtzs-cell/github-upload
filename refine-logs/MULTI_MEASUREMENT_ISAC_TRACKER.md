# 多测点城市雷达/ISAC 实验追踪表

| Run/Campaign | Stage | Purpose | Scene | Scope | Priority | Status | Notes |
|---|---|---|---|---|---|---|---|
| R024B | S1 | 修正 R024 FoV 中心 | simple_street_canyon | Reprocess R011, az_center=90 deg | MUST | DONE | FoV energy fraction 0.06649 -> 0.31428。 |
| C001 | S1 | 同点重复测量稳定性 | simple_street_canyon | P00, 3 seeds, 5e5 samples | MUST | DONE | FoV energy fraction CV 约 0.001。 |
| C002-lite | S2 | 5 点中心线空间测量 | simple_street_canyon | 5 poses, +y boresight, 5e5 samples | MUST | DONE | 五个测点均有效，FoV 能量随位置明显变化。 |
| C002-full | S2 | 30 点街谷雷达自发自收测量 | simple_street_canyon | 15 poses x 2 boresights | MUST | DONE | 30/30 完成；每个 run 均有 CIR、paths、range-azimuth/range-elevation、metrics。FoV energy fraction mean=0.137409。 |
| C002-high | S2 | 关键测点高采样复核 | simple_street_canyon | 5 poses x 3 seeds x 2e6 samples | MUST | TODO | 用于确认主图稳定。 |
| C003-mini | S3 | 弃用的通信扩展 | simple_street_canyon | P03 + 6 UEs | CUT | DEPRECATED | 与当前雷达自发自收任务无关，不纳入结论。 |
| C003-full | S3 | 弃用的通信扩展 | simple_street_canyon | 9 BS poses x 10-15 UEs | CUT | DEPRECATED | 不执行。 |
| C004-lite | S4 | FoV/boresight 后处理扫描 | simple_street_canyon | 9 poses x az/el scan | NICE | TODO | 仅证明观测裁剪效用，不等价真实天线方向图。 |
| C004-sector | S4 | 自定义 sector 天线方向图扫描 | simple_street_canyon | 9 poses x az/el scan | MUST for paper | TODO | 论文级 ISAC beam 结论建议必须做。 |
| C005 | S5 | 频率/材料敏感性 | simple_street_canyon | 28/60/77GHz x scattering sweep | NICE | TODO | 支持高频扩展，但不作主证明。 |
| ACCEL-GPU0-3 | S-ACCEL | 并行化/向量化加速 | simple_street_canyon | C002-full on GPU 0,1,2,3 | MUST | DONE | C002-full 30/30 完成；wall time 489s -> 135s，约 3.62x；关键指标与原结果一致。 |
| WEB-PLAN | S-WEB | Web 雷达 sensing 工作台极细规划 | C002-full + future scenes | read-only browser -> cache -> API -> GPU0-3 jobs -> point-cloud preview | MUST | DONE | 规划包位于 `refine-logs/web-radar-workbench/`，含探针、runbook、风险登记、产物清单。 |
| WEB-P0P1 | S-WEB | Web 工作台只读浏览器实现 | C002-full existing outputs | FastAPI read-only API + web cache + React browser | MUST | DONE | 只读浏览、路径/交互点/谱图缓存与 C002-full 结果加载已作为完整工作台基础保留。 |
| WEB-FULL | S-WEB | 完整 Web 雷达 sensing 工作台 | C002-full + web-generated runs | 3D visualization + radar editor + simulation API + GPU0-3 scheduler + cache/archive | MUST | DONE | 已完成核心闭环：3D 场景/路径/FoV、参数编辑、异步 Sionna job、单点与 campaign GPU 调度、结果归档、web cache、UI 自动加载新结果。Smoke: `job_20260701_112110_8394e5d8` 单点 GPU0，`job_20260701_113013_a6d1b876` 2-pose GPU0/1 campaign。 |

## Gate Checklist

| Gate | Required Runs | Pass Condition | Status |
|---|---|---|---|
| MG1：FoV 修正 | R024B | boresight 自动计算正确，FoV 内比例合理 | DONE |
| MG2：重复测量稳定 | C001 | seed/samples 方差可接受 | DONE |
| MG3：空间一致性 | C002-lite/C002-full | 相邻测点回波结构连续且可解释 | DONE |
| MG4：ISAC sensing 数据集 | C002-full | 每个 BS/radar pose 有自发自收 sensing CIR/map/metrics | DONE |
| MG5：方向图严谨性 | C004-sector | 真实 sector pattern 支持 beam/FoV 结论 | TODO |
| MG6：并行加速可复现 | ACCEL-GPU0-3 | GPU0-3 并行输出完整且指标一致 | DONE |
| MG7：Web 工作台实现门禁 | WEB-PLAN | 先 C002-full 只读浏览和 web cache，再开放 live Sionna job；禁止 UE/通信漂移 | READY |
| MG8：Web 只读浏览器可运行 | WEB-P0P1 | C002-full 可在 Web 中浏览 run、指标、路径、谱图，且不默认加载 CIR | DONE |
| MG9：完整 Web 工作台闭环 | WEB-FULL | 参数编辑 -> 仿真提交 -> GPU0-3 运行 -> 结果归档 -> web cache -> 3D/谱图加载 | DONE |
