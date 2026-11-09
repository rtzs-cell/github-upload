# Sionna RT 城市单站雷达仿真实验追踪表

| Run ID | Milestone | Purpose | Scene | System / Variant | Key Parameters | Metrics | Priority | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|
| R001 | M0 | 记录环境与版本 | none | version capture | Sionna/CUDA/GPU/Python | metadata complete | MUST | DONE | 固定软件环境。 |
| R002 | M0 | 阵列方向检查 | S0 | array visualization | Tx 1x1, Rx 16x16, 0.5 lambda | orientation sanity | MUST | DONE | 确认 planar array 朝向。 |
| R003 | M1 | 同址单墙 sanity | S0 | colocated, los=False | fc=28GHz, max_depth=1 | range/angle error | MUST | DONE | 主单站实现。 |
| R004 | M1 | 小基线对照 | S0 | baseline b=0.1m, los=False | fc=28GHz, max_depth=1 | range/angle delta | MUST | DONE | 检查完全同址稳定性。 |
| R005 | M1 | LoS 错误对照 | S0 | colocated, los=True | fc=28GHz | near-zero leakage | MUST | DONE | 证明为什么主实验关闭 LoS。 |
| R006 | M2 | 一跳路径基线 | S1 | max_depth=1 | specular=True, diffuse=False | path depth histogram | MUST | DONE | 二跳验证对照。 |
| R007 | M2 | 二跳镜面验证 | S1 | max_depth=2 | specular=True, diffuse=False | depth=2 paths | MUST | DONE | 路径需可视化。 |
| R007B | M2 | 专用二跳镜面验证 | double_reflector | max_depth=2 | specular=True, diffuse=False | depth=2 paths | MUST | DONE | 补充内置双反射体场景，避免 floor-wall 几何二跳不明显。 |
| R008 | M2 | 二跳散射验证 | S1 | max_depth=2 + diffuse | scattering_coeff=0.5 | depth/type histogram | MUST | DONE | 检查二跳散射。 |
| R009 | M3 | 城市 pilot 无散射 | S2 | specular-only | max_depth=2, samples=1e6 | paths/map | MUST | DONE | 城市基线。 |
| R010 | M3 | 城市 pilot 后向散射 | S2 | BackscatteringPattern | max_depth=2, samples=1e6 | paths/map | MUST | DONE | 主配置预跑。 |
| R011 | M4 | 城市 final seed 1 | S2 | BackscatteringPattern | samples=5e6-1e7, seed=1 | range-angle map | MUST | DONE | 主结果。 |
| R012 | M4 | 城市 final seed 2 | S2 | BackscatteringPattern | samples=5e6-1e7, seed=2 | map stability | MUST | TODO | 稳定性。 |
| R013 | M4 | 城市 final seed 3 | S2 | BackscatteringPattern | samples=5e6-1e7, seed=3 | map stability | MUST | TODO | 稳定性。 |
| R014 | M4 | 城市 depth=1 | S2 | Backscatter, max_depth=1 | samples=5e6 | depth contribution | MUST | DONE | 对比二跳贡献。 |
| R015 | M4 | 城市 depth=2 | S2 | Backscatter, max_depth=2 | samples=5e6 | depth contribution | MUST | TODO | 主配置。 |
| R016 | M5 | 散射系数 0 | S2 | coeff=0.0 | Backscatter pattern set but coeff=0 | diffuse ratio | MUST | DONE | 消融。 |
| R017 | M5 | 散射系数 0.2 | S2 | coeff=0.2 | samples=5e6 | diffuse ratio | MUST | TODO | 消融。 |
| R018 | M5 | 散射系数 0.5 | S2 | coeff=0.5 | samples=5e6 | diffuse ratio | MUST | DONE | 主值。 |
| R019 | M5 | 散射系数 0.8 | S2 | coeff=0.8 | samples=5e6 | diffuse ratio | MUST | TODO | 强散射边界。 |
| R020 | M5 | Lambertian 对照 | S2 | Lambertian | coeff=0.5 | map difference | MUST | DONE | pattern 消融。 |
| R021 | M5 | Directive 对照 | S2 | Directive | coeff=0.5 | map difference | MUST | DONE | pattern 消融。 |
| R022 | M5 | Backscatter lambda sweep | S2 | lambda_ in {0.1,0.3,0.5,1.0} | alpha_i=20 | backscatter ratio | MUST | TODO | 证明后向散射参数作用。 |
| R023 | M5 | 采样收敛 | S2 | samples sweep | 1e5-1e7 | NRMSE/peak shift | MUST | TODO | 确认不是采样噪声。 |
| R024 | M6 | CIR 距离 binning | S0/S2 | direct CIR processing | B=1GHz | range peak/map | MUST | DONE | 已由 R011 后处理生成 radar_observation.npz 与 range-azimuth 图。 |
| R025 | M6 | FMCW beat signal | S0/S2 | FMCW | B=1GHz, T=40us | FFT peak vs CIR | MUST | TODO | 与雷达波形对应。 |
| R026 | M6 | 2D beamforming | S2 | Bartlett | az +/-60, el 0-40 | P(R,az,el) | MUST | TODO | 输出主 radar map。 |
| R027 | M6 | MUSIC 扩展 | S2 | MUSIC | selected range bins | peak localization | NICE | TODO | 高分辨角估计。 |
| R028 | M7 | 60 GHz 频率敏感性 | S2 | fc=60GHz | same geometry/material | map comparison | NICE | TODO | 高频边界。 |
| R029 | M7 | 77 GHz 频率敏感性 | S2 | fc=77GHz | calibrated/sensitivity materials | map comparison | NICE | TODO | 若声称 77GHz 则必须跑。 |
| R030 | M7 | refraction 扩展 | S2 | glass refraction=True | max_depth=2 | effect on map | NICE | TODO | 不属于主需求。 |
| R031 | M7 | diffraction 扩展 | S2 | diffraction=True | first-order only | effect on map | NICE | TODO | 不属于主需求。 |

## Gate Checklist

| Gate | Required Runs | Pass Condition | Status |
|---|---|---|---|
| G1：几何正确 | R003-R005 | range/angle sanity 通过，LoS 泄漏可控 | DONE |
| G2：二跳正确 | R006-R008 | depth=2 路径存在且几何可解释 | DONE_WITH_NOTE |
| G3：城市主仿真 | R009-R015 | S2 中有建筑反射/散射回波和稳定 range-angle map | DONE |
| G4：后向散射可信 | R016-R023 | pattern/系数/采样消融支持明显散射结论 | DONE_WITH_NOTE |
| G5：雷达观测成立 | R024-R026 | CIR/FMCW/beamforming 输出距离-角度图且 sanity 正确 | PARTIAL_DONE |
| G6：高频扩展 | R028-R029 | 仅在需要 60/77GHz 结论时要求通过 | TODO |
