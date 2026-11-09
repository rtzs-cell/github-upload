# 雷达仿真平台打包与迁移部署指南

最后更新：2026-08-04

本文说明如何以尽可能小的传输量和目标机依赖，将平台迁移到另一台 Linux 机器。默认方案使用项目内的 Python 虚拟环境，并由 FastAPI 在一个端口同时提供界面和 API；目标机不需要 Node.js。

## 1. 先选择部署方式

| 目标 | 源机器打包命令 | 包含内容 | 适用情况 |
|---|---|---|---|
| 安装新平台 | `./scripts/package_radar_workbench.sh` | 源码、教程、已构建界面 | 推荐，体积最小 |
| 继续已有实验 | `./scripts/package_radar_workbench.sh --with-local-data` | 上述内容、实验方案、本地仿真结果 | 换机器继续工作 |
| 携带单个可编辑场景 | `./scripts/package_radar_workbench.sh --with-experiment EXPERIMENT_ID` | 全部源码、文档、指定实验方案、便携场景 JSON | 交付源码和一个可复现实验场景 |
| 携带内置示例结果 | 增加 `--with-example-data` | 上述内容、大型只读示例数据 | 离线演示或结果复核 |
| 后续增量更新 | `./scripts/create_git_bundle.sh --from-tag ...` | 两个发布版本之间的 Git 对象 | 已用 Git bundle 安装的平台 |

默认包不包含 `node_modules`、Web 缓存、日志、Python 缓存和重复生成的 ZIP。Web 缓存与结果包可在目标机按需重建。大型示例数据只有明确指定时才会加入。

如果只需要浏览已有结果，不需要在目标机运行 Sionna RT，可使用“结果浏览模式”。它不安装 Sionna RT，下载量、安装时间和显存要求都更低。

## 2. 目标机器要求

最低要求：

- 64 位 Linux；
- Python 3.10 或更高版本，包含 `venv`；
- `tar` 与 Zstandard 支持；
- 足够存放所选数据包及新结果的磁盘空间。

运行新仿真还需要：

- NVIDIA GPU 和兼容驱动；
- 可安装 `sionna-rt==2.0.1` 及其依赖的 Python 环境；
- 与任务规模相符的显存和磁盘空间。

只浏览结果不要求 NVIDIA GPU。界面已随包构建，正常部署不要求 Node.js。

## 3. 在源机器打包

先确认没有必须等待完成的仿真任务，然后在项目根目录执行：

```bash
./scripts/package_radar_workbench.sh
```

指定输出位置：

```bash
./scripts/package_radar_workbench.sh \
  --output /path/to/radar-workbench.tar.zst
```

需要带走自己的实验方案和结果：

```bash
./scripts/package_radar_workbench.sh \
  --with-local-data \
  --output /path/to/radar-workbench-with-data.tar.zst
```

不要为了“完整”默认携带内置示例结果。它占用大量传输和存储空间，并不影响创建新实验或运行新仿真。

只携带一个可编辑实验场景：

```bash
./scripts/package_radar_workbench.sh \
  --with-experiment exp_20260804_023741_89627b03 \
  --output /path/to/radar-workbench-source-and-scene.tar.zst
```

该方式不会加入大型历史仿真结果。压缩包中既包含完整实验目录，也包含 `portable_scenes/<实验编号>/scene_import.json`。前者在安装时自动重定位并出现在实验方案列表；后者可以通过“场景几何”中的“导入场景 JSON”导入任意实验方案。

打包脚本会同时生成同名 `.sha256` 文件。传输和解压前执行：

```bash
sha256sum -c radar-workbench-source-and-scene.tar.zst.sha256
```

## 4. 传输、解压与安装

将压缩包传到目标机后执行：

```bash
tar --zstd -xf radar-workbench.tar.zst
cd radar_simulate
./scripts/install_radar_workbench.sh
```

安装程序会：

1. 创建项目私有的 `.venv`；
2. 安装 API 和 Sionna RT 依赖；
3. 生成单端口部署配置 `.env.radar`；
4. 检测可用 GPU 编号；
5. 将可编辑实验方案中的绝对场景路径重定位到新目录。

只浏览结果时使用：

```bash
./scripts/install_radar_workbench.sh --without-sionna
```

该模式可以查看已迁移的路径、MPC、统计图和可下载文件，但不能提交新的射线追踪仿真。

## 5. 启动与验证

```bash
./scripts/verify_deployment.sh
./scripts/start_radar_workbench.sh
```

默认访问地址：

```text
http://127.0.0.1:8000/
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/health/sionna_runtime
```

停止服务：

```bash
./scripts/stop_radar_workbench.sh
```

日志位于 `outputs/radar_workbench/logs/`。

## 6. 从自己的电脑访问远程机器

优先使用 SSH 端口转发。服务仍只监听远程机的本地地址，不需要开放防火墙端口：

```bash
ssh -L 8000:127.0.0.1:8000 user@server
```

然后在自己的浏览器打开 `http://127.0.0.1:8000/`。

仅在可信局域网内需要直接访问时，修改 `.env.radar`：

```text
RADAR_API_HOST=0.0.0.0
```

重启后通过 `http://服务器地址:8000/` 访问。`0.0.0.0` 会让服务监听所有网络接口；当前平台没有面向公网的用户认证、访问控制和 TLS，不能直接暴露到互联网。公网部署应在前面配置带身份认证和 HTTPS 的反向代理。

## 7. 数据目录与低成本存储

主要持久数据位于：

```text
outputs/radar_workbench/experiments/   可编辑实验方案
outputs/radar_workbench/campaigns/     已完成仿真结果
outputs/radar_workbench/path_exports/  用户保存的路径导出
```

以下内容可重新生成，迁移和备份时通常可以排除：

```text
outputs/radar_workbench/web_cache/
outputs/radar_workbench/logs/
outputs/radar_workbench/result_bundles/
apps/radar-workbench/node_modules/
```

也可以把新结果放到独立的大容量磁盘。在 `.env.radar` 中设置：

```text
RADAR_OUTPUT_ROOT=/data/radar-workbench
```

内置示例数据位于其他磁盘时可设置：

```text
RADAR_EXAMPLE_DATA_ROOT=/data/example-results
```

## 8. 备份与升级

使用 Git bundle 安装的平台，优先采用 [Git 增量更新指南](GIT_UPDATE_GUIDE.md) 中的校验、自动更新和失败回滚流程。Git 只管理源码和预构建界面，不会把 `outputs/`、`.env.radar`、`.venv` 或日志放进更新包。

备份前停止服务，至少保留实验方案、本地仿真结果和路径导出：

```bash
./scripts/stop_radar_workbench.sh
./scripts/package_radar_workbench.sh \
  --with-local-data \
  --output /backup/radar-workbench-$(date +%F).tar.zst
```

升级建议采用新目录并行安装：

1. 备份旧目录的数据；
2. 将新版代码包解压到新目录；
3. 把三个持久数据目录迁入新版，或继续使用同一个 `RADAR_OUTPUT_ROOT`；
4. 运行安装脚本和部署验证；
5. 确认历史结果可读、新实验可创建后，再下线旧目录。

历史仿真结果中的配置和元数据不会在迁移时被改写。路径重定位脚本只更新仍可编辑的实验方案，避免改变已经完成结果的可追溯性。

## 9. 常见故障

### 页面打不开

依次检查：

```bash
./scripts/verify_deployment.sh
curl http://127.0.0.1:8000/api/health
tail -100 outputs/radar_workbench/logs/radar_api.log
```

### 能浏览但不能运行仿真

检查 `.env.radar` 中是否存在 `RADAR_SIONNA_PYTHON`，再查看运行时探针和 NVIDIA 驱动：

```bash
curl http://127.0.0.1:8000/api/health/sionna_runtime
nvidia-smi
```

### 迁移后实验方案找不到场景

重新执行：

```bash
.venv/bin/python scripts/rebase_radar_paths.py --repo .
```

该命令只处理可编辑实验方案，不修改历史结果。

## 10. Docker 离线迁移

当前项目提供 GPU Docker 镜像。镜像不包含任何现有实验方案、仿真结果、示例结果、缓存或日志。目标机上的 `radar-data/` 从空目录开始，只保存部署后新生成的数据。

### 10.1 目标机前置条件

目标机必须安装 NVIDIA 驱动、Docker Engine、Docker Compose 插件、NVIDIA Container Toolkit 和 `zstd`。先验证 GPU 容器：

```bash
docker run --rm --gpus all \
  nvidia/cuda:12.4.1-base-ubuntu22.04 \
  nvidia-smi
```

该命令失败时应先修复驱动或 NVIDIA Container Toolkit，不能通过修改平台代码解决。

### 10.2 源机器构建

```bash
./scripts/build_docker_image.sh
```

默认镜像名为 `radar-workbench:2.0.1`。构建采用 Python slim 基础镜像，不包含 TensorFlow、Jupyter 和 cuDNN 开发环境。构建完成后可查看展开大小：

```bash
docker image inspect radar-workbench:2.0.1 \
  --format '{{.Size}}'
```

默认从当前网络可访问的 AWS 公共容器仓库读取 Docker 官方 Python 镜像：

```text
public.ecr.aws/docker/library/python:3.10-slim-bookworm
```

如该仓库不可达，可通过 `RADAR_PYTHON_IMAGE` 使用已经审核并缓存的等价 Python 3.10 slim 镜像。不要基于现有大型 TensorFlow/Jupyter 镜像构建。

### 10.3 生成离线迁移包

```bash
./scripts/export_docker_bundle.sh \
  --output /path/radar-workbench-docker.tar
```

离线包包含：

```text
radar-workbench-offline/
├── radar-workbench-image.tar.zst
├── SHA256SUMS
├── compose.yaml
├── .env.docker
└── import_docker_bundle.sh
```

外层 `.tar` 不再重复压缩已经过 Zstandard 压缩的镜像。当前验证构建的离线包为 `283MB`，导入后的镜像展开占用约 `1.11GiB`。镜像内容或依赖版本变化后，大小也会相应变化。

### 10.4 目标机导入并启动

```bash
tar -xf radar-workbench-docker.tar
cd radar-workbench-offline
./import_docker_bundle.sh
RADAR_UID=$(id -u) RADAR_GID=$(id -g) \
  docker compose --env-file .env.docker up -d --no-build
```

检查状态：

```bash
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs --tail=100
curl http://127.0.0.1:8000/api/health
```

访问 `http://127.0.0.1:8000/`。远程使用仍推荐 SSH 端口转发。停止服务：

```bash
docker compose --env-file .env.docker down
```

`down` 不会删除宿主机的 `radar-data/`。不要使用不理解影响范围的批量 volume 清理命令。

### 10.5 修改 GPU 和网络

编辑 `.env.docker`：

```text
RADAR_GPU_IDS=0,1
RADAR_BIND_ADDRESS=127.0.0.1
RADAR_PORT=8000
RADAR_DATA_DIR=./radar-data
```

`RADAR_GPU_IDS` 是平台允许调度的容器内 GPU 编号，默认只使用 GPU 0。只有在可信局域网内才将 `RADAR_BIND_ADDRESS` 改为 `0.0.0.0`；当前服务不能未经认证直接暴露到公网。
