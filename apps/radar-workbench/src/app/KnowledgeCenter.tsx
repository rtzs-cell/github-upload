import { useMemo, useState, type ReactNode } from 'react'
import { BookOpen, Search } from 'lucide-react'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import type { KnowledgeTopic } from './knowledgeTopics'

const glossary = [
  ['CIR', 'Channel Impulse Response，信道冲激响应。用复路径增益和传播时延描述多径信道。'],
  ['MPC', 'Multipath Component，多径分量。本平台的 MPC 主产品是按 AoA 投影的全景空间谱。'],
  ['AoA / AoD', 'Angle of Arrival / Departure，到达角与离开角。'],
  ['Path gain', '复路径增益，包含幅度衰减和传播相位。'],
  ['Delay', '传播时延，单位 s；单站等效距离为 cτ/2。'],
  ['Array manifold', '阵列流形或导向矢量，描述某方向在不同阵元上的相位差。'],
  ['Beamforming', '波束形成，使用复权重对阵元信号进行相干组合。'],
  ['HPBW', 'Half-Power Beamwidth，半功率波束宽度，即主瓣下降 3 dB 两点之间的角宽。'],
  ['FMCW', 'Frequency-Modulated Continuous Wave，调频连续波雷达。'],
  ['Fast / slow time', 'chirp 内 ADC 采样维与 chirp 间序列维，分别主要承载距离和 Doppler 信息。'],
  ['CFAR', 'Constant False Alarm Rate，根据局部背景估计自适应设置检测门限。'],
  ['RCS', 'Radar Cross Section，雷达散射截面积，单位 m²。'],
  ['dB / dBm', 'dB 是比值；dBm 是以 1 mW 为参考的绝对功率单位。'],
  ['Specular reflection', '镜面反射，服从几何光学反射定律。'],
  ['Diffuse reflection', '漫反射，粗糙表面将能量散射到多个方向。'],
  ['Synthetic array', '使用参考点路径与远场阵列相位关系构造阵元响应的计算模型。'],
] as const

function Equation({ latex, number, note }: { latex: string; number: string; note: ReactNode }) {
  const html = useMemo(() => katex.renderToString(latex, { displayMode: true, throwOnError: false, strict: false }), [latex])
  return <figure className="knowledge-equation">
    <div className="equation-row"><div className="equation-math" dangerouslySetInnerHTML={{ __html: html }} /><span className="equation-number">({number})</span></div>
    <figcaption>{note}</figcaption>
  </figure>
}

function InlineMath({ latex }: { latex: string }) {
  const html = useMemo(() => katex.renderToString(latex, { displayMode: false, throwOnError: false, strict: false }), [latex])
  return <span className="inline-math" dangerouslySetInnerHTML={{ __html: html }} />
}

function Chapter({ number, title, intro, sections, children }: { number: string; title: string; intro: string; sections: Array<[string, string]>; children: ReactNode }) {
  return <>
    <header className="chapter-header"><span>第 {number} 章</span><h1>{title}</h1><p>{intro}</p></header>
    <nav className="chapter-toc" aria-label="本章目录"><strong>本章目录</strong>{sections.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}</nav>
    {children}
  </>
}

function Section({ id, number, title, children }: { id: string; number: string; title: string; children: ReactNode }) {
  return <section className="tutorial-section" id={id}><h2><span>{number}</span>{title}</h2>{children}</section>
}

function ParameterTable({ rows }: { rows: Array<[string, string, string, string]> }) {
  return <div className="knowledge-table-wrap"><table className="knowledge-table"><thead><tr><th>参数</th><th>单位/类型</th><th>物理含义</th><th>如何验证</th></tr></thead><tbody>{rows.map((row) => <tr key={row[0]}>{row.map((cell, index) => <td key={index}>{cell}</td>)}</tr>)}</tbody></table></div>
}

function StartChapter() {
  return <Chapter number="1" title="从实验方案到可下载结果" intro="本章先建立平台的数据模型和完整操作路径。完成后，你应能创建实验、运行一次仿真、找到 MPC 与传播路径，并选择正确的下载文件。" sections={[["workspace", "1.1 工作区结构"], ["first-run", "1.2 第一次仿真"], ["read-order", "1.3 结果阅读顺序"], ["data-relation", "1.4 数据关系"]]}>
    <Section id="workspace" number="1.1" title="工作区结构">
      <p>左侧负责选择数据，中央负责场景和结果，右侧负责参数与路径检查。顶部状态显示 Sionna RT 版本、加载状态以及批量任务中已经完成并可下载的测点数。</p>
      <table className="knowledge-table"><thead><tr><th>区域</th><th>主要内容</th><th>使用原则</th></tr></thead><tbody>
        <tr><td>实验方案</td><td>场景、雷达、阵列和信号处理参数</td><td>方案可编辑，但不包含 CIR 或 MPC 结果</td></tr>
        <tr><td>仿真结果</td><td>已经完成的测点结果</td><td>参数不可原地修改；修改后应提交新仿真</td></tr>
        <tr><td>术语教程</td><td>原理、公式、操作和排错</td><td>章节与界面功能一一对应</td></tr>
      </tbody></table>
    </Section>
    <Section id="first-run" number="1.2" title="第一次仿真">
      <ol className="knowledge-steps">
        <li><strong>建立方案</strong><span>进入“实验方案”，点击新建。首次实验保留默认两楼场景。</span></li>
        <li><strong>设置几何</strong><span>确认雷达中心、观察点和分析距离。主视轴由中心指向观察点。</span></li>
        <li><strong>降低复杂度</strong><span>最大反射阶数设为 1，先关闭漫反射，使用较少射线验证几何距离。</span></li>
        <li><strong>检查波束</strong><span>观察 Tx/Rx 预览，确认相对导向角 0° 对准主视轴。</span></li>
        <li><strong>运行</strong><span>点击“运行雷达仿真”。完成后平台自动切换到该结果。</span></li>
        <li><strong>逐步加复杂</strong><span>基线正确后再增加反射阶数、漫反射和射线数。</span></li>
      </ol>
    </Section>
    <Section id="read-order" number="1.3" title="结果阅读顺序">
      <p>推荐按“几何是否正确 → 传播是否合理 → 信号处理是否合理”的顺序检查：</p>
      <div className="knowledge-flow"><span>概览与主峰距离</span><b>→</b><span>MPC 全景</span><b>→</b><span>单条传播路径</span><b>→</b><span>波束形成</span><b>→</b><span>FMCW/CFAR</span><b>→</b><span>下载归档</span></div>
    </Section>
    <Section id="data-relation" number="1.4" title="方案、任务与结果">
      <p><strong>实验方案</strong>是参数模板；<strong>仿真任务</strong>是一次计算提交；<strong>仿真结果</strong>是一个已完成测点的数据快照；<strong>结果包</strong>是该结果的文件归档。删除方案不会删除结果，删除本地结果也不会删除来源方案。</p>
      <div className="knowledge-callout"><strong>内置示例结果</strong><span>内置示例用于对照，不属于用户仿真结果，因此保持只读；本地仿真结果可以逐条删除。</span></div>
    </Section>
  </Chapter>
}

function GeometryChapter() {
  return <Chapter number="2" title="场景、坐标与雷达几何" intro="雷达位置和方向定义了所有角度的参考系。很多看似异常的 AoA、波束或 MPC 图，根源其实是坐标约定没有理解一致。" sections={[["coordinates", "2.1 世界坐标"], ["boresight", "2.2 主视轴"], ["angles", "2.3 AoA/AoD"], ["gate", "2.4 分析范围"], ["scene-edit", "2.5 场景参数"]]}>
    <Section id="coordinates" number="2.1" title="世界坐标与位置">
      <p>雷达中心为 <InlineMath latex="\mathbf p_r=[x_r,y_r,z_r]^T" />，观察点为 <InlineMath latex="\mathbf p_t" />。单位均为米。场景建筑使用中心点和长宽高定义包围盒。</p>
      <Equation latex="\mathbf b=\frac{\mathbf p_t-\mathbf p_r}{\lVert\mathbf p_t-\mathbf p_r\rVert_2}" number="2.1" note={<>向量 <InlineMath latex="\mathbf b" /> 是雷达主视轴单位向量。观察点只确定朝向，不表示该点一定存在目标。</>} />
    </Section>
    <Section id="boresight" number="2.2" title="主视轴与相对导向角">
      <Equation latex="\psi_b=\operatorname{atan2}(b_y,b_x),\qquad \eta_b=\operatorname{atan2}\!\left(b_z,\sqrt{b_x^2+b_y^2}\right)" number="2.2" note="ψ_b 为世界坐标方位角，η_b 为仰角。界面中的 Tx/Rx 导向角是相对主视轴的偏移，不是绝对世界方位。" />
      <p>因此“导向方位 0°、导向俯仰 0°”表示波束沿主视轴，而不是固定沿世界坐标 +X。</p>
    </Section>
    <Section id="angles" number="2.3" title="AoA 与 AoD 角度约定">
      <p>Sionna 路径以方位角 <InlineMath latex="\phi\in[-\pi,\pi]" /> 和天顶角 <InlineMath latex="\theta\in[0,\pi]" /> 表示方向。天顶角 0° 指向 +Z，90° 位于水平面，180° 指向 -Z。</p>
      <Equation latex="\mathbf u(\theta,\phi)=\begin{bmatrix}\sin\theta\cos\phi\\\sin\theta\sin\phi\\\cos\theta\end{bmatrix}" number="2.3" note="该单位方向向量用于角度投影、阵列流形和方向图计算。AoA 与 AoD 分别在接收端和发射端定义。" />
    </Section>
    <Section id="gate" number="2.4" title="分析角域与距离范围">
      <p>方位宽度、俯仰上下界和最大距离用于对已求出的路径做分析筛选。它们不是天线方向图，也不会自动使 Sionna 只向该范围发射候选射线。</p>
      <Equation latex="m_l=\mathbb 1\!\left(|\Delta\phi_l|\leq\frac{\Phi}{2},\ \eta_{\min}\leq\eta_l\leq\eta_{\max},\ R_l\leq R_{\max}\right)" number="2.4" note="m_l 是路径筛选标记；Φ 为方位宽度。角度差 Δφ 必须按圆周角处理。" />
    </Section>
    <Section id="scene-edit" number="2.5" title="主要几何参数">
      <ParameterTable rows={[
        ['雷达 x/y/z', 'm', 'Tx/Rx 中心位置', '三维视图中的雷达标记应位于预期位置'],
        ['指向点 x/y/z', 'm', '定义主视轴', '灰色主视轴应穿过预期建筑或区域'],
        ['Tx-Rx 基线', 'm', '准单站收发位置间距', '基线远小于目标距离时才接近单站模型'],
        ['最大距离', 'm', '分析与距离图显示范围', '主峰不应被截断在最远距离边界'],
        ['场景材料', '材料模型', '影响反射、透射和散射系数', '更换材料后比较路径幅度而非只比较路径数'],
      ]} />
    </Section>
  </Chapter>
}

function PropagationChapter() {
  return <Chapter number="3" title="Sionna RT 传播求解" intro="本章解释哪些工作由 Sionna PathSolver 完成、各传播开关的物理含义，以及射线数量和反射阶数如何影响计算成本与结果收敛。" sections={[["cir", "3.1 多径信道"], ["mechanisms", "3.2 传播机制"], ["sampling", "3.3 射线采样"], ["depth", "3.4 路径深度"], ["convergence", "3.5 收敛检查"]]}>
    <Section id="cir" number="3.1" title="路径与信道冲激响应">
      <Equation latex="h(t,\tau)=\sum_{l=1}^{L}\alpha_l(t)\,\delta\!\left(\tau-\tau_l(t)\right)" number="3.1" note={<>第 l 条路径由复增益 <InlineMath latex="\alpha_l" /> 和时延 <InlineMath latex="\tau_l" /> 描述。复增益的相位必须保留，才能进行阵列相干合成。</>} />
      <Equation latex="R_l=\frac{c\tau_l}{2}" number="3.2" note="单站雷达等效距离。除以 2 是因为传播时延包含发射与返回的双程距离。" />
    </Section>
    <Section id="mechanisms" number="3.2" title="传播机制开关">
      <ParameterTable rows={[
        ['LoS', '布尔', '无遮挡直达传播', '单站 Tx/Rx 很近时可能产生近零时延直达项，需检查最小时延过滤'],
        ['镜面反射', '布尔', '满足反射定律的表面反射', '简单平面场景应出现几何可解释的反射路径'],
        ['漫反射', '布尔', '粗糙表面的方向性散射', '开启后路径数通常显著增加，弱能量背景更丰富'],
        ['绕射', '布尔', '边缘附近的绕射传播', '遮挡区可能新增路径，但计算成本增加'],
        ['折射/透射', '布尔', '穿透介质边界的传播', '需要材料参数与场景网格支持'],
      ]} />
    </Section>
    <Section id="sampling" number="3.3" title="候选射线采样">
      <p><strong>全空间采样</strong>是物理基线，候选方向覆盖整个球面；<strong>扇区采样</strong>是实验性加速方式，只限制候选初始方向，可能漏掉先向扇区外传播、经多次反射后返回的路径。</p>
      <Equation latex="\widehat I_N=\frac{1}{N}\sum_{n=1}^{N}\frac{f(\Omega_n)}{p(\Omega_n)}" number="3.3" note="Monte Carlo 估计形式。N 为样本数，p(Ω) 为方向采样密度。改变采样域时必须保留相应权重，否则能量估计会偏置。" />
    </Section>
    <Section id="depth" number="3.4" title="最大交互深度与计算量">
      <p>最大深度限制一条路径允许经历的交互次数。深度增加会扩大候选组合，计算量和路径数可能快速增长。首次验证使用深度 1；确认单反射正确后再逐级增加。</p>
    </Section>
    <Section id="convergence" number="3.5" title="射线数与随机种子">
      <p>路径求解包含随机采样时，单次图像不是收敛证明。至少比较两档射线数和多个随机种子。</p>
      <Equation latex="\varepsilon_R=\frac{|R_{\text{peak},2}-R_{\text{peak},1}|}{\max(R_{\text{peak},1},\epsilon)},\qquad \varepsilon_P=\frac{|P_2-P_1|}{\max(P_1,\epsilon)}" number="3.4" note="可用主峰距离变化和总能量变化作为基础收敛指标。允许误差应按具体研究目标预先规定。" />
    </Section>
  </Chapter>
}

function ArrayChapter() {
  return <Chapter number="4" title="天线阵列与波束形成" intro="平台区分发射天线物理方向图、阵列相位响应和接收数字波束形成。三者都会影响路径权重，但作用位置不同。" sections={[["upa", "4.1 UPA 阵列"], ["steering", "4.2 导向矢量"], ["tx-pattern", "4.3 Tx 方向图"], ["rx-beam", "4.4 Rx 波束"], ["preview", "4.5 预览判读"]]}>
    <Section id="upa" number="4.1" title="均匀平面阵列">
      <p>阵列由行数、列数和以波长为单位的间距定义。常用 0.5λ 间距可降低可见空间中的栅瓣风险。</p>
      <Equation latex="\mathbf r_{m,n}=\begin{bmatrix}0 & nd_h\lambda & md_v\lambda\end{bmatrix}^{T}" number="4.1" note="m、n 为行列索引；d_v、d_h 是以波长为单位的间距。具体轴方向服从平台阵列坐标约定。" />
    </Section>
    <Section id="steering" number="4.2" title="阵列流形与导向矢量">
      <Equation latex="a_{m,n}(\theta,\phi)=\exp\!\left(j\frac{2\pi}{\lambda}\mathbf r_{m,n}^{T}\mathbf u(\theta,\phi)\right)" number="4.2" note="阵元位置与入射单位方向的内积决定相位差。导向矢量由所有阵元响应组成。" />
      <Equation latex="\mathbf w(\theta_0,\phi_0)=\frac{\mathbf a(\theta_0,\phi_0)}{\lVert\mathbf a(\theta_0,\phi_0)\rVert_2}" number="4.3" note="常规相移波束形成权重。归一化避免仅因阵元数量变化而任意放大输出。" />
    </Section>
    <Section id="tx-pattern" number="4.3" title="发射方向图">
      <Equation latex="G_{\mathrm{Tx}}(\theta,\phi)=G_{\mathrm{elem}}(\theta,\phi)\,\left|\mathbf w_{\mathrm{Tx}}^{H}\mathbf a_{\mathrm{Tx}}(\theta,\phi)\right|^2" number="4.4" note="阵元方向图与阵列因子共同形成发射增益。该增益进入 Sionna 路径复系数，不是求解后的显示筛选。" />
      <p>均匀窗主瓣较窄但旁瓣较高；Hann 窗降低旁瓣，同时会展宽主瓣。方向图预览应显示主瓣峰值位于设定的相对导向角。</p>
    </Section>
    <Section id="rx-beam" number="4.4" title="接收数字波束形成">
      <Equation latex="z_l=\mathbf w_{\mathrm{Rx}}^{H}\,\mathbf H_l\,\mathbf w_{\mathrm{Tx}},\qquad P_l=|z_l|^2" number="4.5" note="H_l 是第 l 条路径的阵列信道矩阵。先做复数相干组合，再取模平方；不能先对阵元功率求和。" />
      <ParameterTable rows={[
        ['disabled', '模式', '不应用数字接收波束', '用于比较波束形成前后的变化'],
        ['uniform', '模式', '所有阵元同权组合', '主瓣通常指向阵列参考方向'],
        ['steering vector', '模式', '对指定方向做相位补偿', '预览峰值与设定导向角一致'],
        ['自定义复权重', '复数组', '用户提供每个阵元的复权重', '权重数量必须等于接收阵元数'],
      ]} />
    </Section>
    <Section id="preview" number="4.5" title="怎样判断预览正确">
      <ul className="knowledge-checklist"><li>主瓣峰值位于设定的相对导向角。</li><li>增加阵列孔径后主瓣通常变窄。</li><li>使用 Hann 窗后旁瓣降低、主瓣变宽。</li><li>改变 Rx 导向只影响后端数字合成，不应改变已经求出的路径几何。</li></ul>
    </Section>
  </Chapter>
}

function MpcChapter() {
  return <Chapter number="5" title="MPC AoA 全景空间谱" intro="本章完整说明 MPC 数据链：路径系数选择、角度投影、孔径核、dB 变换、归一化、透视裁切和下载文件。" sections={[["mpc-input", "5.1 输入口径"], ["projection", "5.2 全景投影"], ["kernel", "5.3 孔径核"], ["normalization", "5.4 dB 与归一化"], ["perspective", "5.5 透视视图"], ["mpc-files", "5.6 文件与判读"]]}>
    <Section id="mpc-input" number="5.1" title="路径系数选择">
      <p>MPC 全景取 CIR 中第 0 个 Rx、第 0 个 Rx 阵元、第 0 个 Tx、第 0 个 Tx 阵元的路径复系数。</p>
      <Equation latex="A_l=\left|a_{0,0,0,0,l}\right|" number="5.1" note="A_l 是用于全景绘制的路径幅值，不使用波束形成后的路径功率。" />
    </Section>
    <Section id="projection" number="5.2" title="AoA 到等距柱状像素">
      <Equation latex="x_l=(180^{\circ}-\phi_l)s,\qquad y_l=\theta_l s,\qquad s=3" number="5.2" note="φ_l 为 AoA 方位角，θ_l 为 AoA 天顶角。输出宽 360s=1080，高 180s=540。" />
      <p>全景横轴覆盖 360° 方位，纵轴覆盖 0° 至 180° 天顶角。该图表达“能量从哪个方向到达”，不包含距离轴。</p>
    </Section>
    <Section id="kernel" number="5.3" title="有限孔径角分辨率">
      <Equation latex="\mathrm{HPBW}\approx\frac{0.886}{Nd},\qquad \sigma=\frac{\mathrm{HPBW}}{2\sqrt{2\ln2}}" number="5.3" note="N 为对应方向阵元数，d 以波长为单位。默认 N=8、d=0.5，矩形窗。σ 再按每度 3 像素换算到图像坐标。" />
      <Equation latex="I(x,y)=\sum_l A_l\,K_{\sigma_\phi,\sigma_\theta}(x-x_l,y-y_l)" number="5.4" note="每条理想角度点用二维核展宽，并在线性幅值域相加。核尺寸由本项目的孔径参数确定。" />
    </Section>
    <Section id="normalization" number="5.4" title="dB 变换与显示范围">
      <Equation latex="M_{\mathrm{dB}}(x,y)=10\log_{10} I(x,y)" number="5.5" note="这是本项目 MPC 空间谱的数据定义。它不同于对单个电压或场幅度比使用 20log10。" />
      <Equation latex="M_{\mathrm{norm}}=\operatorname{clip}\!\left(\frac{M_{\mathrm{dB}}-(q_{99.5}-40)}{40},0,1\right)" number="5.6" note="单帧预览以上侧 99.5 百分位为峰值，显示其下 40 dB。跨测点训练必须使用统一全局上下界。" />
    </Section>
    <Section id="perspective" number="5.5" title="四方向透视裁切">
      <p>前、右、后、左四张图均由同一全景重投影得到，水平 FOV 为 90°，尺寸 300×200。每个接收位置只运行一次路径求解，不应为了四个视图重复运行 Sionna RT。</p>
    </Section>
    <Section id="mpc-files" number="5.6" title="文件与结果判读">
      <table className="knowledge-table"><thead><tr><th>文件</th><th>内容</th><th>用途</th></tr></thead><tbody>
        <tr><td><code>mpc_panorama.npz</code></td><td>未归一化 dB 数组、归一化数组和角度坐标</td><td>定量分析与机器学习</td></tr>
        <tr><td><code>mpc_panorama.png</code></td><td>Jet 伪彩色全景</td><td>快速观察角度结构</td></tr>
        <tr><td><code>mpc_view_*.png</code></td><td>四张 90° 透视图</td><td>与视觉相机方向对齐</td></tr>
        <tr><td><code>analysis_gate_mpc.csv</code></td><td>门限内逐路径表</td><td>传播解释；不是 MPC 全景主产品</td></tr>
      </tbody></table>
      <div className="knowledge-callout"><strong>重要限制</strong><span>伪彩色只表示归一化后的相对强弱。比较不同位置的绝对强度时必须读取未归一化 dB 数组，并使用相同的全局标定范围。</span></div>
    </Section>
  </Chapter>
}

function FmcwChapter() {
  return <Chapter number="6" title="FMCW、距离-Doppler 与 CFAR" intro="本章从线性调频波形开始，说明距离 FFT、Doppler FFT、热噪声和 CA-CFAR 的公式及页面指标。" sections={[["chirp", "6.1 Chirp"], ["range", "6.2 距离处理"], ["doppler", "6.3 速度处理"], ["noise", "6.4 噪声"], ["cfar", "6.5 CA-CFAR"], ["radar-result", "6.6 结果判读"]]}>
    <Section id="chirp" number="6.1" title="线性调频波形">
      <Equation latex="s_{\mathrm{tx}}(t)=\exp\!\left[j2\pi\left(f_ct+\frac{1}{2}St^2\right)\right],\qquad S=\frac{B}{T_c}" number="6.1" note="f_c 为载频，B 为扫频带宽，T_c 为 chirp 时长，S 为调频斜率。" />
    </Section>
    <Section id="range" number="6.2" title="拍频、距离与分辨率">
      <Equation latex="f_b\approx S\tau=\frac{2SR}{c},\qquad R\approx\frac{cf_b}{2S}" number="6.2" note="静止目标且忽略距离-速度耦合时成立。快时间 FFT 将拍频映射到距离单元。" />
      <Equation latex="\Delta R=\frac{c}{2B}" number="6.3" note="理论距离分辨率由有效扫频带宽决定，与显示像素数不是同一概念。" />
    </Section>
    <Section id="doppler" number="6.3" title="Doppler 与径向速度">
      <Equation latex="f_D=\frac{2v_r}{\lambda},\qquad v_r=\frac{\lambda f_D}{2}" number="6.4" note="慢时间 FFT 估计 chirp 间相位变化。静态建筑在理想模型中应接近零速度。" />
      <Equation latex="\Delta v\approx\frac{\lambda}{2NT_r}" number="6.5" note="N 为 chirp 数，T_r 为 chirp 重复周期。增加相干观测时间可提高速度分辨率。" />
    </Section>
    <Section id="noise" number="6.4" title="热噪声与噪声系数">
      <Equation latex="P_n=kTBF,\qquad F=10^{\mathrm{NF}/10}" number="6.6" note="k 为 Boltzmann 常数，T 为接收机温度，B 为噪声带宽，NF 为噪声系数 dB。" />
    </Section>
    <Section id="cfar" number="6.5" title="CA-CFAR 检测">
      <Equation latex="\alpha=N\left(P_{\mathrm{fa}}^{-1/N}-1\right),\qquad T=\alpha\,\overline P_{\mathrm{train}}" number="6.7" note="独立指数噪声假设下的 CA-CFAR 比例因子。训练单元估计背景，保护单元避免目标泄漏污染估计。" />
      <p>减小 <InlineMath latex="P_{\mathrm{fa}}" /> 会提高门限、减少虚警，但也可能漏掉弱目标。检测数量不能单独代表算法更好。</p>
    </Section>
    <Section id="radar-result" number="6.6" title="页面指标怎样读">
      <ParameterTable rows={[
        ['距离分辨率', 'm', 'c/(2B)', '与配置带宽计算值一致'],
        ['速度分辨率', 'm/s', '由载频和相干观测时间决定', '增加 chirp 后应改善'],
        ['路径覆盖率', '%', '进入时域或栅格合成的路径功率比例', '应接近 100%，否则检查 max_synthesis_paths'],
        ['CFAR 检测单元数', '个', '超过自适应检测门限的单元数量', '结合检测位置、门限图和场景解释'],
      ]} />
    </Section>
  </Chapter>
}

function PathsChapter() {
  return <Chapter number="7" title="三维传播路径与统计图" intro="MPC 全景回答能量从哪个方向到达；逐路径检查回答信号具体经过了哪些物体。两类结果互补，但不能混为同一数据产品。" sections={[["path-geometry", "7.1 完整路径"], ["interaction", "7.2 交互类型"], ["selection", "7.3 选中与聚焦"], ["spectra", "7.4 距离角谱"], ["statistics", "7.5 统计口径"]]}>
    <Section id="path-geometry" number="7.1" title="Tx 到 Rx 的完整折线">
      <p>一条路径由 Tx、零个或多个交互点以及 Rx 组成。页面只绘制当前选中的一条完整路径，避免数万条折线同时显示造成遮挡和浏览器负担。</p>
      <Equation latex="L_l=\sum_{q=0}^{Q_l}\left\lVert\mathbf p_{q+1}-\mathbf p_q\right\rVert_2,\qquad \tau_l=\frac{L_l}{c}" number="7.1" note="p_0 为 Tx，p_{Q_l+1} 为 Rx。几何总长度决定传播时延。单站等效距离仍取 cτ/2。" />
    </Section>
    <Section id="interaction" number="7.2" title="镜面反射、漫反射与混合路径">
      <p>镜面反射路径满足几何反射关系；漫反射路径来自粗糙表面散射；混合路径包含多种交互。对象编号来自 Sionna/Mitsuba 场景几何映射。</p>
    </Section>
    <Section id="selection" number="7.3" title="路径选择与场景聚焦">
      <ol className="knowledge-steps"><li><strong>打开路径检查器</strong><span>右侧切换到“路径与对象”。</span></li><li><strong>筛选</strong><span>按镜面、漫反射、混合或门限内状态过滤。</span></li><li><strong>选择路径</strong><span>点击路径行后，场景显示完整折线和交互点。</span></li><li><strong>核对详情</strong><span>比较时延、距离、AoA/AoD、能量、深度和对象。</span></li></ol>
    </Section>
    <Section id="spectra" number="7.4" title="距离-方位与距离-俯仰谱">
      <Equation latex="P[r_i,\phi_j]=\sum_l P_l\,\mathbb 1(R_l\in r_i)\,\mathbb 1(\phi_l\in\phi_j)" number="7.2" note="这是路径功率在距离-角度网格上的直方图。它不是波束扫描得到的高分辨率角谱，也不是 MPC 全景。" />
    </Section>
    <Section id="statistics" number="7.5" title="统计图的口径">
      <ul className="knowledge-checklist"><li>“有效路径总数”来自完整归档统计。</li><li>浏览器路径列表只载入主要路径子集，列表数量不等于原始路径总数。</li><li>对象能量归因在多对象路径中可能采用分摊，仅用于排序。</li><li>发表或定量结论应读取 NPZ/CSV，而不是从柱状图像素估计。</li></ul>
    </Section>
  </Chapter>
}

function DataChapter() {
  return <Chapter number="8" title="批量任务、下载与结果管理" intro="本章说明为什么批量任务可以完成一个下载一个、各种文件的用途，以及实验方案和仿真结果的删除边界。" sections={[["batch", "8.1 批量任务"], ["progress", "8.2 增量发布"], ["download", "8.3 文件选择"], ["bundle", "8.4 结果包大小"], ["delete", "8.5 删除规则"]]}>
    <Section id="batch" number="8.1" title="单测点与多测点任务">
      <p>单测点任务包含一个 pose；campaign 模式可包含多个 pose。每个 pose 有独立运行目录、CIR、路径、MPC 和 FMCW 结果。</p>
      <pre className="knowledge-code"><code>{`"mode": "campaign",
"poses": [
  {"center_m": [0, 0, 10], "look_at_m": [450, 0, 40]},
  {"center_m": [0, 10, 10], "look_at_m": [450, 10, 40]}
]`}</code></pre>
    </Section>
    <Section id="progress" number="8.2" title="完成一个、发布一个">
      <p>GPU 子任务完成后，后端会原子更新结果索引和任务进度。顶部显示已完成数量；后续测点失败不会删除已经完成的结果。</p>
    </Section>
    <Section id="download" number="8.3" title="怎样选择下载文件">
      <table className="knowledge-table"><thead><tr><th>目标</th><th>推荐文件</th><th>是否通常较大</th></tr></thead><tbody>
        <tr><td>训练或分析 MPC</td><td><code>mpc_panorama.npz</code> 或四张视图</td><td>否</td></tr>
        <tr><td>逐路径分析</td><td><code>paths.csv</code> / <code>paths_summary.npz</code></td><td>中等</td></tr>
        <tr><td>重新做阵列相干合成</td><td><code>cir.npz</code></td><td>是</td></tr>
        <tr><td>查看图表与摘要</td><td>轻量分析包</td><td>否</td></tr>
        <tr><td>长期完整复现</td><td>完整科研归档</td><td>是</td></tr>
      </tbody></table>
    </Section>
    <Section id="bundle" number="8.4" title="为什么 CIR 很大">
      <Equation latex="N_{\mathrm{complex}}=N_{\mathrm{Rx}}N_{\mathrm{Tx}}N_{\mathrm{path}}" number="8.1" note="每个阵元对、每条路径都可能保存复系数。complex64 每个数通常占 8 字节；NPZ 已压缩，再套 ZIP 不一定明显变小。" />
    </Section>
    <Section id="delete" number="8.5" title="删除与只读边界">
      <ul className="knowledge-checklist"><li>删除实验方案只删除参数模板，不删除仿真结果。</li><li>删除本地结果会清理运行目录、浏览器数据缓存、下载包和路径导出。</li><li>正在运行的任务不可删除；超过 24 小时的遗留队列状态视为已中断。</li><li>内置示例结果保持只读，不显示删除按钮。</li></ul>
    </Section>
  </Chapter>
}

function ValidationChapter() {
  return <Chapter number="9" title="物理验证、数值验证与故障排查" intro="一张看起来合理的热图并不能证明模型正确。本章给出从几何、能量、收敛到浏览器网络错误的系统检查顺序。" sections={[["geometry-check", "9.1 几何基准"], ["energy-check", "9.2 能量与单位"], ["sampling-check", "9.3 收敛实验"], ["mpc-check", "9.4 MPC 一致性"], ["troubleshooting", "9.5 常见故障"]]}>
    <Section id="geometry-check" number="9.1" title="已知反射面的距离验证">
      <p>先建立一个位置和反射点已知的简单场景，手算 Tx → 反射点 → Rx 的总长度，再与路径时延比较。</p>
      <Equation latex="\varepsilon_L=\frac{|c\tau_l-L_{\mathrm{geom}}|}{\max(L_{\mathrm{geom}},\epsilon)}" number="9.1" note="几何相对误差应接近数值精度和网格误差范围。若误差很大，优先检查单程/双程定义和单位。" />
    </Section>
    <Section id="energy-check" number="9.2" title="功率、幅度和 dB">
      <Equation latex="L_P=10\log_{10}\frac{P_2}{P_1},\qquad L_A=20\log_{10}\frac{A_2}{A_1}" number="9.2" note="功率比用 10log10，幅度比用 20log10。MPC 空间谱遵循第 5 章给出的独立数据定义。" />
      <p>Sionna 路径增益不自动等于校准雷达硬件的绝对接收功率。绝对功率还需要发射功率、天线增益、RCS、系统损耗和噪声带宽口径。</p>
    </Section>
    <Section id="sampling-check" number="9.3" title="射线数与随机种子矩阵">
      <p>建议至少运行“低/高射线数 × 两个随机种子”四组实验，比较主峰距离、总能量、强路径数量和 MPC 未归一化 dB 数组的结构相似性。</p>
    </Section>
    <Section id="mpc-check" number="9.4" title="MPC 实验一致性检查">
      <ul className="knowledge-checklist"><li>对比实验的场景、Tx/Rx 位置、载频和材料一致。</li><li>传播机制、最大深度、射线数和随机种子一致。</li><li>使用相同阵元对的路径系数。</li><li>AoA 的 θ/φ 约定和图像方向一致。</li><li>孔径行列数、间距、窗函数和离散核半径一致。</li><li>跨位置比较时使用相同全局归一化边界。</li></ul>
    </Section>
    <Section id="troubleshooting" number="9.5" title="常见故障">
      <table className="knowledge-table"><thead><tr><th>现象</th><th>优先检查</th><th>处理</th></tr></thead><tbody>
        <tr><td><code>Failed to fetch</code></td><td>API 8000 是否运行、浏览器网络面板状态码</td><td>检查健康接口和后端日志，不要只看扩展脚本报错</td></tr>
        <tr><td>三维场景空白</td><td>浏览器 WebGL、GPU 驱动、控制台</td><td>确认 WebGL 可用并检查场景资源请求</td></tr>
        <tr><td>MPC 全红或全蓝</td><td>归一化上下界与未归一化 dB 分布</td><td>调整显示动态范围；跨位置使用全局边界</td></tr>
        <tr><td>路径数量异常大</td><td>漫反射、最大深度、射线数</td><td>从镜面单反射基线逐项开启机制</td></tr>
        <tr><td>结果无法删除</td><td>是否选择内置示例结果、任务是否仍运行</td><td>切换到本地仿真结果；等待活动任务结束</td></tr>
      </tbody></table>
    </Section>
  </Chapter>
}

function GlossaryChapter() {
  const [query, setQuery] = useState('')
  const terms = useMemo(() => glossary.filter(([term, definition]) => `${term} ${definition}`.toLowerCase().includes(query.toLowerCase())), [query])
  return <Chapter number="附录" title="标准术语索引" intro="本附录用于快速检索。完整推导和平台操作请回到对应编号章节。" sections={[["term-search", "术语检索"]]}>
    <Section id="term-search" number="A.1" title="术语检索">
      <label className="knowledge-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 CIR、AoA、HPBW、FMCW、CFAR" /></label>
      <dl className="glossary-list">{terms.map(([term, definition]) => <div key={term}><dt>{term}</dt><dd>{definition}</dd></div>)}</dl>
    </Section>
  </Chapter>
}

export function KnowledgeCenter({ topic }: { topic: KnowledgeTopic }) {
  return <article className="knowledge-center">
    <div className="knowledge-heading"><BookOpen size={20} /><span>城市雷达仿真原理与操作手册</span></div>
    {topic === 'start' && <StartChapter />}
    {topic === 'geometry' && <GeometryChapter />}
    {topic === 'propagation' && <PropagationChapter />}
    {topic === 'array' && <ArrayChapter />}
    {topic === 'mpc' && <MpcChapter />}
    {topic === 'fmcw' && <FmcwChapter />}
    {topic === 'paths' && <PathsChapter />}
    {topic === 'data' && <DataChapter />}
    {topic === 'validation' && <ValidationChapter />}
    {topic === 'glossary' && <GlossaryChapter />}
  </article>
}
