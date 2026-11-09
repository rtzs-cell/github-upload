# Web 雷达/ISAC Sensing 仿真工作台规划

> **Status update, 2026-07-01**: This file is now a historical high-level plan. The implementation source of truth has been split into the organized package under `refine-logs/web-radar-workbench/`, especially `09_IMPLEMENTATION_RUNBOOK.md`, `10_RISK_REGISTER.md`, and `11_ARTIFACT_INVENTORY.md`.

Recommended reading order:

```text
refine-logs/web-radar-workbench/README.md
refine-logs/web-radar-workbench/08_PREIMPLEMENTATION_PROBES.md
refine-logs/web-radar-workbench/09_IMPLEMENTATION_RUNBOOK.md
refine-logs/web-radar-workbench/10_RISK_REGISTER.md
refine-logs/web-radar-workbench/11_ARTIFACT_INVENTORY.md
```

**日期**：2026-07-01  
**目标**：设计一个 Web 界面，使用户能够加载城市场景/点云，交互式设置雷达位置、方向、天线、频率、散射/反射参数，并调用后端 Sionna RT 生成雷达 sensing 数据，同时可视化传播路径、反射/散射点、range-azimuth/range-elevation 等谱图。

## 1. 总体定位

这个 Web 系统不是简单地把已有 PNG 放到网页上，而是一个“城市雷达 sensing 仿真工作台”：

1. **场景层**：加载城市点云、mesh、建筑 bbox、材料信息。
2. **雷达配置层**：交互设置 radar pose、boresight、FoV、频率、Tx/Rx 阵列、散射/反射配置。
3. **仿真任务层**：把前端配置转成 Sionna RT run config，提交给 GPU 后端异步执行。
4. **结果层**：返回 CIR、paths、交互点、range-azimuth、range-elevation、FoV 能量等数据。
5. **可视化层**：在 3D 场景和 2D 谱图中联动查看雷达方向变化后的传播效果。

核心原则：

```text
前端负责交互和可视化；
后端负责场景转换、Sionna RT 求解、GPU 调度和数据归档；
结果以结构化 JSON/NPZ/Zarr/Parquet + 图像缓存形式保存。
```

## 2. 关键边界：点云不能直接等价于 Sionna 仿真场景

用户希望“前端加载场景点云”，这是可行的，但需要分清两件事：

| 类型 | 作用 | 能否直接用于 Sionna RT |
|---|---|---|
| 点云 `.ply/.las/.laz/.pcd` | 前端显示真实城市形状、辅助选点 | 不能直接作为 Sionna RT radio scene |
| Mesh `.obj/.glb/.ply mesh/.xml` | 可用于射线追踪几何 | 可以，需转换为 Mitsuba/Sionna scene |
| 建筑 bbox/footprint | 快速可视化和简化仿真 | 可以作为简化代理几何 |
| 材料 map | 墙体/玻璃/地面散射参数 | 需要映射到 Sionna radio materials |

因此系统应支持两种模式：

1. **Visualization-only 点云模式**：前端显示点云，雷达点位和方向可以在点云上选，但仿真仍需对应 mesh/proxy scene。
2. **Simulation-ready mesh 模式**：点云经过重建、分割、简化、赋材质后，转换成 Sionna/Mitsuba 可用场景。

## 3. 推荐系统架构

```text
web-radar-workbench/
  frontend/
    React/Vite app
    Three.js scene viewer
    Plotly/ECharts spectrum panels
  backend/
    FastAPI service
    Sionna RT runner
    GPU job scheduler
    result postprocessor
  workers/
    per-GPU simulation workers
  data/
    scenes/
    campaigns/
    runs/
    cache/
```

### 3.1 前端

推荐：

```text
React + TypeScript + Vite
Three.js / react-three-fiber
Plotly.js or ECharts
Zustand/Jotai for UI state
TanStack Query for API state
```

前端职责：

1. 加载并显示点云/mesh/建筑 bbox。
2. 交互式放置 radar Tx/Rx 平台。
3. 调整 boresight、FoV、频率、天线、散射参数。
4. 提交 simulation job。
5. 轮询或 WebSocket 接收 job status。
6. 加载结果并联动展示路径、交互点、谱图。

### 3.2 后端

推荐：

```text
FastAPI
Pydantic config schema
Redis/RQ 或本地 multiprocessing queue
现有 Sionna runner 作为核心执行模块
```

后端职责：

1. 管理 scene manifest。
2. 管理 radar/campaign config。
3. 将前端参数转换为 Sionna run config。
4. 调用 GPU0-3 worker 并行运行。
5. 保存 CIR、paths、radar observation、可视化缓存。
6. 提供结构化 API 给前端按需读取。

### 3.3 GPU worker

沿用当前已验证策略：

```text
每张 GPU 一个 worker process
CUDA_VISIBLE_DEVICES=<gpu_id>
每个 worker 串行执行分配到的 Sionna measurement
```

默认使用：

```text
GPU IDs = [0, 1, 2, 3]
```

不要在同一 GPU 上同时跑多个 Sionna RT worker，除非后续证明显存和吞吐都允许。

## 4. 页面与交互设计

### 4.1 主界面布局

建议采用工程工具式布局，而不是 landing page：

```text
┌──────────────────────────────────────────────────────────────┐
│ Top Bar: Scene selector | Campaign | Save | Run | Job status │
├───────────────┬──────────────────────────────┬───────────────┤
│ Left Panel    │ Center 3D/2D Viewer           │ Right Panel   │
│ Scene layers  │ Point cloud / mesh / paths    │ Radar params  │
│ Run list      │ Radar pose + FoV              │ Solver params │
│ Result list   │ Interaction points            │ Output opts   │
├───────────────┴──────────────────────────────┴───────────────┤
│ Bottom Panel: spectra tabs, metrics table, logs              │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 左侧 Scene/Run 面板

功能：

1. 场景列表：
   - `simple_street_canyon`
   - 用户上传 scene
   - 点云 scene
   - mesh scene

2. 图层开关：
   - point cloud
   - mesh
   - building bbox
   - material colors
   - radar positions
   - boresight/FoV
   - paths
   - reflection/diffuse points
   - first-interaction heatmap

3. 结果列表：
   - 按 run_id
   - 按 pose_id
   - 按 boresight
   - 按 FoV energy fraction 排序

### 4.3 中央 3D/2D Viewer

必须支持两种视图：

#### 3D Scene View

用于看：

1. 点云/mesh。
2. 雷达 Tx/Rx 位置。
3. 16x16 Rx 阵列朝向，可简化成阵列平面 glyph。
4. boresight arrow。
5. 120 deg x 0-40 deg FoV frustum。
6. 传播路径 polyline：
   ```text
   Tx -> interaction vertex 1 -> interaction vertex 2 -> Rx
   ```
7. 反射点/散射点 marker。

#### 2D Top-Down View

用于工程核查：

1. 建筑 footprint。
2. 雷达 pose。
3. 方位 FoV 扇区。
4. 路径在 xy 平面的投影。
5. first-interaction energy hotspots。

建议 3D/2D 用同一套数据状态，用户切换视图时不丢失选中的 path/run。

### 4.4 右侧参数面板

分组如下。

#### Radar Pose

| 控件 | 参数 |
|---|---|
| 三维坐标输入/拖拽 gizmo | `radar_center = [x,y,z]` |
| 朝向角输入 | `azimuth`, `elevation` |
| look-at 目标点 | `look_at = [x,y,z]` |
| 小基线设置 | Tx/Rx offset，例如 0.1 m |
| LoS 开关 | 当前 radar sensing 默认 `los=False` |

#### Antenna

| 控件 | 参数 |
|---|---|
| Tx rows/cols | 默认 1x1 |
| Rx rows/cols | 默认 16x16 |
| element spacing | 默认 0.5 lambda |
| polarization | V/H/VH |
| pattern | isotropic / sector / custom |

#### FoV / Beam

| 控件 | 参数 |
|---|---|
| 方位 FoV slider | 默认 120 deg |
| 俯仰 min/max | 默认 0-40 deg |
| boresight lock | 跟随 look-at 自动计算 |
| sector pattern toggle | 区分后处理 FoV 与真实方向图 |

#### Frequency / Waveform

| 控件 | 参数 |
|---|---|
| carrier frequency | 28/60/77 GHz |
| bandwidth | 默认 1 GHz |
| range bin | 默认 0.15 m |
| max range | 默认 200 m |

#### Propagation / Scattering

| 控件 | 参数 |
|---|---|
| max_depth | 默认 2 |
| specular reflection | on |
| diffuse reflection | on |
| scattering coefficient | 默认 0.5 |
| scattering pattern | Backscattering |
| alpha_r / alpha_i / lambda | BackscatteringPattern 参数 |
| refraction/diffraction | 高级选项，默认 off |

#### Compute

| 控件 | 参数 |
|---|---|
| samples_per_src | 5e5 / 1e6 / 2e6 |
| seed | 固定或自动 |
| GPU selection | 默认 0,1,2,3 |
| run mode | single pose / sweep / campaign |
| output root | campaign folder |

## 5. 结果可视化设计

### 5.1 路径可视化

路径线含义：

| 颜色 | 含义 |
|---|---|
| 蓝色 | specular-only |
| 橙色 | diffuse/backscatter |
| 紫色 | mixed specular + diffuse |

标记：

| 标记 | 含义 |
|---|---|
| 三角 | Tx |
| 方块 | Rx |
| 圆点 | specular 交互点 |
| 叉号 | diffuse/backscatter 交互点 |
| 线宽 | 相对路径能量 |

交互方式：

1. 鼠标 hover 某条路径：显示 range、delay、energy、interactions、objects。
2. 点击路径：在 range-azimuth/range-elevation 图中高亮对应 bin。
3. 点击谱图峰值：反查贡献路径并在 3D 中高亮。
4. 按路径类型过滤：specular/diffuse/mixed。
5. 按 depth 过滤：depth=1/depth=2。
6. 按 energy threshold 过滤。

### 5.2 反射/散射点可视化

至少三种模式：

1. **First-interaction hotspots**
   - 每条路径的第一次交互点。
   - 用颜色显示路径能量。

2. **All-interaction points**
   - 显示 depth=1 和 depth=2 的所有交互点。
   - 用不同 marker 区分 specular/diffuse。

3. **Object contribution view**
   - 按建筑 object 聚合能量。
   - 建筑 bbox 或 mesh 根据贡献能量着色。

### 5.3 谱图可视化

底部面板建议 tabs：

1. `Range-Azimuth`
2. `Range-Elevation`
3. `Range-Doppler`，静态场景中默认无真实 Doppler，可保留占位
4. `CIR`
5. `Path Table`
6. `Metrics`

Range-Azimuth 图：

| 元素 | 含义 |
|---|---|
| x | AoA azimuth |
| y | range |
| color | relative power dB |
| cyan vertical lines | azimuth FoV boundary |

Range-Elevation 图：

| 元素 | 含义 |
|---|---|
| x | AoA elevation |
| y | range |
| color | relative power dB |
| cyan vertical lines | elevation FoV boundary |

联动功能：

1. 鼠标 hover 谱图 cell，显示 range/angle/power。
2. 点击谱图 cell，筛选落入该 bin 的 paths。
3. 调整 radar pose 后，旧谱图灰显，新任务完成后刷新。
4. 支持多 run 对比：同屏显示两个 pose 的谱图差异。

## 6. 数据接口设计

### 6.1 Scene API

```http
GET /api/scenes
POST /api/scenes/upload
GET /api/scenes/{scene_id}/manifest
GET /api/scenes/{scene_id}/geometry/bbox
GET /api/scenes/{scene_id}/pointcloud
GET /api/scenes/{scene_id}/mesh
POST /api/scenes/{scene_id}/convert
```

`convert` 用于点云/mesh 转 Sionna/Mitsuba scene。

### 6.2 Simulation API

```http
POST /api/simulations
GET  /api/simulations/{job_id}
POST /api/simulations/{job_id}/cancel
GET  /api/simulations/{job_id}/logs
```

请求示例：

```json
{
  "scene_id": "simple_street_canyon",
  "mode": "single_pose",
  "gpu_ids": [0, 1, 2, 3],
  "radar": {
    "center_m": [0.0, 0.0, 10.0],
    "look_at_m": [0.0, 30.0, 10.0],
    "tx_array": [1, 1],
    "rx_array": [16, 16],
    "tx_rx_baseline_m": 0.1
  },
  "propagation": {
    "frequency_hz": 28000000000.0,
    "bandwidth_hz": 1000000000.0,
    "max_depth": 2,
    "los": false,
    "specular_reflection": true,
    "diffuse_reflection": true,
    "scattering": {
      "pattern": "backscattering",
      "coefficient": 0.5,
      "alpha_r": 20,
      "alpha_i": 20,
      "lambda": 0.3
    }
  },
  "observation": {
    "az_width_deg": 120,
    "el_min_deg": 0,
    "el_max_deg": 40,
    "rmax_m": 200,
    "range_bin_m": 0.15,
    "angle_bin_deg": 2
  },
  "compute": {
    "samples_per_src": 500000,
    "seed": 501
  }
}
```

### 6.3 Result API

```http
GET /api/results/{run_id}/metadata
GET /api/results/{run_id}/metrics
GET /api/results/{run_id}/paths?top_k=500&type=diffuse
GET /api/results/{run_id}/interactions?mode=first
GET /api/results/{run_id}/range_azimuth
GET /api/results/{run_id}/range_elevation
GET /api/results/{run_id}/cir
GET /api/results/{run_id}/files
```

大数据不要一次性 JSON 返回全部 paths。建议：

1. 前端默认只取 top-k paths。
2. 完整数据仍存为 NPZ/Zarr。
3. 谱图矩阵可用 compressed binary 或 tiled array。

## 7. 数据格式规划

### 7.1 Run 目录

沿用当前归档结构：

```text
runs/<run_id>/
  config.yaml
  metadata.json
  metrics.json
  paths_summary.npz
  cir.npz
  radar_observation.npz
  figures/
```

### 7.2 Web 可视化缓存

建议新增：

```text
web_cache/<run_id>/
  scene_objects.json
  top_paths.json
  interaction_points.parquet
  range_azimuth.bin
  range_elevation.bin
  thumbnails/
```

原因：

1. `cir.npz` 很大，不适合直接给前端读。
2. paths 可达几十万条，前端必须抽样/过滤。
3. 交互需要低延迟，最好准备 web-friendly cache。

### 7.3 top_paths.json 示例

```json
{
  "run_id": "MM_C002full_Pp0_p0_BposY_S501_N500k",
  "paths": [
    {
      "path_id": 64824,
      "range_m": 9.5716,
      "energy": 8.96e-8,
      "kind": "specular",
      "interactions": ["specular"],
      "vertices": [[0.0, 9.5716, 10.0]]
    }
  ]
}
```

## 8. 前端工作流

### 8.1 单点交互仿真

1. 用户选择 scene。
2. 前端加载点云/mesh/bbox。
3. 用户点击或拖拽放置 radar。
4. 用户设置 look-at 或拖动方向箭头。
5. 前端实时显示 FoV 扇区/frustum。
6. 用户点击 `Run Sensing`。
7. 后端提交 job 到 GPU worker。
8. job 完成后，前端加载 paths/spectra/metrics。
9. 用户点击路径或谱图峰值联动检查。

### 8.2 多测点 Campaign

1. 用户在地图上批量布点，或上传 pose manifest。
2. 设置 boresight sweep，例如 `+x`, `+y`, custom azimuth list。
3. 设置 GPU IDs `[0,1,2,3]`。
4. 提交 campaign。
5. 前端显示进度：
   ```text
   17/30 completed, GPU0 running Pp0_p5_BposX ...
   ```
6. 完成后生成：
   - pose heatmap
   - FoV energy map
   - per-run dashboard
   - comparison table

### 8.3 动态方向/位置变化

这里的“动态”建议先定义为交互式重新仿真或预计算 sweep，而不是实时连续 ray tracing：

1. 用户拖动方向时，前端立即更新 FoV 几何。
2. 若结果已有缓存，立即显示对应谱图。
3. 若结果未缓存，显示 `Needs simulation`，用户点击 run。
4. 对常用方向可提前 sweep：
   ```text
   azimuth = -60:10:+60 relative to boresight
   elevation = 0:10:40
   ```
5. 通过缓存实现“近实时查看”。

## 9. 性能与并行策略

### 9.1 仿真并行

沿用当前已验证命令：

```bash
python experiments/sionna_radar/scripts/run_multi_measurement_campaign.py \
  --campaign C002-full \
  --clean \
  --parallel-gpus 0,1,2,3 \
  --campaign-root outputs/sionna_radar_campaigns_parallel
```

Web 后端应封装该能力，而不是让前端直接调用 shell。

### 9.2 后处理向量化

当前已实现：

```text
uniform_weighted_histogram2d()
```

后续建议：

1. 对 top-k path extraction 使用 NumPy partial sort。
2. 对 interaction hotspots 使用向量化 filter。
3. 对多 run summary 用 Pandas/Polars。
4. 超大路径数再考虑 CuPy/JAX。

### 9.3 前端渲染性能

点云/路径不要一次性全部渲染：

1. 点云使用 LOD 或 octree。
2. 路径默认只显示 top-k，例如 top 100/500。
3. 交互点默认采样或按能量阈值过滤。
4. 谱图用 texture/image 或 WebGL heatmap，不用 DOM cell。

## 10. MVP 开发阶段

### Phase 0：只读结果浏览器

目标：不跑新仿真，只浏览当前 C002-full 结果。

功能：

1. 加载 `POSE_METRICS.csv`。
2. 显示 campaign 总览。
3. 选择 run。
4. 显示已有：
   - dashboard PNG
   - range-azimuth PNG
   - range-elevation PNG
   - metrics JSON

价值：最快上线，验证界面布局。

### Phase 1：交互式 2D/3D 可视化

目标：把当前 PNG 变成真正可交互图层。

功能：

1. Three.js 加载建筑 bbox/mesh/点云。
2. 渲染 radar pose、FoV、paths、interaction points。
3. 谱图与路径联动。
4. top-k path filter。

### Phase 2：单点仿真提交

目标：用户在 Web 中设置一个 pose 并运行 Sionna。

功能：

1. 参数面板。
2. FastAPI `POST /api/simulations`。
3. GPU worker。
4. job status。
5. 自动加载结果。

### Phase 3：Campaign 批量仿真

目标：Web 中提交多测点、多朝向、多频率 sweep。

功能：

1. pose manifest 编辑器。
2. GPU0-3 并行调度。
3. campaign 进度条。
4. result table 和 heatmap。

### Phase 4：点云到仿真场景

目标：从用户上传点云构造可仿真的 Sionna scene。

功能：

1. 点云上传。
2. 地面/建筑分割。
3. mesh reconstruction 或 bbox proxy。
4. 材料赋值。
5. 导出 Mitsuba XML / Sionna scene。

这一阶段最复杂，不建议作为 MVP。

## 11. 风险与处理

| 风险 | 说明 | 处理 |
|---|---|---|
| 点云不能直接 RT | Sionna 需要可相交几何 | 点云先用于可视化；仿真用 mesh/proxy |
| 前端一次加载路径太多 | 几十万路径会卡顿 | top-k、LOD、二进制缓存 |
| 单次 Sionna 仿真不够实时 | 30 个 run 即使并行也需分钟级 | 预计算 sweep + 缓存 |
| FoV 被误认为真实天线方向图 | 当前部分结果是后处理 FoV | UI 明确标注 postprocess FoV vs sector pattern |
| 多用户抢 GPU | GPU0-3 资源有限 | job queue、配额、取消任务 |
| 结果文件过大 | `cir.npz` 可达数百 MB | web cache 分离，前端不直接读 CIR |

## 12. 建议优先实现的最小闭环

先做 Phase 0 + Phase 1：

```text
现有 C002-full 结果浏览器
  -> Three.js 建筑/雷达/FoV/路径交互
  -> Plotly/ECharts 谱图
  -> metrics panel
```

不要一开始就做点云到 Sionna scene 的自动转换。先把当前已经验证的 Sionna sensing 数据可视化成一个可用工作台，再接入新仿真提交。

最小可交付：

1. 首页就是工作台，不做营销页。
2. 默认加载 C002-full。
3. 左侧选择 run。
4. 中间显示 3D/2D 场景。
5. 右侧显示 radar config 和 metrics。
6. 底部显示 range-azimuth/range-elevation。
7. 用户点击路径，谱图高亮；点击谱图峰值，路径高亮。

完成这个后，再接入 `POST /api/simulations` 和 GPU0-3 并行执行。
