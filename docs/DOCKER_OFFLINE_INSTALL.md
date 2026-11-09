# 雷达仿真平台 Docker 离线安装手册

最后更新：2026-07-11

本文面向目标服务器管理员和平台使用者。按照章节顺序执行，即可在不访问 Docker Hub、不重新下载 Python 依赖的情况下安装雷达仿真平台。

离线包不包含源机器上的实验方案、仿真结果、示例结果、缓存和日志。目标机器将从空的数据目录开始。

## 1. 部署结构

平台使用一个 GPU 容器：

```text
浏览器
  |
目标机 8000 端口
  |
FastAPI + 已构建前端 + Sionna RT 2.0.1
  |
NVIDIA Container Toolkit
  |
宿主机 NVIDIA 驱动和 GPU
```

新生成的数据保存在宿主机的 `radar-data/`，不会写入镜像。更新或删除容器不会自动删除该目录。

## 2. 离线包内容

解压后应看到：

```text
radar-workbench-offline/
├── INSTALL.md
├── SHA256SUMS
├── .env.docker
├── compose.yaml
├── import_docker_bundle.sh
├── start_radar_workbench.sh
├── stop_radar_workbench.sh
├── verify_radar_workbench.sh
├── radar-workbench-image.tar.zst
└── radar-workbench-source.tar.zst
```

- `radar-workbench-image.tar.zst`：完整应用镜像，包含 Sionna RT 和全部 Python 依赖。
- `radar-workbench-source.tar.zst`：不含历史结果的源码、Docker 配置和项目文档，用于维护或重新构建。
- `SHA256SUMS`：包内大文件完整性校验。
- `.env.docker`：端口、GPU 和数据目录配置。
- `compose.yaml`：容器运行定义。
- 四个脚本分别用于导入、启动、停止和验证。

## 3. 目标机器要求

### 3.1 硬件和系统

推荐配置：

- x86-64 Linux，建议 Ubuntu 22.04 或 24.04；
- NVIDIA GPU；
- 与 GPU 匹配的 NVIDIA 驱动；
- 至少 5GB 可用系统盘空间；
- 根据新仿真规模准备独立的数据盘空间；
- 默认端口 `8000` 未被其他程序占用。

当前镜像在 NVIDIA H100、驱动 `535.230.02` 上完成 CUDA 验证。其他受驱动和 Sionna RT 支持的 NVIDIA GPU仍需在目标机运行第 9 节测试。

### 3.2 必需软件

目标机必须预先安装：

```text
Docker Engine
Docker Compose v2 插件
NVIDIA Container Toolkit
zstd
tar
```

检查命令：

```bash
nvidia-smi
docker version
docker compose version
nvidia-ctk --version
zstd --version
tar --version
```

其中任意一项不存在都应先完成系统软件安装。应用离线包不修改宿主机驱动、Docker 服务或系统软件源。

### 3.3 Ubuntu 上安装基础工具

目标机可联网并已配置适用软件源时，可以先尝试：

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 zstd
sudo systemctl enable --now docker
```

如果发行版仓库没有 `docker-compose-v2`，应按照 Docker 官方文档安装 Docker Engine 和 Compose 插件，不要安装已经停止维护的 Python 版 `docker-compose`。

安装 NVIDIA Container Toolkit 后执行：

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

允许当前用户运行 Docker：

```bash
sudo usermod -aG docker "$USER"
```

随后注销并重新登录。将用户加入 `docker` 组等同于授予较高的宿主机权限，只应对可信管理员或使用者执行。

目标机完全离线且尚未安装上述系统软件时，需要按目标系统版本另行准备 Docker、Compose、NVIDIA Container Toolkit 和依赖包；不能直接复用其他 Linux 版本的软件包。

## 4. 传输文件

需要传输两个文件：

```text
radar-workbench-docker.tar
radar-workbench-docker.tar.sha256
```

通过 SSH 传输示例：

```bash
scp radar-workbench-docker.tar \
    radar-workbench-docker.tar.sha256 \
    user@target:/opt/
```

也可以使用移动硬盘或内网文件服务。传输过程中不要修改文件名，否则需要相应修改校验文件中的名称。

## 5. 校验外层迁移包

登录目标机：

```bash
ssh user@target
cd /opt
sha256sum -c radar-workbench-docker.tar.sha256
```

预期输出：

```text
radar-workbench-docker.tar: OK
```

如果显示 `FAILED`，说明文件不完整或已被改变，应重新传输，不要继续导入。

## 6. 解压并导入镜像

```bash
cd /opt
tar -xf radar-workbench-docker.tar
cd radar-workbench-offline
./import_docker_bundle.sh
```

导入脚本会：

1. 使用 `SHA256SUMS` 校验镜像和源码归档；
2. 解压镜像流并执行 `docker load`；
3. 创建空的 `radar-data/` 目录；
4. 打印后续启动命令。

检查镜像：

```bash
docker image inspect localhost/radar-workbench:2.0.1 \
  --format '镜像={{index .RepoTags 0}} 大小={{.Size}} 字节'
```

当前验证镜像展开大小约为 `1.11GiB`。

## 7. 配置平台

打开 `.env.docker`：

```bash
nano .env.docker
```

默认配置：

```text
RADAR_IMAGE=localhost/radar-workbench:2.0.1
RADAR_VERSION=2.0.1
RADAR_PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.10-slim-bookworm
RADAR_BIND_ADDRESS=127.0.0.1
RADAR_PORT=8000
RADAR_GPU_IDS=0
RADAR_DATA_DIR=./radar-data
```

### 7.1 GPU

只允许使用第一张 GPU：

```text
RADAR_GPU_IDS=0
```

允许任务调度到两张 GPU：

```text
RADAR_GPU_IDS=0,1
```

这些编号是容器内可见的 GPU 编号。Compose 默认把所有 NVIDIA GPU 提供给容器，再由平台限制可调度编号。

### 7.2 端口和访问范围

只允许目标机本机和 SSH 隧道访问，推荐：

```text
RADAR_BIND_ADDRESS=127.0.0.1
RADAR_PORT=8000
```

可信局域网直接访问：

```text
RADAR_BIND_ADDRESS=0.0.0.0
```

当前平台没有面向公网的身份认证和 TLS。不得直接将 `0.0.0.0:8000` 暴露到互联网。

### 7.3 数据目录

默认使用安装目录下的：

```text
RADAR_DATA_DIR=./radar-data
```

使用独立数据盘：

```text
RADAR_DATA_DIR=/data/radar-workbench
```

先创建目录并确认当前用户可写：

```bash
mkdir -p /data/radar-workbench
test -w /data/radar-workbench
```

## 8. 启动

推荐使用包内脚本：

```bash
./start_radar_workbench.sh
```

脚本会自动使用当前用户 UID/GID、创建数据目录、执行 `docker compose up`，并等待健康检查接口响应。

等效的手动命令：

```bash
RADAR_UID=$(id -u) RADAR_GID=$(id -g) \
  docker compose --env-file .env.docker up -d --no-build
```

查看状态和日志：

```bash
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs --tail=100
```

## 9. 部署验证

运行完整验证脚本：

```bash
./verify_radar_workbench.sh
```

它会检查：

- Docker 和 Compose；
- NVIDIA 驱动；
- 镜像是否存在；
- Sionna RT、Mitsuba 和 Dr.Jit 导入；
- 容器内 CUDA 后端和 GPU 数值计算；
- Compose 配置；
- 已启动服务的健康检查。

手动检查 API：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/health/sionna_runtime
```

运行时探针应包含：

```text
available=true
path_solver_available=true
sionna_rt=2.0.1
mitsuba=3.8.0
drjit=1.3.1
```

## 10. 打开界面

在目标机桌面浏览器中打开：

```text
http://127.0.0.1:8000/
```

目标机是远程服务器时，在自己的电脑执行：

```bash
ssh -L 8000:127.0.0.1:8000 user@target
```

保持 SSH 会话连接，然后在自己的浏览器打开：

```text
http://127.0.0.1:8000/
```

## 11. 停止和重新启动

停止：

```bash
./stop_radar_workbench.sh
```

重新启动：

```bash
./start_radar_workbench.sh
```

查看持续日志：

```bash
docker compose --env-file .env.docker logs -f
```

删除容器但保留数据：

```bash
docker compose --env-file .env.docker down
```

不要随意执行 `docker system prune --volumes`。平台使用绑定目录保存数据，但该命令还可能删除机器上其他项目的资源。

## 12. 数据与备份

平台新数据位于 `.env.docker` 的 `RADAR_DATA_DIR`。默认目录结构：

```text
radar-data/
├── experiments/
├── campaigns/
├── jobs/
├── logs/
├── path_exports/
├── result_bundles/
└── web_cache/
```

备份前停止平台：

```bash
./stop_radar_workbench.sh
tar --zstd -cf radar-data-$(date +%F).tar.zst radar-data
```

恢复时先停止平台，再把数据解压到 `.env.docker` 指定的位置，并确认目录归当前运行用户所有。

## 13. 更新

收到新版离线包后：

1. 停止旧容器；
2. 备份 `RADAR_DATA_DIR`；
3. 校验并解压新版迁移包到新目录；
4. 导入新版镜像；
5. 根据需要把新版 `.env.docker` 指向原数据目录；
6. 启动并运行完整验证；
7. 确认无误后再删除旧镜像。

历史仿真结果是不可变快照。升级程序不应原地改写已经完成结果的配置和元数据。

## 14. 常见故障

### 14.1 `permission denied` 访问 Docker

检查：

```bash
groups
ls -l /var/run/docker.sock
```

确认当前用户在 `docker` 组并重新登录，或者由管理员使用适当权限执行。

### 14.2 `could not select device driver` 或找不到 GPU

执行：

```bash
nvidia-smi
nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
./verify_radar_workbench.sh
```

宿主机 `nvidia-smi` 失败时先修复驱动。

### 14.3 端口被占用

```bash
ss -ltnp | grep ':8000 '
```

在 `.env.docker` 中修改：

```text
RADAR_PORT=8010
```

随后重新启动并访问 `http://127.0.0.1:8010/`。

### 14.4 服务启动但页面打不开

```bash
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs --tail=200
curl -v http://127.0.0.1:8000/api/health
```

远程访问还应检查 SSH 端口转发是否保持连接。

### 14.5 镜像校验失败

不要尝试修补压缩包。重新传输外层迁移包，并再次执行外层和内层 SHA-256 校验。

### 14.6 能打开界面但不能仿真

运行：

```bash
./verify_radar_workbench.sh
curl http://127.0.0.1:8000/api/health/sionna_runtime
```

重点检查 GPU 容器运行时、允许的 GPU 编号和 Sionna RT 运行时探针。

## 15. 源码归档

正常安装不需要解压 `radar-workbench-source.tar.zst`。需要审查或重新构建时执行：

```bash
tar --zstd -xf radar-workbench-source.tar.zst
cd radar_simulate
```

源码归档不包含任何旧仿真结果。重新构建镜像：

```bash
CONTAINER_CLI=docker ./scripts/build_docker_image.sh
```

默认基础镜像来自：

```text
public.ecr.aws/docker/library/python:3.10-slim-bookworm
```

该地址是 AWS 公共容器仓库中的 Docker 官方 Python 镜像副本，用于避免直接访问 Docker Hub。
