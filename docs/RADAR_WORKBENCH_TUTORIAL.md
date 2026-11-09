# 城市雷达感知仿真平台使用与结果解读教程

本文档面向需要运行仿真、检查传播路径、分析 MPC、配置接收波束成形和导出科研数据的使用者。它关注“怎样使用”和“怎样判断结果”；跨机器安装与迁移请参阅 `DEPLOYMENT_GUIDE.md`，模块交接请参阅 `RADAR_WORKBENCH_HANDOVER.md`。

最后更新日期：2026-07-10

## 目录

1. [先明确仿真对象](#1-先明确仿真对象)
2. [环境和启动](#2-环境和启动)
3. [界面结构](#3-界面结构)
4. [浏览已有结果的完整流程](#4-浏览已有结果的完整流程)
5. [三维传播路径可视化](#5-三维传播路径可视化)
6. [单条路径参数解读](#6-单条路径参数解读)
7. [分析门限](#7-分析门限)
8. [概览统计怎样读](#8-概览统计怎样读)
9. [MPC 分析](#9-mpc-分析)
10. [发射与接收波束](#10-发射与接收阵列波束成形)
11. [距离-角度谱](#11-距离-角度谱)
12. [新建并运行仿真](#12-新建并运行仿真)
13. [保存路径和下载完整结果](#13-保存路径和下载完整结果)
14. [API 使用示例](#14-api-使用示例)
15. [如何验证结果是否可信](#15-如何验证结果是否可信)
16. [常见问题](#16-常见问题)
17. [定向候选射线实现与限制](#17-定向候选射线实现与限制)
18. [开发验证命令](#18-开发验证命令)
19. [相关文档](#19-相关文档)

## 1. 先明确仿真对象

当前项目使用 Sionna RT 2.0.1 进行静态城市环境中的雷达自发自收传播仿真：

- Tx 和 Rx 位于同一雷达平台附近，以一个很小的基线分离。
- PathSolver 求解 LoS、镜面反射和漫反射等传播路径。
- `cir.npz` 保存阵列通道系数，路径时延和交互几何保存在 `paths_summary.npz`。
- 后处理按 `w_rx^H H_p w_tx` 合成复路径，再生成 FMCW 去斜回波、热噪声、距离-多普勒 FFT 和 CA-CFAR 检测。
- 有效路径同时转换为等效单站距离、AoA/AoD、距离-角度谱、MPC 和统计结果。
- 前端显示场景、已求解路径、交互点、分析门限和波束成形结果。

这属于基于几何光学和射线追踪的相干雷达场景仿真，不是 FDTD/FEM 全波求解；亚波长目标电流、天线馈电结构和微多普勒不在当前模型范围内。

### 1.1 五种容易混淆的“方向”

| 名称 | 当前作用 | 是否改变 PathSolver 候选射线方向 |
|---|---|---|
| 分析角域门限 | 按 AoA 方位、AoA 俯仰和距离筛选已求解路径 | 否 |
| 初始射线采样 | 物理基准使用 Sionna 原生 `full_sphere`；`analysis_sector` 只是实验性加速 | 只有实验模式会改变 |
| Tx 物理方向图 | `radar_array` 通过 Sionna 公开方向图接口计算相控孔径、单元增益、主瓣和旁瓣 | 否，只改变 Sionna 复场系数 |
| Rx 单元方向图 | `iso` 或 Sionna `tr38901`，由 PathSolver 场计算器作用到 CIR | 否 |
| Rx 数字波束成形 | 对 Sionna CIR 的接收阵元维做复数相干加权 | 否 |

因此，界面中的三维线段是 **PathSolver 最终返回的传播路径**，不是全部初始候选射线。新方案默认使用 `full_sphere`；旧结果没有该配置时也按 `full_sphere` 恢复。

## 2. 环境和启动

### 2.1 运行时

推荐安装方式在项目目录创建一个可迁移的 Python 虚拟环境：

```text
.venv/bin/python
```

API 通过外部 Python 子进程运行 Sionna RT，仍可使用
`RADAR_API_PYTHON` 和 `RADAR_SIONNA_PYTHON` 指定两个相互隔离的解释器。

射线追踪环境的直接依赖锁定在：

```text
experiments/sionna_radar/requirements-runtime.txt
```

当前验证版本：

```text
sionna-rt  2.0.1
mitsuba    3.8.0
drjit      1.3.1
```

`RADAR_SIONNA_PYTHONNOUSERSITE=1` 用来禁止混入 `~/.local` 下的其他 Mitsuba、Dr.Jit 或 Sionna 版本。不要去掉这个隔离，除非已经确认所有包的来源和 ABI 一致。

### 2.2 启动和停止

在仓库根目录执行：

```bash
./scripts/start_radar_workbench.sh
```

安装后的单端口地址：

```text
界面与 API：http://127.0.0.1:8000
```

前端开发模式才单独使用 `http://127.0.0.1:5173`。

停止服务：

```bash
./scripts/stop_radar_workbench.sh
```

日志位于：

```text
outputs/radar_workbench/logs/radar_api.log
outputs/radar_workbench/logs/radar_ui.log
```

### 2.3 启动后必须做的检查

```bash
curl -s http://127.0.0.1:8000/api/health | python -m json.tool
curl -s http://127.0.0.1:8000/api/health/sionna_runtime | python -m json.tool
```

第二个响应至少应满足：

```text
available = true
path_solver_available = true
sionna_rt = 2.0.1
module_path 位于当前配置的隔离环境
```

如果端口已被其他进程占用，可以指定新端口：

```bash
RADAR_API_PORT=8010 RADAR_UI_PORT=5180 ./scripts/start_radar_workbench.sh
```

## 3. 界面结构

工作台分为四个主要区域：

| 区域 | 功能 |
|---|---|
| 顶栏 | 显示当前方案或结果快照、刷新数据、确认 Sionna RT 版本和运行状态 |
| 左侧工作区 | 切换实验方案和仿真结果；仿真结果内先选结果集合，再选集合内 run |
| 中央工作区 | 三维传播场景，以及概览、雷达回波、MPC、波束成形、距离角谱五个结果页 |
| 右侧检查器 | 编辑雷达参数，或者筛选并检查单条传播路径和场景对象 |

左右侧栏可以折叠。窄屏设备上，中央结果区、路径检查器和数据导航会改为纵向排列。

### 3.1 方案、结果集合和记录的关系

三者不是三份重复数据，关系如下：

```text
实验方案
  └─ 提交仿真
      └─ 技术 campaign/job 目录
          ├─ run 1 结果快照
          ├─ run 2 结果快照
          └─ ...
```

- 实验方案：场景和参数模板，本身没有 CIR、MPC 或传播路径。
- 技术 campaign/job：一次任务的输出容器；单点任务通常只有一个 run，多测点任务可以有多个 run。
- run：一条不可变的结果快照，包含当时配置、路径、CIR、统计和图像。
- `C002 基准测量`：预置的只读多 run 集合。
- `我的仿真结果`：UI 虚拟集合，把所有 Web job 的 run 聚合显示；底层文件仍按原 job 目录保存，没有复制结果。

新任务会保存 `source_experiment_id`，因此可以从结果追溯来源方案。旧任务创建时没有该字段，会显示为独立结果快照。

### 3.2 点击结果记录会恢复什么

点击 run 后，表单从该 run 的 `config.yaml`、`metadata.json` 和 `metrics.json` 恢复：

- 场景、雷达位置、指向和 Tx/Rx 基线。
- 方位/俯仰门限和最大分析距离。
- 载频、带宽、天线方向图和初始射线采样模式。
- 最大深度、传播机制、散射模型及参数。
- Tx/Rx 阵列规模、Tx 孔径加权与导向角、射线数和随机种子。
- FMCW chirp、ADC、接收机噪声、Rx 波束、CFAR 和回波合成路径上限。

GPU ID 是执行资源，不属于电磁结果；旧 run 不保证恢复当时使用的 GPU，界面使用当前可用 GPU 默认值。修改结果快照后运行会创建新 run，不会覆盖历史文件；“恢复”按钮返回刚加载的快照参数。

## 4. 浏览已有结果的完整流程

### 4.1 选择仿真结果

1. 启动工作台。
2. 在左侧切换到“仿真结果”。
3. 在“结果集合”选择 `C002 基准测量` 或 `我的仿真结果`。
4. 在“集合内记录”选择一个 run。
5. 等待场景、路径和谱图加载完成。

选择 run 后，前端先加载轻量级场景和路径缓存，再加载路径统计、MPC 和谱图。第一次打开某个旧 run 时，后端可能需要从原始 NPZ 构建 Web 缓存，因此会比第二次慢。

### 4.2 确认结果和参数对应

加载历史结果后，顶栏和右侧状态显示“结果快照 · run_id”。表单由该 run 的 `config.yaml`、`metadata.json` 和 `metrics.json` 恢复。修改后状态显示“已修改”，点击恢复可回到快照参数，重新运行会创建新结果而不会覆盖旧 run。

必须遵守以下规则：

- 修改位置、指向、频率、阵列、反射/散射或方向图后，旧路径不再对应新参数。
- 修改分析门限后，如果要获得与新门限一致的归档和统计，也应重新运行当前工作流。
- 参数有未运行的修改时，不要把中央旧结果解释成新配置的输出。

## 5. 三维传播路径可视化

### 5.1 图层含义

三维场景顶部工具条可以控制：

- `未选路径` 或 `路径 #编号`：显示或隐藏当前选中的完整传播路径折线。
- `交互点`：显示或隐藏当前路径上的反射、散射交互点。
- `角域门限`：显示或隐藏由当前指向和角域参数构造的分析边界，默认关闭。
- `#路径编号`：选中路径后出现；点击可在全场景视图和路径聚焦视图之间切换。

颜色约定：

| 元素 | 颜色 | 含义 |
|---|---|---|
| 雷达位置 | 绿色标记 | 雷达 Tx/Rx 附近位置 |
| 主视轴 | 灰色虚线 | 雷达当前指向，不是传播路径 |
| 发射段 | 绿色 | Tx 到第一个交互点 |
| 中间段 | 紫色 | 多阶路径的中间传播段 |
| 回波段 | 红色 | 最后交互点到 Rx |
| 选中路径 | 黄色高亮 | 当前路径检查器对应的路径 |
| 镜面反射点 | 蓝色 | Sionna 路径中的镜面交互 |
| 漫反射/散射点 | 橙色 | Sionna 路径中的漫反射交互 |

### 5.2 选择路径

可以通过以下入口选择路径：

1. 在右侧“路径与对象”页点击路径行。
2. 在 MPC 页底部的“传播路径补充分析”中点击强路径。
3. 在波束成形结果中点击波束合成后的强路径。

选择后，三维场景和右侧检查器会同步，场景只绘制当前这一条路径，并自动把相机聚焦到整条路径的包围范围。点击场景顶部的路径编号可恢复全场景视图；再次点击重新聚焦。

### 5.3 为什么只显示部分路径

原始 run 可能包含数万到数十万条有效路径。浏览器不会一次绘制全部路径：

- API 缓存优先保留全局强路径、分析门限内强路径和一定数量的漫反射路径。
- WebGL 画布只绘制路径检查器当前选中的一条完整路径，不会同时堆叠全部缓存路径。
- 路径列表最多渲染当前匹配集合的前 200 行，以保持检查器响应速度。

这不会改变原始 `paths_summary.npz`，但界面统计必须区分“原始有效路径总数”和“浏览器已载入主要路径数”。

## 6. 单条路径参数解读

右侧“路径与对象”页支持传播类型筛选和仅分析门限内筛选；三维画布始终只显示当前选中的一条完整路径。

### 6.1 等效单站距离

界面使用：

```text
R = c * tau / 2
```

其中 `tau` 是整条 Tx 到 Rx 传播时延，`c` 是光速。除以 2 是单站雷达往返距离约定。当前 Tx/Rx 有小基线，因此它是等效单站距离，不一定等于某个交互点到雷达的严格欧氏距离。

### 6.2 路径能量

路径能量从 CIR 路径系数得到。界面显示：

```text
P_dB = 10 * log10(max(P, 1e-30))
```

这里的 dB 是当前仿真归一化和通道系数下的功率对数值，不应在没有硬件标定、发射功率、噪声系数和雷达截面积标定的情况下直接解释为真实接收 dBm。

### 6.3 AoD 和 AoA

- AoD：路径离开 Tx 时的方位角和俯仰角。
- AoA：路径到达 Rx 时的方位角和俯仰角。
- 方位角规范到 `[-180, 180)` 度。
- 俯仰角由 Sionna 的天顶角转换，水平面为 0 度，向上为正。

分析门限使用 AoA，不使用 AoD。不要用“发射 AoD 在扇区内”替代“回波 AoA 在门限内”的判断。

### 6.4 交互阶数和传播类型

- 阶数 0：没有场景交互，通常对应 LoS；本项目默认雷达自收配置可能关闭 LoS。
- 阶数 1：一次反射或散射。
- 阶数 2：两次交互。
- 镜面反射：有效交互全部为 specular。
- 漫反射：有效交互全部为 diffuse。
- 混合路径：同时包含 specular 和 diffuse。

“交互序列”按传播顺序列出交互类型、对象 ID 和坐标。检查异常强路径时，应同时核对三维折线、对象包围盒和交互坐标。

### 6.5 谱 bin

`距离 / 方位 / 俯仰 bin` 表示该路径落入 `radar_observation.npz` 中哪个分箱。值为 `-` 通常表示路径落在当前谱范围以外，而不是路径本身无效。

## 7. 分析门限

分析门限由四个量组成：

```text
方位中心 az_center
方位宽度 az_width
俯仰下限 el_min
俯仰上限 el_max
最大距离 rmax
```

单条路径进入门限必须同时满足：

```text
abs(wrap(AoA_azimuth - az_center)) <= az_width / 2
el_min <= AoA_elevation <= el_max
range <= rmax
```

`wrap` 负责正确处理 `-180/180` 度边界。

门限本身仍是观测后处理。它适合：

- 只分析雷达关注方向的回波。
- 比较不同测点在统一角域下的路径和能量。
- 诊断是距离、方位还是俯仰条件排除了大部分 MPC。

当“初始射线采样”选择 `分析扇区定向` 时，同一组方位和俯仰边界也会用于 Tx 初始候选方向；`rmax` 仍只用于后处理距离门限。是否使用定向采样应以 `metadata.json` 中的 `initial_ray_sampling.mode` 为准。

门限本身不能证明：

- 旧 run 曾使用定向初始射线；旧结果默认是全空间基线。
- 门限外路径在物理天线下完全没有能量。
- 已经执行了 Tx 或 Rx 阵列相干波束成形。

## 8. 概览统计怎样读

中央“概览”页分为总指标和诊断图。

### 8.1 核心指标

| 指标 | 定义 | 使用时的注意事项 |
|---|---|---|
| 有效路径总数 | `valid=true`、时延有限且大于最小时延阈值的路径数 | 受采样数、最大深度和传播机制影响 |
| 分析门限内路径数 | 有效路径中同时满足距离、方位和俯仰门限的数量 | 不是物理波束照射路径数 |
| 分析门限内能量占比 | 门限内路径能量和 / 全部有效路径能量和 | 比路径数量占比更能反映强回波是否集中 |
| 主峰距离 | 路径/距离像中能量峰值对应的距离 | 多径强峰不一定是目标真实距离 |
| 最大交互阶数 | 当前有效路径中最大的交互次数 | 应小于或等于 PathSolver `max_depth` |

### 8.2 诊断图

- 距离像：距离-方位角谱沿角度维积分得到的距离功率分布。
- 传播机制能量占比：仅基于浏览器载入的主要路径集合，适合快速比较，不等于完整路径全集统计。
- 交互阶数、距离和 AoA 分布：显示主要路径集合的数量分布。
- 建筑物回波能量贡献：一条路径涉及多个对象时，前端会在对象间分摊能量，用于排序而非严格电磁归因。
- 累计能量曲线：先按路径能量降序，再累计；曲线越快接近 1，表示少数强路径越主导回波。
- 多测量排序：比较同一 campaign 中各测点的门限内能量占比。

需要发表或做定量结论时，优先使用结果包中的 `analysis/path_statistics.json`、`analysis/paths.csv` 和完整 NPZ，不要只从前端柱状图读取数值。

## 9. MPC 分析

### 9.1 MPC AoA 全景定义

MPC 页采用 AoA 等距柱状全景数据产品。对第 `l` 条路径，取第 0 个收发阵元对的 CIR 幅值：

```text
A_l = |a_l|
```

按 Sionna 的 AoA 方位角 `phi_l` 和天顶角 `theta_l` 投影：

```text
x_l = (180 deg - phi_l) * 3
y_l = theta_l * 3
```

得到方位 1080 像素、天顶角 540 像素的等距柱状全景图。

### 9.2 阵列孔径核

默认使用 8×8 矩形孔径和 0.5 波长阵元间距。主瓣宽度近似为：

```text
HPBW ~= 0.886/(N*d)
sigma = HPBW/2.3548
```

路径在线性幅值域按该二维核叠加，再计算：

```text
M(x,y) = 10log10(sum_l A_l*K(x-x_l,y-y_l))
```

PNG 使用第 99.5 百分位作为上界并显示下方 40 dB。定量分析应读取 NPZ 中未归一化的 `raw_db`，不要从 Jet 伪彩色反推数值。

### 9.3 全景与透视视图

页面首先显示 360°×180° 全景，然后按 90° FOV 裁切前、右、后、左四个透视视图。每个接收位置只需要运行一次 Sionna 路径求解；四张图由同一全景几何重投影得到，不应为四个方向重复运行 RT。

### 9.4 传播路径补充分析

门限内路径计数、距离-AoA 散点和逐路径三维折线是解释传播机理的补充数据，不是 MPC 全景图本身。旧文件名为兼容已有结果而保留：

```text
analysis/analysis_gate_mpc.csv
figures/analysis_gate_mpc.png
```

MPC 主产物为：

```text
analysis/mpc_panorama.npz
figures/mpc_panorama.png
figures/mpc_view_front.png
figures/mpc_view_right.png
figures/mpc_view_back.png
figures/mpc_view_left.png
```

## 10. 发射与接收阵列波束成形

Tx 相控阵孔径模式使用 Sionna 公开 `register_antenna_pattern()` 接口注册预合成孔径。方向图由 3GPP 单元场方向图与矩形阵列因子相乘；既可由导向角和 Uniform/Hann 孔径生成权重，也可按行优先顺序输入逐阵元复权重。权重按单位范数归一化；Sionna `PathSolver` 仍负责全部路径几何、材料、极化和复场传播。原生 Tx 平面阵列保留独立发送阵元通道时，权重则按 Sionna 列优先顺序输入。

### 10.1 四种模式

| 模式 | 含义 |
|---|---|
| 不进行数字合成 | 只读取第一个 Rx 阵元，不提供阵列合成增益 |
| 等幅同相合成 | 所有 Rx 阵元使用相同相位并做单位范数归一化 |
| 导向矢量 | 根据指定方位角和俯仰角生成阵列复权重 |
| 自定义复权重 | 用户为每个 Rx 阵元提供复数权重，后端再做单位范数归一化 |

自定义复权重接受以下元素形式：

```json
[
  {"re": 1.0, "im": 0.0},
  [0.0, -1.0],
  0.5
]
```

权重数量必须严格等于 `Rx 行数 * Rx 列数`，且不能全部为零。Rx 权重采用列优先顺序：先从上到下填写第一列，再填写下一列，与 Sionna 原始接收通道顺序一致。

### 10.2 预览图

编辑器在发射区和接收区分别全宽显示 Tx 物理发射方向图与 Rx 数字接收响应，包含峰值方向和 3 dB 方位波束宽度。正式结果在 run 创建时由后端从真实 Sionna CIR 生成并作为快照保存；结果页不会用方案参数覆盖历史工件。

### 10.3 相干与非相干功率

设第 `p` 条路径的复通道矩阵为 `H_p`，单位范数 Tx/Rx 权重分别为 `w_tx`、`w_rx`：

```text
y_p = w_rx^H H_p w_tx
P_coherent,p = |y_p|^2
P_noncoherent,p = sum_i |a_p,i|^2
```

相干功率包含阵元间相位关系；非相干功率只把阵元功率相加。二者差异反映当前权重是否与该路径到达方向和通道相位匹配，但不能单独当作系统绝对阵列增益。

### 10.4 阵列坐标约定

当前矩形阵列在局部 `y-z` 平面布置，间距单位为波长。导向矢量使用：

```text
Tx: w = exp(-j*2*pi*(y*sin(az)*cos(el) + z*sin(el)))
Rx: w = exp(+j*2*pi*(y*sin(az)*cos(el) + z*sin(el)))
```

因此，修改阵列行列数、阵元间距或导向角后，都应检查预览峰值是否位于预期角度。

后端产物：

```text
analysis/beamformed_observation.npz
analysis/beamformed_paths.csv
analysis/beamforming_summary.json
analysis/rx_steering_pattern.npz
analysis/rx_steering_pattern_summary.json
analysis/tx_radiation_pattern.npz
figures/rx_steering_pattern.png
figures/tx_radiation_pattern.png
```

## 11. 距离-角度谱

中央“距离角谱”页包含：

- 距离-方位角谱。
- 距离-俯仰角谱。

每条有效路径根据 `range_m` 和 AoA 落入二维 bin，并按 Tx/Rx 相干合成后的路径功率累加。距离角谱仍是路径级角域直方图，不应误称为三维 ADC 数据立方体。

当前距离分辨率近似受后处理 `range_bin_m` 控制。理论带宽分辨率：

```text
Delta_R = c / (2 * bandwidth)
```

中央“雷达回波”页是另一条产品：它根据 Sionna 复路径系数、时延和 Doppler 合成离散 FMCW 去斜样本，加入 `k*T*fs*NF` 热噪声，使用 Hann 窗执行二维 FFT，并用二维 CA-CFAR 输出检测。对应工件为：

```text
analysis/fmcw_range_doppler.npz
analysis/fmcw_summary.json
figures/fmcw_range_doppler.png
```

为控制 CPU 计算量，最强的 `max_synthesis_paths` 条路径逐点生成快时间/慢时间样本；其余有效路径按复系数相干投影到最近的距离-多普勒 FFT 单元。摘要分别记录 `exact_time_domain_path_power_fraction` 和 `fft_gridded_path_count`。后者保留全部路径与复相位，但包含最多半个 FFT 单元的频率量化误差；需要研究弱路径旁瓣时应提高精确合成上限并做收敛比较。

## 12. 新建并运行仿真

### 12.1 建议的基础流程

1. 在左侧“实验方案”中创建或选择方案。
2. 设置雷达位置和指向点，确认三维场景中的主视轴。
3. 设置分析方位、俯仰和最大距离。
4. 使用“原生全空间”物理基准，并配置 Tx 相控孔径方向图。
5. 设置传播机制、散射参数和最大交互阶数。
6. 设置 Tx/Rx 阵列、采样数、随机种子和 GPU。
7. 配置 FMCW、接收机噪声、Rx 波束和 CFAR，并检查 Tx/Rx 预览。
8. 点击“运行雷达仿真”。
9. 等待任务完成并自动加载新 run。
10. 依次检查三维路径、雷达回波、MPC、波束成形和距离角谱。

### 12.2 关键参数建议

| 参数 | 初步调试 | 正式比较 |
|---|---|---|
| `samples_per_src` | 50k 至 100k | 500k 或经过收敛验证的更高值 |
| `max_depth` | 1 | 2；更高深度需评估计算量和物理意义 |
| 随机种子 | 固定一个种子 | 至少比较多个种子或证明结果已收敛 |
| 镜面反射 | 开启 | 按研究问题决定 |
| 漫反射/散射 | 调试时可关闭 | 需要城市回波时开启并说明模型参数 |
| Tx/Rx 阵列 | 小阵列加快调试 | 使用目标阵列尺寸重新运行 CIR |
| 初始射线采样 | 原生全空间 | `analysis_sector` 只用于有全空间对照的加速实验 |

增加采样数主要提高候选路径发现和统计稳定性；增加最大深度会显著扩大搜索空间。不要同时大幅提高两者后再用单次运行结果判断模型是否正确。

### 12.3 GPU 使用

Web 请求允许选择 GPU0 至 GPU3。每个 worker 通过 `CUDA_VISIBLE_DEVICES` 绑定设备。多 GPU 主要用于把多个 pose/task 分配到不同 GPU，不代表单个 PathSolver 调用自动跨多卡并行。

## 13. 保存路径和下载完整结果

### 13.1 保存筛选路径

在参数与当前 run 同步时点击“保存路径”，数据写入：

```text
outputs/radar_workbench/path_exports/<export_id>/
```

其中包括：

```text
manifest.json
paths.json
path_summary.csv
radar_config.json
run_metadata.json
```

### 13.2 完整结果包

概览页的“完整结果包”会生成 ZIP，通常包含：

- 配置、元数据和指标。
- 路径统计 CSV/JSON。
- MPC CSV、摘要和图像。
- 波束成形摘要、路径和阵列响应产物。
- 原始诊断图。

`cir.npz` 是否包含在轻量结果包中应以 ZIP 清单为准。做可重复波束分析或长期归档时，应另外确认原始 run 目录中的 `cir.npz` 已保存。

## 14. API 使用示例

服务运行时可在 `http://127.0.0.1:8000/docs` 使用 FastAPI Swagger UI 查看并直接调用全部接口；机器可读规范位于 `http://127.0.0.1:8000/openapi.json`。

先设置一个存在的 run：

```bash
RUN_ID=MM_C002full_Pp0_p0_BposY_S501_N500k
BASE=http://127.0.0.1:8000
```

### 14.1 读取路径

```bash
curl -s "$BASE/api/results/$RUN_ID/paths?top_k=20&in_fov=true" \
  | python -m json.tool
```

可选查询参数：

```text
top_k: 1 至 5000
kind: all/specular/diffuse/mixed/unknown
in_fov: true/false
```

### 14.2 路径统计、MPC 和波束成形

```bash
curl -s "$BASE/api/results/$RUN_ID/path_statistics" | python -m json.tool
curl -s "$BASE/api/results/$RUN_ID/mpc_analysis" | python -m json.tool
curl -s "$BASE/api/results/$RUN_ID/beamforming" | python -m json.tool
curl -s "$BASE/api/results/$RUN_ID/fmcw" | python -m json.tool
```

run 是不可变结果快照。波束参数必须在方案中修改并提交新仿真；结果 API 不接受用查询参数覆盖历史波束权重。

### 14.3 下载结果包

```bash
curl -fL "$BASE/api/results/$RUN_ID/result_bundle.zip" -o "$RUN_ID.zip"
unzip -l "$RUN_ID.zip"
```

### 14.4 保存路径归档

```bash
curl -s -X POST "$BASE/api/results/$RUN_ID/path_exports" \
  -H 'content-type: application/json' \
  -d '{
    "draft_config": {
      "center_m": [0.0, 0.0, 10.0],
      "look_at_m": [0.0, 30.0, 10.0],
      "az_width_deg": 120.0,
      "el_min_deg": 0.0,
      "el_max_deg": 40.0
    },
    "top_k": 100,
    "kind": "all",
    "in_fov": true,
    "note": "manual API export"
  }' | python -m json.tool
```

## 15. 如何验证结果是否可信

不能只看“图像看起来合理”。建议按以下顺序验证。

### 15.1 几何基准

使用单反射面或双建筑简化场景：

1. 手算 Tx、反射点和 Rx 的传播长度。
2. 用 `R = c*tau/2` 计算期望等效单站距离。
3. 检查最强路径的三维交互点和距离误差。
4. 确认交互对象 ID 与实际建筑一致。

当前迁移验证中，单反射体的主峰距离约为 `10.0001 m`，可作为运行时正确加载的一个基准，但不能替代对每个新场景的几何核查。

### 15.2 采样收敛

保持场景、种子之外的参数不变，逐步提高 `samples_per_src`：

```text
50k -> 100k -> 250k -> 500k
```

比较：

- 最强路径距离和交互对象是否稳定。
- 门限内总能量和能量占比是否趋于稳定。
- 强路径集合是否稳定。
- 距离-角度谱主峰是否稳定。

仅仅“路径总数继续增加”不代表结果错误；关键是研究指标是否收敛。

### 15.3 深度消融

分别运行 `max_depth=1` 和 `max_depth=2`：

- 一阶强路径应在二阶运行中仍有对应几何机制。
- 新增二阶路径应包含两个有效交互点。
- 如果二阶路径能量异常主导，应检查材料、散射系数和路径系数。

### 15.4 门限一致性

MPC 页的“三条件同时满足”应与：

```text
analysis_gate_path_count
analysis_gate_mpc.csv 行数
paths.csv 中 in_analysis_gate=true 的行数
```

一致。若不一致，先确认这些文件是否来自同一个 run 和同一版配置，再检查缓存是否需要重建。

### 15.5 波束峰值

使用导向矢量模式设置已知角度，例如方位 20 度、俯仰 10 度：

- 前端预览峰值应接近 `20/10` 度。
- 后端 `rx_steering_pattern_summary.json` 的峰值应一致。
- 指向强 MPC 的导向角通常应提高该方向路径的相干合成功率，但多径相位可能导致总功率不是简单单调变化。

### 15.6 可重复性

每个正式结果至少记录：

```text
run_id
Git commit 或工作树状态
Sionna RT / Mitsuba / Dr.Jit 版本
GPU 和驱动版本
完整 config.yaml
随机种子
原始 paths_summary.npz、cir.npz，以及真实阵列模式下的 paths_per_element.npz
```

## 16. 常见问题

### 16.1 三维场景没有路径

检查顺序：

1. 顶部“路径”图层是否开启。
2. 右侧是否启用了“仅分析门限内”，而当前门限内路径为 0。
3. 传播类型筛选是否排除了所有路径。
4. API `/paths` 是否返回非空数组。
5. `outputs/radar_workbench/web_cache/<run_id>/top_paths.json` 是否存在。

需要重建缓存时，先停止服务或确认没有同一 run 的构建任务，再删除对应 run 的缓存目录，随后重新请求。

### 16.2 AoD 显示“无”

旧归档可能没有保存 `phi_t_rad/theta_t_rad`。新缓存会把缺失 AoD 明确标记为 `null`，其他路径信息仍可浏览。若研究必须使用 AoD，需要用包含发射角数组的新 runner 重新生成路径摘要。

### 16.3 MPC 一直显示正在生成

检查 API 日志和以下文件：

```text
analysis/analysis_gate_mpc_summary.json
analysis/analysis_gate_mpc.csv
figures/analysis_gate_mpc.png
```

首次生成会读取完整路径统计并绘图；后续请求会使用基于源文件修改时间的缓存。

### 16.4 波束成形返回 400 或 409

常见原因：

- 自定义权重 JSON 语法错误。
- 权重数量与 Rx 阵元数不一致。
- 权重全部为 0。
- `cir.npz` 的阵列轴与配置中的阵列规模不一致。
- 409 表示试图通过结果 API 覆盖历史 run 参数；应新建仿真快照。

### 16.5 修改参数后结果没有变化

修改参数只会更新方案和 Tx/Rx 预览。必须点击“运行雷达仿真”并等待新任务完成，才能得到对应的新传播路径、CIR、波束工件和 FMCW 结果。

### 16.6 静态场景为什么没有 Doppler

静止雷达、静止建筑和静态射线追踪下 Sionna 路径 Doppler 为 0 是预期现象，因此 Range-Doppler 峰值应位于零速度附近。平台已经实现慢时间采样和 Range-Doppler 处理，但尚未实现人体肢体或旋转部件的微多普勒模型。

## 17. 定向候选射线实现与限制

真实雷达模式固定推荐 Sionna 原生 `full_sphere`。项目保留 `analysis_sector` 作为实验性性能加速模式，不将它等同于物理发射波束。

### 17.1 物理模式与实验模式

`full_sphere` 不替换任何 Sionna 内部函数。Tx 能量方向性由公开天线方向图接口作用于 Sionna 场系数；候选射线覆盖全空间只是数值路径搜索，不表示雷达向全空间等功率辐射。

只有选择 `analysis_sector` 时，因为 Sionna RT 2.0.1 的公开 `PathSolver(...)` 没有方向扇区参数，独立仿真子进程才会临时替换初始 ray spawn 函数，求解结束后立即恢复。实现位于：

```text
experiments/sionna_radar/src/sionna_radar/directional_sampling.py
```

每次 run 会在 `metadata.json` 记录：

```text
mode
azimuth_center_deg / azimuth_width_deg
elevation_min_deg / elevation_max_deg
solid_angle_sr / solid_angle_fraction
diffuse_amplitude_correction
```

### 17.2 立体角均匀采样

扇区定义为：

```text
az in [az_center - az_width/2, az_center + az_width/2]
el in [el_min, el_max]
```

球面立体角元和扇区立体角：

```text
dOmega = cos(el) d(el) d(az)
Omega_sector = az_width_rad * (sin(el_max) - sin(el_min))
```

实现对方位使用低差异序列，并均匀采样 `sin(el)`：

```text
u  ~ Uniform(sin(el_min), sin(el_max))
el = asin(u)
```

因此样本在扇区立体角内均匀，而不是对俯仰角错误地线性均匀。

### 17.3 漫反射能量修正

Sionna 默认假设每条初始 ray tube 的立体角为：

```text
Omega_default / N = 4*pi/N
```

定向采样应使用 `Omega_sector/N`。项目在 CIR 输出前，对包含漫反射的路径幅度乘以：

```text
sqrt(Omega_sector / 4*pi)
```

镜面路径不使用该 ray-tube 立体角项，因此不做这一幅度修正。

### 17.4 当前限制

- 只约束 Tx 的初始候选方向；发生漫反射后的方向仍由材料散射模型采样。
- 扇区是硬边界；真实天线边缘通常是连续衰减，仍需通过 Tx/Rx 方向图建模。
- 定向采样提高扇区内预算，但不会发现初始方向在扇区外、经过多次反射后回到接收门限的路径。
- 该接入依赖 Sionna RT 2.0.1 内部模块；升级 Sionna 时必须重新运行 smoke test。
- 同进程线程并发不允许使用该实验模式；Web 任务通过独立外部 Python 进程隔离。
- 前端三维画布显示最终有效路径，不显示全部 500k 初始候选射线。

### 17.5 验证要求

定向实现至少应通过：

- 扇区内方向分布的直方图/球面密度检查。
- 扇区边缘、跨 `-180/180` 度和俯仰极值测试。
- 同样本预算下与全空间基线的强路径召回率比较。
- 增加样本数后的门限内能量收敛检查。
- 方向图增益与采样概率权重的独立单元测试。
- `metadata.json` 中的立体角和修正系数审计。

物理模式 smoke run 使用 Sionna RT 2.0.1 原生全空间采样、4x4 Tx 相控孔径和 2x2 原生 Rx 阵列，单反射体路径 CIR 形状为 `(1,4,1,1,1,1)` 且系数全部有限；10 m 反射路径的 FMCW 结果得到 0.149896 m 距离分辨率和 1 个 CA-CFAR 检测。实验性扇区 smoke run 的 20,000 条初始射线得到 2,190 条有效路径，作为加速模式回归基准保留。

## 18. 开发验证命令

后端测试：

```bash
PYTHONPATH=experiments/sionna_radar/src \
  .venv/bin/python -m pytest -q services/radar_api/tests
```

前端构建：

```bash
cd apps/radar-workbench
npm run build
```

代码差异检查：

```bash
git diff --check
```

后端测试、前端 TypeScript 和 Vite 构建均应通过；具体测试数量会随功能增加而变化。

## 19. 相关文档

- `README.md`：项目入口和快速启动。
- `docs/RADAR_GLOSSARY.md`：面向非专业用户的术语、MPC 对照和结果文件选择。
- `docs/USER_GUIDE.md`：界面操作、批量任务逐项产出、分项下载和删除规则。
- `docs/DEPLOYMENT_GUIDE.md`：最小打包、目标机安装、远程访问、备份和升级。
- `docs/RADAR_WORKBENCH_HANDOVER.md`：模块、数据目录、迁移和交接。
- `services/radar_api/README.md`：后端服务和运行时环境变量。
- `refine-logs/web-radar-workbench/13_IMPLEMENTATION_LOG.md`：实现过程记录。
