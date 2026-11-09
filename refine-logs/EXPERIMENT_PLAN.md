# Sionna RT 城市单站雷达传播仿真实验计划

**问题**：验证 NVIDIA Sionna RT 是否能够在城市环境中完成 28 GHz 及以上毫米波单站雷达传播/回波信道仿真，并满足“同址收发、单发 16x16 阵列收、120 度方位覆盖、0-40 度俯仰覆盖、建筑物反射/散射、后向散射、约两次反射深度”的需求。

**方法主张**：将 Sionna RT 作为可微射线追踪传播求解器，生成静态单站 SIMO 雷达的多径 CIR、时延、角度和复幅度；再将 CIR 转换为距离-角度雷达观测。该仿真具备雷达传播性质，但不应被表述为开箱即用的完整雷达传感器/RCS 仿真器。

**日期**：2026-07-01

## 0. 参考依据和边界

### 0.1 文献与文档依据

| 编号 | 来源 | 相关页码/位置 | 在本计划中的作用 |
|---|---|---:|---|
| R1 | Hoydis et al., *Sionna RT: Differentiable Ray Tracing for Radio Propagation Modeling*, 2023. https://arxiv.org/abs/2303.11103 | PDF p.1 | 官方论文说明 Sionna RT 用于 radio wave propagation、CIR 计算，并将 ISAC 列为典型应用方向。 |
| R2 | Hoydis et al., 2023 | PDF p.3 | 官方论文说明 Sionna RT 可将路径转换为 CIR，并支持 specular reflection、diffuse reflection/scattering 和一阶 diffraction。 |
| R3 | Ait Aoudia et al., *Sionna RT: Technical Report*, 2025. https://arxiv.org/abs/2504.21719 | PDF p.5、p.44 | 技术报告给出 CIR 形式：多条路径复系数与传播时延的叠加，是把 Sionna 输出解释为雷达回波信道的数学基础。 |
| R4 | Ait Aoudia et al., 2025 | PDF p.9-p.10 | 技术报告说明 Sionna RT 当前支持 specular reflection、diffuse reflection、refraction、diffraction。 |
| R5 | Ait Aoudia et al., 2025 | PDF p.52 | 技术报告给出 Lambertian、Directive、Backscattering scattering pattern，其中 Backscattering pattern 明确包含朝入射方向返回的散射瓣。 |
| R6 | Liu et al., *Clutter-Aware Integrated Sensing and Communication: Models, Methods, and Future Directions*, 2026. https://arxiv.org/abs/2602.10537 | PDF p.19-p.20、p.25 | 该文使用 NVIDIA Sionna ray-tracing simulator 构造 site-specific 单站 ISAC/雷达感知环境，讨论 building backscatter、monostatic sensing、Sionna RT scene、maximum interaction depth。 |
| R7 | Yuan Liu et al., *Dynamic Indoor mmWave MIMO Radar Simulation: An Image Rendering-Based Approach*, IEEE TAP 2024. DOI: 10.1109/TAP.2024.3412269 | PDF p.1、p.3、p.7 | 该文不是 Sionna 实现，但给出雷达仿真标准路线：由 RT 得到距离、强度、AoA，再生成 FMCW MIMO 雷达信号；也说明 RCS/散射系数建模较复杂。 |
| R8 | Sionna 2.0.1 官方文档：Antenna Arrays. https://nvlabs.github.io/sionna/rt/api/antenna_array.html | API 文档 | 说明 `PlanarArray` 间距参数以 wavelength multiples 给出，可定义 16x16 接收阵列。 |
| R9 | Sionna 2.0.1 官方文档：Path Solvers、Radio Materials、Scattering tutorial. https://nvlabs.github.io/sionna/rt/ | API/教程 | 用于具体 API 配置，包括 path solving、materials、diffuse scattering、backscattering pattern。 |

### 0.2 本计划允许证明的结论

本实验计划只证明以下结论：

1. Sionna RT 可以在城市 3D mesh 中生成静态单站 SIMO 雷达所需的传播路径、CIR、时延、角度和复幅度。
2. 在打开 diffuse scattering 并配置 BackscatteringPattern 后，可以得到建筑表面后向散射和静态建筑杂波。
3. 在 `max_depth=2` 时，可以分析最多两次场景交互产生的反射/散射回波。
4. 由 CIR 可以构造距离-角度图或 FMCW beat signal，因此输出具备雷达观测性质。

本实验计划不证明以下结论：

1. Sionna RT 能开箱即用地产生经过实测标定的绝对 RCS。
2. Sionna RT 是完整雷达系统仿真器。波形、ADC、噪声、CFAR、目标检测、跟踪、硬件泄漏、天线互耦等需要另行建模。
3. 静态天线和静态场景能产生 Doppler。若无目标或平台运动，本计划只生成静态 range-angle/clutter 结果，不生成真实 Doppler。
4. 对 77 GHz 或更高频率的所有建筑材料模型都天然准确。高频材料参数必须校准或做敏感性分析。

## 1. 需求重述与必要修正

### 1.1 原始需求

| 需求 | 原始表述 | 实验计划采用方式 |
|---|---|---|
| 收发配置 | 收发位置相同，单天线发射，16x16 阵列接收 | 采用单站 SIMO 雷达配置。Tx 为 1x1，Rx 为 16x16 planar array。数值实现上优先使用同一雷达平台、近似同相位中心；为避免零距离 LoS 奇异和自泄漏，将 `los=False`，或设置 Tx/Rx 相距 5-20 cm 的小基线并按双基地总路径换算等效单站距离。 |
| 覆盖范围 | 方位角 120 度，俯仰角 0-40 度 | 雷达波束中心方位为 `az0`，方位覆盖 `az0 +/- 60 deg`；俯仰覆盖相对水平面 `0-40 deg`。实现方式为自定义天线方向图加路径后处理角度门限。 |
| 场景 | 城市环境，信号照射建筑物后由接收机接收 | 使用三层场景：解析验证场景、街谷城市场景、复杂城市 mesh 场景。建筑、地面、玻璃、金属分配 radio material。 |
| 频率 | 28 GHz 或更高 | 主实验为 28 GHz。扩展实验为 60 GHz 或 77 GHz，但只作为频率敏感性分析，不把高频材料准确性作为主结论。 |
| 散射与反射 | 开启明显散射，采用后向散射模型，反射深度约两次反射 | 设置 `specular_reflection=True`、`diffuse_reflection=True`、`max_depth=2`，材料 `scattering_coefficient > 0`，并采用 `BackscatteringPattern`。 |

### 1.2 对需求的关键修正

1. **“收发位置完全相同”改为“单站平台、近似同相位中心”**  
   真实单站雷达的 Tx/Rx 不一定是数学上完全同一点，而是同一平台上的近似同相位中心。Sionna RT 是 Tx-to-Rx 传播求解器，完全同点会产生数值上无意义的零距离直达路径。因此主实验关闭 LoS；若需要更贴近硬件，则设置小基线并单独记录 Tx/Rx 坐标。

2. **“两次反射深度”改为“最多两次场景交互”**  
   Sionna 中 `max_depth=2` 表示一条路径最多与场景对象交互两次，交互类型可以是镜面反射或漫散射。雷达中单个建筑后向散射回波通常已经是一次交互路径；两次交互用于墙-地、墙-墙、角反射或多径杂波。

3. **“雷达信号仿真”分成两层**  
   第一层是 Sionna RT 直接负责的传播信道：路径、CIR、角度、复系数。第二层是雷达信号处理：FMCW 或脉冲波形、距离 FFT、波束形成、检测。这一分层符合 R3 的 CIR 表达和 R7 的 RT-to-FMCW 仿真路线。

## 2. 仿真主张与证据映射

| Claim | 为什么重要 | 最小可信证据 | 实验块 |
|---|---|---|---|
| C1：Sionna RT 可生成单站城市雷达传播回波所需的 CIR | 证明它不是只能做通信链路，而能支持雷达回波信道 | 解析场景中路径时延、AoA、路径深度与几何一致；城市场景中能得到建筑反射/散射路径 | B1、B2、B3 |
| C2：开启 diffuse + backscattering 后能形成明显建筑散射/后向散射 | 对应用户“明显散射”和“后向散射模型”需求 | 与 specular-only 相比，路径数、角度扩展、range-angle 背景能量明显变化；后向散射瓣参数改变结果 | B3、B4 |
| C3：Sionna CIR 可转换为雷达距离-角度观测 | 证明具备雷达性质，而不仅是路径列表 | 已知反射体峰值出现在正确距离/角度；城市场景生成静态 range-angle clutter map | B5 |
| C4：`max_depth=2` 能覆盖一跳后向散射与二跳城市多径 | 对应“两次反射深度”需求 | path depth 分布显示 depth=1 和 depth=2；二跳场景的路径几何可解释 | B2、B3、B4 |
| Anti-Claim：结果不是绝对 RCS 校准雷达仿真 | 避免夸大软件能力 | 只报告相对功率、相对散射趋势；如需绝对 RCS，加入外部标定 | B4、B6 |

## 3. 系统模型

### 3.1 雷达与坐标定义

雷达平台位于城市坐标系位置

```text
p0 = [x0, y0, z0]
```

主实验推荐 `z0 = 8-15 m`，模拟楼顶或杆站雷达；若希望更接近车载雷达，可另设 `z0 = 1.5-2.5 m` 作为扩展。

Tx/Rx 实现采用二选一：

1. **主方案 A：严格同址但关闭 LoS**
   - Tx position = Rx position = `p0`
   - `los=False`
   - 优点：最接近单站几何。
   - 风险：部分求解器/版本可能对完全同点路径有边界行为，需要 sanity check。

2. **备选方案 B：小基线单站近似**
   - Tx position = `p0 + [-b/2, 0, 0]`
   - Rx position = `p0 + [ b/2, 0, 0]`
   - `b = 0.05-0.20 m`
   - `los=False`
   - 回波距离显示为 `R_eq = c tau / 2`；严格几何解释为双基地总路径长 `rho = c tau`。
   - 优点：避免完全重合坐标；更符合实际收发隔离。

所有最终结论需说明采用的是 A 还是 B。若 A 和 B 的 range-angle map 在主视场内差异很小，则可认为单站近似稳定。

### 3.2 天线配置

| 参数 | 推荐值 | 说明 |
|---|---:|---|
| Tx array | `PlanarArray(1, 1)` | 单天线发射。 |
| Rx array | `PlanarArray(16, 16)` | 16x16 接收阵列。 |
| 阵元间距 | `0.5 lambda` | Sionna `PlanarArray` spacing 参数以波长倍数给出，见 R8。 |
| 极化 | `V` 为主，`H` 或 `VH` 为扩展 | 先降低自由度；如研究交叉极化再打开双极化。 |
| 天线方向图 | 自定义 sector pattern 或 `tr38901` 近似 | 为满足 120 deg x 40 deg，应优先用自定义方向图。 |
| Rx 阵列孔径 | 28 GHz 时约 8.0 cm x 8.0 cm | `lambda = 10.7 mm`，相邻 0.5 lambda。 |
| 角分辨率 | 量级约 7-10 deg | 取决于窗函数、SNR、波束形成方法和有效孔径。 |

注意：Sionna planar array 默认位于局部 y-z 平面，方向由 radio device orientation 决定。所有实验必须先用一个已知方向的单反射体检查方位/俯仰定义，避免把 zenith、elevation 和 yaw/pitch/roll 混淆。

### 3.3 覆盖角实现

定义雷达波束中心为 `az0`，水平面为 elevation = 0。目标覆盖：

```text
azimuth:   az0 - 60 deg  <= az <= az0 + 60 deg
elevation: 0 deg         <= el <= 40 deg
```

Sionna 技术报告采用 spherical zenith angle `theta` 和 azimuth `phi`。若 elevation 相对水平面，则转换关系为：

```text
theta = 90 deg - elevation
```

因此俯仰 0-40 deg 对应：

```text
theta = 90 deg down to 50 deg
```

覆盖角采用两级控制：

1. **物理控制**：Tx/Rx 使用 sector-like antenna pattern，使视场外增益低于主瓣至少 20-30 dB。
2. **分析控制**：对输出路径按 AoD/AoA 后处理，只统计视场内路径。这样能明确区分“天线没有照亮/接收”和“场景中没有路径”。

### 3.4 频率和波形参数

| 参数 | 主实验 | 扩展 |
|---|---:|---:|
| 载频 `fc` | 28 GHz | 60 GHz、77 GHz |
| 波长 `lambda` | 10.71 mm | 5.00 mm、3.90 mm |
| 距离显示范围 `Rmax` | 200 m | 50 m、500 m 视场景调整 |
| 雷达带宽 `B` | 1 GHz | 400 MHz、2 GHz |
| 距离分辨率 | `c/(2B) = 0.15 m` | 0.375 m、0.075 m |
| FMCW chirp time | 40 us | 20-100 us |
| FMCW slope | `B/Tchirp = 25e12 Hz/s` | 随 B/T 调整 |

Sionna RT 本身不需要波形即可输出 CIR；波形参数用于把 CIR 转换为雷达距离图。若只分析传播效应，主指标可以直接基于 `tau` 和路径复系数；若要输出雷达图，则使用上述 FMCW 参数生成 beat signal 或直接对 CIR 做距离 binning。

### 3.5 场景建模

使用三层场景，避免直接在复杂城市中调试导致原因不明。

| 场景 | 目的 | 几何内容 | 必须输出 |
|---|---|---|---|
| S0：解析单墙/单平面 | 校验时延、角度、同址/小基线处理 | 单个大墙面或金属/混凝土板，距离 20/50/100 m | 路径时延、AoA/AoD、range peak |
| S1：二次反射角场景 | 校验 `max_depth=2` 和二跳路径 | 地面 + 垂直墙，或两面垂直墙形成 corner | depth=1/2 路径列表、路径可视化 |
| S2：街谷城市 | 主结论场景 | 两排建筑、道路、地面、玻璃窗、金属结构 | 建筑 backscatter、range-angle clutter map |
| S3：复杂城市 mesh | 鲁棒性场景 | OSM/Blender/Mitsuba XML 城市片区 | 采样收敛、运行成本、复杂路径统计 |

S2 是必须完成的主城市场景；S3 是扩展，用于证明方案可扩展到更复杂城市 mesh。

### 3.6 材料与散射模型

主实验材料类别：

| 对象 | 材料 | 初始散射系数 | Scattering pattern | 说明 |
|---|---|---:|---|---|
| 建筑墙体 | concrete/brick | 0.4-0.6 | BackscatteringPattern | 主散射来源。 |
| 玻璃窗 | glass | 0.1-0.3 | Directive 或 BackscatteringPattern | 同时可能有穿透，主实验可先关闭 refraction。 |
| 金属结构 | metal | 0.05-0.2 | Directive 或 specular-dominant | 避免金属漫散射过强。 |
| 地面/道路 | asphalt/concrete | 0.3-0.5 | Lambertian 或 BackscatteringPattern | 参与二跳路径和地面杂波。 |

主实验设置：

```text
specular_reflection = True
diffuse_reflection  = True
refraction          = False
diffraction         = False
max_depth           = 2
```

关闭 refraction 和 diffraction 的理由：

1. 用户需求集中在建筑照射后的反射/散射回波。
2. 高阶衍射和穿透会增加解释难度。
3. 先证明 reflection + diffuse/backscatter 能满足需求，再作为扩展加入 diffraction/refraction。

BackscatteringPattern 参数需要做扫描，而不只给一个固定值。推荐扫描：

```text
alpha_r in {5, 20}       # specular/reflection-side lobe width
alpha_i in {5, 20, 50}   # incident/backscatter-side lobe width
lambda_ in {0.1, 0.3, 0.5}
```

根据 R5，`lambda_` 控制 directive lobe 与 backscattering lobe 的能量分配；当 `lambda_ = 1` 时退化为 directive model。因此要强调后向散射，主实验不应取 `lambda_ = 1`。

### 3.7 Sionna 路径求解配置

主实验配置：

```text
PathSolver parameters:
  los=False
  specular_reflection=True
  diffuse_reflection=True
  refraction=False
  diffraction=False
  max_depth=2
  synthetic_array=True
  samples_per_src:
    S0/S1 sanity: 1e5 - 5e5
    S2 pilot:     1e6
    S2 final:     5e6 - 1e7
    S3 final:     1e7 - 2e7 if GPU budget allows
```

`synthetic_array=True` 的前提是目标/建筑距离远大于阵列孔径的近场范围。28 GHz、16x16、0.5 lambda 阵列孔径约 8 cm，Fraunhofer 距离约 `2D^2/lambda = 1.2 m`；城市建筑通常在数米到数百米，满足该假设。若有 1-2 m 内近场物体，应增加 `synthetic_array=False` 对照。

### 3.8 从 Sionna CIR 到雷达观测

Sionna CIR 形式可写作：

```text
h(tau) = sum_i a_i delta(tau - tau_i)
```

其中 `a_i` 是复路径系数，`tau_i` 是传播时延。对单站近似：

```text
R_i = c tau_i / 2
```

若采用小基线：

```text
rho_i = c tau_i = d_tx_to_scatterers_to_rx
R_eq_i = rho_i / 2
```

`R_eq_i` 是便于和单站雷达图比较的等效距离；严格几何仍是双基地总路径。

距离-角度图构造：

1. 将每条路径按 `R_i` 分入距离 bin。
2. 对每个距离 bin，使用 Rx 16x16 阵列响应做二维波束扫描。
3. 扫描方位 `az in [az0-60, az0+60]`，俯仰 `el in [0,40]`。
4. 输出 `P(R, az, el)` 或积分俯仰后的 `P(R, az)`。

若生成 FMCW beat signal：

```text
s_tx(t) = exp(j 2pi (fc t + 0.5 mu t^2))
y_n(t)  = sum_i a_{i,n} s_tx(t - tau_i)
f_b,i   = mu tau_i
R_i     = c f_b,i / (2 mu)
```

这一路线与 R7 中“RT 输出距离/强度/AoA，再生成 FMCW MIMO radar signal”的方法一致。

## 4. 实验块

### Block B1：解析单反射体 sanity check

**Claim tested**：C1、C3。

**为什么存在**：在复杂城市场景前，必须证明同址/小基线、角度定义、距离换算、阵列相位处理都是正确的。

**场景**：S0，单个大平面墙或金属板，中心位于雷达正前方 20 m、50 m、100 m；另设方位偏转 `-40, 0, +40 deg`，俯仰 `5, 20, 35 deg` 的目标点或小面片。

**系统设置**：

```text
fc = 28 GHz
Tx = 1x1
Rx = 16x16
max_depth = 1
los = False
specular_reflection = True
diffuse_reflection = False for first run
```

**对比系统**：

1. A1：严格同址、`los=False`
2. A2：小基线 `b=0.1 m`、`los=False`
3. A3：错误对照，`los=True`，用于显示直达泄漏路径为什么必须剔除

**指标**：

| 指标 | 成功判据 |
|---|---|
| 时延误差 | `|c tau/2 - R_true| < max(0.1 m, one range bin)` |
| AoA/AoD 误差 | 原始 path angle 误差 < 1 deg；波束图峰值误差 < 1 个阵列主瓣宽度 |
| 直达泄漏 | 主结果中不出现 `tau approx 0` 的 LoS 路径 |
| 同址稳定性 | A1 与 A2 主峰距离/角度一致，功率差异可解释 |

**输出图表**：

1. `fig_B1_delay_angle_check.png`
2. `table_B1_geometry_error.csv`
3. 单路径列表，含 path type、depth、tau、AoA、AoD、amplitude

**失败解释**：

若距离错误，优先检查 `tau` 是否包含 Tx-Rx 直达、坐标单位和小基线换算。若角度错误，优先检查 Sionna zenith/elevation 转换和阵列朝向。

**优先级**：MUST-RUN。

### Block B2：二次反射/二次交互验证

**Claim tested**：C1、C4。

**为什么存在**：用户明确要求“反射深度约为两次反射”。需要证明 `max_depth=2` 的输出确实包含二次场景交互路径，并能在几何上解释。

**场景**：S1，使用以下几何之一：

1. 地面 + 垂直墙：产生 ground-wall 或 wall-ground 二跳路径。
2. 两面垂直墙 corner：产生近似角反射路径。
3. 两栋楼立面形成街角：接近城市二跳杂波。

**系统设置**：

```text
fc = 28 GHz
max_depth in {1, 2}
specular_reflection = True
diffuse_reflection = False first, True second
samples_per_src = 5e5 - 1e6
```

**对比系统**：

1. D1：`max_depth=1`
2. D2：`max_depth=2`
3. D3：`max_depth=2 + diffuse_reflection=True`

**指标**：

| 指标 | 成功判据 |
|---|---|
| depth=2 路径存在性 | D2/D3 中出现 interaction depth = 2 的有效路径 |
| 路径几何一致性 | 可视化路径落在预期墙/地/墙面上 |
| 距离增加关系 | 二跳路径距离大于或等于对应一跳直观路径，且 tau 合理 |
| 贡献可解释 | D2-D1 的 range-angle 差异主要来自二跳区域 |

**输出图表**：

1. path 可视化：一跳和二跳不同颜色。
2. depth histogram。
3. `max_depth=1` vs `max_depth=2` 的 range-angle 差分图。

**失败解释**：

若没有二跳路径，可能是几何没有形成可见二跳、采样数不足、天线视场过窄或表面法线方向错误。先放宽视场和提高 `samples_per_src`，再检查 mesh 法线。

**优先级**：MUST-RUN。

### Block B3：城市单站雷达主仿真

**Claim tested**：C1、C2、C3、C4。

**为什么存在**：这是直接对应用户需求的主实验。

**场景**：S2 街谷城市场景。

推荐几何：

```text
道路宽度: 20-30 m
建筑高度: 15-60 m
街区长度: 150-300 m
雷达高度: 10-15 m
主视场方向: 沿街道或朝向建筑群
```

**系统设置**：

```text
fc = 28 GHz
Tx = single antenna
Rx = 16x16 planar array
azimuth FoV = 120 deg
elevation FoV = 0-40 deg
max_depth = 2
los = False
specular_reflection = True
diffuse_reflection = True
refraction = False
diffraction = False
scattering_pattern = BackscatteringPattern
samples_per_src = 1e6 pilot, 5e6-1e7 final
```

**对比系统**：

1. U0：no scattering，`diffuse_reflection=False`
2. U1：Lambertian diffuse scattering
3. U2：Directive scattering
4. U3：BackscatteringPattern，主结果
5. U4：`max_depth=1`
6. U5：`max_depth=2`

**指标**：

| 指标 | 成功判据 |
|---|---|
| 有效路径数 | U3 中存在来自建筑/地面的非 LoS reflected/scattered paths |
| 建筑后向散射 | 建筑立面朝向雷达区域在 range-angle 图中形成可解释回波 |
| 视场约束 | 主要能量落在 azimuth 120 deg、elevation 0-40 deg 内；视场外能量可由 sidelobe 或后处理解释 |
| 二跳贡献 | U5 相对 U4 出现额外二跳杂波或角反射结构 |
| 雷达观测 | 能生成静态 `P(R, az, el)` 或 `P(R, az)` |
| 可复现性 | 3 个随机 seed 的主结构位置一致，功率差异在可接受范围内 |

**输出图表**：

1. 城市场景俯视图，标出雷达、FoV、建筑材料。
2. 射线路径图，颜色区分 specular、diffuse、depth=1、depth=2。
3. range-angle map。
4. range-elevation map 或固定距离切片的 az-el heatmap。
5. path depth histogram。
6. path interaction type histogram。

**失败解释**：

若只有少量 specular 路径而缺少散射背景，说明散射系数、backscattering pattern、采样数或表面朝向需要调整。若结果过强且满屏杂波，说明散射系数过大或天线视场/旁瓣过宽。

**优先级**：MUST-RUN。

### Block B4：散射/后向散射消融与收敛

**Claim tested**：C2、Anti-Claim。

**为什么存在**：用户要求“开启明显散射”和“采用后向散射模型”。仅给出一张城市图不够，需要证明散射模型确实改变了结果，并且不是采样噪声。

**场景**：S0 单墙 + S2 城市主场景。

**参数扫描**：

```text
scattering_coefficient in {0.0, 0.2, 0.5, 0.8}
pattern in {Lambertian, Directive, Backscattering}
Backscattering alpha_i in {5, 20, 50}
Backscattering lambda_ in {0.1, 0.3, 0.5, 1.0}
samples_per_src in {1e5, 5e5, 1e6, 5e6, 1e7}
seeds = 3
```

**指标**：

| 指标 | 含义 | 成功判据 |
|---|---|---|
| path count | 发现的有效散射路径数 | 随 `samples_per_src` 上升后趋于稳定 |
| diffuse energy ratio | diffuse/scattered energy 占总回波比例 | `scattering_coefficient=0` 时接近 0；提高后显著增加 |
| backscatter dominance | 朝雷达返回方向的能量比例 | BackscatteringPattern 明显高于 Directive/Lambertian 的相应方向能量 |
| map stability | range-angle map 收敛 | 5e6 与 1e7 的主峰位置一致，归一化差异低于预设阈值 |
| qualitative clutter | 建筑静态杂波纹理 | 后向散射下建筑立面形成更明显、可解释背景 |

**输出图表**：

1. `scattering_coefficient` sweep 曲线。
2. Lambertian/Directive/Backscattering 三种 pattern 的 range-angle 对比。
3. samples_per_src 收敛曲线。
4. seed-to-seed 方差图。

**失败解释**：

如果后向散射与其他 pattern 差异不明显，可能是建筑面几何、天线角度、`lambda_` 参数或采样数导致。应先用 S0 单墙控制实验检查 backscatter lobe，再回到城市场景。

**优先级**：MUST-RUN。

### Block B5：雷达观测生成与核查

**Claim tested**：C3。

**为什么存在**：Sionna 输出本质是传播信道；要证明“具备雷达性质”，必须展示由 CIR 到雷达观测的转换。

**输入**：B1/B3 的 paths 或 CIR。

**处理链路**：

1. 从 `paths.cir()` 获取 `a` 和 `tau`。
2. 去除 LoS/direct leakage 和视场外路径。
3. 距离换算：`R = c tau / 2`。
4. 按 `Delta R = c/(2B)` 建立距离 bin。
5. 用 16x16 Rx 阵列做二维 Bartlett beamforming 或 MUSIC。
6. 输出：
   - `P(R, az, el)`
   - `P(R, az)`，对 elevation 积分或取最大值
   - 可选 FMCW beat signal 和 range FFT

**对比系统**：

1. Direct CIR binning，不生成时域 FMCW。
2. FMCW beat signal + range FFT。
3. Bartlett beamforming。
4. MUSIC，作为高分辨率但更敏感的扩展。

**指标**：

| 指标 | 成功判据 |
|---|---|
| 已知反射体定位 | B1 中目标峰值在正确距离/角度 |
| 城市 map 可解释性 | B3 中主要峰值可回投到建筑/地面几何 |
| 波形一致性 | CIR binning 与 FMCW range FFT 的主峰距离一致 |
| 静态性质 | 无运动设置下不声称 Doppler；Doppler 维为空或全零 |

**输出图表**：

1. B1 已知目标 range-angle peak。
2. B3 城市 range-angle map。
3. FMCW beat spectrum 与 CIR binning 对比。
4. 可选：若加入噪声，输出 SNR vs detection threshold 曲线。

**失败解释**：

若 FMCW 和 CIR binning 不一致，优先检查 chirp slope、采样率、tau 单位、baseband 相位和 range scaling。

**优先级**：MUST-RUN。

### Block B6：频率、材料和模型边界敏感性

**Claim tested**：Anti-Claim，同时支持 C1/C2 的稳健性。

**为什么存在**：用户允许 28 GHz 或更高频率。28 GHz 主结果较稳妥，但 60/77 GHz 下材料参数和表面粗糙度更敏感，必须明确边界。

**场景**：S2 城市主场景。

**参数扫描**：

```text
fc in {28 GHz, 60 GHz, 77 GHz}
material set in {default ITU-like, conservative low-scatter, aggressive high-scatter}
refraction in {False, True for glass-only extension}
diffraction in {False, True as extension}
```

**指标**：

| 指标 | 成功判据 |
|---|---|
| 主结构一致性 | 频率变化不应改变几何位置，只改变幅度、相位和材料响应 |
| 材料敏感性 | 高散射和低散射材料给出可解释差异 |
| 模型边界 | 对 77 GHz 不给出未校准的绝对功率结论 |

**输出图表**：

1. 28/60/77 GHz range-angle map 对比。
2. 材料敏感性曲线。
3. limitations table。

**失败解释**：

如果高频结果大幅异常，优先检查材料模型适用频率、mesh 尺寸相对波长、采样数和天线方向图。

**优先级**：NICE-TO-HAVE，但如果最终报告声称“或更高频率”则至少需要 60/77 GHz 中一个频点的敏感性结果。

## 5. 运行顺序与里程碑

| Milestone | 目标 | Runs | 决策门 | 成本估计 | 风险 |
|---|---|---|---|---|---|
| M0：环境锁定 | 固定 Sionna、CUDA、场景和随机 seed | 版本记录、最小 scene 加载、array 可视化 | 能运行 `PathSolver`，能输出 path/CIR | <0.5 GPU-hour | API 版本差异 |
| M1：几何 sanity | 验证同址/小基线、时延、角度 | B1 A1/A2/A3 | 距离和角度误差通过，LoS 泄漏被剔除 | 0.5-2 GPU-hours | 坐标/角度定义错误 |
| M2：二跳验证 | 验证 `max_depth=2` | B2 D1/D2/D3 | depth=2 路径存在且可视化合理 | 1-3 GPU-hours | 几何不产生二跳 |
| M3：城市 pilot | 跑通 S2 城市主场景 | B3 U0/U3 pilot | 有建筑 reflected/scattered paths 和初步 range-angle map | 2-6 GPU-hours | 采样不足或材料过弱 |
| M4：主结果 | 获得最终城市仿真 | B3 U0-U5 final | 主需求全部覆盖，3 seeds 结构稳定 | 6-24 GPU-hours | diffuse 采样成本高 |
| M5：散射消融 | 证明 backscatter 的必要性 | B4 sweep | pattern/系数差异清晰，收敛可接受 | 8-30 GPU-hours | 参数组合过多 |
| M6：雷达观测 | CIR -> range-angle/FMCW | B5 | 已知目标和城市 map 均可解释 | CPU/GPU 少量 | 信号处理 scaling 错 |
| M7：扩展边界 | 高频/材料敏感性 | B6 | 明确 28 GHz 以外的适用边界 | 4-20 GPU-hours | 材料缺乏标定 |

必须运行：M0-M6。  
可选运行：M7，但若最终结论要强调 77 GHz，则 M7 变为必须运行。

## 6. 参数总表

### 6.1 主配置

| 类别 | 参数 | 值 |
|---|---|---|
| 载频 | `fc` | 28 GHz |
| Tx | array | 1x1, V polarization |
| Rx | array | 16x16 planar, 0.5 lambda spacing, V polarization |
| 平台 | position | `[x0, y0, z0]`，`z0=10-15 m` 主实验 |
| 同址处理 | LoS | `los=False` |
| FoV | azimuth | `az0 +/- 60 deg` |
| FoV | elevation | `0-40 deg` |
| 路径深度 | `max_depth` | 2 |
| 反射 | specular | True |
| 散射 | diffuse | True |
| 后向散射 | pattern | BackscatteringPattern |
| 折射 | refraction | False |
| 绕射 | diffraction | False |
| 雷达带宽 | B | 1 GHz |
| 距离窗 | Rmax | 200 m |
| 距离分辨率 | Delta R | 0.15 m |
| 采样 | `samples_per_src` | pilot 1e6，final 5e6-1e7 |
| 随机性 | seeds | 3 |

### 6.2 必须记录的元数据

每次运行必须记录：

1. Sionna version、Python version、CUDA/driver、GPU 型号。
2. 场景文件 hash、材料表、天线方向图文件 hash。
3. Tx/Rx position 和 orientation。
4. PathSolver 全部参数。
5. `samples_per_src` 和 random seed。
6. 输出路径总数、有效路径数、depth 分布、interaction type 分布。
7. 是否使用 `synthetic_array`。

## 7. 输出文件与核查材料

推荐输出目录：

```text
outputs/
  configs/
    run_*.yaml
  paths/
    run_*_paths.npz or .h5
  cir/
    run_*_cir.npz
  metrics/
    run_*_metrics.csv
  figures/
    scene_overview.png
    ray_paths_depth.png
    range_angle_map.png
    scattering_ablation.png
    convergence.png
```

每个主图必须可追溯到具体 run config。不要只保存图片，必须保存 path/CIR 原始数据，否则无法复查。

## 8. 评价指标定义

### 8.1 几何正确性

```text
range_error = |c tau / 2 - R_reference|
angle_error_az = |az_est - az_reference|
angle_error_el = |el_est - el_reference|
```

B1 中要求：

```text
range_error < max(0.1 m, Delta R)
raw path angle error < 1 deg
beam peak error < mainlobe width
```

### 8.2 散射强度指标

```text
E_total = sum_i |a_i|^2
E_diffuse = sum_{i in diffuse paths} |a_i|^2
diffuse_ratio = E_diffuse / E_total
```

对 backscattering pattern，再统计朝入射反向附近角域的能量：

```text
backscatter_ratio = E_within_backscatter_lobe / E_diffuse
```

成功条件：

1. `scattering_coefficient=0` 时 `diffuse_ratio` 接近 0。
2. `scattering_coefficient` 增大时 `diffuse_ratio` 增大。
3. BackscatteringPattern 在建筑正对雷达方向给出比 Directive/Lambertian 更强的后向回波。

### 8.3 雷达图稳定性

定义归一化 range-angle map：

```text
P_norm = P / max(P)
```

不同 seed 或不同采样数之间比较：

```text
NRMSE = ||P_norm_A - P_norm_B||_2 / ||P_norm_A||_2
peak_shift = distance between dominant peaks
```

建议通过标准：

```text
dominant peak locations stable within 1 range bin and 1 angular bin
NRMSE between 5e6 and 1e7 samples < 0.1 for main FoV
```

该阈值可根据场景复杂度调整，但必须预先写入 config 或实验记录。

## 9. 预期主要图表

| 图/表 | 内容 | 支持结论 |
|---|---|---|
| Table 1 | 参数总表和需求对应表 | 证明满足用户需求 |
| Fig. 1 | 城市场景、雷达位置、FoV | 场景可核查 |
| Fig. 2 | B1 几何 sanity：距离/角度误差 | C1、C3 |
| Fig. 3 | B2 depth=1 vs depth=2 路径图 | C4 |
| Fig. 4 | 城市 range-angle map | C1、C3 |
| Fig. 5 | Specular-only vs Backscatter diffuse | C2 |
| Fig. 6 | Scattering coefficient / pattern sweep | C2、Anti-Claim |
| Fig. 7 | Samples/seeds 收敛 | 可信度 |
| Table 2 | 限制与不声称内容 | 防止过度结论 |

## 10. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 完全同址 Tx/Rx 产生零距离 LoS 或数值异常 | 雷达距离图出现无意义近零峰 | `los=False`；使用小基线对照；显式剔除 direct path |
| diffuse scattering 采样噪声大 | 后向散射图不稳定 | 提高 `samples_per_src`；3 seeds；先用 S0 单墙调参 |
| 材料参数缺乏实测标定 | 绝对功率/RCS 不可信 | 主报告只声明相对回波和传播结构；若需要绝对 RCS，加入实测或外部 EM/RCS 标定 |
| 天线 FoV 不能用默认 pattern 精确表达 | 120 deg x 40 deg 覆盖不严格 | 自定义 sector pattern；后处理 AoA/AoD mask；报告两种口径 |
| 角度定义混淆 | range-angle 图方向错误 | B1 单目标 sanity；记录 Sionna theta/phi 与 elevation/azimuth 转换 |
| 城市 mesh 法线或尺度错误 | 反射/散射异常 | 加载后做 mesh 可视化、法线检查、已知距离测量 |
| `max_depth=2` 被误解为两次“雷达往返” | 结论不严谨 | 报告中明确写作“最多两次场景交互” |
| 77 GHz 材料模型超出默认适用性 | 高频结论不可靠 | 28 GHz 为主结论；77 GHz 只做敏感性或使用校准材料 |

## 11. 最终判定规则

若以下条件全部满足，可判定“该配置下 Sionna RT 可以仿真出具备雷达性质的城市毫米波传播效应”：

1. B1 通过：已知目标距离和角度正确，LoS 泄漏被剔除。
2. B2 通过：`max_depth=2` 产生可解释的二次交互路径。
3. B3 通过：城市 S2 场景中存在建筑 reflected/scattered/backscattered paths，并生成稳定 range-angle map。
4. B4 通过：BackscatteringPattern 和散射系数对结果有明确、可重复影响。
5. B5 通过：CIR 可转换为正确的距离-角度雷达观测。
6. 报告明确不声称绝对 RCS、硬件泄漏、Doppler 和完整传感器链路，除非另行建模。

若 B1/B2 不通过，不得进入城市主结论。  
若 B3 通过但 B4 不通过，只能声明“可做反射传播仿真”，不能声明“明显后向散射仿真”。  
若 B5 不通过，只能声明“传播信道可仿真”，不能声明“雷达观测可生成”。

## 12. 最小可执行伪代码

以下伪代码用于固定实验思路，具体 API 以当前 Sionna 版本为准。

```python
from sionna.rt import (
    load_scene, PlanarArray, Transmitter, Receiver,
    PathSolver, BackscatteringPattern
)

scene = load_scene("urban_scene.xml")
scene.frequency = 28e9

scene.tx_array = PlanarArray(
    num_rows=1,
    num_cols=1,
    vertical_spacing=0.5,
    horizontal_spacing=0.5,
    pattern="iso",
    polarization="V",
)

scene.rx_array = PlanarArray(
    num_rows=16,
    num_cols=16,
    vertical_spacing=0.5,
    horizontal_spacing=0.5,
    pattern="iso",
    polarization="V",
)

p0 = [x0, y0, z0]
scene.add(Transmitter("tx", position=p0, orientation=[az0, el0, 0.0], power_dbm=30))
scene.add(Receiver("rx", position=p0, orientation=[az0, el0, 0.0]))

for obj in scene.objects.values():
    mat = obj.radio_material
    if mat is None:
        continue
    mat.scattering_coefficient = 0.5
    mat.scattering_pattern = BackscatteringPattern(
        alpha_r=20,
        alpha_i=20,
        lambda_=0.3,
    )

solver = PathSolver()
paths = solver(
    scene,
    max_depth=2,
    los=False,
    specular_reflection=True,
    diffuse_reflection=True,
    refraction=False,
    diffraction=False,
    synthetic_array=True,
    samples_per_src=5_000_000,
)

a, tau = paths.cir(normalize_delays=False, out_type="numpy")

# Post-processing:
# 1. remove direct/self-leakage if any
# 2. convert tau to range R=c*tau/2
# 3. filter AoA/AoD to az0 +/- 60 deg and elevation 0-40 deg
# 4. beamform with 16x16 Rx array
# 5. save range-angle/range-elevation maps
```

## 13. 最终检查清单

- [ ] 参考文献页码已在报告中列明。
- [ ] 需求表逐条对应原始需求。
- [ ] 同址 Tx/Rx 的数值处理已说明。
- [ ] `max_depth=2` 被表述为“最多两次场景交互”。
- [ ] 28 GHz 主结果完成。
- [ ] 16x16 Rx 阵列和 0.5 lambda 间距记录。
- [ ] 120 deg 方位和 0-40 deg 俯仰通过天线 pattern 或后处理实现。
- [ ] 城市场景 mesh、材料、法线、尺度可核查。
- [ ] Diffuse scattering 与 BackscatteringPattern 已开启并做消融。
- [ ] Range-angle map 由 CIR 生成，并通过解析场景 sanity check。
- [ ] 报告中没有声称未经标定的绝对 RCS。
- [ ] 报告中没有声称静态场景存在 Doppler。
