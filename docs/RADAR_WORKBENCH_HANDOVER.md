# 雷达仿真工作台模块、数据获取与迁移手册

本文档用于项目交接、复现实验、归档和迁移。它描述当前仓库中每个主要模块的功能、数据如何产生和获取，以及把整个项目搬到新机器时应怎样操作。

最后更新日期：2026-07-10

面向使用者的连续操作流程、结果指标解释、MPC/波束成形教程和定向候选射线实现边界，请先阅读 `RADAR_WORKBENCH_TUTORIAL.md`。

## 1. 项目边界

本项目是基于 NVIDIA Sionna RT 的城市环境雷达感知仿真工作区，核心目标是研究静态城市环境中自发自收雷达的传播路径、回波角度、距离谱和 ISAC 感知数据可用性。

当前主线只考虑雷达自发自收：

- Tx 和 Rx 位于同一雷达平台附近，默认小基线分离。
- Tx 为单天线，Rx 可为 16x16 阵列。
- 场景中没有 UE，也没有单独的通信链路 pass。
- 输出侧重路径、CIR、距离-角度谱、散射/反射交互点和统计指标。

需要特别注意：

- `postprocess_fov` 是后处理 AoA/俯仰角/距离门控，不是物理天线方向图。
- `sector` 当前映射到 Sionna 支持的 `tr38901` 方向图近似，并作用于 Tx/Rx 阵列，但它不是严格的 120 度方位、0-40 度俯仰自定义扇区方向图。
- `AoA/range` 散点图是路径几何诊断图，不是 Range-Doppler 图，也不是目标检测结果。
- 静态场景和静止雷达下 Doppler 为 0，这是预期结果。

## 2. 顶层目录职责

| 路径 | 功能 | 迁移时是否必须 |
|---|---|---|
| `apps/radar-workbench/` | React + TypeScript 前端，负责三维显示、参数编辑、谱图查看、路径保存。 | 必须 |
| `services/radar_api/` | FastAPI 后端，负责结果索引、缓存生成、API 服务、GPU 任务调度。 | 必须 |
| `experiments/sionna_radar/` | Sionna RT 仿真实验代码、配置和离线脚本。 | 必须 |
| `scripts/` | 本地启动和停止脚本。 | 必须 |
| `outputs/` | 大体量仿真输出、Web 缓存、任务状态、导出的路径数据。 | 按迁移目标选择 |
| `refine-logs/` | 方案、风险、实验追踪、实现记录。 | 建议迁移 |
| `docs/` | 面向交接和使用的文档。 | 必须 |
| `.gitignore` | 规定大文件输出不进入 Git。 | 必须 |

## 3. 数据流总览

### 3.1 浏览已有实验数据

1. 前端读取 `/api/campaigns`，获得可用 campaign。
2. 选择 campaign 后，前端读取 `/api/campaigns/{campaign_id}/runs`，获得 run 列表。
3. 选择某个 run 后，前端并行读取：
   - `/api/results/{run_id}/metadata`
   - `/api/results/{run_id}/scene_objects`
   - `/api/results/{run_id}/paths`
   - `/api/results/{run_id}/interactions`
   - `/api/results/{run_id}/range_azimuth`
   - `/api/results/{run_id}/range_elevation`
4. 后端如发现 Web 缓存不存在，会从原始 run 目录生成缓存到 `outputs/radar_workbench/web_cache/<run_id>/`。
5. 前端用缓存数据渲染三维场景、路径、交互点、统计面板和距离-角度谱。

### 3.2 从前端提交新雷达仿真

1. 用户在前端设置雷达位置、指向、FoV、频率、散射模型、阵列和 GPU。
2. 前端调用 `POST /api/simulations`。
3. 后端 `GPUScheduler` 根据 `gpu_ids` 把单点或多点任务分配到 GPU0-3。
4. 每个 worker 设置 `CUDA_VISIBLE_DEVICES=<gpu_id>` 后调用 Sionna RT runner。
5. 原始结果写入 `outputs/radar_workbench/campaigns/<job_id>/runs/<run_id>/`。
6. 后端从原始结果生成 `radar_observation.npz`、Web 缓存和 campaign 索引。
7. 任务状态写入 `outputs/radar_workbench/jobs/<job_id>/`。
8. 前端轮询 `/api/simulations/{job_id}`，完成后自动加载新结果。

### 3.3 保存路径归档

1. 用户在前端点击保存路径。
2. 前端调用 `POST /api/results/{run_id}/path_exports`。
3. 后端将筛选后的路径、路径摘要、雷达配置和原始元数据写入：

```text
outputs/radar_workbench/path_exports/<export_id>/
```

该目录适合后续 ISAC 数据分析、论文制图或人工核查。

## 4. 仿真实验模块

目录：`experiments/sionna_radar/`

### 4.1 配置文件

`experiments/sionna_radar/configs/runs.yaml`

作用：

- 定义基础频率、带宽、Tx/Rx 阵列、Sionna path solver 参数。
- 定义反射、散射、后向散射模型参数。
- 定义离线 run 的位置、场景、输出路径。

关键参数：

| 参数 | 含义 |
|---|---|
| `frequency_hz` | 载频，例如 28 GHz、60 GHz、77 GHz。 |
| `bandwidth_hz` | 用于距离分辨率分析的带宽记录。 |
| `tx_array` | Tx 相控孔径配置；`radar_array` 通过 Sionna 公开方向图接口嵌入固定发射波束。 |
| `rx_array` | Rx 阵列配置，当前需求通常为 16x16。 |
| `path_solver.max_depth` | 最大交互深度，例如 2 表示最多两次反射/散射交互。 |
| `path_solver.initial_ray_sampling.mode` | `full_sphere` 全空间基线或 `analysis_sector` 分析扇区定向初始采样。 |
| `path_solver.specular_reflection` | 是否开启镜面反射。 |
| `path_solver.diffuse_reflection` | 是否开启漫反射/散射。 |
| `scattering.pattern` | `backscattering`、`lambertian` 或 `directive`。 |
| `fov` | 后处理视场门控参数。 |
| `waveform` | FMCW chirp 时长、间隔、chirp 数和 ADC 点数。 |
| `receiver` | 温度和噪声系数。 |
| `radar_processing` | 回波合成路径上限和 CA-CFAR 虚警率。 |

### 4.2 核心 Python 包

`experiments/sionna_radar/src/sionna_radar/`

| 文件 | 功能 |
|---|---|
| `runner.py` | 加载 Sionna RT 场景、配置材料、阵列、Tx/Rx，调用 `PathSolver`，保存原始路径和 CIR。 |
| `antenna_patterns.py` | 通过 Sionna 公开注册接口提供相控孔径 Tx 复场方向图及 NumPy 验证实现。 |
| `directional_sampling.py` | 将初始候选射线限制到分析扇区，并校正漫反射 ray-tube 立体角权重。 |
| `processing.py` | 将 Sionna 路径转换为距离、角度、交互统计、距离-角度图和基础诊断图。 |
| `archive.py` | 管理 run 目录、写入 `config.yaml`、`metadata.json`、`metrics.json`。 |
| `config.py` | 加载 YAML 配置并解析 run 配置。 |

### 4.3 离线脚本

`experiments/sionna_radar/scripts/`

| 脚本 | 功能 |
|---|---|
| `run_experiment.py` | 按 run_id 执行一个离线 Sionna 仿真。 |
| `run_multi_measurement_campaign.py` | 执行多测点雷达自发自收 campaign。 |
| `postprocess_radar_observation.py` | 从已有路径和 CIR 后处理生成雷达观测数据。 |
| `generate_radar_sensing_visualizations.py` | 生成俯视路径、交互点、campaign 热力图等可视化。 |
| `summarize_runs.py` | 汇总 `outputs/sionna_radar/runs/` 下的 run。 |

常用命令：

```bash
python experiments/sionna_radar/scripts/run_experiment.py --run-id R010
python experiments/sionna_radar/scripts/summarize_runs.py
```

## 5. 后端模块

目录：`services/radar_api/`

### 5.1 入口和配置

| 文件 | 功能 |
|---|---|
| `app/main.py` | FastAPI 应用入口，挂载 health、campaigns、results、simulations 路由。 |
| `app/config.py` | 根据当前仓库位置自动计算 `repo_root`、已有 C002 campaign 路径、Workbench 输出路径和 Web 缓存路径。 |
| `app/schemas.py` | API 请求和响应的数据结构。 |
| `app/deps.py` | 后端单例依赖，包括 campaign registry、result loader、job store。 |
| `app/bootstrap.py` | 将 `experiments/sionna_radar/src` 加入 Python import 路径。 |

默认关键路径：

```text
existing_campaign_root = outputs/sionna_radar_campaigns/C002_full_radar_sensing
workbench_output_root  = outputs/radar_workbench
web_cache_root         = outputs/radar_workbench/web_cache
```

### 5.2 API 路由

| 文件 | API | 功能 |
|---|---|---|
| `app/api/health.py` | `GET /api/health` | 检查服务状态、可用 GPU ID、既有 campaign 是否存在。 |
| `app/api/campaigns.py` | `GET /api/campaigns` | 列出已有 C002 和 Web 生成的 campaign。 |
| `app/api/campaigns.py` | `GET /api/campaigns/{campaign_id}/runs` | 列出 campaign 内所有 run。 |
| `app/api/results.py` | `GET /api/results/{run_id}/metadata` | 获取配置、元数据、指标和可用 artifact。 |
| `app/api/results.py` | `GET /api/results/{run_id}/scene_objects` | 获取建筑物/物体包围盒和材料信息。 |
| `app/api/results.py` | `GET /api/results/{run_id}/paths` | 获取按能量排序的路径、交互点和路径折线。 |
| `app/api/results.py` | `POST /api/results/{run_id}/path_exports` | 保存路径归档。 |
| `app/api/results.py` | `GET /api/results/{run_id}/interactions` | 获取交互点表格。 |
| `app/api/results.py` | `GET /api/results/{run_id}/range_azimuth` | 获取距离-方位角谱元数据。 |
| `app/api/results.py` | `GET /api/results/{run_id}/range_elevation` | 获取距离-俯仰角谱元数据。 |
| `app/api/results.py` | `GET /api/results/{run_id}/beamforming` | 获取不可变 Tx/Rx 波束和相干 CIR 结果。 |
| `app/api/results.py` | `GET /api/results/{run_id}/fmcw` | 获取 FMCW 距离-多普勒和 CA-CFAR 结果。 |
| `app/api/results.py` | `GET /api/results/{run_id}/{kind}/array` | 获取谱图二进制 `float32` 数组。 |
| `app/api/results.py` | `GET /api/results/{run_id}/figures/{figure_name}` | 获取原始 PNG 诊断图。 |
| `app/api/simulations.py` | `POST /api/simulations` | 提交单点或多点雷达仿真任务。 |
| `app/api/simulations.py` | `GET /api/simulations/{job_id}` | 查询仿真任务状态。 |

### 5.3 结果索引和缓存

| 文件 | 功能 |
|---|---|
| `app/core/campaign_registry.py` | 注册内置 C002 campaign，并扫描 `outputs/radar_workbench/campaigns/` 中 Web 生成的 campaign。 |
| `app/core/result_loader.py` | 根据 `run_id` 找到 run 目录，并安全读取配置、元数据、指标和图像。 |
| `app/core/web_cache.py` | 将原始 `paths_summary.npz` 和 `radar_observation.npz` 转换成前端友好的 JSON、Parquet 和二进制谱图。 |

Web 缓存可手动重建：

```bash
cd services/radar_api
python -m app.core.web_cache \
  --run-dir ../../outputs/sionna_radar_campaigns/C002_full_radar_sensing/runs/<run_id> \
  --out-root ../../outputs/radar_workbench/web_cache
```

如果迁移后缓存中的旧绝对路径不可信，可以删除 `outputs/radar_workbench/web_cache/<run_id>/`，后端会在下一次请求该 run 时自动重建。

### 5.4 GPU 任务调度

| 文件 | 功能 |
|---|---|
| `app/workers/gpu_scheduler.py` | 验证 GPU ID，按 GPU 分配单点或多点任务，使用子进程运行 Sionna。 |
| `app/workers/simulation_worker.py` | 将前端请求转换成 Sionna run 配置，执行仿真，生成雷达观测和 campaign 索引。 |
| `app/workers/job_store.py` | 写入 job 请求、状态、事件日志和错误日志。 |

GPU 限制：

- 默认允许 GPU0、GPU1、GPU2、GPU3。
- 非法 GPU ID 会被后端拒绝。
- 每个子进程通过 `CUDA_VISIBLE_DEVICES` 绑定单个 GPU。

## 6. 前端模块

目录：`apps/radar-workbench/`

### 6.1 API 层

| 文件 | 功能 |
|---|---|
| `src/api/client.ts` | 封装所有后端请求，默认 API 地址为 `http://127.0.0.1:8000`。 |
| `src/api/types.ts` | 前后端共享的 TypeScript 数据结构。 |

可通过环境变量覆盖 API 地址：

```bash
VITE_RADAR_API_BASE=http://<backend-host>:8000 npm run dev -- --host 0.0.0.0
```

### 6.2 应用组件

| 文件 | 功能 |
|---|---|
| `src/app/App.tsx` | 主界面，负责 campaign/run 加载、仿真提交、路径保存、谱图显示和布局。 |
| `src/app/RadarEditor.tsx` | 雷达参数编辑面板，包括位置、指向、FoV、频率、方向约束、散射、阵列、GPU。 |
| `src/app/FovDragControl.tsx` | 可拖动的方位角和方位宽度控制器。 |
| `src/app/Scene3D.tsx` | Three.js 三维场景，显示建筑、雷达位姿、FoV、路径折线和交互点。 |
| `src/app/RadarStatisticsPanel.tsx` | 统计分析面板，包括路径数、FoV 能量、距离像、能量占比、角度分布等。 |
| `src/app/radarConfig.ts` | 从 run 元数据生成可编辑草稿配置，并计算方位角/俯仰角。 |
| `src/styles/globals.css` | 全局样式和布局。 |

### 6.3 前端中重要的专业表述

- “方向约束方式”表示仿真或后处理里如何限制方向。
- “AoA/距离门控（后处理）”表示从全向路径中按接收 AoA、俯仰角和距离筛选。
- “物理扇区方向图”当前是 `tr38901` 近似，不是严格自定义 sector。
- “距离-方位角谱”和“距离-俯仰角谱”来自路径能量按距离和 AoA 分箱累加。
- “路径到达角-等效距离散点图”只用于路径几何诊断。

## 7. 启动、停止和验证

### 7.1 一键启动

```bash
./scripts/start_radar_workbench.sh
```

默认地址：

```text
Frontend: http://127.0.0.1:5173
Backend:  http://127.0.0.1:8000
```

### 7.2 一键停止

```bash
./scripts/stop_radar_workbench.sh
```

### 7.3 指定 Python、端口和地址

```bash
RADAR_API_PYTHON=/path/to/python \
RADAR_API_HOST=0.0.0.0 \
RADAR_API_PORT=8000 \
RADAR_UI_HOST=0.0.0.0 \
RADAR_UI_PORT=5173 \
./scripts/start_radar_workbench.sh
```

### 7.4 验证命令

后端健康检查：

```bash
python - <<'PY'
import requests
for name, url in [
    ("health", "http://127.0.0.1:8000/api/health"),
    ("campaigns", "http://127.0.0.1:8000/api/campaigns"),
    ("ui", "http://127.0.0.1:5173/"),
]:
    r = requests.get(url, timeout=10)
    print(name, r.status_code, len(r.content))
PY
```

后端测试：

```bash
cd services/radar_api
python -m pytest -q
```

前端构建：

```bash
npm -C apps/radar-workbench run build
```

## 8. 输出数据结构

### 8.1 既有离线 campaign

主路径：

```text
outputs/sionna_radar_campaigns/C002_full_radar_sensing/
```

关键文件：

| 文件 | 功能 |
|---|---|
| `reports/POSE_METRICS.csv` | 每个测点/run 的位置、指向、路径数、FoV 能量等指标。 |
| `reports/runs_index.csv` | run 索引，后端也可使用。 |
| `reports/CAMPAIGN_SUMMARY.md` | campaign 文字总结。 |
| `runs/<run_id>/config.yaml` | 该 run 的完整仿真配置。 |
| `runs/<run_id>/metadata.json` | 环境、设备位置、阵列、材料、场景几何。 |
| `runs/<run_id>/metrics.json` | 路径统计、雷达观测统计、图像路径。 |
| `runs/<run_id>/paths_summary.npz` | Sionna 路径级数据摘要。 |
| `runs/<run_id>/paths_per_element.npz` | `synthetic_array=false` 时的逐收发阵元路径元数据；合成阵列模式下不生成。 |
| `runs/<run_id>/cir.npz` | 复数 CIR 数据，体积较大，浏览器默认不加载。 |
| `runs/<run_id>/radar_observation.npz` | 后处理雷达观测，包括 FoV mask 和距离-角度谱。 |
| `runs/<run_id>/figures/*.png` | 原始诊断图。 |

### 8.2 Web 生成 campaign

主路径：

```text
outputs/radar_workbench/campaigns/<job_id>/
```

关键文件：

| 文件 | 功能 |
|---|---|
| `campaign_manifest.json` | Web campaign 元信息、run_id 列表和原始请求。 |
| `pose_manifest.json` | 每个 pose 对应的位置和指向。 |
| `reports/POSE_METRICS.csv` | 新仿真的 run 指标表。 |
| `reports/runs_index.csv` | 新仿真的 run 索引。 |
| `runs/<run_id>/...` | 与离线 run 相同结构的原始输出。 |

### 8.3 Web 缓存

主路径：

```text
outputs/radar_workbench/web_cache/<run_id>/
```

关键文件：

| 文件 | 功能 |
|---|---|
| `manifest.json` | 缓存生成时间、来源 run、源文件大小和修改时间。 |
| `scene_objects.json` | 前端三维建筑显示所需对象。 |
| `radar_pose.json` | 雷达位置、方向和 FoV。 |
| `top_paths.json` | 前端显示的高能路径、交互点和路径折线。 |
| `first_interactions.parquet` | 交互点表，用于统计和可视化。 |
| `range_azimuth.json` | 距离-方位角谱元数据。 |
| `range_azimuth.bin` | 距离-方位角谱 `float32` 二进制矩阵。 |
| `range_elevation.json` | 距离-俯仰角谱元数据。 |
| `range_elevation.bin` | 距离-俯仰角谱 `float32` 二进制矩阵。 |

Web 缓存可以重新生成，因此迁移时不是必须保存。但是保存它可以加快首次打开速度。

### 8.4 路径导出

主路径：

```text
outputs/radar_workbench/path_exports/<export_id>/
```

关键文件：

| 文件 | 功能 |
|---|---|
| `manifest.json` | 导出 ID、源 run、筛选条件、文件列表。 |
| `paths.json` | 导出的路径、交互点、路径折线、能量和角度。 |
| `path_summary.csv` | 便于表格软件或 Python 读取的路径摘要。 |
| `radar_config.json` | 导出时的前端雷达草稿配置和源配置。 |
| `run_metadata.json` | 源 run 的配置、元数据和指标。 |

### 8.5 任务状态

主路径：

```text
outputs/radar_workbench/jobs/<job_id>/
```

关键文件：

| 文件 | 功能 |
|---|---|
| `job.json` | 前端提交的完整请求。 |
| `status.json` | 当前任务状态、进度、结果或错误。 |
| `task_manifest.json` | 任务列表。 |
| `worker_events.jsonl` | worker 启动、完成、失败事件。 |
| `logs.txt` | 错误堆栈和人工排查日志。 |

## 9. 如何获取数据

### 9.1 从前端获取

适合人工核查：

1. 启动服务。
2. 打开 `http://127.0.0.1:5173`。
3. 在左侧选择 campaign 和 run。
4. 在中间查看三维路径、距离-角度谱和统计面板。
5. 如需归档路径，点击右侧“保存路径”。
6. 到 `outputs/radar_workbench/path_exports/<export_id>/` 读取 JSON 或 CSV。

### 9.2 从 API 获取

列出 campaign：

```bash
curl http://127.0.0.1:8000/api/campaigns
```

列出某个 campaign 的 run：

```bash
curl http://127.0.0.1:8000/api/campaigns/c002_full_existing/runs
```

获取 run 元数据：

```bash
curl http://127.0.0.1:8000/api/results/<run_id>/metadata
```

获取高能路径：

```bash
curl "http://127.0.0.1:8000/api/results/<run_id>/paths?top_k=1000&kind=all&in_fov=true"
```

获取交互点：

```bash
curl "http://127.0.0.1:8000/api/results/<run_id>/interactions?top_k=2000&in_fov=true"
```

获取距离-方位角谱元数据：

```bash
curl http://127.0.0.1:8000/api/results/<run_id>/range_azimuth
```

随后按返回的 `array_url` 下载二进制矩阵。该矩阵是 row-major `float32`，shape 在 JSON 元数据里给出。

### 9.3 直接读取原始文件

适合批处理分析：

```python
from pathlib import Path
import json
import numpy as np
import pandas as pd

run_dir = Path("outputs/sionna_radar_campaigns/C002_full_radar_sensing/runs/<run_id>")

metrics = json.loads((run_dir / "metrics.json").read_text())
paths = np.load(run_dir / "paths_summary.npz")
obs = np.load(run_dir / "radar_observation.npz")
cir = np.load(run_dir / "cir.npz")

ranges_m = obs["ranges_m"]
aoa_azimuth_deg = obs["aoa_azimuth_deg"]
aoa_elevation_deg = obs["aoa_elevation_deg"]
fov_mask = obs["fov_path_mask"]
path_energy = obs["path_energy"]
range_azimuth_power = obs["range_azimuth_power"]

print(metrics["radar_observation"])
print(ranges_m.shape, range_azimuth_power.shape)
```

读取路径导出的 CSV：

```python
import pandas as pd

df = pd.read_csv("outputs/radar_workbench/path_exports/<export_id>/path_summary.csv")
print(df.head())
```

### 9.4 从前端提交新仿真

适合交互式实验：

1. 设置雷达中心、指向点、方位宽度、俯仰范围、最大距离。
2. 设置频率、带宽、散射模型、反射阶数和阵列。
3. 设置 GPU ID，默认 `[0, 1, 2, 3]`。
4. 点击运行仿真。
5. 完成后在左侧选择新 campaign 或等待界面自动加载。

提交后数据位置：

```text
outputs/radar_workbench/campaigns/<job_id>/
outputs/radar_workbench/jobs/<job_id>/
outputs/radar_workbench/web_cache/<run_id>/
```

### 9.5 从命令行提交 API 仿真

可以直接构造 JSON 调用 `POST /api/simulations`。示例骨架：

```bash
curl -X POST http://127.0.0.1:8000/api/simulations \
  -H 'content-type: application/json' \
  -d '{
    "scene_id": "simple_street_canyon",
    "mode": "single_pose",
    "radar": {
      "center_m": [-60.0, -5.0, 10.0],
      "look_at_m": [-30.0, -5.0, 10.0],
      "tx_rx_baseline_m": 0.1,
      "az_width_deg": 120.0,
      "el_min_deg": 0.0,
      "el_max_deg": 40.0,
      "rmax_m": 200.0,
      "range_bin_m": 0.15,
      "angle_bin_deg": 2.0
    },
    "propagation": {
      "frequency_hz": 28000000000.0,
      "bandwidth_hz": 1000000000.0
    },
    "scattering": {
      "enabled": true,
      "coefficient": 0.5,
      "pattern": "backscattering",
      "alpha_r": 20,
      "alpha_i": 20,
      "lambda_": 0.3
    },
    "tx_array": {
      "num_rows": 1,
      "num_cols": 1,
      "vertical_spacing": 0.5,
      "horizontal_spacing": 0.5,
      "pattern": "iso",
      "polarization": "V"
    },
    "rx_array": {
      "num_rows": 16,
      "num_cols": 16,
      "vertical_spacing": 0.5,
      "horizontal_spacing": 0.5,
      "pattern": "iso",
      "polarization": "V"
    },
    "path_solver": {
      "max_depth": 2,
      "max_num_paths_per_src": 1000000,
      "samples_per_src": 500000,
      "synthetic_array": true,
      "los": false,
      "specular_reflection": true,
      "diffuse_reflection": true,
      "refraction": false,
      "diffraction": false,
      "edge_diffraction": false,
      "seed": 501
    },
    "observation": {},
    "compute": {
      "samples_per_src": 500000,
      "seed": 501
    },
    "gpu_ids": [0, 1, 2, 3]
  }'
```

返回 `job_id` 后查询：

```bash
curl http://127.0.0.1:8000/api/simulations/<job_id>
```

## 10. 迁移方案

迁移时要先决定迁移级别。

### 10.1 迁移级别

| 级别 | 包含内容 | 适用情况 |
|---|---|---|
| 代码迁移 | 源码、配置、文档，不包含大体量 `outputs/`。 | 只需要继续开发或重新跑实验。 |
| 轻量数据迁移 | 源码，加上 `reports/`、`path_exports/` 和少量代表 run。 | 只做演示和核查。 |
| 完整数据迁移 | 源码，加上所有 `outputs/`。 | 需要完整复现实验和继续分析。 |
| 缓存迁移 | 同时迁移 `outputs/radar_workbench/web_cache/`。 | 希望首次打开 Web 很快。 |

建议论文或项目归档使用“完整数据迁移”。如果磁盘有限，可不迁移 Web 缓存，因为它能重建。

### 10.2 迁移前清理运行状态

在源机器上停止服务：

```bash
./scripts/stop_radar_workbench.sh
```

确认没有正在运行的 Sionna job：

```bash
find outputs/radar_workbench/jobs -name status.json -print
```

如果有 `status` 为 `running` 的 job，建议等待完成或明确记录为未完成。

### 10.3 推荐复制命令

完整迁移，保留 outputs，但不复制依赖缓存和构建产物：

```bash
rsync -a --info=progress2 \
  --exclude 'apps/radar-workbench/node_modules/' \
  --exclude 'apps/radar-workbench/dist/' \
  --exclude '**/__pycache__/' \
  --exclude '.pytest_cache/' \
  /home/DataDisk/plzheng/radar_simulate/ \
  <target-host>:/path/to/radar_simulate/
```

代码迁移，不复制 outputs：

```bash
rsync -a --info=progress2 \
  --exclude 'outputs/' \
  --exclude 'apps/radar-workbench/node_modules/' \
  --exclude 'apps/radar-workbench/dist/' \
  --exclude '**/__pycache__/' \
  /home/DataDisk/plzheng/radar_simulate/ \
  <target-host>:/path/to/radar_simulate/
```

轻量数据迁移示例：

```bash
rsync -a --info=progress2 \
  --exclude 'apps/radar-workbench/node_modules/' \
  --exclude 'apps/radar-workbench/dist/' \
  --exclude 'outputs/radar_workbench/web_cache/' \
  --exclude '**/__pycache__/' \
  /home/DataDisk/plzheng/radar_simulate/ \
  <target-host>:/path/to/radar_simulate/
```

### 10.4 新机器环境准备

Python 环境需要满足：

- Python 3.10 或更高。
- 独立的 Sionna RT 2.x、Mitsuba、Dr.Jit 仿真运行时。
- FastAPI 后端依赖：`fastapi`、`uvicorn`、`pydantic`、`pandas`、`numpy`、`pyarrow`、`pyyaml`。
- NVIDIA 驱动和 CUDA 环境能够被 Sionna RT/Mitsuba 使用。

后端依赖安装：

```bash
cd services/radar_api
python -m pip install -e .
```

Sionna RT 与 FastAPI 后端使用不同 Python 环境。当前默认运行时为：

```text
/home/Users_Work_Space/plzheng/miniconda3/envs/sionna-rt2/bin/python
sionna-rt 2.0.1
```

直接依赖锁定在 `experiments/sionna_radar/requirements-runtime.txt`。运行时应保持 `PYTHONNOUSERSITE=1`，避免混入 `~/.local` 中的 Mitsuba 或 Dr.Jit。

前端环境需要：

- Node.js 和 npm。
- 与 Vite 7 兼容的 Node 版本，建议使用较新的 LTS 版本。

前端依赖安装：

```bash
npm -C apps/radar-workbench install
```

### 10.5 路径和环境变量

后端配置会根据当前仓库位置自动推断根目录，因此搬到新路径后通常不需要修改代码。

如果 Python 不在默认位置，用：

```bash
RADAR_API_PYTHON=/path/to/python ./scripts/start_radar_workbench.sh
RADAR_SIONNA_PYTHON=/path/to/sionna-python ./scripts/start_radar_workbench.sh
```

如果前后端部署在不同机器：

```bash
RADAR_API_HOST=0.0.0.0 RADAR_UI_HOST=0.0.0.0 ./scripts/start_radar_workbench.sh
```

前端开发服务访问远端后端时：

```bash
VITE_RADAR_API_BASE=http://<backend-host>:8000 npm -C apps/radar-workbench run dev -- --host 0.0.0.0
```

注意：`app/main.py` 当前 CORS 只允许 `localhost:5173` 和 `127.0.0.1:5173`。如果远程浏览器直接访问非本机地址，需要在 `services/radar_api/app/main.py` 中加入对应前端 origin。

### 10.6 迁移后重建缓存

如果迁移了原始 run，但没有迁移 Web 缓存，直接打开前端选择 run 即可触发自动缓存生成。

也可以手动重建某个 run：

```bash
cd services/radar_api
python -m app.core.web_cache \
  --run-dir ../../outputs/sionna_radar_campaigns/C002_full_radar_sensing/runs/<run_id> \
  --out-root ../../outputs/radar_workbench/web_cache
```

如果迁移后发现图像或谱图异常，先删除缓存再重新打开：

```bash
rm -rf outputs/radar_workbench/web_cache/<run_id>
```

### 10.7 迁移后验证

1. 检查目录：

```bash
test -d apps/radar-workbench
test -d services/radar_api
test -d experiments/sionna_radar
```

2. 检查已有 C002 数据是否存在：

```bash
test -f outputs/sionna_radar_campaigns/C002_full_radar_sensing/reports/POSE_METRICS.csv
```

3. 启动服务：

```bash
./scripts/start_radar_workbench.sh
```

4. 检查 API：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/campaigns
```

5. 检查前端：

```bash
curl -I http://127.0.0.1:5173/
```

6. 构建前端：

```bash
npm -C apps/radar-workbench run build
```

7. 后端测试：

```bash
cd services/radar_api
python -m pytest -q
```

8. 选择一个 run 打开路径和谱图，确认：

- 三维建筑能显示。
- 雷达位置和 FoV 能显示。
- 距离-方位角谱能显示。
- 路径列表和交互点能加载。
- 保存路径后 `outputs/radar_workbench/path_exports/` 出现新目录。

## 11. 常见问题

### 11.1 API 显示 degraded

`/api/health` 中 `existing_campaign_available=false` 通常说明：

```text
outputs/sionna_radar_campaigns/C002_full_radar_sensing
```

没有迁移或路径不正确。若只需要运行新仿真，可以暂时忽略；若要浏览 C002，必须补齐该目录。

### 11.2 前端空白或无法加载谱图

检查：

- 后端是否启动。
- `VITE_RADAR_API_BASE` 是否指向正确地址。
- 浏览器控制台是否有 CORS 错误。
- `outputs/radar_workbench/web_cache/<run_id>/` 是否能生成。

### 11.3 路径图和谱图看起来与新参数不一致

如果修改了雷达位置、方向、FoV、频率或散射参数，必须重新运行仿真。不能把旧 run 的路径解释为新参数下的路径。

前端已经在参数变更后阻止直接保存旧路径，但人工读取文件时仍需要注意这一点。

### 11.4 后处理 FoV 是否能代表天线方向图

不能。它只代表从全向路径集合中筛选指定视场角内的回波。要研究真实天线方向图，需要使用物理方向图或接收阵列波束形成，并重新运行或重新处理对应数据。

### 11.5 Web 缓存中的路径是旧绝对路径怎么办

删除对应缓存目录，让后端重建即可：

```bash
rm -rf outputs/radar_workbench/web_cache/<run_id>
```

### 11.6 大文件如何归档

必须归档的原始数据：

- `config.yaml`
- `metadata.json`
- `metrics.json`
- `paths_summary.npz`
- `radar_observation.npz`
- `cir.npz`
- `reports/POSE_METRICS.csv`
- `reports/runs_index.csv`

可重建或可选数据：

- `outputs/radar_workbench/web_cache/`
- `apps/radar-workbench/dist/`
- `apps/radar-workbench/node_modules/`
- Python `__pycache__/`

建议长期归档时保留 `cir.npz`，因为它是通道响应原始数据。若只做轻量展示，可以不带 `cir.npz`，但这样后续无法重新做完整 CIR 分析。

## 12. 推荐交接清单

交接给新使用者时，至少提供：

- 仓库源码。
- 本文档。
- `refine-logs/EXPERIMENT_PLAN.md`
- `refine-logs/MULTI_MEASUREMENT_ISAC_PLAN.md`
- `refine-logs/MULTI_MEASUREMENT_ISAC_TRACKER.md`
- `refine-logs/web-radar-workbench/13_IMPLEMENTATION_LOG.md`
- 需要复现的 `outputs/` 数据。
- Python 环境说明或 `pip freeze`。
- GPU/CUDA/Sionna 版本说明。

建议在源机器记录环境：

```bash
python -V
python -m pip freeze > outputs/radar_workbench/PIP_FREEZE.txt
nvidia-smi > outputs/radar_workbench/NVIDIA_SMI.txt
node -v > outputs/radar_workbench/NODE_VERSION.txt
npm -v > outputs/radar_workbench/NPM_VERSION.txt
git log --oneline --decorate -20 > outputs/radar_workbench/GIT_HISTORY_HEAD.txt
```

这些文件在完整归档时很有价值，但注意 `outputs/` 默认不进入 Git，需要单独复制或打包。
