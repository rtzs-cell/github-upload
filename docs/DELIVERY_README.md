# 雷达仿真平台交付说明

请把本目录中的全部文件一起复制到目标 Linux GPU 服务器。

## 文件用途

- `radar-workbench-docker.tar`：平台、Sionna RT 2.0.1 和全部 Python 依赖。
- `radar-workbench-docker.tar.sha256`：检查大文件是否传输完整。
- `安装说明.md`：完整安装、配置、验证、访问、备份和故障排查手册。
- `快速开始.md`：本文件。

## 安装前必须确认

目标机器需要是带 NVIDIA GPU 的 x86-64 Linux，并已安装：

```text
NVIDIA 驱动
Docker Engine
Docker Compose v2
NVIDIA Container Toolkit
zstd
tar
```

先在目标机器执行：

```bash
nvidia-smi
docker version
docker compose version
nvidia-ctk --version
zstd --version
```

任何命令不存在或报错时，请先交给服务器管理员处理。不要跳过 GPU 容器环境安装。

## 最短安装步骤

假设全部交付文件位于 `/opt/radar-delivery/`：

```bash
cd /opt/radar-delivery
sha256sum -c radar-workbench-docker.tar.sha256
tar -xf radar-workbench-docker.tar
cd radar-workbench-offline
./import_docker_bundle.sh
./start_radar_workbench.sh
./verify_radar_workbench.sh
```

所有步骤成功后，在目标机器打开：

```text
http://127.0.0.1:8000/
```

从自己的电脑访问远程服务器：

```bash
ssh -L 8000:127.0.0.1:8000 用户名@服务器地址
```

保持 SSH 连接，再在自己的浏览器打开 `http://127.0.0.1:8000/`。

## 出错时需要提供的信息

请不要只发送错误截图。进入解压后的 `radar-workbench-offline/`，执行并保存完整输出：

```bash
nvidia-smi
docker version
docker compose version
./verify_radar_workbench.sh
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs --tail=200
```

完整说明参见同目录的 `安装说明.md`。
