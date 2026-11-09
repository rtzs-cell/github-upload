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

## 打包迁移

推荐使用 Git bundle 进行首次源码交付和后续离线增量更新：

```bash
./scripts/create_git_bundle.sh
```

目标机从完整 bundle 克隆一次；后续版本使用 `--from-tag` 生成小型增量包，并通过 `scripts/apply_git_bundle.sh` 校验、更新和失败回滚。完整命令参见 [Git 增量更新指南](docs/GIT_UPDATE_GUIDE.md)。

传统源码压缩包仍可用于不保留 Git 历史的一次性迁移：

最小代码包：

```bash
./scripts/package_radar_workbench.sh
```

携带可编辑实验方案与本地仿真结果：

```bash
./scripts/package_radar_workbench.sh --with-local-data
```

大型内置示例结果默认不打包，需要时显式增加 `--with-example-data`。完整步骤、远程访问、备份和升级方法参见 [部署指南](docs/DEPLOYMENT_GUIDE.md)。

Docker GPU 镜像与离线迁移包：

```bash
./scripts/build_docker_image.sh
./scripts/export_docker_bundle.sh
```

Docker 构建严格排除现有实验方案、仿真结果、示例数据、缓存和日志。目标机只会创建一个新的 `radar-data/` 目录保存之后生成的结果。

## 项目结构

```text
apps/radar-workbench/        React + TypeScript 界面
services/radar_api/          FastAPI 服务
experiments/sionna_radar/    Sionna RT 仿真与后处理
scripts/                     安装、启动、验证和迁移脚本
docs/                        使用、原理和部署文档
outputs/                     实验方案、结果和可再生缓存
```

Sionna RT 的直接依赖锁定在 `experiments/sionna_radar/requirements-runtime.txt`。运行时版本与模块来源可通过以下地址检查：

```bash
curl http://127.0.0.1:8000/api/health/sionna_runtime
```

## 文档入口

- [更新摘要](docs/UPDATE_SUMMARY.md)：阵列、场景、发射波束、撤回与失败恢复更新。
- [使用教程](docs/USER_GUIDE.md)：从建立方案到读取和下载结果。
- [原理与结果解读](docs/RADAR_WORKBENCH_TUTORIAL.md)：传播路径、MPC、波束形成、FMCW 与可信度验证。
- [阵列与信道维度说明](docs/CIR_ARRAY_LAYOUT_GUIDE.md)：合成阵列近似、逐阵元路径求解、信道维度和存储格式。
- [阵列坐标与阵元编号](docs/RADAR_ARRAY_COORDINATE_AND_INDEXING.md)：阵面朝向、收发中心、阵元位置和二百五十六通道编号。
- [术语与公式](docs/RADAR_GLOSSARY.md)：专业名词、定义和公式。
- [部署指南](docs/DEPLOYMENT_GUIDE.md)：最小打包、迁移、安装、远程访问和备份。
- [Git 增量更新](docs/GIT_UPDATE_GUIDE.md)：完整 bundle、增量发布、目标机更新和回滚。
- [开发交接](docs/RADAR_WORKBENCH_HANDOVER.md)：模块、API 与数据结构。

## 验证

```bash
npm -C apps/radar-workbench run build
PYTHONPATH=experiments/sionna_radar/src python -m pytest -q services/radar_api/tests
git diff --check
```

生成数据不纳入 Git。正式实验应保留完整配置、随机种子、运行时版本和原始结果文件，以保证结果可追溯。
