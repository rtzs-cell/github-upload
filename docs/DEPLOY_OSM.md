# Radar Workbench 上海 OSM 版部署与使用说明

版本 `0.3.0` · 上海街区框选版 · 2026-11-11

部署包 `radar-workbench-osm-shanghai-0.3.0.zip` 包含源码、已构建的网页、Linux 安装脚本和一个可直接编辑的上海场景。安装完成后，网页和 API 共用一个端口。部署时只需安装 Python 依赖，网页可以直接使用。

## 1. 在 Linux 服务器部署

使用 64 位 Linux、Python 3.10（含 `venv` 和 `pip`）以及 `unzip`。首次安装需要访问 Python 软件包源。运行射线追踪还需要 NVIDIA GPU、可用的驱动和 Sionna RT 2.0.1，安装脚本会安装 Sionna RT。先用 `nvidia-smi` 检查 GPU 是否可用。

把 ZIP 上传到服务器上的新目录，部署路径请使用无空格的目录名。在 ZIP 所在目录执行以下命令。

```bash
unzip -q radar-workbench-osm-shanghai-0.3.0.zip
cd radar_simulate
bash scripts/install_radar_workbench.sh
bash scripts/verify_deployment.sh
bash scripts/start_radar_workbench.sh
```

如果安装提示缺少 `ensurepip`，在 Ubuntu 22.04 上请安装 `python3.10-venv`，或使用已有环境里支持 `venv` 的 Python 3.10。例如用 `PYTHON_COMMAND=/path/to/env/bin/python bash scripts/install_radar_workbench.sh` 替换安装命令。首次失败后，从新解压目录重试。

如果安装反复提示某个软件包镜像无法解析，下面的命令为本次安装指定官方 PyPI。若同时需要换 Python，可在 `bash` 前加上 `PYTHON_COMMAND=/path/to/env/bin/python`。

```bash
env -u PIP_EXTRA_INDEX_URL PIP_CONFIG_FILE=/dev/null \
  PIP_INDEX_URL=https://pypi.org/simple bash scripts/install_radar_workbench.sh
```

只看上海示例、导入或编辑场景时，安装步骤可以用 `bash scripts/install_radar_workbench.sh --without-sionna`。这个模式可在无 GPU 的 Linux 服务器上使用。需要提交新的雷达仿真时，使用上面的完整安装命令。

服务默认监听服务器本机的 `127.0.0.1:8000`。如果同一台机器已运行旧版，安装后先把 `.env.radar` 中的 `RADAR_API_PORT` 改成一个空闲端口，例如 `18000`，再启动。下面的命令和网址也使用同一个端口。

在自己的电脑上打开终端，把 `username@server` 换成服务器的 SSH 登录地址，执行下面的命令并保持连接。

```bash
ssh -N -L 8000:127.0.0.1:8000 username@server
```

然后在自己电脑的浏览器打开工作台。上海示例链接会直接进入场景几何页。[打开工作台](http://127.0.0.1:8000/) · [打开上海示例](http://127.0.0.1:8000/?experiment=exp_20261110_081511_70973cab)

可在服务器上检查服务和 Sionna RT 状态。

```bash
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/health/sionna_runtime
```

停止服务用 `bash scripts/stop_radar_workbench.sh`。启动日志位于 `outputs/radar_workbench/logs/radar_api.log`。实验方案和仿真结果分别保存在 `outputs/radar_workbench/experiments/` 和 `outputs/radar_workbench/campaigns/`。

## 2. 新增和改进的功能

| 功能 | 如何使用 |
| --- | --- |
| 地图框选 | 在「场景几何」点「在地图上框选」。OpenStreetMap 底图显示街道，可拖动、滚轮缩放，再用矩形圈出街区。界面显示选区宽高和经纬度。 |
| 在线获取与文件导入 | 可按地图矩形或中心经纬度加半径在线查询建筑。也可在「本地文件与导出」导入 OSM XML、Overpass JSON、GeoJSON、自定义场景 JSON 或 OBJ、PLY 模型。 |
| 混合场景 | 选「追加到当前场景」保留已有建筑和自定义模型。追加 OSM 数据时沿用已有地图坐标原点，跳过已有的 OSM 建筑编号。选「替换当前建筑」则用新选区替换建筑列表。 |
| 按原始轮廓生成网格 | 建筑底面使用 OSM 闭合轮廓，保存时生成可供 Sionna RT 使用的挤出网格。高度优先取 OSM 高度标注，其次按楼层数估算，两项都缺失时用 12 米。 |
| 场景几何页 | 三维预览自动取景。按建筑名称或 OSM 编号搜索，或直接点选三维建筑，即可编辑位置、尺寸、旋转和材质。导入、撤销和保存都在面板上方。 |

地图矩形的宽和高各限 5 公里，边缘建筑保留完整轮廓。当前在线查询处理 OSM 的建筑和建筑部件轮廓，关系型多边形的洞口暂未单独挤出。

## 3. 用上海示例演示一次

1. 打开「实验方案」，选择「OSM 精确 footprint 示例 · 上海 0.5km」。包内自带 327 栋建筑，打开即可查看三维场景和编辑参数。
2. 在右侧进入「场景几何」，点击「在地图上框选」，再点击「上海人民广场」定位。把地图拖到人民广场东南侧，放大到西藏南路与宁海东路一带。
3. 点击「画矩形」，沿街道拖出选区。复现验证时可参考选框南边纬度 `31.229667`、西边经度 `121.474092`、北边纬度 `31.230971`、东边经度 `121.477278`。界面显示约 `303 m × 144 m`，坐标采用 WGS84。
4. 选择「替换当前建筑」，点击「导入建筑」，即可单独预览这块街区。演示时实测导入 45 栋，在线结果会随 OSM 数据更新。要保留包内示例，可在预览后点击「恢复已保存场景」。要把选区存成自己的方案，可先「新建实验方案」，在新方案中框选并点击「保存场景」。
5. 保存后再次打开地图，蓝色虚线标记上次查询范围。需要跑仿真时，切到「雷达参数」，设置雷达位置、朝向和波形，再提交任务。任务完成后在「仿真结果」查看传播路径、回波与统计图。

预置上海场景在安装完成后可直接查看。在线底图由浏览器访问 `tile.openstreetmap.org`，建筑查询由服务器访问 Overpass。如果地图或查询服务暂时不可达，可使用预置场景，或从「本地文件与导出」导入已有的 OSM、GeoJSON 文件。包内的 `portable_scenes/exp_20261110_081511_70973cab/scene_import.json` 是同一个上海场景的可导入副本。

上海示例包含 OpenStreetMap 数据，数据及其衍生建筑几何遵循 ODbL 1.0。© OpenStreetMap contributors。[数据署名](https://www.openstreetmap.org/copyright) · [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)

## 4. 部署验证

已在 H100 的独立解压目录用 Python 3.10 和 Sionna RT 2.0.1 完整安装并启动。浏览器能打开 327 栋建筑的上海示例，加载带街名的底图并画出选框。Sionna RT 从迁移后的场景文件读入了 327 栋建筑和地面网格。部署与 OSM 导入关键测试共 13 项通过。

另外用界面创建并切换了内置“街谷”场景。该场景包含 4 栋建筑，三维预览、建筑参数选择、场景切换和 Sionna RT 场景读取均通过。测试用的临时方案已经清理，部署后只保留上海示例。

包内 `docs/USER_GUIDE.md` 提供完整功能说明。源码版本与 GitHub 的上海地图改版对应。[查看源码提交](https://github.com/rtzs-cell/github-upload/commit/0428b62eb61775a12779260f7c29b937976b034e)
