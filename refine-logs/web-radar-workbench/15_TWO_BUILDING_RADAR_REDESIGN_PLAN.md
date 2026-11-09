# 两楼远距雷达实验与专业化工作台重构规划

日期：2026-07-05  
状态：规划，不实施代码  
原则：当前仍处开发阶段，不做错误旧接口兼容；凡是术语、数据含义、界面行为不专业的地方直接改正。

## 1. 结论先行

用户提出的实验可以基于当前平台继续发展实现：

- 一个雷达站，自发自收。
- 目标建筑位于 400-500 m 远处。
- 场景包含两个建筑。
- 建筑高度可配置为 60 m、100 m、120 m 等。
- 雷达发射后，统计有效传播路径总数、分析门限内路径数、按建筑物归属的路径数、按交互阶数和交互类型的路径数。
- 保存每条路径的延迟、单站距离、到达角、离开角、路径能量、交互点、交互对象、交互类型。
- 通过浏览器下载完整结果包。

但是有一个必须修正的专业问题：

如果雷达主波束仰角固定为 40 度，楼在 400-500 m 远、雷达高度约 10 m、楼高 60-120 m，则主轴高度约为：

```text
z_axis(d) = z_radar + d * tan(40 deg)
```

在 450 m 处约为 `10 + 450*tan(40 deg) ≈ 388 m`，远高于 60-120 m 建筑。此时主波束大概率越过楼体，除非雷达位于很低/很特殊几何、建筑更高，或 40 度指的是覆盖上界而不是主轴仰角。

因此实验设计应改为：

1. **主轴指向建筑外立面中心、屋顶边缘或指定散射点**。
2. **40 度作为俯仰覆盖上界或可调扫描上界**，而不是默认主轴仰角。
3. 若必须研究主轴 40 度，应明确该设置是在验证“高仰角波束越过低矮建筑导致回波减少”的现象。

## 2. 官方能力依据

本计划基于 Sionna RT 官方能力：

- Sionna RT 可加载和编辑场景，能通过 `SceneObject` 和 `Scene.edit()` 添加对象；官方 Scene-Edit 教程演示了加载场景、增加对象、设置 Tx/Rx、调用 `PathSolver` 并渲染路径。
- `PathSolver` 返回 `Paths`，路径包含信道系数、时延、AoD、AoA；路径还可以用于 `render()`、`preview()` 可视化。
- `Paths.cir()` 可获得 CIR，用于链路级和阵列后处理。
- `PlanarArray` 用于配置 Tx/Rx 阵列；官方说明所有 Tx 和所有 Rx 分别使用 `scene.tx_array` 与 `scene.rx_array`。
- `AntennaPattern` 是单极化或双极化的方向图定义；`PlanarArray` 的 pattern/polarization 是阵列级配置，不是逐阵元独立设置。

因此：

- 几何传播路径、反射/散射交互点和路径数量统计是 Sionna RT 的适配方向。
- 自定义数字波束成形向量更适合在 `cir.npz` 的阵列维度上后处理完成，而不是把它误称为 `FoV`。
- 自定义物理天线方向图属于 `AntennaPattern` 层，应与后处理角域门限分开。

## 3. 当前系统主要问题

### 3.1 左侧栏语义不清

当前左侧栏实际是 campaign/run 选择器，但界面没有清楚表达：

- 哪些是历史实验。
- 哪些是只读既有数据。
- 哪些是刚刚运行的新实验。
- 实验配置是否完整保留。
- 当前显示结果是否对应右侧编辑器中的参数。

这会导致用户感觉它是“一次性列表”或“临时东西”。

### 3.2 历史实验保存过于简陋

当前保存 run 的方式基本依赖：

- `campaign_manifest.json`
- `pose_manifest.json`
- `reports/POSE_METRICS.csv`
- run 目录下的配置和结果

这对程序可读是够的，但对“浏览器中查看历史实验、复查配置、下载结果包、比较版本”不够。

### 3.3 FoV 概念和波束概念混杂

当前系统里有：

- 后处理 AoA/距离门控。
- `tr38901` 方向图近似。
- 三维 FoV 框。

三者容易被误读成同一个东西。专业上必须分成：

| 名称 | 是否物理传播仿真输入 | 作用 |
|---|---:|---|
| 天线单元方向图 | 是 | 影响 Sionna 路径系数。 |
| 数字波束成形权向量 | 后处理或链路处理 | 对阵列 CIR 加权，得到某个波束下的回波。 |
| 角域/距离分析门限 | 否 | 从结果中筛选路径或统计范围。 |
| 三维波束显示体 | 可视化 | 展示主轴、波束宽度和距离范围。 |

### 3.4 三维显示体形式需要修正

当前三维视图显示的是类似四棱锥/线框的 FoV frustum。它不是严格物理波束。

更专业做法：

- 若使用“方位半功率宽度 + 俯仰半功率宽度”，可以显示椭圆锥或角域锥体。
- 若使用阵列波束图，应显示主瓣方向、半功率波束宽度、旁瓣可选轮廓。
- 若只是分析门限，应标注为“角域分析边界”，不能显示成真实发射波束。

### 3.5 结果图重复且用途不统一

当前存在原始诊断图和前端谱图可能重复的问题。未来必须做到：

- 每种图只保留一种主用途。
- 不显示 smoke 图。
- 不显示无解释的旧诊断图。
- 每张图必须有明确物理量、坐标轴、颜色含义和用途。

### 3.6 旧版接口不应继续兼容

当前仍有 `campaign`、`fov_energy_fraction`、`postprocess_fov` 等概念在接口和 UI 里交织。开发阶段不需要兼容旧版，应直接重构为正确的模型：

- `experiment` 表示一次完整实验配置。
- `run` 表示一个配置下的一次仿真执行。
- `analysis` 表示对 run 的后处理分析。
- `result_bundle` 表示可下载归档包。

## 4. 两楼远距实验设计

### 4.1 实验名称

建议命名：

```text
TB-FAR-001: two-building far-range monostatic radar path counting
```

中文名：

```text
两楼远距单站雷达路径统计实验
```

### 4.2 目标问题

回答：

1. 雷达向 400-500 m 远处两个建筑发射信号后，Sionna RT 能得到多少条有效传播路径？
2. 这些路径中有多少条来自建筑 A、建筑 B、地面或多建筑交互？
3. 路径数量和能量如何随建筑高度 60/100/120 m 变化？
4. 路径数量和能量如何随主轴俯仰角、波束宽度、散射模型、反射阶数变化？
5. 接收阵列采用不同波束成形权向量后，路径能量和距离-角度谱如何变化？

### 4.3 建议坐标系

采用 Sionna/Mitsuba 场景坐标：

```text
x: 东向或前向，单位 m
y: 横向，单位 m
z: 高度，单位 m
```

雷达站：

```text
radar_center = [0, 0, 10] m
tx_rx_baseline = 0.1 m
tx/rx small baseline perpendicular to boresight
```

建筑候选布局：

```text
building_A_center = [430, -35, H_A/2]
building_B_center = [480,  45, H_B/2]
building_size_A   = [45, 30, H_A]
building_size_B   = [55, 35, H_B]
H_A, H_B in {60, 100, 120} m
```

地面：

```text
ground plane size >= 800 m x 400 m
material = concrete/asphalt
```

材料：

```text
building material = concrete or brick
ground material   = asphalt/concrete
scattering_coefficient sweep = 0.2, 0.5, 0.8
scattering_pattern = backscattering as main; lambertian/directive as controls
```

### 4.4 主轴角度设计

建筑中心高度：

```text
target_z = H / 2
target_range_xy = 400-500 m
boresight_elevation = atan2(target_z - radar_z, target_range_xy)
```

典型值：

| H | target_z | radar_z | range_xy | 指向楼体中心的俯仰角 |
|---:|---:|---:|---:|---:|
| 60 m | 30 m | 10 m | 450 m | 约 2.5 deg |
| 100 m | 50 m | 10 m | 450 m | 约 5.1 deg |
| 120 m | 60 m | 10 m | 450 m | 约 6.3 deg |

所以主轴不应默认设为 40 deg。建议扫描：

```text
boresight_elevation = [0, 3, 6, 10, 20, 40] deg
```

其中：

- 0/3/6/10 deg 是真实照射楼体主实验。
- 20/40 deg 是高仰角消融，用于证明角度几何是否会越过建筑。

### 4.5 覆盖范围和波束显示

把原先“FoV”拆为两类：

1. **波束参数**：

```text
boresight_azimuth_deg
boresight_elevation_deg
azimuth_beamwidth_deg
elevation_beamwidth_deg
range_max_m
beam_model = isotropic | tr38901 | custom_array_beam
```

2. **分析门限**：

```text
analysis_azimuth_gate_deg
analysis_elevation_gate_deg
analysis_range_max_m
analysis_min_path_power_db
```

如果使用后处理门限，界面必须叫“分析门限”，不能叫“天线波束”。

### 4.6 PathSolver 设置

主实验：

```text
frequency_hz = 28e9
bandwidth_hz = 1e9
tx_array = 1x1
rx_array = 16x16
los = false
specular_reflection = true
diffuse_reflection = true
max_depth = 2
samples_per_src = 5e5 initially; convergence sweep up to 1e6 or 2e6
synthetic_array = true initially
```

注意：

- `los=false` 是为了避免 Tx/Rx 小基线自泄漏主导结果。
- 400-500 m 场景比当前街谷更大，`rmax_m` 至少应设为 800-1200 m。
- 路径数量依赖 `samples_per_src` 和 diffuse scattering 抽样，不能把一次随机种子下的 diffuse path count 当成绝对物理常数。
- 报告必须记录 seed、samples_per_src、max_depth、散射系数和功率阈值。

## 5. 路径统计定义

### 5.1 原始路径数

```text
raw_path_count = paths.valid 中有效路径数量
```

对应“PathSolver 找到多少条有效路径”。

### 5.2 分析门限内路径数

```text
analysis_path_count = raw paths 中满足角域、距离、功率门限的路径数
```

这是用户问“雷达打过去能收到多少条径”时更接近工程意义的数量，因为它排除极远、极弱、非关注方向的路径。

### 5.3 建筑归属路径数

每条路径保存所有交互对象：

```text
path_id
interaction_depth
interaction_type = specular | diffuse | diffraction | refraction
object_id = building_A | building_B | ground | other
position_m = [x, y, z]
```

统计：

```text
paths_touching_building_A
paths_touching_building_B
paths_touching_both_buildings
paths_touching_ground
paths_with_first_interaction_A
paths_with_first_interaction_B
```

### 5.4 交互阶数统计

```text
depth_0: direct/LoS; 主实验应关闭或单独标记
depth_1: 一次反射/散射
depth_2: 二次反射/散射
```

统计：

```text
path_count_by_depth
path_energy_by_depth
path_count_by_interaction_type
path_energy_by_interaction_type
```

### 5.5 波束成形后路径能量

从 `cir.npz` 读取 per-antenna CIR：

```text
a[rx, rx_ant, tx, tx_ant, path, time]
```

对每条路径构造阵列响应后处理：

```text
h_p = H[:, :, p]          # Rx x Tx for path p
y_p = w_rx^H h_p w_tx
beamformed_path_power_p = |y_p|^2
```

当前 Tx 为 1x1 时：

```text
y_p = w_rx^H h_rx_p
```

如果未来 Tx 也变成阵列，则同时支持 Tx/Rx 权重。

## 6. 自定义波束成形设计

### 6.1 必须支持的波束模式

| 模式 | 名称 | 实现方式 | 用途 |
|---|---|---|---|
| `uniform` | 等幅同相合成 | 所有 Rx 端口同相归一化 | 基线 |
| `steering_vector` | 指定方位/俯仰导向矢量 | 按阵列几何生成相位 | 主实验 |
| `dft_codebook` | 二维 DFT 波束码本 | 16x16 阵列生成方位/俯仰波束网格 | 波束扫描 |
| `custom_complex_weights` | 用户自定义复权重 | 上传或编辑复数权重矩阵 | 高级实验 |
| `polarization_weighted` | 极化端口加权 | VH/cross 端口分别加权 | 极化扩展 |

### 6.2 权重保存格式

```json
{
  "beamforming": {
    "rx_mode": "steering_vector",
    "rx_array_shape": [16, 16],
    "polarization_ports": ["V"],
    "steering_azimuth_deg": 0.0,
    "steering_elevation_deg": 5.0,
    "normalization": "unit_norm",
    "weights_format": "complex_interleaved",
    "weights": [[real, imag], ...]
  }
}
```

### 6.3 输出数据

```text
beamformed_paths.npz
beamformed_range_profile.npz
beam_sweep_range_azimuth.npz
beam_sweep_summary.csv
```

指标：

```text
beamformed_path_count_above_threshold
beamformed_energy_total
beamformed_energy_by_building
main_beam_peak_range_m
main_beam_peak_angle_deg
```

## 7. 场景建模重构

### 7.1 新增场景类型

```text
scene_kind = parametric_two_buildings
```

配置：

```json
{
  "scene": {
    "kind": "parametric_two_buildings",
    "ground": {
      "size_m": [900, 500],
      "material": "itu_concrete"
    },
    "buildings": [
      {
        "id": "building_A",
        "center_m": [430, -35, 30],
        "size_m": [45, 30, 60],
        "material": "itu_concrete"
      },
      {
        "id": "building_B",
        "center_m": [480, 45, 50],
        "size_m": [55, 35, 100],
        "material": "itu_concrete"
      }
    ]
  }
}
```

### 7.2 场景文件产物

每次实验保存：

```text
outputs/radar_workbench/experiments/<experiment_id>/
  input/
    experiment_config.json
    scene_config.json
    scene.mitsuba.xml
    meshes/
      building_A.ply
      building_B.ply
      ground.ply
  runs/<run_id>/
```

如果直接在 Python 内创建 scene，也必须保存等价的 `scene_config.json` 和可复建 mesh/xml，确保迁移后可复现。

## 8. API 重构规划

### 8.1 废弃旧概念

不继续扩展这些旧概念：

```text
/api/campaigns
campaign_id 作为主用户概念
fov_energy_fraction 作为主指标
postprocess_fov 作为方向图选项
```

可以在代码迁移期间直接删除或重命名，不提供兼容层。

### 8.2 新 API

```text
GET  /api/health
POST /api/experiments
GET  /api/experiments
GET  /api/experiments/{experiment_id}
POST /api/experiments/{experiment_id}/runs
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/paths
GET  /api/runs/{run_id}/interactions
GET  /api/runs/{run_id}/spectra/range
GET  /api/runs/{run_id}/spectra/range_azimuth
GET  /api/runs/{run_id}/spectra/range_elevation
GET  /api/runs/{run_id}/beamforming
POST /api/runs/{run_id}/beamforming
POST /api/runs/{run_id}/analysis
GET  /api/runs/{run_id}/result_bundle
GET  /api/runs/{run_id}/result_bundle.zip
```

### 8.3 数据对象

`ExperimentConfig`：

```text
experiment_id
name
created_at
scene
radar
waveform
tx_array
rx_array
antenna_pattern
beamforming
propagation
path_solver
analysis_gates
output_policy
```

`RunResult`：

```text
run_id
experiment_id
config_snapshot
status
started_at
completed_at
metrics
artifacts
```

`ResultBundle`：

```text
manifest.json
experiment_config.json
run_config.yaml
scene_config.json
scene_geometry.json
metrics.json
paths.csv
paths.json
interactions.csv
building_path_statistics.csv
beamforming_config.json
beamformed_statistics.csv
spectra/*.npz
figures/*.png
```

## 9. 浏览器界面重构规划

### 9.1 左侧栏重新定义

左侧栏不再是模糊的 campaign/run 列表，而是“实验管理器”。

结构：

```text
新建实验
实验列表
  - 草稿
  - 运行中
  - 已完成
  - 失败
筛选
  - 时间
  - 场景类型
  - 频率
  - 建筑高度组合
  - 波束模式
```

每个历史实验卡片显示：

```text
实验名称
创建时间
场景摘要：两楼，高度 60/100 m，距离 430/480 m
雷达摘要：位置、主轴方位/俯仰、频率
求解摘要：max_depth、samples_per_src、seed
状态：草稿/运行中/完成/失败
路径数：总路径、分析门限内路径、建筑 A/B 路径数
下载按钮
```

### 9.2 主界面布局

建议布局：

```text
左：实验管理器
中：三维场景与结果可视化
右：配置面板 / 结果面板切换
底：任务状态与下载区
```

中间视图区：

- 3D 场景。
- 雷达位置可拖动。
- 指向点可拖动。
- 建筑位置和高度可编辑。
- 波束锥体或分析门限锥体可显示/隐藏。
- 路径线和交互点可按类型/建筑/能量筛选。

右侧配置区分 Tab：

```text
场景
雷达
阵列与波束成形
传播与散射
求解器
分析门限
结果下载
```

### 9.3 雷达位置与方向拖动

三维交互要求：

- 雷达中心点支持拖动。
- 指向点支持拖动。
- 拖动后实时更新主轴方位角、主轴俯仰角。
- 参数变化后必须标记“结果已过期，需要重新仿真”。
- 不允许把旧路径解释为新位姿下的路径。

二维辅助视图：

- 顶视图拖动 x/y。
- 侧视图拖动高度和俯仰角。
- 建筑高度用数值输入和拖动顶面共同控制。

### 9.4 三维波束显示

显示模式：

| 模式 | 几何显示 | 标签 |
|---|---|---|
| 各向同性 | 不显示波束，或显示淡色全向球壳 | 各向同性传播 |
| 物理方向图 | 显示主瓣方向与近似半功率锥 | 天线方向图近似 |
| 数字波束成形 | 显示阵列合成主瓣方向和波束宽度 | 阵列波束 |
| 分析门限 | 显示虚线角域边界 | 后处理分析门限 |

不再用含糊的“等效窗口”之类术语。

## 10. 结果图设计

只保留有明确用途的图。

### 10.1 必备图

| 图 | 用途 | 坐标/标记 |
|---|---|---|
| 三维几何与路径图 | 看雷达、楼、波束、路径、交互点 | 3D 坐标；路径颜色按交互类型；交互点按对象着色 |
| 路径表 | 精确查看每条路径 | path_id、距离、时延、能量、AoA/AoD、交互对象 |
| 路径数统计图 | 回答“收到多少条径” | 按建筑、交互阶数、交互类型分组 |
| 路径能量统计图 | 看主要回波来自哪里 | 按建筑、交互类型、波束成形前后 |
| 距离像 | 估计回波距离分布 | x=单站距离，y=功率或路径数 |
| 距离-方位角谱 | 看水平到达角和距离 | x=AoA 方位角，y=单站距离，色=功率 |
| 距离-俯仰角谱 | 看垂直到达角和距离 | x=AoA 俯仰角，y=单站距离，色=功率 |
| 波束扫描热力图 | 比较不同波束指向 | x=波束方位，y=波束俯仰，色=接收能量或路径数 |
| 高度扫描对比图 | 研究 60/100/120 m 高度影响 | x=高度组合，y=路径数/能量 |

### 10.2 不应显示的图

- smoke 图。
- 与主谱图重复的原始 PNG。
- 没有解释的 AoA/range 散点图。
- 与雷达物理无关的“窗口”类图。
- 只服务开发调试、不服务实验解释的图。

如需要保留调试图，应放在 `debug/` 下载包里，不在主界面展示。

## 11. 历史实验与下载设计

### 11.1 历史实验必须不可变

一次 run 完成后保存：

```text
config_snapshot.json
scene_config.json
solver_config.json
beamforming_config.json
analysis_config.json
```

历史实验查看时，右侧显示的是历史配置快照，不是当前草稿配置。

### 11.2 草稿与历史结果分离

状态：

```text
DraftConfig: 用户正在编辑，未必有结果
RunConfigSnapshot: 已运行配置，不可变
RunResult: 与快照绑定的结果
```

界面行为：

- 载入历史 run 时，显示“历史配置快照”。
- 点击“基于此结果新建草稿”才可编辑。
- 编辑草稿后结果区显示“尚未运行”。

### 11.3 下载包

浏览器提供：

```text
下载完整结果包 ZIP
下载路径 CSV
下载路径 JSON
下载统计 CSV
下载配置 JSON
下载图像 PNG
```

ZIP 结构：

```text
<experiment_id>_<run_id>_result_bundle.zip
  manifest.json
  configs/
  scene/
  raw/
  analysis/
  tables/
  figures/
  logs/
```

## 12. 实施阶段规划

### Phase 0：术语和数据模型纠偏

目标：

- 删除或重命名错误概念。
- 设计新 schema。
- 不做旧 API 兼容。

任务：

1. 把 `campaign` 主概念替换为 `experiment`。
2. 把 `postprocess_fov` 替换为 `analysis_gate`。
3. 把 `fov_energy_fraction` 替换为更明确的：
   - `analysis_gate_energy_fraction`
   - `beamformed_energy`
   - `path_count_in_analysis_gate`
4. 建立 `ExperimentConfig`、`RunConfigSnapshot`、`RunResult`、`ResultBundle`。

验收：

- API、前端类型、UI 文案中不再把后处理门限称为物理方向图。
- 没有 UE/通信 pass。

### Phase 1：两楼参数化场景生成

目标：

- 支持在浏览器中设置两个建筑的位置、尺寸、高度、材料。
- 后端生成可复现的 Sionna/Mitsuba 场景。

任务：

1. 实现 `parametric_two_buildings` scene builder。
2. 保存 `scene_config.json` 和 mesh/XML。
3. 确保 metadata 中 `object_id` 稳定为 `building_A`、`building_B`、`ground`。
4. 单元测试 bbox、高度、材料、object_id。

验收：

- 能创建 60/100/120 m 楼高组合。
- 场景加载后 metadata 能读出两个建筑的 bbox。

### Phase 2：路径统计与建筑归属

目标：

- 回答“收到多少条径”。

任务：

1. 从 `paths_summary.npz` 读取 valid、interactions、objects、vertices、tau、AoA/AoD。
2. 生成 `paths.csv` 和 `paths.json`。
3. 按 object_id 统计 building_A/building_B/ground 路径数。
4. 按 depth、interaction_type、energy threshold 统计。
5. 保存 `building_path_statistics.csv`。

验收：

- 每个 run 有路径总数、分析门限内路径数、建筑 A/B 路径数。
- 路径表能下载。

### Phase 3：波束成形后处理

目标：

- 支持自定义 Rx/Tx 波束权向量。

任务：

1. 读取 `cir.npz` 阵列维度。
2. 实现 Rx steering vector。
3. 实现 16x16 二维 DFT codebook。
4. 实现自定义复权重上传/编辑。
5. 输出波束成形后的路径能量、距离像、距离-角度谱和扫描热力图。

验收：

- 同一 run 不重新 ray tracing 即可切换 Rx 波束。
- 每个波束配置都有 `beamforming_config.json`。
- 波束扫描图能解释能量峰值来自哪个角度和建筑。

### Phase 4：前端三维交互重构

目标：

- 雷达位置、指向、建筑高度可交互设置。

任务：

1. 使用 3D transform control 或自定义拖拽控制雷达中心和指向点。
2. 建筑顶面可拖动改变高度。
3. 波束显示从线框 FoV 改为按模式显示的波束锥/分析门限虚线。
4. 交互点按建筑和类型筛选。
5. 路径按能量、建筑、交互阶数筛选。

验收：

- 拖动后参数面板同步变化。
- 参数变化后历史结果明确标记过期。
- 旧路径不会被显示成新参数结果。

### Phase 5：历史实验管理与下载包

目标：

- 左侧栏变成真正实验管理器。

任务：

1. 实现实验列表、草稿、运行中、完成、失败状态。
2. 每个实验显示配置摘要。
3. 历史 run 配置快照只读。
4. 支持“基于此结果新建草稿”。
5. 后端生成 ZIP 结果包。
6. 前端提供下载按钮。

验收：

- 重启服务后历史实验仍完整可查看。
- 下载 ZIP 后可离线分析。

### Phase 6：图表去重和专业解释

目标：

- 只保留有用途的图。

任务：

1. 删除主界面 smoke/debug 图。
2. 合并重复距离-角度图。
3. 每张图提供坐标轴、颜色、标记说明。
4. 图名使用专业中文和标准英文缩写。

验收：

- 主界面图表不重复。
- 任意图都能回答明确实验问题。

## 13. 验证实验矩阵

### 13.1 几何 sanity

| 实验 | 配置 | 预期 |
|---|---|---|
| G1 | 单楼 60 m，主轴指向楼中心 | 有一次反射/散射路径 |
| G2 | 单楼 60 m，主轴 40 deg | 路径数/能量显著降低 |
| G3 | 双楼 60/100 m，主轴指向两楼中点 | 两楼都有路径 |
| G4 | 双楼 120/120 m，高仰角扫描 | 高度越高，高仰角回波更可能出现 |

### 13.2 高度扫描

```text
H_A in [60, 100, 120]
H_B in [60, 100, 120]
boresight_elevation in [0, 3, 6, 10, 20, 40]
```

输出：

```text
path_count_by_building
energy_by_building
beamformed_energy_by_building
range_profile_peak
```

### 13.3 波束扫描

```text
rx_beam_azimuth in [-30, -20, -10, 0, 10, 20, 30] deg
rx_beam_elevation in [0, 3, 6, 10, 20, 40] deg
```

输出：

```text
beam_sweep_heatmap
best_beam_direction
best_beam_energy
dominant_building_under_best_beam
```

### 13.4 收敛性

```text
samples_per_src in [1e5, 5e5, 1e6, 2e6]
seed in [501, 502, 503]
```

检查：

```text
path_count_cv
energy_cv
building_path_count_rank_stability
```

## 14. 文件夹规划

新结构：

```text
outputs/radar_workbench/
  experiments/
    <experiment_id>/
      experiment_manifest.json
      input/
        experiment_config.json
        scene_config.json
        beamforming_config.json
        analysis_config.json
      scene/
        scene.xml
        meshes/
      runs/
        <run_id>/
          config_snapshot.json
          run_status.json
          raw/
            paths_summary.npz
            cir.npz
            radar_observation.npz
          analysis/
            paths.json
            paths.csv
            interactions.csv
            building_path_statistics.csv
            beamformed_paths.npz
            beam_sweep_summary.csv
          figures/
            scene_paths.png
            range_profile.png
            range_azimuth_spectrum.png
            range_elevation_spectrum.png
            beam_sweep_heatmap.png
          bundle/
            result_bundle.zip
      logs/
```

旧的：

```text
outputs/radar_workbench/campaigns/
outputs/radar_workbench/jobs/
outputs/radar_workbench/web_cache/
```

可在重构时直接迁移或清空，不做旧版兼容。

## 15. 风险与处理

| 风险 | 影响 | 处理 |
|---|---|---|
| 主轴 40 deg 几何不照楼 | 结果路径少，被误判为平台无效 | 把 40 deg 设为扫描点或上边界，并显示主轴高度交点 |
| diffuse path count 随采样波动 | “多少条径”不稳定 | 报告 seed/samples，做收敛性统计 |
| 后处理门限被当成真实波束 | 结论不专业 | UI 和 API 分离 `analysis_gate` 与 `beamforming` |
| 历史配置和当前草稿混淆 | 用户误读结果 | 历史 run 配置只读，编辑必须新建草稿 |
| 结果包过大 | 浏览器下载慢 | 提供完整包和轻量包两种下载 |
| 400-500 m 场景计算慢 | 交互体验差 | 先低采样预览，再高采样正式运行 |

## 16. 最小可行版本

如果要快速落地，建议优先做以下 MVP：

1. 参数化双楼场景。
2. 单站雷达位置/指向/楼高设置。
3. PathSolver 跑出路径。
4. 统计总路径数、建筑 A/B 路径数、交互阶数路径数。
5. 保存并下载 `paths.csv`、`metrics.json`、`experiment_config.json`。
6. 3D 中显示建筑、雷达、主轴、分析门限、路径和交互点。

暂缓：

- 自定义复数权重上传。
- 极化端口加权。
- 高级历史比较。
- 大规模波束扫描。

## 17. 最终验收标准

当用户提出：

```text
一个发射站，远处 400-500 m，两个楼，楼高 60/100/120 m，雷达打过去能收到多少条径？
```

系统应能：

1. 在浏览器里设置这个场景。
2. 清楚显示主轴是否打到建筑。
3. 运行 Sionna RT。
4. 返回路径总数、分析门限内路径数、建筑 A/B 路径数。
5. 显示路径与交互点。
6. 显示唯一且有解释的统计图。
7. 下载完整结果包。
8. 重启后从历史实验中恢复配置和结果。
9. 支持基于历史配置新建草稿重新仿真。
10. 支持接收阵列自定义波束成形后处理。

满足以上条件，才算这个平台真正适合该类雷达/ISAC 几何实验。
