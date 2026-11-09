# 多测点城市雷达/ISAC 仿真实验规划

**目标**：在同一城市 Sionna RT 场景内部进行多次静态测量，系统评估 Sionna 是否能模拟城市环境中的雷达收发效用，并为后续 ISAC 研究生成可复核的数据集。

**基线来源**：

- 单点验证计划：`refine-logs/EXPERIMENT_PLAN.md`
- 单点执行报告：`outputs/sionna_radar/reports/EXECUTION_REPORT.md`
- 已验证能力：28 GHz、Tx 1x1、Rx 16x16、`simple_street_canyon` 城市场景、`BackscatteringPattern`、`max_depth=2`、LoS 关闭的单站雷达回波、CIR 到 range-azimuth 观测转换。

## 1. 核心问题

前一阶段回答了“在一个位置能否出雷达式回波”。下一阶段要回答三个更接近研究的问题：

1. **多测点空间一致性**：雷达在城市内部不同静态位置测量时，路径、距离-角度图、建筑杂波是否随位置连续、可解释地变化？
2. **重复测量可靠性**：同一测点不同随机 seed / 不同采样数下，散射结果是否收敛，是否足够稳定用于研究？
3. **ISAC sensing 数据可用性**：同一雷达平台在多测点上能否生成可用于 ISAC sensing 研究的回波数据，例如 CIR、range-angle map、range-elevation map、clutter/散射统计、FoV 内能量和多径结构？

这里的“多次测量”不是移动天线产生 Doppler，而是多个静态 snapshot。每个 snapshot 有固定雷达位置、固定朝向、固定场景，独立调用 Sionna RT。

## 2. 关键修正：FoV 中心不能硬编码为 0 度

前一阶段 R024 使用：

```text
az_center_deg = 0
azimuth FoV = [-60, +60] deg
```

但 R011/R024 的雷达位置与朝向为：

```text
position = [0, -1, 10]
look_at  = [0, 25, 10]
```

从雷达到 look_at 的方向是 +y，因此方位中心应为：

```text
az_center_deg = atan2(dy, dx) = atan2(26, 0) = 90 deg
```

这解释了 R024 中 FoV 内路径比例和能量比例偏低。新阶段所有测点必须自动计算：

```text
boresight_az_deg = atan2(look_at_y - y, look_at_x - x)
boresight_el_deg = atan2(look_at_z - z, horizontal_distance)
```

后处理 FoV 应以 boresight 为中心，而不是固定 0 度。

## 3. 实验主张

| Claim | 为什么重要 | 最小可信证据 | 对应实验 |
|---|---|---|---|
| M-C1：Sionna 能生成多测点空间一致的城市雷达回波 | 证明它不只是单点可跑，而能用于场景内测量研究 | 相邻测点 range-angle map 主结构连续变化；建筑回波可回投到场景几何 | C001、C002 |
| M-C2：散射/后向散射结果在合理采样下可复现 | diffuse scattering 是随机采样路径，必须证明稳定性 | 同一测点 3 seeds 的主峰、FoV 能量、map NRMSE 稳定 | C001 |
| M-C3：同一城市场景可生成多测点 ISAC sensing 数据集 | 后续 ISAC sensing 工作需要可复核的多测点雷达回波数据 | 每个雷达 pose 保存自发自收 CIR、路径、range-angle/range-elevation map、FoV 能量、depth/diffuse 统计 | C002 |
| M-C4：Sionna 的能力边界可被清晰分离 | 避免把传播仿真误写成完整雷达/RCS 仿真 | 报告只声明传播、CIR、相对功率和空间一致性，不声明绝对 RCS/硬件链路 | 所有实验 |

## 4. 总体设计

### 4.1 场景

主场景仍使用 Sionna 内置：

```text
scene = simple_street_canyon
```

原因：

1. 已经在 R009-R011 验证过该场景可产生城市建筑回波和大量后向散射路径。
2. 场景尺度约 180 m x 120 m，适合布置多测点。
3. 内置材料和 mesh 可归档复现。

扩展场景：

```text
scene = san_francisco
```

只作为第二阶段扩展，不应阻塞主结论。

### 4.2 雷达配置

| 项 | 主配置 |
|---|---|
| 载频 | 28 GHz |
| Tx | 1x1，单天线 |
| Rx | 16x16 planar array，0.5 lambda spacing |
| 收发位置 | 小基线单站近似，Tx/Rx 相距 0.1 m |
| LoS | radar sensing pass 中 `los=False` |
| 反射/散射 | `specular_reflection=True`, `diffuse_reflection=True` |
| 后向散射 | `BackscatteringPattern(alpha_r=20, alpha_i=20, lambda_=0.3)` |
| 散射系数 | 主值 0.5；消融 0、0.2、0.8 |
| 最大交互 | `max_depth=2` |
| 折射/绕射 | 主实验关闭；扩展再打开 |
| 雷达带宽 | 1 GHz，用于 `Delta R = 0.15 m` 的 range bin |

### 4.3 雷达自发自收求解

每个 BS/radar pose 只做雷达 sensing pass：

**Sensing pass：单站雷达回波**

```text
Tx = BS/radar Tx
Rx = BS/radar Rx 16x16
los = False
diffuse_reflection = True
max_depth = 2
output = paths, CIR, range-azimuth/elevation map
```

关闭 LoS 是为了避免自泄漏主导，这一点由 R005 已证明。

这一 pass 才是雷达仿真：发射端和接收端都在同一个 BS/radar 平台上，采用小基线近似同址；建筑物、地面和其他场景物体作为反射/散射体。UE 不参与雷达回波接收。

此前归档中的 BS-to-UE communication pass 属于误扩展，不纳入本任务结论。当前任务只研究雷达自发自收获取 ISAC sensing 数据。

## 5. 多测点 Campaign 设计

### Campaign C001：重复测量与采样稳定性

**目的**：确认同一测点下 diffuse/backscatter Monte Carlo 结果可复现。

**测点**：使用已验证的中心测点：

```text
BS pose P00:
  radar_center = [0.0, -1.0, 10.0]
  look_at      = [0.0, 25.0, 10.0]
  boresight_az = 90 deg
```

**运行矩阵**：

| 维度 | 值 |
|---|---|
| seeds | 3 个：101, 102, 103 |
| samples_per_src | 5e5, 1e6, 2e6 |
| scattering coefficient | 0.5 |
| pattern | Backscattering |

**指标**：

1. 有效路径数均值/方差。
2. FoV 内路径比例、FoV 内能量比例。
3. range-azimuth map NRMSE。
4. dominant peak 的 range/azimuth/elevation shift。
5. depth>=2 路径比例。
6. diffuse path energy ratio。

**通过标准**：

```text
主峰 range shift <= 1 range bin
主峰 azimuth shift <= 1 angular bin
2e6 vs 1e6 map NRMSE <= 0.10-0.15
FoV energy fraction seed CV <= 20%
```

如果不通过，需要提高采样数或降低对 diffuse 细节的结论强度。

### Campaign C002：街谷内多位置雷达测量

**目的**：检验 Sionna 是否能在城市内部多个位置产生空间一致、几何可解释的雷达测量。

`simple_street_canyon` 的道路主要位于建筑之间。建议先在道路中心线和两侧近建筑位置布点：

```text
x positions = [-60, -30, 0, 30, 60] m
y lanes     = [-5, 0, 5] m
z heights   = [10] m
```

共：

```text
5 x 3 x 1 = 15 BS/radar poses
```

每个 pose 使用两个主要朝向：

1. 沿街道 +x 方向看：
   ```text
   look_at = [x + 30, y, z]
   ```
2. 朝街道一侧建筑 +y 方向看：
   ```text
   look_at = [x, y + 30, z]
   ```

因此主测量数量：

```text
15 poses x 2 boresights = 30 measurements
```

每个 measurement 先跑：

```text
samples_per_src = 5e5
seed = 201
```

选 5 个代表测点再跑：

```text
samples_per_src = 2e6
seeds = 3
```

**每个测量保存**：

```text
pose_id
position
look_at
boresight_az/el
scene geometry hash
solver config
paths_summary.npz
cir.npz
radar_observation.npz
range_azimuth.png
range_elevation.png
pose_metrics.json
```

**空间一致性指标**：

| 指标 | 解释 |
|---|---|
| path_count_map | 各测点有效路径数热力图 |
| in_fov_energy_map | FoV 内感知能量热力图 |
| dominant_range_continuity | 相邻测点主峰距离变化是否平滑 |
| map_similarity_adjacent | 相邻测点 range-angle map 相似度 |
| building_echo_consistency | 主要回波是否能回投到建筑立面 |
| depth2_ratio_map | 二次交互路径比例随位置变化 |
| diffuse_ratio_map | 散射路径比例随位置变化 |

**通过标准**：

1. 大多数测点能产生有效 radar echo，而不是只在单点有效。
2. 相邻测点的 dominant structures 连续变化，遮挡/街角处允许突变。
3. 朝建筑方向的测量应比沿空旷方向产生更强建筑回波。
4. depth=2 和 diffuse 路径在城市多径位置更明显。

### Campaign C003：弃用项

此前 C003 被错误设计为 BS-to-UE communication pass。该方向不属于当前任务，归档结果只作为误扩展记录，不纳入雷达获取 ISAC sensing 数据的结论。当前主线以 C001/C002/C004/C005 为准。

### Campaign C004：雷达波束/视场策略扫描

**目的**：研究雷达/ISAC 的收发效用，而不只是固定朝向。

在 C002 的代表 BS/radar pose 上扫描：

```text
boresight az offset = [-60, -30, 0, +30, +60] deg
elevation center    = [0, 10, 20] deg
FoV                 = 120 deg az, 0-40 deg el
```

如果暂时没有自定义 sector antenna pattern，先用后处理 FoV mask 完成 `C004-lite`。正式 ISAC 论文实验应实现物理 sector pattern，再跑 `C004-sector`。

**输出**：

- sensing utility vs boresight
- sensing utility vs boresight
- per-pose best boresight

**关键风险**：如果只做后处理 FoV mask，而天线仍是 isotropic，则不能证明真实波束成形/方向图效应，只能证明“从全向路径中裁剪目标视场后的观测效用”。报告必须分清。

### Campaign C005：频率与材料敏感性

**目的**：支持 28 GHz 之外的 ISAC 扩展。

选 C002 中 5 个代表 pose，运行：

```text
fc = 28 GHz, 60 GHz, 77 GHz
scattering_coefficient = 0.2, 0.5, 0.8
pattern = Backscattering
```

输出：

- path count vs frequency
- in-FoV energy vs frequency
- max range vs frequency
- sensing CIR/path energy vs frequency

边界：

1. 77 GHz 材料参数需要谨慎，不能直接声明绝对准确。
2. 高频结论应表述为“模型敏感性”而非实测验证。

## 6. 数据集与目录规划

建议新增根目录：

```text
outputs/sionna_radar_campaigns/
  C001_repeatability/
    campaign.yaml
    pose_manifest.csv
    runs/
    radar_observations/
    reports/
  C002_spatial_survey/
    campaign.yaml
    pose_manifest.csv
    runs/
    radar_observations/
    reports/
  C003_deprecated_comm_extension/
    README_DEPRECATED.md
```

每个 measurement 使用稳定命名：

```text
MM_<campaign>_<pose_id>_<boresight_id>_<seed>_<samples>
```

示例：

```text
MM_C002_P03_B+y_S201_N500k
```

每个 measurement 目录：

```text
config.yaml
metadata.json
scene_summary.json
paths_summary.npz
cir.npz
radar_observation.npz
metrics.json
figures/
  scene_pose_topdown.png
  range_azimuth.png
  range_elevation.png
  path_depth_hist.png
```

Campaign 级报告：

```text
reports/
  CAMPAIGN_SUMMARY.md
  POSE_METRICS.csv
  SPATIAL_HEATMAPS.png
  SEED_STABILITY.csv
  ISAC_JOINT_METRICS.csv
```

## 7. 实现优先级

### Stage S1：修正 FoV 与多测点框架

必须先做：

1. 在后处理脚本中根据 `position -> look_at` 自动计算 `az_center_deg`。
2. 新增 `pose_manifest.csv` 读取器。
3. 新增 campaign runner：循环 pose、boresight、seed、samples。
4. 所有 run 使用独立目录和统一命名。

第一批运行：

```text
C001: P00, 3 seeds, samples=5e5
C002-lite: 5 个中心线测点, +y boresight, samples=5e5
```

### Stage S2：空间测量主实验

运行 C002 的 30 个测量。先用 5e5 samples 建立空间图，再选关键测点放大到 2e6 samples。

输出：

- path_count spatial heatmap
- sensing energy spatial heatmap
- dominant range/azimuth map
- depth2/diffuse ratio map

### Stage S3：雷达 sensing 数据集整理

将 C001/C002 的所有自发自收测量整理为 ISAC sensing 数据集：

1. 每个 BS/radar pose 保存 sensing CIR、路径、range-angle map。
2. 生成跨测点空间热力图和位置索引。
3. 输出 sensing-only metrics，不包含 UE 或通信链路。

### Stage S4：方向图/波束补强

两条路线：

1. **快速路线**：继续使用 isotropic pattern + FoV mask，结论限定为路径裁剪与观测效用。
2. **严谨路线**：实现 custom sector antenna pattern，再重跑 C004-sector。

若目标是论文级 ISAC 工作，建议必须走第二条。

### Stage S5：频率/材料扩展

只在 C001/C002 主结论稳定后运行，避免早期被材料不确定性拖住。

## 8. 计算预算

基于前一阶段 H100 运行经验粗估：

| Campaign | 测量数 | samples | 估计耗时 |
|---|---:|---:|---:|
| C001 | 9 | 5e5-2e6 | 10-30 min |
| C002-lite | 5 | 5e5 | 5-15 min |
| C002-full | 30 | 5e5 | 30-90 min |
| C002-selected-high | 15 | 2e6 | 45-120 min |
| C004-lite | 9 x 15 beams | 2e5-5e5 | 1-4 h |
| C005 | 5 x 3 x 3 | 5e5 | 1-3 h |

先跑 C001 + C002-lite，确认 FoV 修正和空间测量结构，再扩大。

## 9. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| FoV 方位定义错误 | 多测点结果失真 | 自动由 `look_at-position` 计算 boresight；每个 pose 保存箭头图 |
| diffuse 采样方差大 | 空间差异可能来自随机噪声 | C001 先做 seed/samples 收敛；关键测点多 seed |
| 多测点落入建筑或场景外 | 生成无意义测量 | pose_manifest 生成后做碰撞/高度/地面检查 |
| 把通信链路误混入雷达任务 | 结论跑偏 | 当前主线只保留雷达自发自收 sensing 数据；旧 C003 communication pass 标记弃用 |
| isotropic + FoV mask 被误读为真实波束 | ISAC 方向图结论不严谨 | 报告中分成 C004-lite 和 C004-sector |
| 绝对功率/RCS 不准 | 检测概率/性能被夸大 | 主报告只讲相对效用；绝对性能需外部标定 |
| 77 GHz 材料不确定 | 高频结论弱 | 作为敏感性，不作为主证明 |

## 10. 最小可行下一步

建议马上执行的最小闭环：

1. **修正 R024 FoV**  
   用 R011 重新生成 `R024B`，`az_center_deg=90`，确认 FoV 内路径/能量比例是否显著提高。

2. **C001 repeatability**  
   在 P00 上跑 3 seeds、5e5 samples，验证多次测量稳定性。

3. **C002-lite spatial survey**  
   选 5 个中心线测点：

   ```text
   P01 = [-60, 0, 10], look_at=[-60, 30, 10]
   P02 = [-30, 0, 10], look_at=[-30, 30, 10]
   P03 = [  0, 0, 10], look_at=[  0, 30, 10]
   P04 = [ 30, 0, 10], look_at=[ 30, 30, 10]
   P05 = [ 60, 0, 10], look_at=[ 60, 30, 10]
   ```

   每点 5e5 samples，输出空间热力图。

这三步完成后，就可以判断 Sionna 是否足够支撑你的 ISAC sensing 研究主线。

## 11. 成功判据

若以下条件满足，可以较严谨地声称：

```text
Sionna RT 可以用于城市环境中多测点静态雷达/ISAC传播仿真，
能够生成空间一致的雷达自发自收回波观测，
适合研究相对收发效用、覆盖、杂波、多径和 beam/pose tradeoff。
```

条件：

1. C001 显示同点多 seed 稳定。
2. C002 显示不同位置的雷达图随场景几何合理变化。
3. 所有报告明确不声明绝对 RCS、硬件泄漏、真实检测概率或未经标定的高频材料准确性。
