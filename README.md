# Radar Simulate

基于 Sionna RT 2.0.1 的城市雷达传播与信号处理平台，提供场景编辑、射线追踪、传播路径检查、MPC、阵列波束形成、FMCW 距离-Doppler、CFAR 和分项结果下载。 场景编辑器支持 OSM/GeoJSON 建筑面、OBJ/PLY 模型、自定义场景 JSON，以及追加形成混合场景。

## 快速启动

首次安装：

```bash
./scripts/install_radar_workbench.sh
./scripts/verify_deployment.sh
./scripts/start_radar_workbench.sh
```

打开 `http://127.0.0.1:8000/`。部署模式由 FastAPI 同时提供界面和 API，只使用一个端口，目标机不需要 Node.js。

只安装已有结果浏览功能：

```bash
./scripts/install_radar_workbench.sh --without-sionna
```

停止服务：

```bash
./scripts/stop_radar_workbench.sh
```

开发前端时可将 `.env.radar` 中的 `RADAR_UI_MODE` 改为 `dev`，此时界面和 API 默认分别使用 `5173` 与 `8000` 端口。

## 项目结构

```text
apps/radar-workbench/        React + TypeScript 界面
services/radar_api/          FastAPI 服务
experiments/sionna_radar/    Sionna RT 仿真与后处理
scripts/                     安装、启动、验证和迁移脚本
docs/                        使用、原理和部署文档
```

## 场景导入

场景编辑器支持 OSM XML、Overpass JSON、GeoJSON 建筑面、OBJ/PLY 模型和自定义场景 JSON。OSM/GeoJSON 可追加到当前场景形成混合场景，也可以替换当前建筑。详见 [项目技术说明](docs/PROJECT_TECHNICAL_NOTE.md) 和 [使用教程](docs/USER_GUIDE.md)。

## 验证

```bash
npm -C apps/radar-workbench run build
PYTHONPATH=experiments/sionna_radar/src python -m pytest -q services/radar_api/tests
git diff --check
```

生成数据不纳入 Git。正式实验应保留完整配置、随机种子、运行时版本和原始结果文件，以保证结果可追溯。
