# 城市雷达感知仿真前端

这是面向 Sionna RT 自发自收雷达仿真的浏览器前端。

当前功能范围：

1. 加载只读的 C002 城市雷达感知测量数据。
2. 新建两楼远距单站雷达实验草稿，并生成独立的 Sionna/Mitsuba XML 场景和 PLY 网格。
3. 浏览测量记录、雷达位姿、统计指标、传播路径、交互点和距离-角度谱。
4. 三维显示建筑包围盒、雷达位姿、角域分析门限边界、传播路径折线和交互点。
5. 编辑雷达位姿、方位/俯仰角域分析门限、载频、散射模型、天线阵列、数字波束成形和计算参数。
6. 通过拖动方式调整方位角、方位宽度、俯仰角和最大距离，并与三维视图联动。
7. 提交雷达感知仿真任务，并自动加载完成后的结果。
8. 将当前测量记录的筛选路径、雷达参数、元数据和 CSV 路径摘要保存到 `outputs/radar_workbench/path_exports/`。
9. 生成路径统计、接收阵列波束成形分析，并通过浏览器下载完整结果包。

主要归档目录：

```text
outputs/radar_workbench/experiments/      # 实验草稿、输入配置、场景 XML、PLY 网格
outputs/radar_workbench/campaigns/        # Sionna RT 仿真输出
outputs/radar_workbench/result_bundles/   # 浏览器下载 ZIP
outputs/radar_workbench/path_exports/     # 手动保存的路径子集
outputs/radar_workbench/web_cache/        # 前端谱图和路径缓存
```

本地运行：

```bash
npm install
npm run dev
```

推荐从仓库根目录启动完整工作台：

```bash
./scripts/start_radar_workbench.sh
```

前端默认请求同源 `/api`，Vite 开发服务器会代理到后端服务。默认后端为 `http://127.0.0.1:8000`；如需修改，可在启动前设置 `RADAR_API_HOST`、`RADAR_API_PORT` 或 `RADAR_API_PROXY_TARGET`。如果在远程 IDE 或 SSH 端口转发环境中访问，只需要转发并打开前端端口；除非单独配置了 `VITE_RADAR_API_BASE`，浏览器不会再直接请求自己的 `127.0.0.1:8000`。

提交新的 Sionna 射线追踪任务时，后端需要配置 `RADAR_SIONNA_PYTHON` 指向可导入 `sionna.rt` 的 Python 环境。只浏览已有结果、生成路径统计、下载结果包和做 CIR 波束成形后处理时不需要前端直接加载 Sionna。
