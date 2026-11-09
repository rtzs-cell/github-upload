# 雷达与多径传播术语及公式

最后更新：2026-07-11

本文只收录雷达、阵列信号处理和无线传播中的标准术语。平台操作参阅 `USER_GUIDE.md`。

## 1. 多径信道

### 1.1 Multipath Component, MPC

MPC 是多径分量。第 `l` 条 MPC 通常由复路径增益 `alpha_l`、传播时延 `tau_l`、到达角 AoA 和离开角 AoD 描述。

时变多径信道冲激响应可写为：

```text
h(t, tau) = sum_l alpha_l(t) * delta(tau - tau_l(t))
```

- `alpha_l=|alpha_l|exp(j*phase_l)`：复路径增益；
- `tau_l`：传播时延，单位 s；
- `delta`：Dirac 冲激。

相位决定多条路径相干叠加后增强还是抵消，因此复系数不能只用功率代替。

### 1.2 AoA 与 AoD

- AoA，Angle of Arrival：路径到达接收机的方向；
- AoD，Angle of Departure：路径离开发射机的方向；
- `phi`：方位角；
- `theta`：天顶角。本项目的 Sionna 路径角采用 `theta in [0,180 deg]`。

### 1.3 时延与等效单站距离

```text
R_l = c * tau_l / 2
```

其中 `c=299792458 m/s`。除以 2 是因为单站雷达经历去程和回程。

## 2. MPC AoA 全景谱

MPC 全景取第 0 个收发阵元对的路径幅值 `A_l=|a_l|`，按 AoA 投影到等距柱状全景图。

```text
x_l = (180 deg - phi_l) * scale
y_l = theta_l * scale
scale = 3
```

输出尺寸为方位 1080 像素、天顶角 540 像素。

有限阵列孔径的半功率波束宽度近似为：

```text
HPBW ~= 0.886 / (N*d)        [rad]
sigma = HPBW / 2.3548
```

`N` 是阵元数，`d` 是以波长为单位的阵元间距。默认采用 8×8、`d=0.5 lambda` 的矩形孔径核。

全景谱为：

```text
M(x,y) = 10log10( sum_l A_l * K(x-x_l, y-y_l) )
```

`K` 是孔径主瓣宽度对应的二维核。`mpc_panorama.npz` 保存未归一化 dB 矩阵；PNG 使用 Jet 伪彩色，只用于显示。

## 3. 阵列与波束形成

阵列导向矢量 `a(theta,phi)` 描述给定方向在各阵元上的相位差。接收波束形成输出为：

```text
y = w^H x
B(theta,phi) = |w^H a(theta,phi)|^2
```

- `w`：复波束权重；
- `H`：共轭转置；
- `B`：功率方向响应。

主瓣是最大响应附近的角域；旁瓣是其他局部峰值；零陷是响应接近零的方向。

## 4. FMCW 雷达

线性 FMCW chirp 的调频斜率：

```text
S = B / T_c
```

静止目标、忽略距离-速度耦合时：

```text
f_b ~= 2*S*R/c
R ~= c*f_b/(2*S)
```

距离分辨率：

```text
Delta_R = c/(2*B)
```

单站雷达多普勒频率和径向速度：

```text
f_D = 2*v_r/lambda
v_r = lambda*f_D/2
```

## 5. 雷达方程与 RCS

理想单站雷达方程：

```text
P_r = P_t*G_t*G_r*lambda^2*sigma / ((4*pi)^3*R^4*L)
```

- `P_t/P_r`：发射/接收功率；
- `G_t/G_r`：发射/接收增益；
- `sigma`：RCS，单位 m^2；
- `L`：系统损耗。

Sionna 路径系数不是自动校准后的目标 RCS 测量值。若要预测绝对接收功率，还需明确发射功率、天线增益、RCS 和系统损耗口径。

## 6. CA-CFAR

CA-CFAR 用训练单元平均功率估计局部背景。独立指数噪声假设下：

```text
alpha = N * (Pfa^(-1/N) - 1)
threshold = alpha * mean(training_cells)
```

- `N`：训练单元数；
- `Pfa`：设定虚警概率；
- 保护单元：避免目标能量污染背景估计。

## 7. 对数单位

```text
power_ratio_db = 10log10(P2/P1)
amplitude_ratio_db = 20log10(A2/A1)
P[dBm] = 10log10(P/1mW)
```

`dB` 是比值，`dBm` 和 `dBW` 才是带参考值的绝对功率单位。

## 8. 推荐资料

- 3GPP TR 38.901：天线与无线信道模型；
- M. A. Richards, *Fundamentals of Radar Signal Processing*；
- H. L. Van Trees, *Optimum Array Processing*；
- Sionna RT 官方文档：路径、天线阵列、材料与射线追踪 API。
